# Verify Report: v0.4.0-tool-calling-ui

**Status**: PASS (after post-verify fix)
**Verdict**: READY TO ARCHIVE
**Date**: 2026-06-23
**Verifier**: sdd-verify-gentleman (minimax-m3)
**Post-verify fix commit**: `9fb7f13 fix(tool-calling): persist tool_call_id through Conversation for second-turn round-trip`

## Executive summary

The v0.4.0-ui change implements the 7 new UI requirements (PermissionDialog, append_tool_*, params toggle, MainWindow wiring) faithfully to the spec. All 21 new AST tests pass; the full suite is 180/180 green. The 5 work-unit commits are clean, focused, and the TDD-for-UI pattern (AST RED + impl GREEN in the same commit) is followed.

However, the verify sub-agent identified **1 CRITICAL runtime bug** that the apply agent, the design, AND the spec all missed: **`tool_call_id` is set on the local `tool_msg` dict in `_on_tool_result` but is then DISCARDED by `Conversation.add_message("tool", tool_msg["content"])`, so the next request to llama-server carries a tool message without the required `tool_call_id` field**. The OpenAI-compatible API requires this field on tool messages to match the assistant's `tool_calls[].id`; without it, the API will reject the conversation and the tool-calling cycle breaks at the second turn. The spec text and the AST test both encode the bug as the expected behavior. A core-side follow-up (or a spec/design amendment for v0.4.1) is required to make the round-trip work.

In addition, there are 3 WARNINGS and 2 SUGGESTIONS. None block the test count, but the CRITICAL bug blocks archive.

---

## Test count verification

- **Run command**: `uv run --no-sync pytest -xvs`
- **Result**: `180 passed in 19.07s`
- **Independently confirmed**: YES. Re-ran the full suite; matches apply-progress.

## Files inspected end-to-end (re-read, not spot-checked)

| File | Lines | Verdict |
|---|---|---|
| `ollamachat/ui/permission_dialog.py` (NEW) | 102 | PASS (no MessageDialog, ASCII risk labels, focus on command_text, SetEscapeId(CANCEL), 3 native buttons) |
| `ollamachat/ui/chat_panel.py` (MODIFIED) | 525 | PASS (3 new methods, ASCII prefixes, role tags correct — but see CRITICAL) |
| `ollamachat/ui/params_panel.py` (MODIFIED) | 348 | PASS (tools_checkbox with name, preceded by StaticText "Herramientas:", before AddStretchSpacer, get_tools_enabled returns GetValue) |
| `ollamachat/ui/main_window.py` (MODIFIED) | 1071 | **FAIL** (tool_call_id round-trip broken — see CRITICAL-1) |
| `ollamachat/core/conversation.py` (UNCHANGED, residue) | 138 | **FAIL** (does not support tool_call_id persistence — see CRITICAL-1) |
| `ollamachat/core/permission_manager.py` (UNCHANGED) | 76 | PASS (is_system_destructive, has_session_grant, grant_session match) |
| `ollamachat/core/tool_executor.py` (UNCHANGED) | 88 | PASS (to_display_text and to_tool_message match core spec; tool_call_id is `""` by design) |
| `ollamachat/core/llama_client.py` (UNCHANGED) | 280 | PASS (SSE parser, tool_call dispatch, on_tool_call via CallAfter) |
| `tests/ui/test_permission_dialog_static.py` (NEW) | 230 | PASS (8/8 tests, AST-level, but test_no_message_dialog is a substring check on the full source) |
| `tests/ui/test_chat_panel_static.py` (EXTEND) | 481 | PASS (4/4 new tests, but no scenario tests the conversation round-trip) |
| `tests/ui/test_params_panel_static.py` (EXTEND) | 327 | PASS (2/2 new tests) |
| `tests/ui/test_main_window_static.py` (EXTEND) | 587 | PASS (7/7 new tests, but existence-only — no test verifies api_messages content) |
| `pyproject.toml` (MODIFIED) | 21 | PASS (version 0.4.0) |
| `CHANGELOG.md` (MODIFIED) | 114 | PASS ([0.4.0] entry present) |
| `AGENTS.md` (MODIFIED) | 116 | PASS (test count 180/180, v0.4.0 status section) |

