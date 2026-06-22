# App Shell Capability Specification

## Purpose

Defines `MainWindow`, the top-level wx window that hosts the parameters panel
on the left and the chat panel on the right, plus the menu bar, status bar,
accelerator table, and startup Ollama check. The shell is the integration
point that ties `ParamsPanel`, `ChatPanel`, `OllamaClient`, `Conversation`,
and `Speech` into a single usable app. It also defines the message-send
flow: building the API payload, streaming tokens, and reacting to done/error.

## Requirements

### Requirement: Window Size and Splitter Layout

`MainWindow` SHALL be a `wx.Frame` sized 1100x700 (default, resizable) with
a horizontal `wx.SplitterWindow` that splits the window into a left
`ParamsPanel` (280px) and a right `ChatPanel` (rest of the space). The
splitter's minimum pane size on the left SHALL be 280.

#### Scenario: Frame construction [windows-only]

- GIVEN the app starts
- WHEN `MainWindow` is constructed
- THEN `frame.GetSize() == (1100, 700)` (initial size)
- AND `splitter.GetWindow1() is params_panel`
- AND `splitter.GetWindow2() is chat_panel`
- AND `splitter.GetSashPosition() == 280`

### Requirement: Menu Bar — Archivo

The menu bar MUST have an "Archivo" menu with these items in order: Nueva
conversación (Ctrl+N), Abrir (Ctrl+O), Guardar (Ctrl+S), Salir (Alt+F4).
Each item MUST have a `name=` (`menu_new`, `menu_open`, `menu_save`,
`menu_exit`).

#### Scenario: Archivo menu items present [windows-only]

- GIVEN `MainWindow` is constructed
- WHEN the test inspects the menu bar
- THEN the "Archivo" menu has exactly 4 items
- AND `menu_new.GetItemLabel() == "Nueva conversación"`
- AND `menu_open.GetItemLabel() == "Abrir"`
- AND `menu_save.GetItemLabel() == "Guardar"`
- AND `menu_exit.GetItemLabel() == "Salir"`

### Requirement: Menu Bar — Ayuda

The menu bar MUST have an "Ayuda" menu with these items: Acerca de
(`menu_about`), Atajos de teclado (`menu_shortcuts`).

#### Scenario: Ayuda menu items present [windows-only]

- GIVEN `MainWindow` is constructed
- WHEN the test inspects the "Ayuda" menu
- THEN it has exactly 2 items
- AND `menu_about.GetItemLabel() == "Acerca de"`
- AND `menu_shortcuts.GetItemLabel() == "Atajos de teclado"`

### Requirement: Status Bar

`MainWindow` SHALL have a `wx.StatusBar` with three fields: connection state
(field 0), current model (field 1), activity (field 2). Each field update
MUST trigger `speech.speak(new_text, interrupt=True)` per the
`accessibility-guidelines`.

#### Scenario: Initial status [windows-only]

- GIVEN `MainWindow` is constructed before Ollama is checked
- WHEN the test reads the status bar
- THEN field 0 is `"Iniciando..."`
- AND field 1 is `""`
- AND field 2 is `""`

#### Scenario: Status updates on Ollama up

- GIVEN `OllamaClient.check_running()` returns `True`
- WHEN startup finishes
- THEN status field 0 is `"Conectado"`
- AND `Speech.speak("Conectado", interrupt=True)` was called

### Requirement: Accelerator Table

`MainWindow` SHALL install a `wx.AcceleratorTable` with the following
bindings: Ctrl+N → Nueva conversación, Ctrl+O → Abrir, Ctrl+S → Guardar,
F5 → Actualizar modelos, Escape → abort current generation.

#### Scenario: Accelerator table registered [windows-only]

- GIVEN `MainWindow` is constructed
- WHEN the test reads `frame.GetAcceleratorTable()`
- THEN the table contains exactly 5 entries
- AND the entries map the keys: `Ctrl+N`, `Ctrl+O`, `Ctrl+S`, `F5`, `Escape`

#### Scenario: Escape aborts running generation

- GIVEN a generation is in progress (streaming thread active)
- WHEN the user presses Escape
- THEN `OllamaClient.abort()` is invoked
- AND `chat_panel` re-enables the send and attach buttons

### Requirement: Startup Ollama Check

On `MainWindow` construction, the app MUST call
`OllamaClient.check_running()`. If `False`, it MUST show a
`wx.MessageDialog` warning AND call
`speech.speak("No se puede conectar a Ollama en http://localhost:11434",
interrupt=True)`. If `True`, it MUST call `OllamaClient.list_models()` and
pass the result to `params_panel.set_models(...)`.

#### Scenario: Ollama is up at startup

