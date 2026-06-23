# Accessibility Guidelines Capability Specification

## Purpose

Codifies the non-negotiable MSAA / NVDA / JAWS rules that every wx widget in
OllamaChat MUST follow. These requirements exist because the user is fully
blind: a misnamed or unlabelled control makes the app unusable, and certain
wx sizer types silently break screen-reader reading order. These rules are
testable via reflection-style tests that introspect every widget in a built
window.

## Requirements

### Requirement: Named Interactive Controls

Every interactive widget in the UI (buttons, text inputs, sliders, spin
controls, choices, list boxes, check boxes, radio buttons) MUST be created
with a `name=` keyword argument whose value is a unique, descriptive,
snake_case identifier. Widgets without a `name` MUST fail the accessibility
test.

#### Scenario: Send button has a name

- GIVEN the `ChatPanel` is constructed
- WHEN the test introspects the send button
- THEN `send_button.GetName() == "send_button"`
- AND `send_button.GetName() != ""`

#### Scenario: Slider has a name

- GIVEN the `ParamsPanel` is constructed
- WHEN the test introspects `temperature_slider`
- THEN `temperature_slider.GetName() == "temperature_slider"`

### Requirement: StaticText Labels Precede Interactive Controls

Every interactive widget MUST be preceded in its parent sizer by a
`wx.StaticText` label whose text describes the control's purpose. The
StaticText MUST appear immediately before the control in the sizer
construction order so MSAA associates the label with the control.

#### Scenario: Temperature label precedes slider

- GIVEN the `ParamsPanel` sizer is built
- WHEN the test enumerates the sizer children in order
- THEN a `wx.StaticText` with label `"Temperatura:"` is followed (immediately
  or after a small spacer) by `temperature_slider`

#### Scenario: Send button has a parent label

- GIVEN the `ChatPanel` sizer is built
- WHEN the test checks the button row
- THEN a `wx.StaticText` with label `"Acciones:"` precedes `send_button`,
  `stop_button`, `attach_button`, and `clear_button`

### Requirement: Only `wx.BoxSizer` for Layout

The UI MUST use only `wx.BoxSizer` (horizontal and vertical) for layout. No
`wx.GridSizer`, `wx.FlexGridSizer`, or `wx.GridBagSizer` is permitted anywhere
in `ollamachat/ui/`. This rule is enforceable by AST inspection or by
`grep`-style tests in CI.

#### Scenario: No grid sizers in ui/

- GIVEN a search of `ollamachat/ui/` for `GridSizer`, `FlexGridSizer`, and
  `GridBagSizer`
- WHEN the test runs
- THEN zero matches are found

#### Scenario: Panels use BoxSizer [windows-only]

- GIVEN `ParamsPanel` and `ChatPanel` are constructed
- WHEN the test calls `GetSizer()` on both
- THEN both return `wx.BoxSizer` instances
- AND neither uses `wx.VERTICAL` and `wx.HORIZONTAL` mixing that breaks reading
  order

### Requirement: Sliders Speak Value on Change

Every `wx.Slider` in the UI MUST update its associated value label in real
time AND invoke `speech.speak(formatted_value, interrupt=False)` on every
value change. This is the only way a blind user can hear what number they are
adjusting.

#### Scenario: Temperature slider speaks on change

- GIVEN a `ParamsPanel` with a stubbed `Speech`
- WHEN the temperature slider's value changes from 70 to 130
- THEN `temperature_label.GetLabel() == "1.30"`
- AND the stubbed `Speech.speak` was called with `"1.30"` and
  `interrupt=False`

#### Scenario: Top-p slider speaks on change

- GIVEN a `ParamsPanel` with a stubbed `Speech`
- WHEN the top-p slider's value changes from 90 to 50
- THEN `top_p_label.GetLabel() == "0.50"`
- AND `Speech.speak("0.50", interrupt=False)` was called

#### Scenario: Repeat penalty slider speaks on change

- GIVEN a `ParamsPanel` with a stubbed `Speech`
- WHEN the repeat penalty slider's value changes from 110 to 150
- THEN `repeat_penalty_label.GetLabel() == "1.50"`
- AND `Speech.speak("1.50", interrupt=False)` was called

### Requirement: Status Bar Speaks

The status bar at the bottom of `MainWindow` MUST announce its text changes
via `speech.speak(new_text, interrupt=True)` whenever the text is updated
(e.g., connection state changes, model name, activity indicator).

#### Scenario: Status bar update announces

- GIVEN `MainWindow` with a stubbed `Speech`
- WHEN the status bar text is set to `"Conectado a Ollama"`
- THEN `Speech.speak("Conectado a Ollama", interrupt=True)` was called

#### Scenario: Activity indicator announces

- GIVEN `MainWindow` with a stubbed `Speech`
- WHEN the status bar text is set to `"Generando respuesta..."`
- THEN `Speech.speak("Generando respuesta...", interrupt=True)` was called

### Requirement: Error Dialogs Speak

Any `wx.MessageDialog` or `wx.MessageBox` shown by the app MUST be followed
by a `speech.speak(message, interrupt=True)` call with the same message text,
so the user hears the error even if their screen reader fails to capture the
dialog.

