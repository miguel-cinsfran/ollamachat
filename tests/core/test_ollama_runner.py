"""Tests for ollama_runner — spawning and probing the local Ollama server."""

import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from ollamachat.core.ollama_runner import (
    _POLL_INTERVAL_SECONDS,
    get_ollama_command,
    start_ollama,
)


# ─── get_ollama_command ─────────────────────────────────────────────────────


def test_get_ollama_command_returns_ollama_serve():
    """The command is the same on every platform: ['ollama', 'serve']."""
    cmd = get_ollama_command()
    assert cmd == ["ollama", "serve"]


# ─── start_ollama: already running ──────────────────────────────────────────


def test_start_ollama_already_running_returns_immediately():
    """If Ollama is already up, returns (True, '...corriendo') without spawning."""
    client = MagicMock()
    client.check_running.return_value = True

    with patch("ollamachat.core.ollama_runner.subprocess.Popen") as popen:
        ok, message = start_ollama(client, timeout=0.5)

    assert ok is True
    assert "corriendo" in message.lower()
    popen.assert_not_called()


# ─── start_ollama: spawns then poll finds it up ─────────────────────────────


def test_start_ollama_spawns_and_polls_until_up():
    """Spawns ollama, then check_running returns True on the 3rd poll."""
    client = MagicMock()
    # First call: not running (pre-check). Then 2 polls of not running.
    # 3rd poll: running.
    client.check_running.side_effect = [False, False, False, True]

    with patch("ollamachat.core.ollama_runner.subprocess.Popen") as popen:
        ok, message = start_ollama(client, timeout=1.0)

    assert ok is True
    assert "listo" in message.lower()
    popen.assert_called_once()
    # 4 calls to check_running: 1 pre-check + 3 polls
    assert client.check_running.call_count == 4


# ─── start_ollama: timeout ──────────────────────────────────────────────────


def test_start_ollama_timeout_when_server_never_comes_up():
    """If check_running never returns True, returns (False, 'no responde')."""
    client = MagicMock()
    client.check_running.return_value = False

    with patch("ollamachat.core.ollama_runner.subprocess.Popen") as popen:
        ok, message = start_ollama(client, timeout=0.5)

    assert ok is False
    assert "no responde" in message.lower()
    popen.assert_called_once()


# ─── start_ollama: spawn failure (e.g. ollama not on PATH) ─────────────────


def test_start_ollama_spawn_failure_is_caught():
    """If Popen raises (e.g. FileNotFoundError), returns (False, error msg)."""
    client = MagicMock()
    client.check_running.return_value = False

    with patch(
        "ollamachat.core.ollama_runner.subprocess.Popen",
        side_effect=FileNotFoundError("No such file: ollama"),
    ):
        ok, message = start_ollama(client, timeout=0.5)

    assert ok is False
    assert "no se pudo" in message.lower()


def test_start_ollama_oserror_is_caught():
    """If Popen raises OSError, returns (False, error msg) and does not raise."""
    client = MagicMock()
    client.check_running.return_value = False

    with patch(
        "ollamachat.core.ollama_runner.subprocess.Popen",
        side_effect=OSError("Permission denied"),
    ):
        ok, message = start_ollama(client, timeout=0.5)

    assert ok is False
    assert "no se pudo" in message.lower()


# ─── start_ollama: Windows-specific creation flag ───────────────────────────


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only behavior")
def test_start_ollama_on_windows_uses_create_no_window():
    """On Windows, Popen receives creationflags=0x08000000 to hide console."""
    client = MagicMock()
    client.check_running.return_value = False

    with patch("ollamachat.core.ollama_runner.subprocess.Popen") as popen:
        start_ollama(client, timeout=0.1)

    _, kwargs = popen.call_args
    assert kwargs.get("creationflags") == 0x08000000


def test_start_ollama_stdio_redirected_to_devnull():
    """stdout/stderr/stdin are always redirected to DEVNULL."""
    client = MagicMock()
    client.check_running.return_value = False

    with patch("ollamachat.core.ollama_runner.subprocess.Popen") as popen:
        start_ollama(client, timeout=0.1)

    _, kwargs = popen.call_args
    assert kwargs.get("stdout") == subprocess.DEVNULL
    assert kwargs.get("stderr") == subprocess.DEVNULL
    assert kwargs.get("stdin") == subprocess.DEVNULL


# ─── Internal: poll interval sanity check ──────────────────────────────────


def test_poll_interval_is_short():
    """The poll interval should be small enough to be responsive."""
    assert _POLL_INTERVAL_SECONDS <= 0.5
