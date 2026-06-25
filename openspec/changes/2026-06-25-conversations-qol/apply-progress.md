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

## WU-2b: Recents + Export + Auto-restore + Persist ✅ COMPLETED

- **Date**: 2026-06-25
- **Strategy**: single-pr (D2)
- **Execution**: auto (A2)

### Completed Tasks

| Task | Status | Files Changed |
|------|--------|---------------|
| 2.5 Submenú "Recientes" en menú Archivo | ✅ | `bellbird/ui/main_window.py`, NEW `tests/ui/test_main_window_runtime.py` |
| 2.6 Wire "Exportar a Markdown..." en menú Archivo | ✅ | `bellbird/ui/main_window.py`, `tests/ui/test_main_window_runtime.py` |
| 2.7 Auto-restaura al abrir | ✅ | `bellbird/ui/main_window.py`, `tests/ui/test_main_window_runtime.py` |
| 2.8 Persistir last_session_path + recent_files en save/load | ✅ | `bellbird/ui/main_window.py`, `tests/ui/test_main_window_runtime.py` |
| 2.9 Registrar tests wx-runtime en run_tests.bat | ✅ | `run_tests.bat` |

### Files Changed

| File | Lines Added | Lines Removed |
|------|-------------|---------------|
| `bellbird/ui/main_window.py` | ~140 | 0 |
| `tests/ui/test_main_window_runtime.py` | NEW (275) | 0 |
| `run_tests.bat` | 2 | 1 |
| **Total** | **~417** | **1** |

### Tests Executed (WSL)

- `tests/core/`: 238/238 ✅
- AST/static UI: 308/308 ✅
- `tests/smoke/`: 1/1 ✅
- **Total**: 547/547 passed (wx-runtime tests in `test_main_window_runtime.py` skip gracefully in WSL — 1 skipped)

### Implementation Notes

- **Recents submenu**: Built dynamically on `EVT_MENU_OPEN`. Filters non-existent paths via `os.path.exists`. Paths >60 chars truncated with ellipsis in the middle. Empty list shows disabled "Sin recientes" item.
- **Export**: `wx.FileDialog` with Markdown/Text wildcards. UTF-8 write. Error handling via try/except with speech announcement. No crash on failure.
- **Auto-restore**: `wx.CallAfter` from `__init__` (non-blocking). On failure, clears `last_session_path` + saves config. No dialog shown.
- **Persist**: `save_conversation` and `load_conversation` update `last_session_path` and `recent_files` via `update_recents()` helper on success only.
- All `speech.speak` calls wrapped in try/except per AGENTS.md.
- UI strings in Spanish: "Recientes", "Sin recientes", "Exportar a Markdown...", "Sesión restaurada", etc.
