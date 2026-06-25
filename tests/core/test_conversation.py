"""Tests for Conversation module — strict TDD, RED first, then GREEN."""

import json
import os
from pathlib import Path

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
    assert Path(exc_info.value.filename) == missing


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


# ─── reasoning field (v0.7.3) ──────────────────────────────────────────────────


def test_add_assistant_message_with_reasoning():
    """Given an assistant message with reasoning, the field is persisted."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("assistant", "La respuesta es 42.", reasoning="let me think step by step...")
    assert conv.messages[0]["reasoning"] == "let me think step by step..."
    assert conv.messages[0]["content"] == "La respuesta es 42."


def test_add_message_defaults_empty_reasoning():
    """Given an assistant message without reasoning, get returns ''."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("assistant", "R")
    assert conv.messages[0].get("reasoning", "") == ""


def test_get_messages_for_api_excludes_reasoning():
    """Given a message with non-empty reasoning, API payload has no reasoning key."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("assistant", "X", reasoning="secret thoughts")
    api_msgs = conv.get_messages_for_api()
    assert "reasoning" not in api_msgs[0]
    # The stored messages list is UNCHANGED
    assert "reasoning" in conv.messages[0]


def test_reasoning_round_trip_through_to_dict_from_dict():
    """save+load preserves reasoning verbatim."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("user", "Hola")
    conv.add_message("assistant", "Respuesta", reasoning="paso 1...\npaso 2...")

    d = conv.to_dict()
    conv2 = Conversation.from_dict(d)
    assert conv2.messages[1]["reasoning"] == "paso 1...\npaso 2..."
    assert conv2.messages[0]["content"] == "Hola"


def test_missing_reasoning_key_backward_compat(tmp_path):
    """Given a v0.7.1 file without reasoning, load works and get returns ''."""
    from bellbird.core.conversation import Conversation

    filepath = tmp_path / "old.json"
    data = {
        "messages": [
            {"role": "assistant", "content": "R", "timestamp": "2024-01-01T00:00:00"},
        ]
    }
    import json
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f)

    conv, _ = Conversation.load(filepath)
    assert conv.messages[0].get("reasoning", "") == ""


def test_to_dict_omits_empty_reasoning():
    """Given reasoning == '', to_dict does NOT contain a 'reasoning' key."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("assistant", "R")
    d = conv.to_dict()
    assert "reasoning" not in d["messages"][0]


def test_reasoning_does_not_appear_in_api_payload():
    """Integration: send_message_for_api does not contain reasoning key."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("system", "Eres útil.")
    conv.add_message("user", "Hola")
    conv.add_message("assistant", "¿En qué te ayudo?", reasoning="pensando...")

    result = conv.get_messages_for_api()
    for msg in result:
        assert "reasoning" not in msg, f"Unexpected reasoning key in {msg}"
    assert result[2]["content"] == "¿En qué te ayudo?"


# ─── tool_calls round-trip (v0.7.5) ──────────────────────────────────────────


def test_add_assistant_message_with_tool_calls():
    """Given an assistant message with tool_calls, the key is stored."""
    from bellbird.core.conversation import Conversation

    tc = [{"id": "call_1", "type": "function",
           "function": {"name": "shell", "arguments": '{"cmd": "ls"}'}}]
    conv = Conversation()
    conv.add_message("assistant", "Running...", tool_calls=tc)
    assert "tool_calls" in conv.messages[0]
    assert conv.messages[0]["tool_calls"] == tc


def test_get_messages_propagates_tool_calls():
    """get_messages_for_api includes tool_calls for assistant messages."""
    from bellbird.core.conversation import Conversation

    tc = [{"id": "call_1", "type": "function",
           "function": {"name": "shell", "arguments": '{}'}}]
    conv = Conversation()
    conv.add_message("assistant", "", tool_calls=tc)
    api = conv.get_messages_for_api()
    assert "tool_calls" in api[0]
    assert api[0]["tool_calls"] == tc


def test_get_messages_omits_tool_calls_when_absent():
    """get_messages_for_api does NOT include tool_calls when absent."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("assistant", "Simple response")
    api = conv.get_messages_for_api()
    assert "tool_calls" not in api[0]


def test_tool_calls_ignored_on_non_assistant():
    """tool_calls kwarg silently ignored for non-assistant roles."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("user", "do it", tool_calls=[{"id": "x"}])
    assert "tool_calls" not in conv.messages[0]


def test_tool_calls_round_trip_through_save_load(tmp_path):
    """Save + load preserves tool_calls key verbatim."""
    from bellbird.core.conversation import Conversation

    tc = [{"id": "call_xyz", "type": "function",
           "function": {"name": "shell", "arguments": '{"cmd": "ls"}'}}]
    conv = Conversation()
    conv.add_message("assistant", "", tool_calls=tc)
    filepath = tmp_path / "chat.json"
    Conversation.save(conv, filepath)
    loaded, _ = Conversation.load(filepath)
    assert "tool_calls" in loaded.messages[0]
    assert loaded.messages[0]["tool_calls"] == tc


