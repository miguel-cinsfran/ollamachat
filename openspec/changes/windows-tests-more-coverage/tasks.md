# Tasks: Windows-side Test Coverage

> **Apply split**: 2 work-units (WU-1 + WU-2). Forecast ~700-900 LOC
> total (test files are the bulk). Per lessons-learned v0.8.2 / v0.11.0:
> split when forecast >8 tasks or >400 lines. This change hits both
> thresholds. Single PR (mode D2, per AGENTS.md default).
>
> **Zero changes to `bellbird/` source.** All artifacts are tests +
> pipeline + docs.

---

## Phase 1 — WU-1: wx-runtime test files (6 tasks, ~500 LOC)

- [x] **1.1** Create `tests/ui/test_voice_dialog_runtime.py` with
      `pytest.importorskip("wx")` and 5 tests:
      - `construct_with_choices` — Choice populated, selection matches
      - `get_voice_returns_initial` — verify `current_voice`
      - `get_rate_returns_initial` — verify `current_rate`
      - `change_choice_updates_get_voice` — select "B", verify
      - `change_slider_updates_get_rate` — set 7, verify

- [x] **1.2** Create `tests/ui/test_preferences_dialog_runtime.py`
      with `pytest.importorskip("wx")` and 7 tests:
      - `dialog_constructs` — type + name verification
      - `ok_round_trip_unmodified` — `_apply_config()` on fresh dialog
      - `change_system_prompt_updates_config` — TextCtrl → `_apply_config`
      - `toggle_lectura_filter_updates_config` — `pref_filter_urls` off
      - `preset_apply_writes_to_controls` — `_apply_preset_to_controls`
      - `audio_voice_round_trip` — voice/rate accessors via dialog
      - `every_control_has_name` — `FindWindowByName` for ~10 documented names

- [x] **1.3** Create `tests/ui/test_lectura_tab_runtime.py` with
      `pytest.importorskip("wx")` and 3 tests:
      - `all_4_filters_default_checked` — `BellbirdConfig()` defaults
      - `uncheck_filter_updates_config` — toggle one, `_apply_config`
      - `filter_state_round_trips_reopen` — config with `False`,
        reopen, verify the CheckBox reflects it

- [x] **1.4** Create `tests/ui/test_system_voice_runtime.py` with
      `pytest.importorskip("wx")` and 4 tests:
      - `non_win32_speak_is_noop` — guarded by `sys.platform`
      - `win32_without_sapi_swallow_exceptions` — `unittest.mock.patch`
        on `win32com.client.Dispatch` to raise
      - `set_voice_empty_returns_false`
      - `set_rate_clamps_to_range` — value 15 stays within `[-10, +10]`

- [x] **1.5** Fix `tests/ui/test_keymap_capture.py::TestSixTabOrder`:
      - Update `test_six_tabs_present` → `test_nine_tabs_present` with
        `len(labels) == 9`
      - Update `test_tab_order` expected list to 9 labels INCLUDING
        `&` mnemonics: `["&General", "&Modelo", "C&hat", "&Lectura",
        "&Herramientas", "&Avanzado", "A&tajos", "A&udio",
        "&Estado (F2)"]`
      - Rename the class to `TestNineTabOrder` for clarity
      - Add a comment explaining: the labels come from `AddPage`
        literals in `_build_ui`, which include the `&` mnemonic

- [x] **1.6** Run `uv run --no-sync pytest -xvs` in WSL — confirm
      4 new files SKIP cleanly via `importorskip`; verify total
      passes unchanged (846 + 0 new passes on WSL); verify the
      renamed `TestNineTabOrder` passes on WSL (it's static AST and
      doesn't need wx).

---

## Phase 2 — WU-2: pipeline + docs (4 tasks, ~200 LOC)

- [ ] **2.1** Simplify `run_tests.bat`:
      - Drop line 23's explicit pytest list
      - Add a 4-6 line comment block between lines 21-22 listing which
        `tests/ui/*.py` files are wx-runtime (chat_panel_runtime,
        find_dialog, main_window_runtime, url_dialog,
        message_detail_dialog_runtime, permission_dialog_runtime,
        server_watchdog, mainwindow_construction, keymap_accelerator,
        keymap_capture, chat_quick_actions,
        wx_notifier_runtime, preferences_dialog_runtime,
        voice_dialog_runtime, lectura_tab_runtime,
        system_voice_runtime) — for documentation, not execution
      - Keep the `setlocal` and `TMPFILE` patterns intact

- [ ] **2.2** Fix `smoke_test.py::_MODULOS_UI`:
      - Remove the hardcoded list (lines 45-51)
      - Add a function `_discover_ui_modules() -> list[str]` that uses
        `pkgutil.iter_modules(bellbird.ui.__path__)` and returns the
        module names as `bellbird.ui.<name>`
      - Update `fase2_gui()` to call this function instead of using
        the constant
      - Add `import pkgutil` at the top

- [ ] **2.3** Add "Tests" section to `README.md` (in English, matches
      the existing "Build" section):
      - Section header: `## Tests`
      - 4-row table: level / scope / command
        - `core/` → WSL → `uv run --no-sync pytest -xvs`
        - `ui/` static (AST) → WSL → same
        - `ui/` runtime → Windows → `run_tests.bat`
        - `smoke_test.py` → Windows + pywinauto → `uv run python smoke_test.py`
      - One-paragraph note that WSL skips wx-runtime tests via
        `pytest.importorskip("wx")`

- [ ] **2.4** Run WSL verification:
      - `uv run --no-sync pytest -xvs` — confirm 846 + 0 new passes,
        +4 file-skips, no regressions
      - `uv run python smoke_test.py --no-gui` — confirm Fase 1
        (core) and Fase 2 (UI, now auto-discovered, 9 modules) pass
      - `cat run_tests.bat` — eyeball that line 19 is the only
        pytest call and the comment block is readable

---

## Workload / PR boundary

- **Mode**: single PR (per AGENTS.md default; user D2 = 800 lines; this fits).
- **Estimated changed lines**: ~700-900 (test files are the bulk).
  - WU-1: ~500 LOC (4 new test files + 1 fix).
  - WU-2: ~200 LOC (1 bat file + 1 smoke file + 1 README section).
- **WU-1 / WU-2 split rationale**: forecast >8 tasks AND >400 LOC. Per
  lessons-learned v0.8.2 ("Particionar el apply en 2 work-units
  cuando el budget está cerca del límite") and v0.11.0 ("NO delegar
  apply WU-2 con prompt >3000 palabras"). Splitting protects
  sub-agent reliability.
- **PR boundary**: test infra + docs only. Zero changes to
  `bellbird/` source. Easy to revert (`git revert <merge-sha>`).

## Done-When

- All 10 task checkboxes are checked.
- `uv run --no-sync pytest -xvs` on WSL: 846 + 0 passes, +4 file-skips,
  zero regressions, no warnings.
- `uv run python smoke_test.py --no-gui` on WSL: Fase 1 (9 core
  modules) + Fase 2 (9 UI modules auto-discovered) both [ok], exit 0.
- `git status --short` clean.
- `git diff HEAD~2 HEAD -- bellbird/` returns empty (zero source
  changes, verified).
- Each commit's `git log --pretty=fuller -1` has no `Co-Authored-By:`
  (per project rule).
- Conventional commits: `test(ui): add wx-runtime tests for X` for
  new files, `fix(test): update TestSixTabOrder to 9 tabs` for the
  stale test, `chore(ci): simplify run_tests.bat to single pytest
  invocation + comment block` for the bat, `chore(smoke): auto-discover
  UI modules in smoke_test.py`, `docs: add Tests section to README`.
