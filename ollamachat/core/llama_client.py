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
from typing import Any, Callable

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
    ) -> None:
        """Start a streaming chat in a background daemon thread.

        POST /v1/chat/completions with SSE parsing. The request body
        contains sampling parameters at the root (not nested in options).

        Args:
            messages: List of message dicts with role and content.
            options: Sampling parameters dict (temperature, top_p, etc.).
            on_token: Called per token fragment via wx.CallAfter.
            on_done: Called once on successful completion via wx.CallAfter.
            on_error: Called once on error via wx.CallAfter.
        """
        self._stop_event.clear()
        self._stream_thread = threading.Thread(
            target=self._stream_worker,
            args=(messages, options, on_token, on_done, on_error),
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
    ) -> None:
        """Background thread worker for streaming chat.

        Imports wx locally to keep core/ wx-free at module level.
        Parses SSE lines from the llama-server response and dispatches
        callbacks via wx.CallAfter.
        """
        import wx  # Import wx only when needed (core/ is wx-free at top level)

        try:
            body: dict[str, Any] = {
                "model": "local",
                "messages": messages,
                "stream": True,
            }
            # Flatten sampling parameters into the root of the body
            # Rename num_predict -> max_tokens for OpenAI compatibility
            opts = dict(options)
            if "num_predict" in opts:
                opts["max_tokens"] = opts.pop("num_predict")
            body.update(opts)

            response = self._session.post(
                f"{self.base_url}/v1/chat/completions",
                json=body,
                stream=True,
                timeout=60,
            )

            # Buffer for handling partial SSE lines split across iter_lines chunks
            _buffer = ""

            for line in response.iter_lines():
                if self._stop_event.is_set():
                    break
                if not line:
                    continue

                decoded = line.decode("utf-8") if isinstance(line, bytes) else line

                if decoded.startswith("data: "):
                    payload = decoded[len("data: "):]
                    if payload == "[DONE]":
                        break

                    # Try to parse as standalone JSON; if it fails,
                    # accumulate in buffer for partial chunk handling
                    try:
                        chunk = json.loads(payload)
                        _buffer = ""
                    except json.JSONDecodeError:
                        _buffer += payload
                        # Try the combined buffer
                        try:
                            chunk = json.loads(_buffer)
                            _buffer = ""
                        except json.JSONDecodeError:
                            continue

                    content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    if content:
                        wx.CallAfter(on_token, content)
                elif _buffer:
                    # Non-data line while buffer is active — treat as continuation
                    try:
                        chunk = json.loads(_buffer + decoded)
                        _buffer = ""
                        content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if content:
                            wx.CallAfter(on_token, content)
                    except json.JSONDecodeError:
                        _buffer += decoded
                # else: non-data line (empty, event:, id:) — skip

            wx.CallAfter(on_done)

        except Exception as e:
            error_text = f"{type(e).__name__}: {e}"
            try:
                wx.CallAfter(on_error, error_text)
            except Exception:
                pass  # Last resort: don't crash if wx is gone
