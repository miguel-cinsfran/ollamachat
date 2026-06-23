"""Tests for Conversation module — strict TDD, RED first, then GREEN."""

import json
import os

import pytest


# ─── add_message ──────────────────────────────────────────────────────────────


def test_add_user_message():
    """Given a fresh Conversation, add a user message."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("user", "Hola")
    assert len(conv.messages) == 1
    assert conv.messages[0]["role"] == "user"
    assert conv.messages[0]["content"] == "Hola"
    import re

    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", conv.messages[0]["timestamp"])


def test_add_user_message_with_image():
    """Given a user message with an image, images key is preserved."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("user", "¿Qué ves?", images=["iVBORw0KGgoAAAANSUhEUg..."])
    assert conv.messages[0]["images"] == ["iVBORw0KGgoAAAANSUhEUg..."]


def test_assistant_message_without_images():
    """Given an assistant message, no images key is present."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("assistant", "Hola, ¿en qué te ayudo?")
    assert "images" not in conv.messages[0]


# ─── get_messages_for_api ────────────────────────────────────────────────────


def test_get_messages_strips_timestamp():
    """Given mixed messages, get_messages_for_api strips timestamps."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("system", "Eres útil.")
    conv.add_message("user", "Hola")
    conv.add_message("assistant", "¿En qué te ayudo?")

    result = conv.get_messages_for_api()
    assert len(result) == 3
    for msg in result:
        assert "timestamp" not in msg
    assert result[0] == {"role": "system", "content": "Eres útil."}
    assert result[1] == {"role": "user", "content": "Hola"}
    assert result[2] == {"role": "assistant", "content": "¿En qué te ayudo?"}


def test_api_payload_preserves_images():
    """Given a message with images, API payload preserves them without timestamp."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("user", "ver imagen", images=["AAAA"])
    result = conv.get_messages_for_api()
    assert result[0]["images"] == ["AAAA"]
    assert "timestamp" not in result[0]


# ─── to_dict / from_dict ─────────────────────────────────────────────────────


def test_round_trip_without_images():
    """Given a conversation without images, to_dict/from_dict round-trips."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("user", "Hola")
    conv.add_message("assistant", "¿En qué te ayudo?")

    d = conv.to_dict()
    conv2 = Conversation.from_dict(d)
    assert conv2.messages == conv.messages
    assert len(conv2.messages) == 2


def test_round_trip_with_images():
    """Given a conversation with images, to_dict/from_dict round-trips."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("user", "ver imagen", images=["iVBORw0..."])

    d = conv.to_dict()
    conv2 = Conversation.from_dict(d)
    assert conv2.messages[0]["images"] == ["iVBORw0..."]


# ─── save / load ──────────────────────────────────────────────────────────────


def test_save_to_disk(tmp_path):
    """Given a conversation, save writes valid JSON with UTF-8."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("user", "Hola")
    conv.add_message("assistant", "¿En qué te ayudo?")
    conv.add_message("user", "ver imagen", images=["iVBORw0..."])

    filepath = tmp_path / "chat.json"
    Conversation.save(conv, filepath)
    assert filepath.exists()

    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)
    # The JSON now has a top-level system_prompt field
    assert data["system_prompt"] == ""
    assert data["messages"] == conv.to_dict()["messages"]

    # Verify non-ASCII is not escaped
    content = filepath.read_text(encoding="utf-8")
    assert "¿" in content  # literal non-ASCII preserved


def test_load_from_disk(tmp_path):
    """Given a saved file, load returns an equivalent conversation."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("user", "Hola")
    conv.add_message("assistant", "¿En qué te ayudo?")

    filepath = tmp_path / "chat.json"
    Conversation.save(conv, filepath)

    conv2, _ = Conversation.load(filepath)
    assert len(conv2.messages) == 2
    assert conv2.messages[0]["content"] == "Hola"
    assert conv2.messages[0]["role"] == "user"
    assert conv2.messages[1]["content"] == "¿En qué te ayudo?"


def test_load_missing_file_raises(tmp_path):
    """Given no file, load raises FileNotFoundError."""
    from bellbird.core.conversation import Conversation

    missing = tmp_path / "missing.json"
    with pytest.raises(FileNotFoundError) as exc_info:
        Conversation.load(missing)
    assert str(missing) in str(exc_info.value)


def test_atomic_write_uses_tmp(tmp_path):
    """Given save, the write goes to .tmp first then replaces target."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("user", "test")

    filepath = tmp_path / "chat.json"
    Conversation.save(conv, filepath)

    # The .tmp file should be gone after save
    assert not filepath.with_suffix(".tmp").exists()
    assert filepath.exists()
    # Verify content
    loaded, _ = Conversation.load(filepath)
    assert len(loaded.messages) == 1


