# OllamaChat

Cliente de escritorio accesible para chatear con modelos locales .gguf via llama-server (llama.cpp).
Diseñado para usuarios ciegos en Windows 11 con NVDA o JAWS.

Stack: Python 3.12, wxPython 4.2+, accessible-output2 0.17+, requests 2.31+.
Tests: pytest (102/102 pasan en el ultimo verify).

## Reglas criticas (no negociables)

- Cada control interactivo tiene `name=` descriptivo
- Cada control esta precedido en el sizer por `wx.StaticText` (MSAA asocia la etiqueta adyacente)
- Solo `wx.BoxSizer` horizontal o vertical. **Nunca** grid sizers (rompen el orden de lectura de NVDA)
- Fallos de accessible-output2 nunca crashean la app (try/except en cada metodo publico de `Speech`)
- Todos los callbacks desde hilos de fondo van por `wx.CallAfter` sin excepcion
- Sin `wx.WebView` (inaccesible para lectores de pantalla). Usar `wx.TextCtrl` con `wx.TE_RICH2`
- Para detectar Shift/Ctrl/etc. en handlers usar `event.ShiftDown()`, nunca `wx.GetKeyState`
- Encoding `utf-8` explicito en toda lectura/escritura de archivos
- Compatible con Python 3.12, sin sintaxis de versiones posteriores

## Reglas adicionales de controles (investigadas en fuentes de NVDA)

- **No usar `wx.MessageDialog` para botones con labels personalizados en español.**
  `SetYesNoCancelLabels()` tiene regresiones de MSAA documentadas — NVDA puede leer el label
  generico en vez del texto personalizado. Para dialogos con 2+ botones custom: usar
  `wx.Dialog` custom con `wx.Button` nativos (exactamente como hace NVDA internamente).
- **No usar `wx.richtext.RichTextCtrl`** para mostrar contenido al usuario. La propia
  documentacion de wxPython dice que es "poor choice for screen readers" por ser una
  implementacion from-scratch no nativa.
- **No usar `wx.html.HtmlWindow`** para contenido que el usuario necesite leer con NVDA.
  No es un browser nativo y no tiene soporte MSAA/UIA confiable.
- **Para HTML renderizado**, usar `webbrowser.open()` con un archivo temporal `.html`.
  El browser (Edge, Chrome) con NVDA en modo virtual es el entorno mas accesible posible.
- **Operaciones de mas de 2 segundos** (arrancar el servidor, ejecutar comandos) deben
  correr en un hilo de fondo con anuncios periodicos via `wx.CallAfter(speech.speak, ...)`.
  Nunca bloquear el hilo principal en silencio.
- **`wx.ListBox`** es el control mas accesible para listas navegables con NVDA.
  Preferir sobre `wx.Choice`, `wx.ListCtrl` o `wx.CheckListBox`.
- **Vista dual**: el historial en `wx.ListBox` con previews de 80 caracteres y el streaming
  en `wx.TextCtrl` son dos controles separados. NVDA navega cada uno correctamente. No
  combinar en un solo control.
- **Cuando el foco entra a un dialogo**, llamar `SetFocus()` en el primer control relevante
  (normalmente el TextCtrl con el contenido) para que NVDA lo anuncie inmediatamente.
- **`winsound` y otros modulos Windows-only** requieren guard: `if sys.platform == 'win32'`.
  El mismo patron ya usado en `llama_runner.py` con `CREATE_NO_WINDOW`.
- **Alt+numero** es la convencion de atajos directos a controles (Alt+1 input, Alt+2 lista,
  Alt+3 modelo, etc.). F2 esta reservado para el anuncio de estado de sesion. F6 para ciclar paneles.

## Layout del proyecto

```
ollamachat/
  main.py             # entry point
  core/               # wx-free, totalmente testeable
    speech.py         # wrapper accessible-output2 (never-crash)
    conversation.py   # persistencia JSON con atomic write + system_prompt
    llama_client.py   # REST SSE streaming + abort + on_tool_call + on_usage
    llama_runner.py   # spawn llama-server + poll
    text_utils.py     # strip_markdown() sin dependencias externas [v0.3.0]
    permission_manager.py  # permisos de tools por sesion, clasificacion de riesgo [v0.4.0]
    tool_executor.py  # ejecuta comandos PowerShell, captura stdout/stderr [v0.4.0]
    logger.py         # logger a data/ollamachat.log
  ui/                 # wx, solo testeable en Windows
    main_window.py    # SplitterWindow + menu + status bar + send flow + tool flow
    chat_panel.py     # ListBox historial + TextCtrl streaming + _history list
    params_panel.py   # model selector + sliders + use_model_button
    message_detail_dialog.py  # popup detalle mensaje [v0.3.0]
    permission_dialog.py      # dialogo confirmacion tool calling [v0.4.0]
  data/               # runtime (gitignored, se crea solo)
tests/
  core/               # TDD estricto, importan el codigo
  ui/                 # AST checks + placeholders [windows-only]
  smoke/              # degradacion silenciosa
openspec/             # artefactos SDD (ver seccion abajo)
```

## Tests

