# App Configuration Capability Specification — v0.10.0 Delta

<!-- v0.10.0 audio-output-tts-notifications: 6 new fields on BellbirdConfig. Forward-compat — no migration entry needed. -->

This delta appends six new fields to the existing `BellbirdConfig`
shape defined in `openspec/specs/app-configuration/spec.md`. All
fields are additive (no removal, no rename) and use the documented
default as the post-change value. The existing `__dataclass_fields__`
filter in `load_config` preserves forward-compat automatically: a
reverted build that does not know these fields drops them silently
and the saved JSON re-loads with the new defaults.

## ADDED Requirements

### Requirement: Audio Output Fields (v0.10.0)

`BellbirdConfig` MUST gain the following six fields, all
additive:

| Field | Type | Default | Notes |
|---|---|---|---|
| `system_voice_name` `[v0.10.0]` | `str` | `""` | SAPI voice name; `""` = first available. |
| `system_voice_rate` `[v0.10.0]` | `int` | `0` | SAPI rate, range `[-10, +10]`; the voice dialog validates the slider bounds. |
| `auto_speak_responses` `[v0.10.0]` | `bool` | `False` | **Off by default** — never auto-reads. Only explicit F8 (or a future button) calls `speak_with_system_voice`. |
| `notifications_enabled` `[v0.10.0]` | `bool` | `True` | Master toast toggle (see `notifications` spec). |
| `sounds_enabled` `[v0.10.0]` | `bool` | `True` | Master sound-cue toggle. |
| `sound_theme` `[v0.10.0]` | `str` | `"default"` | Subdir of `data/sounds/`. `"none"` → no playback. |

(Previously: the dataclass had 28 fields ending at `pre_send_warn`;
the six new fields extend the shape additively. After v0.10.0:
**34 fields** total.)

#### Scenario: All six new fields exist with documented defaults

- GIVEN a fresh `BellbirdConfig()`
- WHEN the field values are read
- THEN `system_voice_name == ""`
- AND `system_voice_rate == 0`
- AND `auto_speak_responses is False`
- AND `notifications_enabled is True`
- AND `sounds_enabled is True`
- AND `sound_theme == "default"`

#### Scenario: save/load round-trip preserves the new fields

- GIVEN a `BellbirdConfig` with `auto_speak_responses=True`,
  `sound_theme="custom"`, `system_voice_rate=3`,
  `notifications_enabled=False`
- WHEN `save_config(cfg, path)` then `load_config(path)` runs
- THEN the loaded config equals the original
  (all 6 new fields round-trip, no data loss)

#### Scenario: forward-compat — unknown keys are silently dropped (regression guard)

- GIVEN a JSON config file with a `future_field` key that no
  build knows about
- WHEN `load_config` runs
- THEN no exception is raised
- AND the known 6 new fields load with their stored values
- AND `future_field` is dropped silently
  (the `__dataclass_fields__` filter, unchanged from v0.8.2,
  protects the round-trip in both directions)

#### Scenario: `auto_speak_responses=False` is the safe default (regression guard)

- GIVEN a fresh `BellbirdConfig()` (no user edits)
- WHEN the application reads the config
- THEN `auto_speak_responses is False`
- AND no code path in `core/` or `ui/` auto-calls
  `speak_with_system_voice` on generation completion
  (the existing `speech.speak("Respuesta completa")` is the
  only on-done voice output; the new channel fires only on
  explicit F8 — see `app-shell` v0.10.0)

---

## Verification (WU-1 apply, 2026-06-25)

The 6 fields have been added to `BellbirdConfig` and verified via
10 tests (`TestV0100AudioConfig`) covering: all defaults, save/load
round-trip, forward-compat from v0.9.0 configs, unknown-key filtering,
and no migration entry creep. All tests pass on WSL.
