# Proposal: 2026-06-22-ux-navigation-history

## Why — current UX problems

After v0.2.0 (llama.cpp migration), blind users on NVDA still hit eight concrete blockers. This change resolves them in one slice before v0.4.0 tool calling.

| # | Problem | Source |
|---|---|---|
| 1 | Single scrolling `conversation_display` forces NVDA to read the whole transcript to find one message | chat spec |
| 2 | No way to inspect a past message in detail (no popup, no copy of full text) | chat spec |
| 3 | No way to view rendered markdown (no browser, no `wx.WebView`) | AGENTS.md |
| 4 | `Iniciar servidor` blocks UI for 10–60s on large `.gguf` with no audio feedback | llama-integration spec |
| 5 | No keyboard shortcut to jump between input, list, model, sliders, system prompt | accessibility-guidelines |
| 6 | No way to hear session state (model, tokens, status) at a glance | accessibility-guidelines |
| 7 | Window title always says "OllamaChat" — no model in title | app-shell spec |
| 8 | Saved conversations lose the system prompt on reload | conversation-persistence spec |

## What changes — 15 sub-features

**A. Dual view in `chat_panel.py`** — `wx.ListBox("Historial:")` with first 80 chars of each message + read-only `wx.TextCtrl("Respuesta actual:")` with `TE_MULTILINE|TE_READONLY|TE_RICH2` for streaming. Parallel `self._history: list[tuple[str, str]]`. New methods `get_message_at`, `get_history`, `set_history`. Bindings: `EVT_LISTBOX_DCLICK`, `EVT_KEY_DOWN`, `EVT_CONTEXT_MENU`.
**B. New `ui/message_detail_dialog.py`** — `MessageDetailDialog(wx.Dialog)` with read-only `content_text` (focused on init), 3 native `wx.Button`s (`open_browser_button`, `copy_button`, `close_button`). Escape closes. **Per AGENTS.md: no `wx.MessageDialog` for custom labels.**
**C. Open in browser** — `MainWindow._open_message_in_browser(text)` writes `tempfile.NamedTemporaryFile(suffix='.html', delete=False)` via `webbrowser.open`. Tracked in `self._temp_html_files`, cleaned in `_on_close`.
**D. Context menu on `message_list`** — `wx.Menu` items: Copiar (Ctrl+C), Ver en navegador (Ctrl+Enter), Eliminar (only when not generating). All with `name=`.
**E. New `core/text_utils.py`** — `strip_markdown(text)` using only `re` (headers, bold/italic, code fences, inline code, links, list items). Headless, fully unit-tested.
**F. `use_model_button`** in `params_panel` + rename "Iniciar servidor" → "Reiniciar servidor" (`restart_server_button`). Wired to `_on_use_model()` in `main_window`.
**G. Background-thread model loading** — `threading.Thread` daemon, periodic `wx.CallAfter(speech.speak, "Cargando modelo, por favor espera...", interrupt=False)` every 8s. `llama_runner.py` unchanged (its existing polling releases the lock).
**H. Accelerator table** — Alt+1 input, Alt+2 list, Alt+3 model, Alt+4 temp, Alt+5 system prompt, Alt+6 use_model/restart; F2 status, F6 cycle panels. ListBox `EVT_KEY_DOWN` routes printable keys to input.
**I. F2 `_announce_session_status()`** — composes model/server/msg count/tokens/temp/top_p/generating, speaks with `interrupt=True`. No dialog.
**J. Token usage capture** — `llama_client.chat_stream(..., on_usage: Callable[[dict], None] | None = None)`. Parse `chunk.get("usage")` in `_stream_worker`, fire `wx.CallAfter(on_usage, usage)`. `MainWindow._on_usage` stores and updates status bar field 1.
**K. Initial focus** — `wx.CallAfter(self._set_initial_focus)` at end of `__init__`: input if server running, else `use_model_button`, else `scan_models_button`.
**L. Confirm-close dialog** — In `_on_close`, BEFORE abort: if conversation non-empty, `wx.MessageDialog("¿Salir sin guardar?", YES_NO|NO_DEFAULT|ICON_QUESTION)`. Stock labels (not custom Spanish) — **per AGENTS.md: stock-label `wx.MessageDialog` is permitted**; only `SetYesNoCancelLabels()` triggers the MSAA regression. On Yes: proceed, unlink temp files. On No: `event.Veto()`.
**M. Window title** — `_update_title(model)`: `f"OllamaChat — {Path(model).stem}"` or `"OllamaChat"`. Called from `_on_start_server_done` + `_on_stop_server`.
**N. `system_prompt` in saved conversation** — `Conversation.save(conv, path, system_prompt="")` + `load(path) -> (Conversation, str)`. Top-level `"system_prompt": str` field. `load_conversation` restores prompt via `params_panel.set_system_prompt` AND repopulates history via `chat_panel.set_history`.
**O. Generation beep** — `_maybe_beep()` in `_on_token` path, Windows-guarded `if sys.platform != 'win32': return`, throttle max 1/s via `time.monotonic()`. `winsound.Beep(520, 50)` in try/except.

### Files

