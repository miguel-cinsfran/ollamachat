# Design: Audio Output (TTS on demand + SAPI + Notifications + Sounds)

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        MainWindow (wx.Frame)                        │
│                                                                     │
│  ┌─ ChatPanel ──────────────────────────────────────────────────┐   │
│  │  message_list (wx.ListBox)        get_selected_message_text() │   │
│  └───────────────────────────────────────────────────────────────┘   │
│                          │ F8                                        │
│                          ▼                                           │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  _on_read_selected_message()                                 │   │
│  │  1. gate: _is_generating? → "Generación en curso"            │   │
│  │  2. get_selected_message_text() → strip_markdown()            │   │
│  │  3. Speech.speak_with_system_voice(plain_text)               │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  5 event sites call Notifier.notify(event, msg)                    │
│  ┌─ Notifier (core/notifier.py) ────────────────────────────────┐   │
│  │  is_focused? → skip toast (sound optional)                   │   │
│  │  !focused? → toast + sound                                   │   │
│  │  │                                                          │   │
│  │  ├──▶ ToastSender ──── WxToastSender (ui/wx_notifier.py)    │   │
│  │  │     (wx.adv.NotificationMessage, line-local win32)       │   │
│  │  │                                                          │   │
│  │  └──▶ SoundPlayer ──── core/sound_player.py                 │   │
│  │        (winsound.PlaySound, line-local win32)               │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Data flow: F8 TTS on demand

```
User presses F8
  → MainWindow reads KEYMAP_DEFAULT["read_selected_message"] → wx.AcceleratorEntry
  → handler calls _on_read_selected_message()
  → gate: if _is_generating → speech.speak("Generación en curso"); return
  → get last_completed_assistant text OR chat_panel.message_list.GetSelection()
  → role, text = chat_panel.get_selected_message_text(index)
  → plain = text_utils.strip_markdown(text)
  → speech.speak_with_system_voice(plain)
    → SystemVoice.speak(text)  (SAPI SpVoice, line-local win32com)
    → never-interrupt (interrupt=False)
```

### Data flow: Background notifications

```
Event fires (server ready, generation done, error, tool_request, model loaded)
  → wx.CallAfter(MainWindow._on_*)
    → handler does existing work (speech announcement, UI update)
    → handler calls self._notifier.notify(event_name, summary)
       → Notifier.notify():
         if not self._notifications_enabled: return
         if self._focus_check():  # window not focused
           self._toast.show("Bellbird", summary)
         if self._sounds_enabled:
           self._sound.play(event_name)  # always (even when focused)
```

## 2. Module Contracts

### `core/system_voice.py` — `SystemVoice`

```python
class SystemVoice:
    def __init__(self, voice_name: str = "", rate: int = 0) -> None: ...

    @staticmethod
    def voices() -> list[str]:
        """List available SAPI voice names. Returns [] outside win32."""
        ...

    def set_voice(self, name: str) -> bool:
        """Set voice by name. Falls back to first available on miss."""
        ...

    def set_rate(self, rate: int) -> None:
        """Set rate (-10..+10). Clamped to SAPI range -10..+10."""

    def speak(self, text: str) -> None:
        """Blocking SAPI speak. No-op outside win32. Never raises."""

    def is_available(self) -> bool:
        """True when win32 + win32com loaded successfully."""
```

**Never-crash contract**: all public methods wrap COM calls in `try/except Exception: pass`. Outside win32, `speak()` and `set_voice()` are no-ops; `voices()` returns `[]`.

**Platform guard pattern** (mirror v0.7.0 `context_advisor.read_vram`):
```python
def speak(self, text: str) -> None:
    if sys.platform != "win32":
        return
    try:
        from win32com.client import Dispatch
        voice = Dispatch("SAPI.SpVoice")
        voice.Speak(text, 1)  # SVSFlagsAsync=1 for non-blocking
    except Exception:
        pass
```

**Testability hook**: TEST injects `mock.patch("bellbird.core.system_voice.sys.platform", "linux")` for no-op tests; OR patches `Dispatch` for win32-voice tests.

### `core/sound_player.py` — `SoundPlayer`

```python
class SoundPlayer:
    def __init__(self, sound_theme: str = "default") -> None:
        self._base = user_data_dir() / "sounds" / sound_theme
        ...

    def play(self, event: str) -> None:
        """Play <base>/<event>.wav async. Silent if file missing or non-win32."""
        ...
```

**Never-crash contract**: wraps `winsound.PlaySound` in `try/except`. `Path.is_file()` guard before play. No-op outside win32.

**Platform guard**: line-local `import winsound` inside `if sys.platform == "win32"` + `try/except`.

**Testability hook**: Tests mock `winsound.PlaySound` directly, or patch `sys.platform` to non-win32.

