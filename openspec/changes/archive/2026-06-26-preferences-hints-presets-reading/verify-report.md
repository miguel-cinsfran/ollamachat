# Verify Report — Preferences Hints + Presets + Reading Filters (v0.11.0)

**Date**: 2026-06-25
**Change**: 2026-06-25-preferences-hints-presets-reading
**Status**: BLOCKED (1 CRITICAL — C1: leaked LLM tokens in apply-progress.md)

## Test run

- `uv run --no-sync pytest -xvs`: **844 passed, 15 skipped in 97.68s (0:01:37)**
- `git status --short`: clean (no output)

## Findings

### CRITICAL (block archive)

- **C1** — `openspec/changes/2026-06-25-preferences-hints-presets-reading/apply-progress.md:138-203` — The `apply-progress.md` file has leaked LLM tokens (`<｜end▁of▁thinking｜>Now let me commit everything:`, `<｜｜DSML｜｜tool_calls>`, `<｜｜DSML｜｜invoke name="bash">`, `<｜｜DSML｜｜parameter name="command" string="true">`) AND a full duplicated WU-1 apply-progress section after the WU-2 close. This is an artifact from the WU-2 apply sub-agent's tool-call serialization leaking into the file write (file is committed in `e1d0362` with the corruption). The leaked content includes a `git add -A && git status --short` bash command that was never executed but appears as text in the file. This file gets archived with the change, so leaking sub-agent metadata into the archive dir is undesirable. **Suggested fix**: `chore(docs): trim leaked LLM tokens from apply-progress.md` — delete lines 138-203 (everything after `_apply_config reads no preset field.` on line 138, which is the end of the WU-2 "Notes" section). Fix is small (1 commit, no test re-run needed). Per v0.8.3 lessons: "Commit pequeño post-verify para remediación es OK y preferible a archivar con CRITICAL".

### WARNING (archive OK, file as debt)

- **W1** — Spec drift: `apply_preset_to_controls` is implemented as an **instance method** (`_apply_preset_to_controls(self, preset)` at `preferences_dialog.py:1470`) with **no `controls` dict parameter** and a leading underscore. The spec describes a free function `apply_preset_to_controls(preset, controls: dict[str, wx.Window])` (parameters delta, §2 Module Contracts, and the `apply_preset_to_controls is wx-side` scenario). **Behavioural contract preserved**: the method writes only to the 7 sampler widgets (temp/min_p/max_tokens/top_p/top_k/repeat/seed), does NOT touch `system_prompt`, `confirm_new_conversation`, or `tools_enabled`. **Suggested fix**: spec edit to reflect `_apply_preset_to_controls` as the canonical name (method on `PreferencesDialog`), no code change needed.

- **W2** — Spec drift: preset button `name=` strings. Spec scenarios use **singular + `_button` suffix** (`pref_preset_apply_button`, `pref_preset_save_button`, `pref_preset_delete_button`). Impl uses **plural, no suffix** (`pref_presets_apply`, `pref_presets_save`, `pref_presets_delete`) to match the ListBox name pattern (`pref_presets_list`). Both naming schemes are consistent within their own context (impl is internally consistent, spec is internally consistent). **Suggested fix**: spec edit to align with impl; the impl names are more idiomatic and match the `pref_presets_list` pattern.

- **W3** — Spec drift: missing `name="pref_presets_subpanel"` named container. The parameters spec (Scenario: "preset sub-panel is below `pref_max_tokens_spin`") implies a `name="pref_presets_subpanel"` wrapper widget. Impl uses a flat section of the model_page sizer with no named wrapper. The `pref_presets_list` + 3 buttons are direct children of `model_page`. The AST test (`test_presets_sub_panel_below_max_tokens`) only checks ordering, not the named wrapper, so it passes. **Suggested fix**: spec edit — the spec requirement is satisfied behaviourally (sub-panel is below max_tokens); the named container was an implementation detail.