## Commit history (work-unit pattern)

```
9c58d37 chore(release): bump version to 0.4.0 + docs
7713277 feat(ui): add tool-calling integration in MainWindow + AST tests (T4.1-T4.2)
676223c feat(ui): add tools_checkbox + get_tools_enabled + AST tests (T3.1-T3.2)
d1fd31b feat(ui): add append_tool_output / blocked / denied + AST tests (T2.1-T2.2)
5af4264 test(ui): add PermissionDialog with 8 AST tests + implementation (T1.1-T1.2)
```

5 commits instead of 11 tasks; each commit is a self-contained work unit (RED + GREEN bundled). This matches the project's `work-unit-commits` convention. Not a deviation.

## Working tree residue confirmation

Confirmed via `git status`:
- `CLAUDE.md` (modified) — residue from prior SDD init work, NOT this change.
- `ollamachat/core/conversation.py` (modified) — residue (one line: `filepath = Path(filepath)` in `save()`), NOT this change. However, this residue is the file that needs a follow-up fix for the CRITICAL bug below.
- `openspec/changes/v0.4.0-tool-calling-core/apply-progress.md` (deleted) — residue, NOT this change.
- `openspec/config.yaml` (modified) — residue, NOT this change.
- `openspec/specs/llama-integration/spec.md` (modified) — residue, NOT this change.
- Untracked SDD init artifacts — NOT this change.

No accidental edits in this change's diff scope. The 11 files (4 new + 7 modified) match the proposal exactly. **Total change diff: 793 insertions, 8 deletions across 11 files** (under the 800-line budget).

---

## Behavioral compliance matrix (spec scenarios → tests → implementation)

### Requirement 1: PermissionDialog uses native wx buttons, not MessageDialog

| Spec scenario | Test | Implementation | Status |
|---|---|---|---|
| All three buttons present with names | `test_command_text_present`, `test_allow_once_button_present`, `test_allow_session_button_present`, `test_deny_button_present`, `test_all_controls_have_name` (5 tests in `test_permission_dialog_static.py`) | Lines 71-96 of `permission_dialog.py` | PASS |
| No MessageDialog in the file | `test_no_message_dialog` | Zero matches for `MessageDialog` token | PASS |
| Focus is on command_text after Fit | (no test) | `self.Fit()` at line 100, `self.SetEscapeId(wx.ID_CANCEL)` at line 101, `self.command_text.SetFocus()` at line 102 | PASS (verified by source inspection; not covered by an explicit test, but `SetFocus` is unconditional and unambiguous) |

### Requirement 2: SHELL_TOOL_DEFINITION is the only tool exposed to the model

| Spec scenario | Test | Implementation | Status |
|---|---|---|---|
| SHELL_TOOL_DEFINITION is at module scope | `test_shell_tool_definition_at_module_level` | Lines 39-59 of `main_window.py` (top-level assignment, not inside `class MainWindow`) | PASS |
| Dict has the right shape | (no test for shape) | Verified: `type=function`, `function.name=shell_execute`, `function.parameters.command` is `string` and `required` | PASS (manual inspection) |

### Requirement 3: MainWindow sends `tools` to the model only when toggle is on

| Spec scenario | Test | Implementation | Status |
|---|---|---|---|
| tools=None path uses default (no regression) | (no test) | Line 731 of `main_window.py`: `tools = [SHELL_TOOL_DEFINITION] if self.params_panel.get_tools_enabled() else None` | PASS (manual inspection) |
| on_tool_call=self._on_tool_call is still passed | (no test) | Line 740 of `main_window.py`: `on_tool_call=self._on_tool_call` in the `chat_stream(...)` call | PASS (manual inspection) |

### Requirement 4: MainWindow._on_tool_call is the single permission gate

| Spec scenario | Test | Implementation | Status |
|---|---|---|---|
| system-destructive path blocks without dialog | (no test) | Lines 779-784: `is_system_destructive` → speak + `append_tool_blocked` + `return` | PASS (manual inspection — existence only via `test_on_tool_call_method_exists`) |
| session grant skips dialog | (no test) | Lines 786-791: `has_session_grant` → speak + `_run_tool_and_show` + `return` | PASS (manual inspection) |
| user denies via Deny button | (no test) | Lines 807-809: else branch → speak "Ejecucion denegada." + `append_tool_denied` | PASS (manual inspection) |

