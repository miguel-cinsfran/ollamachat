# OllamaChat

Cliente de escritorio accesible para chatear con modelos locales .gguf via llama-server (llama.cpp).
Diseñado para usuarios ciegos en Windows 11 con NVDA o JAWS.

Stack: Python 3.12, wxPython 4.2+, accessible-output2 0.17+, requests 2.31+.
Tests: pytest (186/186 en v0.4.0).

## Reglas criticas (no negociables)

- Cada control interactivo tiene `name=` descriptivo
- Cada control esta precedido en el sizer por `wx.StaticText` (MSAA asocia la etiqueta adyacente)
- Solo `wx.BoxSizer` horizontal o vertical. **Nunca** grid sizers (rompen el orden de lectura de NVDA)
- Fallos de accessible-output2 nunca crashean la app (try/except en cada metodo publico de `Speech`)
- Todos los callbacks desde hilos de fondo van por `wx.CallAfter` sin excepcion
- Sin `wx.WebView` (inaccesible). Usar `wx.TextCtrl` con `wx.TE_RICH2`
- Para detectar Shift/Ctrl/etc. usar `event.ShiftDown()`, nunca `wx.GetKeyState`
- Encoding `utf-8` explicito en toda lectura/escritura de archivos
- Compatible con Python 3.12, sin sintaxis de versiones posteriores

## Reglas adicionales de controles (investigadas en fuentes de NVDA)

- **No usar `wx.MessageDialog` para botones con labels personalizados en español** (regresiones MSAA). Para dialogos con 2+ botones custom: `wx.Dialog` + `wx.Button` nativos. Stock labels (YES_NO) sí OK para close confirm.
- **No usar `wx.richtext.RichTextCtrl`** ni `wx.html.HtmlWindow` para contenido que el usuario necesite leer con NVDA. Para HTML renderizado: `webbrowser.open()` con archivo temporal `.html` en browser nativo (Edge/Chrome con NVDA modo virtual).
- **Operaciones de mas de 2 segundos** (arrancar servidor, ejecutar comandos) en hilo de fondo con anuncios periodicos via `wx.CallAfter(speech.speak, ...)`. Nunca bloquear el hilo principal en silencio.
- **`wx.ListBox`** es el control mas accesible para listas navegables. Preferir sobre `wx.Choice`, `wx.ListCtrl` o `wx.CheckListBox`. Vista dual: ListBox (historial) + TextCtrl (stream) son dos controles separados.
- **Cuando el foco entra a un dialogo**, llamar `SetFocus()` en el primer control relevante.
- **`winsound` y modulos Windows-only** requieren guard: `if sys.platform == 'win32'` E import line-local DENTRO del guard.
- **Alt+numero** = atajos directos a controles. F2 = estado sesion. F6 = ciclar paneles. Enter = enviar (sin Shift). Shift+Enter = newline.

## Layout del proyecto

```
ollamachat/
  main.py
  core/               # wx-free, testeable
    speech.py, conversation.py, llama_client.py, llama_runner.py,
    text_utils.py [v0.3.0], logger.py
    permission_manager.py, tool_executor.py [v0.4.0]
  ui/                 # wx, testeable en Windows
    main_window.py, chat_panel.py, params_panel.py,
    message_detail_dialog.py [v0.3.0]
    permission_dialog.py [v0.4.0]
  data/               # gitignored runtime
tests/{core,ui,smoke}/
openspec/             # artefactos SDD
```

## Tests

- Windows: `uv sync` y despues `uv run pytest -xvs`.
- WSL / Linux sin wxPython: usar `uv run --no-sync pytest -xvs`. Tests de `core/` y smoke + AST de UI pasan (AST leen source, no importan wx).

## Como iterar

Bumpear version en `pyproject.toml` (semver), tests en WSL con `uv run --no-sync pytest -xvs`, copiar a Windows y verificar UI con NVDA. No usar tablas en docs para usuarios finales (NVDA lee celda por celda).

