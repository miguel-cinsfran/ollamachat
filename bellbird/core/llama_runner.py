"""Spawn and probe the local llama-server process.

This module is intentionally wx-free so it can be unit-tested
in environments that do not have wxPython installed (e.g. WSL during
development). It returns plain ``(ok, message)`` tuples; the UI layer
in ``MainWindow`` is responsible for announcing the message via
``Speech`` and updating the status bar.

Platform notes
--------------
- On Windows, ``subprocess.Popen`` is called with ``creationflags =
  0x08000000`` (``CREATE_NO_WINDOW``) so a console window does not
  flash when the user clicks the "Iniciar servidor" button.
- On Linux / macOS the same ``llama-server`` command is used; the
  subprocess inherits the terminal's stdio, which is fine during dev.
"""

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from bellbird.core.llama_client import LlamaClient
from bellbird.core.startup import parse_stderr_line


# Module-level state for tracked server process.
# _lock guards mutation of _server_process across threads.
# RLock allows re-entrant acquisition (start_server calls stop_server while holding the lock).
_server_process: subprocess.Popen | None = None
_lock = threading.RLock()

# Windows subprocess creation flag: prevents a console window from
# flashing when the spawned process is started.
_CREATE_NO_WINDOW = 0x08000000

# Poll interval for server startup checks.
_POLL_INTERVAL_SECONDS = 0.2

# Timeout for graceful shutdown (terminate -> kill fallback).
_STOP_TIMEOUT_SECONDS = 5.0


def find_llama_server() -> str | None:
    """Locate the llama-server binary on PATH.

    Returns:
        Absolute path to llama-server (or .exe on Windows), or None
        if not found. Does not raise.
    """
    found = shutil.which("llama-server")
    if found is None:
        return None
    return str(Path(found).resolve())


def _is_windows() -> bool:
    """Return True if the current platform is Windows.

    Extracted as a function so tests can mock it without triggering
    pathlib.WindowsPath instantiation in non-Windows environments.
    """
    return os.name == "nt"


def _get_standard_paths() -> list[str]:
    """Return the list of standard model paths on Windows.

    Returns absolute path strings. Returns [] on non-Windows platforms.
    Extracted as a function so tests can mock it.
    """
    if not _is_windows():
        return []
    home = os.path.expanduser("~")
    paths = [
        os.path.join(home, "models"),
        os.path.join(home, "Downloads"),
        os.path.join(home, ".cache", "huggingface", "hub"),
        os.path.join(home, ".lmstudio", "models"),
    ]
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        paths.append(os.path.join(local_app_data, "nomic.ai", "GPT4All"))
    return paths


def find_gguf_models(extra_paths: list[str] | None = None) -> list[str]:
    """Scan standard locations for .gguf model files.

    On Windows, scans the standard paths (returned by
    :func:`_get_standard_paths`) plus any caller-provided ``extra_paths``.
    The HuggingFace cache is scanned recursively to depth 5; all other
    locations are scanned non-recursively.

    On non-Windows, returns [] (per REQ-LLAMA-006: the function is
    platform-aware and the standard Windows paths are absent on Linux
    / WSL). This keeps the behavior deterministic in CI.

    The scan uses ``os.path`` and ``os.scandir`` so it does not depend
    on the pathlib Path class flavor. This matters for tests that
    simulate a Windows environment on a POSIX host.

    Returns:
        Sorted list of absolute .gguf paths, deduplicated. Never raises.
    """
    # REQ-LLAMA-006: on non-Windows the function MUST return [].
    if not _is_windows():
        return []

    # Build (path, recursive) list. The HuggingFace cache is at index 2
    # in the standard paths and is the only recursive one.
    paths_to_scan: list[tuple[str, bool]] = [
        (p, i == 2) for i, p in enumerate(_get_standard_paths())
    ]
    if extra_paths:
        for p in extra_paths:
            paths_to_scan.append((p, False))

    collected: set[str] = set()
    for dir_path, recursive in paths_to_scan:
        if not os.path.isdir(dir_path):
            continue
        if recursive:
            _scan_recursive_os(dir_path, collected, current_depth=0, max_depth=5)
        else:
            _scan_non_recursive_os(dir_path, collected)

    return sorted(collected, key=lambda p: os.path.basename(p).lower())


def _scan_non_recursive_os(dir_path: str, collected: set[str]) -> None:
    """Add .gguf files from a single directory (non-recursive)."""
    try:
        with os.scandir(dir_path) as it:
            for entry in it:
                if entry.is_file() and entry.name.lower().endswith(".gguf"):
                    collected.add(os.path.abspath(entry.path))
    except OSError:
        pass


def _scan_recursive_os(
    dir_path: str, collected: set[str], current_depth: int, max_depth: int
) -> None:
    """Recursively add .gguf files, up to a given depth."""
    if current_depth > max_depth:
        return
    try:
        with os.scandir(dir_path) as it:
            for entry in it:
                if entry.is_file() and entry.name.lower().endswith(".gguf"):
                    collected.add(os.path.abspath(entry.path))
                elif entry.is_dir() and current_depth < max_depth:
                    _scan_recursive_os(
                        entry.path, collected, current_depth + 1, max_depth
                    )
    except OSError:
        pass


