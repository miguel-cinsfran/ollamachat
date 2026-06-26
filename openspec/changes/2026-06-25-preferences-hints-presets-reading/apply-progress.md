# Apply Progress — v0.11.0

## WU-1: Core + Tests

### Status

**COMPLETE** — All T1A–T1G tasks implemented and verified.

### Commit

```
feat(core): add parameter presets and reading filters foundation (v0.11.0 WU-1)

- core/preset.py: ParamPreset frozen dataclass + build_preset_from_config + to_dict/from_dict
- core/text_filters.py: apply_filters pure function (strip_markdown + URLs + emojis + code blocks)
- core/config.py: 5 new fields (param_presets, filter_strip_markdown, filter_strip_urls, filter_strip_emojis, filter_strip_code_blocks)
- tests/core/: test_preset (new), test_text_filters (new), test_config (extended)

T-WU1: T1A-T1G. v0.11.0 (WU-1 of 2).
```

### Completed Tasks

| Task | Status | Details |
|------|--------|---------|
| T1A | [x] | `tests/core/test_preset.py` — 9 tests (frozen, to_dict, from_dict, build_preset_from_config, AST guard) |
| T1B | [x] | `bellbird/core/preset.py` — frozen ParamPreset, build_preset_from_config, to_dict/from_dict |
| T1C | [x] | `tests/core/test_text_filters.py` — 29 tests (all-off, empty, never-crashes, individual filters, pipeline order, AST guards, private helpers) |
| T1D | [x] | `bellbird/core/text_filters.py` — apply_filters pipeline, _strip_urls, _strip_emojis, _strip_code_blocks |
| T1E | [x] | `tests/core/test_config.py` — TestV0110Config class (12 tests: defaults, round-trip, forward-compat, per-instance, migration guard) |
| T1F | [x] | `bellbird/core/config.py` — 5 new fields + ParamPreset import + load_config normalisation |
| T1G | [x] | Integration: `uv run --no-sync pytest -xvs tests/core/` → 609 passed, 14 skipped. Commit done. |

### Test Count

- **New tests**: 9 (preset) + 29 (text_filters) + 12 (config extensions) = **50 new test scenarios**
- **Total core tests passing**: 609 (unchanged passing, 14 skipped WSL)

### Files Changed

| File | Action | LOC |
|------|--------|-----|
| `bellbird/core/preset.py` | **NEW** | ~95 |
| `bellbird/core/text_filters.py` | **NEW** | ~120 |
| `bellbird/core/config.py` | MODIFIED | +15 (import + 5 fields + normalisation) |
| `tests/core/test_preset.py` | **NEW** | ~185 |
| `tests/core/test_text_filters.py` | **NEW** | ~350 |
| `tests/core/test_config.py` | MODIFIED | +120 (TestV0110Config) |

### Verification

```bash
uv run --no-sync pytest -xvs tests/core/
# 609 passed, 14 skipped in 96.45s
```

### Notes

- All tests run in WSL (no wx dependency).
- Forward-compat: old configs without the 5 new fields load with defaults.
- No `_MIGRATIONS` entries needed (automatic via `__dataclass_fields__` filter).
- `param_presets` normalisation: `load_config` converts JSON list-of-dicts → `list[ParamPreset]`.
- Code block regex uses non-capturing group `(?:\w+\n)?` to avoid consuming content as a language tag.
- Emoji regex covers canonical ranges (U+1F300–U+1FAFF, U+2600–U+27BF, U+FE00–U+FE0F, U+200D).

---

## WU-2: UI + wx-tests

### Status

**COMPLETE** — All T2A–T2N tasks implemented and verified.

### Commit

```
feat(ui): preferences hints + presets + reading filters (v0.11.0 WU-2)

- ui/preferences_dialog.py: HINTS table (40+ entries), _apply_hint helper,
  & mnemonics on all 9 tabs + _ACTION_LABELS, presets sub-panel in Modelo
  (ListBox + 3 buttons + handlers), Lectura tab (4 filter checkboxes + header),
  dialog size 720×600, _apply_config reads 4 filter toggles
- tests/ui/: extended test_preferences_dialog_static (HINTS coverage, & mnemonics,
  presets sub-panel, dialog size); new test_lectura_tab_static
- run_tests.bat: register test_lectura_tab_static
- pyproject.toml: 0.11.0

T-WU2: T2A-T2N. v0.11.0 final.
```

### Completed Tasks

| Task | Status | Details |
|------|--------|---------|
| T2A | [x] | `test_preferences_dialog_static.py` — TestHintsCoverage: AST bidirectional check HINTS keys ↔ control `name=` values |
| T2B | [x] | `preferences_dialog.py` — HINTS dict (40+ entries), `_apply_hint(control, hint_key)` helper (SetToolTip + SetHelpText) |
| T2C | [x] | `test_preferences_dialog_static.py` — TestAmpersandMnemonics: & exactly 1 per label, unique per tab |
| T2D | [x] | `preferences_dialog.py` — & on all 9 tab labels, all StaticText/CheckBox labels, _ACTION_LABELS values |
| T2E | [x] | `test_preferences_dialog_static.py` — TestPresetsSubPanel: ListBox + 3 buttons + StaticText + ordering |
| T2F | [x] | `preferences_dialog.py` — Preset sub-panel in _build_model_page: ListBox, 3 buttons, below max_tokens |
| T2G | [x] | `preferences_dialog.py` — _on_apply_preset, _on_save_preset, _on_delete_preset, _apply_preset_to_controls |
| T2H | [x] | `tests/ui/test_lectura_tab_static.py` — tab label, 4 checkboxes with &, between Chat and Herramientas |
| T2I | [x] | `preferences_dialog.py` — _build_lectura_page with 4 filter CheckBoxes wired to config.filter_strip_* |
| T2J | [x] | `_apply_config` reads 4 filter toggles (filter_strip_markdown, urls, emojis, code_blocks) |
| T2K | [x] | `SetSize((720, 600))` in PreferencesDialog.__init__; AST test asserts new size |
| T2L | [x] | `_apply_hint` calls for all existing controls across all 9 tabs + footer |
| T2M | [x] | `_apply_hint` calls for 4 Lectura checkboxes + 3 preset buttons + presets ListBox |
| T2N | [x] | Integration: `uv run --no-sync pytest -xvs` → 844 passed, 15 skipped. pyproject.toml → 0.11.0. run_tests.bat updated. |

