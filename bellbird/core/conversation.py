"""Conversation persistence for Bellbird.

Defines the Conversation class that holds the in-memory transcript of a
chat session and serializes it to/from UTF-8 JSON files.

Usage:
    conv = Conversation()
    conv.add_message("user", "Hello")
    Conversation.save(conv, Path("chat.json"))
    loaded = Conversation.load(Path("chat.json"))
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class Conversation:
    """In-memory conversation transcript with JSON persistence.

    Maintains a list of message dicts, each with role, content, timestamp,
    and optionally images.

    Attributes:
        messages: List of message dicts.
    """

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def add_message(
        self,
        role: str,
        content: str,
        images: list[str] | None = None,
        tool_call_id: str | None = None,
        reasoning: str = "",
        tool_calls: list[dict] | None = None,
    ) -> None:
        """Append a message to the conversation.

        Args:
            role: Message role ("user", "assistant", "system", "tool").
            content: Message text content.
            images: Optional list of base64-encoded image strings (user role only).
            tool_call_id: Required for role="tool" — the ID returned by the
                model in its assistant tool_calls[].id field. The OpenAI-
                compatible API requires tool messages to carry the matching
                tool_call_id so the model can correlate the result with the
                call. Ignored for non-tool roles.
            reasoning: Optional reasoning/chain-of-thought text. Persisted
                locally but stripped from API payloads. Defaults to ``""``
                for backward compatibility with existing code that does not
                pass this parameter.
            tool_calls: Optional list of tool call dicts for role="assistant".
                Each dict has ``id``, ``type``, and ``function`` keys.
                Ignored for non-assistant roles.
        """
        msg: dict[str, Any] = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if images:
            msg["images"] = images
        if tool_call_id is not None and role == "tool":
            msg["tool_call_id"] = tool_call_id
        if reasoning:
            msg["reasoning"] = reasoning
        if tool_calls is not None and role == "assistant":
            msg["tool_calls"] = tool_calls
        self.messages.append(msg)

    def get_messages_for_api(self) -> list[dict[str, Any]]:
        """Return messages in the format required by the Ollama API.

        Strips the timestamp key and preserves images, tool_call_id,
        and tool_calls if present. For role="tool" messages, the
        tool_call_id MUST be present so the model can correlate the
        result with the assistant's tool_calls[].id (OpenAI-compatible
        API requirement).

        The ``reasoning`` key is LOCAL-ONLY — it MUST NOT appear in the
        API payload. This is a pinned invariant.

        Returns:
            List of message dicts with role, content, and optional
            images, tool_call_id, and tool_calls.
        """
        result: list[dict[str, Any]] = []
        for msg in self.messages:
            api_msg: dict[str, Any] = {
                "role": msg["role"],
                "content": msg["content"],
            }
            if "images" in msg:
                api_msg["images"] = msg["images"]
            if "tool_call_id" in msg:
                api_msg["tool_call_id"] = msg["tool_call_id"]
            if "tool_calls" in msg:
                api_msg["tool_calls"] = msg["tool_calls"]
            # timestamp is stripped (API rejects unknown fields)
            # reasoning is local-only (MUST NOT appear in API payload)
            result.append(api_msg)
        return result

    def clear(self) -> None:
        """Remove all messages from the conversation."""
        self.messages.clear()

    def to_dict(self) -> dict[str, Any]:
        """Serialize the conversation to a plain dict.

        Returns:
            Dict with a "messages" key containing all messages.
        """
        return {"messages": self.messages}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Conversation":
        """Create a Conversation from a dict.

        Args:
            data: Dict with a "messages" key.

        Returns:
            New Conversation populated with the given messages.
        """
        conv = cls()
        conv.messages = data.get("messages", [])
        return conv

    def truncate_to(self, index: int) -> None:
        """Keep messages up to and including ``index``, drop everything after.

        The message at ``index`` is kept; only messages strictly AFTER it
        are removed. System-role rows at the head (before ``index``) are
        preserved — they are never removed by this operation.

        Args:
            index: Zero-based index; all messages ``[index+1:]`` are removed.
                A value of ``-1`` or less clears all messages.
        """
        self.messages = self.messages[: index + 1]

    def pop_last(self, role: str | None = None) -> None:
        """Drop the trailing row, optionally filtered by ``role``.

        If the trailing pair is ``assistant(tool_calls=...)`` followed by
        ``tool``, BOTH are removed together (the pair drops atomically so
        the API payload never contains an orphaned ``tool`` row).

        Args:
            role: If set, only the trailing row with this role is removed.
                If the trailing row does not match ``role``, nothing is removed.
        """
        if not self.messages:
            return
        if role is not None and self.messages[-1].get("role") != role:
            return

        # Check for the assistant(tool_calls) + tool pair at the end
        if (
            len(self.messages) >= 2
            and self.messages[-2].get("role") == "assistant"
            and "tool_calls" in self.messages[-2]
            and self.messages[-1].get("role") == "tool"
        ):
            # Pop the tool row first, then the assistant row (pair)
            self.messages.pop()
            self.messages.pop()
            return

        # Standard pop: remove the trailing message
        self.messages.pop()

    @classmethod
    def save(
        cls, conv: "Conversation", filepath: Path, system_prompt: str = ""
    ) -> None:
        """Save a conversation to disk with atomic write.

        Writes to a .tmp file first, then replaces the target atomically.
        The system_prompt is stored at the top level alongside messages.

        Args:
            conv: The conversation to save.
            filepath: Path to the output JSON file.
            system_prompt: Optional system prompt text to persist.
        """
        data = conv.to_dict()
        full = {"system_prompt": system_prompt, **data}
        filepath = Path(filepath)  # wx.FileDialog.GetPath() returns str, not Path
        tmp_path = filepath.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(full, f, indent=2, ensure_ascii=False)
        tmp_path.replace(filepath)

    @classmethod
    def load(cls, filepath: Path) -> tuple["Conversation", str]:
        """Load a conversation from disk.

        Args:
            filepath: Path to an existing JSON file.

        Returns:
            Tuple of (Conversation, system_prompt_string).

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        sp: str = data.get("system_prompt", "")
        body = {"messages": data.get("messages", [])}
        return cls.from_dict(body), sp
