# Tasks: 2026-06-22-ux-navigation-history (v0.3.0)

## Review Workload Forecast

| Metric | Estimate |
|---|---|
| Estimated changed lines (code + tests + docs) | **1,050–1,100** |
| New files | 3 (`core/text_utils.py`, `ui/message_detail_dialog.py`, `tests/ui/test_message_detail_dialog_static.py`) |
| Modified files | 7 (`core/conversation.py`, `core/llama_client.py`, `ui/chat_panel.py`, `ui/params_panel.py`, `ui/main_window.py`, `pyproject.toml`, docs) |
| Test delta | +~30 tests (8 unit + 3 conversation + 2 llama_client + 17 AST) |
| Review budget (preflight D2) | 800 lines |
| **Budget risk** | **High — 25–38 % over budget** |
| Decision needed before apply | **Yes** — `delivery: single-pr-default` requires maintainer-approved `size:exception` to exceed 800 lines |

**Per-line breakdown (rough):**

| Surface | New/changed lines | Notes |
|---|---|---|
| `core/text_utils.py` (NEW) | ~50 | re-only |
| `core/conversation.py` (MOD) | +20 | signature change + tuple return |
| `core/llama_client.py` (MOD) | +15 | on_usage param + worker hook |
| `ui/message_detail_dialog.py` (NEW) | ~90 | wx.Dialog + 3 buttons + sizer |
| `ui/chat_panel.py` (REFACTOR) | ~150 net new | dual view, context menu, key routing, 3 new AST tests |
| `ui/params_panel.py` (MOD) | +25 | use_model_button + enable/disable logic |
| `ui/main_window.py` (MOD) | +280 | all coordination (accelerators, F2, F6, focus, close, title, beep, bg load, browser, on_usage, load/save) |
| `tests/core/test_text_utils.py` (NEW) | ~120 | 8 TDD tests |
| `tests/core/test_conversation.py` (EXT) | +60 | 3 tests |
| `tests/core/test_llama_client.py` (EXT) | +60 | 2 tests |
| `tests/ui/test_chat_panel_static.py` (EXT) | +50 | 3 AST tests + 2 search-and-replace assertions |
| `tests/ui/test_main_window_static.py` (EXT) | +90 | 5 AST tests + 2 new assertions |
| `tests/ui/test_message_detail_dialog_static.py` (NEW) | ~120 | 6 AST tests |
| `pyproject.toml` (MOD) | +1 | markdown dep |
| `CHANGELOG.md` (MOD) | +30 | new entry |
| `AGENTS.md` (MOD) | +20 | layout note |
| `README.md` (MOD) | +50 | shortcuts table |
| **Total** | **~1,230** | over budget by ~430 |

## Dependency graph

```
1. text_utils       (TDD core, no deps)
2. conversation     (TDD core, no deps)
3. llama_client     (TDD core, no deps)
        ↓
4. message_detail_dialog   (uses text_utils)
5. params_panel     (use_model_button)
6. chat_panel       (REFACTOR; uses text_utils for preview; uses MessageDetailDialog at runtime)
7. main_window      (orchestrates ALL of the above; longest task)
8. pyproject.toml   (adds markdown; can ship with task 4 or task 7)
9. docs             (CHANGELOG, AGENTS, README — last, reflects final state)
10. verify          (full pytest run + manual Windows checklist)
```

Tasks 1–3 are pure TDD with no wx; they can be done in any order or in parallel. Tasks 4–6 each add new code with their own AST tests. Task 7 is the largest and depends on all of 1–6. Docs ship after the code is final. Verify is last.

---

## Task 1: Foundation — `core/text_utils.py` (TDD)

**1.1** Write `tests/core/test_text_utils.py` with 8 tests:
- `test_strip_headers` — `"# Title\n\nBody"` → `"Title\n\nBody"`
- `test_strip_bold_italic` — `"**bold**"` → `"bold"`
- `test_strip_code_fences` — `` "```\nfoo\nbar\n```" `` contains `"foo"` and `"bar"`, no backticks
- `test_strip_inline_code` — `` "`x`" `` → `"x"`
- `test_strip_links` — `"[docs](https://example.com)"` → `"docs"`
- `test_strip_list_items` — `"- a\n- b"` starts with `"• a"`, contains `"• b"`
- `test_strip_empty_string` — `""` → `""`
- `test_strip_plain_text_unchanged` — `"  hello  "` → `"hello"`