### `core/focus.py` — `FocusChecker` Protocol

```python
from typing import Protocol

class FocusChecker(Protocol):
    def is_focused(self) -> bool: ...
```

Minimal — just the protocol type alias. The production impl in `MainWindow` is `lambda: not self.IsActive()` (wx-native). On non-Windows, null impl always returns `False` (or `True`, depending on default behavior). Tests inject a stub.

### `core/notifier.py` — `Notifier`

```python
class Notifier:
    def __init__(
        self,
        focus_check: Callable[[], bool],
        toast_sender: object,  # ToastSender protocol
        sound_player: SoundPlayer,
        notifications_enabled: bool = True,
        sounds_enabled: bool = True,
    ) -> None: ...

    def notify(self, event: str, message: str) -> None:
        """Fire toast (if !focused) + play sound (always).
        Raises: never."""
        ...
```

**Never-crash contract**: wraps `toast_sender.show()` and `sound_player.play()` in `try/except`. If `notifications_enabled` is `False`, skips toast. If `sounds_enabled` is `False`, skips sound.

**Testability hook**: Tests pass stub `focus_check`, stub `ToastSender`, stub `SoundPlayer`, then assert calls.

### `ui/wx_notifier.py` — `WxToastSender`

```python
class WxToastSender:
    def __init__(self, parent: wx.Window) -> None: ...

    def show(self, title: str, message: str, timeout: int = 5) -> None:
        """Show a Windows toast notification. No-op outside win32."""
        ...
```

**Platform guard** (mirrors `_maybe_beep` in `main_window.py`):
```python
def show(self, title: str, message: str, timeout: int = 5) -> None:
    if sys.platform != "win32":
        return
    try:
        import wx.adv  # line-local
        notification = wx.adv.NotificationMessage(
            parent=self._parent, title=title, message=message,
        )
        notification.Show(timeout=timeout)
    except Exception:
        pass
```

**Testability hook**: AST test asserts `import wx.adv` is line-local. Runtime test: `importorskip("wx")` + calls `Show(0)` with try/except.

### `ui/voice_dialog.py` — `VoiceDialog`

```python
class VoiceDialog(wx.Dialog):
    def __init__(
        self, parent: wx.Window,
        voices: list[str], current_voice: str = "",
        current_rate: int = 0,
    ) -> None: ...

    def get_voice(self) -> str: ...
    def get_rate(self) -> int: ...
```

Returns `(voice_name, rate)` on OK. All controls have `name=` + preceding `wx.StaticText`. Uses `wx.Choice` for voices + `wx.Slider` for rate. Tested via AST + `importorskip("wx")` runtime.

## 3. Config Schema Delta

New fields in `BellbirdConfig.__init__`, inserted after `v0.9.0` fields (`pre_send_warn` at line 52):

```python
# v0.10.0: audio output (TTS + SAPI + notifications + sounds)
system_voice_name: str = ""          # empty = first available
system_voice_rate: int = 0           # -10..+10, validated in dialog
auto_speak_responses: bool = False   # OFF by default (never auto)
notifications_enabled: bool = True   # master toast toggle
sounds_enabled: bool = True          # master sound toggle
sound_theme: str = "default"         # subdir of data/sounds/; "none" = no playback
```

Forward-compat works automatically via `__dataclass_fields__` filter in `load_config` (lesson v0.8.2). No migration entry needed.

## 4. Keymap Delta

In `bellbird/core/keymap.py`:

```python
_WXK_F8 = 346  # add to module-level constants (lines 29-34)

# Add to _KEYCODE_LABELS dict (line 44-45):
_WXK_F8: "F8",

# Add to DEFAULT_KEYMAP (line 294, after "attach_url"):
"read_selected_message": Binding(KEYMAP_MOD_NONE, _WXK_F8, "F8"),
```

In `bellbird/ui/preferences_dialog.py`, add to `_ACTION_LABELS`:
```python
"read_selected_message": "Leer mensaje seleccionado",
```

In `bellbird/ui/main_window.py`, add to `handlers` dict in `_build_accelerators`:
```python
"read_selected_message": lambda: self._on_read_selected_message(),
```

Auto-registration: the Atajos tab (lesson v0.8.0) and `_show_shortcuts` discover the entry automatically — zero extra code.

## 5. UI Changes

### Audio tab in PreferencesDialog

New page `_build_audio_page()` (after `_build_keymap_page`, before `_build_status_page`):

**Layout** (vertical BoxSizer, 4 groups, no grid sizers):

