# Conocimiento: wxPython accesible con lectores de pantalla

Documento de referencia extraído de investigación práctica (junio 2026).
Aplicable a cualquier app de escritorio Python con wxPython que deba funcionar con NVDA, JAWS u otros lectores de pantalla en Windows.

---

## Reglas de oro (no negociables)

- Cada control interactivo lleva `name=` descriptivo. Sin `name=`, NVDA lee un label genérico.
- Cada control está precedido en el sizer por `wx.StaticText` con la etiqueta. MSAA asocia el StaticText adyacente al control que sigue en el tab order.
- Solo `wx.BoxSizer` horizontal o vertical. Los grid sizers (GridSizer, FlexGridSizer, GridBagSizer) rompen el orden de lectura de NVDA — el lector salta en orden DOM, no en orden visual de cuadrícula.
- Todos los callbacks desde hilos de fondo van por `wx.CallAfter`. Nunca llamar métodos wx desde un hilo que no sea el principal.
- `accessible-output2` se usa para anuncios proactivos (cosas que pasan sin que el usuario navegue a ellas). Los controles nativos los lee NVDA solo al recibir foco.

---

## Controles: qué funciona y qué no con NVDA

### Funciona bien (nativo Windows)

| Control | Notas |
|---|---|
| `wx.TextCtrl` (TE_MULTILINE, TE_READONLY, TE_RICH2) | NVDA lo lee con cursor virtual. TE_RICH2 para soporte de texto largo. |
| `wx.Button` | Lee el label del botón directamente. Nativo Win32. |
| `wx.ComboBox` | NVDA anuncia ítem seleccionado al navegar. Preferido sobre wx.Choice para listas editables. |
| `wx.ListBox` | Flechas arriba/abajo, NVDA anuncia cada ítem. Los propios devs de NVDA lo prefieren a wx.Choice (#6100 en nvaccess/nvda). |
| `wx.SpinCtrl` | NVDA lee valor actual. |
| `wx.Slider` | Funciona, pero NVDA no siempre anuncia el valor al cambiar. Complementar con `accessible-output2.speak(valor)` en el handler. |
| `wx.CheckBox` | Nativo, funciona. |
| `wx.RadioButton` | Nativo, funciona. |
| `wx.FileDialog` | Diálogo nativo del sistema, NVDA lo lee perfecto. |
| `wx.MessageDialog` (con botones estándar) | Cuando usa los IDs estándar (OK, YES, NO, CANCEL) es el MessageBox nativo Win32. Plenamente accesible. |
| `wx.Dialog` (custom) | Plenamente accesible si los controles internos son nativos y tienen `name=`. Es lo que usa NVDA internamente para sus propios diálogos. |

### NO funciona bien con NVDA

| Control | Razón |
|---|---|
| `wx.richtext.RichTextCtrl` | Implementación from-scratch, no nativa. Documentación de wxPython dice explícitamente: "poor choice if intended users rely on screen readers". |
| `wx.html.HtmlWindow` | Renderer HTML propio de wx, no un browser nativo. Sin evidencia de soporte MSAA/UIA confiable para navegación. |
| `wx.html2.WebView` | Embeds un browser real (WebView2/Edge). Tiene soporte NVDA vía UIA, pero NVDA lo trata como página web (modo virtual), no como app nativa. Comportamiento diferente al esperado en una app de escritorio. Evitar en apps para usuarios de lectores de pantalla salvo que sea imprescindible. |
| `wx.stc.StyledTextCtrl` | Basado en Scintilla. Problemas conocidos con NVDA braille. |
| `wx.grid.Grid` | Grid sizers y controles grid tienen el mismo problema de orden de lectura. |

---

## wx.MessageDialog: cuándo sí, cuándo no

**Sí**: alertas simples con botones estándar (OK, Yes/No, Yes/No/Cancel con labels en inglés).

```python
wx.MessageDialog(parent, message="Texto", caption="Título",
                 style=wx.YES_NO | wx.ICON_WARNING).ShowModal()
```

**No**: cuando necesitás botones con labels personalizados en español o con más de 3 opciones.
`SetYesNoCancelLabels()` existe pero tiene regresiones de MSAA documentadas en wxPython — en algunas versiones NVDA lee el label genérico en vez del texto personalizado.

**Solución correcta para diálogos complejos**: `wx.Dialog` custom con `wx.Button` nativos.
El propio NVDA deprecó `messageBox()` a favor de su clase `MessageDialog(wx.Dialog)` interna exactamente por esta razón (ver `nvaccess/nvda/source/gui/message.py`).

---

## Patrón: diálogo custom accesible con múltiples botones

```python
class ConfirmDialog(wx.Dialog):
    def __init__(self, parent, title, message, buttons):
        # buttons: list of (label, id) tuples
        super().__init__(parent, title=title)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        sizer.Add(wx.StaticText(self, label="Mensaje:"),
                  flag=wx.LEFT | wx.TOP, border=8)
        self.text = wx.TextCtrl(self, value=message,
                                style=wx.TE_MULTILINE | wx.TE_READONLY,
                                name="message_text")
        sizer.Add(self.text, flag=wx.EXPAND | wx.ALL, border=8)
        
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(wx.StaticText(self, label="Opciones:"),
                  flag=wx.LEFT, border=8)
        for label, btn_id in buttons:
            btn = wx.Button(self, id=btn_id, label=label, name=label)
            btn.Bind(wx.EVT_BUTTON, lambda e, i=btn_id: self.EndModal(i))
            btn_sizer.Add(btn, flag=wx.RIGHT, border=4)
        sizer.Add(btn_sizer, flag=wx.ALL, border=8)
        
        self.SetSizer(sizer)
        self.text.SetFocus()  # NVDA lee el mensaje al abrir
```

Puntos clave:
- `wx.TextCtrl(TE_READONLY)` para el mensaje → NVDA puede leer carácter a carácter si es largo
- `self.text.SetFocus()` en el constructor → NVDA anuncia el contenido al abrir el diálogo
- Cada `wx.Button` con `name=` → NVDA lee exactamente el label
- `wx.StaticText` antes del bloque de botones → orienta al usuario antes de llegar a los botones

---

## Patrón: operaciones largas en hilo de fondo con feedback a NVDA

Operaciones de más de ~2 segundos nunca deben bloquear el hilo principal. Con NVDA, el silencio prolongado es desorientante.

```python
import threading

def start_long_operation(self):
    self.speech.speak("Iniciando operación...", interrupt=True)
    self.button.Disable()
    
    def worker():
        for i in range(n_steps):
            if self._stop_event.is_set():
                break
            do_step(i)
            # Anuncio periódico cada ~5s
            if i % 5 == 0:
                wx.CallAfter(self.speech.speak,
                             f"Paso {i} de {n_steps}...", interrupt=False)
        wx.CallAfter(self._on_operation_done, result)
    
    t = threading.Thread(target=worker, daemon=True)
    t.start()
```

Nunca llamar métodos wx desde el hilo de trabajo. Todo por `wx.CallAfter`.

---

## Patrón: ListBox como historial de mensajes

`wx.ListBox` es el control más accesible para listas navegables con NVDA:
- Flechas arriba/abajo: NVDA anuncia el ítem
- Al recibir foco: NVDA anuncia el ítem seleccionado y opcionalmente la cantidad total
- Enter: acción sobre el ítem (abrir detalle, etc.)
- Tecla Aplicaciones: menú contextual

Para texto largo (mensajes de chat), el ítem del ListBox muestra solo un preview (primeros ~80 chars, sin newlines). El texto completo se guarda en una estructura paralela:

```python
self._history: list[tuple[str, str]] = []  # [(role, full_text), ...]
self.message_list = wx.ListBox(self, name="message_list")

def add_message_to_list(self, role: str, text: str):
    self._history.append((role, text))
    preview = text.replace('\n', ' ')[:80]
    label = "Tú" if role == "user" else "IA"
    self.message_list.Append(f"[{label}] {preview}...")
    self.message_list.SetSelection(self.message_list.GetCount() - 1)
```

Nunca actualizar el ListBox ítem por ítem durante streaming (NVDA anuncia cada cambio → ruido). El streaming va a un `wx.TextCtrl` separado. El ListBox se actualiza solo al completarse la respuesta.

---

## Patrón: "escribir para ir al input" desde el ListBox

Capturar caracteres en el ListBox y redirigir al campo de entrada:

```python
def _on_list_char(self, event: wx.KeyEvent):
    key = event.GetUnicodeKey()
    if (key > 31  # imprimible
            and not event.ControlDown()
            and not event.AltDown()
            and not event.MetaDown()):
        self.message_input.SetFocus()
        self.message_input.AppendText(chr(key))
        self.message_input.SetInsertionPointEnd()
    else:
        event.Skip()
```

---

## Patrón: atajos de teclado para acceso directo

`Alt+número` es la convención más segura — no choca con mnemonics de menú (que usan letras) ni con shortcuts de sistema.

```python
accel_entries = [
    wx.AcceleratorEntry(wx.ACCEL_ALT, ord('1'), ID_FOCUS_INPUT),
    wx.AcceleratorEntry(wx.ACCEL_ALT, ord('2'), ID_FOCUS_LIST),
    wx.AcceleratorEntry(wx.ACCEL_ALT, ord('3'), ID_FOCUS_MODEL),
    wx.AcceleratorEntry(wx.ACCEL_NORMAL, wx.WXK_F2, ID_SESSION_STATUS),
    wx.AcceleratorEntry(wx.ACCEL_NORMAL, wx.WXK_F6, ID_CYCLE_PANES),
]
```

F2 como "tecla de estado" es una convención tomada de apps como NVDA y JAWS (F1=ayuda, F2=info actual). F6 para ciclar paneles es convención de Windows (Word, Outlook, Explorer).

---

## Markdown y lectores de pantalla

El usuario de lector de pantalla no se beneficia del renderizado visual de markdown. Lo que importa es que el texto sea limpio y navegable.

### Opciones (de mejor a peor para NVDA):

1. **Texto plano en `wx.TextCtrl`** — funciona perfecto. El markdown raw (`**texto**`, `# Título`) se lee como texto plano, no ideal pero perfectamente usable.

2. **Texto limpio (strip markdown) en `wx.TextCtrl`** — óptimo. Strip con regex o librería `strip-markdown`. Sin símbolos, NVDA lee el contenido directamente.

3. **HTML en browser externo** (`webbrowser.open(temp_file.html)`) — óptimo para estructuras complejas (tablas, código con sintaxis). NVDA en modo virtual en browsers es su modo más potente: navega headings con H, listas con L, tablas con T. Implementación simple:
   ```python
   import tempfile, webbrowser
   from markdown import markdown
   html = f"<html><meta charset='utf-8'><body>{markdown(text)}</body></html>"
   with tempfile.NamedTemporaryFile(suffix='.html', delete=False,
                                    mode='w', encoding='utf-8') as f:
       f.write(html)
       webbrowser.open(f'file:///{f.name}')
   ```
   Limpiar temp files en `_on_close` (ignorar errores si el browser los tiene abiertos).

4. **`wx.html.HtmlWindow`** — NO. Sin soporte NVDA confiable, no es un browser nativo.

5. **`wx.richtext.RichTextCtrl`** — NO. Explícitamente bad for screen readers según docs oficiales.

---

## accessible-output2: cuándo usarlo

`accessible-output2` habla directamente por el lector de pantalla activo (NVDA, JAWS, SAPI, etc.) **sin que el usuario navegue a ningún control**. Es para anuncios proactivos.

Casos de uso correctos:
- "Generando respuesta..." cuando empieza el stream
- "Respuesta completa" cuando termina
- "Servidor listo" cuando llama-server arranca
- Valor del slider al moverlo (NVDA no siempre lo anuncia solo)
- Beep/tono durante streaming (`winsound.Beep(520, 50)` en Windows)

No usarlo para el contenido de los mensajes — eso lo lee NVDA solo cuando el usuario navega al control.

Patrón never-crash (obligatorio):
```python
class Speech:
    def __init__(self):
        try:
            from accessible_output2.outputs.auto import Auto
            self._output = Auto()
        except Exception:
            self._output = None
    
    def speak(self, text: str, interrupt: bool = False) -> None:
        try:
            if self._output:
                self._output.speak(text, interrupt=interrupt)
        except Exception:
            pass  # nunca crashear la app por speech
```

---

## Patrón: tono de progreso durante streaming

Tomado de NVDA-AI-assistant. Un beep breve periódico mientras el modelo genera, para que el usuario sepa que algo está pasando sin que NVDA intente leer cada token:

```python
import sys
import threading
import time

_last_beep = 0.0
_beep_lock = threading.Lock()

def maybe_beep():
    """Llamar desde on_token. Beep como máximo cada 1s."""
    if sys.platform != 'win32':
        return
    global _last_beep
    now = time.monotonic()
    with _beep_lock:
        if now - _last_beep < 1.0:
            return
        _last_beep = now
    try:
        import winsound
        winsound.Beep(520, 50)  # 520Hz, 50ms
    except Exception:
        pass
```

---

## Tool calling con llama-server

llama-server soporta tool calling con `--jinja` (obligatorio). La respuesta SSE puede contener `choices[0].delta.tool_calls` en vez de `choices[0].delta.content`.

Estructura del JSON cuando hay tool call:
```json
{
  "choices": [{
    "delta": {
      "tool_calls": [{
        "id": "call_abc",
        "function": {
          "name": "shell_execute",
          "arguments": "{\"command\": \"Get-Process\"}"
        }
      }]
    }
  }]
}
```

El parser SSE debe detectar `tool_calls` y llamar `on_tool_call(name, arguments_dict)` vía `wx.CallAfter`.

### Sistema de permisos para tool calling

Inspirado en Claude Code (uno/sesión/denegar) + QwenPaw (bloqueo de paths del sistema):

```python
class PermissionManager:
    def __init__(self):
        self._session_grants: set[str] = set()  # tool names con permiso de sesión
    
    def check(self, tool_name: str, command: str) -> str:
        """Retorna 'granted', 'session', o 'denied'."""
        if self._is_system_destructive(command):
            return 'denied'  # bloqueo automático sin diálogo
        if tool_name in self._session_grants:
            return 'session'  # ya tiene permiso de sesión
        return 'ask'  # mostrar diálogo
    
    def grant_session(self, tool_name: str):
        self._session_grants.add(tool_name)
    
    def _is_system_destructive(self, command: str) -> bool:
        """Bloquea solo paths sistémicos, no operaciones de usuario."""
        dangerous = [
            r'C:\\Windows', r'C:\\System32', r'C:\\Program Files',
            'Format-Volume', 'Clear-Disk', 'Remove-Item.*C:\\\\Windows',
        ]
        import re
        cmd_lower = command.lower()
        for pattern in dangerous:
            if re.search(pattern.lower(), cmd_lower):
                return True
        return False
```

Clasificación de riesgo para el diálogo (no bloquear, solo informar):
- Verde: comandos que solo leen o crean (`Get-*`, `ls`, `mkdir`, `New-Item`, `Copy-Item`)
- Amarillo: comandos que modifican (`Move-Item`, `Rename-Item`, `Set-Content`)
- Rojo: comandos que borran (`Remove-Item`, `del`, `rmdir`, `rd /s`)

---

## Patrones de threading en wxPython

Resumen de la regla de oro:

```
hilo principal (wx) ←── wx.CallAfter(callback, args) ←── hilo de fondo
```

Nunca al revés. Nunca llamar métodos de widgets desde hilos de fondo.

Para abort limpio de streams:
```python
self._stop_event = threading.Event()
# En el worker: if self._stop_event.is_set(): break
# Para abortar: self._stop_event.set(); self._thread.join(timeout=1.0)
```

`join(timeout=1.0)` evita esperar indefinidamente si el hilo está bloqueado en I/O.

---

## Notas de plataforma

- `winsound` es Windows-only. Guard: `if sys.platform == 'win32': import winsound`
- `subprocess.Popen` en Windows con `creationflags=0x08000000` (CREATE_NO_WINDOW) evita que aparezca una consola al lanzar procesos hijos.
- `os.path.expanduser("~")` en Windows da `C:\Users\usuario`, correcto para encontrar modelos.
- `shutil.which("llama-server")` encuentra el ejecutable en PATH incluyendo la instalación de winget.
- PyInstaller no puede compilar .exe de Windows desde WSL — hay que correr en Windows directamente.
- wxPython no tiene wheel de Linux precompilado — en WSL solo corren tests que no importan wx (core/ + AST checks de ui/).

---

## Patrones de NVDA observados en sus propias fuentes

De `nvaccess/nvda/source/gui/message.py`:
- NVDA deprecó `wx.MessageDialog` a favor de `MessageDialog(wx.Dialog)` custom
- Usan `wx.BoxSizer` exclusivamente para sus propios diálogos
- Todos sus botones tienen labels explícitos y son `wx.Button` nativos
- Al abrir un diálogo, llaman `SetFocus()` en el primer control relevante para orientar al usuario inmediatamente
- Usan `winsound.MessageBeep()` para el sonido de alerta — no confiar en el sistema para elegir el sonido correcto

De `nvaccess/nvda` en general:
- NVDA mismo está construido con wxPython — es la evidencia más fuerte de que wx + NVDA funciona bien cuando se hace correctamente
- Usan `wx.ListBox` para sus propias listas de opciones (PR #12215: migración de controles a wx.ListBox para mejor accesibilidad)
- Evitan `wx.CheckListBox` y `wx.ListCtrl` — tienen problemas de accesibilidad conocidos

---

## Dependencias recomendadas para apps accesibles

```toml
[project.dependencies]
wxPython = ">=4.2.0"
accessible-output2 = ">=0.17"
requests = ">=2.31"       # para APIs HTTP
markdown = ">=3.5"        # para convertir md→html (abrir en browser)
# strip-markdown no es necesario si hacés regex simple (ver sección markdown)
```

Strip de markdown sin dependencias extra (cubre el 90% de los casos):
```python
import re

def strip_markdown(text: str) -> str:
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)  # headers
    text = re.sub(r'\*{1,3}([^*\n]+)\*{1,3}', r'\1', text)     # bold/italic
    text = re.sub(r'`{3}[^`]*?`{3}', lambda m:
                  m.group().replace('```', ''), text, flags=re.DOTALL)  # code blocks
    text = re.sub(r'`([^`\n]+)`', r'\1', text)                  # inline code
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)       # links
    text = re.sub(r'^[-*+]\s+', '• ', text, flags=re.MULTILINE) # list items
    return text.strip()
```

---

*Documento generado el 2026-06-22. Fuentes principales: wxPython docs, nvaccess/nvda source, adil-adysh/NVDA-AI-assistant, agentscope-ai/QwenPaw.*