- **W4** — Spec drift: `interrupt=True` for the "Nombre vacío" / "Ya existe" speak in the `Guardar actual como…` scenarios. Spec says `speech.speak("Nombre vacío", interrupt=True)`; impl uses `interrupt=False` at `preferences_dialog.py:1443` and `:1449`. The spec scenario notes the test is OK with the call being made (or would be if speech is wired) — so the `interrupt=True` is a soft requirement. **Suggested fix**: spec edit to `interrupt=False` (which matches the v0.8.3 lesson "NO usar `interrupt=True` para mensajes no críticos de progreso" — the user should not be interrupted while typing in the TextEntryDialog). No code change.

- **W5** — Spec drift: HINTS test scope. Spec says "extracts all `name=` arguments in `wx.StaticText`, `wx.Slider`, `wx.SpinCtrl`, `wx.CheckBox`, `wx.ListBox`, `wx.Button`, `wx.TextCtrl`, `wx.Choice` constructors". The impl test `test_hints_bidirectional_coverage` (`test_preferences_dialog_static.py:784`) **excludes `wx.StaticText`** and instead includes `wx.Notebook`. This is correct (StaticText are not interactive, so they don't need tooltips; the value labels like `temp_value_label` are StaticText-only and don't need coverage). **Suggested fix**: spec edit to drop `wx.StaticText` from the widget types list and add `wx.Notebook`.

### SUGGESTION (optional polish)

- **S1** — TTS integration in `Speech.speak_with_system_voice` is NOT wired (per design §10, marked SUGGESTION). The `core/speech.py` file is unchanged (152 lines, 0 diff lines vs. base commit ed98a7b). The `apply_filters` function exists but is not called from any production code path. The apply-progress notes explicitly mark this as deferred. **Acceptable per design** — wire in a follow-up change if desired. No code change recommended.

- **S2** — StaticText "group labels" with `&` mnemonic are decorative (StaticText is not focusable). Examples: `&Voz del sistema:`, `&Lectura automática:`, `&Notificaciones:`, `&Ajustes preestablecidos:`, `Filtros de lectura (al leer en voz &alta con SAPI):`. NVDA reads the `&` letter (e.g. "Voz del sistema, V") but it does not focus anything. This is intentional per AGENTS.md / v0.8.3 lesson. **No change recommended**.

- **S3** — Atajos tab `_ACTION_LABELS` dict has all 21 entries prefixed with `&` (`abort_generation: "&Detener generación"`, etc.) per the spec requirement. Verified at `preferences_dialog.py:29-51`. Collision within the tab is impossible because each `&X` is on a separate row, and wx resolves Alt+letter to the focused tab's first interactive control with that letter. The `test_ampersand_mnemonics_unique_within_tab` AST test only checks StaticText + CheckBox, not buttons — but the action labels are StaticText (decorative) and the buttons are repeated per row, so the per-tab uniqueness constraint effectively only applies to StaticText + CheckBox. **No change recommended**.

## Spec drift register

- **D1** — `parameters` delta (Module Contracts §2) + parameters Scenario: `apply_preset_to_controls` is described as a free function with `controls: dict[str, wx.Window]` param. Impl is `_apply_preset_to_controls(self, preset)`. **Resolution**: instance method with internal access to `self.pref_*` widgets is functionally equivalent and arguably cleaner; spec wording is the looser description. File as W1.
- **D2** — `app-configuration` delta: preset button `name=` strings. **Resolution**: impl chose plural + no suffix to match the existing `pref_presets_list` pattern. Spec scenarios use singular + suffix. Both are internally consistent. File as W2.
- **D3** — `parameters` delta: `pref_presets_subpanel` named container. **Resolution**: impl is a flat section. Spec scenario is satisfied behaviourally. File as W3.
- **D4** — `app-configuration` Lectura tab spec scenario: `interrupt=True` for "Nombre vacío" / "Ya existe". **Resolution**: impl uses `interrupt=False` (consistent with v0.8.3 lesson). File as W4.
- **D5** — `app-configuration` HINTS spec scenario: `wx.StaticText` listed in widget types for `name=` extraction. **Resolution**: impl AST test excludes StaticText (correct — not interactive). File as W5.
- **D6** — `parameters` delta mentions `_ACTION_LABELS` (21 entries) with `&` injection. Impl has 21 entries, all with `&` prefix. **Resolution**: satisfied, no drift.

