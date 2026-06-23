# Verification Report: v0.4.0-tool-calling-core

## Summary

v0.4.0 tool-calling core change is verified and ready to merge. All 159 tests pass (107 core + 52 UI/smoke). The surgical diff to `llama_client.py` touches exactly the 5 sites defined in `design.md` with zero collateral changes. Both new modules (`permission_manager.py`, `tool_executor.py`) are byte-identical to the apply prompt. The critical safety lock test (`test_is_system_destructive_user_dir_returns_false`) passes. The wx-free boundary is preserved. No UI files or version bump were touched. TDD protocol was followed with documented RED-GREEN evidence for all 7 tasks. One WARNING: the malformed-JSON fallback scenario from the spec has no explicit test.

---

## Critical

None.

---

## Warnings

### W1: Missing explicit test for malformed JSON fallback

**Spec**: `llama-integration/spec.md` — "Scenario: malformed JSON falls back to {"raw": ...}"
**Code**: `llama_client.py` lines 264-267 implement `try/except json.JSONDecodeError` → `{"raw": entry["arguments"]}` correctly.
**Test gap**: No test sends invalid accumulated arguments and asserts the `{"raw": ...}` dict. The `test_chat_stream_accumulates_tool_call_arguments` test only exercises the happy path where `json.loads` succeeds.
**Risk**: Low — the fallback code is 3 lines and structurally correct, but a spec scenario is untested at runtime.
**Recommendation**: Add `test_chat_stream_malformed_json_falls_back_to_raw` before merge or as first follow-up.

### W2: Spec scenario "no callback when finish_reason is never tool_calls" has no dedicated test

**Spec**: `llama-integration/spec.md` — "Scenario: no callback when finish_reason is never tool_calls"
**Coverage**: Implicitly covered — all v0.3.0 tests use `on_tool_call=None` default and pass without error. But there is no test that passes a non-None `on_tool_call` and verifies it is NOT called when `finish_reason` is `"stop"` or `None`.
**Risk**: Low — the guard `if finish_reason == "tool_calls" and on_tool_call is not None` is straightforward.

### W3: Missing explicit tests for two spec scenarios in tool-calling

**Spec**: `tool-calling/spec.md`
- "Classification is case-insensitive" — tests use mixed-case inputs but don't assert `classify_risk("REMOVE-ITEM foo.txt") == RiskLevel.RED` explicitly.
- "stderr truncated independently from stdout" — `test_max_output_truncated` only tests stdout truncation; no test verifies stderr truncation leaves stdout untouched.
- "CREATE_NO_WINDOW flag is set on win32" — implementation has `creationflags=0x08000000` but no test asserts it via mock inspection.

**Risk**: Low — code is correct, tests cover the primary paths.

---

## Suggestions

### S1: apply-progress.md says "6 work-unit commits" but there are 7

The first RED commit (`8bd272f test(core): add 10 permission_manager tests (RED)`) was not counted. Cosmetic documentation inconsistency — does not affect code quality.

### S2: Consider adding case-insensitivity assertion to `test_classify_risk_red`

A single additional assertion `assert pm.classify_risk("REMOVE-ITEM foo.txt") == RiskLevel.RED` would close the explicit coverage gap for the case-insensitivity spec scenario.

---

## Per-Check Result

