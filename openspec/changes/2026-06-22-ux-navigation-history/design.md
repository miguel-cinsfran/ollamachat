# Design: 2026-06-22-ux-navigation-history (v0.3.0)

## 0. Goals & non-goals

**Goals.** Convert the v0.2.0 baseline (single scrolling transcript, blocking server start, no shortcuts) into an NVDA-navigable app: a `wx.ListBox` of message previews, a focused read-only `stream_display` for the live response, a per-message detail dialog with browser rendering, an `Alt+N` accelerator table, F2 status announcement, token-usage capture, and a Windows beep while generating. The 8 NVDA blockers in the proposal are each addressed by exactly one or two of the 15 sub-features A–O.

**Non-goals (explicit).** Tool calling (v0.4.0 — `permission_manager`, `permission_dialog`, `tool_executor`, `shell_execute`); persistent session state across restarts; search/filter in the message list; multi-tab; image content in the popup (popup shows stripped text only); distribution / PyInstaller; renaming the `ollamachat` package.

---

## 1. Architecture overview

### Component diagram

```
┌────────────────────────────────────────────────────────────────────┐
│                         MainWindow (ui/)                           │
│                                                                    │
│  ┌──────────────┐   ┌──────────────┐   ┌────────────────────────┐  │
│  │ Splitter     │   │ Toolbar      │   │ Status bar (3 fields)  │  │
│  │              │   │ restart_     │   │  0: server state       │  │
│  │              │   │ stop_        │   │  1: tokens             │  │
│  │              │   │              │   │  2: generation state   │  │
│  └──────┬───────┘   └──────────────┘   └────────────────────────┘  │
│         │                                                            │
│    ┌────┴─────┐                                                      │
│    │          │                                                      │
│    ▼          ▼                                                      │
│ ┌──────────┐ ┌──────────────────────────────────────────────────┐  │
│ │ Params   │ │ ChatPanel (ui/)                                   │  │
│ │ Panel    │ │  ┌─ message_list  (ListBox)   ─┐  StaticText    │  │
│ │          │ │  │  [Tú] Hola ¿cómo estás?     │  "Historial:"  │  │
│ │ use_     │ │  │  [IA] Bien, gracias. ...     │                │  │
│ │ model_   │ │  └─────────────────────────────┘                │  │
│ │ button   │ │  ┌─ stream_display (TextCtrl) ─┐  StaticText    │  │
│ │ restart_ │ │  │  [Asistente] Bien, gracias. │  "Respuesta    │  │
│ │ server_  │ │  │  (live streaming)           │   actual:"     │  │
│ │ button   │ │  └─────────────────────────────┘                │  │
│ │ sliders  │ │  ┌─ message_input (TextCtrl)  ─┐  StaticText    │  │
│ │ system_  │ │  │  Type here…                  │  "Mensaje:"   │  │
│ │ prompt   │ │  └─────────────────────────────┘                │  │
│ └────┬─────┘ │  [Enviar] [Detener] [Adjuntar] [Limpiar]         │  │
│      │       └──────────────────────────────────────────────────┘  │
└──────┼──────────────────────────────────────────────────────────────┘
       │
       │ invokes
       ▼
┌────────────────────────────────────────────────────────────────────┐
│                       core/  (wx-free at module level)             │
│                                                                    │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐ │
│  │ LlamaClient      │  │ LlamaRunner      │  │ Conversation     │ │
│  │  - chat_stream() │  │  - start_server  │  │  - save(conv,    │ │
│  │    (daemon)      │  │  - stop_server   │  │     path, sp="") │ │
│  │  - check_        │  │  - find_gguf     │  │  - load(path)    │ │
│  │    running       │  │  - find_llama_   │  │    -> (Conv, sp) │ │
│  │  - get_loaded_   │  │    server        │  └──────────────────┘ │
│  │    model         │  └──────────────────┘                        │
│  └──────────────────┘                                             │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐ │
│  │ text_utils       │  │ Speech           │  │ logger           │ │
│  │  - strip_        │  │  - speak()       │  │  - get_logger()  │ │
│  │    markdown()    │  │  - announce_     │  └──────────────────┘ │
│  │  (NEW, re-only)  │  │    token_chunk() │                        │
│  └──────────────────┘  └──────────────────┘                        │
└────────────────────────────────────────────────────────────────────┘

Auxiliary:
  - MessageDetailDialog (ui/message_detail_dialog.py) — modal popup
  - markdown (3rd-party, NEW) — html rendering for browser open
  - webbrowser (stdlib) — opens the .html temp file
```

### Threading model

| Thread | Owner | Lifespan | wx crossing |
|---|---|---|---|
| Main (wx) | always | app lifetime | direct |
| `LlamaClient._stream_thread` (daemon) | `LlamaClient.chat_stream` | per request | `wx.CallAfter` only |
| `_model_load_thread` (daemon, NEW) | `MainWindow._on_use_model` | per start (10–60s) | `wx.CallAfter` only |
| `_loading_announce_timer` (`threading.Timer`, NEW) | `_model_load_thread` | chained inside the load thread, cancelled on done | `wx.CallAfter(speech.speak, ..., interrupt=False)` |

