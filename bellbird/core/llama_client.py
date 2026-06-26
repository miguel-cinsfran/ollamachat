"""LlamaClient — HTTP client for llama.cpp's OpenAI-compatible server.

Provides headless (wx-free) access to a local llama-server:
- Health check via GET /health
- Loaded model query via GET /v1/models
- Streaming chat via POST /v1/chat/completions with SSE parsing in a daemon thread
- Clean abort via threading.Event

All streaming callbacks are marshalled to the wx main thread via wx.CallAfter.
"""

import json
import re
import threading
from collections.abc import Callable
from typing import Any

import requests

from bellbird.core.logger import get_logger


class _ThinkTagParser:
    """Parses inline <think>/<thinking>/<thought> tags from a token stream.

    Conservative matching: an opening tag is only recognised when followed
    by whitespace, end-of-line, or end-of-stream — this avoids false
    positives on literal ``<think>`` in user code or markdown examples.

    Tags are case-insensitive. Tags split across arbitrary ``feed()``
    calls are handled via an internal buffer.
    """

    # Opening tag: case-insensitive <think>/<thinking>/<thought>
    # followed by whitespace or end-of-string (conservative guard).
    _OPEN_RE = re.compile(
        r"<(?:think|thinking|thought)>(?=\s|$)", re.IGNORECASE
    )
    # Closing tag: case-insensitive </think>/</thinking>/</thought>.
    # No conservative guard on closing tags.
    _CLOSE_RE = re.compile(
        r"</(?:think|thinking|thought)>", re.IGNORECASE
    )

    def __init__(self) -> None:
        self._buf: str = ""
        self._in_reasoning: bool = False

    def feed(self, chunk: str) -> list[tuple[str, str]]:
        """Process a chunk and return emitted (type, text) pairs.

        Args:
            chunk: A token fragment from the stream.

        Returns:
            List of ``("content", text)`` or ``("reasoning", text)`` tuples.
        """
        self._buf += chunk
        return self._parse_buffer()

    def flush(self) -> list[tuple[str, str]]:
        """Flush remaining buffer content.

        Returns:
            Any pending (type, text) tuples for text that never
            completed a tag boundary.
        """
        out = self._parse_buffer(final=True)
        if self._buf:
            tag = "reasoning" if self._in_reasoning else "content"
            out.append((tag, self._buf))
            self._buf = ""
        return out

    def _parse_buffer(self, final: bool = False) -> list[tuple[str, str]]:
        """Scan the internal buffer for complete tags.

        Args:
            final: When True, emit everything (used by ``flush()``).

        Returns:
            Emitted (type, text) tuples from this scan pass.
        """
        results: list[tuple[str, str]] = []
        while True:
            if self._in_reasoning:
                m = self._CLOSE_RE.search(self._buf)
                if m:
                    before = self._buf[: m.start()]
                    if before:
                        results.append(("reasoning", before))
                    self._buf = self._buf[m.end() :]
                    self._in_reasoning = False
                    # Strip a single trailing \n or space after closing tag
                    # (per spec: conservative whitespace stripping on content
                    # transition).
                    if self._buf and self._buf[0] in ("\n", " "):
                        self._buf = self._buf[1:]
                    continue  # look for more tags in the remainder
                # No closing tag found. If we're at final flush, emit
                # everything; otherwise keep the buffer for future chunks.
                if final:
                    results.append(("reasoning", self._buf))
                    self._buf = ""
                break
            else:
                m = self._OPEN_RE.search(self._buf)
                if m:
                    before = self._buf[: m.start()]
                    if before:
                        results.append(("content", before))
                    self._buf = self._buf[m.end() :]
                    self._in_reasoning = True
                    continue
                if final:
                    results.append(("content", self._buf))
                    self._buf = ""
                break
        return results


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
        request_timeout: int = 120,
    ) -> None:
        self.base_url = base_url
        self.request_timeout = request_timeout
        self._session = session or requests.Session()
        self._stop_event = threading.Event()
        self._stream_thread: threading.Thread | None = None
        self._tool_support_cache: bool | None = None

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

    def check_state(self) -> str:
        """Ternary server health state.

        Returns:
            ``"loading"`` — 503 with ``error.message`` containing ``"Loading model"``.
            ``"dead"``    — connection refused, timeout, 5xx without a loading message,
                          or any non-200/503 response.
            ``"ready"``   — 200 OK with ``{"status": "ok"}``.

        Never raises. Timeout: 5s per call.
        """
        try:
            response = self._session.get(
                f"{self.base_url}/health", timeout=5
            )
            if response.status_code == 200:
                body = response.json()
                return "ready" if body.get("status") == "ok" else "dead"
            if response.status_code == 503:
                try:
                    body = response.json()
                    err = body.get("error", {})
                    msg = (err.get("message") or "") if isinstance(err, dict) else ""
                    if "loading model" in msg.lower():
                        return "loading"
                except Exception:
                    pass
                return "dead"
            return "dead"
        except Exception:
            return "dead"

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

    def check_tool_support(self) -> bool:
        """Probe whether the model's template supports tool calling.

        Calls ``GET /props`` once per instance and caches the result.
        Returns ``True`` iff the response JSON has a truthy
        ``chat_template_tool_use`` field. On any exception (network,
        JSON decode, timeout, non-200 status) returns ``False`` without
        raising.

        Returns:
            Cached boolean — ``True`` if tool use is supported,
            ``False`` otherwise.
        """
        if self._tool_support_cache is not None:
            return self._tool_support_cache
        try:
            response = self._session.get(
                f"{self.base_url}/props", timeout=5
            )
            if response.status_code != 200:
                self._tool_support_cache = False
                return False
            body = response.json()
            self._tool_support_cache = bool(body.get("chat_template_tool_use", False))
        except Exception:
            self._tool_support_cache = False
        return self._tool_support_cache

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
        on_reasoning: Callable[[str], None] | None = None,
        on_timings: Callable[[dict], None] | None = None,
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
            on_reasoning: Optional callback for reasoning/chain-of-thought
                text via wx.CallAfter. Receives reasoning text fragments
                from ``delta.reasoning_content`` and parsed inline
                ``<think>``/``<thinking>``/``<thought>`` blocks. When
                ``None``, reasoning text is silently dropped.
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
            args=(messages, options, on_token, on_done, on_error, on_usage, on_tool_call, tools, on_reasoning, on_timings),
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
        on_reasoning: Callable[[str], None] | None = None,
        on_timings: Callable[[dict], None] | None = None,
    ) -> None:
        """Background thread worker for streaming chat.

        Imports wx locally to keep core/ wx-free at module level.
        Parses SSE lines from the llama-server response and dispatches
        callbacks via wx.CallAfter.
        """
        import wx  # Import wx only when needed (core/ is wx-free at top level)

        log = get_logger()

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
                "stream_options": {"include_usage": True},
            }
            body.update(options)

            if tools is not None:
                body["tools"] = tools
                body["tool_choice"] = "auto"

            log.info(
                "stream_worker: POST /v1/chat/completions "
                "messages=%d tools=%s options=%s",
                len(messages),
                "yes" if tools else "no",
                {k: v for k, v in options.items()},
            )

            # D9: use a context manager so the connection is released
            # back to the pool on exit even if an exception escapes
            # the parser. D10: check status_code so a 4xx/5xx response
            # is reported as an error instead of being silently parsed
            # as (empty) SSE.
            with self._session.post(
                f"{self.base_url}/v1/chat/completions",
                json=body,
                stream=True,
                timeout=self.request_timeout,
            ) as response:
                log.info("stream_worker: HTTP %d %s", response.status_code, response.reason or "")
                if response.status_code != 200:
                    error_text = (
                        f"Server returned HTTP {response.status_code}: "
                        f"{response.reason or 'no reason'}"
                    )
                    log.error("stream_worker: server error — %s", error_text)
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
                _think_parser = _ThinkTagParser()
                total_content_len = 0
                total_reasoning_len = 0
                chunk_count = 0
                first_token_logged = False
                in_reasoning_phase = False
                for line in response.iter_lines():
                    if self._stop_event.is_set():
                        log.info("stream_worker: aborted by stop_event after %d chunks", chunk_count)
                        break
                    if not line:
                        continue

                    decoded = line.decode("utf-8") if isinstance(line, bytes) else line
                    if not decoded.startswith("data: "):
                        log.debug("stream_worker: non-data SSE line: %r", decoded[:80])
                        continue  # blank, ":comment", "event:...", "id:..." → skip

                    payload = decoded[len("data: "):]
                    if payload == "[DONE]":
                        log.info("stream_worker: [DONE] received")
                        break

                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        log.warning("stream_worker: JSON parse error on line: %r", decoded[:120])
                        continue  # malformed data line, skip

                    chunk_count += 1

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

                    # Timings callback: fire on the final chunk's timings
                    # field. When on_timings is None, skip the field entirely
                    # (no overhead, no error).
                    if on_timings is not None:
                        timings = chunk.get("timings")
                        if timings is not None and timings:  # non-empty dict
                            wx.CallAfter(on_timings, timings)

                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    reasoning_content = delta.get("reasoning_content") or ""
                    content = delta.get("content") or ""

                    # Route delta.reasoning_content to on_reasoning ONLY
                    # (NOT through the parser — it is the SSE-native channel).
                    if reasoning_content:
                        total_reasoning_len += len(reasoning_content)
                        if not in_reasoning_phase:
                            in_reasoning_phase = True
                            log.info("stream_worker: reasoning phase started (delta)")
                        if on_reasoning is not None:
                            wx.CallAfter(on_reasoning, reasoning_content)

                    # Feed delta.content through the inline tag parser
                    # so <think>/<thinking>/<thought> blocks are split
                    # into reasoning and content channels.
                    # Optimization: if the content has no '<' AND the
                    # parser buffer is empty, dispatch directly without
                    # the parser to preserve per-chunk granularity for
                    # normal (non-tag) content.
                    if content:
                        total_content_len += len(content)
                        if not first_token_logged:
                            if in_reasoning_phase:
                                log.info("stream_worker: reasoning phase ended, response started")
                            else:
                                log.info("stream_worker: first token received")
                            first_token_logged = True
                            in_reasoning_phase = False
                        if "<" in content or _think_parser._buf:
                            for tag, text in _think_parser.feed(content):
                                if not text:
                                    continue
                                if tag == "reasoning":
                                    total_reasoning_len += len(text)
                                    if on_reasoning is not None:
                                        wx.CallAfter(on_reasoning, text)
                                else:
                                    wx.CallAfter(on_token, text)
                        else:
                            wx.CallAfter(on_token, content)

                    if finish_reason:
                        log.info(
                            "stream_worker: finish_reason=%r chunk=%d content_so_far=%d tool_calls_pending=%d",
                            finish_reason, chunk_count, total_content_len, len(_tc_buffer),
                        )

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

            # Flush any remaining content from the inline tag parser
            # (e.g. text after the last <think> block that never closed).
            for tag, text in _think_parser.flush():
                if not text:
                    continue
                if tag == "reasoning":
                    total_reasoning_len += len(text)
                    if on_reasoning is not None:
                        wx.CallAfter(on_reasoning, text)
                else:
                    wx.CallAfter(on_token, text)

            log.info(
                "stream_worker: done — chunks=%d content=%d chars reasoning=%d chars",
                chunk_count, total_content_len, total_reasoning_len,
            )
            wx.CallAfter(on_done)

        except Exception as e:
            log.exception("stream_worker: unhandled exception: %s", e)
            error_text = f"{type(e).__name__}: {e}"
            try:
                wx.CallAfter(on_error, error_text)
            except Exception:
                pass  # Last resort: don't crash if wx is gone
