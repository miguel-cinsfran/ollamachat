# Design: v0.4.0-tool-calling-ui

## Architecture overview

This change wires the headless v0.4.0-core (`PermissionManager` +
`ToolExecutor` + `LlamaClient.on_tool_call`) into the wx UI of
`MainWindow`. The split is intentional and unchanged from
v0.4.0-core:

```
core/   (wx-free, TDD-strict)        ui/   (wx-dependent, AST-tested)
─────────────────────────────         ──────────────────────────────
PermissionManager.classify_risk  ──▶  PermissionDialog (risk_label)
PermissionManager.is_system_destr──▶  _on_tool_call gate
PermissionManager.session_grants ──▶  _on_tool_call gate
ToolExecutor.run                 ──▶  _run_tool_and_show (daemon thread)
ToolResult.to_display_text       ──▶  chat_panel.append_tool_output
ToolResult.to_tool_message       ──▶  _on_tool_result → add_message
LlamaClient.on_tool_call callback──▶  MainWindow._on_tool_call (main thread)
LlamaClient.tools catalog        ──▶  SHELL_TOOL_DEFINITION + params toggle
```

The UI layer adds **zero new core behavior**. It only:
1. Surfaces existing core capabilities to the user.
2. Owns the user-confirmation flow.
3. Re-feeds the model with the tool result.

## File-by-file changes

### 1. `ollamachat/ui/permission_dialog.py` (NEW, ~85 lines)

```python
import sys
import wx
from ollamachat.core.permission_manager import RiskLevel


class PermissionDialog(wx.Dialog):
    def __init__(self, parent, tool_name, command, risk_level):
        super().__init__(parent, title="Confirmar ejecución",
                         name="permission_dialog")
        self._build_ui(tool_name, command, risk_level)

    def _build_ui(self, tool_name, command, risk_level):
        if sys.platform == "win32":
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except Exception:
                pass

        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.Add(
            wx.StaticText(self, label="El modelo quiere ejecutar:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.command_text = wx.TextCtrl(
            self, value=command,
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            size=(-1, 80), name="command_text",
        )
        sizer.Add(self.command_text,
                  flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)

        risk_labels = {
            "GREEN":  "Operacion de lectura o creacion",
            "YELLOW": "Advertencia: operacion de modificacion",
            "RED":    "Advertencia: operacion irreversible (los archivos NO van a la Papelera)",
        }
        risk_text = risk_labels.get(risk_level.name, "")
        if risk_text:
            sizer.Add(
                wx.StaticText(self, label=risk_text, name="risk_label"),
                flag=wx.LEFT | wx.TOP | wx.BOTTOM, border=8,
            )

        sizer.Add(
            wx.StaticText(self, label="Opciones:"),
            flag=wx.LEFT, border=8,
        )
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.allow_once_button = wx.Button(
            self, id=wx.ID_YES, label="Permitir una vez",
            name="allow_once_button",
        )
        self.allow_once_button.Bind(
            wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_YES)
        )
        btn_sizer.Add(self.allow_once_button, flag=wx.RIGHT, border=4)

        self.allow_session_button = wx.Button(
            self, label="Permitir en esta sesion",
            name="allow_session_button",
        )
        self.allow_session_button.Bind(
            wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_OK)
        )
        btn_sizer.Add(self.allow_session_button, flag=wx.RIGHT, border=4)

        self.deny_button = wx.Button(
            self, id=wx.ID_CANCEL, label="Denegar",
            name="deny_button",
        )
        self.deny_button.Bind(
            wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CANCEL)
        )
        btn_sizer.Add(self.deny_button)

        sizer.Add(btn_sizer, flag=wx.ALL, border=8)
        self.SetSizer(sizer)
        self.Fit()
        self.SetEscapeId(wx.ID_CANCEL)
        self.command_text.SetFocus()
```

**Decisions**:
- `wx.Dialog` + `wx.Button` nativos (NO `wx.MessageDialog`) por
  regresión documentada de MSAA con labels en español.
- Foco en `command_text` (no en el primer botón) para que NVDA lea
  el comando antes de cualquier botón.
- `SetEscapeId(wx.ID_CANCEL)` mapea Escape a "Denegar" (default
  seguro).
- `winsound.MessageBeep` envuelto en `try/except` y guardado por
  `sys.platform == "win32"` (import INSIDE the guard, no top-level).