- Windows: `uv sync` primero, despues `uv run pytest -xvs`. 102/102 pasan.
- WSL / Linux sin wxPython: wxPython no tiene wheel de Linux por defecto, falla al compilar desde source. Usar `uv run --no-sync pytest -xvs`. Los tests de `core/` y smoke + tests AST de UI pasan igual (los AST leen el codigo fuente, no importan wx).

## Como iterar una nueva version

1. Modificar el codigo
2. Bumpear la version en `pyproject.toml` (formato semver: 0.2.x para fixes, 0.x.0 para features)
3. Correr `uv run --no-sync pytest -xvs` en WSL para verificar core + AST
4. Copiar el directorio a Windows, correr `uv sync` y luego `uv run python -m ollamachat.main` para verificar UI con NVDA

No usar tablas en docs que el usuario final va a leer (NVDA lee celda por celda, rompe el flujo). Solo listas.

## Arquitectura en una pagina

- `core/` no importa `wx` a nivel de modulo. `llama_client.py` lo importa **solo adentro** de `_stream_worker` (threading daemon + wx.CallAfter)
- `ui/` depende de `core/` y de `wx`. Nunca al reves.
- `data/` es el unico side-effect persistente; esta gitignored.
- `Speech` envuelve `accessible_output2.outputs.auto.Auto()` con try/except en constructor y en cada metodo. `is_screen_reader_active()` usa `is_system_output()` para distinguir lector real de TTS fallback.
- `Conversation` escribe a `.tmp` y hace `Path.replace` (atomic write).
- `LlamaClient.chat_stream` lanza un `threading.Thread` daemon por request, parsea SSE linea por linea (`data: {...}` / `[DONE]`), abort via `threading.Event` chequeado ENTRE lineas, todos los callbacks por `wx.CallAfter`.
- `LlamaRunner.start_server` es wx-free y testeable; MainWindow solo traduce `(ok, mensaje)` a speech + status bar. Siempre pasa `--jinja` y `--n-gpu-layers 99`.
- Logger usa sentinel `_ollamachat_configured` en el logger (no `if logger.handlers`) para no chocar con pytest caplog.

## Decisiones de diseño (referencia rapida)

- Estructura `ollamachat/{core,ui,data}/` (no cambiarla; core testeable headless, ui wx, data runtime)
- Sin `ruff`/`mypy` (dropped para el MVP; pytest + verify cubren la calidad)
- `AGENTS.md` se mantiene
- Branch por defecto: `main` (no `master`)
- Strict TDD activo en `core/`
- Verificacion manual de UI en Windows (4 tareas `[windows-only]` pendientes en el change archivado)

## Donde esta el contexto profundo

Para una sesion nueva, leer en este orden:

1. `README.md` — que es la app y como se usa
2. `openspec/specs/<capability>/spec.md` — que tiene que hacer cada modulo
3. `openspec/changes/archive/2026-06-22-migrate-llama-cpp/proposal.md` — migracion Ollama→llama.cpp
4. `openspec/changes/archive/2026-06-22-migrate-llama-cpp/design.md` — arquitectura detallada + diagramas de secuencia
5. `openspec/changes/archive/2026-06-22-migrate-llama-cpp/verify-report.md` — verify final (102/102, 0 showstopper)
6. `CHANGELOG.md` — historial de versiones

## Estado actual

- Version: 0.2.0
- Tests: 102/102 pasan
- Backend: llama-server (llama.cpp) via API OpenAI-compatible. Ollama eliminado.
- SUGGESTION pendientes (no bloqueantes): set_models([]) sin anuncio de voz, _on_close bloquea 5s, stop_server_button re-enable redundante
- Verificacion manual en Windows: pendiente (UI con NVDA, streaming, botones servidor)

## Proximos cambios planificados

- v0.3.0: UX de navegacion (PROMPT_UX_NAVEGACION.txt) — ListBox historial, atajos Alt+N,
  F2 estado sesion, carga modelo en hilo de fondo, popup detalle, browser HTML, beep streaming,
  "Usar modelo", tokens en status bar, foco inicial correcto, confirmacion al cerrar.
- v0.4.0: Tool calling (PROMPT_TOOL_CALLING.txt) — PermissionManager, PermissionDialog,
  ToolExecutor (PowerShell), shell_execute tool, output en chat, reenvio al modelo.
  Prerequisito: v0.3.0 aplicado y verificado.

## Entorno

- WSL Ubuntu: no puede correr wx windows, solo logica testeable. wxPython no compila aca.
- Tests UI en WSL: AST checks sobre source + placeholders para Windows.
- Engram (`mem_save`/`mem_session_summary`) **no esta disponible** en este entorno. Persistir via OpenSpec files.

## SDD workflow

- Preflight: pace=interactive, artifact_store=openspec, delivery=single-pr-default, review_budget=400
- Cambios: `openspec/changes/<name>/` con proposal/specs/design/tasks/apply-progress/verify-report
- Archivados: `openspec/changes/archive/<fecha>-<name>/`
- Specs main: `openspec/specs/<capability>/spec.md`
- Para arrancar un nuevo change: usar `sdd-new-gentleman` o delegar a `sdd-propose-gentleman` con el contexto
