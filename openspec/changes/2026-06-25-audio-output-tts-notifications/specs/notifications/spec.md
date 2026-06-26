# Notifications Capability Specification

## Purpose

Defines the audio + OS-notification dispatcher that informs the user
when the application is not in focus: a generation finishes, the
server is ready, the model is loaded, a tool is awaiting permission,
or an error occurs. The module is split into two pieces to keep
`core/` wx-free: a pure dispatcher (`core/notifier.py`) and a thin
wx adapter (`ui/wx_notifier.py`) that wraps `wx.adv.NotificationMessage`
with a line-local `wx.adv` import under `sys.platform == "win32"`.

The dispatcher policy is: when the app window is not focused, fire a
toast AND a sound cue; when focused, stay silent (the screen reader
is the live channel). The master toggles `notifications_enabled` and
`sounds_enabled` (both default `True`) and the per-theme knob
`sound_theme` (default `"default"`, `"none"` = no playback) live on
`BellbirdConfig`. The dispatcher is fed by six event sites in
`MainWindow` (see `app-shell` v0.10.0): `generation_complete`,
`server_ready`, `model_loaded`, `tool_request`, `error`. Reasoning
is never announced.

## Requirements

### Requirement: `FocusChecker` protocol (core is wx-free)

`bellbird/core/focus.py` SHALL define a `FocusChecker` protocol with
a single method `is_focused() -> bool` (returns `True` if the app
window currently has OS focus, `False` otherwise). The protocol is
defined in `core/` so the `Notifier` dispatcher remains unit-testable
on WSL without `wx`. The wx implementation in `main_window.py` is
a lambda: `lambda: not self.IsActive()`.

#### Scenario: FocusChecker protocol is importable from core

- GIVEN `bellbird/core/focus.py`
- WHEN `from bellbird.core.focus import FocusChecker` runs
- THEN the import succeeds
- AND no `wx` import is triggered (AST guard: no `import wx` at module scope)

#### Scenario: Custom FocusChecker implementations satisfy the protocol

- GIVEN a stub `class FakeFocus: def is_focused(self): return False`
- WHEN `FakeFocus()` is passed to `Notifier(...)`
- THEN the dispatcher accepts it (structural typing — no explicit `isinstance` check)

### Requirement: `Notifier` is silent when the app is focused

`core/notifier.py::Notifier` MUST accept a `FocusChecker`, a
`ToastSender` (callable: `(event: str, message: str) -> None`), and a
`SoundPlayer` (callable: `(event: str) -> None`) at construction
time. `Notifier.notify(event: str, message: str) -> None` MUST check
focus first: if `focus.is_focused() is True`, the call is a silent
no-op — no toast, no sound. The method MUST NOT raise.

#### Scenario: notifier is silent when focused

- GIVEN a `Notifier` with a `FocusChecker` returning `True`
- AND stubbed `ToastSender` and `SoundPlayer` recording calls
- WHEN `notifier.notify("generation_complete", "Listo")` is called
- THEN the toast sender is NOT called
- AND the sound player is NOT called

#### Scenario: notifier fires toast and sound when not focused

- GIVEN a `Notifier` with a `FocusChecker` returning `False`
- AND stubbed `ToastSender` and `SoundPlayer` recording calls
- WHEN `notifier.notify("generation_complete", "Listo")` is called
- THEN the toast sender receives `("generation_complete", "Listo")` exactly once
- AND the sound player receives `"generation_complete"` exactly once

### Requirement: `notifications_enabled` master toggle

When `BellbirdConfig.notifications_enabled` is `False`, the notifier
MUST NOT call the `ToastSender`. The `SoundPlayer` path is governed
independently by `sounds_enabled` and `sound_theme` (see below).

#### Scenario: notifications disabled silences toasts only

- GIVEN a `BellbirdConfig` with `notifications_enabled=False`,
  `sounds_enabled=True`, `sound_theme="default"`
- AND a `Notifier` with a `FocusChecker` returning `False`
  and stubbed `ToastSender` + `SoundPlayer`
- WHEN `notifier.notify("generation_complete", "Listo")` is called
- THEN the toast sender is NOT called
- AND the sound player IS called with `"generation_complete"`
  (sounds are independent of the toast master toggle)

#### Scenario: notifications enabled (default) fires toasts

- GIVEN a `BellbirdConfig` with `notifications_enabled=True`
  (the default)
- AND a `Notifier` with a `FocusChecker` returning `False`
- WHEN `notifier.notify("generation_complete", "Listo")` is called
- THEN the toast sender IS called

### Requirement: `sounds_enabled` master toggle and `sound_theme="none"`

