# Proposal: v0.4.0-tool-calling-ui

## Why

v0.4.0 core (`PermissionManager` + `ToolExecutor` + `LlamaClient.on_tool_call`)
is shipped and verified at 159/159 tests. The model can ask to invoke a tool,
the core can decide risk and run PowerShell, but **no UI exists to confirm
the invocation with the user**. Without a UI layer:

- The blind user is never asked — the prompt is silent, the model just acts.
- PermissionManager.classify_risk / is_system_destructive have no entry point
  from the chat flow.
- Session grants (`grant_session`) are unused.
- The `tools` catalog is never sent to the model.

The user is blind (NVDA + Windows 11). Every tool execution must be (a)
announced by voice *before* it runs, (b) confirmed by an accessible dialog,
and (c) deniable from a single keypress. A `wx.MessageDialog` with custom
Yes/No labels has documented MSAA regressions — the buttons get associated
with the wrong names. This change wires up the dialog, the params_panel
toggle, and the full send→think→confirm→run→respond loop in `MainWindow`.

This change **completes v0.4.0** and is the trigger for the version bump.

## What changes

### A. New module `ollamachat/ui/permission_dialog.py`

`class PermissionDialog(wx.Dialog)` with three native `wx.Button`s
(`Permitir una vez`, `Permitir en esta sesion`, `Denegar`) returning
`wx.ID_YES`, `wx.ID_OK`, `wx.ID_CANCEL`. `wx.MessageDialog` is FORBIDDEN
here (see AGENTS.md). Foco inicial va al `command_text` (read-only
`wx.TextCtrl`) para que NVDA lea el comando antes de los botones.
Risk-level label (`GREEN` / `YELLOW` / `RED`) se muestra en texto plano
sin emojis (NVDA lee los emojis literalmente: "llave inglesa",
"señal de prohibición"). Beep de alerta en `win32` antes de mostrar.

### B. `ollamachat/ui/chat_panel.py` — 3 new methods

Al final de la clase:

- `append_tool_output(text: str)` — preview `[Herramienta] {preview}`
  en `message_list`, `_history` recibe `("tool", text)`.
- `append_tool_blocked(tool_name, command)` — preview `[Bloqueado] ...`.
- `append_tool_denied(tool_name)` — preview `[Denegado] {tool_name}`.

Sin emojis en los prefijos. Solo ASCII en los textos visibles para NVDA.

### C. `ollamachat/ui/params_panel.py` — checkbox

`wx.CheckBox` con `name="tools_checkbox"` y label "Permitir herramientas
(PowerShell)" debajo del bloque de parámetros, antes de
`AddStretchSpacer()`. Precedido por un `wx.StaticText` con label
"Herramientas:". Método `get_tools_enabled() -> bool` lee el estado.

### D. `ollamachat/ui/main_window.py` — wiring completo

1. Constante de módulo `SHELL_TOOL_DEFINITION` (OpenAI function schema
   para `shell_execute` con `command: string`).
2. `__init__` agrega `self._permission_manager = PermissionManager()` y
   `self._tool_executor = ToolExecutor()`.
3. `send_message()` calcula
   `tools = [SHELL_TOOL_DEFINITION] if self.params_panel.get_tools_enabled() else None`
   y la pasa a `chat_stream(..., on_tool_call=self._on_tool_call, tools=tools)`.
4. Nuevos métodos:
   - `_on_tool_call(tool_name, tool_call_id, args)` — gate central de
     seguridad: auto-block si `is_system_destructive`, grant si
     `has_session_grant`, sino `PermissionDialog`. Anuncia por voz
     antes de mostrar el diálogo.
   - `_run_tool_and_show(tool_name, tool_call_id, command)` — lanza
     `threading.Thread(daemon=True)` que llama a `_tool_executor.run`
     y vuelve a main thread con `wx.CallAfter(self._on_tool_result, ...)`.
   - `_on_tool_result(result, tool_call_id)` — actualiza `chat_panel`,
     anuncia por voz, agrega el tool message a la conversación, llama a
     `_continue_after_tool`.
   - `_continue_after_tool(tool_msg)` — reenvía la conversación al
     modelo con `tools` y `on_tool_call`, repitiendo el ciclo.

### E. Tests (AST + static, ui/ scope)

- `tests/ui/test_permission_dialog_static.py` (NEW, 8 tests): name= en
  command_text + 3 buttons, all controls named, only BoxSizer, zero
  `MessageDialog`, risk_labels ASCII-only.
