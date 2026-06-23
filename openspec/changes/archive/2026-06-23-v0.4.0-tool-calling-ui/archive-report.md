# Archive Report: v0.4.0-tool-calling-ui

**Status**: ARCHIVED
**Date**: 2026-06-23
**Archived to**: `openspec/changes/archive/2026-06-23-v0.4.0-tool-calling-ui/`
**Artifact store**: openspec

## Summary

v0.4.0-ui change shipped the UI layer of tool calling for OllamaChat. This completes the v0.4.0 tool-calling feature (core + UI). 1 new module (PermissionDialog), 3 extended UI files (chat_panel, params_panel, main_window), 4 new/extended test files (21 new AST tests), version 0.3.0→0.4.0, CHANGELOG and AGENTS updates. 7 in-scope commits (5 apply + 1 post-verify fix + 1 verify-report update). 186/186 tests passing.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| `tool-calling` | MODIFIED | 8 new UI requirements appended to `openspec/specs/tool-calling/spec.md`. Core 7 requirements unchanged, 8 UI requirements added under `## UI Layer Requirements (added in v0.4.0-ui)`. Total: 15 requirements. Purpose section updated to reflect UI layer addition. |

## Task Completion Gate Reconciliation

The tasks.md uses `[DONE]` markers (not `- [ ]` checkboxes) for all 11 tasks. apply-progress.md confirms 11/11 complete. verify-report confirms all tests pass (186/186). No stale checkbox reconciliation needed — the task artifact, apply-progress, and verify-report are consistent.

**Note**: The delta spec header states "This delta adds 7 requirements" but the document contains 8 `### Requirement:` blocks. The 8th requirement (ParamsPanel exposes a tools-enable toggle) has been part of the spec since the original proposal. The header discrepancy was inherited — the archive report records 8 UI requirements merged, which is the accurate count.

## Post-verify fix

Commit `9fb7f13 fix(tool-calling): persist tool_call_id through Conversation for second-turn round-trip` resolved the CRITICAL-1 bug found by sdd-verify-gentleman: `tool_call_id` was set on the local `tool_msg` dict but discarded by `Conversation.add_message("tool", tool_msg["content"])`, breaking the second-turn round-trip. The fix:

1. Extended `Conversation.add_message` with optional `tool_call_id` kwarg (persisted only when `role == "tool"`).
2. Updated `Conversation.get_messages_for_api` to propagate `tool_call_id` to the API message dict.
3. Updated `MainWindow._on_tool_result` to pass `tool_call_id=tool_call_id` to `add_message`.
4. Added 5 core tests in `test_conversation.py` (persistence, non-tool omission, get_messages_for_api inclusion, save/load round-trip, backward compat).
5. Added 1 AST regression test in `test_main_window_static.py`.
6. Updated the delta spec to prescribe the corrected behavior with 2 new scenarios.

## Test count delta

| State | Count | Notes |
|-------|-------|-------|
| Pre-v0.4.0-ui | 180 | 159 (pre-v0.4.0-core + core) + 21 (v0.4.0-core tests from apply) |
| Post-v0.4.0-ui (apply) | 180 | 159 + 21 new AST tests |
| Post-verify fix (commit 9fb7f13) | 186 | +5 core tool_call_id tests + 1 AST regression test |

Final: 186/186 tests passing.

## File count delta

- **Source**: 22 (pre) → 24 (post): +`permission_dialog.py`, +1 line each in `conversation.py` (tool_call_id extension)
- **Tests**: 6 core files (unchanged), 4 ui test files (3 extended + 1 new), 1 smoke file (unchanged)

## Commits (oldest to newest)

1. `5af4264 test(ui): add PermissionDialog with 8 AST tests + implementation (T1.1-T1.2)`
2. `d1fd31b feat(ui): add append_tool_output / blocked / denied + AST tests (T2.1-T2.2)`
3. `676223c feat(ui): add tools_checkbox + get_tools_enabled + AST tests (T3.1-T3.2)`
4. `7713277 feat(ui): add tool-calling integration in MainWindow + AST tests (T4.1-T4.2)`
5. `9c58d37 chore(release): bump version to 0.4.0 + docs`
6. `9fb7f13 fix(tool-calling): persist tool_call_id through Conversation for second-turn round-trip`
7. `628d0c4 docs(verify): mark v0.4.0-ui as READY TO ARCHIVE after CRITICAL-1 fix`

## WARNINGS and SUGGESTIONS from verify-report (deferred)

The following observations were recorded in the verify report as non-blocking. All are deferred to v0.5.0 or later:

- **WARNING-1**: `_continue_after_tool` accepts `tool_msg: dict` but never uses it (dead parameter).
- **WARNING-2**: `test_no_emoji_in_tool_prefixes` passes for a less-strict reason than its name implies.
- **WARNING-3**: `test_no_emoji_in_risk_labels` checks only the dict inside `_build_ui`, not the whole dialog.
- **WARNING-4**: `append_tool_blocked` uses `_preview` (80-char truncate) for the message_list display.
- **SUGGESTION-1**: Merge `send_message` and `_continue_after_tool` to reduce code duplication.
- **SUGGESTION-2**: Drop the dead `tool_msg` parameter from `_continue_after_tool`.

## Working tree residue (unchanged, pre-existing)

These files remain uncommitted and untouched by v0.4.0-ui:
- `CLAUDE.md` (modified) — SDD init artifact
- `openspec/config.yaml` (modified) — SDD init artifact
- `openspec/specs/llama-integration/spec.md` (modified) — SDD init artifact
- `openspec/changes/v0.4.0-tool-calling-core/apply-progress.md` (deleted) — SDD init artifact

## Source of Truth Updated

`openspec/specs/tool-calling/spec.md` — now contains both core (7) and UI (8) requirements. Future SDD work reads this merged file.

## Rollback

To roll back v0.4.0-ui:

1. `git revert` the 7 commits in reverse chronological order:
   ```
   git revert 628d0c4 9fb7f13 9c58d37 7713277 676223c d1fd31b 5af4264
   ```
   (resolve conflicts in CHANGELOG.md, AGENTS.md, pyproject.toml if other changes touched them)
2. `mv openspec/changes/archive/2026-06-23-v0.4.0-tool-calling-ui/ openspec/changes/v0.4.0-tool-calling-ui/`
3. Revert the main spec merge (restore `openspec/specs/tool-calling/spec.md` to pre-merge state: 7 core requirements only, original Purpose text).
4. `uv run --no-sync pytest -xvs` must pass at 180 (the pre-apply state, not pre-fix state, since the fix is also part of v0.4.0-ui).

Note: The main spec merge (`openspec/specs/tool-calling/spec.md`) is an uncommitted working tree edit. To fully restore pre-v0.4.0-core main spec state, the `openspec/specs/tool-calling/` directory must be restored from git (it was untracked before this change).

## SDD Cycle Complete

The change has been fully planned (proposal), specified (delta spec), designed (design), implemented (5 apply commits + 1 fix commit), verified (186/186 tests, verify report PASS), and archived. Ready for the next change.
