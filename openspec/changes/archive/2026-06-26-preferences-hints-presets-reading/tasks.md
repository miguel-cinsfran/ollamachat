# Tasks: Preferences Hints + Parameter Presets + Reading Filters

## Review Workload Forecast

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Medium

| Field | Value |
|-------|-------|
| Estimated changed lines | ~900-1100 |
| 400-line budget risk | Medium |
| Chained PRs recommended | No |
| Suggested split | WU-1 (core) → WU-2 (UI) |
| Delivery strategy | exception-ok |

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| WU-1 | Core + tests: preset.py, text_filters.py, config fields | 1 commit to main | ~500 LOC, wx-free, fully WSL-runnable |
| WU-2 | UI: HINTS, & mnemonics, presets sub-panel, Lectura tab, size bump | 1 commit to main | ~450 LOC, AST tests run in WSL, wx-runtime on Windows |

## WU-1: Core + Tests (7 tasks, ~500 LOC)

### Phase 1: TDD — ParamPreset dataclass

- [ ] **T1A**: Write `tests/core/test_preset.py` — `ParamPreset` frozen (mutation raises `FrozenInstanceError`); `to_dict`/`from_dict` round-trip via `asdict`; `build_preset_from_config` copies 7 fields; no `wx` import (AST guard).
- [ ] **T1B**: Implement `bellbird/core/preset.py` — frozen `@dataclass` with 8 fields (`name` + 7 sampler fields), `build_preset_from_config(name, config)`, no `wx`.

### Phase 2: TDD — Text filters pipeline

- [ ] **T1C**: Write `tests/core/test_text_filters.py` — order: `strip_markdown` → `strip_urls` → `strip_emojis` → `strip_code_blocks`; all OFF = identity; empty = `""`; never raises; no `wx` import; `[link](url)` order test.
- [ ] **T1D**: Implement `bellbird/core/text_filters.py` — `apply_filters(text, config)` + private helpers (`_strip_urls`, `_strip_emojis`, `_strip_code_blocks`). Reuses `text_utils.strip_markdown`. Never-crash guard.

### Phase 3: TDD — Config fields

- [ ] **T1E**: Extend `tests/core/test_config.py` — 5 new field defaults; round-trip via save+load; forward-compat (old config loads with defaults); `param_presets` per-instance default; `_MIGRATIONS` unchanged.
- [ ] **T1F**: Extend `bellbird/core/config.py` — add `param_presets`, `filter_strip_markdown`, `filter_strip_urls`, `filter_strip_emojis`, `filter_strip_code_blocks` (all defaults `True`, except `param_presets`=`[]`). Import `ParamPreset`.

### Phase 4: Integration

- [ ] **T1G**: `uv run --no-sync pytest -xvs tests/core/test_preset.py tests/core/test_text_filters.py tests/core/test_config.py` green. Write `apply-progress.md` with WU-1 block.

## WU-2: UI + wx-tests (14 tasks, ~450 LOC)

### Phase 1: HINTS dict + & mnemonics

- [ ] **T2A**: Extend `tests/ui/test_preferences_dialog_static.py` — AST test parses all `wx.Window` constructor calls with `name="pref_*"`, builds name set, asserts bidirectional coverage with `HINTS` keys.
- [ ] **T2B**: Add `HINTS: dict[str, str]` module-level in `preferences_dialog.py` (~40 entries per design §4). Add `_apply_hint(control, hint_key)` helper (sets `SetToolTip` + `SetHelpText`, try/except).
- [ ] **T2C**: Extend `test_preferences_dialog_static.py` — AST test scans every `StaticText` and `CheckBox` `label=` argument; asserts exactly one `&` per label; within each `_build_*_page`, asserts `&` letters are unique.
- [ ] **T2D**: Add `&` mnemonics to every Spanish label literal in all 8 existing `_build_*_page` methods + `_ACTION_LABELS` values. Resolve collisions per design §7 table (e.g., `C&hat`, `A&tajos`, `A&udio`). Preserve existing `&` in Estado/F2 and `&Ayuda de encaje`.

### Phase 2: Preset sub-panel (Modelo tab)

- [ ] **T2E**: Extend `test_preferences_dialog_static.py` — AST asserts `_build_model_page` contains `wx.ListBox` with `name="pref_presets_list"` and 3 `wx.Button` with `name="pref_presets_apply"`, `"pref_presets_save"`, `"pref_presets_delete"`, each preceded by `wx.StaticText`.
- [ ] **T2F**: Add preset sub-panel to `_build_model_page` — BELOW `pref_max_tokens_spin`, ABOVE `sizer.AddStretchSpacer()`. StaticText `"&Ajustes preestablecidos:"`, ListBox populated from `self._config.param_presets`, 3 buttons in horizontal sizer.
- [ ] **T2G**: Wire 3 preset handlers — `_on_apply_preset` (reads listbox selection → `_apply_preset_to_controls` updates 7 widgets → speak "Aplicado"); `_on_save_preset` (`wx.TextEntryDialog` → validate name → `build_preset_from_config` → append → refresh listbox → speak); `_on_delete_preset` (remove from listbox + config → speak). Duplicate name → speak "Ya existe". Empty name → speak "Nombre vacío". No selection → no-op.

### Phase 3: Lectura tab

- [ ] **T2H**: Write `tests/ui/test_lectura_tab_static.py` — AST asserts dialog has page `"&Lectura"` between Chat and Herramientas; 4 `wx.CheckBox` with `name="pref_filter_markdown"`, `pref_filter_urls`, `pref_filter_emojis`, `pref_filter_code_blocks`; each with `&` in label.
- [ ] **T2I**: Implement `_build_lectura_page(notebook)` — insert between Chat and Herramientas in `_build_ui()`. StaticText header `"Filtros de lectura (al leer en voz &alta con SAPI):"` + 4 CheckBoxes wired to `self._config.filter_strip_*` defaults.
- [ ] **T2J**: Extend `_apply_config` — read the 4 filter checkboxes into `self._config.filter_strip_markdown` etc. `param_presets` already mutated in-place by UI handlers (no read needed).

### Phase 4: Final wiring + bump

- [ ] **T2K**: Change `self.SetSize((620, 520))` → `self.SetSize((720, 600))` in `__init__`. AST test asserts the new size literal is present.
- [ ] **T2L**: Go through each `_build_*_page` existing controls and call `self._apply_hint(control, "hint_key")` for every interactive widget. Verify via T2A AST coverage.
- [ ] **T2M**: Call `self._apply_hint` for the 4 Lectura tab checkboxes and the 3 preset buttons.
- [ ] **T2N**: `uv run --no-sync pytest -xvs` green. Bump `pyproject.toml` to `0.11.0`. Update `run_tests.bat` with new wx-runtime tests. Update `apply-progress.md`. `git status --short` clean before verify.

## Task Summary

| Phase | Tasks | Focus |
|-------|-------|-------|
| Phase 1 (WU-1) | T1A–T1G | Core: preset, text_filters, config fields |
| Phase 2 (WU-2) | T2A–T2N | UI: HINTS, mnemonics, presets, Lectura, size bump |
| Total | 21 | |

**Implementation Order**: WU-1 first (core + tests, fully WSL-runnable) → WU-2 second (UI + wx-tests, AST tests in WSL, runtime on Windows). Each WU is one commit to main.