When `BellbirdConfig.sounds_enabled` is `False`, the notifier MUST
NOT call the `SoundPlayer`. When `BellbirdConfig.sound_theme` is
`"none"`, the notifier MUST NOT call the `SoundPlayer` regardless of
`sounds_enabled`. Both checks happen INSIDE the notifier (not in
`SoundPlayer`); the contract is asserted at the dispatcher boundary.

#### Scenario: sounds disabled silences sound playback

- GIVEN a `BellbirdConfig` with `sounds_enabled=False`,
  `sound_theme="default"`
- AND a `Notifier` with a `FocusChecker` returning `False`
  and stubbed `ToastSender` + `SoundPlayer`
- WHEN `notifier.notify("generation_complete", "Listo")` is called
- THEN the sound player is NOT called
- AND the toast sender IS called (toasts independent of sound toggle)

#### Scenario: sound_theme="none" silences sound playback

- GIVEN a `BellbirdConfig` with `sound_theme="none"`,
  `sounds_enabled=True`
- AND a `Notifier` with a `FocusChecker` returning `False`
  and stubbed `ToastSender` + `SoundPlayer`
- WHEN `notifier.notify("generation_complete", "Listo")` is called
- THEN the sound player is NOT called
- AND the toast sender IS called

### Requirement: `SoundPlayer.play` looks up the event WAV

`core/sound_player.py::SoundPlayer` MUST resolve the event sound to
`data/sounds/<sound_theme>/<event>.wav`. The lookup is computed from
the `BellbirdConfig` fields at construction time (or via a per-call
arg) — the testable contract is: given theme and event, the resolved
path is `<sounds_dir>/<theme>/<event>.wav`. On `win32` with the file
present, `play()` calls `winsound.PlaySound(str(path), SND_FILENAME |
SND_ASYNC)`. On non-`win32`, on missing `winsound`, on missing file,
or on any internal error, `play()` is a silent no-op and MUST NOT
raise.

#### Scenario: SoundPlayer resolves the path from theme + event

- GIVEN a `SoundPlayer` with `sounds_dir=<tmp>/sounds`,
  `theme="default"`
- WHEN `sp._resolve("generation_complete")` runs
- THEN the result is `<tmp>/sounds/default/generation_complete.wav`

#### Scenario: missing file is a silent no-op

- GIVEN a `SoundPlayer` with `theme="default"`
  AND `<sounds_dir>/default/generation_complete.wav` does NOT exist
- AND `sys.platform == "win32"` with `winsound` available
  and `winsound.PlaySound` is a recording fake
- WHEN `sp.play("generation_complete")` is called
- THEN no exception is raised
- AND `winsound.PlaySound` is NOT called
- AND the call returns `None`

#### Scenario: existing file calls winsound.PlaySound on win32 [windows-only]

- GIVEN a `SoundPlayer` with `theme="default"`
  AND `<sounds_dir>/default/generation_complete.wav` IS a real file
- AND `sys.platform == "win32"` with `winsound.PlaySound` recorded
- WHEN `sp.play("generation_complete")` is called
- THEN `winsound.PlaySound` is called exactly once
- AND the first argument is the absolute path of the file
- AND the second argument includes the `SND_FILENAME` flag

#### Scenario: theme="none" skips the lookup and the playback

- GIVEN a `SoundPlayer` with `theme="none"`
- WHEN `sp.play("generation_complete")` is called
- THEN no `winsound.PlaySound` call is made
- AND no `Path.is_file()` check is made (fast-path: never even resolve the file)

#### Scenario: play on non-win32 is a silent no-op

- GIVEN `sys.platform != "win32"`
- AND a `SoundPlayer` with `theme="default"`
  AND the WAV file exists
- WHEN `sp.play("generation_complete")` is called
- THEN no exception is raised
- AND no audio backend call is attempted

#### Scenario: winsound missing or raising is a silent no-op

- GIVEN `sys.platform == "win32"` and `import winsound` raises `ImportError`
- WHEN `sp.play("generation_complete")` is called
- THEN no `ImportError` propagates
- AND the call returns `None`

### Requirement: `wx_notifier` wraps `wx.adv.NotificationMessage` line-local

`bellbird/ui/wx_notifier.py` SHALL provide a `WxToastSender` class
implementing the `ToastSender` protocol `(title: str, message: str,
timeout: int = 5) -> None`. It MUST import `wx.adv` line-local under
`sys.platform == "win32"`, wrapped in a `try/except ImportError` for
systems where `wx.adv` is missing. The toast class MUST be
`wx.adv.NotificationMessage` with the title set to the event name
and the message body set to the second arg; `Show(timeout=N)` is
called with a small non-zero timeout (e.g. 5 seconds). On any
non-`win32` platform, on missing `wx.adv`, on construction failure,
or on any `Show()` error, the call is a silent no-op.

#### Scenario: WxToastSender imports wx.adv line-local (regression guard)

