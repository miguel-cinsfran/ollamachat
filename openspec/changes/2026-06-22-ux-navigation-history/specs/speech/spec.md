# speech Spec — Delta for v0.3.0

## Purpose

Documents the new generation-beep cross-reference and the F2 session-status announcement that compose existing `Speech` primitives. The `Speech` class itself does not gain new public methods in v0.3.0 — the beep and the F2 status are coordinated by `app-shell` and `accessibility-guidelines` respectively. This delta records the call-shape expectations for those orchestration sites.

## ADDED Requirements

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
