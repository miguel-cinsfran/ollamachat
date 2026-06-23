# Tasks: v0.4.0-tool-calling-ui

## Review Workload Forecast

- **Estimated changed lines**: ~430 lines (1 new file ~95 lines, 3
  extended files +110/-5 lines, 4 new test files/extensions +220/-0
  lines, 1 pyproject bump +1/-1, 1 changelog +12/-0, 1 AGENTS update
  +5/-2)
- **400-line budget risk**: HIGH (~430 > 400)
- **800-line budget (D2 chosen)**: LOW (430 < 800)
- **Chained PRs recommended**: NO (single PR is OK with 800-line budget
  per `delivery: single-pr-default` and `review_budget_lines: 800`
  in `openspec/config.yaml`)
- **Decision needed before apply**: NO — within budget for single PR
- **Actual**: 180/180 tests passing, no deviations

## Work-unit commits

Each commit is independently revertable. Tests are written
BEFORE implementation per the project's TDD convention (RED-GREEN).
For `ui/`, the "tests" are AST checks (project convention), not
runtime tests. `core/` is unchanged.

---

### Phase 1: Permission dialog (foundation of the user-facing flow) [DONE]

#### T1.1 [RED] test(ui): add 8 permission_dialog AST tests [DONE]
- **File**: `tests/ui/test_permission_dialog_static.py` (NEW)
- **Tests**:
  - `test_command_text_present` ✅
  - `test_allow_once_button_present` ✅
  - `test_allow_session_button_present` ✅
  - `test_deny_button_present` ✅
  - `test_all_controls_have_name` ✅
  - `test_only_boxsizer_used` ✅
  - `test_no_message_dialog` ✅
  - `test_no_emoji_in_risk_labels` ✅
- **Status**: 8/8 tests passing

#### T1.2 [GREEN] feat(ui): add PermissionDialog with native buttons [DONE]
- **File**: `ollamachat/ui/permission_dialog.py` (NEW)
- **Contract**: 3 native buttons, no `MessageDialog`, focus on
  `command_text` after `Fit()`, `SetEscapeId(CANCEL)`, ASCII-only
  risk labels, `winsound.MessageBeep` guarded by `sys.platform == "win32"`
- **Status**: 8/8 AST tests pass

---

### Phase 2: ChatPanel appenders (UI hooks for tool results) [DONE]

#### T2.1 [RED] test(ui): add 4 chat_panel append_tool_* AST tests [DONE]
- **File**: `tests/ui/test_chat_panel_static.py` (EXTEND)
- **Tests**:
  - `test_append_tool_output_method_exists` ✅
  - `test_append_tool_blocked_method_exists` ✅
  - `test_append_tool_denied_method_exists` ✅
  - `test_no_emoji_in_tool_prefixes` ✅
- **Status**: 4/4 tests passing

#### T2.2 [GREEN] feat(ui): add append_tool_output / blocked / denied [DONE]
- **File**: `ollamachat/ui/chat_panel.py` (EXTEND, +~25 lines)
- **Contract**: 3 new methods at the bottom of the class; ASCII-only
  prefixes `[Herramienta]`, `[Bloqueado]`, `[Denegado]`; correct
  `_history` role tags
- **Status**: 4/4 AST tests pass

---

### Phase 3: ParamsPanel toggle (catalog gate) [DONE]

#### T3.1 [RED] test(ui): add 2 params_panel tools_checkbox AST tests [DONE]
- **File**: `tests/ui/test_params_panel_static.py` (EXTEND)
- **Tests**:
  - `test_tools_checkbox_present` ✅
  - `test_get_tools_enabled_method_exists` ✅
- **Status**: 2/2 tests passing

#### T3.2 [GREEN] feat(ui): add tools_checkbox + get_tools_enabled [DONE]
- **File**: `ollamachat/ui/params_panel.py` (EXTEND, +~10 lines)
- **Contract**: `wx.CheckBox` with `name="tools_checkbox"`, preceded
  by `wx.StaticText` "Herramientas:", added before `AddStretchSpacer()`;
  `get_tools_enabled() -> bool` returns `GetValue()`
- **Status**: 2/2 AST tests pass

---

### Phase 4: MainWindow integration (wires it all together) [DONE]