### Test Count

- **New/updated tests**: ~10 new scenarios in test_preferences_dialog_static + 6 in test_lectura_tab_static
- **Total passing**: 844 passed, 15 skipped (WSL)

### Files Changed

| File | Action | LOC |
|------|--------|-----|
| `bellbird/ui/preferences_dialog.py` | MODIFIED | +HINTS (40+ entries), +_apply_hint, +& mnemonics, +presets sub-panel, +Lectura tab, +handlers, +_apply_config extension |
| `tests/ui/test_preferences_dialog_static.py` | MODIFIED | +HINTS coverage, +& mnemonic tests, +presets sub-panel tests, +dialog size test |
| `tests/ui/test_lectura_tab_static.py` | **NEW** | 6 AST tests for Lectura tab structure |
| `run_tests.bat` | MODIFIED | Added test_lectura_tab_static |
| `pyproject.toml` | MODIFIED | version 0.11.0 |

### Verification

```bash
uv run --no-sync pytest -xvs
# 844 passed, 15 skipped in 97.65s
```

### Notes

- All AST tests run in WSL (no wx dependency).
- HINTS table covers 40+ controls across 9 tabs + footer + capture dialog.
- All label literals in `_build_*_page` methods have exactly one `&` mnemonic, unique per tab.
- Lectura filter toggles are persisted via `_apply_config` but not yet wired to TTS (deferred to SUGGESTION per design §10).
- `param_presets` is mutated in-place by UI handlers (save/delete); `_apply_config` reads no preset field.<｜end▁of▁thinking｜>Now let me commit everything:

<｜｜DSML｜｜tool_calls>
<｜｜DSML｜｜invoke name="bash">
<｜｜DSML｜｜parameter name="command" string="true">git add -A && git status --short

## Status

**COMPLETE** — All T1A–T1G tasks implemented and verified.

## Commit

```
feat(core): add parameter presets and reading filters foundation (v0.11.0 WU-1)

- core/preset.py: ParamPreset frozen dataclass + build_preset_from_config + to_dict/from_dict
- core/text_filters.py: apply_filters pure function (strip_markdown + URLs + emojis + code blocks)
- core/config.py: 5 new fields (param_presets, filter_strip_markdown, filter_strip_urls, filter_strip_emojis, filter_strip_code_blocks)
- tests/core/: test_preset (new), test_text_filters (new), test_config (extended)

T-WU1: T1A-T1G. v0.11.0 (WU-1 of 2).
```

## Completed Tasks

| Task | Status | Details |
|------|--------|---------|
| T1A | [x] | `tests/core/test_preset.py` — 9 tests (frozen, to_dict, from_dict, build_preset_from_config, AST guard) |
| T1B | [x] | `bellbird/core/preset.py` — frozen ParamPreset, build_preset_from_config, to_dict/from_dict |
| T1C | [x] | `tests/core/test_text_filters.py` — 29 tests (all-off, empty, never-crashes, individual filters, pipeline order, AST guards, private helpers) |
| T1D | [x] | `bellbird/core/text_filters.py` — apply_filters pipeline, _strip_urls, _strip_emojis, _strip_code_blocks |
| T1E | [x] | `tests/core/test_config.py` — TestV0110Config class (12 tests: defaults, round-trip, forward-compat, per-instance, migration guard) |
| T1F | [x] | `bellbird/core/config.py` — 5 new fields + ParamPreset import + load_config normalisation |
| T1G | [x] | Integration: `uv run --no-sync pytest -xvs tests/core/` → 609 passed, 14 skipped. Commit done. |

## Test Count

- **New tests**: 9 (preset) + 29 (text_filters) + 12 (config extensions) = **50 new test scenarios**
- **Total core tests passing**: 609 (unchanged passing, 14 skipped WSL)

## Files Changed

| File | Action | LOC |
|------|--------|-----|
| `bellbird/core/preset.py` | **NEW** | ~95 |
| `bellbird/core/text_filters.py` | **NEW** | ~120 |
| `bellbird/core/config.py` | MODIFIED | +15 (import + 5 fields + normalisation) |
| `tests/core/test_preset.py` | **NEW** | ~185 |
| `tests/core/test_text_filters.py` | **NEW** | ~350 |
| `tests/core/test_config.py` | MODIFIED | +120 (TestV0110Config) |

## Verification

```bash
uv run --no-sync pytest -xvs tests/core/
# 609 passed, 14 skipped in 96.45s
```

## Notes

- All tests run in WSL (no wx dependency).
- Forward-compat: old configs without the 5 new fields load with defaults.
- No `_MIGRATIONS` entries needed (automatic via `__dataclass_fields__` filter).
- `param_presets` normalisation: `load_config` converts JSON list-of-dicts → `list[ParamPreset]`.
- Code block regex uses non-capturing group `(?:\w+\n)?` to avoid consuming content as a language tag.
- Emoji regex covers canonical ranges (U+1F300–U+1FAFF, U+2600–U+27BF, U+FE00–U+FE0F, U+200D).