**Rule of one bridge:** only `wx.CallAfter` crosses from any background thread to wx. Direct calls to `self.SetStatusText`, `self.chat_panel.AppendText`, etc. from a worker are forbidden — they crash or no-op. The two new threads must follow the existing `chat_stream` discipline.

**Daemon guarantee:** all background threads are `daemon=True` so the interpreter exits even if they hang. `threading.Timer` is daemon by default; assert it.

### File-level dependency graph

```
ollamachat/
  main.py
    └─> ui/main_window.py
  core/
    conversation.py         stdlib only (json, datetime, pathlib)
    llama_client.py         stdlib + requests; wx imported INSIDE _stream_worker
    llama_runner.py         stdlib only
    speech.py               accessible-output2; try/except in constructor
    logger.py               stdlib logging
    text_utils.py  (NEW)    stdlib re only; headless on WSL
  ui/
    main_window.py          wx + all of core/
    chat_panel.py           wx; depends on core/text_utils for preview text
    params_panel.py         wx; depends on core/llama_runner.find_gguf_models
    message_detail_dialog.py  (NEW) wx; uses core/text_utils.strip_markdown
```

`core/` has zero `import wx` at module level. `ui/` may import `wx` at module level. The dependency arrow points only one way: `ui/ → core/`, never `core/ → ui/`.

---

## 2. Sequence diagrams

### 2.1 Background model loading (the hardest one)

```
User clicks use_model_button  (params_panel.use_model_button)
  └─> MainWindow._on_use_model
        ├─> model = params_panel.get_model()
        ├─> if not Path(model).is_file(): speech + return  (fail-fast, no spawn)
        ├─> params_panel.use_model_button.Disable()
        ├─> main_window.restart_server_button.Disable()
        ├─> status_bar "Iniciando servidor..."
        ├─> wx.CallAfter(speech.speak, f"Iniciando servidor con {basename}...",
        │                interrupt=True)
        ├─> self._loading_timer = self._make_announce_timer()  # see below
        └─> spawn daemon thread:
              threading.Thread(target=self._model_load_worker,
                               args=(model, self._loading_timer),
                               daemon=True).start()

_model_load_worker(model, timer)   # runs in daemon thread
  └─> try:
        ok, message = start_server(model, self._client)   # existing core/ call
      finally:
        # ALWAYS: cancel the announce timer, even on error
        timer.cancel()
        wx.CallAfter(self._on_start_server_done, ok, message)

_make_announce_timer()
  # 8-second chained timer; each tick re-arms itself while loading.
  # Self-cancelling when the worker thread finishes.
  def _announce():
      if self._is_closing: return
      wx.CallAfter(speech.speak, "Cargando modelo, por favor espera...",
                   interrupt=False)
      self._loading_timer = threading.Timer(8.0, _announce)
      self._loading_timer.daemon = True
      self._loading_timer.start()
  t = threading.Timer(8.0, _announce)
  t.daemon = True
  t.start()
  return t

_on_start_server_done(ok, message)   # runs in main thread via CallAfter
  ├─> self._loading_timer.cancel()           # belt + suspenders
  ├─> status_bar = "Servidor listo" | "Error al iniciar"
  ├─> if ok: _sync_button_state(True);  _update_title(loaded_model)
  ├─> else:  _sync_button_state(False)
  └─> speech.speak(message, interrupt=True)
```

**Close race guard:** `self._is_closing` is set in `_on_close` BEFORE `self._client.abort()` and `stop_server()`. The timer's `_announce` closure checks it on every tick to avoid a `wx.CallAfter` landing on a destroyed window. Same check guards the worker's final `CallAfter(_on_start_server_done, ...)` — actually the worker's CallAfter is unconditional; the destroyed-window crash is prevented by the order: `_on_close` runs `abort()` + `stop_server()` first, so `start_server` returns quickly with `(False, "shutdown")`; the worker's `try/finally` cancels the timer and calls `CallAfter` to `_on_start_server_done`, which short-circuits on `self._is_closing` (added to that handler too).

### 2.2 Send + stream + end (existing flow, refactored display)