def test_legacy_message_no_tool_calls_still_works():
    """A legacy message without tool_calls loads and serializes fine."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("user", "hi")
    conv.add_message("assistant", "hello")
    api = conv.get_messages_for_api()
    assert {"role": "user", "content": "hi"} == api[0]
    assert {"role": "assistant", "content": "hello"} == api[1]
    assert len(api) == 2


# ─── truncate_to (v0.8.0) ───────────────────────────────────────────────────


def test_truncate_to_preserves_system_rows():
    """GIVEN messages [system, user, assistant(tool_calls), tool, user]
    WHEN truncate_to(3)
    THEN result == [system, user, assistant(tool_calls), tool]
    AND system row is unchanged
    AND get_messages_for_api carries tool_calls on the assistant row."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("system", "Eres útil.")
    conv.add_message("user", "Hola")
    conv.add_message("assistant", "", tool_calls=[{"id": "c1", "type": "function"}])
    conv.add_message("tool", "output", tool_call_id="c1")
    conv.add_message("user", "otra cosa")

    conv.truncate_to(3)
    assert len(conv.messages) == 4
    assert conv.messages[0]["role"] == "system"
    assert conv.messages[0]["content"] == "Eres útil."
    assert conv.messages[2]["role"] == "assistant"
    assert "tool_calls" in conv.messages[2]

    api = conv.get_messages_for_api()
    assert len(api) == 4
    assert api[2].get("tool_calls") is not None


def test_truncate_to_drops_tool_calls_assistant_row_correctly():
    """GIVEN [system, user, assistant(tool_calls=[c1]), tool]
    WHEN truncate_to(2)
    THEN assistant with tool_calls preserved, tool row dropped."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("system", "Eres útil.")
    conv.add_message("user", "Hola")
    conv.add_message("assistant", "", tool_calls=[{"id": "c1", "type": "function"}])
    conv.add_message("tool", "output", tool_call_id="c1")

    conv.truncate_to(2)
    assert len(conv.messages) == 3
    assert conv.messages[2]["role"] == "assistant"
    assert "tool_calls" in conv.messages[2]

    api = conv.get_messages_for_api()
    assert len(api) == 3
    assert api[2].get("tool_calls") is not None


def test_truncate_to_without_system():
    """GIVEN [user, assistant]
    WHEN truncate_to(0)
    THEN result == [user] (keeps index 0)."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("user", "Q1")
    conv.add_message("assistant", "A1")
    conv.truncate_to(0)
    assert len(conv.messages) == 1
    assert conv.messages[0]["role"] == "user"
    assert conv.messages[0]["content"] == "Q1"


def test_truncate_to_index_zero():
    """GIVEN [user, assistant]
    WHEN truncate_to(0)
    THEN only index 0 is kept (message at index 0 is inclusive)."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("user", "Q1")
    conv.add_message("assistant", "A1")
    conv.truncate_to(0)
    assert len(conv.messages) == 1
    assert conv.messages[0]["role"] == "user"


# ─── pop_last (v0.8.0) ────────────────────────────────────────────────────


def test_pop_last_drops_trailing_assistant_and_tool():
    """GIVEN [user, assistant(tool_calls=[c1]), tool]
    WHEN pop_last()
    THEN trailing tool removed first, then assistant,
    AND result == [user]."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("user", "Q1")
    tc = [{"id": "c1", "type": "function", "function": {"name": "test", "arguments": "{}"}}]
    conv.add_message("assistant", "", tool_calls=tc)
    conv.add_message("tool", "output", tool_call_id="c1")

    conv.pop_last()
    assert len(conv.messages) == 1
    assert conv.messages[0]["role"] == "user"

    api = conv.get_messages_for_api()
    assert len(api) == 1


def test_pop_last_removes_trailing_user():
    """GIVEN [user, assistant(tool_calls), tool, user]
    WHEN pop_last(role='user')
    THEN trailing user removed, assistant+tool preserved."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("user", "Q1")
    tc = [{"id": "c1", "type": "function", "function": {"name": "test", "arguments": "{}"}}]
    conv.add_message("assistant", "", tool_calls=tc)
    conv.add_message("tool", "output", tool_call_id="c1")
    conv.add_message("user", "Q2")

    conv.pop_last(role="user")
    assert len(conv.messages) == 3
    assert conv.messages[-1]["role"] == "tool"
    api = conv.get_messages_for_api()
    assert len(api) == 3
    assert api[-1]["role"] == "tool"
    assert api[-1]["tool_call_id"] == "c1"


def test_pop_last_without_matching_role_noop():
    """GIVEN [user, assistant]
    WHEN pop_last(role='tool')
    THEN no message removed (no trailing tool row)."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("user", "Q1")
    conv.add_message("assistant", "A1")

    conv.pop_last(role="tool")
    assert len(conv.messages) == 2


def test_pop_last_empty_noop():
    """GIVEN empty messages
    WHEN pop_last()
    THEN no error, messages remains empty."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.pop_last()
    assert conv.messages == []


def test_pop_last_assistant_without_tool():
    """GIVEN [user, assistant]
    WHEN pop_last()
    THEN assistant removed, user remains."""
    from bellbird.core.conversation import Conversation

    conv = Conversation()
    conv.add_message("user", "Q1")
    conv.add_message("assistant", "A1")
    conv.pop_last()
    assert len(conv.messages) == 1
    assert conv.messages[0]["role"] == "user"


def test_tool_calls_in_order_with_tool():
    """Assistant msg with tool_calls precedes following tool message in API."""
    from bellbird.core.conversation import Conversation

    tc = [{"id": "c1", "type": "function",
           "function": {"name": "sh", "arguments": '{"x":"y"}'}}]
    conv = Conversation()
    conv.add_message("assistant", "", tool_calls=tc)
    conv.add_message("tool", "output", tool_call_id="c1")
    api = conv.get_messages_for_api()
    assert len(api) == 2
    assert api[0]["role"] == "assistant"
    assert "tool_calls" in api[0]
    assert api[1]["role"] == "tool"
    assert api[1]["tool_call_id"] == "c1"



