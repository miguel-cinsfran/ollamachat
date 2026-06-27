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

# Track whether the last successful launch included a non-None mmproj path.
# Reset on stop_server() and at the start of each start_server() call.
_vision_capable: bool = False

# Windows subprocess creation flag: prevents a console window from
# flashing when the spawned process is started.
_CREATE_NO_WINDOW = 0x08000000

# Poll interval for server startup checks.
_POLL_INTERVAL_SECONDS = 0.2

# Timeout for graceful shutdown (terminate -> kill fallback).
_STOP_TIMEOUT_SECONDS = 5.0


def _force_stop_on_port(port: int) -> None:
    """Best-effort: kill the process LISTENING on *port* (Windows only).

    ``stop_server`` only terminates the process this run spawned. When a
    llama-server from a previous app session still holds the port, switching
    models would otherwise silently no-op (the fast-path sees "already
    running"). This finds the owning PID via PowerShell and kills it. Never
    raises; a failure just means the subsequent spawn will report the busy port.
    """
    if not _is_windows():
        return
    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                f"(Get-NetTCPConnection -LocalPort {port} -State Listen "
                f"-ErrorAction SilentlyContinue).OwningProcess",
            ],
            capture_output=True, text=True, timeout=5,
            creationflags=_CREATE_NO_WINDOW,
        )
        for token in result.stdout.split():
            pid = token.strip()
            if pid.isdigit():
                subprocess.run(
                    ["taskkill", "/F", "/PID", pid],
                    capture_output=True, timeout=5,
                    creationflags=_CREATE_NO_WINDOW,
                )
    except Exception:
        pass


def _diagnose_exit(stderr_tail: list[str]) -> str:
    """Turn llama-server's last stderr lines into a Spanish, actionable reason.

    Blind users were getting a generic "se cerró al iniciar" with no clue why
    (commonly: the GPU ran out of VRAM for a big model). This scans the tail
    for well-known failure phrases and otherwise surfaces the last real line.
    """
    joined = " \n".join(stderr_tail[-12:]).lower()
    vram_markers = (
        "out of memory", "cudamalloc", "failed to allocate", "ggml_cuda",
        "cublas", "cuda error", "vram", "not enough memory",
    )
    if any(m in joined for m in vram_markers):
        return (
            "El servidor se cerró: memoria de GPU insuficiente para este modelo. "
            "Probá un modelo más chico, reducí 'capas en GPU' (n-gpu-layers) o el "
            "contexto."
        )
    if any(m in joined for m in (
        "error loading model", "unable to load model", "failed to load model",
        "invalid model", "unknown model architecture",
    )):
        return (
            "El servidor se cerró: no pudo cargar el modelo (archivo inválido o "
            "arquitectura no soportada por esta versión de llama-server)."
        )
    if "address already in use" in joined or "bind: " in joined:
        return "El servidor se cerró: el puerto ya está en uso."
    last = next((l.strip() for l in reversed(stderr_tail) if l.strip()), "")
    if last:
        return f"El servidor se cerró al iniciar. Detalle: {last[:180]}"
    return "El servidor se cerró al iniciar"


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


def _is_mmproj_name(name: str) -> bool:
    """Return True if the filename is a multimodal projector, not a chat model.

    mmproj files share the .gguf extension but cannot be loaded as a model.
    They are filtered out of scan results so they don't appear in the selector.
    """
    return "mmproj" in name.lower()


# Scan depth per index in _get_standard_paths():
# 0 = ~/models       → depth 2: catches model/subdir/model.gguf
# 1 = ~/Downloads    → depth 0: root only — avoid crawling user files
# 2 = HF cache       → depth 5: deep snapshots/.../model.gguf
# 3 = LM Studio      → depth 2: LM Studio organises in subdirs
# 4 = GPT4All        → depth 0: flat layout
_STANDARD_PATH_DEPTHS: list[int] = [2, 0, 5, 2, 0]


