"""LlamaClient — HTTP client for llama.cpp's OpenAI-compatible server.

Provides headless (wx-free) access to a local llama-server:
- Health check via GET /health
- Loaded model query via GET /v1/models
- Streaming chat via POST /v1/chat/completions with SSE parsing in a daemon thread
- Clean abort via threading.Event

All streaming callbacks are marshalled to the wx main thread via wx.CallAfter.
"""

import json
import threading
from collections.abc import Callable
from typing import Any

import requests


class LlamaClient:
    """Client for a local llama-server (llama.cpp's HTTP server).

    Args:
        base_url: Server URL (default http://localhost:8080).
        session: Optional requests.Session for test injection.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url
        self._session = session or requests.Session()
        self._stop_event = threading.Event()
        self._stream_thread: threading.Thread | None = None

    def check_running(self) -> bool:
        """Check if llama-server is running and healthy.

        Returns:
            True if GET /health returns 200 with {"status": "ok"},
            False otherwise (no raise).
        """
        try:
            response = self._session.get(
                f"{self.base_url}/health", timeout=5
            )
            if response.status_code != 200:
                return False
            body = response.json()
            return body.get("status") == "ok"
        except Exception:
            return False

    def get_loaded_model(self) -> str:
        """Get the id of the currently loaded model.

        Returns:
            Model id string from GET /v1/models data[0]["id"],
            or "" on any error (no raise).
        """
        try:
            response = self._session.get(
                f"{self.base_url}/v1/models", timeout=5
            )
            if response.status_code != 200:
                return ""
            data = response.json()
            models = data.get("data", [])
            if not models:
                return ""
            return models[0].get("id", "")
        except Exception:
            return ""

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        options: dict[str, Any],
        on_token: Callable[[str], None],
        on_done: Callable[[], None],
        on_error: Callable[[str], None],
        on_usage: Callable[[dict], None] | None = None,
        on_tool_call: Callable[[str, str, dict], None] | None = None,
        tools: list[dict] | None = None,
    ) -> None:
        """Start a streaming chat in a background daemon thread.

        POST /v1/chat/completions with SSE parsing. The request body
        contains sampling parameters at the root (not nested in options).

        If a previous stream is still running (e.g. the user clicked
        "Enviar" twice in quick succession), it is aborted and joined
        before the new stream starts. This prevents two concurrent
        workers from racing on wx.CallAfter and emitting interleaved
        tokens.

        Args:
            messages: List of message dicts with role and content.
            options: Sampling parameters dict (temperature, top_p, etc.).
            on_token: Called per token fragment via wx.CallAfter.
            on_done: Called once on successful completion via wx.CallAfter.
            on_error: Called once on error via wx.CallAfter.
            on_usage: Optional callback for usage stats dict via wx.CallAfter.
            on_tool_call: Optional callback for tool_calls delta, receives
                (tool_name, tool_call_id, arguments_dict) via wx.CallAfter.
            tools: Optional OpenAI-format tool catalog forwarded to the model.
        """
        # A1/A3: stop any in-flight stream before starting a new one.
        # Set the event first so the worker notices at its next line
        # boundary, then join with a short timeout so we don't block
        # the UI indefinitely.
        self._stop_event.set()
        if self._stream_thread is not None and self._stream_thread.is_alive():
            self._stream_thread.join(timeout=1.0)
            # If the thread is still alive after 1s (e.g. blocked in
            # iter_lines), we proceed anyway. The new stream will start
            # but the old one will eventually exit and discard its
            # tokens — CallAfter ordering may not be perfect, but no
            # callback is lost.

        self._stop_event.clear()
        self._stream_thread = threading.Thread(
            target=self._stream_worker,
            args=(messages, options, on_token, on_done, on_error, on_usage, on_tool_call, tools),
            daemon=True,
        )
        self._stream_thread.start()

    def abort(self) -> None:
        """Signal the streaming thread to stop after the current SSE line."""
        self._stop_event.set()

    def _stream_worker(
        self,
        messages: list[dict[str, Any]],
        options: dict[str, Any],
        on_token: Callable[[str], None],
        on_done: Callable[[], None],
        on_error: Callable[[str], None],
        on_usage: Callable[[dict], None] | None = None,
        on_tool_call: Callable[[str, str, dict], None] | None = None,
        tools: list[dict] | None = None,
    ) -> None:
        """Background thread worker for streaming chat.

        Imports wx locally to keep core/ wx-free at module level.
        Parses SSE lines from the llama-server response and dispatches
        callbacks via wx.CallAfter.
        """
        import wx  # Import wx only when needed (core/ is wx-free at top level)

        try:
            # Build the request body. The model key is set to "local" because
            # llama-server serves a single model chosen at startup; the API
            # requires the field but ignores its value. Sampling parameters
            # live at the root of the body (NOT nested in an options object)
            # because llama-server's OpenAI-compatible endpoint expects the
            # OpenAI schema, not the Ollama schema.
            body: dict[str, Any] = {
                "model": "local",
                "messages": messages,
                "stream": True,
            }
            body.update(options)

            if tools is not None:
                body["tools"] = tools
                body["tool_choice"] = "auto"

            # D9: use a context manager so the connection is released
            # back to the pool on exit even if an exception escapes
            # the parser. D10: check status_code so a 4xx/5xx response
            # is reported as an error instead of being silently parsed
            # as (empty) SSE.
            with self._session.post(
                f"{self.base_url}/v1/chat/completions",
                json=body,
                stream=True,
                timeout=60,
            ) as response:
                if response.status_code != 200:
                    error_text = (
                        f"Server returned HTTP {response.status_code}: "
                        f"{response.reason or 'no reason'}"
                    )
                    wx.CallAfter(on_error, error_text)
                    return

                # SSE parser. requests.iter_lines() already buffers bytes until
                # a newline, so each yielded item is a complete SSE line. We
                # therefore only need to handle the line-level protocol here:
                # skip blank/comment/event lines, recognize the "[DONE]"
                # terminator, parse data: lines as JSON, extract the delta
                # content, and forward it to on_token via wx.CallAfter.
                # Malformed JSON lines are silently skipped (REQ-LLAMA-003).
                # Tool-call deltas are accumulated by index and dispatched
                # when finish_reason == "tool_calls".
                _tc_buffer: dict[int, dict] = {}
                for line in response.iter_lines():
                    if self._stop_event.is_set():
                        break
                    if not line:
                        continue

                    decoded = line.decode("utf-8") if isinstance(line, bytes) else line
                    if not decoded.startswith("data: "):
                        continue  # blank, ":comment", "event:...", "id:..." → skip

                    payload = decoded[len("data: "):]
                    if payload == "[DONE]":
                        break

                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue  # malformed data line, skip

                    # Tool-call delta accumulation: extract before content
                    # so we capture finish_reason even on the final chunk.
                    finish_reason = (
                        chunk.get("choices", [{}])[0]
                        .get("finish_reason") or ""
                    )
                    tool_calls_delta = (
                        chunk.get("choices", [{}])[0]
                        .get("delta", {})
                        .get("tool_calls", [])
                    )
                    for tc in tool_calls_delta:
                        idx = tc["index"]
                        if idx not in _tc_buffer:
                            _tc_buffer[idx] = {"id": "", "name": "", "arguments": ""}
                        entry = _tc_buffer[idx]
                        if "id" in tc:
                            entry["id"] = tc["id"]
                        if "function" in tc:
                            fn = tc["function"]
                            if "name" in fn:
                                entry["name"] = fn["name"]
                            if "arguments" in fn:
                                entry["arguments"] += fn["arguments"]

                    # Usage callback: fire before content extraction so
                    # the on_usage hook runs even on the final chunk
                    # which may contain usage but no delta content.
                    if on_usage is not None:
                        usage = chunk.get("usage")
                        if usage is not None:
                            wx.CallAfter(on_usage, usage)

                    content = (
                        chunk.get("choices", [{}])[0]
                        .get("delta", {})
                        .get("content", "")
                    )
                    if content:
                        wx.CallAfter(on_token, content)

                    # Dispatch tool_calls when finish_reason signals it.
                    if finish_reason == "tool_calls" and on_tool_call is not None:
                        for entry in _tc_buffer.values():
                            try:
                                args = json.loads(entry["arguments"])
                            except json.JSONDecodeError:
                                args = {"raw": entry["arguments"]}
                            wx.CallAfter(
                                on_tool_call, entry["name"], entry["id"], args
                            )
                        _tc_buffer.clear()

            wx.CallAfter(on_done)

        except Exception as e:
            error_text = f"{type(e).__name__}: {e}"
            try:
                wx.CallAfter(on_error, error_text)
            except Exception:
                pass  # Last resort: don't crash if wx is gone
