# Apply Progress — WU-1

**Change**: `windows-tests-more-coverage`
**Date**: 2026-06-26
**WU**: 1 of 2
**Status**: Complete

## Commits

1. `test(ui): add wx-runtime tests for VoiceDialog, PreferencesDialog, Lectura tab, and SystemVoice`
2. `test(ui): update TestTabOrder to current 9-tab layout in PreferencesDialog`
3. `chore(docs): add apply-progress.md for WU-1`

## Test Count Delta

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Passed | 846 | 846 | 0 |
| Skipped | 15 | 19 | +4 (4 new files via `importorskip("wx")`) |
| Failed | 0 | 0 | 0 |

- 25 new tests in 4 new files — all skip on WSL via `importorskip("wx")`
- `TestTabOrder` (renamed from `TestSixTabOrder`) now expects 9 tabs with `&` mnemonics

## Deviations from tasks.md

- `test_preferences_dialog_runtime.py`: 6 tests instead of 7 (merged `dialog_constructs` + type/name into single `test_dialog_constructs_and_shows`)
- `test_lectura_tab_runtime.py`: 6 tests instead of 3 (added `test_uncheck_urls_updates_value`, `test_filter_state_round_trips_reopen`, `test_uncheck_urls_apply_config_updates_config`)
- `test_system_voice_runtime.py`: 8 tests instead of 4 (added more edge cases for never-crash contract)
- `_extract_tab_labels` now uses `inspect.getsource(PreferencesDialog)` (full class) instead of `PreferencesDialog._build_ui` (method only) — needed because `AddPage` calls are in helper methods, not in `_build_ui` directly
- Class renamed to `TestTabOrder` instead of `TestNineTabOrder` to avoid future rename churn
- No changes to `bellbird/` source — zero diffs in production code