# ─── clear ────────────────────────────────────────────────────────────────────


def test_clear_empties_messages():
    """Given a conversation with messages, clear empties them."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("user", "Hola")
    conv.add_message("assistant", "¿En qué te ayudo?")

    conv.clear()
    assert conv.messages == []
    assert conv.get_messages_for_api() == []


def test_clear_allows_reuse():
    """Given a cleared conversation, adding new messages works."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("user", "Hola")
    conv.clear()

    conv.add_message("user", "de nuevo")
    assert len(conv.messages) == 1
    assert conv.messages[0]["content"] == "de nuevo"


# ─── images preserve order ────────────────────────────────────────────────────


def test_images_preserve_order():
    """Given multiple images, get_messages_for_api preserves order."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("user", "ver", images=["img1", "img2", "img3"])
    api_msgs = conv.get_messages_for_api()
    assert api_msgs[0]["images"] == ["img1", "img2", "img3"]


# ─── system_prompt (v0.3.0) ─────────────────────────────────────────────────


def test_save_includes_system_prompt(tmp_path):
    """Given save with system_prompt, the JSON file includes the field."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("user", "Hola")

    filepath = tmp_path / "chat.json"
    Conversation.save(conv, filepath, system_prompt="Eres útil.")

    with open(filepath, encoding="utf-8") as f:
        parsed = json.load(f)
    assert parsed["system_prompt"] == "Eres útil."
    assert len(parsed["messages"]) == 1
    assert parsed["messages"][0]["content"] == "Hola"


def test_load_returns_system_prompt(tmp_path):
    """Given a file with system_prompt, load returns tuple with it."""
    from bellbird.core.conversation import Conversation

    filepath = tmp_path / "chat.json"
    data = {
        "system_prompt": "X",
        "messages": [{"role": "user", "content": "hi", "timestamp": "now"}],
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f)

    result = Conversation.load(filepath)
    assert isinstance(result, tuple)
    assert len(result) == 2
    conv, sp = result
    assert sp == "X"
    assert len(conv.messages) == 1
    assert conv.messages[0]["content"] == "hi"


def test_load_missing_system_prompt_returns_empty_string(tmp_path):
    """Given a v0.2.0 file (no system_prompt), load returns empty string."""
    from bellbird.core.conversation import Conversation

    filepath = tmp_path / "chat.json"
    data = {
        "messages": [{"role": "user", "content": "hi", "timestamp": "now"}],
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f)

    conv, sp = Conversation.load(filepath)
    assert sp == ""
    assert len(conv.messages) == 1


# ─── tool_call_id (v0.4.0, for tool-calling second-turn round-trip) ──────────


def test_add_tool_message_with_tool_call_id():
    """Given a tool message with tool_call_id, the field is persisted."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("tool", "ls output", tool_call_id="call_abc123")
    assert conv.messages[0]["tool_call_id"] == "call_abc123"


def test_add_non_tool_message_omits_tool_call_id():
    """Given a user/assistant message with tool_call_id arg, the field is NOT added.

    tool_call_id is meaningful only for role="tool". For other roles, the
    parameter is silently ignored to avoid pollution.
    """
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("user", "hola", tool_call_id="ignored")
    assert "tool_call_id" not in conv.messages[0]

    conv.add_message("assistant", "respuesta", tool_call_id="also_ignored")
    assert "tool_call_id" not in conv.messages[1]


def test_get_messages_includes_tool_call_id():
    """Given a tool message, get_messages_for_api includes tool_call_id.

    This is the critical contract for the tool-calling second turn:
    llama-server requires the tool message to carry the same
    tool_call_id as the assistant's tool_calls[].id.
    """
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("tool", "ls output", tool_call_id="call_abc123")
    api_msgs = conv.get_messages_for_api()
    assert api_msgs[0]["tool_call_id"] == "call_abc123"
    assert "timestamp" not in api_msgs[0]


def test_get_messages_omits_tool_call_id_when_not_set():
    """Given a tool message without tool_call_id, get_messages_for_api omits the key."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("tool", "ls output")
    api_msgs = conv.get_messages_for_api()
    assert "tool_call_id" not in api_msgs[0]


def test_tool_call_id_round_trip_through_save_load(tmp_path):
    """Given a tool message with tool_call_id, save+load preserves the field."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("user", "ls please")
    conv.add_message(
        "tool", "file1\nfile2", tool_call_id="call_xyz789"
    )

    filepath = tmp_path / "chat.json"
    Conversation.save(conv, filepath)

    loaded, _ = Conversation.load(filepath)
    assert loaded.messages[1]["tool_call_id"] == "call_xyz789"
