# Delta for `speech` — v0.11.0 (preferences-hints-presets-reading) [OPTIONAL]

> **Provenance**: `openspec/changes/2026-06-25-preferences-hints-presets-reading/proposal.md`
> § 4.4 (Pestaña "Lectura") — the proposal marks
> `Speech.speak_with_system_voice` integration of `apply_filters`
> as a **SUGGESTION, not CRITICAL** (proposal R3: "Audio = voz
> del sistema + notificaciones + sonidos; Lectura = filtros de
> TTS (text shaping). Complementary, not duplicate"). The
> `Speech.speak` channel (the live screen-reader path) is
> **NOT** touched — applying filters there would break
> streaming per the v0.6.0 lesson. All scenarios in this delta
> are marked `[optional]` — they describe the desired
> behavior IF the verify step decides to wire the integration;
> if NOT wired, the spec is informational only (the 4
> `filter_strip_*` toggles are persisted but not yet applied
> to the system-voice channel).
>
> Cross-references: `text-filters` capability (the
> `apply_filters` function this delta references), the
> v0.10.0 `speak_with_system_voice` requirement (this delta
> is additive only).

## Added in v0.11.0 (preferences-hints-presets-reading) [OPTIONAL]

### Requirement: `speak_with_system_voice` may apply filters before delegating [optional]

`Speech.speak_with_system_voice(text: str, system_voice:
object, config: BellbirdConfig | None = None) -> None` MAY,
when the optional `config` argument is provided, call
`apply_filters(text, config)` and pass the filtered result to
`system_voice.speak(...)` instead of the raw input. The
never-crash contract of `Speech` (v0.10.0) MUST be preserved:
any exception from `apply_filters` or `system_voice.speak` is
caught, the call returns `None`, and no exception propagates.
The `config` argument defaults to `None` for backward
compatibility with the v0.10.0 two-argument call sites; when
`None`, the function MUST behave identically to the v0.10.0
version (raw text → `system_voice.speak(text)`).

(If the verify step decides NOT to wire this integration, this
requirement is informational and the call sites in
`MainWindow` continue to pass the raw text. The 4
`filter_strip_*` toggles are persisted but unused on the
system-voice channel — the screen-reader channel
`Speech.speak` is unaffected either way.)

#### Scenario: `config=None` preserves the v0.10.0 behavior [optional] [regression guard]

- GIVEN `Speech.speak_with_system_voice("**bold** 👋", system_voice)` (no `config` argument)
- WHEN the function runs
- THEN `_system_voice.speak("**bold** 👋")` is called with the RAW text (no filter applied)
- AND no exception propagates
- AND the call returns `None`

#### Scenario: `config=BellbirdConfig()` (all ON) applies filters before delegating [optional]

- GIVEN `Speech.speak_with_system_voice("**bold** https://x.com 👋 ```code```", system_voice, BellbirdConfig())` (all 4 toggles ON)
- WHEN the function runs
- THEN `apply_filters` is called with the input text and the config
- AND `_system_voice.speak(filtered_text)` is called with the filtered result (no `**`, no `https://`, no emoji, no triple backticks)
- AND no exception propagates

#### Scenario: `config=BellbirdConfig()` with all toggles OFF is a pass-through [optional]

- GIVEN `BellbirdConfig(filter_strip_markdown=False, filter_strip_urls=False, filter_strip_emojis=False, filter_strip_code_blocks=False)`
- AND `Speech.speak_with_system_voice("**bold** https://x.com 👋", system_voice, cfg)` is called
- WHEN the function runs
- THEN `_system_voice.speak("**bold** https://x.com 👋")` is called with the RAW text (`apply_filters` returned the input unchanged)
- AND no exception propagates

#### Scenario: `apply_filters` raising is swallowed (never-crash contract) [optional]

- GIVEN a `BellbirdConfig` whose `filter_strip_*` access raises `AttributeError` (defensive test)
- WHEN `Speech.speak_with_system_voice(text, system_voice, cfg)` is called
- THEN no exception propagates
- AND the call returns `None` (the `apply_filters` failure is silently swallowed, same as `system_voice.speak` failures)

#### Scenario: `Speech.speak` (live screen-reader) is NOT modified [optional] [regression guard]

- GIVEN a `Speech` instance with a fake `_output`
- WHEN `Speech.speak("**bold**", interrupt=True)` is called (the v0.10.0 screen-reader method)
- THEN `_output.speak("**bold**", interrupt=True)` is called with the RAW text
- AND no `apply_filters` call is made
- AND the live streaming channel is unaffected (v0.6.0 lesson: do NOT break streaming)

#### Scenario: `auto_speak_responses=False` still does not auto-fire [optional] [regression guard]

- GIVEN `Speech` with `auto_speak_responses=False` (v0.10.0 default)
- AND a generation completes
- WHEN `_on_done` runs
- THEN `_system_voice.speak` is NOT called automatically (the v0.10.0 contract is preserved)
- AND `output.speak("Respuesta completa")` IS called (the screen-reader announcement is unchanged)

## Test strategy

- WSL: add `tests/core/test_speech_filter_integration.py` (OPTIONAL
  class) — verifies the `config=None` pass-through and the
  never-crash contract. If the integration is NOT wired, the
  test class is a no-op stub that asserts the v0.10.0
  behavior is preserved.
- Windows (`run_tests.bat` wx-runtime block): no new tests
  (the integration is a `core/` change, not a UI change).
