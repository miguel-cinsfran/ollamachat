"""Tests for LlamaClient module — strict TDD, RED first, then GREEN."""

import json
import sys
import threading
import time
import types
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests


# ─── Wx module stub ──────────────────────────────────────────────────────────


def _ensure_wx_module():
    """Ensure wx module exists in sys.modules for patching wx.CallAfter."""
    if "wx" not in sys.modules:
        wx_mod = types.ModuleType("wx")

        def call_after(fn, *args):
            fn(*args)

        wx_mod.CallAfter = call_after
        sys.modules["wx"] = wx_mod


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def ensure_wx():
    """Ensure wx module is available for all tests."""
    _ensure_wx_module()
    yield


@pytest.fixture
def mock_session():
    """Inject a fake requests.Session."""
    return Mock(spec=requests.Session)


@pytest.fixture
def mock_call_after():
    """Capture wx.CallAfter calls for assertion."""
    calls = []

    def fake_call_after(fn, *args):
        calls.append((fn, args))
        # Invoke immediately so tests can assert on effects
        fn(*args)

    with patch("wx.CallAfter", side_effect=fake_call_after):
        yield calls


# ─── Test class ───────────────────────────────────────────────────────────────


class TestLlamaClient:
    """Tests for LlamaClient."""

    # ── check_running ────────────────────────────────────────────────────

    def test_check_running_returns_true_on_200_ok(self, mock_session):
        """Given 200 OK with status ok, check_running returns True."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_session.get.return_value = mock_response

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        assert client.check_running() is True

    def test_check_running_returns_false_on_connection_error(self, mock_session):
        """Given ConnectionError, check_running returns False."""
        mock_session.get.side_effect = requests.ConnectionError("refused")

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        assert client.check_running() is False

    def test_check_running_returns_false_on_503(self, mock_session):
        """Given 503, check_running returns False."""
        mock_response = Mock()
        mock_response.status_code = 503
        mock_session.get.return_value = mock_response

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        assert client.check_running() is False

    def test_check_running_returns_false_on_timeout(self, mock_session):
        """Given requests.Timeout, check_running returns False."""
        mock_session.get.side_effect = requests.exceptions.Timeout("timed out")

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        assert client.check_running() is False

    # ── get_loaded_model ─────────────────────────────────────────────────

    def test_get_loaded_model_returns_id(self, mock_session):
        """Given 200 OK with data, get_loaded_model returns the model id."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [{"id": "llama-3.1-8b-q4.gguf"}]
        }
        mock_session.get.return_value = mock_response

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        result = client.get_loaded_model()
        assert result == "llama-3.1-8b-q4.gguf"

    def test_get_loaded_model_returns_empty_on_error(self, mock_session):
        """Given ConnectionError, get_loaded_model returns ''."""
        mock_session.get.side_effect = requests.ConnectionError("refused")

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        assert client.get_loaded_model() == ""

    # ── chat_stream — SSE dispatch ───────────────────────────────────────

    def _stub_stream(self, mock_session, lines: list[bytes]):
        """Helper: stub POST to return a response whose iter_lines yields lines.

        The production code uses `with session.post(...) as response:`,
        so we configure the mock so that ``__enter__()`` returns the
        same mock_response object (rather than a fresh child mock) and
        ``__exit__()`` returns False.
        """
        mock_response = MagicMock()
        mock_response.iter_lines.return_value = lines
        mock_response.status_code = 200
        mock_response.reason = "OK"
        ctx = MagicMock()
        ctx.__enter__.return_value = mock_response
        ctx.__exit__.return_value = False
        mock_session.post.return_value = ctx

    def test_chat_stream_two_events_then_done(self, mock_session, mock_call_after):
        """Given two SSE events then [DONE], on_token fires twice and on_donce once."""
        self._stub_stream(mock_session, [
            b'data: {"choices":[{"delta":{"content":"Hello "}}]}',
            b'data: {"choices":[{"delta":{"content":"World"}}]}',
            b'data: [DONE]',
        ])

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        on_token = Mock()
        on_done = Mock()
        on_error = Mock()

        client.chat_stream([], {}, on_token, on_done, on_error)
        time.sleep(0.1)

        assert on_token.call_count == 2
        assert on_token.call_args_list[0][0][0] == "Hello "
        assert on_token.call_args_list[1][0][0] == "World"
        assert on_done.call_count == 1
        assert on_error.call_count == 0

    def test_chat_stream_post_raises_invokes_on_error(self, mock_session, mock_call_after):
        """Given ConnectionError in POST, on_error fires with error text."""
        mock_session.post.side_effect = requests.ConnectionError("Connection refused")

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        on_token = Mock()
        on_done = Mock()
        on_error = Mock()

        client.chat_stream([], {}, on_token, on_done, on_error)
        time.sleep(0.1)

        assert on_error.call_count == 1
        assert "ConnectionError" in on_error.call_args[0][0]
        assert on_done.call_count == 0

    def test_chat_stream_request_body_shape(self, mock_session, mock_call_after):
        """Given options, the POST body has correct shape (no options sub-object)."""
        options = {
            "temperature": 0.7,
            "max_tokens": 256,
            "top_p": 0.9,
            "top_k": 40,
            "repeat_penalty": 1.1,
        }
        messages = [{"role": "user", "content": "hello"}]
        self._stub_stream(mock_session, [
            b'data: {"choices":[{"delta":{"content":"ok"}}]}',
            b'data: [DONE]',
        ])

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        client.chat_stream(messages, options, Mock(), Mock(), Mock())
        time.sleep(0.1)

        _, kwargs = mock_session.post.call_args
        body = kwargs["json"]
        assert body["model"] == "local"
        assert body["stream"] is True
        assert body["messages"] == messages
        assert body["temperature"] == 0.7
        assert body["max_tokens"] == 256
        assert body["top_p"] == 0.9
        assert body["top_k"] == 40
        assert body["repeat_penalty"] == 1.1
        # Verify NO options sub-object
        assert "options" not in body

    def test_chat_stream_skips_malformed_json(self, mock_session, mock_call_after):
        """Given malformed JSON line, it's skipped and valid events are forwarded."""
        self._stub_stream(mock_session, [
            b'data: {not json}',
            b'data: {"choices":[{"delta":{"content":"good"}}]}',
            b'data: [DONE]',
        ])

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        on_token = Mock()
        on_done = Mock()
        on_error = Mock()

        client.chat_stream([], {}, on_token, on_done, on_error)
        time.sleep(0.1)

        assert on_token.call_count == 1
        assert on_token.call_args[0][0] == "good"
        assert on_done.call_count == 1
        assert on_error.call_count == 0

    def test_chat_stream_handles_blank_and_comment_lines(self, mock_session, mock_call_after):
        """Given blank lines and SSE comments interleaved with valid events,
        the parser skips them and forwards only valid events.

        requests.iter_lines() already buffers bytes until a newline, so
        each yielded line is a complete SSE line. The parser is only
        responsible for line-level filtering (blank, comment, event, id).
        """
        self._stub_stream(mock_session, [
            b'',                                          # blank (SSE event separator)
            b': heartbeat comment',                       # SSE comment
            b'data: {"choices":[{"delta":{"content":"ok"}}]}',
            b'',                                          # blank
            b'data: [DONE]',
        ])

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        on_token = Mock()
        on_done = Mock()
        on_error = Mock()

        client.chat_stream([], {}, on_token, on_done, on_error)
        time.sleep(0.1)

        assert on_token.call_count == 1
        assert on_token.call_args[0][0] == "ok"
        assert on_done.call_count == 1
        assert on_error.call_count == 0

    # ── abort semantics ──────────────────────────────────────────────────

    def test_abort_stops_stream_between_chunks(self, mock_session, mock_call_after):
        """Given abort mid-stream, fewer than 100 tokens fire and on_done fires."""
        def slow_iter_lines():
            for i in range(100):
                line = ('data: %s' % json.dumps(
                    {"choices": [{"delta": {"content": f"token{i}"}}]}
                )).encode()
                yield line
                time.sleep(0.005)
            yield b'data: [DONE]'

        mock_response = MagicMock()
        mock_response.iter_lines.return_value = slow_iter_lines()
        mock_response.status_code = 200
        mock_response.reason = "OK"
        ctx = MagicMock()
        ctx.__enter__.return_value = mock_response
        ctx.__exit__.return_value = False
        mock_session.post.return_value = ctx

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        on_token = Mock()
        on_done = Mock()
        on_error = Mock()

        client.chat_stream([], {}, on_token, on_done, on_error)
        time.sleep(0.03)  # let a few tokens through
        client.abort()
        time.sleep(0.1)  # let thread exit

        assert 0 < on_token.call_count < 100, (
            f"Expected some (<100) tokens, got {on_token.call_count}"
        )
        assert on_done.call_count == 1
        assert on_error.call_count == 0

    def test_abort_is_noop_when_idle(self, mock_session, mock_call_after):
        """Given abort before any stream, no exception and no callbacks."""
        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        # Should not raise
        client.abort()
        # Verify no callbacks happened (session.post was never called)
        mock_session.post.assert_not_called()

    # ── on_usage (v0.3.0) ────────────────────────────────────────────────

    def test_chat_stream_calls_on_usage_when_present(self, mock_session, mock_call_after):
        """Given a stream with usage in final chunk, on_usage is called with the dict."""
        self._stub_stream(mock_session, [
            b'data: {"choices":[{"delta":{"content":"hi"}}]}',
            b'data: {"choices":[{"delta":{"content":" there"}}]}',
            b'data: {"usage": {"prompt_tokens": 12, "completion_tokens": 80, "total_tokens": 92}}',
            b'data: [DONE]',
        ])

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        on_token = Mock()
        on_done = Mock()
        on_error = Mock()
        on_usage = Mock()

        client.chat_stream([], {}, on_token, on_done, on_error, on_usage=on_usage)
        time.sleep(0.1)

        assert on_usage.call_count == 1
        usage_arg = on_usage.call_args[0][0]
        assert usage_arg["prompt_tokens"] == 12
        assert usage_arg["completion_tokens"] == 80
        assert usage_arg["total_tokens"] == 92
        assert on_token.call_count == 2
        assert on_done.call_count == 1
        assert on_error.call_count == 0

    def test_chat_stream_no_error_when_usage_absent(self, mock_session, mock_call_after):
        """Given a stream with no usage key, no error and normal callbacks fire."""
        self._stub_stream(mock_session, [
            b'data: {"choices":[{"delta":{"content":"hello"}}]}',
            b'data: [DONE]',
        ])

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        on_token = Mock()
        on_done = Mock()
        on_error = Mock()

        # No on_usage passed (default None) — should not error
        client.chat_stream([], {}, on_token, on_done, on_error)
        time.sleep(0.1)

        assert on_token.call_count == 1
        assert on_token.call_args[0][0] == "hello"
        assert on_done.call_count == 1
        assert on_error.call_count == 0

    # ── tool_calls (v0.4.0) ──────────────────────────────────────────────

    def test_chat_stream_passes_tools_in_body(self, mock_session, mock_call_after):
        """Given tools are passed, the POST body contains tools and tool_choice."""
        self._stub_stream(mock_session, [
            b'data: {"choices":[{"delta":{"content":"ok"}}]}',
            b'data: [DONE]',
        ])

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        on_token = Mock()
        on_done = Mock()
        on_error = Mock()

        tools = [{"type": "function", "function": {"name": "shell_execute"}}]
        client.chat_stream([], {}, on_token, on_done, on_error, tools=tools)
        time.sleep(0.1)

        _, kwargs = mock_session.post.call_args
        body = kwargs["json"]
        assert body["tools"] == tools
        assert body["tool_choice"] == "auto"

    def test_chat_stream_no_tools_when_none(self, mock_session, mock_call_after):
        """Given tools=None, the POST body does NOT contain tools or tool_choice."""
        self._stub_stream(mock_session, [
            b'data: {"choices":[{"delta":{"content":"ok"}}]}',
            b'data: [DONE]',
        ])

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        on_token = Mock()
        on_done = Mock()
        on_error = Mock()

        # tools defaults to None — no tools/tool_choice in body
        client.chat_stream([], {}, on_token, on_done, on_error)
        time.sleep(0.1)

        _, kwargs = mock_session.post.call_args
        body = kwargs["json"]
        assert "tools" not in body
        assert "tool_choice" not in body

    def test_chat_stream_calls_on_tool_call(self, mock_session, mock_call_after):
        """Given SSE with tool_calls delta and finish_reason=tool_calls,
        on_tool_call is called with parsed args."""
        self._stub_stream(mock_session, [
            b'data: {"choices":[{"delta":{"content":"I will run that."}}]}',
            b'data: {"choices":[{"finish_reason":"tool_calls","delta":{"tool_calls":[{"index":0,"id":"call_abc","function":{"name":"shell_execute","arguments":"{\\"command\\":\\"ls\\"}"}}]}}]}',
            b'data: [DONE]',
        ])

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        on_token = Mock()
        on_done = Mock()
        on_error = Mock()
        on_tool_call = Mock()

        client.chat_stream([], {}, on_token, on_done, on_error,
                           on_tool_call=on_tool_call)
        time.sleep(0.1)

        assert on_tool_call.call_count == 1
        name, call_id, args = on_tool_call.call_args[0]
        assert name == "shell_execute"
        assert call_id == "call_abc"
        assert args == {"command": "ls"}
        assert on_token.call_count == 1
        assert on_done.call_count == 1
        assert on_error.call_count == 0

    def test_chat_stream_accumulates_tool_call_arguments(self, mock_session, mock_call_after):
        """Given tool_call arguments split across 3 SSE chunks,
        on_tool_call receives the reassembled dict."""
        self._stub_stream(mock_session, [
            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_x","function":{"name":"shell_execute","arguments":"{"}}]}}]}',
            b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\\"command\\": \\"ls\\""}}]}}]}',
            b'data: {"choices":[{"finish_reason":"tool_calls","delta":{"tool_calls":[{"index":0,"function":{"arguments":"}"}}]}}]}',
            b'data: [DONE]',
        ])

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        on_token = Mock()
        on_done = Mock()
        on_error = Mock()
        on_tool_call = Mock()

        client.chat_stream([], {}, on_token, on_done, on_error,
                           on_tool_call=on_tool_call)
        time.sleep(0.1)

        assert on_tool_call.call_count == 1
        name, call_id, args = on_tool_call.call_args[0]
        assert name == "shell_execute"
        assert call_id == "call_x"
        assert args == {"command": "ls"}
        assert on_done.call_count == 1
        assert on_error.call_count == 0

    def test_chat_stream_malformed_json_falls_back_to_raw(self, mock_session, mock_call_after):
        """Given tool_call with malformed JSON arguments, on_tool_call receives
        {"raw": <accumulated_string>} instead of a parsed dict."""
        self._stub_stream(mock_session, [
            b'data: {"choices":[{"finish_reason":"tool_calls","delta":{"tool_calls":[{"index":0,"id":"call_bad","function":{"name":"shell_execute","arguments":"not valid json {"}}]}}]}',
            b'data: [DONE]',
        ])

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        on_tool_call = Mock()
        on_done = Mock()
        on_error = Mock()

        client.chat_stream([], {}, Mock(), on_done, on_error,
                           on_tool_call=on_tool_call)
        time.sleep(0.1)

        assert on_tool_call.call_count == 1
        name, call_id, args = on_tool_call.call_args[0]
        assert name == "shell_execute"
        assert call_id == "call_bad"
        assert "raw" in args
        assert args["raw"] == "not valid json {"
        assert on_error.call_count == 0

    def test_chat_stream_no_tool_call_when_finish_reason_stop(self, mock_session, mock_call_after):
        """Given finish_reason=stop and a non-None on_tool_call, the callback
        is NOT invoked — only tool_calls finish_reason triggers it."""
        self._stub_stream(mock_session, [
            b'data: {"choices":[{"delta":{"content":"Sure!"}}]}',
            b'data: {"choices":[{"finish_reason":"stop","delta":{}}]}',
            b'data: [DONE]',
        ])

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        on_tool_call = Mock()
        on_done = Mock()

        client.chat_stream([], {}, Mock(), on_done, Mock(),
                           on_tool_call=on_tool_call)
        time.sleep(0.1)

        assert on_tool_call.call_count == 0
        assert on_done.call_count == 1
