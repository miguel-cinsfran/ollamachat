"""Conversation persistence for OllamaChat.

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
    ) -> None:
        """Append a message to the conversation.

        Args:
            role: Message role ("user", "assistant", "system").
            content: Message text content.
            images: Optional list of base64-encoded image strings.
        """
        msg: dict[str, Any] = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if images:
            msg["images"] = images
        self.messages.append(msg)

    def get_messages_for_api(self) -> list[dict[str, Any]]:
        """Return messages in the format required by the Ollama API.

        Strips the timestamp key and preserves images if present.

        Returns:
            List of message dicts with role, content, and optional images.
        """
        result: list[dict[str, Any]] = []
        for msg in self.messages:
            api_msg: dict[str, Any] = {
                "role": msg["role"],
                "content": msg["content"],
            }
            if "images" in msg:
                api_msg["images"] = msg["images"]
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