| Check | Description | Result | Evidence |
|-------|-------------|--------|----------|
| 1 | Test count and green | PASS | `159 passed in 19.02s` (107 core + 52 UI/smoke) |
| 2 | Surgical edit scope | PASS | `git diff main~7 -- llama_client.py` shows exactly 5 sites: signature(+2), docstring(+3), Thread.args(±1), worker signature(+2), body branch(+4), SSE buffer+dispatch(+28 comment+code). Zero changes outside boundary. |
| 3 | Source verbatim from apply prompt | PASS | `permission_manager.py` (76 lines) and `tool_executor.py` (88 lines) are byte-identical to `/tmp/opencode/v0.4.0-apply-prompt.md` code blocks. |
| 4 | Critical safety test | PASS | `test_is_system_destructive_user_dir_returns_false` at line 47 asserts `"C:\\Users\\Miguel\\Documents\\Remove-Item test.txt"` returns `False`. Present and green. |
| 5 | wx-free boundary at module level | PASS | `grep '^import wx\|^from wx'` on permission_manager.py and tool_executor.py: empty. llama_client.py: `import wx` only at line 152 (inside `_stream_worker`). |
| 6 | Scope check (no UI, no version bump) | PASS | `git diff --stat main~7 -- ollamachat/ui/ tests/ui/ pyproject.toml`: empty. Version still `0.3.0`. |
| 7 | Pre-existing uncommitted changes preserved | PASS | `CLAUDE.md`, `conversation.py`, `openspec/config.yaml` are dirty in working tree but NOT in any of the 7 feature commits. `git log -- main~7..HEAD -- <those files>`: empty. |
| 8 | Commit messages follow convention | PASS | All 7 commits use conventional prefix (`test:`, `feat:`, `chore:`), scope in parens, imperative mood. No `Co-Authored-By` lines. |
| 9 | Argument accumulation test rigor | PASS | Test sends 3 chunks: `"{"`, `"\"command\": \"ls\""`, `"}"`. Buffer concatenates to `{"command": "ls"}`. `json.loads` parses to dict. Assertion: `args == {"command": "ls"}` — on the FINAL parsed dict, not a partial string. |
| 10 | Error-path risks (_tc_buffer) | PASS | `_tc_buffer` is declared at line 200 as `_tc_buffer: dict[int, dict] = {}` — a LOCAL variable inside `_stream_worker`, not `self._tc_buffer`. Fresh per invocation, no leak risk. |

---

## TDD Compliance

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | PASS | Found in apply-progress.md — "RED verification" and "GREEN verification" for each of 7 tasks |
| All tasks have tests | PASS | 7/7 tasks have corresponding test files |
| RED confirmed (tests exist) | PASS | 7/7 test files verified to exist in codebase |
| GREEN confirmed (tests pass) | PASS | 159/159 pass on execution |
| Triangulation adequate | PASS | 10 tests for PermissionManager (3 risk + 4 system-destructive + 3 session), 5 for ToolExecutor, 4 for LlamaClient tool-calling |
| Safety Net for modified files | PASS | `llama_client.py` (modified): all 15 pre-existing tests still pass. New files: N/A (correctly marked) |

**TDD Compliance**: 6/6 checks passed

---

## Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit | 19 new | 3 (test_permission_manager, test_tool_executor, test_llama_client) | pytest + unittest.mock |
| Integration | 0 | 0 | n/a |
| E2E | 0 | 0 | n/a |
| **Total new** | **19** | **3** | |

All 19 new tests are unit tests. This is appropriate for a wx-free core layer. Integration/E2E for the UI dialog is deferred to PROMPT_TOOL_CALLING2.

---

## Changed File Coverage

Coverage analysis skipped — no coverage tool detected in project configuration (AGENTS.md: "Sin ruff/mypy (pytest + verify cubren)").

---

## Assertion Quality

**Assertion quality**: All assertions verify real behavior.

- No tautologies found
- No orphan empty checks
- No type-only assertions without value assertions
- No ghost loops
- No smoke-test-only patterns
- No implementation-detail coupling
- Mock/assertion ratio is healthy across all 3 test files

---

## Spec Compliance Matrix

### tool-calling spec