def find_gguf_models(extra_paths: list[str] | None = None) -> list[str]:
    """Scan standard locations for .gguf model files.

    On Windows, scans the standard paths (returned by
    :func:`_get_standard_paths`) plus any caller-provided ``extra_paths``.
    Each standard path has a configured scan depth (see ``_STANDARD_PATH_DEPTHS``);
    ``~/models`` and LM Studio are recursive to depth 2, the HuggingFace cache
    to depth 5, and ``~/Downloads`` / GPT4All to depth 0 (root only).
    mmproj files are excluded — they share the .gguf extension but are vision
    projectors, not loadable chat models.

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

    paths_to_scan: list[tuple[str, int]] = [
        (p, _STANDARD_PATH_DEPTHS[i] if i < len(_STANDARD_PATH_DEPTHS) else 2)
        for i, p in enumerate(_get_standard_paths())
    ]
    if extra_paths:
        for p in extra_paths:
            paths_to_scan.append((p, 2))

    collected: set[str] = set()
    for dir_path, max_depth in paths_to_scan:
        if not os.path.isdir(dir_path):
            continue
        _scan_recursive_os(dir_path, collected, current_depth=0, max_depth=max_depth)

    return sorted(collected, key=lambda p: os.path.basename(p).lower())


def _scan_recursive_os(
    dir_path: str, collected: set[str], current_depth: int, max_depth: int
) -> None:
    """Recursively add .gguf model files up to max_depth levels of subdirs.

    mmproj files are skipped — they share the .gguf extension but are vision
    projectors, not loadable models. max_depth=0 scans only the given dir.
    """
    if current_depth > max_depth:
        return
    try:
        with os.scandir(dir_path) as it:
            for entry in it:
                if (
                    entry.is_file()
                    and entry.name.lower().endswith(".gguf")
                    and not _is_mmproj_name(entry.name)
                ):
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
    mmproj: str | None = None,
    mmproj_offload: bool = True,
    threads: int | None = None,
    flash_attn: bool = False,
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
        mmproj: Path to multimodal projector .gguf, or None for text-only.
        mmproj_offload: If False, pass ``--no-mmproj-offload`` to save VRAM.

    Returns:
        (ok, message) tuple.
    """
    global _server_process, _vision_capable

    with _lock:
        # Reset vision flag at the start of every launch attempt.
        _vision_capable = False
        # Step 1: Stop any tracked process first
        stop_server()

        # Step 2: Fast-path - server already running WITH THE SAME MODEL.
        if client.check_running():
            loaded = client.get_loaded_model()
            if not isinstance(loaded, str) or not loaded:
                # Loaded model unknown — keep the running server (fast path).
                return True, "El servidor ya está corriendo"
            if os.path.basename(loaded) == os.path.basename(model_path):
                return True, "El servidor ya está corriendo"
            # A DIFFERENT model is loaded — almost always an untracked server
            # from a previous app run (stop_server only kills the process THIS
            # run spawned). Force-stop whatever holds the port so the requested
            # model actually loads; otherwise switching models silently no-ops
            # and the UI keeps showing the old model.
            _force_stop_on_port(port)
            freed = False
            for _ in range(25):
                time.sleep(_POLL_INTERVAL_SECONDS)
                if not client.check_running():
                    freed = True
                    break
            if not freed:
                return False, "No se pudo liberar el puerto para cambiar de modelo"

        # Step 3: Build argv
        argv = [
            "llama-server",
            "--model", model_path,
            "--port", str(port),
            "--host", "127.0.0.1",
            "--ctx-size", str(ctx_size),
            "--jinja",
        ]
        # n_gpu_layers < 0 means "auto": OMIT the flag so llama.cpp's
        # common_fit_params offloads as many layers as fit in VRAM and runs the
        # rest on CPU. Forcing --n-gpu-layers (e.g. 99) DISABLES that auto-fit,
        # so a model bigger than VRAM aborts with an OOM instead of loading
        # partially on the GPU. (Confirmed in llama-server's startup logs:
        # "failed to fit params... n_gpu_layers already set by user, abort".)
        if n_gpu_layers is not None and n_gpu_layers >= 0:
            argv.extend(["--n-gpu-layers", str(n_gpu_layers)])
        if mmproj is not None:
            argv.extend(["--mmproj", mmproj])
        if not mmproj_offload:
            argv.append("--no-mmproj-offload")
        if threads is not None:
            argv.extend(["--threads", str(threads)])
        if flash_attn:
            argv.append("--flash-attn")

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
        # _early_exit / _ok_ready are mutated by the reader thread
        # and read by the poll loop. Under CPython's GIL, individual
        # list.append() / len() / index access are atomic — no Lock
        # needed. Project targets CPython only (requires-python=">=3.12").
        _early_exit: list[tuple[bool, str]] = []
        _ok_ready: list[bool] = []
        # Rolling tail of the last stderr lines, so an unclassified crash
        # (e.g. CUDA out of memory) can report the REAL reason instead of a
        # generic "se cerró al iniciar". CPython list ops are atomic.
        _stderr_tail: list[str] = []

        from bellbird.core.logger import get_logger
        _log = get_logger()
        # Backend lines worth surfacing so we KNOW whether the GPU is used and
        # how many layers were offloaded (answers "does this use CUDA?" and why
        # loading is slow / why a big model OOMs). llama-server prints these to
        # stderr at startup.
        _backend_markers = (
            "cuda", "vulkan", "metal", "rocm", "hipblas", "sycl",
            "offload", "n_gpu_layers", "using device", "ggml_backend",
            "load_tensors", "model size", "buffer size",
        )

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
                    if line.strip():
                        _stderr_tail.append(line)
                        del _stderr_tail[:-12]  # keep only the last 12 lines
                        low = line.lower()
                        if any(m in low for m in _backend_markers):
                            _log.info("llama-server: %s", line.strip()[:200])
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
            return False, _diagnose_exit(_stderr_tail)

        # Success: stderr OK signal or health endpoint ready
        if _ok_ready:
            reader.join(timeout=1.0)
            if mmproj is not None:
                _vision_capable = True
            return True, "Servidor listo"

        state = client.check_state()
        if state == "ready":
            reader.join(timeout=1.0)
            if mmproj is not None:
                _vision_capable = True
            return True, "Servidor listo"

    return False, f"El servidor no responde dentro de {timeout}s"


def is_vision_capable() -> bool:
    """Return True iff the last successful launch included a non-None mmproj path."""
    return _vision_capable


def stop_server() -> None:
    """Stop the tracked llama-server process.

    Sends terminate(), waits up to 5s for graceful exit, falls back to
    kill() if needed. Idempotent — safe to call when no process is tracked.
    Resets the vision-capable flag to False.
    """
    global _server_process, _vision_capable

    with _lock:
        proc = _server_process
        if proc is None:
            _vision_capable = False
            return
        if proc.poll() is not None:
            # Already exited
            _server_process = None
            _vision_capable = False
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
                _vision_capable = False
                return

        # Force kill
        try:
            proc.kill()
            proc.wait()
        except Exception:
            pass  # Last resort: don't raise if kill fails

        _server_process = None
        _vision_capable = False


def get_install_command() -> str:
    """Return the winget command to install llama-server.

    Returns:
        The literal string "winget install ggml.llamacpp".
    """
    return "winget install ggml.llamacpp"
