# Speech Capability Specification

## Purpose

Defines `Speech`, the headless wrapper around
`accessible_output2.outputs.auto.Auto` that gives OllamaChat its voice. The
module exists for ONE reason: the TTS layer is the least reliable dependency
on Windows, WSL, CI, and locked-down user machines. `Speech` MUST therefore
swallow every exception and degrade to silent no-ops so the app NEVER crashes
because speech failed. Token-chunk buffering prevents the screen reader from
being drowned by one-syllable fragments.

## Requirements

### Requirement: Constructor — Never-Crash Initialization

`Speech.__init__` MUST try `from accessible_output2.outputs.auto import Auto`
followed by `Auto()`. If ANY exception is raised (ImportError, OSError,
RuntimeError, anything), the constructor MUST catch it, set `self._output =
None`, and the instance MUST still be usable (all methods become no-ops). The
constructor MUST NOT re-raise.

#### Scenario: accessible_output2 available

- GIVEN a stubbed `accessible_output2.outputs.auto` module whose `Auto()`
  returns a fake `output` object
- WHEN `Speech()` is instantiated
- THEN `speech._output is not None`
- AND `speech.is_silent` is `False`

#### Scenario: accessible_output2 ImportError

- GIVEN a stubbed import that raises `ImportError("No module named
  accessible_output2")`
- WHEN `Speech()` is instantiated
- THEN the constructor does NOT raise
- AND `speech._output is None`
- AND `speech.is_silent` is `True`

#### Scenario: Auto() raises OSError

- GIVEN `Auto()` raises `OSError("No TTS engine")`
- WHEN `Speech()` is instantiated
- THEN the constructor does NOT raise
- AND `speech.is_silent` is `True`

### Requirement: `speak` Method

`Speech.speak(text, interrupt=True)` MUST delegate to
`self._output.speak(text, interrupt=interrupt)` when `_output` is not `None`.
When `_output` is `None`, it MUST be a silent no-op. The method MUST NOT
raise, regardless of `text` type or content.

#### Scenario: Speak with output available

- GIVEN a `Speech` instance with a fake `output` recording calls
- WHEN `speech.speak("Hola", interrupt=True)` is called
- THEN the fake output records `output.speak("Hola", interrupt=True)` exactly
  once

#### Scenario: Speak when silent

- GIVEN a `Speech` instance with `_output is None`
- WHEN `speech.speak("Hola")` is called
- THEN no exception is raised
- AND no side effect occurs

#### Scenario: Speak with non-string text

- GIVEN any `Speech` instance
- WHEN `speech.speak(None)` is called
- THEN no exception is raised
- AND the method returns `None`

### Requirement: `output` Method (Voice + Braille)

`Speech.output(text)` MUST delegate to `self._output.output(text)` when
`_output` is not `None`. When `_output` is `None`, it MUST be a silent no-op.
The method MUST NOT raise.

#### Scenario: Output when available

- GIVEN a fake `output` recording calls
- WHEN `speech.output("Línea en braille")` is called
- THEN the fake output records `output.output("Línea en braille")` exactly
  once

#### Scenario: Output when silent

- GIVEN a silent `Speech` instance
- WHEN `speech.output("texto")` is called
- THEN no exception is raised

### Requirement: `stop` Method

`Speech.stop()` MUST delegate to `self._output.stop()` (or equivalent
interrupt API) when `_output` is not `None`. When `_output` is `None`, it MUST
be a silent no-op. The method MUST NOT raise.

#### Scenario: Stop when available

- GIVEN a fake `output` recording calls
- WHEN `speech.stop()` is called
- THEN the fake output records a stop call exactly once

#### Scenario: Stop when silent

- GIVEN a silent `Speech` instance
- WHEN `speech.stop()` is called
- THEN no exception is raised

### Requirement: Token Chunk Buffering

`Speech.announce_token_chunk(token)` MUST append `token` to an internal
buffer. It MUST flush and speak the buffer if the buffer now contains any
sentence terminator (`.`, `?`, `!`, or newline `\n`) OR if the buffer length
exceeds 80 characters. On flush, the buffer is cleared and a single
`self.speak(flushed_text, interrupt=False)` call is made.

#### Scenario: Short token — no flush

- GIVEN a fresh `Speech` instance
- WHEN `speech.announce_token_chunk("Ho")` is called
- THEN no `speak` call is made
- AND `speech._buffer == "Ho"`

#### Scenario: Sentence terminator triggers flush

- GIVEN the buffer is `"Hola."`
- WHEN `speech.announce_token_chunk("")` is called
- THEN `speak` is called with `"Hola."` and `interrupt=False`
- AND `speech._buffer == ""`

