# System Voice Capability Specification

## Purpose

Defines `SystemVoice`, the wx-free wrapper around the Windows SAPI
(`SAPI.SpVoice` via `win32com.client`) that gives Bellbird an on-demand
OS-level TTS channel — independent of the screen reader, used for
explicit re-reads of selected messages and any future button-bound
utterances. The module MUST degrade to a silent no-op on any platform
that is not `win32`, and on `win32` systems where `pywin32` is not
installed. The class is deliberately minimal: voice list, voice
selection, rate control, and a single `speak` method. All wx surface
(voice picker dialog) lives in `ui/voice_dialog.py` and reuses this
module's API.

The system voice is **supplementary** to the screen reader. It MUST
never interrupt screen-reader speech and MUST only fire from explicit
user actions (keypress, button). Auto-read is a config flag that
defaults to `False`; the screen reader is the live channel during
generation. The class MUST not import `wx` at module scope (AST guard).

## Requirements

### Requirement: Module has no `wx` dependency (regression guard)

`bellbird/core/system_voice.py` MUST NOT import `wx` at module scope.
A static AST test asserts the source contains no `import wx` and no
`from wx ...` statement. `win32com.client` MUST be imported line-local
inside `speak()` only, under an `if sys.platform == "win32":` guard,
wrapped in a `try/except ImportError` so a missing `pywin32` install
downgrades to a silent no-op.

#### Scenario: No `wx` import at module scope (regression guard)

- GIVEN the source of `bellbird/core/system_voice.py`
- WHEN the AST test inspects the top-level imports
- THEN no `import wx` and no `from wx ...` line exists

#### Scenario: `win32com.client` is imported line-local under `win32` guard

- GIVEN the source of `bellbird/core/system_voice.py`
- WHEN the AST test locates `win32com` references
- THEN every occurrence is inside a function body
- AND the enclosing function contains `if sys.platform == "win32":`
- AND the import is inside a `try/except ImportError` block

### Requirement: `voices()` returns the SAPI voice list

`SystemVoice.voices() -> list[str]` MUST return the names of the SAPI
voices available on the current machine. On `win32` + `pywin32`
installed, it queries the live `SAPI.SpVoice.GetVoices()` collection
and returns each voice's `GetDescription()` as a `str`. On
`win32` + `pywin32` missing, it returns `[]` (the missing dependency
is a silent downgrade, not an error). On any non-`win32` platform,
it returns `[]` without importing `win32com`.

#### Scenario: voices() on win32 with pywin32 [windows-only]

- GIVEN a `win32` platform and a stubbed `win32com.client.Dispatch`
  that returns an object with `GetVoices()` returning two fake voices
  named `"Microsoft Helena"` and `"Microsoft Sabina"`
- WHEN `SystemVoice().voices()` is called
- THEN the result is `["Microsoft Helena", "Microsoft Sabina"]`
- AND no exception is raised

#### Scenario: voices() on non-win32 returns empty list

- GIVEN `sys.platform != "win32"`
- WHEN `SystemVoice().voices()` is called
- THEN the result is `[]`
- AND no `ImportError` propagates

#### Scenario: voices() on win32 without pywin32 returns empty list

- GIVEN `sys.platform == "win32"` and `import win32com` raises `ImportError`
- WHEN `SystemVoice().voices()` is called
- THEN the result is `[]`
- AND no exception propagates

### Requirement: `set_voice` selects a voice and validates input

`SystemVoice.set_voice(name: str) -> bool` MUST attempt to set the
active SAPI voice to the given name. It MUST return `True` on success
and `False` on failure. Failure modes are: (a) non-`win32` platform,
(b) `pywin32` not installed, (c) `name` is empty, (d) `name` does
not match any voice from `voices()`. On failure, the previously-set
voice MUST be unchanged.

#### Scenario: set_voice succeeds for a valid voice [windows-only]

- GIVEN a `SystemVoice` whose `voices()` returns `["Microsoft Helena", "Microsoft Sabina"]`
- WHEN `sv.set_voice("Microsoft Helena")` is called
- THEN the return value is `True`
- AND the active voice is `"Microsoft Helena"`

