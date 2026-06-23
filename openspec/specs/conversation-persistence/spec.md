# Conversation Persistence Capability Specification

## Purpose

Defines the `Conversation` data class that holds the in-memory transcript of a
chat session and serializes it to/from UTF-8 JSON files in `data/`. Persistence
is the user's only way to come back to a previous conversation, so the
on-disk format MUST be stable across runs and MUST round-trip identically
(including base64 image payloads). The module is headless (no wx) and fully
testable.

## Requirements

### Requirement: Message Shape and Storage

`Conversation` SHALL maintain an internal `list[dict]` of messages where each
message has at least the keys `role` (str), `content` (str), and `timestamp`
(ISO 8601 UTC string). Messages MAY additionally carry an `images` key whose
value is a `list[str]` of base64-encoded image payloads.

#### Scenario: Add a user message

- GIVEN a fresh `Conversation`
- WHEN `conv.add_message("user", "Hola")` is called
- THEN `len(conv.messages) == 1`
- AND `conv.messages[0]["role"] == "user"`
- AND `conv.messages[0]["content"] == "Hola"`
- AND `conv.messages[0]["timestamp"]` matches the regex
  `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}`

#### Scenario: Add a user message with an image

- GIVEN a fresh `Conversation`
- WHEN `conv.add_message("user", "¿Qué ves?",
  images=["iVBORw0KGgoAAAANSUhEUg..."])` is called
- THEN `conv.messages[0]["images"] == ["iVBORw0KGgoAAAANSUhEUg..."]`

#### Scenario: Assistant message without images

- GIVEN a fresh `Conversation`
- WHEN `conv.add_message("assistant", "Hola, ¿en qué te ayudo?")` is called
- THEN `"images" not in conv.messages[0]`

### Requirement: API-shaped Message Extraction

`Conversation.get_messages_for_api()` SHALL return a `list[dict]` containing
only the keys Ollama needs: `role`, `content`, and (if present) `images`. The
`timestamp` key MUST be stripped because Ollama's API rejects unknown fields.

#### Scenario: Mixed messages

- GIVEN a `Conversation` with messages:
  1. `{"role": "system", "content": "Eres útil.", "timestamp": "..."}`
  2. `{"role": "user", "content": "Hola", "timestamp": "..."}`
  3. `{"role": "assistant", "content": "¿En qué te ayudo?",
     "timestamp": "..."}`
- WHEN `conv.get_messages_for_api()` is called
- THEN the result is
  `[{"role": "system", "content": "Eres útil."},
    {"role": "user", "content": "Hola"},
    {"role": "assistant", "content": "¿En qué te ayudo?"}]`
- AND no `timestamp` key is present in any returned dict

#### Scenario: API payload preserves images

- GIVEN a message `{"role": "user", "content": "ver imagen",
  "images": ["AAAA"], "timestamp": "..."}`
- WHEN the conversation is queried via `get_messages_for_api()`
- THEN the returned message has key `images == ["AAAA"]`
- AND no `timestamp` key

### Requirement: In-memory Serialization — `to_dict` / `from_dict`

`Conversation.to_dict()` SHALL return a plain `dict` suitable for
`json.dumps`. `Conversation.from_dict(d)` SHALL be a `@classmethod` that
returns a new `Conversation` populated from `d`. Round-trip MUST be lossless
for all keys including `images`.

#### Scenario: Round-trip without images

- GIVEN a `Conversation` with two messages, no images
- WHEN `d = conv.to_dict()` then `conv2 = Conversation.from_dict(d)`
- THEN `conv2.messages == conv.messages`
- AND `len(conv2.messages) == 2`

#### Scenario: Round-trip with images

- GIVEN a `Conversation` with a user message carrying
  `images=["iVBORw0..."]`
- WHEN `d = conv.to_dict()` then `conv2 = Conversation.from_dict(d)`
- THEN `conv2.messages[0]["images"] == ["iVBORw0..."]`

### Requirement: Disk Persistence — `save` / `load`

`Conversation.save(conv, filepath, system_prompt: str = "")` SHALL be a `@classmethod` that writes `json.dumps({"system_prompt": system_prompt, **conv.to_dict()}, indent=2, ensure_ascii=False)` to `filepath` with `encoding="utf-8"`. `Conversation.load(filepath) -> tuple[Conversation, str]` SHALL be a `@classmethod` that reads the file, parses JSON, extracts the top-level `"system_prompt"` key (defaulting to `""` if absent — v0.2.0 backward compatibility), and returns `(Conversation.from_dict(body), system_prompt)`. Atomic write (`.tmp` + `Path.replace`) and the `FileNotFoundError` contract are unchanged.

#### Scenario: Save includes system prompt at top level

- **GIVEN** `conv` has 2 messages and `system_prompt = "Eres útil."`
- **WHEN** `Conversation.save(conv, tmp_path / "chat.json", system_prompt="Eres útil.")` runs
- **THEN** the file contents are valid JSON
- **AND** `parsed["system_prompt"] == "Eres útil."`
- **AND** `parsed["messages"]` is preserved

#### Scenario: Load returns tuple

- **GIVEN** a file containing `{"system_prompt": "Eres útil.", "messages": [...]}`
- **WHEN** `Conversation.load(tmp_path / "chat.json")` is called
- **THEN** the result is a `tuple` of length 2
- **AND** `result[0].messages` equals the file's messages
- **AND** `result[1] == "Eres útil."`

#### Scenario: Backward compat — missing field

- **GIVEN** a v0.2.0 file with no `"system_prompt"` key
- **WHEN** `Conversation.load(...)` runs
- **THEN** the result is `(Conversation, "")` and no `KeyError` is raised

#### Scenario: Default system_prompt empty string

- **GIVEN** a conversation with no system prompt
- **WHEN** `Conversation.save(conv, path)` is called (omitting the argument)
- **THEN** the persisted file has `"system_prompt": ""`

### Requirement: Clear Conversation

`Conversation.clear()` SHALL empty the message list in place. The method MUST
return `None`. After `clear()`, `get_messages_for_api()` returns `[]`.

#### Scenario: Clear empties messages

- GIVEN a `Conversation` with two messages
- WHEN `conv.clear()` is called
- THEN `conv.messages == []`
- AND `conv.get_messages_for_api() == []`

#### Scenario: Clear allows re-use

- GIVEN a cleared `Conversation`
- WHEN `conv.add_message("user", "de nuevo")` is called
- THEN `len(conv.messages) == 1`
- AND `conv.messages[0]["content"] == "de nuevo"`

## Added in v0.3.0

### Requirement: System Prompt Survives Reload

`MainWindow._on_load_conversation` SHALL pass the loaded system prompt string to `params_panel.set_system_prompt(...)` and SHALL pass the loaded message list to `chat_panel.set_history(...)` in the same handler. The system prompt and the history MUST be restored atomically — partial state is not acceptable.

#### Scenario: Load restores prompt and history

- **GIVEN** a saved file with `system_prompt="Eres útil."` and 2 messages
- **WHEN** the user opens the file via the `Abrir` menu
- **THEN** `params_panel.get_system_prompt() == "Eres útil."`
- **AND** `chat_panel.get_history()` has length 2
- **AND** both are set before control returns to the event loop
