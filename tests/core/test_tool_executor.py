"""Tests for ToolExecutor — covering non-win32, display text, tool message,
Popen path, cancel(), and ToolResult.cancelled flag."""

import subprocess
import time
import threading
from unittest.mock import Mock, MagicMock, patch

import pytest

from bellbird.core.tool_executor import ToolExecutor, ToolResult


# ── Helper ──────────────────────────────────────────────────────────────────


def _make_mock_popen(
    stdout: str = "output",
    stderr: str = "",
    returncode: int = 0,
    wait_side_effect: list | None = None,
) -> MagicMock:
    """Build a mock subprocess.Popen with the given outputs.

    Args:
        stdout: Text that stdout.read() returns.
        stderr: Text that stderr.read() returns.
        returncode: The returncode once poll()/wait() settle.
        wait_side_effect: If given, used as ``side_effect`` for ``wait()``.
            If None, ``wait()`` returns ``returncode`` immediately.
    """
    proc = MagicMock()
    proc.stdout = MagicMock()
    proc.stdout.read.return_value = stdout
    proc.stderr = MagicMock()
    proc.stderr.read.return_value = stderr
    proc.returncode = returncode
    if wait_side_effect is not None:
        proc.wait.side_effect = wait_side_effect
    else:
        proc.wait.return_value = returncode
    proc.poll.return_value = returncode
    return proc


# ── Prologue: these tests need subprocess.run mocked for the probe,
#    and subprocess.Popen mocked for the command. We provide a fixture-like
#    context-manager helper for common patches.


def _tool_ctx(popen_proc: MagicMock | None = None, run_return=None):
    """Context manager that patches sys.platform to win32 and both
    subprocess.run (probe) and subprocess.Popen (command).

    Args:
        popen_proc: The mock Popen instance for ``subprocess.Popen``.
            If None, ``_make_mock_popen()`` is used.
        run_return: Return value for the first (probe) subprocess.run call.
            If None, a default success mock is created.
    """
    if run_return is None:
        run_return = MagicMock(returncode=0, stdout="", stderr="")
    if popen_proc is None:
        popen_proc = _make_mock_popen()

    return patch.multiple(
        "bellbird.core.tool_executor.subprocess",
        run=MagicMock(return_value=run_return),
        Popen=MagicMock(return_value=popen_proc),
    )