## Arquitectura

- `core/` no importa `wx` a nivel de modulo (`llama_client.py` lo importa dentro de `_stream_worker`).
- `ui/` depende de `core/` y de `wx`. Nunca al reves.
- `data/` es el unico side-effect persistente; gitignored.
- `Speech` envuelve accessible-output2 con try/except en cada metodo.
- `Conversation.save` hace atomic write a `.tmp` + `Path.replace`.
- `LlamaClient.chat_stream` lanza daemon thread, parsea SSE linea por linea, abort via `threading.Event`, callbacks por `wx.CallAfter`.
- `LlamaRunner` es wx-free; `start_server` siempre pasa `--jinja` y `--n-gpu-layers 99`.

## Decisiones de diseno

Estructura `ollamachat/{core,ui,data}/` (no cambiarla). Sin `ruff`/`mypy` (pytest + verify cubren). `AGENTS.md` se mantiene. Branch `main`. Strict TDD en `core/`. Verificacion manual de UI en Windows.

## Lecciones aprendidas (v0.3.0)

### Process
- **Verify post-apply DEBE leer TODOS los archivos cambiados.** Spot check inline perdió 3 bugs (B1, B2, B3) en v0.3.0 v1. El verify v2 (focused inline de archivos no leídos) encontró 5; v3 (focused en detail dialog) encontró 1 mas. Regla: sub-agente de verify, no spot check.
- **AST tests: chequean ESTRUCTURA (indentación), no posición.** El B3 v1 usaba `rfind` y pasaba en código viejo y nuevo; el v2 chequea `append_indent > if_indent` y atrapa la regresión.
- **`size:exception` está OK** si forecast > budget. Single PR estructurado en commits work-unit (15 para v0.3.0) es revisable commit por commit.

### Sub-agents
- Diagnóstico v0.3.0: contexto largo en el prompt puede colgar sub-agents silenciosamente. Acción: granularizar prompts en v0.4.0+ (dividir en 2+ llamadas cuando el contexto crece).
- `deepseek-v4-flash` anduvo bien para tareas de ejecución.
- `minimax-m3` anduvo bien para tareas de síntesis.
- **Táctica**: si un sub-agente cuelga, el orquestador escribe el artefacto inline como senior architect. Ya funcionó en `design.md` y `tasks.md` de v0.3.0.

### Code patterns (código wx multi-thread)
- `event.GetUnicodeKey()` (no `GetKeyCode()`) para chars no-ASCII. Importante para usuarios en español (B4 fix).
- `wx.CallAfter` es el único puente thread→main permitido. `threading.Timer.daemon = True`.
- `threading.Timer.cancel()` es idempotente; cancelar en done handler Y defensivamente en `_on_close`.
- `self._is_closing` flag en `_on_close` para evitar `wx.CallAfter` post-destroy (B2 fix).
- `threading.Thread` daemon + try/finally con defaults ANTES del try (B1 fix: UnboundLocalError en `_model_load_worker`).

### For v0.4.0
- No skipear verify sub-agente.
- Tool calling usará `wx.Dialog` + `wx.Button` nativos (no `MessageDialog`).
- Cada control wx: `name=` + StaticText previo + solo BoxSizer.

## Lecciones aprendidas (v0.4.0)

### Process
- **Verify post-apply sigue siendo crítico.** El verify v1 del v0.4.0-ui detectó CRITICAL-1: `tool_call_id` se perdía en `Conversation.add_message` (la spec y el apply sub-agent codificaron el bug como expected behavior). Regla reforzada: sub-agente de verify, no spot check.
- **El spec también es código.** Cuando la spec prescribe un bug, la implementación fiel reproduce el bug. Verify lee la spec Y el código; corrige la spec cuando prescribe algo incorrecto. El fix post-verify toca `core/conversation.py` aunque el change sea "UI only" — el bug lo justifica.
- **Post-verify fixes pequeños y bien definidos: inline OK.** Cuando verify encuentra bugs acotados (5 archivos, ~130 líneas) con root cause claro, el orquestador puede hacer el fix inline. El sub-agent de verify ya ejerció el juicio independiente. Documentar en el chat qué se fixed y por qué.