All tests must fail initially (TDD red). Verify with `uv run --no-sync pytest tests/core/test_text_utils.py -xvs`.

**1.2** Implement `ollamachat/core/text_utils.py`:
- Module docstring + 1 import (`re`)
- `def strip_markdown(text: str) -> str:` with the pipeline in the spec order: headers → bold → italic → fenced code → inline code → links → list items → `strip()`

**1.3** Run `uv run --no-sync pytest tests/core/test_text_utils.py -xvs`. Confirm 8/8 pass (TDD green).

---

## Task 2: Core — `conversation.py` system_prompt (TDD)

**2.1** Extend `tests/core/test_conversation.py` with 3 tests:
- `test_save_includes_system_prompt` — save with `system_prompt="Eres útil."`; parse the file as JSON; assert `parsed["system_prompt"] == "Eres útil."` and `parsed["messages"]` is preserved
- `test_load_returns_system_prompt` — file with `{"system_prompt": "X", "messages": [...]}`; assert result is `tuple[Conversation, str]` with `result[1] == "X"`
- `test_load_missing_system_prompt_returns_empty_string` — v0.2.0 file (no field); assert result is `(Conversation, "")`, no `KeyError`

**2.2** Modify `ollamachat/core/conversation.py`:
- `save(cls, conv, filepath, system_prompt: str = "")` — build `{"system_prompt": system_prompt, **conv.to_dict()}`; dump with `indent=2, ensure_ascii=False`; atomic write unchanged
- `load(cls, filepath) -> tuple[Conversation, str]` — `sp = data.get("system_prompt", "")`; `body = {"messages": data.get("messages", [])}`; return `(cls.from_dict(body), sp)`

**2.3** Run `uv run --no-sync pytest tests/core/test_conversation.py -xvs`. Confirm all (existing + 3 new) pass.

---

## Task 3: Core — `llama_client.py` on_usage (TDD)

**3.1** Extend `tests/core/test_llama_client.py` with 2 tests:
- `test_chat_stream_calls_on_usage_when_present` — stub SSE response whose last chunk is `{"usage": {"prompt_tokens": 12, "completion_tokens": 80, "total_tokens": 92}}`; pass `on_usage=fake`; assert `fake` was called with the dict
- `test_chat_stream_no_error_when_usage_absent` — stub stream with no `usage` key; `on_usage=None`; assert no exception, `on_token` and `on_done` still called

**3.2** Modify `ollamachat/core/llama_client.py`:
- `chat_stream(..., on_usage: Callable[[dict], None] | None = None)` — new optional kwarg
- Pass `on_usage` through to `_stream_worker` in `args=(...)`
- In `_stream_worker`, immediately after `chunk = json.loads(payload)` and BEFORE the `content` extraction:
  ```python
  if on_usage is not None:
      usage = chunk.get("usage")
      if usage is not None:
          wx.CallAfter(on_usage, usage)
  ```

**3.3** Run `uv run --no-sync pytest tests/core/test_llama_client.py -xvs`. Confirm all pass.

---

## Task 4: New file — `ui/message_detail_dialog.py` (AST-driven)

**4.1** Create `tests/ui/test_message_detail_dialog_static.py` with 6 AST tests:
- `test_content_text_present` — assert `wx.TextCtrl(..., name="content_text", ...)` appears in source
- `test_open_browser_button_present` — assert `wx.Button(..., name="open_browser_button", ...)`
- `test_copy_button_present`
- `test_close_button_present`
- `test_all_controls_have_name` — assert every `wx.Button(...)` and `wx.TextCtrl(...)` call in the file has `name=`
- `test_only_boxsizer_used` — assert no `GridSizer` (or `wx.GridSizer`, `FlexGridSizer`) in source