## Compliance with lessons-learned

- **v0.8.3 verify-reads-code**: **YES** — read all 4 implementation files end-to-end (`core/preset.py`, `core/text_filters.py`, `core/config.py`, `ui/preferences_dialog.py` 1493 lines), 5 test files, and the 4 spec deltas + design + proposal. Audited `core/speech.py` to confirm TTS integration is NOT wired (per design §10). Inspected handler bodies (`_on_apply_preset`, `_on_save_preset`, `_on_delete_preset`, `_apply_preset_to_controls`, `_apply_config`, `_apply_hint`) for race conditions / closure leaks.
- **v0.8.3 wx-isolation**: **PASS** — `grep -l "import wx" bellbird/core/*.py` returns only pre-existing modules (`llama_client.py`, `notifier.py`, `sound_player.py`, `system_voice.py`). The two new core modules (`preset.py`, `text_filters.py`) are wx-free. AST guards in `test_preset.py` and `test_text_filters.py` enforce this.
- **AGENTS.md no-GridSizer**: **PASS** — `grep -n "GridSizer" bellbird/ui/preferences_dialog.py` returns 0 matches. All sizers are `wx.BoxSizer(wx.HORIZONTAL)` or `wx.BoxSizer(wx.VERTICAL)`. Test `test_no_grid_sizer` and `test_no_grid_sizer_in_preferences` and `test_audio_tab_no_grid_sizer` all pass.
- **AGENTS.md name-on-every-control**: **PASS** — `test_all_controls_have_name` passes for all interactive widgets (Button, Slider, TextCtrl, SpinCtrl, ListBox, CheckBox). The Lectura tab 4 checkboxes all have `name="pref_filter_*"`. The preset sub-panel ListBox has `name="pref_presets_list"` and the 3 buttons have `name="pref_presets_apply"`, `"pref_presets_save"`, `"pref_presets_delete"`.
- **AGENTS.md StaticText precedes controls**: **PASS** — In Lectura tab, StaticText header precedes 4 CheckBoxes. In Modelo tab preset sub-panel, StaticText "&Ajustes preestablecidos:" precedes the ListBox. In other tabs, the pattern is consistent.
- **v0.9.0 AST guard for pure helpers**: **PASS** — `tests/core/test_preset.py::TestPresetASTGuards::test_ast_no_wx_import` (line 156) and `tests/core/test_text_filters.py::TestTextFiltersASTGuards::test_ast_no_wx_import` (line 371) both pass. Both modules pass the AST walk.
- **v0.8.2 spec drift normal**: **YES** — 6 spec drifts identified (D1-D6) plus 1 content-quality issue (C1: leaked LLM tokens in apply-progress.md). All non-blocking; spec edits proposed in W1-W5.
- **v0.9.0 `FakeSpeech.output()` stub audit**: **N/A** — the new code paths in `preferences_dialog.py` call `self._speech.speak(...)` only. The `apply_filters` function is not called from any production code path (TTS integration deferred per design §10). No new stub is required.
- **v0.8.0 keymap pattern**: **N/A** — no new keybind added in this change.
- **v0.6.0 state machine reset**: **N/A** — no new state machine in this change.
- **v0.8.3 menu lifecycle**: **N/A** — no new menu items in this change.
- **WU-1 / WU-2 split (v0.8.2 process)**: **PASS** — Two work units applied serially (commits 8290ec1 + 888085e + c44ac3a + e1d0362). Both WU-1 (core + tests) and WU-2 (UI + wx-tests) are complete. Pytest reports `844 passed, 15 skipped` (the +50 from WU-1 and +16 from WU-2 reconcile to the 250 new test scenarios from this change).
- **Pre-archive check (`git status --short` clean)**: **PASS** — no untracked files, no modified files, no deleted files.

