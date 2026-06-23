# Design: v0.4.0 Tool-Calling Core

Surgical core-layer extension: two new wx-free modules (`PermissionManager`, `ToolExecutor`) plus a 5-site edit to `LlamaClient`. UI dialog, tool catalog, and `shell_execute` registration are deferred to PROMPT_TOOL_CALLING2.

## Technical Approach

`PermissionManager` classifies command risk via `re` patterns and holds ephemeral session grants in a `set[str]`. `ToolExecutor` wraps `subprocess.run` for PowerShell on win32, returning a `ToolResult` with two serializers. `LlamaClient.chat_stream` gains two optional params (`on_tool_call`, `tools`) flowing through the existing daemon-thread bridge; a per-stream `_tc_buffer` accumulates split `arguments` fragments and dispatches via `wx.CallAfter` on `finish_reason == "tool_calls"`. All v0.3.0 contracts preserved when both new params are `None`.

## File Changes

### `ollamachat/core/permission_manager.py` (NEW)

Headless risk classifier + session grant store. `RiskLevel(enum.Enum)` with GREEN/YELLOW/RED. `PermissionManager.classify_risk(command) -> RiskLevel` matches lowercased input against red-then-yellow pattern lists; falls back to GREEN. `is_system_destructive(command) -> bool` returns True ONLY for `c:\windows`, `c:\system32`, `c:\program files`, `c:\program files (x86)`, `format-volume`, `clear-disk`. Session grants: `grant_session`, `has_session_grant`, `revoke_session`, `revoke_all` — all operate on an in-memory `set[str]`. Imports: `enum`, `re` only. No wx, no I/O.

**Rationale**: Spec requires risk classification to be pure (no raise, no mutate) and system-destructive to NEVER flag user directories. The apply prompt's regex lists are the authoritative pattern set.

### `ollamachat/core/tool_executor.py` (NEW)

`ToolResult` data class with `to_display_text()` (multi-line chat transcript format) and `to_tool_message()` (OpenAI `role: tool` dict). `ToolExecutor.run(tool_name, command, timeout=30.0) -> ToolResult`: on non-win32 returns error result immediately; on win32 probes `pwsh.exe` (falls back to `powershell.exe`), runs with `CREATE_NO_WINDOW`, truncates stdout/stderr independently to `MAX_OUTPUT_CHARS = 4000`. All exceptions caught and converted to `ToolResult(returncode=1)`. Imports: `subprocess`, `sys` only.

**Rationale**: Spec requires `ToolExecutor.run` to NEVER raise. The non-win32 early return lets WSL tests run without mocking subprocess for the platform check.

### `ollamachat/core/llama_client.py` (EDIT — surgical, 5 sites only)

See "Surgical Diff Boundary" section below. No other lines change.

### `tests/core/test_permission_manager.py` (NEW, 10 tests)

Covers: risk classification (green/yellow/red), case-insensitivity, `is_system_destructive` for each system path, the CRITICAL user-dir negative case, `format-volume`, and session grant/revoke/revoke_all.

### `tests/core/test_tool_executor.py` (NEW, 5 tests)

Covers: non-win32 error result, `to_display_text` format, `to_tool_message` shape, stderr in tool message, `MAX_OUTPUT_CHARS` truncation.

### `tests/core/test_llama_client.py` (EXTEND, +4 tests)

Covers: body contains `tools` when provided, body has no `tools` key when `None`, `on_tool_call` fires on `finish_reason="tool_calls"`, split-argument accumulation across 3 SSE chunks.

## Surgical Diff Boundary — `llama_client.py`

Exactly 5 sites change. Everything else is PRESERVED VERBATIM.