1. **"Voz del sistema" group**:
   - `wx.StaticText("Voz:")` + `wx.Choice(name="pref_system_voice_choice")` (populated lazily via `SystemVoice.voices()`)

     (Naming follows the existing `pref_*_choice` convention used
     throughout the dialog — e.g. `pref_*_checkbox`, `pref_*_spin`.)
   - `wx.Button("Probar", name="voice_test_button")` — plays a test phrase
   - `wx.Button("Seleccionar voz...", name="voice_select_button")` — opens VoiceDialog
   - `wx.StaticText("Velocidad:")` + `wx.Slider(min=-10, max=10, name="voice_rate_slider")` + `wx.StaticText(value_label)`

2. **"Lectura automática" group**:
   - `wx.CheckBox("Leer respuestas automáticamente con la voz del sistema", name="auto_speak_checkbox")`
   - Default: unchecked

3. **"Notificaciones" group**:
   - `wx.CheckBox("Notificaciones del sistema", name="notifications_checkbox")` (default: checked)
   - `wx.CheckBox("Sonidos", name="sounds_checkbox")` (default: checked)
   - `wx.StaticText("Tema de sonido:")` + `wx.Choice(["default", "none"], name="sound_theme_choice")`

4. Stretch spacer at bottom.

All `wx.Slider` changes update their value label via `EVT_SLIDER` (same pattern as `_on_slider_change` in existing dialog).

### VoiceDialog

`wx.Dialog(name="voice_dialog", title="Seleccionar voz")`:

```
wx.StaticText("Voz:")
wx.Choice(voices, name="voice_choice")

wx.StaticText("Velocidad:")
wx.Slider(min=-10, max=10, name="voice_rate_slider")
wx.StaticText(rate_value, name="rate_value_label")

[Academia [Aceptar]]  [Cancelar]
```

Returns `(voice_name, rate)` on OK. Slider updates label on `EVT_SLIDER`.

### Keymap auto-registration

The new `read_selected_message` action id appears in the Atajos tab (lesson v0.8.0) and `_show_shortcuts` automatically — no code needed in those surfaces.

## 6. Notifier Wiring in `main_window.py`

| Event site | After line | Insert |
|---|---|---|
| `_on_done()` — after `self._speech.speak("Respuesta completa", interrupt=True)` (line 1565) | After existing speech, before save | `self._notifier.notify("generation_complete", "Respuesta completa")` |
| `_on_start_server_done()` — after `self._speech.speak(message, interrupt=True)` (line 983) | After existing speech, end of method | `if ok: self._notifier.notify("server_ready", "Servidor listo")` |
| `_on_error()` / watchdog `_on_server_state_checked` — when state == "dead" (line 1838-1841) | After `self._speech.speak("El servidor se detuvo...")` | `self._notifier.notify("error", "Servidor caído")` |
| `_on_tool_call()` — after `self._speech.speak("El modelo quiere ejecutar un comando...")` (line 1621-1624) | After the speech, before `PermissionDialog` | `self._notifier.notify("tool_request", "El modelo quiere ejecutar un comando")` |
| `_on_startup_probe_done()` — when loaded model is available (line 1111) | After `self._speech.output(f"Modelo:...")` | `self._notifier.notify("model_loaded", Path(loaded).stem)` |

## 7. Concurrency & Threading

All Notifier calls happen on the main thread (they are in `wx.CallAfter` callbacks or event handlers already). No new threads needed.

| Component | Thread safety | Notes |
|---|---|---|
| `SystemVoice.speak()` (SAPI) | Synchronous, main-thread only | SAPI `SpVoice.Speak` is blocking; short messages (< 200 chars) complete in < 500 ms |
| `SoundPlayer.play()` (`winsound.PlaySound`) | Async by design | `SND_ASYNC` flag; returns immediately |
| `WxToastSender.show()` (`wx.adv.NotificationMessage`) | wx widget — main thread only | Always called from existing wx.CallAfter paths |

## 8. Sound Assets

**Minimum-viable approach**: ship 1 tiny `beep.wav` (~50 ms, 880 Hz, 8-bit mono) copied 5 times. The apply phase generates them.

**Theme directory**: `bellbird/data/sounds/default/` (resolved via `user_data_dir()`). Theme name `"none"` is a sentinel — no folder needed, `SoundPlayer.play()` returns immediately.

**Exact file paths** (generated at apply time):
```
data/sounds/default/generation_complete.wav   ← beep.wav copy
data/sounds/default/server_ready.wav          ← beep.wav copy
data/sounds/default/error.wav                 ← beep.wav copy (can be different later)
data/sounds/default/tool_request.wav          ← beep.wav copy
data/sounds/default/model_loaded.wav          ← beep.wav copy
```

`data/` is gitignored — assets are generated at apply time, not committed.

**Sourcing decision**: base64-decode a tiny embedded WAV in the apply script (option a in §12). Pure stdlib, no runtime dependency.