### 2. `ollamachat/ui/params_panel.py` (extend `_build_ui`, ~10 lines)

Agregar antes de `sizer.AddStretchSpacer()`:

```python
sizer.Add(
    wx.StaticText(self, label="Herramientas:"),
    flag=wx.LEFT | wx.TOP, border=8,
)
self.tools_checkbox = wx.CheckBox(
    self, label="Permitir herramientas (PowerShell)",
    name="tools_checkbox",
)
sizer.Add(self.tools_checkbox,
          flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)
```

Y agregar el método:

```python
def get_tools_enabled(self) -> bool:
    return self.tools_checkbox.GetValue()
```

**Decisiones**:
- Checkbox en la parte inferior del panel, no arriba, porque la
  mayoría de los usuarios no usan tools. Mantiene el flujo
  principal (modelo → parámetros → temperature) en la zona top.
- `StaticText` previo por la regla MSAA de etiqueta adyacente.
- Default: **unchecked** (más seguro, el usuario tiene que
  activarlo explícitamente).

### 3. `ollamachat/ui/chat_panel.py` (3 métodos al final, ~25 lines)

```python
def append_tool_output(self, text: str) -> None:
    """Muestra el resultado de una herramienta en el historial."""
    self._history.append(("tool", text))
    preview = f"[Herramienta] {self._preview(text)}"
    self.message_list.Append(preview)
    self.message_list.SetSelection(self.message_list.GetCount() - 1)

def append_tool_blocked(self, tool_name: str, command: str) -> None:
    """Muestra que un comando fue bloqueado por seguridad."""
    text = f"[Bloqueado] {tool_name}: {command}"
    self._history.append(("system", text))
    self.message_list.Append(f"[Bloqueado] {self._preview(text)}")
    self.message_list.SetSelection(self.message_list.GetCount() - 1)

def append_tool_denied(self, tool_name: str) -> None:
    """Muestra que el usuario denegó la ejecución."""
    text = f"[Denegado] {tool_name}"
    self._history.append(("system", text))
    self.message_list.Append(text)
    self.message_list.SetSelection(self.message_list.GetCount() - 1)
```

**Decisiones**:
- Roles en `_history`: `"tool"` para output real, `"system"` para
  blocked/denied. Esto permite que la conversación que se persiste
  distinga un resultado de un mensaje de sistema.
- **NO emojis** en los prefijos (NVDA los lee literalmente).
  `"[Herramienta]"`, `"[Bloqueado]"`, `"[Denegado]"` son ASCII puro.
- `_preview` reusado del helper existente (trunca a 80 chars).

### 4. `ollamachat/ui/main_window.py` (extend, ~110 lines net)

**Module-level constant** (FUERA de la clase):

```python
SHELL_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "shell_execute",
        "description": (
            "Ejecuta un comando en PowerShell en el sistema Windows del "
            "usuario. Usa esto para operaciones de archivos, sistema, o "
            "cuando el usuario lo pide explicitamente."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "El comando de PowerShell a ejecutar.",
                }
            },
            "required": ["command"],
        },
    },
}
```

**Imports** (en el bloque de imports del módulo, no dentro de clase):

```python
from ollamachat.core.permission_manager import PermissionManager
from ollamachat.core.tool_executor import ToolExecutor, ToolResult
from ollamachat.ui.permission_dialog import PermissionDialog
```

(`threading` ya está importado desde v0.3.0, no duplicar.)

**`__init__` additions** (después de `self._last_usage`):

```python
self._permission_manager = PermissionManager()
self._tool_executor = ToolExecutor()
```

**`send_message` patch** — antes del `chat_stream` call, agregar:

```python
tools = [SHELL_TOOL_DEFINITION] if self.params_panel.get_tools_enabled() else None
```

Y modificar el `chat_stream(...)` call para pasar:

```python
self._client.chat_stream(
    messages=api_messages,
    options=options,
    on_token=self._on_token,
    on_done=self._on_done,
    on_error=self._on_error,
    on_usage=self._on_usage,
    on_tool_call=self._on_tool_call,
    tools=tools,
)
```

**4 nuevos métodos** (después de `_on_done`):

