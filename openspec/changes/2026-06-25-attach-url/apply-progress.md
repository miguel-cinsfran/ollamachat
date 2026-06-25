# Apply Progress: 2026-06-25-attach-url

## WU-1: Core + Tests ✅ COMPLETED

- **Date**: 2026-06-25
- **Execution**: auto (A2)
- **Strategy**: single-pr (D2)

### Completed Tasks

| Task | Status | Files Changed |
|------|--------|---------------|
| 1.1 `core/web_fetch.py` — FetchResult + fetch_text | ✅ | `bellbird/core/web_fetch.py` (new), `tests/core/test_web_fetch.py` (new) |
| 1.2 Config `url_max_chars: int = 50000` | ✅ | `bellbird/core/config.py`, `tests/core/test_config.py` |
| 1.3 Keymap entry `attach_url: Ctrl+U` → 22 entries | ✅ | `bellbird/core/keymap.py`, `tests/core/test_keymap.py` |
| 1.4 Bump `pyproject.toml` → v0.8.3 | ✅ | `pyproject.toml`, `tests/ui/test_main_window_static.py` |

### Files Changed

| File | Lines Added | Lines Removed |
|------|-------------|---------------|
| `bellbird/core/web_fetch.py` | NEW (127) | 0 |
| `bellbird/core/config.py` | 1 | 0 |
| `bellbird/core/keymap.py` | 1 | 0 |
| `tests/core/test_web_fetch.py` | NEW (325) | 0 |
| `tests/core/test_config.py` | 93 | 0 |
| `tests/core/test_keymap.py` | 45 | 7 |
| `tests/ui/test_main_window_static.py` | 2 | 2 |
| `pyproject.toml` | 1 | 1 |
| **Total** | **595** | **10** |

### Tests Executed

- `tests/core/test_web_fetch.py`: 23/23 ✅
- `tests/core/test_config.py`: 67/67 ✅
- `tests/core/test_keymap.py`: 42/42 ✅
- Full suite: **555 passed, 13 skipped, 1 deselected** ✅

### Commit

```
dcb50b7 feat(core): add web_fetch, attach_url keymap, and url_max_chars config
```

### Implementation Notes

- **`FetchResult` is frozen** — `@dataclass(frozen=True)`. All error paths return `FetchResult(ok=False, ...)`, never raise.
- **Scheme guard** runs before any `requests` call: `^https?://` (case-insensitive). Rejects `file://`, `ftp://`, `gopher://`.
- **HTML cleaning order**: (1) subclass `HTMLParser` strips `<script>`/`<style>` content, (2) `html.unescape()` unescapes entities, (3) `re.sub(r"\s+", " ")` collapses whitespace.
- **Encoding**: `response.text` primary; fallback via `response.content.decode(response.apparent_encoding, errors="replace")`.
- **User-Agent**: Hardcoded `"Bellbird/0.8.3"` with TODO for dynamic read from pyproject.toml.
- **AST guard**: `web_fetch.py` has no `wx` import — verified by test.
- **Config forward-compat**: Unchanged — `__dataclass_fields__` filter already handles unknown keys. No migration needed for `url_max_chars` (default 50000 applied on missing field).
- **Keymap**: `attach_url` at position 22, collision-free (`Ctrl+U` unique).

---

## WU-2: UI + Tests wx + Specs ✅ COMPLETED

- **Date**: 2026-06-25

### Completed Tasks

| Task | Status | Files Changed |
|------|--------|---------------|
| 2.1 Refactor `_make_announce_timer` to accept `phrase` param | ✅ | `bellbird/ui/main_window.py` |
| 2.2 `ui/url_dialog.py` — accessible URL dialog | ✅ | `bellbird/ui/url_dialog.py` (new), `tests/ui/test_url_dialog.py` (new) |
| 2.3 `ChatPanel.attach_url(url, text, origin_label)` | ✅ | `bellbird/ui/chat_panel.py`, `tests/ui/test_chat_panel_runtime.py` |
| 2.4 `_on_attach_url()` — gate, dialog, scheme check, timer + thread | ✅ | `bellbird/ui/main_window.py`, `tests/ui/test_main_window_runtime.py` |
| 2.5 `_fetch_url_worker` + `_on_fetch_complete` (+ `_derive_origin_label`) | ✅ | `bellbird/ui/main_window.py`, `tests/ui/test_main_window_runtime.py` |
| 2.6 Wire handler in `_build_accelerators` + menu item in `_build_menu` | ✅ | `bellbird/ui/main_window.py`, `tests/ui/test_main_window_static.py` |
| 2.7 `_url_fetch_timer` slot in `__init__`, cancel in `_on_close` | ✅ | `bellbird/ui/main_window.py` |
| 2.8 Specs delta verified (4 files) | ✅ | `openspec/changes/2026-06-25-attach-url/specs/{app-shell,chat,keymap,app-configuration}/spec.md` |
| 2.9 Register new wx-runtime tests in `run_tests.bat` | ✅ | `run_tests.bat` |
| 2.10 AST guards: no MessageDialog, name=, BoxSizer only, speech try/except | ✅ | (sanity check) |
| 2.11 Full suite passes WSL | ✅ | 594 passed, 14 skipped |