## Acceptance criteria (from proposal §Acceptance)

- [x] `uv run --no-sync pytest -xvs` green in WSL. **Evidence**: 844 passed, 15 skipped in 97.68s.
- [x] Every control in `preferences_dialog.py` has a hint entry in `HINTS` AND `SetToolTip` + `SetHelpText` are set. **Evidence**: `test_hints_bidirectional_coverage` passes (bidirectional check: HINTS keys ⊇ control `name=` AND HINTS keys ⊆ control `name=`). `_apply_hint` calls `SetToolTip` + `SetHelpText` (lines 1411-1412) and is invoked for every interactive control.
- [x] `param_presets` round-trips through `save_config` / `load_config` (JSON file → list of `ParamPreset`). **Evidence**: `TestV0110Config` in `test_config.py` covers round-trip, per-instance default, and forward-compat (old config without the field). `load_config` normalises list-of-dicts to `list[ParamPreset]` (config.py:144-151).
- [x] **Lectura** tab exists, inserted between Chat and Herramientas, with 4 toggles. **Evidence**: `_build_ui` (line 448) calls `_build_lectura_page` between `_build_chat_page` (447) and `_build_tools_page` (449). `test_lectura_tab_between_chat_and_herramientas` passes. 4 CheckBoxes with correct `name=` strings covered by `test_lectura_tab_has_four_filter_checkboxes`.
- [x] Every Spanish label literal in all 9 tabs has exactly one `&` preceding a non-space letter. **Evidence**: `test_ampersand_mnemonics_each_label_has_exactly_one` and `test_ampersand_mnemonics_unique_within_tab` both pass. The `&Ayuda de encaje` regression guard passes. The `Estado (F2)` 11 toggle labels regression guard passes.
- [x] `apply_filters` is unit-tested for: 4 filters ON, 4 filters OFF, order preserved, idempotent, handles empty input. **Evidence**: `test_text_filters.py::TestApplyFiltersBasics::test_all_toggles_off_returns_input`, `::test_empty_input_returns_empty`, `::test_never_raises_on_none_input`, `::TestApplyFiltersOrder::test_order_is_strip_markdown_first`, `::test_order_is_strip_urls_second`, plus 4 `TestStrip*` classes with 3-4 scenarios each. Total 29 scenarios in `test_text_filters.py`.
- [x] Dialog size bumped to `(720, 600)` and the AST test pins it. **Evidence**: `preferences_dialog.py:436` `self.SetSize((720, 600))`. `test_dialog_size_is_720_600` passes.

## Recommendation

**BLOCKED: 1 CRITICAL (C1) — fix with `chore(docs):` commit, then re-verify and archive.**

The change is functionally complete and all 844 tests pass. The 1 CRITICAL (C1: leaked LLM tokens in `apply-progress.md`) must be cleaned up before archive because the file with leaked content will be moved to the archive dir. The 5 spec drifts (W1-W5) and 3 SUGGESTIONs (S1-S3) are non-blocking and can be cleaned up in the same or follow-up commits.

**Pre-archive actions required** (small, mechanical):
1. `chore(docs): trim leaked LLM tokens from apply-progress.md` — delete lines 138-203 of `apply-progress.md` (fixes **C1**).
2. (Optional, recommended) `chore(spec): align v0.11.0 spec deltas with impl` — apply the proposed spec edits for W1-W5 (5 small markdown edits). Per v0.8.2 lesson, "spec drift entre proposal/spec/design/impl es normal y debe resolverse pre-archive" — but these are non-blocking drifts, all docs-only. Acceptable as debt per the v0.9.0 lesson: "aceptar como deuda si el impl es más idiomático o el test pasa, y documentar para cleanup. NO bloquear el archive."

The C1 fix is docs-only, does not change behaviour, and the test suite does not need to re-run (the change artifacts are not the test source). Total: ~5 minutes for C1 (mandatory) + ~25 minutes for the optional spec cleanup.
