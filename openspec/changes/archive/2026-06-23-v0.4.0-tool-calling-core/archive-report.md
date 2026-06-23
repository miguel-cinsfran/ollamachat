# Archive Report: 2026-06-23-v0.4.0-tool-calling-core

**Status**: ARCHIVED

## Summary

This change shipped the v0.4.0 tool-calling core layer for OllamaChat: two new headless modules (`PermissionManager` with risk-level classification, system-path auto-block, and in-memory session grants; `ToolExecutor` with a PowerShell subprocess wrapper), plus a surgical edit to `LlamaClient.chat_stream` that adds `on_tool_call` and `tools` parameters (both defaulting to `None` for full v0.3.0 backward compatibility). Scope was strictly core-only — no UI dialogs, no tool catalog, no `shell_execute` registration, no version bump. 19 new unit tests across 3 test files bring the total to 159/159 passing (107 core + 52 UI/smoke). 7 work-unit commits (RED-GREEN TDD for each module plus a scope-check commit). The verification report classified the change as **READY TO MERGE** with 0 critical issues and 4 low-risk warnings (all missing explicit tests for correct code paths).

## Specs Synced

- **`tool-calling`** — **CREATED** as new capability at `openspec/specs/tool-calling/spec.md` (7 requirements: PermissionManager risk classification, system-path auto-block, session grants; ToolExecutor PowerShell wrapper, non-Windows guard; ToolResult display and tool-message formatting)
- **`llama-integration`** — **MODIFIED**: REQ-LLAMA-003 updated with `on_tool_call` and `tools` params + backward-compat guarantee; 3 new requirements added (REQ-LLAMA-017 on_tool_call callback, REQ-LLAMA-018 tools catalog, REQ-LLAMA-019 tool_call fragment accumulation)

### Task Completion Gate Reconciliation

All 8 implementation tasks in `tasks.md` used unchecked `- [ ]` markers (stale checkboxes from `sdd-apply`). The orchestrator explicitly instructed archive to proceed, citing apply-progress.md and verify-report.md as proof that every task was completed. All 8 tasks are DONE according to apply-progress.md (RED-GREEN evidence for each), verify-report.md confirms 159/159 tests pass and all design/spec checks pass, and the git log shows 7 commits implementing every task. The archive proceeded with this exceptional reconciliation. The archived `tasks.md` retains the original unchecked markers; the apply-progress.md is the authoritative source for completion status.

## Artifacts Archived

```
archive/2026-06-23-v0.4.0-tool-calling-core/
├── archive-report.md     ← this file
├── proposal.md           ← original change proposal (tool-calling safety architecture)
├── design.md             ← architecture, surgical diff boundary, sequence diagrams
├── tasks.md              ← 8 implementation tasks (all complete per apply-progress)
├── verify-report.md      ← 159/159 tests, 0 critical, 4 warnings, READY TO MERGE
├── apply-progress.md     ← RED-GREEN evidence for all 8 tasks
└── specs/                ← delta specs (2 subdirectories)
    ├── llama-integration/
    │   └── spec.md       ← delta for MODIFIED requirement + 3 ADDED requirements
    └── tool-calling/
        └── spec.md       ← full spec (new capability)
```

## Commits (7 work-unit commits, oldest to newest)

| Commit | Message | Files |
|--------|---------|-------|
| `8bd272f` | `test(core): add 10 permission_manager tests (RED)` | `test_permission_manager.py` (new) |
| `2d56480` | `feat(core): add PermissionManager with risk + session grants` | `permission_manager.py` (new) |
| `e6eaaa6` | `test(core): add 5 tool_executor tests (RED)` | `test_tool_executor.py` (new) |
| `bf4d41b` | `feat(core): add ToolExecutor with PowerShell wrapper` | `tool_executor.py` (new) |
| `407b395` | `test(core): add 4 tool_calls SSE tests for LlamaClient` | `test_llama_client.py` (extended) |
| `9a13dd8` | `feat(llama_client): stream tool_calls via on_tool_call + tools catalog` | `llama_client.py` (surgical edit) |
| `f69a0ea` | `chore(core): verify 159/159 + scope check (no UI, no version)` | (verification only) |

## Deferred to Follow-up

- **Permission dialog UI** — `wx.Dialog` with `wx.Button` nativos for approve/deny/always-allow (per v0.4.0 design.md)
- **Tool catalog** — OpenAI-style tool definition for `shell_execute`
- **`shell_execute` registration** — wiring the tool catalog into `chat_stream`
- **`pyproject.toml` version bump** — 0.3.0 → 0.4.0

All owned by `PROMPT_TOOL_CALLING2` (separate change).

## Open Follow-up Change

**`v0.4.0-tool-calling-ui`** — Permission dialog, tool catalog, `shell_execute` registration, and version bump.

## Source of Truth Updated

The following main specs now reflect v0.4.0 behavior:
- `openspec/specs/tool-calling/spec.md` (new)
- `openspec/specs/llama-integration/spec.md` (REQ-LLAMA-003 modified + REQ-LLAMA-017/018/019 added)

## Rollback

To revert: `git revert` the 7 commits in reverse chronological order (or a single revert of the merge commit if this was merged as a group). The commits are all on `main` as separate work-unit commits and can be reverted individually if needed. All 7 commits preserve the existing v0.3.0 contract — `chat_stream` with defaults is identical to before.

## Test Count Delta

| Version | Tests | Delta |
|---------|-------|-------|
| Pre-v0.4.0 (v0.3.0) | 140 | — |
| v0.4.0 | 159 | +19 |

## File Count Delta

| Version | Source Files | Delta |
|---------|-------------|-------|
| v0.3.0 | 20 | — |
| v0.4.0 | 22 | +2 |

New files in v0.4.0:
- `ollamachat/core/permission_manager.py` — risk classification, system-path auto-block, session grants
- `ollamachat/core/tool_executor.py` — PowerShell subprocess wrapper with ToolResult data class

New test files:
- `tests/core/test_permission_manager.py` — 10 tests
- `tests/core/test_tool_executor.py` — 5 tests
- `tests/core/test_llama_client.py` — +4 tool-calling tests (extended)

## SDD Cycle Complete

The change has been fully planned, proposed, specced, designed, implemented (8 tasks, 7 commits), verified (159/159 tests), and archived. Ready for the next change: **`v0.4.0-tool-calling-ui`**.