- `tests/ui/test_chat_panel_static.py` (EXTEND, 4 tests): 3 métodos
  existen, prefijos `[Herramienta]` / `[Bloqueado]` / `[Denegado]`
  son ASCII puro.
- `tests/ui/test_main_window_static.py` (EXTEND, 7 tests):
  `_permission_manager` y `_tool_executor` en `__init__`, 4 métodos
  nuevos existen, `SHELL_TOOL_DEFINITION` está fuera de la clase.
- `tests/ui/test_params_panel_static.py` (EXTEND, 2 tests): checkbox
  presente con `name=`, método `get_tools_enabled` existe.

### F. Version & docs

- `pyproject.toml`: `0.3.0` → `0.4.0`.
- `CHANGELOG.md`: entrada `[0.4.0]` con resumen del feature.
- `AGENTS.md`: actualizar conteo de tests y nota sobre tool calling.

## Impact

### New capability fragments

- `tool-calling` (existing, MODIFIED) — 6 nuevos REQs para la capa UI:
  PermissionDialog, params_panel toggle, main_window flow, chat_panel
  methods, SHELL_TOOL_DEFINITION, threading/announce contract.

### Explicitly unaffected

- `core/permission_manager.py` y `core/tool_executor.py` — sin cambios.
  La API del core ya cubre todo lo que la UI necesita
  (grants, classify_risk, is_system_destructive, run, to_display_text,
  to_tool_message).
- `core/llama_client.py` — sin cambios. Ya acepta `on_tool_call` y
  `tools` desde v0.4.0-core.

## Approach

1. **UI-first, sin TDD estricto en `ui/`**: el AST-test va PRIMERO (RED)
   para fijar el contrato de `name=`, no-MessageDialog, ASCII puro, etc.
   Después se implementa para que pasen (GREEN). Esto sigue la
   convención de `ui/` del proyecto (manual verification en Windows +
   AST + smoke).
2. **Tocar archivos en orden top-down**: `params_panel.py` (1 método
   nuevo) → `chat_panel.py` (3 métodos) → `permission_dialog.py`
   (NEW) → `main_window.py` (4 métodos + import + SHELL_TOOL_DEFINITION).
   Esto minimiza el tiempo de "roto" entre commits.
3. **No tocar `core/`**. La core ya está. Esto mantiene el diff limpio
   y la review enfocada.
4. **Version bump al final**, después de verify.
5. **Work-unit commits** (siguiendo la convención de v0.3.0):
   - test(ui): add 8 permission_dialog AST tests (RED)
   - feat(ui): add PermissionDialog with native buttons
   - test(ui): add 4 chat_panel append_tool_* AST tests (RED)
   - feat(ui): add append_tool_output/blocked/denied
   - test(ui): add 2 params_panel tools_checkbox AST tests (RED)
   - feat(ui): add tools_checkbox + get_tools_enabled
   - test(ui): add 7 main_window tool-calling AST tests (RED)
   - feat(ui): add SHELL_TOOL_DEFINITION + _on_tool_call + _run_tool_and_show + _on_tool_result + _continue_after_tool
   - test: bump + run full suite
   - docs: CHANGELOG + AGENTS update for v0.4.0

## Non-goals

- **Refactor de `LlamaClient`**: ya soporta `on_tool_call` + `tools`. Sin cambios.
- **Nuevas tools además de `shell_execute`**: una sola tool, suficiente para v0.4.0.
- **Persistencia de session grants**: siguen in-memory (decisión de seguridad).
- **Bloqueo automático de user dirs**: el usuario es la autoridad de su
  `C:\Users\<name>\...`. Solo bloqueamos system paths (`C:\Windows`, etc.).