#### Scenario: Ollama down dialog announces

- GIVEN `MainWindow` with a stubbed `Speech`
- WHEN the startup Ollama check fails and the app shows a `wx.MessageDialog`
  with text `"No se puede conectar a Ollama en http://localhost:11434"`
- THEN `Speech.speak("No se puede conectar a Ollama en
  http://localhost:11434", interrupt=True)` was called

#### Scenario: Generation error dialog announces

- GIVEN a generation error fires the `on_error` callback
- WHEN `MainWindow` shows a `wx.MessageDialog` with the error text
- THEN `Speech.speak(error_text, interrupt=True)` was called

### Requirement: No `wx.WebView`

The UI MUST NOT use `wx.WebView` or any HTML-based widget anywhere in
`ollamachat/ui/`. Web views are opaque to screen readers and break the
blind-user contract. Markdown rendering, if added later, MUST be done in
plain `wx.TextCtrl` with `TE_RICH2`.

#### Scenario: No WebView imports

- GIVEN a search of `ollamachat/ui/` for `import wx.html`, `import
  wx.webkit`, and `wx.WebView`
- WHEN the test runs
- THEN zero matches are found

## Added in v0.3.0

### Requirement: Full Keyboard Accelerator Table

`MainWindow` SHALL install a `wx.AcceleratorTable` built in `_build_accelerators` with the following bindings (existing Ctrl+N / Ctrl+O / Ctrl+S / F5 / Escape are preserved; new entries are additive):

| Key | Action | Target control |
|---|---|---|
| `Alt+1` | Focus message input | `message_input` |
| `Alt+2` | Focus message list, auto-select last, speak `"Historial, N mensajes"` | `message_list` |
| `Alt+3` | Focus model selector | `model_selector` |
| `Alt+4` | Focus temperature slider | `temperature_slider` |
| `Alt+5` | Focus system prompt | `system_prompt` |
| `Alt+6` | Focus use-model / restart-server button | `use_model_button` or `restart_server_button` |
| `F2` | Announce session status | `speech.speak` |
| `F6` | Cycle params → list → input | focus advances via `self._focus_cycle_index` |

All bindings MUST be defined in a single method `_build_accelerators()` that returns a `wx.AcceleratorTable` assigned via `frame.SetAcceleratorTable(...)`. The F6 cycle MUST maintain `self._focus_cycle_index: int` across cycles.

#### Scenario: Accelerator table contains all bindings

- **GIVEN** `MainWindow` is constructed
- **WHEN** the test reads `frame.GetAcceleratorTable().GetEntries()` length
- **THEN** it is at least 8 (Ctrl+N, Ctrl+O, Ctrl+S, F5, Escape + Alt+1..6 + F2 + F6 = 13 entries minimum)

#### Scenario: Alt+2 announces message count

- **GIVEN** `message_list` contains 3 rows
- **WHEN** the user presses `Alt+2`
- **THEN** focus moves to `message_list`
- **AND** the last item is auto-selected
- **AND** `speech.speak("Historial, 3 mensajes", interrupt=True)` is called

#### Scenario: F6 cycles panels

- **GIVEN** the cycle index starts at 0
- **WHEN** F6 is pressed three times
- **THEN** focus moves to: `params_panel` → `message_list` → `message_input`
- **AND** `self._focus_cycle_index` advances by one modulo 3 on each press

### Requirement: F2 Session-Status Announcement

`MainWindow._announce_session_status()` SHALL compose a single speech string containing the current model basename, server status, message count, accumulated token count, temperature, top_p, and a `Generando: Sí/No` flag. The string MUST be spoken via `speech.speak(..., interrupt=True)`. The method MUST NOT open a `wx.MessageDialog` — voice only. All numeric values MUST be read in Spanish (e.g. `"1,30"`, `"0,90"`).

#### Scenario: F2 speaks composed status

- **GIVEN** model=`"phi-3.gguf"`, server=running, messages=4, tokens=512, temp=0.7, top_p=0.9, generating=False
- **WHEN** the user presses F2
- **THEN** `speech.speak` is called with a string that contains `"phi-3.gguf"`, `"conectado"` or `"corriendo"`, `"4 mensajes"`, `"512"`, `"0,70"` / `"1,30"` style numbers, and `"Generando: No"`
- **AND** `interrupt=True` is passed
- **AND** no dialog is shown

#### Scenario: F2 reflects generating state

- **GIVEN** a generation is in progress
- **WHEN** F2 is pressed
- **THEN** the spoken status contains `"Generando: Sí"`

### Requirement: Listbox Printable-Key Routing

`message_list` SHALL bind `EVT_KEY_DOWN` so that any printable character NOT bound by the accelerator table (i.e. not Ctrl+C, not Ctrl+Enter) routes the character to `message_input.AppendText(char)` and calls `message_input.SetFocus()`. This lets a blind user keep typing without first pressing Alt+1.

#### Scenario: Printable letter moves focus to input

- **GIVEN** `message_list` has focus
- **WHEN** the user presses `"a"` (no modifier)
- **THEN** `message_input.SetFocus()` is called
- **AND** `message_input.GetValue()` ends with `"a"`