#### T4.1 [RED] test(ui): add 7 main_window tool-calling AST tests [DONE]
- **File**: `tests/ui/test_main_window_static.py` (EXTEND)
- **Tests**:
  - `test_permission_manager_initialized` ✅
  - `test_tool_executor_initialized` ✅
  - `test_on_tool_call_method_exists` ✅
  - `test_run_tool_and_show_method_exists` ✅
  - `test_on_tool_result_method_exists` ✅
  - `test_continue_after_tool_method_exists` ✅
  - `test_shell_tool_definition_at_module_level` ✅
- **Status**: 7/7 tests passing

#### T4.2 [GREEN] feat(ui): add SHELL_TOOL_DEFINITION + 4 MainWindow methods + send_message patch [DONE]
- **File**: `ollamachat/ui/main_window.py` (EXTEND, +~110 lines)
- **Contract**:
  - Module-level `SHELL_TOOL_DEFINITION` (not inside the class) ✅
  - 3 new imports at top: `PermissionManager`, `ToolExecutor`, `PermissionDialog` ✅
  - `__init__` initializes `_permission_manager` and `_tool_executor` ✅
  - `send_message` builds `tools` and passes `on_tool_call` + `tools` to `chat_stream` ✅
  - 4 new methods: `_on_tool_call`, `_run_tool_and_show`, `_on_tool_result`, `_continue_after_tool` ✅
  - Threading: `daemon=True`, `wx.CallAfter` to bounce back to main ✅
- **Status**: 7/7 AST tests pass

---

### Phase 5: Version & docs [DONE]

#### T5.1 chore(release): bump pyproject to 0.4.0 [DONE]
- **File**: `pyproject.toml`
- **Change**: `version = "0.3.0"` → `version = "0.4.0"`
- **No tests** (manifest change only)

#### T5.2 docs: add [0.4.0] entry to CHANGELOG.md [DONE]
- **File**: `CHANGELOG.md`
- **Change**: new section at top with:
  - Tool calling con sistema de permisos accesible ✅
  - PermissionManager, PermissionDialog (wx.Dialog nativo) ✅
  - ToolExecutor (PowerShell con fallback pwsh→powershell) ✅
  - Checkbox "Permitir herramientas" en params_panel ✅
  - Auto-bloqueo solo para paths de sistema, no directorios del usuario ✅
- **No tests** (docs only)

#### T5.3 docs(agents): update test count and tool-calling note in AGENTS.md [DONE]
- **File**: `AGENTS.md`
- **Change**: bump 140/140 → 180/180; note v0.4.0 tool calling entry
  in the "Proximos cambios" section (move to "Estado actual")
- **No tests** (docs only)

---

### Phase 6: Final verification [DONE]

#### T6.1 chore(verify): full suite green at 180/180 [DONE]
- **Action**: `uv run --no-sync pytest -xvs`
- **Expected**: 180 passed, 0 failed
- **Result**: 180/180 passed, 0 failed (no fixes needed)**

---

## Summary

- **11 tasks** across **6 phases**
- **21 new AST tests** + **5 docs/test/manifest files**
- **1 new source file** + **4 extended source files**
- **Estimated diff**: ~430 lines (within 800-line budget)
- **No `core/` changes**
- **No new dependencies**
- **Strict TDD**: AST tests in `ui/` are written BEFORE the
  implementation (RED-GREEN pattern); `core/` is untouched
- **Backward compatible**: `chat_stream` defaults unchanged,
  `PermissionManager` / `ToolExecutor` / `LlamaClient` unchanged

## Dependency graph

```
T1.1 ─▶ T1.2 ──────────────────────────────────────┐
                                                      │
T2.1 ─▶ T2.2 ──────────────────────────────────────┤
                                                      │
T3.1 ─▶ T3.2 ──────────────────────────────────────┤
                                                      ├─▶ T4.1 ─▶ T4.2 ─▶ T5.1 ─▶ T5.2 ─▶ T5.3 ─▶ T6.1
                                                      │
(no preceding deps)                                  │
```

Phases 1, 2, 3 are independent of each other (different files).
Phase 4 depends on all three (it consumes the symbols they add).
Phases 5 and 6 are sequential cleanup.
