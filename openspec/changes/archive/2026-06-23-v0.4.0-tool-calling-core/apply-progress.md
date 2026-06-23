# Apply Progress: v0.4.0-tool-calling-core

> **Note**: This file was moved from `openspec/changes/v0.4.0-tool-calling-core/` to `openspec/changes/archive/2026-06-23-v0.4.0-tool-calling-core/` as part of the archive process. Contents are unchanged.

## Execution Summary

- **Status:** DONE — all 8 tasks completed
- **Test result:** 159/159 passed (107 core + 52 UI/smoke)
- **Commits:** 6 work-unit commits

## Task Log

### Task 1 — RED: PermissionManager tests

- **Status:** DONE
- **Commit:** 8bd272f0 (test(core): add 10 permission_manager tests (RED))
- **Files:** `tests/core/test_permission_manager.py` (new, 87 lines)
- **RED verification:** `uv run --no-sync pytest tests/core/test_permission_manager.py -xvs` → ModuleNotFoundError (expected)
- **Actions:** Wrote 10 test functions for RiskLevel classification, is_system_destructive, session grants

### Task 2 — GREEN: PermissionManager implementation

- **Status:** DONE
- **Commit:** 2d56480 (feat(core): add PermissionManager with risk + session grants)
- **Files:** `ollamachat/core/permission_manager.py` (new, 76 lines)
- **GREEN verification:** `uv run --no-sync pytest tests/core/test_permission_manager.py -xvs` → 10/10 pass
- **Actions:** Implemented RiskLevel enum, PermissionManager with classify_risk, is_system_destructive, grant_session, revoke_session, revoke_all, has_session_grant

### Task 3 — RED: ToolExecutor tests

- **Status:** DONE
- **Commit:** e6eaaa6 (test(core): add 5 tool_executor tests (RED))
- **Files:** `tests/core/test_tool_executor.py` (new, 65 lines)
- **RED verification:** `uv run --no-sync pytest tests/core/test_tool_executor.py -xvs` → ModuleNotFoundError (expected)
- **Actions:** Wrote 5 test functions for non-win32 error, to_display_text, to_tool_message, stderr integration, MAX_OUTPUT_CHARS truncation

### Task 4 — GREEN: ToolExecutor implementation

- **Status:** DONE
- **Commit:** bf4d41b (feat(core): add ToolExecutor with PowerShell wrapper)
- **Files:** `ollamachat/core/tool_executor.py` (new, 88 lines)
- **GREEN verification:** `uv run --no-sync pytest tests/core/test_tool_executor.py -xvs` → 5/5 pass
- **Actions:** Implemented ToolResult with to_display_text() and to_tool_message(), ToolExecutor with PowerShell subprocess wrapper, platform guard, MAX_OUTPUT_CHARS=4000

### Task 5 — RED: LlamaClient tool-calling tests

- **Status:** DONE
- **Commit:** 407b395 (test(core): add 4 tool_calls SSE tests for LlamaClient)
- **Files:** `tests/core/test_llama_client.py` (extended, +108 lines)
- **RED verification:** `uv run --no-sync pytest tests/core/test_llama_client.py -xvs` → 15 pass, 4 fail (TypeError: unexpected keyword argument)
- **Actions:** Appended 4 test functions for tools in body, no tools when None, on_tool_call dispatch, 3-chunk argument accumulation

### Task 6 — GREEN: Surgical edit to llama_client.py

- **Status:** DONE
- **Commit:** 9a13dd8 (feat(llama_client): stream tool_calls via on_tool_call + tools catalog)
- **Files:** `ollamachat/core/llama_client.py` (edited, ±53 lines net)
- **GREEN verification:** `uv run --no-sync pytest tests/core/test_llama_client.py -xvs` → 19/19 pass
- **Actions:** Applied 5 surgical edits per design.md boundary table:
  1. Added `on_tool_call` and `tools` params to `chat_stream` signature
  2. Extended `Thread.args` tuple to include both new params
  3. Added same params to `_stream_worker` signature
  4. Added `if tools is not None: body["tools"] = tools; body["tool_choice"] = "auto"` body branch
  5. Added `_tc_buffer` accumulation + `finish_reason == "tool_calls"` dispatch via `wx.CallAfter` with `json.loads`/`JSONDecodeError` fallback

### Task 7 — Final verification

- **Status:** DONE
- **Verification:** `uv run --no-sync pytest -xvs` → 159/159 passed (140 prior + 10 + 5 + 4)
- **Actions:** Ran full test suite including all core + UI AST + smoke tests

### Task 8 — Scope check

- **Status:** DONE
- **Verification:**
  - `git diff --stat HEAD~6..HEAD` → 6 files (3 new source + 2 new tests + 1 extended test = 476 insertions, 1 deletion)
  - `pyproject.toml` version: still `0.3.0` (no bump)
  - No files under `ollamachat/ui/` or `tests/ui/` touched
  - Pre-existing uncommitted changes (CLAUDE.md, conversation.py) not included in feature commits

## Gotchas and Learnings

- Llama-server splits tool_call `arguments` across multiple SSE chunks. The `_tc_buffer` accumulates by index, concatenating `function.arguments` strings. The accumulated JSON is parsed only when `finish_reason == "tool_calls"`.
- The `test_chat_stream_accumulates_tool_call_arguments` test was the most critical SSE test: it validates that 3 chunks with split `{`, `"command": "ls"`, and `}` fragments reassemble into `{"command": "ls"}`.
- Existing v0.3.0 tests (`test_chat_stream_no_error_when_usage_absent` etc.) pass because `on_tool_call=None` and `tools=None` defaults keep the original contract.
- WSL tests for `ToolExecutor` rely entirely on `sys.platform` mocking — no subprocess is invoked on non-Windows, which is verified by the test.

## Next Steps

- `sdd-verify` recommended for completeness check
- PROMPT_TOOL_CALLING2 for UI permission dialog, tool catalog, and `shell_execute` registration
- Version bump to 0.4.0 deferred to PROMPT_TOOL_CALLING2