### Sub-agents — DELEGATE BY DEFAULT
- **Default: delegar. Inline: excepción con justificación.** v0.4.0-ui orquestador escribió proposal/specs/design/tasks inline porque el usuario dio la spec "completa". Error: perdí el paralelismo specs+design (única oportunidad real del grafo SDD), inflé mi contexto con 4 artefactos grandes (45k chars), no aproveché la especialización de modelo.
- **Cuándo SÍ escribir inline:** solo cuando un sub-agent ya colgó o devolvió output inutilizable, Y está documentado en el chat o en `apply-progress.md`. La "Táctica: si un sub-agent cuelga" de v0.3.0 era para FALLOS, no para atajos preventivos. Se aplicó mal.
- **Aprovechar paralelismo del grafo SDD.** Después de `proposal`, `specs` y `design` son paralelizables (ambos leen solo proposal; design no depende de specs). Lanzar en paralelo cuando aplique. Inline secuencial pierde esta ventaja.
- **Model assignments importan.** La tabla de model assignments asigna `deepseek-v4-flash` a design (architectural decisions) y tasks (mechanical breakdown), distinto del orquestador (`minimax-m3`). Delegar es también delegar el "tipo de pensamiento" al modelo más apto, no solo descargar trabajo.
- **El usuario dando la spec "completa" no es razón para saltarse sub-agents.** Estructurar la spec en proposal + escenarios GIVEN-WHEN-THEN + diagramas de secuencia + Review Workload Forecast es trabajo de phase, no de coordinación. El sub-agent de la phase está calibrado para eso.

### Code patterns (v0.4.0)
- `Conversation.add_message` con `tool_call_id` opcional (solo persiste cuando `role == "tool"`); `get_messages_for_api` lo propaga. Round-trip de tool calling depende de esto.
- `MainWindow._on_tool_result` pasa `tool_call_id=tool_call_id` a `add_message`. Sin esto, el segundo turno del tool-calling cycle se rompe (OpenAI-compatible API requiere `tool_call_id` en tool messages).
- AST tests cubren existencia y estructura, no comportamiento de runtime. Bugs de round-trip (como CRITICAL-1) requieren tests de `core/` que verifiquen el payload que sale por `get_messages_for_api`. Complementar AST con al menos un test runtime por cada capability que toca I/O o estado compartido.

## Estado actual

- Version: 0.4.0 (186/186 tests, tool calling UI layer done).
- Backend: llama-server (llama.cpp) via API OpenAI-compatible.
- Tool calling: PermissionManager, PermissionDialog (wx.Dialog nativo),
  ToolExecutor (PowerShell con fallback pwsh→powershell), SHELL_TOOL_DEFINITION.
- Pendiente: verificación manual en Windows (4 tareas `[windows-only]`:
  NVDA Tab order chat panel, F2 announcement, Alt+N shortcuts, popup Tab order).

## Entorno

- WSL Ubuntu: no corre wx windows, solo lógica testeable. Tests UI = AST checks sobre source.
- Engram (`mem_save`/`mem_session_summary`) **no está disponible** en este entorno. Persistir via OpenSpec files.

## SDD workflow

- Cambios: `openspec/changes/<name>/` con proposal/specs/design/tasks/verify-report/archive-report.
- Archivados: `openspec/changes/archive/<fecha>-<name>/`.
- Specs main: `openspec/specs/<capability>/spec.md`.
- Para arrancar: `sdd-new-gentleman` o delegar a `sdd-propose-gentleman` con el contexto.
- Grafo SDD: `proposal → (specs || design) → tasks → apply → verify → archive`. Después de proposal, specs y design se pueden delegar **en paralelo** (ambos leen solo proposal; design no depende de specs). No perder esa oportunidad.