**4.2** Create `ollamachat/ui/message_detail_dialog.py`:
- `class MessageDetailDialog(wx.Dialog):`
- `__init__(self, parent, role: str, text: str)` — sets title to `"Mensaje de Tú"` or `"Mensaje de IA"` based on role
- Sizer: VERTICAL BoxSizer
  - `wx.StaticText("Contenido:")`
  - `self.content_text = wx.TextCtrl(self, style=TE_MULTILINE|TE_READONLY, name="content_text")` — value = `strip_markdown(text)` from `core/text_utils`
  - `wx.StaticText("Acciones:")`
  - HORIZONTAL BoxSizer with 3 buttons: `open_browser_button`, `copy_button`, `close_button`
- `self.content_text.SetFocus()` in `__init__`
- Escape binding: `self.Bind(wx.EVT_CHAR_HOOK, ...)` or override `AcceptsFocusFromKeyboard` — cleanest: use `self.SetEscapeId(wx.ID_CANCEL)` and bind EVT_BUTTON on `close_button` to `EndModal(wx.ID_CANCEL)`
- Handlers for the 3 buttons (placeholders; real logic in `main_window._open_message_in_browser` and `wx.Clipboard`)
- **Source contains ZERO `MessageDialog` tokens** — AST test enforces

**4.3** Run `uv run --no-sync pytest tests/ui/test_message_detail_dialog_static.py -xvs`. Confirm 6/6 pass.

---

## Task 5: `ui/params_panel.py` — `use_model_button` (AST-driven)

**5.1** Add 3 AST assertions to `tests/ui/test_main_window_static.py` (the existing AST file for the main window area is the natural home for cross-module checks):
- `test_use_model_button_present` — assert `name="use_model_button"` in `params_panel.py` source
- `test_use_model_button_in_boxsizer` — assert `use_model_button` is added to a `wx.BoxSizer` (heuristic: appears in a `.Add(` call within a `BoxSizer` context)
- `test_use_model_button_disabled_initially` — assert `.Disable()` is called on `use_model_button` either in `__init__` or in `set_models([])`

**5.2** Modify `ollamachat/ui/params_panel.py`:
- In `__init__`, add `self.use_model_button = wx.Button(self, label="Usar modelo", name="use_model_button")` and `self.use_model_button.Disable()` and add to the model_sizer
- In `set_models(paths)`: if `paths` is non-empty, `use_model_button.Enable()`; else `use_model_button.Disable()`
- In `add_model(path)`: after `model_selector.Append(...)`, re-evaluate (enable if count > 0)
- Bind `EVT_COMBOBOX` on `model_selector` to a private handler that re-evaluates the button

**5.3** Run the extended `test_main_window_static.py`. Confirm all pass.

---

## Task 6: `ui/chat_panel.py` — dual view refactor (AST-driven, largest UI refactor)

**6.1** Add 3 new AST tests to `tests/ui/test_chat_panel_static.py`:
- `test_message_list_present` — `wx.ListBox(..., name="message_list", ...)` exists
- `test_stream_display_present` — `wx.TextCtrl(..., name="stream_display", ...)` with `TE_READONLY` exists
- `test_history_list_exists_in_init` — `self._history: list[tuple[str, str]] = []` (or equivalent) appears in `__init__`

**6.2** Refactor `ollamachat/ui/chat_panel.py`:
- `__init__`: add `self._history: list[tuple[str, str]] = []` and `self._is_generating: bool = False`
- Sizer change: REPLACE the single `conversation_display` block with:
  ```
  StaticText "Historial:" → message_list (ListBox)
  StaticText "Respuesta actual:" → stream_display (TextCtrl, ~4 lines, TE_MULTILINE|TE_READONLY|TE_RICH2)
  StaticText "Mensaje:" → message_input (unchanged)
  Buttons row (unchanged)
  ```