- GIVEN the source of `bellbird/ui/wx_notifier.py`
- WHEN the AST test inspects the source
- THEN no `import wx.adv` and no `from wx.adv ...` line exists at module scope
- AND every `wx.adv` reference is inside a function body
- AND the enclosing function contains `if sys.platform == "win32":`

#### Scenario: WxToastSender shows the toast on win32 with wx.adv [windows-only]

- GIVEN `sys.platform == "win32"` and `wx.adv.NotificationMessage` is available
- AND a recording fake of the toast class
- WHEN `WxToastSender().show("generation_complete", "Listo", timeout=5)` is called
- THEN the fake toast is constructed with title `"generation_complete"`
  and body `"Listo"`
- AND `Show(timeout=...)` is called exactly once

#### Scenario: WxToastSender is a no-op on non-win32

- GIVEN `sys.platform != "win32"`
- WHEN `WxToastSender().show("generation_complete", "Listo", timeout=5)` is called
- THEN no exception is raised
- AND no `wx.adv` import is attempted

#### Scenario: WxToastSender swallows missing-wx.adv

- GIVEN `sys.platform == "win32"` and `wx.adv` raises `ImportError`
- WHEN `WxToastSender().show("generation_complete", "Listo", timeout=5)` is called
- THEN no `ImportError` propagates
- AND the call returns `None`

### Requirement: Six notifier event sites in `MainWindow`

`MainWindow` MUST instantiate exactly one `Notifier` in `__init__`,
bound to the lambda focus check, the `WxToastSender` toast sender, and
the `SoundPlayer`. The notifier MUST be invoked from exactly six
event sites, each after the existing in-window announcement:

| Event | Trigger site | Toast title | Toast body |
|---|---|---|---|---|
| `generation_complete` | `_on_done` | `"generation_complete"` | `"Respuesta completa"` |
| `server_ready` | `_on_start_server_done(ok=True)` | `"server_ready"` | `"Servidor listo"` |
| `model_loaded` | `_on_startup_probe_done` | `"model_loaded"` | `"Modelo cargado"` |
| `tool_request` | `_on_tool_request` (permission dialog open) | `"tool_request"` | `"Solicitud de herramienta"` |
| `error` | `_on_error` paths | `"error"` | `"Error"` |
| `error` | `_on_server_state_checked` (server watchdog, state=="dead") | `"error"` | `"Servidor caído"` |

The notifier MUST only be called when `is_focused` is `False` (the
dispatcher enforces this internally; the call sites do not double-
check). Reasoning paths (anything in `<think>…</think>` or
`delta.reasoning_content`) MUST NOT trigger a notifier call.

#### Scenario: _on_done fires generation_complete

- GIVEN a generation that just finished
- AND the focus checker reports `False` (window not focused)
- WHEN `_on_done` runs
- THEN `notifier.notify("generation_complete", "Respuesta completa")`
  is called exactly once
- AND `speech.speak("Respuesta completa")` is also called
  (the existing in-window announcement is preserved)

#### Scenario: _on_start_server_done fires server_ready on success

- GIVEN `LlamaRunner.start_server(...)` returned `ok=True`
- AND the focus checker reports `False`
- WHEN `_on_start_server_done(ok=True)` runs
- THEN `notifier.notify("server_ready", "Servidor listo")` is called

#### Scenario: _on_start_server_done is silent on failure

- GIVEN `LlamaRunner.start_server(...)` returned `ok=False`
- WHEN `_on_start_server_done(ok=False)` runs
- THEN `notifier.notify` is NOT called for `"server_ready"`
  (the existing error announcement path is used instead)

#### Scenario: _on_startup_probe_done fires model_loaded

- GIVEN the startup probe resolved with a loaded model
- AND the focus checker reports `False`
- WHEN `_on_startup_probe_done` runs
- THEN `notifier.notify("model_loaded", "Modelo cargado")` is called

#### Scenario: _on_tool_request fires tool_request

- GIVEN a tool permission request arrived
- AND the focus checker reports `False`
- WHEN `_on_tool_request` runs
- THEN `notifier.notify("tool_request", "Solicitud de herramienta")`
  is called

#### Scenario: _on_error fires error

- GIVEN an error event
- AND the focus checker reports `False`
- WHEN `_on_error` runs
- THEN `notifier.notify("error", "Error")` is called

#### Scenario: reasoning is never announced (regression guard)

- GIVEN the source of `bellbird/ui/main_window.py`
- WHEN the AST test searches for `notifier.notify` call sites
- THEN no call is made with an event name that appears in
  `delta.reasoning_content` / `<think>…</think>` parsing paths
- (The contract: the notifier is wired only to the six event
  sites listed above; no reasoning path can accidentally raise a
  notification.)
