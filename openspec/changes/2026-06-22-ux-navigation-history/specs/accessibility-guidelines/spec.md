# accessibility-guidelines Spec — Delta for v0.3.0

## Purpose

Adds a comprehensive `wx.AcceleratorTable` (Alt+1..6, F2, F6) and a session-status announcement (F2) so blind users can navigate and inspect the app without touching the mouse. Keeps all existing MSAA / NVDA rules intact.

## ADDED Requirements

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