- GIVEN `OllamaClient.check_running()` returns `True` and
  `list_models()` returns `["llama3:latest", "llava:13b"]`
- WHEN `MainWindow` finishes startup
- THEN no error dialog is shown
- AND `params_panel.model_selector.GetCount() == 2`
- AND `params_panel.model_selector.GetString(0) == "llama3:latest"`

#### Scenario: Ollama is down at startup

- GIVEN `OllamaClient.check_running()` returns `False`
- WHEN `MainWindow` finishes startup
- THEN a `wx.MessageDialog` is shown with text starting with
  `"No se puede conectar"`
- AND `Speech.speak` is called with that text and `interrupt=True`
- AND `params_panel.model_selector` remains empty

### Requirement: Send Message Flow — Payload Construction

When the user triggers a send (via Enter in input or send button), the
shell MUST: (1) read the input text and any attachment from `chat_panel`,
(2) prepend a `{"role": "system", "content": system_prompt}` message IF
`get_system_prompt()` is non-empty, (3) append the current
`Conversation.get_messages_for_api()` to the payload, (4) append the new
user message (with images if attached), (5) clear the input and attachment,
(6) display the user message in the conversation, (7) call
`OllamaClient.chat_stream(model, messages, options, on_token, on_done,
on_error)` with options from `params_panel.get_params()`.

#### Scenario: Send with system prompt

- GIVEN system prompt is `"Eres útil."`, conversation has one user message
  `"Hola"`, and input is `"¿Qué es Python?"`
- WHEN the user presses Enter
- THEN the `chat_stream` call's `messages` argument is:
  `[{"role": "system", "content": "Eres útil."},
    {"role": "user", "content": "Hola"},
    {"role": "user", "content": "¿Qué es Python?"}]`
