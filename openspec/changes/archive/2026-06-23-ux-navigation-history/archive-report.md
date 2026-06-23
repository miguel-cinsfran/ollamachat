# Archive Report: 2026-06-22-ux-navigation-history (v0.3.0)

**Status**: ARCHIVED

## Summary

This change shipped the v0.3.0 UX navigation overhaul for OllamaChat: a dual-view chat panel (ListBox previews + stream display), message detail popup, browser rendering, accelerator-driven keyboard navigation (Alt+1..6, F2, F6), background-thread model loading with periodic voice announcements, deterministic initial focus, close-with-conversation confirmation, a model-aware window title, generation-progress beep on Windows, full token-usage capture from llama-server, system prompt persistence across conversation reloads, a `use_model_button` that loads and starts in one click, the `restart_server_button` rename, and the headless `strip_markdown()` utility. All 8 spec deltas were merged into their respective main specs; `text_utils` was added as a new capability. The codebase grew by 3 files (text_utils.py, message_detail_dialog.py, test_message_detail_dialog_static.py) and 32 tests (102 → 134), all passing.

## Spec Delta Merge Summary

| Capability | Requirements Added | Requirements Modified | Requirements Removed | Location in Main Spec |
|---|---|---|---|---|
| chat | 5 (Message Detail Dialog, Open in Browser, Context Menu, Public History Accessors, Ctrl+C Copies) | 1 (Read-only Conversation Display → dual-view) | 0 | `openspec/specs/chat/spec.md` — MODIFIED in ## Requirements, ADDED in ## Added in v0.3.0 |
| accessibility-guidelines | 3 (Full Keyboard Accelerator Table, F2 Session-Status Announcement, Listbox Printable-Key Routing) | 0 | 0 | `openspec/specs/accessibility-guidelines/spec.md` — ## Added in v0.3.0 |
| parameters | 2 (use_model_button, restart_server_button) | 0 | 0 | `openspec/specs/parameters/spec.md` — ## Added in v0.3.0 |
| conversation-persistence | 1 (System Prompt Survives Reload) | 1 (Disk Persistence save/load → includes system_prompt) | 0 | `openspec/specs/conversation-persistence/spec.md` — MODIFIED in ## Requirements, ADDED in ## Added in v0.3.0 |
| llama-integration | 0 | 1 (REQ-LLAMA-003: added optional on_usage callback) | 0 | `openspec/specs/llama-integration/spec.md` — REQ-LLAMA-003 updated in-place |
| app-shell | 5 (Background-Thread Model Loading, Deterministic Initial Focus, Close Confirmation, Window Title, Generation Beep) | 0 | 0 | `openspec/specs/app-shell/spec.md` — ## Added in v0.3.0 |
| speech | 3 (Generation-Beep Announcements, F2 Session Status, Loading Announcements) | 0 | 0 | `openspec/specs/speech/spec.md` — ## Added in v0.3.0 |
| text_utils | 2 (strip_markdown Removes Markdown Syntax, strip_markdown Is Pure and Headless) | — | 0 | `openspec/specs/text_utils/spec.md` — new capability, full spec |

**Totals**: 21 ADDED, 3 MODIFIED, 0 REMOVED requirements across 8 capabilities.

## Capability List

- **accessibility-guidelines** — Existing capability (updated)
- **app-shell** — Existing capability (updated)
- **chat** — Existing capability (updated)
- **conversation-persistence** — Existing capability (updated)
- **llama-integration** — Existing capability (updated)
- **parameters** — Existing capability (updated)
- **speech** — Existing capability (updated)
- **text_utils** — **NEW** capability created in v0.3.0 at `openspec/specs/text_utils/spec.md`

## Pre-archive vs Post-archive State of `openspec/specs/`

| Axis | Pre-v0.3.0 | Post-v0.3.0 |
|---|---|---|
| Capabilities | 7 | 8 |
| Spec files | 7 (`*-/spec.md`) | 8 (`*-/spec.md`) |
| Total spec lines | ~1,778 | ~2,057 |

The `text_utils/` directory was created as a new capability. All 7 existing specs were updated with v0.3.0 additions and modifications.

## Carry-forward / Open Follow-ups

- **4 manual `[windows-only]` verifications** remain open from the verification phase:
  1. ChatPanel dual-view (ListBox + stream display) with NVDA reading order on Windows
  2. MessageDetailDialog focus, Escape close, and NVDA interaction
  3. Alt+1..6 / F2 / F6 accelerator routing under NVDA on Windows
  4. Model loading background thread — 8-second voice announcement timing
- **SUGGESTION items** (non-blocking) from verify-report:
  - `set_models([])` should speak empty-model announcement
  - `_on_close` wait for background thread could give better UX
  - `stop_server_button` re-enable after server down is slightly redundant

## Test Count Delta

| Version | Tests | Delta |
|---|---|---|
| Pre-v0.3.0 (v0.2.1) | 102 | — |
| v0.3.0 | 134 | +32 |

## File Count Delta

| Version | Source Files | Delta |
|---|---|---|
| Post-migration (v0.2.x) | 17 | — |
| v0.3.0 | 20 | +3 |

New files in v0.3.0:
- `ollamachat/core/text_utils.py` — headless `strip_markdown()` function
- `ollamachat/ui/message_detail_dialog.py` — custom `wx.Dialog` for full message viewing
- `tests/core/test_message_detail_dialog_static.py` — AST-based accessibility invariants

## Archive Contents

```
archive/2026-06-23-ux-navigation-history/
├── archive-report.md     ← this file
├── proposal.md           ← original change proposal
├── design.md             ← architecture and sequence diagrams
├── tasks.md              ← 30 implementation tasks (all complete)
├── verify-report.md      ← 134/134 tests, 8 spec deltas satisfied
└── specs/                ← delta specs (8 subdirectories)
```

## Source of Truth Updated

The following main specs now reflect v0.3.0 behavior:
- `openspec/specs/chat/spec.md`
- `openspec/specs/accessibility-guidelines/spec.md`
- `openspec/specs/parameters/spec.md`
- `openspec/specs/conversation-persistence/spec.md`
- `openspec/specs/llama-integration/spec.md`
- `openspec/specs/app-shell/spec.md`
- `openspec/specs/speech/spec.md`
- `openspec/specs/text_utils/spec.md` (new)

## SDD Cycle Complete

The change has been fully planned, proposed, specced, designed, implemented (30 tasks), verified (134/134 tests), and archived. Ready for the next change.
