"""Tests for LlamaRunner module — strict TDD, RED first, then GREEN."""

import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest


# ─── Test class ───────────────────────────────────────────────────────────────


class TestLlamaRunner:
    """Tests for LlamaRunner."""

    # ── find_llama_server ───────────────────────────────────────────────

    def test_find_llama_server_found_in_path(self):
        """Given shutil.which returns a path, find_llama_server returns it."""
        with patch("ollamachat.core.llama_runner.shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/llama-server"
            from ollamachat.core.llama_runner import find_llama_server

            result = find_llama_server()
            assert result == "/usr/bin/llama-server"

    def test_find_llama_server_returns_none(self):
        """Given shutil.which returns None, find_llama_server returns None."""
        with patch("ollamachat.core.llama_runner.shutil.which") as mock_which:
            mock_which.return_value = None
            from ollamachat.core.llama_runner import find_llama_server

            result = find_llama_server()
            assert result is None

    # ── find_gguf_models ────────────────────────────────────────────────

    def test_find_gguf_models_filters_extensions(self, tmp_path):
        """Given a dir with .gguf and .safetensors, only .gguf files are returned."""
        (tmp_path / "a.gguf").write_text("")
        (tmp_path / "b.gguf").write_text("")
        (tmp_path / "c.safetensors").write_text("")

        from ollamachat.core.llama_runner import find_gguf_models

        result = find_gguf_models(extra_paths=[str(tmp_path)])
        assert len(result) == 2
        assert all(p.endswith(".gguf") for p in result)
        # Sorted by basename: a.gguf, b.gguf
        assert all("a.gguf" in p for p in result if "a.gguf" in p)
        assert all("b.gguf" in p for p in result if "b.gguf" in p)

    def test_find_gguf_models_skips_nonexistent_dirs(self):
        """Given non-existent extra_paths, returns [] without raising."""
        from ollamachat.core.llama_runner import find_gguf_models

        result = find_gguf_models(extra_paths=["/does/not/exist"])
        # On non-Windows, returns [] (extra_paths also skipped on non-Windows per spec)
        assert result == []

    def test_find_gguf_models_extra_paths(self, tmp_path):
        """Given extra_paths with .gguf, returns it."""
        (tmp_path / "phi-3.gguf").write_text("")

        from ollamachat.core.llama_runner import find_gguf_models

        result = find_gguf_models(extra_paths=[str(tmp_path)])
        assert len(result) == 1
        assert "phi-3.gguf" in result[0]

    def test_find_gguf_models_non_windows_skips_standard_paths(self, tmp_path):
        """On non-Windows, only standard Windows paths are skipped; extra_paths works."""
        (tmp_path / "test.gguf").write_text("")

        from ollamachat.core.llama_runner import find_gguf_models

        # On non-Windows (os.name != 'nt'), standard Windows paths are skipped,
        # but extra_paths is still scanned for dev testing convenience.
        result = find_gguf_models(extra_paths=[str(tmp_path)])
        assert len(result) == 1
        assert "test.gguf" in result[0]

    def test_find_gguf_models_respects_recursive_depth(self, tmp_path):
        """Given a nested structure, only files at depth <= 5 are returned."""
        # Create structure at depths 1, 3, 5, 7
        (tmp_path / "depth1.gguf").write_text("")
        d3 = tmp_path / "a" / "b" / "c"
        d3.mkdir(parents=True)
        (d3 / "depth3.gguf").write_text("")
        d5 = tmp_path / "a" / "b" / "c" / "d" / "e"
        d5.mkdir(parents=True)
        (d5 / "depth5.gguf").write_text("")
        d7 = tmp_path / "a" / "b" / "c" / "d" / "e" / "f" / "g"
        d7.mkdir(parents=True)
        (d7 / "depth7.gguf").write_text("")

        from ollamachat.core.llama_runner import find_gguf_models

        # extra_paths is scanned with non-recursive scan on non-Windows,
        # so only depth1.gguf (at root) is found.
        result = find_gguf_models(extra_paths=[str(tmp_path)])
        # On non-Windows, extra_paths is scanned non-recursively, so only
        # depth1.gguf at the root dir is returned
        assert len(result) == 1
        assert "depth1.gguf" in result[0]

    # ── get_install_command ─────────────────────────────────────────────

    def test_get_install_command_returns_literal(self):
        """get_install_command returns the literal string."""
        from ollamachat.core.llama_runner import get_install_command

        result = get_install_command()
        assert result == "winget install ggml.llamacpp"

    # ── start_server ────────────────────────────────────────────────────

    def _make_client(self, check_running_result=True):
        """Create a MagicMock client with check_running configured."""
        client = MagicMock()
        client.check_running.return_value = check_running_result
        return client

    def test_start_server_already_running_no_popen(self):
        """Given check_running returns True, returns (True, '...corriendo') without Popen."""
        client = self._make_client(check_running_result=True)

        with patch("ollamachat.core.llama_runner.subprocess.Popen") as popen:
            from ollamachat.core.llama_runner import start_server

            ok, message = start_server("/fake/model.gguf", client, timeout=0.5)

        assert ok is True
        assert "corriendo" in message.lower()
        popen.assert_not_called()

    def test_start_server_spawns_with_documented_argv(self):
        """Given valid model, Popen is called with the documented argv."""
        client = self._make_client(check_running_result=False)

        with patch("ollamachat.core.llama_runner.subprocess.Popen") as popen:
            from ollamachat.core.llama_runner import start_server

            start_server("/fake/model.gguf", client, timeout=0.5)

        popen.assert_called_once()
        args, kwargs = popen.call_args
        argv = args[0]
        assert argv[0] == "llama-server"
        assert "--model" in argv
        assert argv[argv.index("--model") + 1] == "/fake/model.gguf"
        assert "--port" in argv
        assert "--jinja" in argv

    def test_start_server_success_after_3_polls(self):
        """Given check_running goes True after 3 polls, returns (True, '...listo')."""
        client = MagicMock()
        client.check_running.side_effect = [False, False, False, True]

        with patch("ollamachat.core.llama_runner.subprocess.Popen"):
            from ollamachat.core.llama_runner import start_server

            ok, message = start_server("/fake/model.gguf", client, timeout=1.0)

        assert ok is True
        assert "listo" in message.lower()
        assert client.check_running.call_count == 4  # 1 pre-check + 3 polls

    def test_start_server_timeout(self):
        """Given check_running always returns False, returns (False, timeout msg)."""
        client = MagicMock()
        client.check_running.return_value = False

        with patch("ollamachat.core.llama_runner.subprocess.Popen"):
            from ollamachat.core.llama_runner import start_server

            ok, message = start_server("/fake/model.gguf", client, timeout=0.5)

        assert ok is False
        assert "timeout" in message.lower() or "no responde" in message.lower()

    def test_start_server_popen_failure(self):
        """Given Popen raises FileNotFoundError, returns (False, error msg)."""
        client = self._make_client(check_running_result=False)

        from ollamachat.core.llama_runner import start_server

        # Popen already patched at module level in the import; we need to patch at the right place
        with patch("ollamachat.core.llama_runner.subprocess.Popen",
                   side_effect=FileNotFoundError("No such file: llama-server")):
            ok, message = start_server("/fake/model.gguf", client, timeout=0.5)

        assert ok is False
        assert "no se encontr" in message.lower()

    def test_start_server_stops_before_respawning(self):
        """Given a previously started server, calling start_server again stops the old one first."""
        client = MagicMock()
        client.check_running.side_effect = [
            False, False, True,   # first call: pre-check (F), poll (F), poll (T) → success
            False, False, True,   # second call: pre-check (F), poll (F), poll (T) → success
        ]

        processes = []

        def popen_side_effect(*args, **kwargs):
            proc = MagicMock()
            proc.poll.return_value = None  # alive by default
            processes.append(proc)
            return proc

        with patch("ollamachat.core.llama_runner.subprocess.Popen",
                   side_effect=popen_side_effect) as popen:
            # Reset module-level state
            import ollamachat.core.llama_runner as runner_mod
            runner_mod._server_process = None

            from ollamachat.core.llama_runner import start_server, stop_server

            # First call: spawn tracked process
            ok1, msg1 = start_server("/fake/model1.gguf", client, timeout=0.5)
            assert ok1 is True, f"First start_server failed: {msg1}"

            # Get the tracked process
            old_process = runner_mod._server_process
            assert old_process is not None
            assert len(processes) == 1

            # Make the old process appear already-exited so stop_server
            # doesn't try to kill it (which would block with time.sleep)
            old_process.poll.return_value = 0  # exited

            # Second call: should stop old process before spawning new one
            ok2, msg2 = start_server("/fake/model2.gguf", client, timeout=0.5)
            assert ok2 is True, f"Second start_server failed: {msg2}"

            # A new process should have been spawned
            assert len(processes) == 2

            # The tracking reference should point to the new process
            new_process = runner_mod._server_process
            assert new_process is not old_process
            assert new_process is processes[1]

    # ── stop_server ─────────────────────────────────────────────────────

    def test_stop_server_graceful_exit(self):
        """Given a tracked process that exits on terminate, kill is NOT called."""
        import ollamachat.core.llama_runner as runner_mod
        runner_mod._server_process = None

        with patch("ollamachat.core.llama_runner.subprocess.Popen") as popen:
            from ollamachat.core.llama_runner import stop_server

            proc = MagicMock()
            proc.poll.return_value = None  # alive
            # After 2 polls (0.2s), poll returns 0 (exited)
            proc.poll.side_effect = [None, None, 0]
            runner_mod._server_process = proc

            stop_server()

            proc.terminate.assert_called_once()
            proc.kill.assert_not_called()
            assert runner_mod._server_process is None

    def test_stop_server_kill_fallback(self):
        """Given a tracked process that ignores terminate, kill is called."""
        import ollamachat.core.llama_runner as runner_mod
        runner_mod._server_process = None

        # Mock time.sleep to speed up the 5s wait
        with patch("ollamachat.core.llama_runner.time.sleep"), \
             patch("ollamachat.core.llama_runner.subprocess.Popen") as popen:
            from ollamachat.core.llama_runner import stop_server

            proc = MagicMock()
            proc.poll.return_value = None  # Never exits
            runner_mod._server_process = proc

            stop_server()

            proc.terminate.assert_called_once()
            proc.kill.assert_called_once()
            assert runner_mod._server_process is None

    def test_stop_server_no_op_when_idle(self):
        """Given no tracked process, stop_server is a no-op."""
        import ollamachat.core.llama_runner as runner_mod
        runner_mod._server_process = None

        from ollamachat.core.llama_runner import stop_server

        # Should not raise
        stop_server()
        assert runner_mod._server_process is None
