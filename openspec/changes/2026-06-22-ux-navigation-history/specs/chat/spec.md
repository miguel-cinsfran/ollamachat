# chat Spec — Delta for v0.3.0

## Purpose

Replaces the single read-only transcript with a dual view (ListBox of previews + TextCtrl for the current stream), adds a popup detail dialog, an "open in browser" action, and a right-click context menu. Exposes `get_message_at` / `get_history` / `set_history` as pure-Python APIs to keep `core/` testable.

> **AGENTS.md constraint (binding)**: `MessageDetailDialog` MUST be a custom `wx.Dialog` with native `wx.Button`s. `wx.MessageDialog` with `SetYesNoCancelLabels()` is forbidden (NVDA regresses on custom labels via MSAA). Encoded below.

## MODIFIED Requirements

### Requirement: Read-only Conversation Display

(Previously: single `conversation_display` `wx.TextCtrl` showing the full transcript.)

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

## ADDED Requirements

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