## 9. Wiring in `MainWindow.__init__`

Order (after `self._speech = Speech()` at line 116):

```python
# Audio output subsystems (v0.10.0)
self._sound_player = SoundPlayer(sound_theme=self._config.sound_theme)
self._system_voice = SystemVoice(
    voice_name=self._config.system_voice_name,
    rate=self._config.system_voice_rate,
)
# Toast sender (Windows-only, null outside win32)
if sys.platform == "win32":
    from bellbird.ui.wx_notifier import WxToastSender
    self._toast = WxToastSender(parent=self)
else:
    self._toast = _NullToastSender()  # inner class, no-op
# Notifier orchestrator
from bellbird.core.notifier import Notifier
self._notifier = Notifier(
    focus_check=lambda: not self.IsActive(),
    toast_sender=self._toast,
    sound_player=self._sound_player,
    notifications_enabled=self._config.notifications_enabled,
    sounds_enabled=self._config.sounds_enabled,
)
```

`_NullToastSender` is a private class with `def show(self, title, message, timeout=5): pass`.

## 10. Workload Forecast & WU Split

Per proposal (lesson v0.8.2 "split when >= 400 lines or 5+ UI tasks"):

| WU | Scope | Files | Est. LOC | wx? |
|---|---|---|---|---|
| **WU-1** (core + tests) | `system_voice.py`, `notifier.py`, `focus.py`, `sound_player.py`, `speech.py` extend, `config.py` 6 fields, `keymap.py` 1 entry, `tests/core/*` new files | ~8 files | ~400-500 | No |
| **WU-2** (ui + wx-tests) | `voice_dialog.py`, `wx_notifier.py`, preferences Audio tab, main_window notifier wiring + `_on_read_selected_message`, `_ACTION_LABELS`, `chat_panel.get_selected_message_text`, AST/runtime tests, `run_tests.bat`, `pyproject.toml`, WAV assets | ~10 files | ~350-450 | Yes |

Total: ~750-950 lines (within budget). WU-2 can be further split if needed (voice dialog + keymap first; notifier wiring second).

## 11. Risks & Mitigations

| # | Risk | Mitigation |
|---|---|---|
| R1 | `win32com.client` missing on non-Windows | Line-local `import`, `sys.platform` guard, no-op fallback |
| R2 | `winsound.PlaySound` raises for corrupt/missing WAV | `Path.is_file()` + `try/except` |
| R3 | `wx.adv` not available on all wx builds | Line-local `import wx.adv` in `try/except`; AST test asserts guard |
| R4 | SAPI voice disappears after being configured | `set_voice("")` fallback to first available; log warning |
| R5 | Sounds fire during focused app (annoying) | Per spec: sounds always fire (subtle); toasts only when `!IsActive()` |
| R6 | Audio tab grows with Change B | Keep this change audio-only; Change B extends or adds a tab |
| R7 | `wx.adv.NotificationMessage` may trigger Windows "First time?" UAC | Runtime test calls `.Show(0)` only; not asserting on user-visible outcome |
| R8 | Audio tab vertical space with 4 groups | Use `AddStretchSpacer()` at bottom; `wx.ScrolledWindow` if needed (unlikely at 4 groups) |
| R9 | SAPI + NVDA speech collision when auto-speak is ON | Auto is OFF by default; risk only exists when user explicitly enables it |

## 12. Open Question for Apply Phase

**WAV asset sourcing**: how to produce the 5 identical `.wav` files:

- **(a) Embedded base64**: encode a 50ms 880Hz 8-bit mono WAV as a base64 literal in the apply script, decode and write 5 copies. Pure stdlib (`base64`, `wave`, `struct`), no dependencies.
- **(b) Runtime synthesis**: generate at first run using `winsound.Beep` + record (not feasible — `Beep` doesn't produce WAV files).

**Recommendation**: (a). The apply step writes a helper `_generate_beep_wavs()` that decodes the embedded base64 and writes all 5 files. Around 30 lines, pure Python stdlib, deterministic, testable.

---

## Summary

- **Approach**: Add SAPI TTS on demand (F8), toast notifications (unfocused only), and per-event sound cues — all optional, all silent outside win32.
- **Key Decisions**: 4 new modules (SystemVoice, Notifier, SoundPlayer, FocusChecker), 2 new UI modules (VoiceDialog, WxToastSender), 1 new Preferences tab, 5 notifier event sites.
- **Files Affected**: 9 new + 7 modified + ~250-350 new test LOC.
- **Testing Strategy**: Core modules fully unit-tested on WSL (platform guards + no-ops + stubs). UI modules AST-tested + `importorskip("wx")` runtime, registered in `run_tests.bat`.
