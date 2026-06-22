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

from ollamachat.core.llama_client import LlamaClient


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


def find_gguf_models(extra_paths: list[str] | None = None) -> list[str]:
    """Scan standard locations for .gguf model files.

    On Windows (os.name == "nt"), scans:
    - %%USERPROFILE%%\\models\\ (non-recursive)
    - %%USERPROFILE%%\\Downloads\\ (non-recursive)
    - %%USERPROFILE%%\\.cache\\huggingface\\hub\\ (recursive, depth 5)
    - %%USERPROFILE%%\\.lmstudio\\models\\ (non-recursive)
    - %%LOCALAPPDATA%%\\nomic.ai\\GPT4All\\ (non-recursive)
    - extra_paths (if provided, non-recursive)

    On non-Windows, returns [] (extra_paths is also skipped).

    Returns:
        Sorted list of absolute .gguf paths, deduplicated. Never raises.
    """
    paths_to_scan: list[tuple[str, bool]] = []

    # On non-Windows, skip the Windows-specific standard paths but still scan
    # extra_paths for dev testing convenience.
    if os.name != "nt":
        collected: set[str] = set()
        if extra_paths:
            for p in extra_paths:
                base = Path(p)
                if base.is_dir():
                    _scan_non_recursive(base, collected)
        return sorted(collected, key=lambda p: Path(p).name.lower())

    home = Path.home()
    # Non-recursive standard paths
    for subdir in ("models", "Downloads"):
        paths_to_scan.append((str(home / subdir), False))
    # Recursive: HuggingFace cache (depth 5)
    paths_to_scan.append((str(home / ".cache" / "huggingface" / "hub"), True))
    # Non-recursive: LM Studio, GPT4All
    paths_to_scan.append((str(home / ".lmstudio" / "models"), False))
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        paths_to_scan.append((str(Path(local_app_data) / "nomic.ai" / "GPT4All"), False))

    # Extra paths (non-recursive, provided by caller)
    if extra_paths:
        for p in extra_paths:
            paths_to_scan.append((p, False))

    collected: set[str] = set()
    for dir_path, recursive in paths_to_scan:
        base = Path(dir_path)
        if not base.is_dir():
            continue

        if recursive:
            # Manual recursion with depth cap of 5
            _scan_recursive(base, collected, max_depth=5)
        else:
            _scan_non_recursive(base, collected)

    # Sort by basename, deduplicated
    return sorted(collected, key=lambda p: Path(p).name.lower())


def _scan_non_recursive(base: Path, collected: set[str]) -> None:
    """Add .gguf files from a single directory (non-recursive)."""
    for entry in base.iterdir():
        if entry.is_file() and entry.suffix.lower() == ".gguf":
            collected.add(str(entry.resolve()))


def _scan_recursive(base: Path, collected: set[str], max_depth: int) -> None:
    """Recursively add .gguf files, up to a given depth."""
    _scan_recursive_impl(base, collected, current_depth=0, max_depth=max_depth)


def _scan_recursive_impl(
    base: Path, collected: set[str], current_depth: int, max_depth: int
) -> None:
    """Internal recursive scanner with depth tracking."""
    if current_depth > max_depth:
        return
    try:
        for entry in base.iterdir():
            if entry.is_file() and entry.suffix.lower() == ".gguf":
                collected.add(str(entry.resolve()))
            elif entry.is_dir() and current_depth < max_depth:
                _scan_recursive_impl(entry, collected, current_depth + 1, max_depth)
    except PermissionError:
        pass  # Skip directories we cannot read


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
    (3) Spawns subprocess.Popen with the documented argv.
    (4) Polls client.check_running() every 0.2s for up to timeout seconds.
    (5) Returns (True, "Servidor listo") on success or (False, reason)
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

        # Step 4: Spawn
        kwargs: dict = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
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

        # Step 5: Release lock before polling
        # (lock released at end of with block)

    # Step 6: Poll
    attempts = max(1, int(timeout / _POLL_INTERVAL_SECONDS))
    for _ in range(attempts):
        time.sleep(_POLL_INTERVAL_SECONDS)
        if client.check_running():
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