#### Scenario: set_voice returns False for unknown voice (regression guard)

- GIVEN a `SystemVoice` whose `voices()` returns `["Microsoft Helena"]`
- AND a previously-set voice `"Microsoft Helena"`
- WHEN `sv.set_voice("nonexistent")` is called
- THEN the return value is `False`
- AND the active voice is still `"Microsoft Helena"`
  (the previously-set voice is unchanged)

#### Scenario: set_voice on non-win32 returns False

- GIVEN `sys.platform != "win32"`
- WHEN `SystemVoice().set_voice("Microsoft Helena")` is called
- THEN the return value is `False`
- AND no exception propagates

#### Scenario: set_voice("") returns False (empty = no-op)

- GIVEN any `SystemVoice`
- WHEN `sv.set_voice("")` is called
- THEN the return value is `False`
  (empty string is not a valid voice name; the caller uses the
  configured default instead)

### Requirement: `set_rate` clamps to the SAPI-documented range

`SystemVoice.set_rate(rate: int) -> None` MUST set the SAPI voice
rate. It MUST clamp the input to the documented SAPI range
`[-10, +10]`. Values below `-10` are clamped to `-10`; values above
`+10` are clamped to `+10`. The method MUST be a no-op on
non-`win32` platforms and on `win32` without `pywin32`.

#### Scenario: set_rate clamps below the lower bound

- GIVEN a `SystemVoice` on `win32` with `pywin32` available
- WHEN `sv.set_rate(-20)` is called
- THEN the effective SAPI rate is `-10`
- AND no exception propagates

#### Scenario: set_rate clamps above the upper bound

- GIVEN a `SystemVoice` on `win32` with `pywin32` available
- WHEN `sv.set_rate(50)` is called
- THEN the effective SAPI rate is `10`
- AND no exception propagates

#### Scenario: set_rate accepts in-range value verbatim [windows-only]

- GIVEN a `SystemVoice` on `win32`
- WHEN `sv.set_rate(2)` is called
- THEN the effective SAPI rate is `2`

#### Scenario: set_rate on non-win32 is a no-op

- GIVEN `sys.platform != "win32"`
- WHEN `SystemVoice().set_rate(2)` is called
- THEN no exception propagates
- AND no SAPI state is touched

### Requirement: `speak` plays text through SAPI on win32 only

`SystemVoice.speak(text: str) -> None` MUST speak the given text
through the active SAPI voice. It MUST only call SAPI on `win32`
with `pywin32` available. On any other platform, on missing
`pywin32`, on a silent `Speech` instance, or on any internal SAPI
error, the call MUST be a no-op and MUST NOT propagate any exception
(`ImportError`, `OSError`, `com_error`, etc.).

#### Scenario: speak calls SAPI on win32 [windows-only]

- GIVEN a `SystemVoice` on `win32` with `pywin32` available
  and a stubbed `SAPI.SpVoice` recording `Speak` calls
- WHEN `sv.speak("hola")` is called
- THEN the stubbed voice records `Speak("hola")` exactly once

#### Scenario: speak on non-win32 is a silent no-op

- GIVEN `sys.platform != "win32"`
- WHEN `SystemVoice().speak("hola")` is called
- THEN no exception propagates
- AND no SAPI call is attempted

#### Scenario: speak with missing pywin32 catches ImportError

- GIVEN `sys.platform == "win32"` and `import win32com` raises `ImportError`
- WHEN `SystemVoice().speak("hola")` is called
- THEN no `ImportError` propagates
- AND the call returns `None`

#### Scenario: speak swallows mid-call SAPI errors

- GIVEN a stubbed SAPI voice whose `Speak` raises `OSError`
- WHEN `sv.speak("hola")` is called
- THEN no exception propagates
- AND the call returns `None`

#### Scenario: speak with non-string text is a safe no-op

- GIVEN any `SystemVoice`
- WHEN `sv.speak(None)` is called
- THEN no exception propagates
- AND no SAPI call is attempted