class TestToolExecutor:
    """Tests for ToolExecutor."""

    def test_run_nonwindows_returns_error(self):
        """Given sys.platform is linux, run returns error result without subprocess."""
        with patch("sys.platform", "linux"):
            executor = ToolExecutor()
            result = executor.run("shell_execute", "ls")

        assert result.returncode == 1
        assert result.stderr == "Tool execution only available on Windows."
        assert result.stdout == ""

    def test_tool_result_to_display_text(self):
        """Given a known ToolResult, to_display_text contains tool_name and command."""
        result = ToolResult("shell_execute", "Get-Process", "Idle   123", "", 0)
        text = result.to_display_text()
        assert "[Herramienta: shell_execute]" in text
        assert "> Get-Process" in text
        assert "Idle   123" in text
        assert "[stderr]" not in text
        assert "[codigo de salida:" not in text

    def test_tool_result_to_tool_message(self):
        """Given a ToolResult, to_tool_message has role, content, tool_call_id keys."""
        result = ToolResult("shell_execute", "ls", "file1\nfile2", "", 0)
        msg = result.to_tool_message()
        assert msg["role"] == "tool"
        assert msg["content"] == "file1\nfile2"
        assert msg["tool_call_id"] == ""

    def test_tool_result_to_tool_message_includes_stderr(self):
        """Given stderr is non-empty, to_tool_message content includes it."""
        result = ToolResult("shell_execute", "bad", "", "boom", 2)
        msg = result.to_tool_message()
        assert msg["role"] == "tool"
        assert "[stderr] boom" in msg["content"]
        assert "[exit code: 2]" in msg["content"]
        assert msg["tool_call_id"] == ""

    def test_max_output_truncated(self):
        """Given stdout longer than MAX_OUTPUT_CHARS, it is truncated."""
        proc = _make_mock_popen(stdout="x" * 5000, stderr="", returncode=0)
        with patch("sys.platform", "win32"), patch(
            "bellbird.core.tool_executor.subprocess.run",
            return_value=MagicMock(returncode=0, stdout="", stderr=""),
        ), patch(
            "bellbird.core.tool_executor.subprocess.Popen",
            return_value=proc,
        ):
            executor = ToolExecutor()
            result = executor.run("shell_execute", "echo x")

        assert len(result.stdout) == 4000

    def test_stderr_truncated_independently_from_stdout(self):
        """Given both stdout and stderr exceed MAX_OUTPUT_CHARS, both truncated independently."""
        proc = _make_mock_popen(
            stdout="a" * 5000, stderr="e" * 5000, returncode=1
        )
        with patch("sys.platform", "win32"), patch(
            "bellbird.core.tool_executor.subprocess.run",
            return_value=MagicMock(returncode=0, stdout="", stderr=""),
        ), patch(
            "bellbird.core.tool_executor.subprocess.Popen",
            return_value=proc,
        ):
            executor = ToolExecutor()
            result = executor.run("shell_execute", "bad cmd")

        assert len(result.stdout) == 4000
        assert len(result.stderr) == 4000
        assert result.stdout == "a" * 4000
        assert result.stderr == "e" * 4000

    def test_pwsh_probe_has_creationflags_on_win32(self):
        """Given win32, the PROBE subprocess call also uses CREATE_NO_WINDOW (BUG 3)."""
        CREATE_NO_WINDOW = 0x08000000

        def run_side_effect(*args, **kwargs):
            return MagicMock(returncode=0, stdout="", stderr="")

        proc = _make_mock_popen()

        with patch("sys.platform", "win32"), patch(
            "bellbird.core.tool_executor.subprocess.run",
            side_effect=run_side_effect,
        ) as mock_run, patch(
            "bellbird.core.tool_executor.subprocess.Popen",
            return_value=proc,
        ):
            executor = ToolExecutor()
            executor.run("shell_execute", "Get-Process")

        assert mock_run.call_count >= 1
        probe_call = mock_run.call_args_list[0]
        kwargs = probe_call[1] if probe_call[1] else {}
        assert kwargs.get("creationflags") == CREATE_NO_WINDOW, (
            "CREATE_NO_WINDOW flag must be set on the PROBE subprocess call "
            "to prevent console flash on Windows (BUG 3)"
        )

    def test_create_no_window_flag_set_on_win32(self):
        """Given win32, the actual command subprocess.Popen call uses CREATE_NO_WINDOW."""
        CREATE_NO_WINDOW = 0x08000000
        proc = _make_mock_popen()

        with patch("sys.platform", "win32"), patch(
            "bellbird.core.tool_executor.subprocess.run",
            return_value=MagicMock(returncode=0, stdout="", stderr=""),
        ) as mock_run, patch(
            "bellbird.core.tool_executor.subprocess.Popen",
            return_value=proc,
        ) as mock_popen:
            executor = ToolExecutor()
            executor.run("shell_execute", "Get-Process")

        assert mock_run.call_count >= 1  # probe
        assert mock_popen.call_count == 1
        _, popen_kwargs = mock_popen.call_args
        assert popen_kwargs.get("creationflags") == CREATE_NO_WINDOW, (
            "CREATE_NO_WINDOW flag must be set on Popen to prevent console flash"
        )

    # ── Popen path — timeout ────────────────────────────────────────────────

    def test_timeout_returns_error_result(self):
        """Given Popen.wait() raises TimeoutExpired, returns error result (no raise)."""
        proc = MagicMock()
        proc.stdout = MagicMock()
        proc.stdout.read.return_value = ""
        proc.stderr = MagicMock()
        proc.stderr.read.return_value = ""
        # First call raises TimeoutExpired; second call (kill+wait in handler) returns 1
        proc.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="sleep 999", timeout=5.0),
            1,
        ]
        proc.poll.return_value = None

        with patch("sys.platform", "win32"), patch(
            "bellbird.core.tool_executor.subprocess.run",
            return_value=MagicMock(returncode=0, stdout="", stderr=""),
        ), patch(
            "bellbird.core.tool_executor.subprocess.Popen",
            return_value=proc,
        ):
            executor = ToolExecutor()
            result = executor.run("shell_execute", "sleep 999", timeout=5.0)

        assert result.returncode == 1
        assert "Timeout" in result.stderr
        assert result.cancelled is False

    # ── Cancel functionality ────────────────────────────────────────────────

    def test_cancel_terminates_live_process(self):
        """Given a running process, cancel() terminates it and returns cancelled=True."""
        import threading as _threading

        proc = MagicMock()
        proc.stdout = MagicMock()
        proc.stdout.read.return_value = "partial"
        proc.stderr = MagicMock()
        proc.stderr.read.return_value = ""
        proc.poll.side_effect = [None, None, 0]  # alive, still alive after terminate, then dead
        # wait blocks until terminate kills it, then returns 1
        real_wait = [threading.Event()]

        def wait_side(timeout=None):
            real_wait[0].wait(timeout=5)
            return 1

        proc.wait.side_effect = wait_side

        with patch("sys.platform", "win32"), patch(
            "bellbird.core.tool_executor.subprocess.run",
            return_value=MagicMock(returncode=0, stdout="", stderr=""),
        ), patch(
            "bellbird.core.tool_executor.subprocess.Popen",
            return_value=proc,
        ):
            executor = ToolExecutor()
            results = []

            def worker():
                r = executor.run("shell_execute", "sleep 30", timeout=30)
                results.append(r)

            t = _threading.Thread(target=worker, daemon=True)
            t.start()
            time.sleep(0.2)  # let run() get to wait()
            executor.cancel()
            real_wait[0].set()  # unblock the stub wait
            t.join(timeout=5)

        assert len(results) == 1
        assert results[0].cancelled is True
        assert proc.terminate.called

    def test_cancel_idempotent(self):
        """Given cancel() called twice, second call is a no-op (no crash, no double terminate)."""
        proc = _make_mock_popen()
        proc.poll.side_effect = [None, None, 0]  # alive, alive, dead

        import threading as _threading

        real_wait = [threading.Event()]

        def wait_side(timeout=None):
            real_wait[0].wait(timeout=5)
            return 1

        proc.wait.side_effect = wait_side

        with patch("sys.platform", "win32"), patch(
            "bellbird.core.tool_executor.subprocess.run",
            return_value=MagicMock(returncode=0, stdout="", stderr=""),
        ), patch(
            "bellbird.core.tool_executor.subprocess.Popen",
            return_value=proc,
        ):
            executor = ToolExecutor()
            results = []

            def worker():
                r = executor.run("shell_execute", "sleep 30", timeout=30)
                results.append(r)

            t = _threading.Thread(target=worker, daemon=True)
            t.start()
            time.sleep(0.2)
            executor.cancel()
            # Second call must be a no-op
            executor.cancel()
            real_wait[0].set()
            t.join(timeout=5)

        assert len(results) == 1
        assert proc.terminate.call_count == 1  # only one terminate

    def test_cancel_noop_when_idle(self):
        """Given no process running, cancel() does nothing (no raise)."""
        executor = ToolExecutor()
        # Should not raise
        executor.cancel()
        # Should still be safe
        executor.cancel()

    def test_cancel_after_normal_exit_is_noop(self):
        """Given process has already exited, cancel() is a no-op."""
        proc = _make_mock_popen(returncode=0)

        with patch("sys.platform", "win32"), patch(
            "bellbird.core.tool_executor.subprocess.run",
            return_value=MagicMock(returncode=0, stdout="", stderr=""),
        ), patch(
            "bellbird.core.tool_executor.subprocess.Popen",
            return_value=proc,
        ):
            executor = ToolExecutor()
            result = executor.run("shell_execute", "echo hi", timeout=5)

        assert result.cancelled is False
        # Cancel after the process has already exited — should be noop
        executor.cancel()

    def test_cancel_never_raises_on_broken_popen(self):
        """Given Popen.terminate() raises, cancel() swallows the exception."""
        proc = MagicMock()
        proc.poll.return_value = None
        proc.wait.side_effect = [None]  # poll returns None initially
        # make wait work for the second time
        import subprocess as sp
        proc.terminate.side_effect = OSError("access denied")
        # cancel will terminate, then wait. We need wait to return
        # after terminate even though terminate raised.
        # In cancel(), after terminateException, the wait happens.
        # Let's make wait work.

        from unittest.mock import call

        # wait returns 1
        proc.wait.return_value = 1

        import threading as _threading
        real_wait = [threading.Event()]

        # For the main run() wait, use a blocking wait
        run_wait_called = [False]

        def run_wait_side(timeout=None):
            run_wait_called[0] = True
            real_wait[0].wait(timeout=5)
            return 1

        # run() uses proc.wait(timeout=N) then reads stdout
        # cancel() uses proc.wait(timeout=2) then proc.wait(timeout=1)
        proc.wait.side_effect = run_wait_side

        with patch("sys.platform", "win32"), patch(
            "bellbird.core.tool_executor.subprocess.run",
            return_value=MagicMock(returncode=0, stdout="", stderr=""),
        ), patch(
            "bellbird.core.tool_executor.subprocess.Popen",
            return_value=proc,
        ):
            executor = ToolExecutor()
            results = []

            def worker():
                r = executor.run("shell_execute", "sleep 30", timeout=30)
                results.append(r)

            t = _threading.Thread(target=worker, daemon=True)
            t.start()
            time.sleep(0.3)
            executor.cancel()
            real_wait[0].set()
            t.join(timeout=5)

        assert len(results) == 1
        # terminate raised but cancel caught it — result is still returned
        assert results[0].cancelled is True

    # ── ToolResult.cancelled flag (NEW) ─────────────────────────────────────

    def test_tool_result_cancelled_true_surfaces_in_display_text(self):
        """Given cancelled=True, to_display_text contains [Cancelado]."""
        result = ToolResult("shell_execute", "ls", "", "", 1, cancelled=True)
        text = result.to_display_text()
        assert "[Cancelado]" in text

    def test_tool_result_cancelled_false_no_cancelado_in_display_text(self):
        """Given cancelled=False, to_display_text does NOT contain [Cancelado]."""
        result = ToolResult("shell_execute", "ls", "file1", "", 0, cancelled=False)
        text = result.to_display_text()
        assert "[Cancelado]" not in text

    def test_tool_result_cancelled_true_surfaces_in_tool_message(self):
        """Given cancelled=True, to_tool_message content contains [Cancelado]."""
        result = ToolResult("shell_execute", "ls", "file1", "", 1, cancelled=True)
        msg = result.to_tool_message()
        assert "[Cancelado]" in msg["content"]

    def test_tool_result_cancelled_false_byte_identical_to_v0_4_0(self):
        """Given cancelled=False (default), output is byte-identical to v0.4.0."""
        # v0.4.0: no cancelled field - to_display text
        result = ToolResult("shell_execute", "ls", "file1", "", 0)
        text = result.to_display_text()
        assert "[Cancelado]" not in text
        assert "[Herramienta: shell_execute]" in text
        assert "file1" in text

        msg = result.to_tool_message()
        assert "[Cancelado]" not in msg["content"]
        assert msg["role"] == "tool"

    def test_tool_result_backward_compat_5_args(self):
        """Given 5-arg constructor (old style), cancelled defaults to False."""
        result = ToolResult("shell_execute", "ls", "file1", "", 0)
        assert result.cancelled is False
        assert result.tool_name == "shell_execute"
        assert result.returncode == 0

    def test_timeout_returns_cancelled_false(self):
        """Given a real timeout (no cancel involved), cancelled=False."""
        proc = MagicMock()
        # First raises TimeoutExpired, second wait (kill+wait in handler) returns
        proc.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="sleep", timeout=5.0),
            1,
        ]
        proc.stdout = MagicMock()
        proc.stdout.read.return_value = ""
        proc.stderr = MagicMock()
        proc.stderr.read.return_value = ""

        with patch("sys.platform", "win32"), patch(
            "bellbird.core.tool_executor.subprocess.run",
            return_value=MagicMock(returncode=0, stdout="", stderr=""),
        ), patch(
            "bellbird.core.tool_executor.subprocess.Popen",
            return_value=proc,
        ):
            executor = ToolExecutor()
            result = executor.run("shell_execute", "sleep 999", timeout=5.0)

        assert result.cancelled is False
        assert result.returncode == 1

    def test_nonwin32_path_cancelled_false(self):
        """Given non-win32 path, cancelled=False (regression guard)."""
        with patch("sys.platform", "linux"):
            executor = ToolExecutor()
            result = executor.run("shell_execute", "ls")

        assert result.cancelled is False
        assert result.returncode == 1



