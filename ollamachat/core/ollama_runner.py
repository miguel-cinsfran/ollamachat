"""Spawn and probe the local Ollama server process.

This module is intentionally small and wx-free so it can be unit-tested
in environments that do not have wxPython installed (e.g. WSL during
development). It returns plain ``(ok, message)`` tuples; the UI layer
in ``MainWindow`` is responsible for announcing the message via
``Speech`` and updating the status bar.

Platform notes
--------------

- On Windows, ``subprocess.Popen`` is called with ``creationflags =
  0x08000000`` (``CREATE_NO_WINDOW``) so a console window does not
  flash when the user clicks the "Iniciar Ollama" button.
- On Linux / macOS the same ``ollama serve`` command is used; the
  subprocess inherits the terminal's stdio, which is fine during dev.
"""

import subprocess
import sys
import time

from ollamachat.core.ollama_client import OllamaClient


# Windows subprocess creation flag: prevents a console window from
# flashing when the spawned process is started.
_CREATE_NO_WINDOW = 0x08000000

# Poll interval and number of attempts when waiting for Ollama to come
# up. 25 * 0.2s = 5 seconds of patience, which is plenty for a local
# server start.
_POLL_INTERVAL_SECONDS = 0.2
_DEFAULT_TIMEOUT_SECONDS = 5.0


def get_ollama_command() -> list[str]:
    """Return the command used to start the Ollama server.

    Same on every platform; only the ``creationflags`` differ.
    """
    return ["ollama", "serve"]


def _spawn_ollama() -> None:
    """Spawn ``ollama serve`` as a detached subprocess.

    Raises whatever ``subprocess.Popen`` raises (typically
    ``FileNotFoundError`` if the ``ollama`` binary is not on PATH).
    """
    cmd = get_ollama_command()
    kwargs: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = _CREATE_NO_WINDOW
    subprocess.Popen(cmd, **kwargs)


def start_ollama(
    client: OllamaClient, timeout: float = _DEFAULT_TIMEOUT_SECONDS
) -> tuple[bool, str]:
    """Attempt to bring Ollama up.

    If Ollama is already responding, returns immediately. Otherwise
    spawns ``ollama serve`` and polls ``OllamaClient.check_running``
    for up to ``timeout`` seconds.

    Args:
        client: An ``OllamaClient`` used to probe the server.
        timeout: Maximum seconds to wait for the server to start.

    Returns:
        A tuple ``(ok, message)`` where ``ok`` is True if Ollama is
        responding (either it was already up or it came up within
        the timeout) and ``message`` is a short human-readable string
        suitable for the screen reader.
    """
    if client.check_running():
        return True, "Ollama ya está corriendo"

    try:
        _spawn_ollama()
    except Exception as e:
        return False, f"No se pudo iniciar Ollama: {e}"

    attempts = max(1, int(timeout / _POLL_INTERVAL_SECONDS))
    for _ in range(attempts):
        time.sleep(_POLL_INTERVAL_SECONDS)
        if client.check_running():
            return True, "Ollama listo"

    return False, "Ollama no responde"