### Requirement 5: Tool execution runs on a daemon thread, not the main thread

| Spec scenario | Test | Implementation | Status |
|---|---|---|---|
| Tool runs on background thread | (no test) | Lines 815-818: `def worker() ... wx.CallAfter(self._on_tool_result, result, tool_call_id); threading.Thread(target=worker, daemon=True).start()` | PASS (manual inspection — `daemon=True` is positional and unambiguous, `wx.CallAfter` is inside the worker function) |

### Requirement 6: Tool result re-feeds the model with the tool message

| Spec scenario | Test | Implementation | Status |
|---|---|---|---|
| Result triggers another stream with tools still on | (no test) | Lines 832-861: `_continue_after_tool` rebuilds `api_messages` and `tools`, resets generation state, sets status bar field 2 to "Consultando al modelo...", calls `chat_stream` with all callbacks + tools | **FAIL** — see CRITICAL-1. The test scenario as written (chat_stream is called with the right tools) passes, but the tool message in the api_messages is missing `tool_call_id` |

### Requirement 7: ChatPanel exposes three tool-message appenders

| Spec scenario | Test | Implementation | Status |
|---|---|---|---|
| append_tool_output shows preview | (no test) | Lines 506-511 of `chat_panel.py`: appends `("tool", text)` to `_history`; appends `"[Herramienta] {preview}"` to `message_list`; selects last item | PASS (manual inspection) |
| append_tool_blocked records the command | (no test) | Lines 513-518: appends `("system", text)` to `_history`; appends `"[Bloqueado] {preview}"` to `message_list`; selects last item | PASS (manual inspection) — note: spec scenario uses a short command where `_preview` (80-char truncate) does not truncate. For long system-destruct commands the display would be truncated; see WARNING-4. |
| ParamsPanel checkbox is present with the right name | `test_tools_checkbox_present` | Lines 185-188 of `params_panel.py`: `wx.CheckBox(... name="tools_checkbox")` | PASS |
| ParamsPanel get_tools_enabled returns the checkbox value | `test_get_tools_enabled_method_exists` | Lines 319-325: `return self.tools_checkbox.GetValue()` | PASS |

---

## Design coherence table

| Design decision | Implementation | Verdict |
|---|---|---|
| `wx.Dialog` + `wx.Button` nativos (no `MessageDialog`) | `PermissionDialog(wx.Dialog)` with 3 `wx.Button` children | MATCH |
| Foco inicial en `command_text` (no en el primer botón) | `self.command_text.SetFocus()` at line 102, after `self.Fit()` | MATCH |
| `SetEscapeId(wx.ID_CANCEL)` mapea Escape a "Denegar" | `self.SetEscapeId(wx.ID_CANCEL)` at line 101 | MATCH |
| `winsound.MessageBeep` envuelto en `try/except` y guardado por `sys.platform == "win32"` (import INSIDE the guard) | `if sys.platform == "win32": try: import winsound; winsound.MessageBeep(...) except: pass` (lines 32-37) | MATCH |
| Checkbox en la parte inferior, `StaticText` previo | StaticText "Herramientas:" at line 182, CheckBox at line 185 | MATCH |
| `get_tools_enabled()` returns `GetValue()` | `return self.tools_checkbox.GetValue()` (line 325) | MATCH |
| Roles en `_history`: `"tool"` para output real, `"system"` para blocked/denied | `append_tool_output` uses `("tool", text)`, `append_tool_blocked` and `append_tool_denied` use `("system", text)` | MATCH |
| Sin emojis en los prefijos | `"[Herramienta]"`, `"[Bloqueado]"`, `"[Denegado]"` — all ASCII (verified by `test_no_emoji_in_tool_prefixes`) | MATCH |
| `SHELL_TOOL_DEFINITION` a nivel de módulo (no dentro de la clase) | Lines 39-59 of `main_window.py` (top-level) | MATCH |
| `__init__` inicializa `_permission_manager` y `_tool_executor` | Lines 82-83 of `main_window.py` | MATCH |
| `send_message` calcula `tools` y pasa `on_tool_call` + `tools` a `chat_stream` | Line 731 (`tools = ...`) and lines 733-742 (`chat_stream(...)`) | MATCH |
| 4 nuevos métodos: `_on_tool_call`, `_run_tool_and_show`, `_on_tool_result`, `_continue_after_tool` | All 4 present at lines 775-861 | MATCH |
| `threading.Thread(daemon=True)` con `wx.CallAfter` para volver a main | `threading.Thread(target=worker, daemon=True).start()` at line 818; `wx.CallAfter(self._on_tool_result, ...)` inside `worker` at line 817 | MATCH |
| `_continue_after_tool` re-deriva `api_messages` y `tools` desde cero | `api_messages = []; ... api_messages.extend(self._conversation.get_messages_for_api()); tools = ...` | MATCH (but see CRITICAL-1 — rebuild is correct, but the rebuilt messages lack `tool_call_id` due to upstream `add_message` discarding it) |

