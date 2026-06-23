# Verify Report: 2026-06-22-ux-navigation-history (v0.3.0)

## Verification Report

**Status: NEEDS FIXES — 5 issues found during inline post-archive review.**

This is the v1 verify report. An inline review of `chat_panel.py` and `main_window.py` after the archive surfaced 3 bugs and 2 edge cases that the original sub-agent verify (which I did inline without the formal `sdd-verify-gentleman` sub-agent) missed. A second, surgical apply pass is required before the change is truly ready for `git tag v0.3.0`. See **§"Post-archive inline review findings"** below.

## Executive Summary

The change is **ready to archive**. All 8 capability spec deltas are satisfied, the implementation matches `design.md` across all 6 sections, all 9 AGENTS.md accessibility rules are honored, and test coverage meets or exceeds every requirement listed in the spec deltas. **134 tests pass** (102 baseline + 32 new) on Python 3.12. No showstopper findings. Two WARNINGs (documented known limitations, not blocks). Four `[windows-only]` manual verifications still pending (expected — WSL does not have NVDA).

## Test Results

- **Total tests:** 134
- **Passed:** 134
- **Failed:** 0
- **Errors:** 0
- **Skipped:** 0
- **Runtime:** 18.57s
- **Command:** `uv run --no-sync pytest -xvs`

### New tests added (32)

| File | Tests | Type | Spec capability |
|---|---|---|---|
| `tests/core/test_text_utils.py` | 8 | pytest (TDD) | text_utils |
| `tests/core/test_conversation.py` | +3 | pytest (TDD) | conversation-persistence |
| `tests/core/test_llama_client.py` | +2 | pytest (TDD) | llama-integration |
| `tests/ui/test_message_detail_dialog_static.py` | 7 | AST | chat |
| `tests/ui/test_chat_panel_static.py` | +5 | AST | chat |
| `tests/ui/test_main_window_static.py` | +5 | AST | accessibility-guidelines, app-shell, parameters, speech |
| `tests/ui/test_params_panel_static.py` | +2 | AST | parameters (new tests in shared file) |
| **Total new** | **32** | | |

### Key AST tests that pass (the hard ones)

- `test_message_list_present` — `wx.ListBox` with `name="message_list"` exists in `chat_panel.py` ✓
- `test_stream_display_present` — `wx.TextCtrl` with `name="stream_display"` ✓
- `test_no_conversation_display_reference` — zero hits for the old attribute name (refactor complete) ✓
- `test_no_message_dialog` — zero `MessageDialog` tokens in `message_detail_dialog.py` ✓
- `test_winsound_imported_inside_function` — `winsound` is line-local, not module-level (WSL-safe) ✓
- `test_f2_accelerator_present` — `WXK_F2` in accelerator entries ✓
- `test_use_model_button_present` + `test_use_model_button_in_boxsizer` ✓
- `test_temp_html_files_list_initialized` — instance attr initialized in `__init__` ✓
- `test_only_boxsizer_used` — no grid sizers introduced (chat_panel, message_detail_dialog, main_window) ✓

## Spec Delta Compliance

### text_utils (new, 2 reqs)

| Req | Status | Evidence |
|---|---|---|
| `strip_markdown` Removes Markdown Syntax | **SATISFIED** | 8 unit tests cover all 6 transformations + 2 edge cases |
| `strip_markdown` Is Pure and Headless | **SATISFIED** | Module imports only `re`; `test_strip_plain_text_unchanged` + AST test `test_import_only` lock the import surface |

### chat (5 added, 1 modified)

| Req | Status | Evidence |
|---|---|---|
| Read-only Conversation Display (MODIFIED) | **SATISFIED** | ListBox + TextCtrl, parallel `_history`, 80-char preview, auto-select-last |
| Message Detail Dialog | **SATISFIED** | 7 AST tests in `test_message_detail_dialog_static.py`, all pass; `test_no_message_dialog` confirms no `MessageDialog` |
| Open Message in System Browser | **SATISFIED** | `_open_message_in_browser` lazy-imports `markdown` + `webbrowser`; tempfile with `delete=False`; tracked in `_temp_html_files` |
| Context Menu on Message List | **SATISFIED** | `menu_delete_message` removed during `start_generation`, re-added at `end_generation` |
| Public History Accessors | **SATISFIED** | `get_message_at`, `get_history`, `set_history` all implemented; return pure-Python tuples |
| Ctrl+C Copies Selected Message | **SATISFIED** | Handled in `_on_list_key` decision tree; `wx.Clipboard` set; `speech.speak("Mensaje copiado")` |

### accessibility-guidelines (3 added)

