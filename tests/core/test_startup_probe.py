"""Tests for core.startup module — parse_stderr_line and probe.

Strict TDD: tests written BEFORE the code they exercise.
"""

import ast
import pathlib
from unittest.mock import MagicMock, patch

import pytest


# ─── parse_stderr_line ────────────────────────────────────────────────────


class TestParseStderrLine:
    """Parametrized truth table for parse_stderr_line."""

    @pytest.mark.parametrize(
        "line, expected_verdict",
        [
            # FAIL tokens
            ("error loading model: invalid magic number", "FAIL"),
            ("Error Loading Model: bad file", "FAIL"),
            ("failed to load model from file", "FAIL"),
            ("unable to load model: unsupported format", "FAIL"),
            ("ggml: out of memory allocating tensor buffer", "FAIL"),
            ("unknown model architecture: q4_k_xl_99", "FAIL"),
            ("unknown architecture: foo", "FAIL"),
            # OK tokens
            ("model loaded (2048 layers)", "OK"),
            ("listo", "OK"),
            ("llama server listening on port 8080", "OK"),
            # NEUTRAL tokens
            ("", "NEUTRAL"),
            ("llama_model_loader: - loading model...", "NEUTRAL"),
            ("some unrelated info banner", "NEUTRAL"),
            ("llama_model_loader: loaded meta data with 19 key-value pairs", "NEUTRAL"),
        ],
    )
    def test_verdicts(self, line: str, expected_verdict: str) -> None:
        """Each known token maps to its expected verdict."""
        from bellbird.core.startup import parse_stderr_line

        verdict, _ = parse_stderr_line(line)
        assert verdict == expected_verdict, (
            f"parse_stderr_line({line!r}) expected {expected_verdict}, got {verdict}"
        )

    def test_fail_contains_reason(self) -> None:
        """FAIL lines return the stripped line as reason."""
        from bellbird.core.startup import parse_stderr_line

        verdict, reason = parse_stderr_line("error loading model: bad magic")
        assert verdict == "FAIL"
        assert "error loading model: bad magic" in reason

    def test_neutral_no_reason(self) -> None:
        """NEUTRAL lines return empty reason."""
        from bellbird.core.startup import parse_stderr_line

        verdict, reason = parse_stderr_line("some benign line")
        assert verdict == "NEUTRAL"
        assert reason == ""

    def test_ok_no_reason(self) -> None:
        """OK lines return empty reason."""
        from bellbird.core.startup import parse_stderr_line

        verdict, reason = parse_stderr_line("model loaded")
        assert verdict == "OK"
        assert reason == ""


# ─── probe ────────────────────────────────────────────────────────────────


class TestProbe:
    """Three probe scenarios: running, not-found, exception swallowed."""

    def test_probe_server_running_with_model(self) -> None:
        """Given a running server with a loaded model, probe returns full result."""
        from bellbird.core.startup import probe

        client = MagicMock()
        client.check_running.return_value = True
        client.get_loaded_model.return_value = "phi-3.gguf"

        runner = MagicMock()
        runner.find_llama_server.return_value = "/usr/bin/llama-server"

        result = probe(client, runner)

        assert result.server_path is not None
        assert "llama-server" in str(result.server_path)
        assert result.is_running is True
        assert result.loaded_model == "phi-3.gguf"
        assert result.error is None
        client.check_running.assert_called_once()
        client.get_loaded_model.assert_called_once()

    def test_probe_binary_not_found_short_circuits(self) -> None:
        """Given find_llama_server returns None, probe short-circuits."""
        from bellbird.core.startup import probe

        client = MagicMock()
        runner = MagicMock()
        runner.find_llama_server.return_value = None

        result = probe(client, runner)

        assert result.server_path is None
        assert result.is_running is False
        assert result.loaded_model is None
        assert result.error is not None
        assert "not found" in result.error.lower()
        # Client must NOT be called
        client.check_running.assert_not_called()
        client.get_loaded_model.assert_not_called()

    def test_probe_check_running_exception_swallowed(self) -> None:
        """Given check_running raises, probe returns without raising."""
        from bellbird.core.startup import probe

        client = MagicMock()
        client.check_running.side_effect = ConnectionError("refused")

        runner = MagicMock()
        runner.find_llama_server.return_value = "/usr/bin/llama-server"

        result = probe(client, runner)

        assert result.server_path is not None
        assert result.is_running is False
        assert result.loaded_model is None
        assert result.error is not None
        assert "ConnectionError" in result.error

    def test_probe_find_llama_server_exception_swallowed(self) -> None:
        """Given find_llama_server raises, probe returns without raising."""
        from bellbird.core.startup import probe

        client = MagicMock()
        runner = MagicMock()
        runner.find_llama_server.side_effect = OSError("permission denied")

        result = probe(client, runner)

        assert result.server_path is None
        assert result.is_running is False
        assert result.loaded_model is None
        assert result.error is not None
        assert "OSError" in result.error


# ─── AST: no wx import ───────────────────────────────────────────────────


def test_startup_module_does_not_import_wx() -> None:
    """core/startup.py MUST NOT import wx at module level."""
    source_path = (
        pathlib.Path(__file__).resolve().parent.parent.parent
        / "bellbird"
        / "core"
        / "startup.py"
    )
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "wx", (
                    "bellbird/core/startup.py must NOT import wx at module level"
                )
        if isinstance(node, ast.ImportFrom):
            assert node.module != "wx", (
                "bellbird/core/startup.py must NOT import wx from"
            )
