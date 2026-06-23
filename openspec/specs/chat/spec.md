# Chat Capability Specification

## Purpose

Defines the conversation panel widget that lets a blind user compose messages to
a local Ollama model, attach files (images or text), and read both their own
input and the assistant's streamed reply. The panel is the only place a user
hears the model's voice (via `speech.announce_token_chunk`) and the only place
they trigger send, stop, attach, and clear. All widgets are named and labeled
so MSAA exposes them to NVDA/JAWS in a predictable reading order.

## Requirements

### Requirement: Read-only Conversation Display

The chat panel SHALL provide a `wx.ListBox` named `message_list` (preceded by `wx.StaticText("Historial:")`) and a `wx.TextCtrl` named `stream_display` (preceded by `wx.StaticText("Respuesta actual:")`) with `TE_MULTILINE | TE_READONLY | TE_RICH2`. The panel SHALL keep a parallel `self._history: list[tuple[str, str]]`; `message_list` rows format as `"[Tú] <first 80 chars>"` or `"[IA] <first 80 chars>"` and auto-select the last item on append. All sizers MUST be `wx.BoxSizer`; `wx.GridSizer` is forbidden.

#### Scenario: Preview, auto-select, stream isolation

- **GIVEN** history is `[("user", "Hola, ¿cómo estás hoy?")]`
- **WHEN** the list renders and a new append fires
- **THEN** `message_list.GetString(0) == "[Tú] Hola, ¿cómo estás hoy?"` (truncated with `…` past 80)
- **AND** `message_list.GetSelection()` points to the newly appended row
- **AND** `on_token(" mundo")` only updates `stream_display`, not `message_list`

#### Scenario: Accessibility invariants

- **GIVEN** the `ChatPanel` is built
- **WHEN** the source is inspected (AST)
- **THEN** every new `wx` control has `name=`, every interactive control is preceded by `wx.StaticText`, and only `wx.BoxSizer` is used (zero `GridSizer` matches)

### Requirement: Multiline Message Input

The chat panel SHALL provide an editable multiline text control named
`message_input` created with `TE_MULTILINE | TE_PROCESS_ENTER` so the user can
type multi-line prompts and trigger the send action with the Enter key. The
control MUST be paired with a preceding `wx.StaticText` label "Mensaje:" so
screen readers announce the field purpose before focus.

#### Scenario: Read user input

- GIVEN the user has typed `"¿Qué es Python?"` into `message_input`
- WHEN the panel calls `get_input_text()`
- THEN the returned string is exactly `"¿Qué es Python?"`
- AND the string preserves accented characters (UTF-8 preserved)

#### Scenario: Clear input after send

- GIVEN `message_input` contains `"Hola"`
- WHEN a send action is triggered
- THEN the panel calls `_clear_input()`
- AND `get_input_text()` returns the empty string

### Requirement: Horizontal Action Button Row

The chat panel SHALL display four buttons in a horizontal `wx.BoxSizer`, in this
order from left to right: Enviar, Detener, Adjuntar, Limpiar. Each button MUST
have a `name=` argument (`send_button`, `stop_button`, `attach_button`,
`clear_button`) and MUST be preceded in the sizer by a `wx.StaticText` label
(or the buttons are grouped under a single "Acciones" label) so MSAA exposes
them as a labeled group.

#### Scenario: Buttons disabled while generating

- GIVEN the panel is idle and no generation is in progress
- WHEN `start_generation()` is called
- THEN `send_button` and `attach_button` are disabled (`Enable(False)`)
- AND `stop_button` is enabled
- AND `clear_button` is enabled

#### Scenario: Buttons re-enabled after generation finishes

- GIVEN `start_generation()` was called and `stop_button` is enabled
- WHEN the `on_done` callback fires
- THEN `send_button`, `attach_button`, and `clear_button` are all enabled
- AND `stop_button` is disabled (no active generation to stop)

#### Scenario: Clear button wipes transcript

- GIVEN `conversation_display` contains `[Usuario] Hola\n[Asistente] Hola, ¿en qué te ayudo?`
- WHEN the user activates `clear_button`
- THEN the panel calls `conversation.clear()` and the display is empty
- AND `get_input_text()` returns the empty string

### Requirement: Attachment File Dialog and Payload Routing

The chat panel SHALL open a `wx.FileDialog` when `attach_button` is activated
and route the chosen file by extension: `jpg`, `jpeg`, `png`, `bmp`, `gif`
MUST be base64-encoded and added to the next user message under the `images`
key; any other extension MUST be read as UTF-8 text and appended to the
message body. The original filename MUST be announced via `speech.speak`.

#### Scenario: Attach a PNG image

- GIVEN the user clicks `attach_button` and selects `cat.png`
- WHEN `attach_file("cat.png")` runs
- THEN `self._attached_images` contains exactly one base64 string
- AND `self._attached_text` is `None`
- AND `speech.speak("Imagen adjuntada: cat.png", interrupt=True)` is called

#### Scenario: Attach a non-image file as text

- GIVEN the user selects `notes.txt` containing `"comprar leche"`
- WHEN `attach_file("notes.txt")` runs
- THEN `self._attached_text == "comprar leche"`
- AND `self._attached_images` is empty
- AND `speech.speak("Archivo de texto adjuntado: notes.txt", interrupt=True)` is called

#### Scenario: Re-attaching replaces previous attachment