- AND `message_input` is empty
- AND the conversation display shows `[Usuario] ¿Qué es Python?\n`
- AND the conversation now has 2 messages (the system one is NOT added to
  the local conversation; it's only in the API payload)

#### Scenario: Send without system prompt

- GIVEN system prompt is `""`, conversation is empty, input is `"Hola"`
- WHEN the user presses Enter
- THEN the `chat_stream` call's `messages` argument is:
  `[{"role": "user", "content": "Hola"}]`
- AND no `{"role": "system"}` entry is prepended

#### Scenario: Send with attached image

- GIVEN input is `"¿Qué ves?"` and an image is attached
- WHEN the user presses Enter
- THEN the new user message in the API payload is
  `{"role": "user", "content": "¿Qué ves?",
  "images": [<base64 string>]}`
- AND `chat_panel.attachment_label` is reset to `"(ninguno)"`

### Requirement: Streaming Callbacks

`on_token` MUST append the token to `conversation_display` (after the
`[Asistente]` prefix) and call `speech.announce_token_chunk(token)`.
`on_done` MUST call `speech.flush_token_buffer()`,
`speech.speak("Respuesta completa", interrupt=True)`, re-enable the send and
attach buttons, save the full assistant response to the conversation, and
clear any abort state. `on_error` MUST append the error text to
`conversation_display` and call
`speech.speak(error_text, interrupt=True)`.

#### Scenario: on_token updates display and announces

- GIVEN a generation is in progress and the display shows
  `[Usuario] Hola\n[Asistente]`
- WHEN `on_token(" mundo")` fires
- THEN the display shows `[Usuario] Hola\n[Asistente] mundo`
- AND `speech.announce_token_chunk(" mundo")` was called

#### Scenario: on_done finalizes

- GIVEN a generation completes with full response `"Hola, ¿en qué te
  ayudo?"`
- WHEN `on_done()` fires
- THEN `speech.flush_token_buffer()` was called
- AND `speech.speak("Respuesta completa", interrupt=True)` was called
- AND the conversation has a new assistant message with content
  `"Hola, ¿en qué te ayudo?"`
- AND `send_button` and `attach_button` are enabled

#### Scenario: on_error shows and announces

- GIVEN a generation fails with error text `"Connection refused"`
- WHEN `on_error("Connection refused")` fires
- THEN `conversation_display` ends with the text `Connection refused`
- AND `speech.speak("Connection refused", interrupt=True)` was called
- AND the send and attach buttons are re-enabled

### Requirement: Save and Load Conversation

When the user activates "Guardar" (Ctrl+S), the shell MUST open a
`wx.FileDialog` (default name `conversacion.json`, wildcard `*.json`) and
call `Conversation.save(conv, filepath)` with the current `Conversation`
instance and the chosen path. "Abrir" (Ctrl+O) MUST open a `wx.FileDialog`
and call `Conversation.load(filepath)` to replace the current conversation,
updating the `conversation_display` to show the loaded transcript.

#### Scenario: Save conversation

- GIVEN a conversation with 3 messages
- WHEN the user activates "Guardar" and picks a path
- THEN `Conversation.save(conv, filepath)` is called
- AND the file exists on disk and parses back to an equal conversation

#### Scenario: Load conversation

- GIVEN a previously saved file at `/tmp/chat.json` with 2 messages
- WHEN the user activates "Abrir" and picks that file
- THEN the current `Conversation` is replaced with the loaded one
- AND `conversation_display` shows the loaded transcript
- AND the conversation has exactly 2 messages

### Requirement: New Conversation (Clear)

When the user activates "Nueva conversación" (Ctrl+N), the shell MUST call
`chat_panel.clear()` (which clears the conversation and the display) and
reset the attachment label to `"(ninguno)"`.

#### Scenario: New conversation clears state

- GIVEN a conversation with 2 messages and a display with content
- WHEN the user activates "Nueva conversación"
- THEN `conversation.messages == []`
- AND `conversation_display` is empty
- AND `chat_panel.attachment_label.GetLabel() == "(ninguno)"`

### Requirement: Start Ollama Button

The shell MUST display a button labeled "Iniciar Ollama" with
`name="start_ollama_button"`, preceded by a `wx.StaticText` label
"Servidor:". When clicked, `MainWindow` MUST delegate to
`ollamachat.core.ollama_runner.start_ollama(client)`. Every state
transition (click, already running, spawn, success, timeout, spawn
failure) MUST be logged via `ollamachat.core.logger.get_logger()` and
announced via `speech.speak(message, interrupt=True)`. On Windows, the
spawned subprocess MUST be created with `creationflags=0x08000000`
(`CREATE_NO_WINDOW`) so no console window flashes.

#### Scenario: Button present in UI [windows-only]

- GIVEN `MainWindow` is constructed
- WHEN the source is inspected
- THEN a `wx.Button` with `name="start_ollama_button"` exists
- AND a preceding `wx.StaticText` label "Servidor:" exists

#### Scenario: Click when already running

- GIVEN Ollama is responding
- WHEN the user clicks the start button
- THEN `start_ollama(client)` returns `(True, "Ollama ya está corriendo")`
- AND the logger records the "already running" event
- AND `speech.speak` is called with "Ollama ya está corriendo", interrupt=True

#### Scenario: Click when down spawns and announces success

- GIVEN Ollama is not responding
- AND `ollama serve` is spawned successfully
- AND `check_running` becomes True within the poll window
- WHEN the user clicks the start button
- THEN `start_ollama(client)` returns `(True, "Ollama listo")`
- AND the logger records "spawn" and "started successfully"
- AND `speech.speak` is called with "Ollama listo", interrupt=True
- AND `check_running` is polled at most 25 times at 0.2s intervals

#### Scenario: Click when down but timeout

- GIVEN Ollama is not responding
- AND `ollama serve` is spawned but `check_running` never returns True
- WHEN the user clicks the start button
- THEN `start_ollama(client)` returns `(False, "Ollama no responde")`
- AND the logger records the timeout
- AND `speech.speak` is called with "Ollama no responde", interrupt=True

#### Scenario: Click when ollama binary missing

- GIVEN Ollama is not responding
- AND the `ollama` command is not on PATH (FileNotFoundError)
- WHEN the user clicks the start button
- THEN the exception is caught inside `start_ollama`
- AND it returns `(False, "No se pudo iniciar Ollama: ...")`
- AND the logger records the error
- AND `speech.speak` is called with the error message, interrupt=True

### Requirement: Application Logging

`MainWindow` MUST use `ollamachat.core.logger.get_logger()` to record
the following events: startup detection (Ollama up / down), model list
refreshes (with count and selection), and the start-Ollama flow (click,
spawn, success, timeout, error). The logger MUST be idempotent
(repeated calls return the same configured logger) and MUST never
crash the app on file-open failure. The default log file is
`data/ollamachat.log` in the current working directory, written in
UTF-8.

#### Scenario: Log file is created on first use

- GIVEN `MainWindow` is constructed and the working directory is writable
- WHEN any logged event occurs
- THEN `data/ollamachat.log` exists in the working directory
- AND the log file contains the event with a timestamp

#### Scenario: Logger does not crash on file-open failure

- GIVEN the data directory cannot be created or written
- WHEN `get_logger()` is called
- THEN no exception is raised
- AND a `NullHandler` is attached as fallback
- AND `log.info(...)` calls do not raise

#### Scenario: Logger is idempotent

- GIVEN `get_logger()` has been called once
- WHEN it is called again
- THEN the same logger object is returned
- AND no second FileHandler is attached
