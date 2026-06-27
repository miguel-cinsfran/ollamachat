"""Tests for LlamaClient module — strict TDD, RED first, then GREEN."""

import json
import sys
import threading
import time
import types
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests


# ─── request_timeout (v0.7.1) ────────────────────────────────────────────────


class TestLlamaClientRequestTimeout:
    """Tests for configurable request_timeout."""

    def test_default_request_timeout_is_120(self):
        """GIVEN LlamaClient() without request_timeout
        THEN request_timeout == 120."""
        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=Mock(spec=requests.Session))
        assert client.request_timeout == 120

    def test_custom_request_timeout_is_stored(self):
        """GIVEN LlamaClient(request_timeout=300)
        THEN request_timeout == 300."""
        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(
            session=Mock(spec=requests.Session),
            request_timeout=300,
        )
        assert client.request_timeout == 300

    def test_request_timeout_reaches_session_post(self, mock_session, mock_call_after):
        """GIVEN LlamaClient(request_timeout=300)
        WHEN chat_stream is called
        THEN session.post is called with timeout=300."""
        mock_response = MagicMock()
        mock_response.iter_lines.return_value = [
            b'data: {"choices":[{"delta":{"content":"ok"}}]}',
            b'data: [DONE]',
        ]
        mock_response.status_code = 200
        mock_response.reason = "OK"
        ctx = MagicMock()
        ctx.__enter__.return_value = mock_response
        ctx.__exit__.return_value = False
        mock_session.post.return_value = ctx

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session, request_timeout=300)
        client.chat_stream([], {}, Mock(), Mock(), Mock())
        time.sleep(0.1)

        _, kwargs = mock_session.post.call_args
        assert kwargs.get("timeout") == 300

    def test_health_check_timeout_unchanged(self, mock_session):
        """GIVEN LlamaClient(request_timeout=300)
        WHEN check_running() / check_state() is called
        THEN the GET is called with timeout=5 (unchanged)."""
        from bellbird.core.llama_client import LlamaClient

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_session.get.return_value = mock_response

        client = LlamaClient(session=mock_session, request_timeout=300)
        client.check_running()
        client.check_state()

        assert mock_session.get.call_count == 2
        for call_args in mock_session.get.call_args_list:
            _, kwargs = call_args
            assert kwargs.get("timeout") == 5, (
                "Health-check timeout must remain 5s, not be affected by "
                "request_timeout"
            )


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
            "min_p": 0.05,
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
        assert body["min_p"] == 0.05
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

    def test_chat_stream_empty_choices_usage_chunk_no_indexerror(
        self, mock_session, mock_call_after
    ):
        """Final chunk with ``"choices": []`` must not raise IndexError.

        With ``stream_options.include_usage`` (the F2 context meter) llama.cpp
        sends a terminal chunk whose ``choices`` is an EMPTY LIST carrying only
        ``usage``. ``chunk.get("choices", [{}])[0]`` only falls back when the
        key is absent, so ``[][0]`` raised "IndexError: list index out of range"
        on every generation. This pins the empty-list handling.
        """
        self._stub_stream(mock_session, [
            b'data: {"choices":[{"delta":{"content":"hola"}}]}',
            b'data: {"choices":[],"usage":{"prompt_tokens":3,"completion_tokens":1,"total_tokens":4}}',
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

        assert on_error.call_count == 0, on_error.call_args
        assert on_token.call_count == 1
        assert on_done.call_count == 1
        assert on_usage.call_count == 1
        assert on_usage.call_args[0][0]["total_tokens"] == 4

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


# ─── on_reasoning routing (v0.7.3) ────────────────────────────────────────────


class TestLlamaClientReasoning:
    """Tests for the ``on_reasoning`` callback in ``chat_stream``."""

    def test_reasoning_content_routes_only_to_on_reasoning(self, mock_session, mock_call_after):
        """``delta.reasoning_content`` fires ``on_reasoning``, NOT ``on_token``."""
        self._stub_stream(mock_session, [
            b'data: {"choices":[{"delta":{"reasoning_content":"Let me think","content":""}}]}',
            b'data: {"choices":[{"delta":{"content":"Answer"}}]}',
            b'data: [DONE]',
        ])

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        on_token = Mock()
        on_done = Mock()
        on_error = Mock()
        on_reasoning = Mock()

        client.chat_stream(
            [], {}, on_token, on_done, on_error,
            on_reasoning=on_reasoning,
        )
        import time
        time.sleep(0.2)

        assert on_reasoning.call_count == 1, (
            f"on_reasoning called {on_reasoning.call_count} times, expected 1"
        )
        assert "Let me think" in on_reasoning.call_args[0][0], (
            f"on_reasoning got {on_reasoning.call_args[0][0]!r}"
        )
        assert on_token.call_count == 1, (
            f"on_token called {on_token.call_count} times, expected 1 (only content)"
        )
        assert "Answer" in on_token.call_args[0][0]
        assert on_done.call_count == 1
        assert on_error.call_count == 0

    def test_reasoning_skipped_when_callback_none(self, mock_session, mock_call_after):
        """``on_reasoning=None`` with reasoning_content present does not crash."""
        self._stub_stream(mock_session, [
            b'data: {"choices":[{"delta":{"reasoning_content":"thinking...","content":""}}]}',
            b'data: {"choices":[{"delta":{"content":"result"}}]}',
            b'data: [DONE]',
        ])

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        on_token = Mock()
        on_done = Mock()
        on_error = Mock()

        # No on_reasoning passed — should not crash
        client.chat_stream([], {}, on_token, on_done, on_error)
        import time
        time.sleep(0.2)

        assert on_token.call_count == 1
        assert on_done.call_count == 1
        assert on_error.call_count == 0

    def test_content_chunks_pass_through_parser(self, mock_session, mock_call_after):
        """Inline <think> in delta.content triggers on_reasoning via parser."""
        self._stub_stream(mock_session, [
            b'data: {"choices":[{"delta":{"content":"<think> hidden</think> visible"}}]}',
            b'data: [DONE]',
        ])

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        on_token = Mock()
        on_done = Mock()
        on_error = Mock()
        on_reasoning = Mock()

        client.chat_stream(
            [], {}, on_token, on_done, on_error,
            on_reasoning=on_reasoning,
        )
        import time
        time.sleep(0.2)

        assert on_reasoning.call_count == 1, (
            f"on_reasoning called {on_reasoning.call_count} times"
        )
        reasoning_text = on_reasoning.call_args[0][0]
        assert "hidden" in reasoning_text, f"got {reasoning_text!r}"
        assert on_token.call_count == 1
        token_text = on_token.call_args[0][0]
        assert "visible" in token_text, f"got {token_text!r}"
        assert on_done.call_count == 1

    def test_parser_does_not_get_delta_reasoning_content(self, mock_session, mock_call_after):
        """When ``delta.reasoning_content`` is present, it is NOT fed to parser."""
        self._stub_stream(mock_session, [
            b'data: {"choices":[{"delta":{"reasoning_content":"X","content":""}}]}',
            b'data: [DONE]',
        ])

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        on_token = Mock()
        on_done = Mock()
        on_error = Mock()
        on_reasoning = Mock()

        client.chat_stream(
            [], {}, on_token, on_done, on_error,
            on_reasoning=on_reasoning,
        )
        import time
        time.sleep(0.2)

        assert on_reasoning.call_count == 1
        # on_token should NOT be called (content is empty and reasoning
        # content was not fed to the parser)
        assert on_token.call_count == 0, (
            f"on_token was called {on_token.call_count} times — "
            "reasoning_content should NOT go through the parser"
        )
        assert on_done.call_count == 1

    # Helper — reuse the same pattern from TestLlamaClient
    def _stub_stream(self, mock_session, lines: list[bytes]):
        """Helper: stub POST to return a response whose iter_lines yields lines."""
        from unittest.mock import MagicMock

        mock_response = MagicMock()
        mock_response.iter_lines.return_value = lines
        mock_response.status_code = 200
        mock_response.reason = "OK"
        ctx = MagicMock()
        ctx.__enter__.return_value = mock_response
        ctx.__exit__.return_value = False
        mock_session.post.return_value = ctx


# ─── _ThinkTagParser (v0.7.3) ────────────────────────────────────────────────


class TestThinkTagParser:
    """Tests for the inline <think>/<thinking>/<thought> tag parser.

    All test chunks include the opening '<' character,
    split across feed() calls to simulate token streaming.
    """

    def test_split_across_two_chunks(self):
        """Given <thi> nk> Hello</think> World, reasoning=Hello content=World.

        Note: the opening tag must be followed by whitespace (conservative
        match), so the chunk after the complete <think> starts with space.
        """
        from bellbird.core.llama_client import _ThinkTagParser

        p = _ThinkTagParser()
        out = []
        out.extend(p.feed("<thi"))
        out.extend(p.feed("nk> Hello</think>"))
        out.extend(p.feed("World"))
        out.extend(p.flush())

        reasoning_text = "".join(text for t, text in out if t == "reasoning")
        content_text = "".join(text for t, text in out if t == "content")
        assert "Hello" in reasoning_text, f"reasoning={reasoning_text!r}"
        assert "World" in content_text, f"content={content_text!r}"

    def test_split_across_three_chunks(self):
        """Given <thin> k> deep\n thought</think> out."""
        from bellbird.core.llama_client import _ThinkTagParser

        p = _ThinkTagParser()
        out = []
        out.extend(p.feed("<thin"))
        out.extend(p.feed("k> deep\n"))
        out.extend(p.feed("thought</think>out"))
        out.extend(p.flush())

        reasoning_text = "".join(text for t, text in out if t == "reasoning")
        content_text = "".join(text for t, text in out if t == "content")
        assert "deep" in reasoning_text, f"reasoning={reasoning_text!r}"
        assert "thought" in reasoning_text
        assert "out" in content_text, f"content={content_text!r}"

    def test_split_across_four_chunks(self):
        """Given <th> ink> A\nB\n C</think> D."""
        from bellbird.core.llama_client import _ThinkTagParser

        p = _ThinkTagParser()
        out = []
        out.extend(p.feed("<th"))
        out.extend(p.feed("ink> "))
        out.extend(p.feed("A\nB\n"))
        out.extend(p.feed("C</think>D"))
        out.extend(p.flush())

        reasoning_text = "".join(text for t, text in out if t == "reasoning")
        content_text = "".join(text for t, text in out if t == "content")
        assert "A" in reasoning_text, f"reasoning={reasoning_text!r}"
        assert "B" in reasoning_text
        assert "C" in reasoning_text
        assert "D" in content_text, f"content={content_text!r}"

    def test_case_insensitive(self):
        """Given <THINK>, <Thinking>, <thought> all work case-insensitively."""
        from bellbird.core.llama_client import _ThinkTagParser

        p = _ThinkTagParser()
        out = []
        out.extend(p.feed("<THINK> Hello</THINK> World"))
        out.extend(p.flush())
        assert any(t == "reasoning" for t, _ in out)
        assert any(t == "content" for t, _ in out)

        p2 = _ThinkTagParser()
        out2 = []
        out2.extend(p2.feed("<Thinking> Hi</Thinking> There"))
        out2.extend(p2.flush())
        assert any(t == "reasoning" for t, _ in out2)

        p3 = _ThinkTagParser()
        out3 = []
        out3.extend(p3.feed("<thought> secret</thought> visible"))
        out3.extend(p3.flush())
        assert any(t == "reasoning" for t, _ in out3)

    def test_false_positive_guard(self):
        """Given literal <think> inside code, no block is opened.

        <think> followed by non-whitespace is NOT an opening tag.
        """
        from bellbird.core.llama_client import _ThinkTagParser

        p = _ThinkTagParser()
        out = []
        out.extend(p.feed('print("<think>Hello")'))
        out.extend(p.flush())
        # No reasoning should be emitted — all content
        assert all(t == "content" for t, _ in out), (
            f"Expected all content, got {out}"
        )

    def test_false_positive_guard_with_newline(self):
        """Given <think>\\n then content, the block IS opened."""
        from bellbird.core.llama_client import _ThinkTagParser

        p = _ThinkTagParser()
        out = []
        out.extend(p.feed("<think>\n"))
        out.extend(p.feed("explanation\n"))
        out.extend(p.feed("</think>\n"))
        out.extend(p.feed("Answer"))
        out.extend(p.flush())
        reasoning_text = "".join(text for t, text in out if t == "reasoning")
        content_text = "".join(text for t, text in out if t == "content")
        assert "explanation" in reasoning_text, f"reasoning={reasoning_text!r}"
        assert "Answer" in content_text, f"content={content_text!r}"

    def test_fresh_parser_per_stream(self):
        """Given separate parsers, no state carries over."""
        from bellbird.core.llama_client import _ThinkTagParser

        p1 = _ThinkTagParser()
        out1 = []
        out1.extend(p1.feed("<think> secret</think> done"))
        out1.extend(p1.flush())
        assert any(t == "reasoning" for t, _ in out1)

        # A fresh parser starts clean (no leftover state from p1)
        p2 = _ThinkTagParser()
        out2 = []
        out2.extend(p2.feed("no tags here"))
        out2.extend(p2.flush())
        assert all(t == "content" for t, _ in out2), (
            f"Fresh parser leaked state: {out2}"
        )

    def test_all_three_tag_names(self):
        """Three separate parsers handle <think>, <thinking>, <thought>."""
        from bellbird.core.llama_client import _ThinkTagParser

        for tag in ("think", "thinking", "thought"):
            p = _ThinkTagParser()
            out = []
            out.extend(p.feed(f"<{tag}> inner </{tag}> outer"))
            out.extend(p.flush())
            reasoning = [text for t, text in out if t == "reasoning"]
            content = [text for t, text in out if t == "content"]
            assert reasoning, f"No reasoning for <{tag}>"
            assert "inner" in "".join(reasoning), f"reasoning={reasoning}"
            assert "outer" in "".join(content), f"content={content}"


# ─── AST invariants (v0.7.3) ──────────────────────────────────────────────────


def test_ast_stream_worker_does_not_call_on_token_with_reasoning_content():
    """``_stream_worker`` does NOT call ``wx.CallAfter(on_token, ...)`` with
    ``delta.reasoning_content``.

    Reasoning content must be routed to ``on_reasoning`` only. The worker
    code must NOT have ``wx.CallAfter(on_token, reasoning)`` or similar
    patterns (line 322 in the v0.7.1 code).
    """
    import pathlib
    src = (
        pathlib.Path(__file__).resolve().parent.parent.parent
        / "bellbird/core/llama_client.py"
    ).read_text(encoding="utf-8")

    # The _stream_worker should reference reasoning_content only in the
    # context of on_reasoning, not on_token.
    # Simple check: find the _stream_worker method and verify no
    # CallAfter(on_token, reasoning) pattern exists.
    import re
    m = re.search(
        r"def _stream_worker\(.*?\) -> None:.*?(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_stream_worker method not found in llama_client.py"
    body = m.group(0)

    # The old bug was: wx.CallAfter(on_token, reasoning)
    # Verify this pattern is NOT present
    assert "wx.CallAfter(on_token, reasoning)" not in body, (
        "BUG REINTRODUCED: _stream_worker calls wx.CallAfter(on_token, reasoning) "
        "— reasoning content must go to on_reasoning only"
    )

    # Verify that reasoning_content is associated with on_reasoning
    assert "on_reasoning" in body, (
        "_stream_worker must reference on_reasoning to handle "
        "reasoning_content routing"
    )


# ─── check_tool_support (v0.7.5) ─────────────────────────────────────────────


class TestCheckToolSupport:
    """Tests for LlamaClient.check_tool_support()."""

    def test_check_tool_support_true(self, mock_session):
        """Given /props returns chat_template_tool_use=True, returns True."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"chat_template_tool_use": True}
        mock_session.get.return_value = mock_response

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        assert client.check_tool_support() is True
        mock_session.get.assert_called_once()

    def test_check_tool_support_false(self, mock_session):
        """Given /props returns empty dict, returns False."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_session.get.return_value = mock_response

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        assert client.check_tool_support() is False

    def test_check_tool_support_cached(self, mock_session):
        """Second call does NOT make an HTTP request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"chat_template_tool_use": True}
        mock_session.get.return_value = mock_response

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        assert client.check_tool_support() is True
        assert client.check_tool_support() is True
        # Only one HTTP call
        mock_session.get.assert_called_once()

    def test_check_tool_support_connection_error(self, mock_session):
        """Given ConnectionError, returns False without raising."""
        mock_session.get.side_effect = requests.ConnectionError("refused")

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        assert client.check_tool_support() is False

    def test_check_tool_support_timeout(self, mock_session):
        """Given Timeout, returns False without raising."""
        mock_session.get.side_effect = requests.exceptions.Timeout("timed out")

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        assert client.check_tool_support() is False

    def test_check_tool_support_non_200(self, mock_session):
        """Given 503, returns False."""
        mock_response = Mock()
        mock_response.status_code = 503
        mock_session.get.return_value = mock_response

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        assert client.check_tool_support() is False

    def test_check_tool_support_malformed_json(self, mock_session):
        """Given non-JSON response, returns False without raising."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("bad json")
        mock_session.get.return_value = mock_response

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        assert client.check_tool_support() is False


# ─── on_timings callback (v0.9.0, T-WU1-09) ─────────────────────────────────


class TestOnTimings:
    """Tests for the on_timings callback in chat_stream."""

    def test_on_timings_fires_with_timings_dict(self, mock_session, mock_call_after):
        """GIVEN a stream with timings in the final chunk
        WHEN chat_stream(..., on_timings=<mock>) is called
        THEN on_timings is invoked with the timings dict."""
        mock_response = MagicMock()
        mock_response.iter_lines.return_value = [
            b'data: {"choices":[{"delta":{"content":"hi"}}]}',
            b'data: {"timings":{"predicted_per_second":18.4,"prompt_n":12,"predicted_n":80},"choices":[{"finish_reason":"stop","delta":{}}]}',
            b'data: [DONE]',
        ]
        mock_response.status_code = 200
        mock_response.reason = "OK"
        ctx = MagicMock()
        ctx.__enter__.return_value = mock_response
        ctx.__exit__.return_value = False
        mock_session.post.return_value = ctx

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        on_timings = Mock()
        on_done = Mock()
        on_error = Mock()

        client.chat_stream([], {}, Mock(), on_done, on_error, on_timings=on_timings)
        import time; time.sleep(0.15)

        assert on_timings.call_count == 1
        args = on_timings.call_args[0][0]
        assert args["predicted_per_second"] == 18.4

    def test_on_timings_none_does_not_crash(self, mock_session, mock_call_after):
        """GIVEN a stream with timings AND on_timings=None (default)
        WHEN chat_stream runs
        THEN no error occurs."""
        mock_response = MagicMock()
        mock_response.iter_lines.return_value = [
            b'data: {"choices":[{"delta":{"content":"ok"}}]}',
            b'data: {"timings":{"predicted_per_second":18.4},"choices":[{"finish_reason":"stop","delta":{}}]}',
            b'data: [DONE]',
        ]
        mock_response.status_code = 200
        mock_response.reason = "OK"
        ctx = MagicMock()
        ctx.__enter__.return_value = mock_response
        ctx.__exit__.return_value = False
        mock_session.post.return_value = ctx

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        on_done = Mock()
        on_error = Mock()

        # No exception should be raised
        client.chat_stream([], {}, Mock(), on_done, on_error)
        import time; time.sleep(0.15)
        assert on_done.call_count == 1

    def test_on_timings_fires_after_on_usage(self, mock_session, mock_call_after):
        """GIVEN a stream with both usage and timings in the final chunk
        WHEN chat_stream runs
        THEN both callbacks fire."""
        mock_response = MagicMock()
        mock_response.iter_lines.return_value = [
            b'data: {"choices":[{"delta":{"content":"ok"}}]}',
            b'data: {"usage":{"prompt_tokens":12,"completion_tokens":80,"total_tokens":92},"timings":{"predicted_per_second":18.4},"choices":[{"finish_reason":"stop","delta":{}}]}',
            b'data: [DONE]',
        ]
        mock_response.status_code = 200
        mock_response.reason = "OK"
        ctx = MagicMock()
        ctx.__enter__.return_value = mock_response
        ctx.__exit__.return_value = False
        mock_session.post.return_value = ctx

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        on_timings = Mock()
        on_usage = Mock()
        on_done = Mock()
        on_error = Mock()

        client.chat_stream(
            [], {}, Mock(), on_done, on_error,
            on_usage=on_usage, on_timings=on_timings,
        )
        import time; time.sleep(0.15)

        assert on_usage.call_count == 1
        assert on_timings.call_count == 1

    def test_on_timings_empty_timings_skipped(self, mock_session, mock_call_after):
        """GIVEN a stream with timings={} (empty dict)
        WHEN chat_stream(..., on_timings=<mock>) is called
        THEN on_timings is NOT invoked."""
        mock_response = MagicMock()
        mock_response.iter_lines.return_value = [
            b'data: {"choices":[{"delta":{"content":"ok"}}]}',
            b'data: {"timings":{},"choices":[{"finish_reason":"stop","delta":{}}]}',
            b'data: [DONE]',
        ]
        mock_response.status_code = 200
        mock_response.reason = "OK"
        ctx = MagicMock()
        ctx.__enter__.return_value = mock_response
        ctx.__exit__.return_value = False
        mock_session.post.return_value = ctx

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        on_timings = Mock()
        on_done = Mock()

        client.chat_stream([], {}, Mock(), on_done, Mock(), on_timings=on_timings)
        import time; time.sleep(0.15)

        assert on_timings.call_count == 0


# ─── include_usage wire contract regression (v0.9.0, T-WU1-10) ───────────────


class TestIncludeUsageRegression:
    """Regression test that pins stream_options.include_usage in the body."""

    def test_body_contains_include_usage(self, mock_session):
        """GIVEN a stubbed session.post
        WHEN chat_stream runs (no on_usage provided)
        THEN the JSON body contains 'stream_options': {'include_usage': True}."""
        mock_response = MagicMock()
        mock_response.iter_lines.return_value = [
            b'data: {"choices":[{"delta":{"content":"ok"}}]}',
            b'data: [DONE]',
        ]
        mock_response.status_code = 200
        mock_response.reason = "OK"
        ctx = MagicMock()
        ctx.__enter__.return_value = mock_response
        ctx.__exit__.return_value = False
        mock_session.post.return_value = ctx

        from bellbird.core.llama_client import LlamaClient

        client = LlamaClient(session=mock_session)
        client.chat_stream([], {}, Mock(), Mock(), Mock())
        import time; time.sleep(0.1)

        _, kwargs = mock_session.post.call_args
        body = kwargs["json"]
        assert body["stream"] is True
        assert body["stream_options"] == {"include_usage": True}