def start_server(
    model_path: str,
    client: LlamaClient,
    port: int = 8080,
    ctx_size: int = 4096,
    n_gpu_layers: int = 99,
    timeout: float = 60.0,
) -> tuple[bool, str]:
    """Start llama-server with the given model.

    (1) Calls stop_server() unconditionally (idempotent).
    (2) Fast-path: if client.check_running() returns True, returns
        (True, "ya está corriendo") without spawning.
    (3) Spawns subprocess.Popen with the documented argv, capturing
        stderr via PIPE instead of DEVNULL.
    (4) Starts a daemon thread that reads stderr lines and classifies
        them via ``core.startup.parse_stderr_line``. On FAIL the
        process is terminated and the reason is returned early.
    (5) Polls client.check_state() every 0.2s for up to timeout seconds.
    (6) Returns (True, "Servidor listo") on success or (False, reason)
        on failure.

    Args:
        model_path: Absolute path to the .gguf file.
        client: LlamaClient instance for health polling.
        port: Server port (default 8080).
        ctx_size: Context size in tokens (default 4096).
        n_gpu_layers: GPU layers offload (default 99 = all).
        timeout: Maximum seconds to wait for the server to start.

    Returns:
        (ok, message) tuple.
    """
    global _server_process

    with _lock:
        # Step 1: Stop any tracked process first
        stop_server()

        # Step 2: Fast-path - server already running
        if client.check_running():
            return True, "El servidor ya está corriendo"

        # Step 3: Build argv
        argv = [
            "llama-server",
            "--model", model_path,
            "--port", str(port),
            "--host", "127.0.0.1",
            "--ctx-size", str(ctx_size),
            "--n-gpu-layers", str(n_gpu_layers),
            "--jinja",
        ]

        # Step 4: Spawn — capture stderr so we can detect known errors
        # early instead of waiting the full polling timeout.
        kwargs: dict = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.PIPE,
            "stdin": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = _CREATE_NO_WINDOW

        try:
            _server_process = subprocess.Popen(argv, **kwargs)
        except FileNotFoundError:
            return False, "No se encontró llama-server"
        except OSError as e:
            return False, f"No se pudo iniciar el servidor: {e}"

        # B1: detect immediate death. llama-server can exit instantly
        # when the model file is unreadable, the port is busy, or any
        # other startup error. Polling /health for 60s in that case
        # would be a very long wait for an obvious failure.
        # Give the process a short grace period (1s) to either stay
        # alive or surface its error.
        if _server_process.poll() is not None:
            _server_process = None
            return (
                False,
                "El servidor se cerró al iniciar (modelo inválido o puerto ocupado)",
            )

        # Start the stderr reader daemon thread.
        # It feeds each line through parse_stderr_line; on FAIL it
        # records the reason and terminates the process so the poll
        # loop below can return early.
        _early_exit: list[tuple[bool, str]] = []
        _ok_ready: list[bool] = []

        def _stderr_reader(proc: subprocess.Popen) -> None:
            """Daemon thread: read stderr lines and classify them."""
            stderr = proc.stderr
            if stderr is None:
                return
            try:
                for raw_line in iter(stderr.readline, b""):
                    if not raw_line:
                        break
                    try:
                        text = raw_line.decode("utf-8", errors="replace")
                    except AttributeError:
                        continue
                    line = text.rstrip("\n")
                    verdict, reason = parse_stderr_line(line)
                    if verdict == "FAIL":
                        _early_exit.append((False, reason))
                        proc.terminate()
                        break
                    elif verdict == "OK":
                        _ok_ready.append(True)
            except Exception:
                pass

        reader = threading.Thread(
            target=_stderr_reader,
            args=(_server_process,),
            daemon=True,
        )
        reader.start()

    # Lock is now released. Poll the health endpoint without holding
    # the lock so a concurrent stop_server() can interrupt the wait by
    # terminating the process; the next check_running() call will then
    # return False and we will report a timeout.
    attempts = max(1, int(timeout / _POLL_INTERVAL_SECONDS))
    for _ in range(attempts):
        time.sleep(_POLL_INTERVAL_SECONDS)

        # Early exit on stderr-detected failure
        if _early_exit:
            stop_server()
            reader.join(timeout=1.0)
            return _early_exit[0]

        # Process exited on its own (crash / unknown error)
        if _server_process.poll() is not None:
            stop_server()
            reader.join(timeout=1.0)
            return False, "El servidor se cerró al iniciar"

        # Success: stderr OK signal or health endpoint ready
        if _ok_ready:
            reader.join(timeout=1.0)
            return True, "Servidor listo"

        state = client.check_state()
        if state == "ready":
            reader.join(timeout=1.0)
            return True, "Servidor listo"

    return False, f"El servidor no responde dentro de {timeout}s"


def stop_server() -> None:
    """Stop the tracked llama-server process.

    Sends terminate(), waits up to 5s for graceful exit, falls back to
    kill() if needed. Idempotent — safe to call when no process is tracked.
    """
    global _server_process

    with _lock:
        proc = _server_process
        if proc is None:
            return
        if proc.poll() is not None:
            # Already exited
            _server_process = None
            return

        # Graceful shutdown
        proc.terminate()

        # Wait up to STOP_TIMEOUT_SECONDS for graceful exit
        poll_interval = 0.1
        attempts = int(_STOP_TIMEOUT_SECONDS / poll_interval)
        for _ in range(attempts):
            time.sleep(poll_interval)
            if proc.poll() is not None:
                # Exited gracefully
                _server_process = None
                return

        # Force kill
        try:
            proc.kill()
            proc.wait()
        except Exception:
            pass  # Last resort: don't raise if kill fails

        _server_process = None


def get_install_command() -> str:
    """Return the winget command to install llama-server.

    Returns:
        The literal string "winget install ggml.llamacpp".
    """
    return "winget install ggml.llamacpp"