| File | Change |
|---|---|
| `ollamachat/core/text_utils.py` | NEW — `strip_markdown` |
| `ollamachat/ui/message_detail_dialog.py` | NEW — popup dialog |
| `ollamachat/core/conversation.py` | MODIFY — `system_prompt` save/load |
| `ollamachat/core/llama_client.py` | MODIFY — `on_usage` callback param |
| `ollamachat/ui/chat_panel.py` | MODIFY — dual view + new methods + bindings |
| `ollamachat/ui/params_panel.py` | MODIFY — `use_model_button` |
| `ollamachat/ui/main_window.py` | MODIFY — coordination, accelerator, focus, title, beep, close confirm |
| `pyproject.toml` | MODIFY — add `markdown>=3.5` |
| `tests/core/test_text_utils.py` | NEW — 8 unit tests |
| `tests/core/test_conversation.py` | EXTEND — 3 tests |
| `tests/core/test_llama_client.py` | EXTEND — 2 tests |
| `tests/ui/test_chat_panel_static.py` | EXTEND AST — 3 tests |
| `tests/ui/test_main_window_static.py` | EXTEND AST — 5 tests |
| `tests/ui/test_message_detail_dialog_static.py` | NEW AST — 6 tests |
| `AGENTS.md`, `CHANGELOG.md`, `README.md` | UPDATE |

## Capabilities

### New Capabilities

- `text_utils` — markdown stripping for the popup + browser rendering (E).

### Modified Capabilities

- `chat` — A (dual view), B (popup), C (browser), D (context menu).
- `accessibility-guidelines` — H (Alt+N, F2, F6 shortcuts).
- `parameters` — F (`use_model_button`, system prompt), N (system_prompt accessor stays).
- `conversation-persistence` — N (top-level `system_prompt` in JSON).
- `llama-integration` — J (`on_usage` callback in `chat_stream`).
- `app-shell` — G (background loading), K (initial focus), L (close confirm), M (title), O (beep coordinator).
- `speech` — O (beep is platform-guarded no-op on non-Windows), I (F2 composes via existing `speak`).

## Approach

- `text_utils` follows the `speech` pattern: headless `re`-only module, fully TDD'd. Other new code lives in `ui/` and is AST-checked.
- `chat_panel` keeps `wx`-import isolation: ListBox + TextCtrl are wx widgets, but `get_history`/`set_history` accept pure Python tuples so `core/` stays testable.
- `markdown` dep: use `markdown.markdown(text)` to render for `webbrowser.open`; `strip_markdown` for the popup read-only TextCtrl. Two surfaces, one source of truth via `text_utils`.
- Threading: extend the existing pattern (daemon thread + `wx.CallAfter` + `threading.Event`). The periodic announcement timer is a `threading.Timer` chained inside the worker, cancelled on done.

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| NVDA reads ListBox + TextCtrl in wrong tab order | Med | AST check + `[windows-only]` verify with NVDA focus traversal |
| `markdown` library injects unsafe HTML | Low | Use `markdown.markdown(text)` with default safe mode; output is opened in user's browser (sandboxed); user-initiated only |
| Background load + close race (timer fires after window destroyed) | Med | `threading.Timer.daemon = True`; cancel timer in `_on_start_server_done`; bind `_on_close` to also call `stop_server` |
| `_on_close` still blocks 5s on stop_server (S2 from prior verify) | Med | Accepted; close is the only blocking call left; document in code comment |
| 15 sub-features + strict TDD = large PR | High | review_budget raised from 400→800 per preflight; AST checks for UI allow rapid iteration |
| `on_usage` parsing breaks when llama-server omits it | Low | Callback is `Optional`; absence is silent (test `test_chat_stream_no_error_when_usage_absent` locks this) |
| Refactor of `chat_panel` breaks existing 9 AST tests | Med | Update AST tests in same change; do not delete old assertions until new ones are green |
| `winsound` import on non-Windows breaks WSL tests | Low | AST check `if sys.platform != 'win32': return` before any `winsound` import (line-local import inside the guard) |

## Out of scope / non-goals

- **Tool calling (v0.4.0)** — `permission_manager.py`, `permission_dialog.py`, `tool_executor.py`, `shell_execute` tool. Listed in AGENTS.md as the next planned change. Requires v0.3.0 verified.
- Persistent session state across app restarts (last-loaded model, last temperature).
- Search/filter inside the message ListBox.
- Multi-tab conversations.
- Renaming the `ollamachat` package.
- Distribution / PyInstaller.
- Image content in the popup (popup shows stripped text; images are visible only in the full transcript).

## Acceptance criteria

- [ ] `uv run --no-sync pytest -xvs` passes (102 prior + ≥30 new = ≥132).
- [ ] All 9 AGENTS.md accessibility rules honored in new dialog + chat panel.
- [ ] F2 announces model, server status, msg count, tokens, temp, top_p, generating.
- [ ] Accelerator table has all Alt+1..6 + F2 + F6 bindings.
- [ ] Saved `.json` round-trips `system_prompt`.
- [ ] Background model load announces every 8s and disables both `use_model_button` and `restart_server_button`.
- [ ] Close-with-active-conversation shows confirm dialog (NO default).
- [ ] `[windows-only]` verify: NVDA focus traversal through ListBox+TextCtrl, F2 announcement, Alt+N shortcuts, popup dialog Tab order.

## Rollback plan

1. `git revert` the merge commit (single PR per `delivery: single-pr-default`).
2. `pip uninstall markdown` (or restore `pyproject.toml` to remove the dep).
3. `uv run --no-sync pytest -xvs` must still pass at 102/102 (the prior green state).
4. The pre-v0.3.0 version is `0.2.0`; reverting bumps back to it in `pyproject.toml` + `CHANGELOG.md`.

## Skill resolution

`paths-injected` — `cognitive-doc-design` loaded from `/home/ic_ma/.config/opencode/skills/`. Engram unavailable per `AGENTS.md`; artifact store is `openspec`.
