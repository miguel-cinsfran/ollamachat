"""Tests for ToolExecutor — 5 tests covering non-win32 error, display text,
tool message format, stderr inclusion, and MAX_OUTPUT_CHARS truncation."""

from unittest.mock import Mock, patch

import pytest

from ollamachat.core.tool_executor import ToolExecutor, ToolResult


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
            "ollamachat.core.tool_executor.subprocess.run"
        ) as mock_run:
            mock_result = Mock()
            mock_result.stdout = "x" * 5000
            mock_result.stderr = ""
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            executor = ToolExecutor()
            result = executor.run("shell_execute", "echo x")

        assert len(result.stdout) == 4000