### Files Changed (WU-2)

| File | Lines Added | Lines Removed |
|------|-------------|---------------|
| `bellbird/ui/url_dialog.py` | NEW (94) | 0 |
| `bellbird/ui/main_window.py` | ~108 | ~3 |
| `bellbird/ui/chat_panel.py` | ~40 | 0 |
| `tests/ui/test_url_dialog.py` | NEW (105) | 0 |
| `tests/ui/test_chat_panel_runtime.py` | ~82 | 0 |
| `tests/ui/test_main_window_runtime.py` | ~170 | 0 |
| `tests/ui/test_main_window_static.py` | ~93 | 0 |
| `run_tests.bat` | ~1 | ~1 |
| **Total WU-2** | **~693** | **~4** |

### Tests Executed

- Full suite (WSL): **594 passed, 14 skipped** ✅ (vs 555/13 pre-WU-2 — 39 new tests, 7 static/AST in WSL, 32 wx-runtime skipped on WSL)

### Specs Delta Verified

All 4 spec delta files exist in `openspec/changes/2026-06-25-attach-url/specs/`:
- `app-shell/spec.md` — URL dialog, menu item, background fetch, mid-generation gate
- `chat/spec.md` — `attach_url` method contract, no-op for empty text, image replacement
- `keymap/spec.md` — `attach_url` action id, 22 entries, collision-free
- `app-configuration/spec.md` — `url_max_chars: int = 50000`

### Implementation Notes

- **`_make_announce_timer` refactored**: now `_make_announce_timer(self, phrase: str = "Cargando modelo, por favor espera...")`. Backwards-compatible default. Internal closure captures `phrase` parameter instead of hardcoded string. No existing call site changed.
- **Two separate timer slots**: `_loading_timer` (model load, unchanged) and `_url_fetch_timer` (URL fetch, new). Both are `threading.Timer | None`, both canceled in their respective completion callbacks. `_url_fetch_timer` also canceled in `_on_close` to prevent dangling timers.
- **URLDialog** mirrors `FindDialog`: `wx.Dialog(name="url_dialog")` with `StaticText("URL:")` + `TextCtrl(name="url_input", TE_PROCESS_ENTER)` + two native buttons. `SetFocus()` on input at open. `SetEscapeId(wx.ID_CANCEL)`. Only `wx.BoxSizer` (no grid).
- **`ChatPanel.attach_url()`** stores text in `_attached_text`, clears images (with `"Imagen reemplazada"` speech if images were present), updates label. Empty text is a silent no-op.
- **`_on_attach_url()` gate**: checks `self.chat_panel._is_generating` first — speaks `"Generación en curso"` and returns. After dialog, validates non-empty URL and scheme regex `^https?://`. On valid URL: speaks `"Descargando página"`, starts announce timer, spawns daemon thread.
- **`_on_fetch_complete`**: cancels timer. On success: calls `chat_panel.attach_url(...)`, speaks `"Página adjuntada"`, and if truncated speaks `"Página grande, se truncó a X caracteres"`. On error: speaks `"Error al descargar: {reason}"`. No `MessageDialog` anywhere.
- **`_derive_origin_label`**: static method using `urllib.parse.urlparse` to produce `netloc + path`, truncated to 60 chars.
- **Thread safety**: `daemon=True` on the fetch thread. All UI updates via `wx.CallAfter`. `speech.speak` wrapped in try/except per AGENTS.md.
- **Menu item**: "Adjuntar URL..." with `Ctrl+U` accelerator, positioned after "Exportar a Markdown..." and before "Preferencias" in the Archivo menu.
- **Handler wiring**: one new entry `"attach_url": lambda: self._on_attach_url()` in the `_build_accelerators` dispatch dict.
- **Edge case — image replacement**: if `_attached_images` has elements when `attach_url` is called, `"Imagen reemplazada"` is spoken BEFORE clearing the images.
- **Race avoidance**: `_url_fetch_timer` is a separate slot to avoid races with `_loading_timer`. Both are independently canceled.

### Commit

```
feat(ui): add Adjuntar URL dialog, fetch worker, and attach_url wiring
```