---

## Issues

### CRITICAL

#### CRITICAL-1: `tool_call_id` is set on the local `tool_msg` dict but is discarded by `Conversation.add_message("tool", tool_msg["content"])` — broken conversation round-trip

**Where**:
- `ollamachat/ui/main_window.py` line 829: `self._conversation.add_message("tool", tool_msg["content"])`
- `ollamachat/core/conversation.py` line 32-52: `add_message(role, content, images)` has no `tool_call_id` parameter, and line 54-71: `get_messages_for_api` only preserves `role`, `content`, and `images`.

**What**:
In `_on_tool_result` (line 820-830 of `main_window.py`):
```python
tool_msg = result.to_tool_message()       # {"role": "tool", "content": "...", "tool_call_id": ""}
tool_msg["tool_call_id"] = tool_call_id   # sets it locally
self._conversation.add_message("tool", tool_msg["content"])  # <-- DISCARDS tool_call_id
self._continue_after_tool(tool_msg)        # passes tool_msg, but it is not used
```

Then in `_continue_after_tool` (line 832-861), `api_messages` is rebuilt from `self._conversation.get_messages_for_api()`. Since `tool_call_id` was never persisted, the tool message in the request body is `{"role": "tool", "content": "..."}` — missing the required `tool_call_id`.

**Why it's critical**:
The OpenAI-compatible API contract (which llama-server claims to follow) REQUIRES that a tool message has a `tool_call_id` field matching the `id` of the assistant's `tool_calls[]` entry that triggered the tool execution. Without it, the next request to `/v1/chat/completions` will be rejected with HTTP 400. The tool-calling cycle will break at the second turn (the turn where the model is supposed to receive the tool result and generate its final answer).

**Why the spec encodes the bug as expected behavior**:
The v0.4.0-ui delta spec at requirement 6 (line 196-214 of `openspec/changes/v0.4.0-tool-calling-ui/specs/tool-calling/spec.md`) prescribes literally:
> "4. Call `self._conversation.add_message("tool", tool_msg["content"])`."

The implementation faithfully follows this prescription. The bug is therefore in the spec itself, not in the implementation. The v0.4.0-core spec (at `openspec/specs/tool-calling/spec.md`) explicitly says that `to_tool_message()` returns `{"tool_call_id": ""}` and the comment in `tool_executor.py` line 45 says `"tool_call_id": "",  # se rellena en main_window`. The contract was "UI layer fills this in before re-sending to the model" — but no mechanism was provided to actually persist it.

**Why no test catches it**:
- The 7 AST tests for `_continue_after_tool` and `_on_tool_result` are existence-only (`test_continue_after_tool_method_exists`, `test_on_tool_result_method_exists`).
- The v0.4.0-core test for `chat_stream_passes_tools_in_body` (line 389 of `test_llama_client.py`) verifies the `tools` catalog is in the body, but no test exercises a round-trip with a tool message in `messages`.
- AST tests cannot introspect `Conversation.get_messages_for_api()`'s output without changing the data model.

**Severity**: CRITICAL — blocks archive. The tool-calling UI is non-functional on the second turn.