#### Scenario: 80-char fallback flush

- GIVEN a fresh `Speech` instance
- WHEN `speech.announce_token_chunk("a" * 81)` is called
- THEN `speak` is called with the 81-char string
- AND `speech._buffer == ""`

#### Scenario: Question mark flushes

- GIVEN the buffer is `"¿Qué tal"`
- WHEN `speech.announce_token_chunk("?")` is called
- THEN `speak` is called with `"¿Qué tal?"`
- AND `speech._buffer == ""`

#### Scenario: Newline in middle flushes

- GIVEN the buffer is `"primera línea"`
- WHEN `speech.announce_token_chunk("\n")` is called
- THEN `speak` is called with `"primera línea\n"`
- AND `speech._buffer == ""`

### Requirement: `flush_token_buffer` Method

`Speech.flush_token_buffer()` MUST speak the current buffer (if non-empty)
with `interrupt=False`, then clear the buffer. The method MUST NOT raise.

#### Scenario: Flush non-empty buffer

- GIVEN `speech._buffer == "fragmento pendiente"`
- WHEN `speech.flush_token_buffer()` is called
- THEN `speak` is called with `"fragmento pendiente"` and `interrupt=False`
- AND `speech._buffer == ""`

#### Scenario: Flush empty buffer is a no-op

- GIVEN `speech._buffer == ""`
- WHEN `speech.flush_token_buffer()` is called
- THEN no `speak` call is made
- AND no exception is raised

### Requirement: Never-Crash Guarantee

Every public method of `Speech` (`speak`, `output`, `stop`,
`announce_token_chunk`, `flush_token_buffer`) MUST catch all exceptions
internally and return `None`. A `Speech` instance in silent mode MUST be
indistinguishable from a working one to the caller, except that no audible
output occurs.

#### Scenario: Output raises mid-call

- GIVEN a fake `output.output` that raises `RuntimeError`
- WHEN `speech.output("texto")` is called
- THEN no exception propagates
- AND the call returns `None`

#### Scenario: Speak raises mid-call

- GIVEN a fake `output.speak` that raises `OSError`
- WHEN `speech.speak("texto")` is called
- THEN no exception propagates
- AND the call returns `None`

## Added in v0.3.0

### Requirement: Generation-Beep Announcements Use Existing `speak`

The generation-progress beep (see `app-shell` delta) MUST be implemented exclusively via `winsound.Beep` — NOT via `Speech.speak`. Beeps and spoken announcements are coordinated by `MainWindow._maybe_beep()` independently of the speech engine; a silent `Speech` instance MUST NOT prevent the beep from firing on Windows.

#### Scenario: Silent speech engine does not block beep

- **GIVEN** a `Speech` instance with `is_silent is True`
- **AND** `sys.platform == "win32"`
- **WHEN** `_maybe_beep()` is called
- **THEN** `winsound.Beep(520, 50)` is invoked
- **AND** no call is made to `speech.speak`

### Requirement: F2 Session Status Uses `speak` With `interrupt=True`

`MainWindow._announce_session_status` (F2) MUST compose a single multi-clause string (model, server status, message count, token count, temperature, top_p, generating flag) and emit it through the existing `speech.speak(..., interrupt=True)` path. The composed string MUST use Spanish decimal notation (comma, not period) for numeric values. No new public method is added to `Speech`.

#### Scenario: F2 uses existing speak

- **GIVEN** a `Speech` instance with a fake `output`
- **WHEN** `_announce_session_status` runs
- **THEN** `output.speak` is called exactly once
- **AND** the argument is a single string (not a list of calls)
- **AND** `interrupt=True` is passed

#### Scenario: Spanish number formatting

- **GIVEN** temperature is `0.7` and top_p is `0.9`
- **WHEN** `_announce_session_status` composes the string
- **THEN** the string contains `"0,70"` (or `"1,30"` if slider is 130)
- **AND** the string contains `"0,90"`
- **AND** no `0.7` / `0.9` period-style floats appear in the spoken text

### Requirement: Loading Announcements Use `interrupt=False`

`MainWindow` background-loader timer MUST call `speech.speak("Cargando modelo, por favor espera...", interrupt=False)` on each 8-second tick. The `interrupt=False` flag is required so the announcement does not cut off streaming speech from a previous generation; a silent `Speech` MUST remain a no-op per the existing `speak` contract.

#### Scenario: Loading announcement does not interrupt

- **GIVEN** a generation is in progress (streaming speech active)
- **WHEN** the 8-second loading timer fires
- **THEN** `speech.speak(..., interrupt=False)` is called
- **AND** any in-progress spoken output is NOT cut off