- **Cambios a otros capabilities** (`accessibility-guidelines`, `chat`,
  `app-shell`, `parameters`, `speech`, `llama-integration`): sin
  deltas. La integración con tool-calling es local.

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `PermissionDialog` con `wx.MessageDialog` por copy-paste | Med | Test `test_no_message_dialog` que falla si aparece el token en el archivo |
| `_on_tool_call` corre en hilo equivocado | Low | Viene por `wx.CallAfter` desde `LlamaClient._stream_worker` (ya patrón existente). Test de ubicación. |
| `_run_tool_and_show` blockea el main thread si el tool tarda | Low | `threading.Thread(daemon=True)` + `_tool_executor.run` con `timeout=30s` por defecto. UI queda responsiva. |
| Emojis en mensajes al usuario | Med | Test `test_no_emoji_in_risk_labels` y `test_no_emoji_in_tool_prefixes` (ASCII-only en strings visibles) |
| `_continue_after_tool` re-envía la conversación con `messages` mutated | Low | Re-construye `api_messages` desde cero cada vez (mismo patrón que `send_message`) |
| NVDA no lee el `command_text` antes de los botones | Med | Foco explícito en `command_text` (`self.command_text.SetFocus()`) ANTES de `Fit()`. Test que verifica el orden. |
| Race: dos `tool_calls` en el mismo `finish_reason` chunk | Low | `LlamaClient._tc_buffer` ya acumula por `index`; UI solo procesa uno a la vez (en cola de eventos wx) |
| `wx.SetEscapeId` no mapea a Deny | Low | Test verifica `SetEscapeId(wx.ID_CANCEL)` está presente |
| User cancela el diálogo → `_current_response` queda con basura | Low | En `wx.ID_CANCEL` se llama `append_tool_denied` y se vuelve al flujo idle. `send_message` ya limpia el input antes de empezar. |

## Acceptance criteria

- [ ] `ollamachat/ui/permission_dialog.py` existe, importable, 3 botones nativos.
- [ ] `ollamachat/ui/params_panel.py` tiene `tools_checkbox` y `get_tools_enabled()`.
- [ ] `ollamachat/ui/chat_panel.py` tiene `append_tool_output`,
      `append_tool_blocked`, `append_tool_denied`.
- [ ] `ollamachat/ui/main_window.py` tiene `_on_tool_call`,
      `_run_tool_and_show`, `_on_tool_result`, `_continue_after_tool`,
      y la constante `SHELL_TOOL_DEFINITION` a nivel de módulo.
- [ ] `send_message` pasa `on_tool_call=self._on_tool_call` y
      `tools=...` a `chat_stream`.
- [ ] `__init__` inicializa `_permission_manager` y `_tool_executor`.
- [ ] Cero uso de `wx.MessageDialog` en `permission_dialog.py`.
- [ ] Cero emojis en prefijos de tool (`[Herramienta]`, `[Bloqueado]`, `[Denegado]`)
      ni en `risk_labels` del diálogo.
- [ ] `tests/ui/test_permission_dialog_static.py` (NEW) — 8 tests pasan.
- [ ] `tests/ui/test_chat_panel_static.py` (EXTEND) — 4 tests nuevos pasan.
- [ ] `tests/ui/test_main_window_static.py` (EXTEND) — 7 tests nuevos pasan.
- [ ] `tests/ui/test_params_panel_static.py` (EXTEND) — 2 tests nuevos pasan.
- [ ] `pyproject.toml` version = `0.4.0`.
- [ ] `CHANGELOG.md` tiene entrada `[0.4.0]`.
- [ ] `uv run --no-sync pytest -xvs` corre verde: 159 (previos) + 8 + 4 + 7 + 2 = **180/180 tests** pasando.
- [ ] Cero cambios en `ollamachat/core/`.
- [ ] Working tree limpio al final (los residue changes del core commit
      previo deben haberse commiteado antes; o se commitean en un
      chore commit aparte antes de este change).

## Rollback plan

1. `git revert` del merge commit o de los work-unit commits en orden
   inverso (cada uno es independiente y revierte limpiamente porque
   solo tocan UI, no core ni otros capabilities).
2. `rm ollamachat/ui/permission_dialog.py` si queda suelto.
3. Revertir el bump de `pyproject.toml` (0.4.0 → 0.3.0).
4. Revertir `CHANGELOG.md`.
5. `uv run --no-sync pytest -xvs` debe seguir verde en el estado
   pre-v0.4.0-ui (159/159).
6. `openspec/changes/v0.4.0-tool-calling-ui/` se archiva a
   `openspec/changes/archive/<fecha>-v0.4.0-tool-calling-ui/` con
   `archive-report.md` documentando el rollback.

## Skill resolution

`paths-injected` — `sdd-apply`, `work-unit-commits`, `sdd-verify`,
`sdd-archive` cargadas desde `/home/ic_ma/.config/opencode/skills/`.
Engram no disponible (per `AGENTS.md`); artifact store es `openspec`.