```
User types text, presses Enter (or clicks Enviar)
  └─> ChatPanel._on_input_enter
        └─> MainWindow.send_message
              ├─> api_messages = [system, *history, user]
              ├─> conversation.add_message("user", stored_text)
              ├─> chat_panel.append_user_message(text)
              │     └─> _history.append(("user", text))
              │     └─> message_list.Append("[Tú] <preview>")
              │     └─> message_list.SetSelection(last)
              ├─> chat_panel.start_generation()
              ├─> chat_panel.append_assistant_prefix()
              │     └─> stream_display.Clear()
              │     └─> stream_display.AppendText("[Asistente] ")
              ├─> self._is_generating = True
              └─> self._client.chat_stream(messages, options,
                              on_token=_on_token,
                              on_done=_on_done,
                              on_error=_on_error,
                              on_usage=_on_usage)        # NEW

# Streaming (background thread → main via CallAfter)
_on_token(token)
  ├─> self._current_response += token
  ├─> chat_panel.append_assistant_chunk(token)
  │     └─> stream_display.AppendText(token)            # ONLY here
  ├─> self._maybe_beep()                                # NEW (Windows)
  └─> speech.announce_token_chunk(token)

_on_done()
  ├─> speech.flush_token_buffer(); speech.speak("Respuesta completa")
  ├─> conversation.add_message("assistant", _current_response)
  ├─> chat_panel.append_assistant_chunk("\n")
  ├─> chat_panel.end_generation()
  │     ├─> final = stream_display.GetValue()
  │     ├─> _history.append(("assistant", final))
  │     ├─> message_list.Append("[IA] <preview>")
  │     ├─> message_list.SetSelection(last)
  │     └─> stream_display.Clear()
  └─> self._is_generating = False

_on_error(text)
  ├─> chat_panel.append_assistant_chunk(f"\n[Error: {text}]")
  ├─> chat_panel.end_generation()       # partial still moved to history
  ├─> self._is_generating = False
  └─> MessageDialog(text) + speech(text)

_on_usage(usage)                          # NEW
  ├─> self._last_usage = usage
  └─> status_bar.SetStatusText(f"Tokens: {usage.get('total_tokens', 0)}", 1)
```

### 2.3 F2 session status

```
User presses F2  (AcceleratorTable → _on_f2)
  └─> MainWindow._announce_session_status
        ├─> model_str  = Path(self._client.get_loaded_model()).stem
        │                or "sin modelo cargado"
        ├─> server_str = "en ejecución" if check_running() else "detenido"
        ├─> msg_str    = f"{len(conversation.messages) // 2} mensajes"
        ├─> tokens_str = (f"{_last_usage['total_tokens']} tokens"
        │                if _last_usage else "Tokens: sin información")
        ├─> temp_str   = f"{temp:.2f}".replace(".", ",")
        ├─> topp_str   = f"{top_p:.2f}".replace(".", ",")
        ├─> gen_str    = "Generando: Sí" if _is_generating else "Generando: No"
        └─> speech.speak(
              f"Modelo {model_str}. {server_str}. {msg_str}. {tokens_str}. "
              f"Temperatura {temp_str}. Top-p {topp_str}. {gen_str}.",
              interrupt=True)
```

### 2.4 Close with confirmation

```
User closes the window (X / Alt+F4)
  └─> MainWindow._on_close(event)
        ├─> self._is_closing = True             # NEW: gate background threads
        ├─> if len(self._conversation.messages) > 0:
        │     dlg = wx.MessageDialog(
        │       self,
        │       message="¿Salir sin guardar la conversación actual?",
        │       caption="Confirmar salida",
        │       style=wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION)
        │     result = dlg.ShowModal(); dlg.Destroy()
        │     if result != wx.ID_YES:
        │         event.Veto()
        │         return                          # abort+stop NOT called
        ├─> self._client.abort()
        ├─> stop_server()
        ├─> for p in self._temp_html_files:
        │     try:   os.unlink(p)
        │     except OSError:  pass              # browser may have it open
        ├─> self._temp_html_files.clear()
        └─> event.Skip()
```

---

## 3. Component design

### 3.1 `text_utils` (new module)

**Public API:** `strip_markdown(text: str) -> str`. The implementation is a fixed pipeline of `re.sub` calls in the order given by the spec: headers → bold → italic → fenced code → inline code → links → list items → `strip()`. Each substitution is anchored (`^` for headers and list items) or non-greedy (`*?`, `+?`) to avoid eating too much. The module imports nothing but `re` and `string` (if needed for printable helpers). It is importable on WSL where wxPython is not built.