```python
def _on_tool_call(self, tool_name: str, tool_call_id: str, args: dict) -> None:
    """Callback cuando el modelo solicita ejecutar una herramienta."""
    command = args.get("command", str(args))

    if self._permission_manager.is_system_destructive(command):
        self._speech.speak(
            f"Comando bloqueado por seguridad: {command[:80]}", interrupt=True
        )
        self.chat_panel.append_tool_blocked(tool_name, command)
        return

    if self._permission_manager.has_session_grant(tool_name):
        self._speech.speak(
            f"Ejecutando {tool_name}: {command[:50]}", interrupt=True
        )
        self._run_tool_and_show(tool_name, tool_call_id, command)
        return

    self._speech.speak(
        "El modelo quiere ejecutar un comando. Escucha el comando y confirma.",
        interrupt=True,
    )
    risk = self._permission_manager.classify_risk(command)
    dlg = PermissionDialog(self, tool_name, command, risk)
    result = dlg.ShowModal()
    dlg.Destroy()

    if result == wx.ID_YES:
        self._run_tool_and_show(tool_name, tool_call_id, command)
    elif result == wx.ID_OK:
        self._permission_manager.grant_session(tool_name)
        self._run_tool_and_show(tool_name, tool_call_id, command)
    else:
        self._speech.speak("Ejecucion denegada.", interrupt=True)
        self.chat_panel.append_tool_denied(tool_name)

def _run_tool_and_show(
    self, tool_name: str, tool_call_id: str, command: str
) -> None:
    """Ejecuta la tool en hilo de fondo para no bloquear la UI."""
    def worker() -> None:
        result = self._tool_executor.run(tool_name, command)
        wx.CallAfter(self._on_tool_result, result, tool_call_id)
    threading.Thread(target=worker, daemon=True).start()

def _on_tool_result(self, result, tool_call_id: str) -> None:
    """Callback en hilo principal con el resultado de la herramienta."""
    self.chat_panel.append_tool_output(result.to_display_text())
    self._speech.speak(
        f"Comando completado, codigo {result.returncode}. Consultando al modelo.",
        interrupt=True,
    )
    tool_msg = result.to_tool_message()
    tool_msg["tool_call_id"] = tool_call_id
    self._conversation.add_message("tool", tool_msg["content"])
    self._continue_after_tool(tool_msg)

def _continue_after_tool(self, tool_msg: dict) -> None:
    """Reenvía la conversación al modelo con el resultado de la tool."""
    api_messages = []
    system_prompt = self.params_panel.get_system_prompt()
    if system_prompt.strip():
        api_messages.append({"role": "system", "content": system_prompt})
    api_messages.extend(self._conversation.get_messages_for_api())

    tools = (
        [SHELL_TOOL_DEFINITION]
        if self.params_panel.get_tools_enabled()
        else None
    )

    self._current_response = ""
    self.chat_panel.start_generation()
    self._is_generating = True
    self.chat_panel.append_assistant_prefix()
    self.status_bar.SetStatusText("Consultando al modelo...", 2)

    self._client.chat_stream(
        messages=api_messages,
        options=self.params_panel.get_params(),
        on_token=self._on_token,
        on_done=self._on_done,
        on_error=self._on_error,
        on_usage=self._on_usage,
        on_tool_call=self._on_tool_call,
        tools=tools,
    )
```

## Sequence: model asks → user confirms → tool runs → model answers

```
User sends msg
    │
    ▼
send_message() ─── builds api_messages ───▶ chat_stream(tools=...)
                                              │
              (model emits tool_call)        ▼
                                              │
              ┌───────────────────────────────┘
              ▼
LlamaClient._stream_worker ── wx.CallAfter ──▶ MainWindow._on_tool_call
                                                       │
                                       ┌───────────────┼───────────────┐
                                       ▼               ▼               ▼
                              is_system_destructive has_session_grant  else
                                       │               │               │
                                       ▼               ▼               ▼
                                  block+speak    speak+_run_tool  speak+PermissionDialog
                                       │               │               │
                                       ▼               ▼       ┌───────┴───────┐
                                append_blocked   worker()    ▼               ▼
                                                (daemon)   ID_YES       ID_OK    ID_CANCEL
                                                       │       │       │           │
                                                       ▼       ▼       ▼           ▼
                                                    run    _run_tool grant+run append_denied
                                                                │       │
                                                                ▼       ▼
                                                  wx.CallAfter(_on_tool_result, result)
                                                                │
                                                                ▼
                                                  append_tool_output + speak
                                                                │
                                                                ▼
                                                  _continue_after_tool(tool_msg)
                                                                │
                                                                ▼
                                                  chat_stream(tools=...)  ◀─── cycle repeats
```