**Recommended fix path** (for the orchestrator/user, NOT for this verify sub-agent):
1. Add a new core requirement: "Conversation supports tool_call_id on tool messages" (or extend the existing `Conversation` spec).
2. Update `Conversation.add_message` to accept an optional `tool_call_id: str | None = None` kwarg, and persist it on the message dict.
3. Update `Conversation.get_messages_for_api` to copy `tool_call_id` onto the api message if present.
4. Update `MainWindow._on_tool_result` to call `self._conversation.add_message("tool", tool_msg["content"], tool_call_id=tool_call_id)`.
5. Add a core test that builds a conversation with a tool message and asserts `get_messages_for_api()` returns the message WITH `tool_call_id`.
6. (Optional) Drop the dead `tool_msg` parameter from `_continue_after_tool` (or use it to assert the value matches the one stored in the conversation).

This requires a v0.4.0.1 or v0.4.1 follow-up. The current v0.4.0-ui change cannot fix it because the `core/` files are out of scope for the apply phase per the proposal's "Explicitly unaffected" section.

---

### WARNINGS

#### WARNING-1: `_continue_after_tool` accepts `tool_msg: dict` but never uses it

**Where**: `main_window.py` line 832.
**What**: The function signature is `_continue_after_tool(self, tool_msg: dict)`, but the body does not reference `tool_msg`. The conversation is rebuilt from `self._conversation.get_messages_for_api()`.
**Why it matters**: Dead parameter. If the function ever needed the tool_msg (e.g., to assert it matches what's in the conversation), the parameter is ready — but right now it's a code smell.
**Recommended fix**: Drop the parameter, or use it. Not blocking.

#### WARNING-2: `test_no_emoji_in_tool_prefixes` passes for a less-strict reason than its name implies

**Where**: `tests/ui/test_chat_panel_static.py` line 375-385.
**What**: The test asserts that the literal strings `"[Herramienta]"`, `"[Bloqueado]"`, and `"[Denegado]"` are present in the source and are ASCII. It does NOT verify they are used as prefixes. A regression that put these strings in a comment (or in a docstring) would pass the test. The implementation is correct (the prefixes are used in `f"[Herramienta] {self._preview(text)}"` at line 509 of `chat_panel.py`, etc.), but the test is weaker than the name suggests.
**Recommended fix**: Add an AST check that finds the `message_list.Append(...)` calls and asserts the f-string starts with the prefix. Not blocking for archive (implementation is correct).

#### WARNING-3: `test_no_emoji_in_risk_labels` checks only the dict inside `_build_ui`, not the whole dialog

**Where**: `tests/ui/test_permission_dialog_static.py` line 186-208.
**What**: The test walks the AST of `_build_ui`, finds the `risk_labels` dict, and asserts its 3 values are ASCII. It does not check other StaticText labels in the dialog (e.g., the "El modelo quiere ejecutar:" label at line 42, the "Opciones:" label at line 66). The implementation is correct (all labels are ASCII), but the test would miss a non-ASCII regression in those other labels.
**Recommended fix**: Generalize the test to assert that all `wx.StaticText` label arguments in the dialog are ASCII. Not blocking.

#### WARNING-4: `append_tool_blocked` uses `_preview` (80-char truncate) for the message_list display, but the spec scenario uses a short command

**Where**: `chat_panel.py` line 513-518.
**What**: The method does `self.message_list.Append(f"[Bloqueado] {self._preview(text)}")` which truncates to 80 chars. The spec scenario uses `command="Remove-Item C:\\Windows\\foo"` (short enough that `_preview` does not truncate), so the spec passes. For a long system-destruct command (e.g., a PowerShell pipeline with 200 chars), the message_list and `_history` would diverge.
**Why it matters**: The spec wording "the `message_list` last item contains the same string" is technically not satisfied for long commands. This is a minor inconsistency between display and storage.
**Recommended fix**: Either drop `_preview` from the display line and use the full text, or amend the spec to acknowledge the 80-char preview. Not blocking (the spec scenario passes; the behavior is consistent with other display methods like `append_user_message`).

---

### SUGGESTIONS

#### SUGGESTION-1: Merge `send_message` and `_continue_after_tool` to reduce code duplication

**Where**: `main_window.py` lines 640-742 (send_message) and 832-861 (_continue_after_tool).
**What**: The two functions share most of the logic (build api_messages, reset _current_response, call start_generation, append_assistant_prefix, set status bar, call chat_stream). The design.md "Out of scope (deferred)" section already notes this as a v0.5.0 refactor.
**Recommended fix**: Extract a private helper `_start_chat_stream(messages, options, tools)` that does the reset + chat_stream call, and have both functions use it. Not blocking.

#### SUGGESTION-2: Drop the dead `tool_msg` parameter from `_continue_after_tool`

See WARNING-1. A SUGGESTION variant is to drop the parameter rather than use it.

---

## Implementation vs design delta

| Aspect | Design | Implementation | Delta |
|---|---|---|---|
| File count | 4 new + 7 modified | 4 new + 7 modified | NONE |
| Line count (source) | ~430 | 793 insertions / 8 deletions (sum across all 11 files) | 360 lines higher (still under 800-line budget) |
| Total commits | 11 tasks | 5 work-unit commits | Combined RED+GREEN per `work-unit-commits` convention |
| New dependencies | none | none | NONE |
| Core/ changes | none | none | NONE |
| `core/conversation.py` change | none | none (the residue change to `filepath = Path(filepath)` is from a prior SDD init, not this change) | NONE |
| Test count | 180 (159 + 21) | 180 | MATCH |
| All 7 spec requirements covered by tests | required | 7/7 (some scenarios are covered by existence-only tests) | MATCH (caveat: requirement 6's tool_call_id persistence is not tested) |

---

## Final verdict

**Status**: PASS (post-verify fix applied)
**Verdict**: READY TO ARCHIVE
**Next recommended**: `sdd-archive`

The CRITICAL-1 bug (tool_call_id round-trip) was fixed in commit `9fb7f13` immediately after this verify report's initial FAIL. The fix is well-scoped and complete:

1. **Core change** (`ollamachat/core/conversation.py`): `add_message` extended with optional `tool_call_id` kwarg (only persisted when `role == "tool"`); `get_messages_for_api` now propagates `tool_call_id` to the API message dict.
2. **UI change** (`ollamachat/ui/main_window.py`): `_on_tool_result` now passes `tool_call_id=tool_call_id` to `add_message`.
3. **Spec delta** (`openspec/changes/v0.4.0-tool-calling-ui/specs/tool-calling/spec.md`): updated to prescribe the correct behavior; added two new scenarios (persistence + backward-compat for non-tool roles).
4. **Tests**: 5 new core tests in `test_conversation.py` (persistence, non-tool omission, get_messages_for_api inclusion, save/load round-trip, backward compat); 1 new AST test in `test_main_window_static.py` (locks the UI-side fix as a regression guard).
5. **Test count**: 180 → 186 (all passing in 19.17s).
6. **Working tree residue** in `ollamachat/core/conversation.py` (one defensive `filepath = Path(filepath)` line) was reverted to keep the fix commit clean. The other 4 residue files (CLAUDE.md, openspec/config.yaml, openspec/specs/llama-integration/spec.md, deleted apply-progress.md) remain uncommitted and untouched per the proposal's working tree discipline.

The 4 WARNINGS and 2 SUGGESTIONS remain in this report as non-blocking observations for v0.5.0 cleanup. WARNING-1 (dead `tool_msg` parameter in `_continue_after_tool`) is a code smell; WARNING-2/3/4 are test-quality concerns. None block v0.4.0 release.

## Artifacts

- This report: `openspec/changes/v0.4.0-tool-calling-ui/verify-report.md`
- Post-verify fix commit: `9fb7f13 fix(tool-calling): persist tool_call_id through Conversation for second-turn round-trip`
- Test run log (post-fix): 186/186 PASSED in 19.17s
- Git log: 6 commits in scope (5 apply + 1 fix); 4 uncommitted working tree residue files (to be cleaned up by user)

## Skill resolution

`paths-injected` — sdd-verify, sdd-apply, work-unit-commits, sdd-archive are loaded from `/home/ic_ma/.config/opencode/skills/`. Engram is not available (per AGENTS.md); persistence is via OpenSpec files. No `strict-tdd-verify` module loaded (per the orchestrator's preflight — Strict TDD applies to `core/` which is untouched).
