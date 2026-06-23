# app-shell Spec — Delta for v0.3.0

## Purpose

Adds five `MainWindow` capabilities: background-thread model loading with periodic voice, deterministic initial focus, close-with-conversation confirmation, a model-aware window title, and a generation-progress audio beep. Existing layout, menu, status-bar, and send/stream contracts remain unchanged.

## ADDED Requirements

### Requirement: Background-Thread Model Loading

`MainWindow._on_use_model` SHALL spawn a daemon `threading.Thread` (`daemon=True`) calling `LlamaRunner.start_server(model_path, client, ...)`. The handler MUST (1) disable `use_model_button` AND `restart_server_button`, (2) speak `"Iniciando servidor con <basename>..."` via `wx.CallAfter(speech.speak, ...)`, (3) schedule a `threading.Timer(8.0, ...)` that re-speaks `"Cargando modelo, por favor espera..."` every 8 seconds while loading, (4) call `wx.CallAfter(self._on_start_server_done, ok, message)` on completion, and (5) cancel the active timer in `_on_start_server_done`.

#### Scenario: Disabled buttons, periodic announcement, done handler

- **GIVEN** the user clicks `use_model_button` with a valid model
- **WHEN** the worker spawns
- **THEN** `use_model_button` and `restart_server_button` are disabled
- **AND** a 20-second load produces ≥ 2 `"Cargando modelo, por favor espera..."` calls ~8s apart
- **AND** `_on_start_server_done(True, ...)` cancels the timer and re-enables buttons per state
- **AND** on app close the daemon thread does not block exit and no `wx.CallAfter` fires after window destruction

### Requirement: Deterministic Initial Focus

`MainWindow.__init__` SHALL end with `wx.CallAfter(self._set_initial_focus)`. The method MUST focus exactly one control per this rule:

| State | Focused control |
|---|---|
| Server is running | `message_input` |
| Server down, models present | `use_model_button` |
| Otherwise | `scan_models_button` |

#### Scenario: Focus follows the three states

- **GIVEN** `check_running()` returns `True` → focus is `message_input`
- **GIVEN** `check_running()` is `False` and `model_selector.GetCount() == 2` → focus is `use_model_button`
- **GIVEN** `check_running()` is `False` and `model_selector.GetCount() == 0` → focus is `scan_models_button`

### Requirement: Close Confirmation with Active Conversation

`MainWindow._on_close` SHALL check `len(self._conversation.messages) > 0` BEFORE invoking `LlamaRunner.stop_server()`. If true, it MUST show a `wx.MessageDialog` with stock `YES_NO` labels (NOT custom Spanish — `SetYesNoCancelLabels` is forbidden per AGENTS.md), `NO_DEFAULT`, `ICON_QUESTION`, and text `"¿Salir sin guardar la conversación actual?"`. On "No" → `event.Veto()` and return. On "Yes" → `stop_server()`, unlink each path in `self._temp_html_files` (try/except `os.unlink`), and close.

> Stock `YES_NO` / `NO_DEFAULT` / `ICON_QUESTION` are explicitly permitted; only custom labels trigger the MSAA regression.

#### Scenario: Empty conversation closes silently

- **GIVEN** `len(self._conversation.messages) == 0`
- **WHEN** the user closes the window
- **THEN** no dialog is shown, `stop_server()` runs, and temp files are unlinked (try/except)

#### Scenario: Active conversation prompts and respects choice

- **GIVEN** the conversation has 3 messages
- **WHEN** the user closes the window
- **THEN** a `wx.MessageDialog` is shown with the documented text and `NO_DEFAULT`
- **AND** "No" calls `event.Veto()` and skips `stop_server()`
- **AND** "Yes" calls `stop_server()`, unlinks temp files, and closes

### Requirement: Window Title Reflects Loaded Model

`MainWindow._update_title(model: str | None)` SHALL set the frame title to `f"OllamaChat — {Path(model).stem}"` when `model` is non-empty, and to `"OllamaChat"` when `model is None` or empty. Called from `_on_start_server_done` (success) and `_on_stop_server` (completion).

#### Scenario: Title with and without model

- **GIVEN** model path `"C:\\models\\phi-3.gguf"` is loaded
- **WHEN** `_update_title("C:\\models\\phi-3.gguf")` runs
- **THEN** `frame.GetTitle() == "OllamaChat — phi-3"`
- **AND** `_update_title(None)` resets to `"OllamaChat"`

### Requirement: Generation Beep (Windows Only)

`MainWindow._maybe_beep()` SHALL emit a 50ms 520Hz beep during active generation on Windows. The method MUST (1) early-return on non-Windows via `if sys.platform != "win32": return`, (2) throttle to ≤1 emission/second using `time.monotonic()`, (3) wrap `winsound.Beep(520, 50)` in try/except, and (4) import `winsound` INSIDE the function (line-local) so WSL/Linux imports succeed.

#### Scenario: Beep fires, throttles, and is platform-safe

- **GIVEN** `sys.platform == "win32"` and a previous beep at `t0`
- **WHEN** `_maybe_beep()` is called at `t0 + 0.2` and `t0 + 1.2`
- **THEN** the first call invokes `winsound.Beep(520, 50)` once, the second also invokes it, and a call 0.2s after a beep does NOT
- **AND** on `sys.platform == "linux"` the method returns without importing `winsound`
- **AND** any exception from `winsound.Beep` is swallowed