**Edge cases handled:** empty string returns empty string; plain text returns the text after `strip()`; fenced code blocks with language hints (`` ```python ``) are reduced to inner text only; nested emphasis is not handled (intentional — it's rare and the spec doesn't require it); HTML tags inside markdown are not stripped (the spec doesn't require it; the popup's TextCtrl is read-only so tags appear as literal text — acceptable).

**Test strategy:** 8 unit tests as spec'd; each test maps to one Given/When/Then scenario in the spec delta. Strict TDD: write the test, watch it fail, then implement.

### 3.2 `chat` — dual view + popup + context menu + browser

**`ChatPanel` refactor.** The single `self.conversation_display` is replaced by two controls:
- `self.message_list: wx.ListBox` (`name="message_list"`) preceded by `wx.StaticText("Historial:")`. Default selection is "no item"; `SetSelection` is called on every append to make NVDA announce the new item.
- `self.stream_display: wx.TextCtrl` (`name="stream_display"`, `TE_MULTILINE|TE_READONLY|TE_RICH2`, fixed height ~4 lines) preceded by `wx.StaticText("Respuesta actual:")`. The `~4 lines` is enforced by sizing the TextCtrl with a fixed height in the sizer (`flag=wx.EXPAND` with a min-size constraint, or wrap in a `wx.Panel` with a `BoxSizer` that has a proportion=0). The TextCtrl is cleared at the start of each generation and populated only with the current assistant turn.

**Parallel state.** `self._history: list[tuple[str, str]]` mirrors the canonical transcript; `message_list` only holds preview strings (first 80 chars after `strip_markdown` + newlines collapsed to spaces, suffixed with `…` when truncated). The full text is always in `_history` and retrievable via `get_message_at(i)`. The three public accessors (`get_message_at`, `get_history`, `set_history`) operate on `_history` only — they return pure-Python tuples, never wx objects, so `core/` can be tested headless.

**Preview text generation.** Helper: `_preview(text: str) -> str` returns the first 80 chars of `text.replace("\n", " ").strip()[:80] + ("…" if len > 80 else "")`. The 80-char cap is enforced in the spec.

**`end_generation()`** is now responsible for moving the stream content into the history: it reads `stream_display.GetValue()`, appends to `_history`, adds the preview to `message_list`, calls `SetSelection(last)`, and calls `stream_display.Clear()`. This runs in both `_on_done` AND `_on_error` so partial responses are preserved.

**Context menu.** `_on_message_context_menu` builds a `wx.Menu` with three items: `menu_copy_message` (Ctrl+C), `menu_open_browser` (Ctrl+Enter), `menu_delete_message`. The third item is removed at the start of `start_generation()` and re-added at the end of `end_generation()`. All items have `SetName(...)` for MSAA. Bindings: `EVT_CONTEXT_MENU` on `message_list`.

**Key routing.** `message_list.Bind(wx.EVT_KEY_DOWN, self._on_list_key)`. Decision tree (in order):
- if `event.ControlDown() and event.GetKeyCode() == ord("C")` → copy via `wx.Clipboard`; `speech.speak("Mensaje copiado", interrupt=False)`; consume
- elif `event.ControlDown() and event.GetKeyCode() == wx.WXK_RETURN` → call `MainWindow._open_message_in_browser(selected_text)`; consume
- elif `event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER)` and not `event.ShiftDown()` → open `MessageDetailDialog` modal; consume
- elif printable char (no Ctrl/Alt/Meta) → `message_input.SetFocus()`; `message_input.AppendText(chr(key))`; `message_input.SetInsertionPointEnd()`; consume
- else `event.Skip()`

**`MessageDetailDialog`.** Custom `wx.Dialog` (`name="message_detail_dialog"`). Sizer order (NON-NEGOTIABLE per AGENTS.md and the spec):
1. `wx.StaticText("Contenido:")` (no name needed; labels are static)
2. `self.content_text = wx.TextCtrl(self, style=TE_MULTILINE|TE_READONLY, name="content_text", value=strip_markdown(text))`
3. `wx.StaticText("Acciones:")`
4. Horizontal `wx.BoxSizer` with three native `wx.Button`s: `open_browser_button`, `copy_button`, `close_button`

In `__init__`, call `self.content_text.SetFocus()` so NVDA reads the content immediately. Bind `EVT_BUTTON` for each button. Bind Escape to `EndModal(wx.ID_CANCEL)`. **Zero `MessageDialog` tokens** in the source — enforced by the AST test `test_message_detail_dialog_static.py`.

**`_open_message_in_browser`.** Lazy import `markdown` and `webbrowser` inside the method (avoids hard dep at import time). The pipeline:
```python
html = markdown.markdown(text, extensions=[])   # default safe mode
with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as f:
    f.write(f"<!doctype html><meta charset='utf-8'><body>{html}</body>")
    temp_path = f.name