- New helper: `_preview(text)` returns first 80 chars after `text.replace("\n", " ").strip()`, suffixed with `"…"` if truncated
- Modify `append_user_message(text)`: append to `_history`, `message_list.Append(f"[Tú] {self._preview(text)}")`, `message_list.SetSelection(last)`, `stream_display.Clear()`
- Modify `append_assistant_prefix()`: `stream_display.Clear()`, `stream_display.AppendText("[Asistente] ")`
- Modify `append_assistant_chunk(token)`: `stream_display.AppendText(token)` (unchanged behavior, new control name)
- Modify `start_generation()`: also set `self._is_generating = True` and rebuild the context menu (remove `menu_delete_message`)
- Modify `end_generation()`: read `stream_display.GetValue()`, append to `_history`, `message_list.Append(f"[IA] {self._preview(text)}")`, `SetSelection(last)`, `stream_display.Clear()`, set `self._is_generating = False`, rebuild context menu (re-add `menu_delete_message`)
- Modify `clear()`: clear `message_list`, `_history`, `stream_display`, attachment (same as before)
- Add `get_message_at(index) -> tuple[str, str]` — returns `_history[index]`, raises `IndexError` naturally
- Add `get_history() -> list[tuple[str, str]]` — returns `list(self._history)` (a copy)
- Add `set_history(messages: list[tuple[str, str]])` — replaces `self._history`, clears and repopulates `message_list` with previews
- Add `_on_message_context_menu(event)`: builds a `wx.Menu` with `menu_copy_message` (Ctrl+C), `menu_open_browser` (Ctrl+Enter), and (conditionally) `menu_delete_message`. All items have `SetName(...)`. Bindings via `Bind(wx.EVT_MENU, ..., item)` for each
- Add `_on_list_key(event)`: decision tree per design §3.2 (Ctrl+C → clipboard, Ctrl+Enter → browser, Enter → popup, printable → input, else Skip)
- Add `_build_context_menu()` helper that returns the wx.Menu (called from `_on_message_context_menu` and rebuilt in start/end_generation)
- Bind `message_list.Bind(wx.EVT_CONTEXT_MENU, self._on_message_context_menu)` and `message_list.Bind(wx.EVT_KEY_DOWN, self._on_list_key)` and `message_list.Bind(wx.EVT_LISTBOX_DCLICK, self._on_message_dclick)` (open popup)

**6.3** Add 2 more AST tests:
- `test_no_conversation_display_reference` — assert zero hits for `conversation_display` in `chat_panel.py` (search-and-replace verification)
- `test_history_initialized_empty` — assert `_history: list[tuple[str, str]]` appears in `__init__`

**6.4** Run `uv run --no-sync pytest tests/ui/ -xvs` (all AST tests). Confirm all pass and `conversation_display` is fully gone.

---

## Task 7: `ui/main_window.py` — coordination (AST-driven, biggest module change)

This is the longest task. Break into sub-commits for review.

**7.1** New state attributes in `__init__`:
```python
self._is_generating = False
self._is_closing = False
self._temp_html_files: list[str] = []
self._last_usage: dict | None = None
self._focus_cycle_index = 0
self._last_beep_time = 0.0
self._loading_timer: threading.Timer | None = None
self._model_load_thread: threading.Thread | None = None
```