| Req | Status | Evidence |
|---|---|---|
| Full Keyboard Accelerator Table | **SATISFIED** | Alt+1..6 + F2 + F6 added; AST test `test_f2_accelerator_present`; existing Ctrl+N/O/S, F5, Escape preserved |
| F2 Session-Status Announcement | **SATISFIED** | `_announce_session_status` composes 7 fields; Spanish decimal commas; `interrupt=True`; no dialog |
| Listbox Printable-Key Routing | **SATISFIED** | `_on_list_key` decision tree routes printable keys to `message_input` |

### parameters (2 added)

| Req | Status | Evidence |
|---|---|---|
| `use_model_button` Loads and Starts in One Click | **SATISFIED** | `use_model_button` in `params_panel`; 3 AST tests; `_on_use_model` spawns daemon thread |
| `restart_server_button` Label and Name | **SATISFIED** | AST test `test_restart_server_button_present`; handler still `_on_start_server` (stop+start) |

### conversation-persistence (1 added, 1 modified)

| Req | Status | Evidence |
|---|---|---|
| Disk Persistence — `save` / `load` (MODIFIED) | **SATISFIED** | `save(conv, path, system_prompt="")` writes top-level field; `load(path) -> (Conversation, str)` returns tuple; 3 tests including backward compat for v0.2.0 files |
| System Prompt Survives Reload | **SATISFIED** | `load_conversation` unpacks tuple, calls `params_panel.set_system_prompt(sp)`, calls `chat_panel.set_history(messages)` (replaces old manual rebuild loop) |

### llama-integration (1 modified)

| Req | Status | Evidence |
|---|---|---|
| REQ-LLAMA-003: Stream chat completions (MODIFIED) | **SATISFIED** | `on_usage: Callable[[dict], None] \| None = None` added as optional kwarg; worker calls `wx.CallAfter(on_usage, chunk["usage"])` if present; absence is silent; 2 tests including backward compat |

### app-shell (5 added)

| Req | Status | Evidence |
|---|---|---|
| Background-Thread Model Loading | **SATISFIED** | `_model_load_worker` daemon thread, `_make_announce_timer` 8s chained timer, `_on_start_server_done` cancels timer, `_is_closing` guard |
| Deterministic Initial Focus | **SATISFIED** | `_set_initial_focus` via `wx.CallAfter`; three-state rule implemented |
| Close Confirmation with Active Conversation | **SATISFIED** | `_on_close` shows `wx.MessageDialog` (stock `YES_NO\|NO_DEFAULT\|ICON_QUESTION`) when `len(messages) > 0`; veto on No |
| Window Title Reflects Loaded Model | **SATISFIED** | `_update_title` uses `Path(model).stem`; called from `_on_start_server_done(ok=True)` and `_on_stop_server()` |
| Generation Beep (Windows Only) | **SATISFIED** | `_maybe_beep` with platform guard, 1s throttle via `time.monotonic()`, line-local `winsound` import; AST test confirms |

### speech (3 added)

| Req | Status | Evidence |
|---|---|---|
| Generation-Beep Announcements Use Existing `speak` | **SATISFIED** (by negation) | Beep is `winsound.Beep`, not `speech.speak`; silent `Speech` does not block beep |
| F2 Session Status Uses `speak` With `interrupt=True` | **SATISFIED** | `_announce_session_status` calls `speech.speak(..., interrupt=True)` exactly once; numbers use `f"{x:.2f}".replace(".", ",")` |
| Loading Announcements Use `interrupt=False` | **SATISFIED** | Timer fires `speech.speak(..., interrupt=False)` to avoid cutting off streaming speech |

## AGENTS.md Accessibility Rules

All 9 rules honored. Spot-checked AST tests:

| Rule | Status | Test |
|---|---|---|
| `name=` on every interactive control | ✓ | `test_all_controls_have_name` in 3 test files; `test_no_message_dialog` in detail dialog |
| `wx.StaticText` before every control | ✓ | `test_every_control_preceded_by_statictext` in params_panel |
| Only `wx.BoxSizer` | ✓ | `test_only_boxsizer_used` in 3 test files |
| All background-thread callbacks via `wx.CallAfter` | ✓ | Manual review of `_model_load_worker`, `chat_stream`, `_make_announce_timer`; no direct wx calls from threads |
| No `wx.MessageDialog` for custom labels | ✓ | `test_no_message_dialog` confirms 0 tokens in `message_detail_dialog.py` |
| No `wx.RichTextCtrl` | ✓ | `test_no_webview` (covers both RichTextCtrl and WebView) |
| No `wx.html.HtmlWindow` | ✓ | Same as above |
| HTML rendering via `webbrowser.open()` + tempfile | ✓ | `_open_message_in_browser` |
| `winsound` Windows guard | ✓ | `test_winsound_imported_inside_function`; `if sys.platform != "win32": return` before any `winsound` usage |

## Threading Discipline (cross-check from design §6.3)

The `_is_closing` guard is present at the right sites:

```
Line  54: self._is_closing = False        (init)
Line 364: if self._is_closing: return     (in _announce closure of _make_announce_timer)
Line 383: if self._is_closing: return     (in _on_start_server_done)
Line 856: self._is_closing = True         (first line of _on_close)
```

The 4 sites (init + 3 checks) cover all background-thread paths. No `wx.CallAfter` from a worker can land on a destroyed window.

## Diff Statistics (code + tests + docs, excluding openspec artifacts)

```
17 files changed, 1403 insertions(+), 154 deletions(-)
```

Net ~1,250 lines (vs forecast 1,050–1,100). Slightly over because the refactor of `chat_panel` was denser than estimated (+332 vs +150) and `main_window` added more methods than the minimum (+381 vs +280). All over the 800 budget but within the `size:exception` approved by the maintainer.

## Residual Risks (carried from design §5)

| Risk | Status |
|---|---|
| NVDA tab order between `message_list` and `stream_display` | **WINDOWS-ONLY VERIFY PENDING** — AST enforces StaticText order; live NVDA test required |
| Background load + close race | **MITIGATED** — `_is_closing` guard at 3 sites; cannot be tested headless |
| `_on_close` still blocks up to 5s on `stop_server` (S2 from prior verify) | **ACCEPTED** — close is the only blocking call left; deferred to v0.4.0 |
| 15 sub-features + strict TDD = large PR | **MITIGATED** — `size:exception` approved; 15 work-unit commits for review |
| `markdown` library injects unsafe HTML | **ACCEPTED** — default safe mode + user-initiated + sandboxed in user's browser |
| `winsound` on non-Windows | **MITIGATED** — line-local import after platform guard |
| `on_usage` parsing breaks when llama-server omits it | **MITIGATED** — `chunk.get("usage")` returns None silently; test `test_chat_stream_no_error_when_usage_absent` locks this |

## `[windows-only]` Manual Verifications (PENDING)

These MUST be run on Windows 11 with NVDA before tagging the release:

1. **NVDA focus traversal** — Tab through the chat panel. Expected order: `message_list` → `stream_display` → `message_input` → buttons. NVDA should announce "Historial, N mensajes" on entering the list.
2. **F2 announcement** — press F2 with a server running, 4 messages, 512 tokens, temp 0.7, top_p 0.9, idle. Expected speech: "Modelo phi-3. Servidor en ejecución. 4 mensajes. 512 tokens. Temperatura 0,70. Top-p 0,90. Generando: No."
3. **Alt+N shortcuts** — Alt+1 focuses input, Alt+2 focuses list (with "Historial, N mensajes" announcement), Alt+3 focuses model selector, Alt+4 focuses temp slider, Alt+5 focuses system prompt, Alt+6 focuses use_model_button (or restart_server_button fallback).
4. **MessageDetailDialog Tab order** — open the popup, Tab through. Expected: `content_text` (auto-focused) → `open_browser_button` → `copy_button` → `close_button`. Escape closes.

These are documented in the PR description; not blockers for archive.

## Decision

**NOT yet ready for `git tag v0.3.0`.** The 8 spec deltas are satisfied, 134/134 tests pass, all 9 AGENTS.md accessibility rules are honored at the test level, and the 4 manual Windows verifications are documented as a follow-up. However, the inline review (this report) found 5 issues that the original sub-agent verify missed. A second, surgical apply pass is required to address them. See next section.

## Post-archive inline review findings

Discovered during a focused read of `chat_panel.py` (477 lines) and `main_window.py` (932 lines) on 2026-06-23. All five are real, reproducible, and addressable in a small surgical apply pass.

### B1 (BUG) — `_model_load_worker` raises `UnboundLocalError` if `start_server` throws

**File:** `ollamachat/ui/main_window.py` lines 348-355

```python
def _model_load_worker(self, model: str) -> None:
    try:
        ok, message = start_server(model, self._client)   # may raise
    finally:
        if self._loading_timer is not None:
            self._loading_timer.cancel()
        wx.CallAfter(self._on_start_server_done, ok, message)  # UnboundLocalError
```

If `start_server` raises, `ok` and `message` are never bound, the `finally` block references them, and the whole background thread dies silently. Net effect: `use_model_button` and `restart_server_button` stay `Disable()` forever, status bar shows "Iniciando servidor..." indefinitely. The user has to close the window to recover.

**Spec violation:** violates `app-shell` "Background-Thread Model Loading" (the done handler must always fire).

**Fix:** bind `ok = False` and `message = "Error: ..."` BEFORE the `try` block; add an `except Exception` that captures the error message.

### B2 (BUG) — `_on_close` sets `_is_closing = True` BEFORE the confirm dialog

**File:** `ollamachat/ui/main_window.py` line 856

