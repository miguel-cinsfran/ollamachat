# conversation-persistence Spec — Delta for v0.3.0

## Purpose

Persists the system prompt at the top level of the conversation JSON so reloading a saved conversation restores the system prompt as well as the messages. Maintains atomic-write semantics and backward compatibility with files written by v0.2.0 (which lack the field).

## MODIFIED Requirements

### Requirement: Disk Persistence — `save` / `load`

(Previously: `Conversation.save(conv, filepath)` — no system prompt; `Conversation.load(filepath) -> Conversation`.)

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

## ADDED Requirements

### Requirement: System Prompt Survives Reload

`MainWindow._on_load_conversation` SHALL pass the loaded system prompt string to `params_panel.set_system_prompt(...)` and SHALL pass the loaded message list to `chat_panel.set_history(...)` in the same handler. The system prompt and the history MUST be restored atomically — partial state is not acceptable.

#### Scenario: Load restores prompt and history

- **GIVEN** a saved file with `system_prompt="Eres útil."` and 2 messages
- **WHEN** the user opens the file via the `Abrir` menu
- **THEN** `params_panel.get_system_prompt() == "Eres útil."`
- **AND** `chat_panel.get_history()` has length 2
- **AND** both are set before control returns to the event loop