**7.2** Rename `start_server_button` → `restart_server_button`. Update lines 69, 70, 90, 209, 297, 312, 326 in main_window.py. Keep `_on_start_server` method name (it's still the same stop+start operation). Label changes from `"Iniciar servidor"` to `"Reiniciar servidor"`.

**7.3** Wire `use_model_button` to a new method `_on_use_model` (NOT the same as `_on_start_server`):
```python
def _on_use_model(self) -> None:
    model = self.params_panel.get_model()
    if not model or not Path(model).is_file():
        self._speech.speak("Archivo de modelo no encontrado", interrupt=True)
        return
    basename = Path(model).name
    self.params_panel.use_model_button.Disable()
    self.restart_server_button.Disable()
    self._speech.speak(f"Iniciando servidor con {basename}...", interrupt=True)
    self.status_bar.SetStatusText("Iniciando servidor...", 0)
    self._loading_timer = self._make_announce_timer()
    self._model_load_thread = threading.Thread(
        target=self._model_load_worker,
        args=(model,),
        daemon=True,
    )
    self._model_load_thread.start()
```

**7.4** Implement `_model_load_worker(model)`:
```python
def _model_load_worker(self, model: str) -> None:
    try:
        ok, message = start_server(model, self._client)
    finally:
        if self._loading_timer is not None:
            self._loading_timer.cancel()
        wx.CallAfter(self._on_start_server_done, ok, message)
```

**7.5** Implement `_make_announce_timer()`:
```python
def _make_announce_timer(self) -> threading.Timer:
    def _announce() -> None:
        if self._is_closing:
            return
        self._speech.speak("Cargando modelo, por favor espera...", interrupt=False)
        self._loading_timer = threading.Timer(8.0, _announce)
        self._loading_timer.daemon = True
        self._loading_timer.start()
    t = threading.Timer(8.0, _announce)
    t.daemon = True
    t.start()
    return t
```

**7.6** Implement `_on_start_server_done(ok, message)`:
```python
def _on_start_server_done(self, ok: bool, message: str) -> None:
    if self._loading_timer is not None:
        self._loading_timer.cancel()
        self._loading_timer = None
    if self._is_closing:
        return
    self.status_bar.SetStatusText("Servidor listo" if ok else "Error al iniciar", 0)
    if ok:
        loaded = self._client.get_loaded_model()
        self._update_title(loaded or None)
        if "corriendo" not in message:
            self._scan_models()
    self._sync_button_state(ok)
    self._speech.speak(message, interrupt=True)
```

**7.7** Implement `_update_title(model: str | None) -> None`:
```python
def _update_title(self, model: str | None) -> None:
    if model:
        self.SetTitle(f"OllamaChat — {Path(model).stem}")
    else:
        self.SetTitle("OllamaChat")
```

Call from `_on_start_server_done(ok=True, ...)` and from `_on_stop_server()` (reset to `"OllamaChat"`).

**7.8** Implement `_announce_session_status()` per design §2.3. Spanish decimals via `f"{x:.2f}".replace(".", ",")`. Single `speech.speak(..., interrupt=True)`.

**7.9** Implement `_set_initial_focus()` per design §3.7. Add `wx.CallAfter(self._set_initial_focus)` at the end of `__init__` (after `_startup_check`).

**7.10** Modify `_on_close(event)` per design §2.4:
- First line: `self._is_closing = True`
- Check `len(self._conversation.messages) > 0`; if yes, show `wx.MessageDialog` with stock YES_NO|NO_DEFAULT|ICON_QUESTION, text `"¿Salir sin guardar la conversación actual?"`. Veto on No.
- After confirmation (or no messages): `self._client.abort()`, `stop_server()`, then iterate `self._temp_html_files` with `try: os.unlink(p) except OSError: pass`; clear the list
- `event.Skip()`

**7.11** Implement `_maybe_beep()` per design §3.7. Call from `_on_token` after `append_assistant_chunk`.

**7.12** Implement `_open_message_in_browser(text)` per design §3.2 (lazy imports, tempfile with `delete=False`, `webbrowser.open`, append to `self._temp_html_files`).

**7.13** Implement `_on_usage(usage)`:
```python
def _on_usage(self, usage: dict) -> None:
    self._last_usage = usage
    self.status_bar.SetStatusText(f"Tokens: {usage.get('total_tokens', 0)}", 1)
```

Pass as the `on_usage` kwarg in the `chat_stream` call inside `send_message`.

**7.14** Update `save_conversation()` (line 518):
```python
Conversation.save(
    self._conversation, filepath,
    system_prompt=self.params_panel.get_system_prompt(),
)
```

**7.15** Update `load_conversation()` (lines 522–555):
- Replace `self._conversation = Conversation.load(filepath)` with tuple unpack
- `self.params_panel.set_system_prompt(system_prompt)`
- `self.chat_panel.set_history([(m["role"], m["content"]) for m in self._conversation.messages])`
- DELETE the manual rebuild loop (lines 537–544)
- Speech + error handling unchanged

**7.16** Extend `_build_accelerators()` (line 175). Add 8 new entries: Alt+1, Alt+2, Alt+3, Alt+4, Alt+5, Alt+6, F2, F6. Define new `wx.NewIdRef()` IDs (or use a fixed block like `ID_FOCUS_INPUT = 1000`, etc.). Bind handlers (`_on_focus_input`, `_on_focus_list`, etc.).

**7.17** Add 5 new AST tests to `tests/ui/test_main_window_static.py`:
- `test_use_model_button_present` — assert `name="use_model_button"` and `_on_use_model` exists
- `test_f2_accelerator_present` — assert `WXK_F2` appears in the accelerator entries
- `test_announce_session_status_method_exists` — assert the method definition
- `test_open_message_in_browser_method_exists`
- `test_temp_html_files_list_initialized` — assert `self._temp_html_files: list[str]` in `__init__`

**7.18** Update `_show_shortcuts()` text to include Alt+1..6, F2, F6.

---

## Task 8: `pyproject.toml`

Add `markdown = ">=3.5"` to the `dependencies` list, between `requests>=2.31` and the closing bracket. Run `uv lock` (or `uv pip compile`) to update the lockfile.

---

## Task 9: Documentation

**9.1** `CHANGELOG.md` — prepend an `[0.3.0] - 2026-06-22` entry with `### Agregado` listing the 15 sub-features grouped by area (vista dual, atajos, foco, etc.), `### Cambiado` for the `start_server_button` → `restart_server_button` rename and `Conversation.save`/`load` signature change, `### Conocido` for the WSL-only verification limitation.

**9.2** `AGENTS.md` — add a one-paragraph note in the "Layout del proyecto" section mentioning `text_utils.py` and `message_detail_dialog.py`. Update the "Reglas adicionales de controles" list to include the dual-view invariant (ListBox is preferred over TextCtrl for NVDA-navigable lists).

**9.3** `README.md` — add an "Atajos de teclado" section with a list (NOT a table — NVDA reads cell-by-cell) of the 8 new bindings: Alt+1..6, F2, F6, plus the existing Ctrl+N/O/S, F5, Escape.

---

## Task 10: Verify

**10.1** `uv run --no-sync pytest -xvs` — full run. Expected: ~132 tests passing. If any test fails, fix and re-run.

**10.2** Manual `[windows-only]` verify (documented in the PR description, not automated):
- NVDA focus traversal: Tab through ListBox + stream_display (the order matters — Historial first, then Respuesta actual, then Mensaje)
- F2 announcement: reads model, server status, msg count, tokens, temp, top_p, generating — all in Spanish with comma decimals
- Alt+N shortcuts: each one focuses the documented control
- MessageDetailDialog Tab order: content_text (auto-focused) → open_browser → copy → close
- Context menu on the list: shows 3 items idle, 2 items during generation
- Beep during generation: audible on Windows, no-op on WSL/Linux
- Window title: updates when server starts, resets on stop

**10.3** Update `CHANGELOG.md` "Conocido" with any new limitations discovered during the verify.

---

## Commit plan (work-unit-commits)

Per the `work-unit-commits` skill, each task is one or more reviewable commits. Suggested grouping:

1. **commit 1**: Task 1 (text_utils + 8 tests)
2. **commit 2**: Task 2 (conversation + 3 tests)
3. **commit 3**: Task 3 (llama_client on_usage + 2 tests)
4. **commit 4**: Task 4 (MessageDetailDialog + 6 AST tests)
5. **commit 5**: Task 5 (params_panel use_model_button + 3 AST assertions)
6. **commit 6**: Task 6 (chat_panel dual view refactor + 5 AST tests)
7. **commit 7**: Task 7.1–7.2 (state attrs + button rename)
8. **commit 8**: Task 7.3–7.7 (use_model + bg load + done handler + title)
9. **commit 9**: Task 7.8–7.11 (F2, focus, close, beep)
10. **commit 10**: Task 7.12–7.13 (browser + on_usage)
11. **commit 11**: Task 7.14–7.16 (save/load update + accelerators)
12. **commit 12**: Task 7.17–7.18 (AST tests + shortcuts dialog)
13. **commit 13**: Task 8 (pyproject)
14. **commit 14**: Task 9 (docs)
15. **commit 15**: Task 10 (CHANGELOG "Conocido" update + version bump in pyproject.toml + CHANGELOG header)

Each commit is independently buildable and the test suite passes at every commit boundary. Core/ commits (1–3) can ship independently; UI commits (4–12) must come in order.