self._temp_html_files.append(temp_path)
webbrowser.open(f"file:///{temp_path}")
```

The temp file is NOT deleted by the function — `_on_close` does it (browser may have it open).

**Search-and-replace list.** The refactor REPLACES `conversation_display` (no backwards compat needed — it was an internal name). Locations to update in `chat_panel.py`:
- line 37: `wx.StaticText(self, label="Conversación:")` → two separate labels
- lines 40–45: the `conversation_display` TextCtrl → split into `message_list` + `stream_display`
- line 154: `self.conversation_display.AppendText(...)` in `append_user_message` → new ListBox logic
- line 158: `self.conversation_display.AppendText("[Asistente] ")` in `append_assistant_prefix` → `stream_display` logic
- line 166: `self.conversation_display.AppendText(token)` in `append_assistant_chunk` → `stream_display`
- line 257: `self.conversation_display.Clear()` in `clear` → both new controls

### 3.3 `accessibility-guidelines` — accelerators

**Accelerator table.** The existing `_build_accelerators` (main_window.py:175) gets extended. New entries (additive — existing Ctrl+N/O/S, F5, Escape preserved):
| Key | wx flag | wx ID | Handler |
|---|---|---|---|
| Alt+1 | `ACCEL_ALT` | new `ID_FOCUS_INPUT` | `_on_focus_input` |
| Alt+2 | `ACCEL_ALT` | new `ID_FOCUS_LIST` | `_on_focus_list` |
| Alt+3 | `ACCEL_ALT` | new `ID_FOCUS_MODEL` | `_on_focus_model` |
| Alt+4 | `ACCEL_ALT` | new `ID_FOCUS_TEMP` | `_on_focus_temp` |
| Alt+5 | `ACCEL_ALT` | new `ID_FOCUS_SYSPROMPT` | `_on_focus_sysprompt` |
| Alt+6 | `ACCEL_ALT` | new `ID_FOCUS_USE` | `_on_focus_use` |
| F2 | `ACCEL_NORMAL` | new `ID_F2` | `_announce_session_status` |
| F6 | `ACCEL_NORMAL` | new `ID_F6` | `_on_f6_cycle` |

The handlers focus the right control. `_on_focus_list` additionally calls `message_list.SetSelection(message_list.GetCount() - 1)` and `speech.speak(f"Historial, {count} mensajes", interrupt=True)`. `_on_focus_use` falls back to `restart_server_button` if `use_model_button` is disabled.

**F6 cycle.** `self._focus_cycle_index = 0` (instance attr). The cycle is `[params_panel.model_selector, chat_panel.message_list, chat_panel.message_input]`. On F6, increment modulo 3, then `wx.CallAfter` to the focus target (CallAfter avoids the focus race that happens when a focus event triggers within a focus handler). The F6 handler speaks `"Panel N de 3"` after cycling.

### 3.4 `parameters` — `use_model_button` + system prompt API

**Button placement.** Added to the existing `model_sizer` in `params_panel.py` (the row that already contains `scan_models_button` and `browse_model_button`). Order: scan, browse, **use_model** (the new one). A `wx.StaticText("Acciones del modelo:")` precedes the row, OR the row inherits the existing label — to be confirmed by reading the current `params_panel.py` (not done in this design pass; the spec says "or grouped under a parent label", so either is acceptable).

**Enable/disable logic.**
- `set_models([])` → `use_model_button.Disable()` (no model to use)
- `set_models([...])` → `use_model_button.Enable()` (first item is auto-selected by ComboBox)
- `add_model(...)` → re-evaluate: enable if `model_selector.GetCount() > 0`
- On `model_selector` selection change → re-evaluate (handler bound in `_build_ui`)

**Rename.** `start_server_button` → `restart_server_button` (name + label "Reiniciar servidor"). The handler `_on_start_server` stays the same (it's still a stop+start cycle). References in main_window.py to update:
- line 69: `self.start_server_button = wx.Button(..., name="start_server_button", label="Iniciar servidor")` → new label/name
- line 90: `toolbar_sizer.Add(self.start_server_button, ...)` → use renamed attr
- line 209: `self.start_server_button.Enable()` in `_sync_button_state` → use renamed attr
- line 297: `self.start_server_button.Disable()` in `_on_start_server` → use renamed attr
- lines 312, 326: button state updates in handlers → use renamed attr

**System prompt API.** `get_system_prompt()` and `set_system_prompt(sp)` already exist (per the spec delta); unchanged. Used by `MainWindow.save_conversation` (read) and `MainWindow._on_load_conversation` (write).

### 3.5 `conversation-persistence` — system prompt in JSON

**Signature change.**
- `Conversation.save(conv, filepath, system_prompt: str = "")` — new positional/keyword `system_prompt`.
- `Conversation.load(filepath) -> tuple[Conversation, str]` — returns tuple instead of `Conversation`.

**JSON format** (top level):
```json
{
  "system_prompt": "Eres un asistente útil.",
  "messages": [
    {"role": "user", "content": "...", "timestamp": "..."},
    {"role": "assistant", "content": "...", "timestamp": "..."}
  ]
}
```

**Implementation.** In `save`:
```python
data = conv.to_dict()  # {"messages": [...]}
full = {"system_prompt": system_prompt, **data}
json.dump(full, f, indent=2, ensure_ascii=False)
```

In `load`:
```python
data = json.load(f)
sp = data.get("system_prompt", "")   # backward compat: missing → ""
body = {"messages": data.get("messages", [])}
return cls.from_dict(body), sp
```

**Call sites to update** in main_window.py:
- line 518: `Conversation.save(self._conversation, filepath)` → `Conversation.save(self._conversation, filepath, system_prompt=self.params_panel.get_system_prompt())`
- line 535: `self._conversation = Conversation.load(filepath)` → `self._conversation, system_prompt = Conversation.load(filepath)`, then `self.params_panel.set_system_prompt(system_prompt)` and `self.chat_panel.set_history([(m["role"], m["content"]) for m in self._conversation.messages])`

The current load loop (lines 537–544) is DELETED — `set_history` replaces it.

**Test strategy:** 3 new tests (save includes, load returns tuple, backward compat). Strict TDD.

### 3.6 `llama-integration` — `on_usage` callback

**New param.** `chat_stream(messages, options, on_token, on_done, on_error, on_usage: Callable[[dict], None] | None = None)`. Backward compatible: default `None`, existing callers don't change.

**Worker change.** Inside `_stream_worker`, after `chunk = json.loads(payload)` and BEFORE the `content` extraction:
```python
if on_usage is not None:
    usage = chunk.get("usage")
    if usage is not None:
        wx.CallAfter(on_usage, usage)