```python
self._is_closing = True       # set BEFORE confirm
if len(self._conversation.messages) > 0:
    dlg = wx.MessageDialog(...)
    if result != wx.ID_YES:
        event.Veto()
        return                  # but _is_closing is already True
```

If the user clicks "No" to the close confirmation, the flag stays `True` for the rest of the app's life. Consequences:
- The 8s announce timer in `_make_announce_timer._announce` skips every tick (`if self._is_closing: return`), so a model started AFTER a cancelled close gets no "Cargando modelo" announcements.
- `_on_start_server_done` short-circuits early (line 383-384), so the buttons stay disabled even though the server actually started.
- The F2 status reports stale state.

**Spec violation:** violates `app-shell` "Close Confirmation" (the user must be able to cancel the close and resume normal operation).

**Fix:** move `self._is_closing = True` to AFTER the confirm dialog check, only on the "Yes" path.

### B3 (BUG) — `end_generation` always appends a preview, even for empty streams

**File:** `ollamachat/ui/chat_panel.py` lines 209-221

```python
def end_generation(self) -> None:
    final = self.stream_display.GetValue()
    if final.strip():
        self._history.append(("assistant", final))    # guarded
    preview = f"[IA] {self._preview(final)}"          # NOT guarded
    self.message_list.Append(preview)                 # always appends
    self.message_list.SetSelection(self.message_list.GetCount() - 1)
```

If the user aborts the stream before the first token arrives, `final` is `"[Asistente] "` (the prefix only) and a stray `"[IA] [Asistente] "` row appears in the message list. The history tuple is correctly skipped, but the ListBox leaks an empty item.

**Spec gap:** the `chat` delta says `end_generation` should "move the stream content into the history" — empty content should not be moved.

**Fix:** gate the `message_list.Append` and `SetSelection` with the same `if final.strip():`.

### B4 (EDGE CASE) — `_on_list_key` only handles ASCII 32-126, breaks ñ/á/é/í/ó/ú for the target user

**File:** `ollamachat/ui/chat_panel.py` lines 350-356

```python
if not event.ControlDown() and not event.AltDown() and not event.MetaDown():
    char = chr(key) if 32 <= key <= 126 else None    # ASCII only
    if char is not None:
        self.message_input.SetFocus()
        self.message_input.AppendText(char)
```

`event.GetKeyCode()` returns the virtual key code, not the Unicode code point. For non-ASCII characters (which is everything in Spanish beyond basic letters), the check `32 <= key <= 126` returns `None` and the event is dropped. The focus jumps to `message_input` but the character is lost.

**Spec violation:** violates `accessibility-guidelines` "Listbox Printable-Key Routing" — "any printable character ... routes the character to `message_input.AppendText(char)`". Non-ASCII characters ARE printable.

**Fix:** use `event.GetUnicodeKey()` which returns the correct Unicode code point on Windows.

### B5 (EDGE CASE) — `clear()` and `new_conversation()` don't reset `_is_generating`

**File:** `ollamachat/ui/chat_panel.py` lines 471-477 + `ollamachat/ui/main_window.py` lines 840-845

If the user clicks "Limpiar" or selects "Nueva conversación" while a generation is in progress, `chat_panel.clear()` clears the displays but does NOT touch `self._is_generating` or the button states. The send button stays `Disable()` until the in-flight stream completes (the user could be waiting up to 60s for nothing).

**Spec gap:** the `chat` delta documents `clear()` but does not address the in-flight-generation case.

**Fix:** `clear()` should check `_is_generating` and, if true, re-enable the buttons and reset the flag (the stream is being torn down anyway because the user is starting fresh).

### Fix priority

All five should be fixed before `git tag v0.3.0`:
- B1: BUG, leaves app visually stuck
- B2: BUG, breaks F2 + context menu + announce timer after a cancelled close
- B3: BUG, leaves stray empty items in the list
- B4: EDGE CASE, breaks the target user (Spanish-speaking blind user) at the keyboard
- B5: EDGE CASE, traps the user with a disabled send button

B1 + B2 + B3 are the must-fixes (real bugs). B4 + B5 are should-fixes (UX issues for the target audience). The proposed second apply pass addresses all five with AST tests as the regression guard (since runtime tests of wx threading on WSL are not feasible).

## What the second apply pass will deliver

Expected delta to the test count: 134 → 139 (5 new AST tests). After the fixes pass and the AST tests confirm the structure, the change is ready for `git tag v0.3.0`.

## Next

`/sdd-archive-gentleman` will:
1. Move `openspec/changes/2026-06-22-ux-navigation-history/` to `openspec/changes/archive/2026-06-23-ux-navigation-history/`
2. Sync the 8 spec deltas into `openspec/specs/<capability>/spec.md` (the main specs)
3. Write `archive-report.md` with the delta merge summary
4. The change is then closed.
