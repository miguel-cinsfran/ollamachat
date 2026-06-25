# Apply Progress: 2026-06-25-conversations-qol

## WU-1: Core + Tests ✅ COMPLETED

- **Date**: 2026-06-25
- **Strategy**: single-pr (D2)
- **Execution**: auto (A2)

### Completed Tasks

| Task | Status | Files Changed |
|------|--------|---------------|
| 1.1 BellbirdConfig: 3 new fields | ✅ | `bellbird/core/config.py`, `tests/core/test_config.py` |
| 1.2 Conversation.to_markdown() | ✅ | `bellbird/core/conversation.py`, `tests/core/test_conversation.py` |
| 1.3 find_in_history() | ✅ | `bellbird/core/conversation.py`, `tests/core/test_conversation.py` |
| 1.4 Recents helpers + should_auto_restore | ✅ | `bellbird/core/config.py`, `tests/core/test_config.py` |
| 1.5 Version bump (pyproject.toml) | ✅ | `pyproject.toml` (already 0.8.2) |
| 1.6 find_in_history keymap entry | ✅ | `bellbird/core/keymap.py`, `tests/core/test_keymap.py` |

### Files Changed

| File | Lines Added | Lines Removed |
|------|-------------|---------------|
| `bellbird/core/config.py` | 55 | 0 |
| `bellbird/core/conversation.py` | 102 | 0 |
| `bellbird/core/keymap.py` | 1 | 0 |
| `tests/core/test_config.py` | 255 | 0 |
| `tests/core/test_conversation.py` | 172 | 0 |
| `tests/core/test_keymap.py` | 6 | 2 |
| **Total** | **591** | **2** |

### Tests Executed

- `tests/core/test_config.py`: 61/61 ✅
- `tests/core/test_conversation.py`: 57/57 ✅
- `tests/core/test_keymap.py`: 37/37 ✅
- `tests/core/test_llama_client.py`: 59/59 ✅
- `tests/core/test_llama_client_state.py`: 8/8 ✅
- `tests/core/test_html_render.py`: 11/11 ✅
- `tests/core/test_html_render_static.py`: 5/5 ✅

**Total**: 238/238 passed (excluding `test_llama_runner.py` which uses subprocess polling and times out in WSL)

### Commit

```
9971619... feat(core): add to_markdown, find_in_history, recents helpers, and find_in_history keymap
```

## WU-2a: Find feature (select_and_announce_message + FindDialog + wiring) ✅ COMPLETED

- **Date**: 2026-06-25
- **Strategy**: single-pr (D2)
- **Execution**: auto (A2)

### Completed Tasks

| Task | Status | Files Changed |
|------|--------|---------------|
| 2.1 ChatPanel.select_and_announce_message() | ✅ | `bellbird/ui/chat_panel.py` |
| 2.2 FindDialog (accessible wx.Dialog) | ✅ | NEW `bellbird/ui/find_dialog.py` |
| 2.3 Wire find_in_history accelerator in main_window | ✅ | `bellbird/ui/main_window.py` |
| 2.4 _on_find handler (search loop) | ✅ | `bellbird/ui/main_window.py` |

### Files Changed

| File | Lines Added | Lines Removed |
|------|-------------|---------------|
| `bellbird/ui/chat_panel.py` | 62 | 0 |
| `bellbird/ui/find_dialog.py` | NEW (117) | 0 |
| `bellbird/ui/main_window.py` | 25 | 0 |
| `tests/ui/test_chat_panel_runtime.py` | 83 | 0 |
| `tests/ui/test_find_dialog.py` | NEW (126) | 0 |
| `tests/ui/test_find_dialog_static.py` | NEW (152) | 0 |
| `tests/ui/test_main_window_static.py` | 52 | 0 |
| **Total** | **617** | **0** |

### Tests Executed (WSL)

- `tests/core/`: 238/238 ✅
- AST/static UI: 277/277 ✅
- `tests/smoke/`: 1/1 ✅
- **Total**: 516/516 passed

### Notes for WU-2b

- `select_and_announce_message()` uses full text for speech (not preview)
- `find_in_history()` 1-based ↔ 0-based conversion handled in `find_and_select()`
- `FindDialog` is `wx.Dialog` with 3 native `wx.Button`s — no `wx.MessageDialog`
- Ctrl+F handler registered in `_build_accelerators`; FindDialog shown modally; focus restored to `message_list` on close
- WU-2b scope: Recents submenu, Exportar..., Auto-restore, run_tests.bat registration