## Accessibility decisions (recap)

| Decision | Why |
|---|---|
| Foco inicial en `command_text`, no en el primer botón | NVDA lee el comando antes de los botones |
| `SetEscapeId(wx.ID_CANCEL)` | Escape = "Denegar" (default seguro) |
| `winsound.MessageBeep` antes del diálogo | Audio cue para el usuario ciego |
| Speak `_on_tool_call` announcement **antes** del `ShowModal` | NVDA anuncia la acción, después muestra el diálogo |
| Speak "Comando completado, codigo N. Consultando al modelo." después de cada tool | El usuario sabe que el ciclo continúa |
| No emojis en `[Herramienta]`, `[Bloqueado]`, `[Denegado]`, ni en `risk_labels` | NVDA lee los emojis literalmente y genera ruido |
| `wx.Dialog` + `wx.Button` nativos, NO `wx.MessageDialog` con labels custom | Regresión documentada de MSAA con `SetYesNoCancelLabels` |
| Toggle default = `False` (unchecked) en `tools_checkbox` | Más seguro: el usuario activa explícitamente |
| `interrupt=True` en TODOS los `speak()` de tool flow | Corta cualquier anuncio en curso para dar el feedback correcto |

## Threading contract

| Hilo | Qué hace | Regla |
|---|---|---|
| Main (UI) | `wx.*` calls, `_on_tool_call`, `_on_tool_result`, `_continue_after_tool`, `append_*` | Único hilo que toca widgets |
| Background (`_run_tool_and_show` worker) | `self._tool_executor.run(tool_name, command)` | NO toca widgets. Devuelve por `wx.CallAfter` |
| Streaming daemon (existente, v0.4.0-core) | `LlamaClient._stream_worker` | Ya usa `wx.CallAfter` para tokens, done, error, usage, tool_call |

`threading.Thread(daemon=True)` para el worker de tool → la app
puede salir limpiamente aunque haya un tool en curso. Mismo patrón
que `_model_load_worker` de v0.3.0.

## Test strategy

| Capa | Tests |
|---|---|
| AST (UI) | 8 nuevos en `test_permission_dialog_static.py` + 4 en `test_chat_panel_static.py` + 7 en `test_main_window_static.py` + 2 en `test_params_panel_static.py` = **21 nuevos** |
| Core (no cambia) | Los 19 tests de v0.4.0-core siguen pasando |
| Total esperado | 159 (previo) + 21 (nuevos) = **180/180** |

AST tests verifican:
- `name=` en todos los widgets interactivos.
- Solo `BoxSizer` (no Grid/Flex/GridBag).
- Cero `MessageDialog` en `permission_dialog.py`.
- ASCII puro en strings visibles.
- Métodos existen con la firma esperada.
- `SHELL_TOOL_DEFINITION` está a nivel de módulo.
- `command_text.SetFocus()` está DESPUÉS de `Fit()`.

## Backward compatibility

- `chat_stream` defaults intactos: sin `on_tool_call` ni `tools`
  se comporta idéntico a v0.3.0 (contract de v0.4.0-core).
- `PermissionManager` y `ToolExecutor` sin cambios.
- `LlamaClient` sin cambios.
- Los 159 tests previos siguen pasando sin modificación.

## Out of scope (deferred)

- Múltiples tools en el catálogo (solo `shell_execute`).
- Editor visual de permisos (panel de configuración).
- Persistencia de grants entre sesiones (in-memory por seguridad).
- Refactor de `send_message` para que el tool flow no duplique código
  con `_continue_after_tool`. Considerado para v0.5.0.
- `[windows-only]` verification tasks para F6 cycling con el dialog
  abierto. Para v0.4.1 si surge un issue.

## Risk mitigation recap

See proposal.md for the full risk table. The 4 highest:

1. **`wx.MessageDialog` slip-in**: `test_no_message_dialog` AST check.
2. **Emojis en strings visibles**: 2 AST checks (tool prefixes + risk labels).
3. **Tool runs on main thread**: source inspection verifica `daemon=True` y `wx.CallAfter`.
4. **NVDA focus wrong**: AST check verifica `SetFocus()` después de `Fit()`.