```

Then the existing `content` extraction continues. The usage detection is non-blocking (it just enqueues a CallAfter) and the rest of the chunk processing is unchanged.

**Test strategy:** 2 new tests:
- `test_chat_stream_calls_on_usage_when_present`: stub a stream whose final chunk has `{"usage": {...}}`, assert `on_usage` was called with the dict
- `test_chat_stream_no_error_when_usage_absent`: stub a stream with no usage key, assert no exception and `on_token`/`on_done` were called normally

### 3.7 `app-shell` — background, focus, close, title, beep

**Background model loading.** Described fully in §2.1. The implementation lives in `MainWindow._on_use_model` + `_model_load_worker` + `_make_announce_timer`. The existing `start_server` in `llama_runner.py` is UNCHANGED — the proposal explicitly says not to touch it; the polling already releases the lock so the worker can be interrupted by `stop_server()` if the user clicks Stop.

**Initial focus.** End of `MainWindow.__init__` adds `wx.CallAfter(self._set_initial_focus)`. The method:
```python
def _set_initial_focus(self):
    if self._client.check_running():
        self.chat_panel.message_input.SetFocus()
    elif self.params_panel.model_selector.GetCount() > 0:
        self.params_panel.use_model_button.SetFocus()
    else:
        self.params_panel.scan_models_button.SetFocus()
```

`wx.CallAfter` defers the focus to the next event loop tick, by which time the window is fully realized and the focus race is avoided.

**Close confirmation.** Described in §2.4. The `wx.MessageDialog` uses stock `YES_NO` labels (NO `SetYesNoCancelLabels`); per AGENTS.md, only custom labels regress MSAA.

**Window title.** `_update_title(model: str | None)`:
```python
def _update_title(self, model: str | None) -> None:
    if model:
        self.SetTitle(f"OllamaChat — {Path(model).stem}")
    else:
        self.SetTitle("OllamaChat")
```
Called from `_on_start_server_done(ok=True, ...)` (with the loaded model from `self._client.get_loaded_model()`) and from `_on_stop_server()`. The fallback when `ok=False` is to NOT change the title (the old title remains, which is honest — no model loaded).

**Beep.** `_maybe_beep()`:
```python
def _maybe_beep(self) -> None:
    if sys.platform != "win32":
        return
    now = time.monotonic()
    if now - self._last_beep_time < 1.0:
        return
    self._last_beep_time = now
    try:
        import winsound
        winsound.Beep(520, 50)
    except Exception:
        pass