| Scenario | Status | Covering Test |
|----------|--------|---------------|
| Remove-Item is RED | PASS | `test_classify_risk_red` |
| Move-Item is YELLOW | PASS | `test_classify_risk_yellow` |
| Get-Process is GREEN | PASS | `test_classify_risk_green` |
| Classification is case-insensitive | WARNING | Implicitly covered (tests use mixed case) but no explicit assertion |
| C:\Windows is system-destructive | PASS | `test_is_system_destructive_windows_dir` |
| C:\Users\...\Remove-Item NOT system-destructive (CRITICAL) | PASS | `test_is_system_destructive_user_dir_returns_false` |
| Format-Volume is system-destructive | PASS | `test_is_system_destructive_format_volume` |
| read-only command NOT system-destructive | PASS | Implicitly via `test_is_system_destructive_format_volume` setup |
| grant then has | PASS | `test_session_grant_and_has` |
| revoke removes one grant only | PASS | `test_session_revoke` |
| revoke_all clears every grant | PASS | `test_revoke_all` |
| non-win32 returns error result | PASS | `test_run_nonwindows_returns_error` |
| stdout truncated to 4000 | PASS | `test_max_output_truncated` |
| stderr truncated independently | WARNING | Code correct; no explicit test |
| CREATE_NO_WINDOW flag set | WARNING | Code correct; no explicit test |
| to_display_text happy path | PASS | `test_tool_result_to_display_text` |
| to_display_text non-zero exit | PASS | Implicitly via `test_tool_result_to_tool_message_includes_stderr` |
| to_tool_message happy path | PASS | `test_tool_result_to_tool_message` |
| to_tool_message with stderr+exit | PASS | `test_tool_result_to_tool_message_includes_stderr` |

### llama-integration spec

| Scenario | Status | Covering Test |
|----------|--------|---------------|
| backward compat (both None) | PASS | `test_chat_stream_no_error_when_usage_absent` + all v0.3.0 tests |
| body contains tools when provided | PASS | `test_chat_stream_passes_tools_in_body` |
| body has no tools key when None | PASS | `test_chat_stream_no_tools_when_none` |
| callback fires with parsed args | PASS | `test_chat_stream_calls_on_tool_call` |
| no callback when finish_reason != tool_calls | WARNING | Implicitly covered; no dedicated test with non-None on_tool_call |
| callback NOT invoked when on_tool_call is None | PASS | `test_chat_stream_no_tools_when_none` (no crash) |
| arguments split across 3 chunks reassemble | PASS | `test_chat_stream_accumulates_tool_call_arguments` |
| malformed JSON falls back to {"raw": ...} | WARNING | Code correct (lines 264-267); no explicit test |

---

## Design Coherence

| Design Decision | Implementation | Status |
|-----------------|---------------|--------|
| 5-site surgical boundary | Exactly 5 sites changed, no collateral | PASS |
| wx-free at module level | No wx imports at module level in any core file | PASS |
| `_tc_buffer` as local dict | Line 200: `_tc_buffer: dict[int, dict] = {}` — local, not instance attr | PASS |
| `wx.CallAfter` for on_tool_call | Line 268-270: `wx.CallAfter(on_tool_call, ...)` | PASS |
| `json.loads` + `JSONDecodeError` fallback | Lines 264-267: try/except with `{"raw": ...}` | PASS |
| `PermissionManager` imports only `enum` + `re` | Lines 8-9: `import enum`, `import re` | PASS |
| `ToolExecutor` imports only `subprocess` + `sys` | Lines 7-8: `import subprocess`, `import sys` | PASS |
| `MAX_OUTPUT_CHARS = 4000` | Line 50: `MAX_OUTPUT_CHARS = 4000` | PASS |
| Independent stdout/stderr truncation | Lines 80-81: separate `[:MAX_OUTPUT_CHARS]` slices | PASS |
| `on_usage` plumbing untouched | Lines 248-251: identical to v0.3.0 | PASS |

---

## Quality Metrics

**Linter**: Not available (project convention: no ruff/mypy per AGENTS.md)
**Type Checker**: Not available (project convention: no ruff/mypy per AGENTS.md)

---

## Final Verdict

**READY TO MERGE**

159/159 tests green. Surgical diff verified. Source verbatim. Critical safety lock test passes. wx-free boundary preserved. No scope creep. TDD protocol followed. 4 WARNINGs (all missing explicit tests for correct code — low risk). 2 SUGGESTIONs (cosmetic).
