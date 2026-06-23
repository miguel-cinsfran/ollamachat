"""Tests for ToolExecutor — 5 tests covering non-win32 error, display text,
tool message format, stderr inclusion, and MAX_OUTPUT_CHARS truncation."""

from unittest.mock import Mock, patch

import pytest

from bellbird.core.tool_executor import ToolExecutor, ToolResult


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
        with patch("sys.platform", "win32"), patch(
            "bellbird.core.tool_executor.subprocess.run"
        ) as mock_run:
            mock_result = Mock()
            mock_result.stdout = "x" * 5000
            mock_result.stderr = ""
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            executor = ToolExecutor()
            result = executor.run("shell_execute", "echo x")

        assert len(result.stdout) == 4000

    def test_stderr_truncated_independently_from_stdout(self):
        """Given both stdout and stderr exceed MAX_OUTPUT_CHARS, both are
        truncated independently — long stderr does not eat into stdout budget."""
        with patch("sys.platform", "win32"), patch(
            "bellbird.core.tool_executor.subprocess.run"
        ) as mock_run:
            mock_result = Mock()
            mock_result.stdout = "a" * 5000
            mock_result.stderr = "e" * 5000
            mock_result.returncode = 1
            mock_run.return_value = mock_result

            executor = ToolExecutor()
            result = executor.run("shell_execute", "bad cmd")

        assert len(result.stdout) == 4000
        assert len(result.stderr) == 4000
        assert result.stdout == "a" * 4000
        assert result.stderr == "e" * 4000

    def test_create_no_window_flag_set_on_win32(self):
        """Given win32, the actual command subprocess call uses CREATE_NO_WINDOW.

        On Windows, CREATE_NO_WINDOW (0x08000000) prevents a visible console
        flash when PowerShell executes. This test verifies the flag is passed
        on the second subprocess.run call (the command itself, not the pwsh check).
        """
        CREATE_NO_WINDOW = 0x08000000
        call_index = {"n": 0}

        def run_side_effect(*args, **kwargs):
            call_index["n"] += 1
            mock_r = Mock()
            mock_r.stdout = "output"
            mock_r.stderr = ""
            mock_r.returncode = 0
            return mock_r

        with patch("sys.platform", "win32"), patch(
            "bellbird.core.tool_executor.subprocess.run",
            side_effect=run_side_effect,
        ) as mock_run:
            executor = ToolExecutor()
            executor.run("shell_execute", "Get-Process")

        # The second call is the actual command execution (first is the pwsh check)
        assert mock_run.call_count >= 2
        actual_cmd_call = mock_run.call_args_list[-1]
        kwargs = actual_cmd_call[1] if actual_cmd_call[1] else {}
        assert kwargs.get("creationflags") == CREATE_NO_WINDOW, (
            "CREATE_NO_WINDOW flag must be set to prevent console flash on Windows"
        )