```

`winsound` is imported INSIDE the function (after the platform guard) so the module imports cleanly on WSL. Called from `_on_token` AFTER `append_assistant_chunk`. `self._last_beep_time = 0.0` is set in `__init__`.

### 3.8 `speech` — beep + F2 status

**Beep.** Already described in §3.7. The cross-ref is that the beep is NOT a `Speech.speak` call — it's a direct `winsound.Beep`. The `Speech` instance being silent (`is_silent is True`) MUST NOT prevent the beep from firing on Windows. The spec delta encodes this.

**F2 status.** Already described in §2.3. The composed string is spoken via `speech.speak(..., interrupt=True)`. Numbers are formatted with `f"{x:.2f}".replace(".", ",")` to get Spanish decimal notation (e.g. `0,70` not `0.70`). The `interrupt=True` is critical so the status announcement doesn't get queued behind streaming speech.

**Loading announcements.** Already described in §2.1. Use `speech.speak(..., interrupt=False)` — the `interrupt=False` is intentional so it doesn't cut off the in-progress streaming speech (if the user is mid-sentence when the 8s tick fires).

---

## 4. State & lifecycle

New instance attributes on `MainWindow` (set in `__init__` unless noted):

| Attr | Type | Default | Set in | Read in | Cleared in |
|---|---|---|---|---|---|
| `_is_generating` | `bool` | `False` | `send_message` | `_announce_session_status`, context menu | `_on_done`, `_on_error` |
| `_is_closing` | `bool` | `False` | `_on_close` (very first line) | `_on_start_server_done`, `_announce`, `_maybe_beep` (defensive) | (process exit) |
| `_temp_html_files` | `list[str]` | `[]` | `_open_message_in_browser` | `_on_close` (for unlink) | `_on_close` (after unlink) |
| `_last_usage` | `dict \| None` | `None` | `_on_usage` | `_announce_session_status` | (only on app restart) |
| `_focus_cycle_index` | `int` | `0` | `__init__` | `_on_f6_cycle` | (wraps modulo 3) |
| `_last_beep_time` | `float` | `0.0` | `__init__` | `_maybe_beep` | (only on app restart) |
| `_loading_timer` | `threading.Timer \| None` | `None` | `_make_announce_timer` (when start begins) | `_on_start_server_done` (cancel), `_on_close` (cancel defensive) | set to `None` after cancel |
| `_model_load_thread` | `threading.Thread \| None` | `None` | `_on_use_model` (after spawn) | (none — fire-and-forget) | (process exit) |

New instance attribute on `ChatPanel`:

| Attr | Type | Default | Set in | Read in |
|---|---|---|---|---|
| `_history` | `list[tuple[str, str]]` | `[]` | `__init__` | `get_message_at`, `get_history`, `append_*` |

The timer ownership is the most error-prone part: the timer is CREATED in the worker thread's context (inside `_make_announce_timer`, which is called from the main thread just before spawning the worker), but the timer's CALLBACK runs in its own thread. The cancel must be called from BOTH the worker's `finally` block AND `_on_start_server_done` AND `_on_close` (three times — defense in depth). The cancel is idempotent (`threading.Timer.cancel` is safe to call multiple times).

---

## 5. Risks

These are flagged, not resolved. The mitigation column is what the apply phase should pay attention to; some are explicit AST tests, some are `[windows-only]` manual verifications.

| Risk | Where it lives | Mitigation in apply phase |
|---|---|---|
| ChatPanel refactor breaks the 9 existing AST assertions in `test_chat_panel_static.py` | chat capability | The 3 new tests (test_message_list_present, test_stream_display_present, test_history_list_exists_in_init) are ADDITIVE; old assertions about `conversation_display` must be removed in the same commit. Strict TDD order: write new tests, watch them fail, refactor, watch them pass. |
| NVDA tab order between `message_list` and `stream_display` is not enforced by code | chat + accessibility-guidelines | AST test on sizer construction order (StaticText "Historial:" before `message_list`, StaticText "Respuesta actual:" before `stream_display`). Manual `[windows-only]` verify with NVDA focus traversal. |
| `markdown` library injects unsafe HTML into user's browser | chat + new dep | Use `markdown.markdown(text)` with default safe mode (escapes raw HTML). Output is opened in the user's default browser (sandboxed by the OS). User-initiated only. Documented in code comment. |
| Background load + close race fires `wx.CallAfter` after window destroyed | app-shell | `self._is_closing` guard in `_on_start_server_done`, `_announce`, and the timer callback. AST test: search for `self._is_closing` in the new code paths. |
| `_on_close` still blocks up to 5s on `stop_server` (S2 from prior verify) | app-shell | Accepted; close is the only blocking call left. Document with a code comment. Future improvement (v0.4.0?): spawn a shutdown thread. |
| `winsound` import on non-Windows breaks WSL tests | app-shell | `import winsound` is INSIDE `_maybe_beep` (line-local) AFTER the `if sys.platform != "win32": return` guard. AST test: confirm the import appears inside the function, not at module level. |
| `on_usage` parsing breaks when llama-server omits the key | llama-integration | `chunk.get("usage")` returns `None` silently; the `if usage is not None` skips it. Test `test_chat_stream_no_error_when_usage_absent` locks this. |
| 15 sub-features + strict TDD = large PR | delivery | `review_budget: 800` per preflight. AST checks for UI allow rapid iteration. If the apply phase finds the diff > 800 lines, the orchestrator will stop and ask for `size:exception`. |
| App-shell spec is at 644 words (close to 650 budget) | spec phase residual | This design does not add new requirements to app-shell. If the apply phase needs to, propose a trim in the same change. |
| F2 fallback strings not defined for missing model/usage | accessibility-guidelines | Resolved in §3.8. AST test: search for the literal fallback strings ("sin modelo cargado", "Tokens: sin información"). |

---

## 6. Senior architect commentary

This section is mine, not the sub-agent's. It records the WHY behind the design, the tradeoffs I accepted, and the things I want the apply phase to be careful about.

### 6.1 Why the dual view is the right refactor

A `wx.TextCtrl` is a continuous flow of text. NVDA can read it, but it cannot announce "the third message" — the user has to listen to everything up to it. A `wx.ListBox` is a navigable list: NVDA announces "Item 3 of 12, [Asistente] Bien, gracias" the moment focus lands on it. This is the single biggest UX win in v0.3.0 for blind users. The split into `message_list` (history) + `stream_display` (live) also matches the cognitive model: "things that happened" vs "thing that's happening right now." NVDA's virtual buffer handles each control type differently and correctly.

I considered using a single `wx.html.HtmlWindow` (cheaper refactor, no new controls). Rejected: AGENTS.md is explicit that HtmlWindow is not accessible with NVDA. I considered `wx.RichTextCtrl` for the stream display. Rejected: same accessibility issue. The `TE_RICH2` TextCtrl is the right primitive for read-only streaming text.

### 6.2 Why the temp-file-then-browser approach for HTML

Three options were on the table:
1. `webbrowser.open(f"file:///{temp_path}")` — what we picked
2. `wx.html.HtmlWindow` — rejected, not accessible
3. `wx.WebView` (wraps Edge WebView2) — rejected, focus management is brittle with NVDA; also pulls a heavy native dep

Option 1 is the simplest and the most accessible: NVDA in virtual mode in Edge/Chrome is the gold standard for reading HTML on Windows. The browser is what NVDA integrates with. The cost is the temp-file lifecycle, but it's bounded (one file per open, cleaned on close) and the leak is harmless (a few KB in the user's temp dir).

### 6.3 Threading — the rule of one, applied twice

The codebase already has one daemon thread pattern (`LlamaClient._stream_thread`). v0.3.0 adds a SECOND (`_model_load_thread`) and a third (`_loading_announce_timer`, technically a Timer but still its own thread of execution). The hard rule is: **only `wx.CallAfter` crosses the thread boundary**. Direct calls to `self.SetStatusText(...)`, `self.message_list.Append(...)`, `self.speech.speak(...)` from a worker are forbidden — they either crash (post-`Destroy()`) or get called from the wrong thread context.

The `_is_closing` flag is the safety net. Set it in `_on_close` FIRST, before any other action. Every background callback checks it before calling `wx.CallAfter`. The cost of the check is one branch; the cost of skipping it is a crash on close-during-load.

### 6.4 The MessageDialog exception is a one-line carve-out

AGENTS.md is firm: no `wx.MessageDialog` with custom Spanish labels (`SetYesNoCancelLabels`). The reasoning is solid — MSAA regresses and NVDA reads the generic label instead of the custom one. But there are existing `wx.MessageDialog` calls in the code (the install dialog, error dialogs, About, Shortcuts) that use stock labels and have worked fine. The close-confirm dialog is in the same category: stock `YES_NO` (English on most Windows installs), stock `NO_DEFAULT`, stock `ICON_QUESTION`. The only NEW dialog in v0.3.0 that needs custom labels (Open in browser, Copy, Close) is the `MessageDetailDialog`, and that one uses `wx.Dialog` + native `wx.Button`s — explicit per the spec and the AGENTS.md rule. So: the exception is real, the carve-out is narrow, and the AST test that bans `MessageDialog` from `message_detail_dialog.py` is the enforcement.

### 6.5 The system_prompt JSON change is a schema migration

`Conversation.load` used to return `Conversation`; it now returns `(Conversation, str)`. This is a breaking change for every caller. There is one caller (`main_window.load_conversation` at line 535). I want the apply phase to do the rename in ONE commit with the test that asserts the new tuple shape, so `git bisect` lands on a clean state.

The `system_prompt` field is at the TOP level of the JSON, not inside `messages`. This is intentional: a system prompt is a property of the conversation, not a message. If a future change adds per-message metadata (e.g. token counts, citations), it doesn't have to fight the system_prompt slot. The `to_dict()`/`from_dict()` pair on `Conversation` continues to handle only `messages`; the new `system_prompt` is added/removed at the `save`/`load` boundary. Backward compat: missing field defaults to `""` — the v0.2.0 files still load cleanly.

### 6.6 F2 status — the escape hatch

The status announcement is a small piece of code but a huge deal for the user. When a blind user gets disoriented (focus lost, unclear what's happening), F2 is the panic button. It tells them everything they need: what model, whether the server is up, how long the conversation is, how many tokens they've used, the current sampling parameters, and whether a generation is in progress. The fallback strings (resolved in §3.8) matter because every field can be in an unknown state — and a status announcement that says `None` or `0` is worse than a graceful "sin información".

Spanish decimal notation (`0,70` not `0.70`) is non-negotiable: NVDA reads "0.70" as "cero punto setenta" which is jarring. `0,70` reads as "cero coma setenta" which is what a Spanish-speaking user expects.

### 6.7 The implementation order I would pick

If I were writing this myself:
1. `text_utils.py` + 8 tests (TDD, isolated, fast)
2. `conversation.py` system_prompt + 3 tests
3. `llama_client.py` on_usage + 2 tests
4. `message_detail_dialog.py` + 6 AST tests
5. `params_panel.py` use_model_button + 2 AST tests (button present, name, label, enable/disable logic)
6. `chat_panel.py` refactor + 3 new AST tests
7. `main_window.py` coordination (accelerators, F2, close confirm, title, beep, background load) + 5 new AST tests
8. `pyproject.toml` add `markdown>=3.5`
9. Run full `uv run --no-sync pytest -xvs` — must pass at ≥132 tests
10. `CHANGELOG.md`, `README.md`, `AGENTS.md` updates

Each step is a work-unit commit (see the `work-unit-commits` skill). The core/ changes (1, 2, 3) are pure TDD with no wx. The UI changes (4–7) are AST-driven — write the test, watch it fail, build the widget/handler, watch it pass.

### 6.8 What I am explicitly NOT going to do

- No refactor of `ParamsPanel` beyond the `use_model_button` addition
- No change to `LlamaRunner` (the proposal says don't touch it; the polling release is the design's foundation)
- No new public methods on `Speech` (F2 and beep compose existing primitives)
- No new public methods on `LlamaClient` other than the optional `on_usage` param
- No change to the message format sent to llama-server (still OpenAI content-array, same as v0.2.0)
- No new dependency other than `markdown>=3.5`

### 6.9 What the apply phase should NOT do without checking back

- Any change to the close-veto semantics (currently: veto on No, abort+stop on Yes)
- Any change to `_on_token` ordering (chunk → speak → beep is the spec)
- Any change to the F2 string format (Spanish decimals, the exact field order)
- Any rename of `_on_start_server` (the button renamed; the handler stays)
- Any addition of a new public method on `Speech` (would be scope creep)

If any of these come up, STOP and surface the question to me. The proposal and specs are the contract; deviating from them without a stated reason is how review goes off the rails.