| Site | Location | Change |
|------|----------|--------|
| 1 | `chat_stream` signature (line ~77) | Add `on_tool_call: Callable[[str, str, dict], None] \| None = None` and `tools: list[dict] \| None = None` as optional keyword params |
| 2 | `Thread.args=...` tuple (line ~121) | Extend to `(messages, options, on_token, on_done, on_error, on_usage, on_tool_call, tools)` |
| 3 | `_stream_worker` signature (line ~130) | Add same two params with same defaults |
| 4 | Body construction (after line ~159) | `if tools is not None: body["tools"] = tools; body["tool_choice"] = "auto"` |
| 5 | SSE loop (inside the `for line in response.iter_lines()` block) | Add `_tc_buffer: dict[int, dict] = {}` before the loop. Inside the loop, before content extraction: extract `finish_reason` and `tool_calls_delta`, accumulate by index (stamp `id`/`name` once, concatenate `arguments`). After the loop body for each chunk: if `finish_reason == "tool_calls"` and `on_tool_call is not None`, iterate buffer, `json.loads` arguments (fallback `{"raw": ...}`), dispatch via `wx.CallAfter`, then `_tc_buffer.clear()` |

**Preserved verbatim**: `on_usage` plumbing, SSE parser structure, abort event logic, daemon thread creation, `wx` import-inside-worker pattern, `check_running`, `get_loaded_model`, `abort`, error handling, docstrings for existing methods. Apply must NOT "improve" surrounding code.

## TDD Ordering

Strict RED-GREEN-REFACTOR, one test at a time:

1. **RED**: Write `tests/core/test_permission_manager.py` (10 tests) → run `uv run --no-sync pytest tests/core/test_permission_manager.py -xvs` → all fail
2. **GREEN**: Write `ollamachat/core/permission_manager.py` → all 10 pass
3. **RED**: Write `tests/core/test_tool_executor.py` (5 tests) → run `uv run --no-sync pytest tests/core/test_tool_executor.py -xvs` → all fail
4. **GREEN**: Write `ollamachat/core/tool_executor.py` → all 5 pass
5. **RED**: Extend `tests/core/test_llama_client.py` with 4 new tests → run `uv run --no-sync pytest tests/core/test_llama_client.py -xvs` → 4 new fail, existing pass
6. **GREEN**: Surgical edit to `ollamachat/core/llama_client.py` → all pass

**Final verification**: `uv run --no-sync pytest tests/core/ -xvs` → 159/159 (140 prior + 10 + 5 + 4).

## Cross-Cutting Concerns

| Concern | Rule |
|---------|------|
| **wx import boundary** | `permission_manager.py` and `tool_executor.py` import NO wx. `llama_client.py` keeps its existing pattern: `import wx` inside `_stream_worker`. The new `on_tool_call` dispatch uses the same `wx.CallAfter` bridge. |
| **Threading** | `chat_stream` continues to spawn a daemon `threading.Thread`. `_tc_buffer` is a local dict inside `_stream_worker`; cleared after dispatch. No shared state with main thread except existing callbacks. |
| **Error containment** | `ToolExecutor.run` MUST never raise — all subprocess exceptions → `ToolResult(returncode=1, stderr=...)`. `PermissionManager.classify_risk` MUST never raise — pattern match is best-effort. |
| **Encoding** | Tool output: `encoding="utf-8", errors="replace"`. JSON in SSE: existing parser (no changes). |
| **Cross-platform** | `ToolExecutor.run` returns non-zero `ToolResult` on non-win32. Tests use `unittest.mock.patch("sys.platform", "linux")` to simulate WSL. |

## What This Design Does NOT Cover

- UI permission dialog (PROMPT_TOOL_CALLING2)
- Tool catalog / `shell_execute` registration (PROMPT_TOOL_CALLING2)
- Persisting permissions to disk (intentional non-goal — security boundary)
- Cross-platform execution (intentional non-goal)
- Version bump in `pyproject.toml` (deferred to PROMPT_TOOL_CALLING2)
- Any file under `ollamachat/ui/` or `tests/ui/`

## Risk Register

| Risk | Likelihood | Mitigation | Owner |
|------|-----------|------------|-------|
| `is_system_destructive` regex flags user dir by accident | Med | `test_is_system_destructive_user_dir_returns_false` is the locked CRITICAL test | Apply phase |
| `json.loads(entry["arguments"])` raises on malformed JSON | Med | `try/except JSONDecodeError` → `{"raw": entry["arguments"]}` fallback; tested by buffer-accumulation test | Apply phase |
| Surgical edit accidentally touches surrounding code | Med | Verify phase reads ALL changed files line-by-line; diff must show exactly 5 sites | Verify phase |

## Open Questions

None. All technical decisions are resolved in the proposal and specs.