- GIVEN `self._attached_images` already has one image from `cat.png`
- WHEN the user selects `dog.jpg`
- THEN `self._attached_images` contains exactly one base64 string
- AND the previous cat.png base64 is no longer present

### Requirement: Attachment Label Visibility

The chat panel SHALL display a `wx.StaticText` named `attachment_label` (with
a preceding "Adjunto:" label) showing the currently attached filename, or the
text "(ninguno)" when no file is attached. The label MUST update immediately
on attach and on clear.

#### Scenario: Initial label state

- GIVEN a fresh `ChatPanel`
- WHEN the panel is constructed
- THEN `attachment_label.GetLabel() == "(ninguno)"`

#### Scenario: Label updates on attach

- GIVEN `attachment_label` shows "(ninguno)"
- WHEN the user attaches `report.txt`
- THEN `attachment_label.GetLabel() == "report.txt"` within the same tick

### Requirement: Keyboard Handling for Input

The chat panel SHALL bind `message_input` so that pressing `Enter` triggers
the send action and pressing `Shift+Enter` inserts a newline (since
`TE_PROCESS_ENTER` swallows plain Enter). Pressing `Escape` while a generation
is in progress MUST abort the in-flight `OllamaClient.chat_stream` call.

#### Scenario: Enter sends a message [windows-only]

- GIVEN `message_input` contains `"Hola"` and the input has focus
- WHEN the user presses Enter (no Shift)
- THEN the panel triggers the send action exactly once
- AND the input is cleared

#### Scenario: Shift+Enter inserts newline [windows-only]

- GIVEN `message_input` has focus and contains `"line1"`
- WHEN the user presses Shift+Enter
- THEN the input value becomes `"line1\n"`
- AND the send action is NOT triggered

#### Scenario: Escape aborts generation [windows-only]

- GIVEN `chat_stream` is running and `stop_button` is enabled
- WHEN the user presses Escape
- THEN `OllamaClient.abort()` is invoked (sets the stop event)
- AND `on_done` fires with an `aborted=True` signal so the UI re-enables controls

## Added in v0.3.0

### Requirement: Message Detail Dialog

`MessageDetailDialog` SHALL be a `wx.Dialog` (`name="message_detail_dialog"`) with one read-only `wx.TextCtrl` named `content_text` (`TE_MULTILINE | TE_READONLY | TE_RICH2`) and three native `wx.Button`s named `open_browser_button`, `copy_button`, `close_button`. The dialog MUST call `content_text.SetFocus()` in `__init__` and MUST close on `Escape` via `EndModal(wx.ID_CANCEL)`. AST MUST verify zero `MessageDialog` tokens in `message_detail_dialog.py` (AGENTS.md).

#### Scenario: Focus, Escape, no MessageDialog

- **GIVEN** the dialog is constructed with text `"Hola"`
- **THEN** `FindFocus()` is `content_text`
- **AND** `Escape` calls `EndModal(wx.ID_CANCEL)`
- **AND** the source contains no `MessageDialog` token

### Requirement: Open Message in System Browser

`MainWindow._open_message_in_browser(text)` SHALL write a UTF-8 `.html` tempfile (`tempfile.NamedTemporaryFile(suffix=".html", delete=False)`), render via `markdown.markdown(text)`, open with `webbrowser.open(path)`, and append the path to `self._temp_html_files`. `markdown` MUST be added to `pyproject.toml`.

#### Scenario: Tempfile is tracked and cleaned on close

- **GIVEN** `_open_message_in_browser("# Hola")` is called
- **THEN** `len(self._temp_html_files) == 1`, the file exists, and `_on_close` calls `os.unlink(p)` (try/except) and clears the list

### Requirement: Context Menu on Message List

`message_list` SHALL bind `EVT_CONTEXT_MENU` to a `wx.Menu` with three items, all with `name=`: `menu_copy_message` (`Ctrl+C`), `menu_open_browser` (`Ctrl+Enter`), `menu_delete_message`. The `menu_delete_message` item MUST be omitted when a generation is in progress.

#### Scenario: Menu shrinks while generating

- **GIVEN** the panel is idle
- **THEN** the menu has three items with the documented `name=` values
- **WHEN** `start_generation()` runs
- **THEN** `menu_delete_message` is removed and the other two remain

### Requirement: Public History Accessors

`ChatPanel` SHALL expose `get_message_at(index)` (returns `(role, content)` or raises `IndexError`), `get_history()` (returns a copy of `self._history`), and `set_history(items)` (replaces `self._history` and repopulates `message_list`). All three MUST be safe from any thread — no wx objects in the return value.

#### Scenario: Round-trip via accessors

- **GIVEN** `set_history([("user", "A"), ("assistant", "B")])`
- **THEN** `get_history()` returns a copy equal to the input, `get_message_at(1) == ("assistant", "B")`, and `message_list.GetCount() == 2`

### Requirement: Ctrl+C Copies Selected Message

`message_list` SHALL bind `Ctrl+C` to copy the FULL (non-truncated) selected message to the clipboard and call `speech.speak("Mensaje copiado", interrupt=False)`.

#### Scenario: Full body is copied

- **GIVEN** the selected message has a 200-char body
- **WHEN** `Ctrl+C` is pressed
- **THEN** the clipboard holds the full 200-char body and `speech.speak("Mensaje copiado", interrupt=False)` is invoked
