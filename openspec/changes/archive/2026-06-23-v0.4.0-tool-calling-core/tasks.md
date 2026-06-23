# Tasks: v0.4.0 Tool-Calling Core

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~380 (2 new source ~180, 1 surgical edit ~30 net, 2 new test files ~130, 1 extended test ~40) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | single-pr-default (review_budget_lines: 800) |
| Chain strategy | not_applicable |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: not_applicable
400-line budget risk: Low

## 1. RED — PermissionManager tests

- [ ] 1.1 Create `tests/core/test_permission_manager.py` with 10 tests
  - **Files:** `tests/core/test_permission_manager.py` (new)
  - **Action:** Write verbatim test functions: `test_classify_risk_green`, `test_classify_risk_yellow`, `test_classify_risk_red`, `test_is_system_destructive_windows_dir`, `test_is_system_destructive_system32`, `test_is_system_destructive_user_dir_returns_false`, `test_is_system_destructive_format_volume`, `test_session_grant_and_has`, `test_session_revoke`, `test_revoke_all`. All import from `ollamachat.core.permission_manager`.
  - **Verify:** `uv run --no-sync pytest tests/core/test_permission_manager.py -xvs` → 10 failures (ImportError or NameError)
  - **Done when:** File exists, all 10 test names present, run shows 10 failures

## 2. GREEN — PermissionManager implementation

- [ ] 2.1 Create `ollamachat/core/permission_manager.py`
  - **Files:** `ollamachat/core/permission_manager.py` (new)
  - **Action:** Write verbatim from apply prompt: `RiskLevel(enum.Enum)` with GREEN/YELLOW/RED, `PermissionManager` class with `classify_risk`, `is_system_destructive`, `has_session_grant`, `grant_session`, `revoke_session`, `revoke_all`. Imports: `enum`, `re` only.
  - **Verify:** `uv run --no-sync pytest tests/core/test_permission_manager.py -xvs` → 10/10 pass
  - **Done when:** 10/10 green

## 3. RED — ToolExecutor tests

- [ ] 3.1 Create `tests/core/test_tool_executor.py` with 5 tests
  - **Files:** `tests/core/test_tool_executor.py` (new)
  - **Action:** Write verbatim test functions: `test_run_nonwindows_returns_error` (mock `sys.platform` to `"linux"`), `test_tool_result_to_display_text`, `test_tool_result_to_tool_message`, `test_tool_result_to_tool_message_includes_stderr`, `test_max_output_truncated`. All import from `ollamachat.core.tool_executor`.
  - **Verify:** `uv run --no-sync pytest tests/core/test_tool_executor.py -xvs` → 5 failures
  - **Done when:** 5 failures

## 4. GREEN — ToolExecutor implementation

- [ ] 4.1 Create `ollamachat/core/tool_executor.py`
  - **Files:** `ollamachat/core/tool_executor.py` (new)
  - **Action:** Write verbatim from apply prompt: `ToolResult` class with `to_display_text()` and `to_tool_message()`, `ToolExecutor` class with `MAX_OUTPUT_CHARS = 4000` and `run(tool_name, command, timeout=30.0)`. Imports: `subprocess`, `sys` only.
  - **Verify:** `uv run --no-sync pytest tests/core/test_tool_executor.py -xvs` → 5/5 pass
  - **Done when:** 5/5 green

## 5. RED — LlamaClient tool-calling tests

- [ ] 5.1 Extend `tests/core/test_llama_client.py` with 4 new tests
  - **Files:** `tests/core/test_llama_client.py` (extend)
  - **Action:** Append test functions: `test_chat_stream_passes_tools_in_body`, `test_chat_stream_no_tools_when_none`, `test_chat_stream_calls_on_tool_call`, `test_chat_stream_accumulates_tool_call_arguments`. Use existing test patterns (mock `requests.post`, mock `wx.CallAfter`).
  - **Verify:** `uv run --no-sync pytest tests/core/test_llama_client.py -xvs` → exactly 4 new failures, all prior tests pass
  - **Done when:** 4 new failures, prior tests green

## 6. GREEN — LlamaClient surgical edit

- [ ] 6.1 Apply 5-site edit to `ollamachat/core/llama_client.py`
  - **Files:** `ollamachat/core/llama_client.py` (edit)
  - **Action:** Per design.md "Surgical Diff Boundary" table: (1) add `on_tool_call` and `tools` params to `chat_stream` signature, (2) extend `Thread.args` tuple, (3) add same params to `_stream_worker` signature, (4) add `body["tools"]`/`body["tool_choice"]` branch when `tools is not None`, (5) add `_tc_buffer` accumulation and `finish_reason == "tool_calls"` dispatch with `json.loads` + `JSONDecodeError` fallback + `wx.CallAfter`. No other lines change.
  - **Verify:** `uv run --no-sync pytest tests/core/test_llama_client.py -xvs` → 4/4 new pass, all prior pass
  - **Done when:** 0 failures in `test_llama_client.py`

## 7. Final verification

- [ ] 7.1 Run full core test suite
  - **Files:** none
  - **Action:** Run `uv run --no-sync pytest tests/core/ -xvs`
  - **Verify:** 159/159 pass (140 prior + 10 + 5 + 4)
  - **Done when:** 159/159 green, 0 failures

## 8. Scope check

- [ ] 8.1 Confirm diff scope and version unchanged
  - **Files:** none
  - **Action:** Run `git diff --stat`. Confirm `pyproject.toml` still says `0.3.0`. Confirm no file under `ollamachat/ui/` is touched.
  - **Verify:** `git diff --stat` shows only 6 expected files (3 new source, 2 new tests, 1 extended test) plus any pre-existing uncommitted changes
  - **Done when:** Diff scope is correct, version unchanged

## Review Workload Forecast

- **Total changed lines (estimate)**: ~380 (2 new source files ~180 lines, 1 surgical edit ~30 lines net, 2 new test files ~130 lines, 1 extended test file ~40 lines new)
- **Chained PRs recommended**: No (single PR, within 800-line review budget)
- **400-line budget risk**: Low
- **Decision needed before apply**: No
- **Strategy**: Single PR with work-unit commits — one commit per RED-GREEN pair (tasks 1-6), plus scope-check commit (task 8). Per `work-unit-commits` skill: each commit is a reviewable work unit with tests alongside code.
