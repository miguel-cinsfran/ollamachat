# Bellbird — guía para Claude Code / Sonnet

App de escritorio **wxPython** para chatear con modelos `.gguf` locales vía
**llama-server** (llama.cpp). Backend OpenAI-compatible, SSE streaming, `--jinja`
obligatorio. **Usuario: Miguel, ciego, NVDA en Windows 11.** Toda decisión de UI
pasa por "¿funciona con lector de pantalla?".

## Cómo retomar — decí "continuemos"

El disco es tu memoria, no la conversación. Al empezar o tras una compactación:

1. Leé **`memory/MEMORY.md`** y **`memory/project_state.md`** → estado vivo +
   **próxima tarea concreta** (qué falta, archivo:línea, criterio "done").
2. `git log --oneline -8` → qué se hizo recién.
3. Corré los tests (ver "Correr tests") y confirmá **verde antes de tocar nada**.
4. **Logs de sesión de Miguel:** `C:\Users\ic_ma\AppData\Local\Bellbird\logs\session_*.log`
   (el más nuevo). Tienen cada `speak()`/`output()`, lifecycle de server/modelo, F2,
   tools, backend. **Diagnosticá desde el log ANTES de pedirle que describa.**

## Sobrevivir a la auto-compactación (CRÍTICO para Sonnet)

Tu contexto se llena y **se compacta solo en ciclos (~80%)**. Para no perder el hilo:

- **El estado va a disco, no a tu cabeza.** Después de cada paso con sentido —y antes
  de que el contexto se llene— actualizá `memory/project_state.md`: qué hiciste, qué
  falta, **el siguiente edit exacto** con `archivo:línea`. Tras compactar, ese archivo
  + `git log` + esta guía son tu única fuente de verdad.
- **Lotes chicos, commit por lote.** Una unidad coherente → tests verdes → commit →
  actualizá `project_state.md`. El commit es el registro durable: si te compactás a
  mitad, el git log te dice dónde quedaste.
- **Nunca dejes trabajo a medias sin anotarlo.** Refactor incompleto → nota con el
  estado exacto y el próximo paso.
- **Re-orientate primero** (los 4 pasos de "Cómo retomar") en lugar de asumir.

Patrón de referencia: planificación persistente en archivos (`OthmanAdi/planning-with-files`),
memory-bank (`centminmod/my-claude-code-setup`).

## Entorno: WSL vs Windows

`uname -r` contiene "microsoft" → WSL. En **Windows hacé `uv sync`** antes del 1er pytest.

| Entorno | Tests | Comando |
|---------|-------|---------|
| WSL/Linux | core + AST estático | `uv run --no-sync pytest tests/core -q` |
| Windows | todos (wx runtime) | `run_tests.bat` |

Los `ui/*_runtime.py` requieren wx real (solo Windows); los `ui/*_static.py` son AST
(ambos). **git:** rama `main`, remoto autenticado (`gh` anda en ambos).

## Correr tests — NO uses un solo proceso pytest

`uv run pytest` (toda la suite en UN proceso) **se cuelga al ~70%** por acumulación de
estado wxPython. Cada carpeta pasa sola, en su propio proceso:

```bash
run_tests.bat                                              # Windows: todo, por carpeta
uv run pytest tests/core -o addopts= -q -p no:cacheprovider
uv run pytest tests/ui   -o addopts= -q -p no:cacheprovider
uv run --no-sync pytest tests/core -q                      # WSL (ui runtime se saltan)
```

- `addopts` por defecto es `-xvs` → pasá `-o addopts=` para correr todo, no parar al 1er fallo.
- `scripts/diagnose_tests.ps1 [timeout]`: corre cada archivo aislado para cazar un cuelgue.
- Baseline actual: **core 685 ✓, ui 405 ✓ (+2 skip)**. `tests/build/...` falla (preexistente,
  script .sh en Windows; no relacionado).
- **Presupuesto:** Miguel está en plan $20. Batchea TODOS los fixes y corré los tests UNA
  vez al final, no tras cada edit. Sé conciso.

## Flujo de trabajo

**Claude/Sonnet es el implementor directo** (opencode offline). Miguel prueba en vivo
con NVDA → te pasa el log → diagnosticás → arreglás → tests → **commiteás solo con su OK**
(cambios de UI/accesibilidad: que los pruebe primero). Comentarios de código en **inglés**,
strings de UI en **español** (no es bug).

## Reglas críticas de UI (no negociables)

- **Nunca** `wx.MessageDialog` con labels en español (regresión MSAA) → `wx.Dialog` custom
  con `wx.Button` nativos.
- **Nunca** `RichTextCtrl`, `HtmlWindow` ni `WebView` (inaccesibles). HTML legible →
  `webbrowser.open()` + tempfile `.html`.
- **`wx.ListBox`** = el control de lista más accesible. Preferir siempre.
- **CheckBox** toma su nombre accesible de su PROPIO `label=` (NO de un StaticText previo;
  eso solo vale para edit/combo). Sin `label=` → "sin etiqueta".
- **StaticText ANTES del control** en el código (z-order → asociación de label UIA).
- Toda op >2s: hilo de fondo + `wx.CallAfter(speech.speak, ...)`. Todo callback de hilo de
  fondo: `wx.CallAfter`, sin excepción.
- Código Windows-only (`winsound`): guard `if sys.platform == 'win32'`.

## Regla de seguridad (tool calling)

El sistema de permisos **nunca** auto-bloquea operaciones en directorios del usuario.
Auto-bloqueo SOLO para paths de sistema: `C:\Windows`, `C:\System32`, `C:\Program Files`,
`Format-Volume`, `Clear-Disk`. Todo lo demás pasa por el diálogo de confirmación.

## Arquitectura

```
bellbird/core/  # wx-free, 100% testeable en WSL. NUNCA importa wx a nivel módulo.
bellbird/ui/    # wx, solo verificable en Windows. Depende de core/, nunca al revés.
bellbird/data/  # runtime, gitignored (platformdirs). Jamás escribir en el paquete.
scripts/        # run_tests.ps1, diagnose_tests.ps1, generate_sound_assets.py
```

**Archivo gigante:** `ui/main_window.py` (~2.4k líneas) — candidato a partir en módulos
(`ServerController`/`StreamController`/`StatusReporter`). Riesgoso: los AST tests están
acoplados a su forma → podarlos primero (ver roadmap).

## Checklist de gotchas (lo que más se rompe)

- **Razonamiento:** dos vías (`reasoning_content` + parser `<think>` inline). NUNCA guardar
  en `_current_response` ni `Conversation`; no se lee en voz por defecto.
- **Tool-calling:** reenviar el `assistant` con `tool_calls[]` en el 2º turno;
  `finish_reason == "tool_calls"`; guard de iteraciones. Soporte de tools = `/props`
  `chat_template_caps.supports_tools` (NO `chat_template_tool_use`). Al denegar/bloquear:
  llamar `_finish_tool_turn()` o `_is_generating` queda pegado (freeze). Con tools on se
  inyecta `core/tool_prompt.py` (entorno Win11/WSL + reglas).
- **Envío sin freeze:** `send_message` hace el prep pesado (`token_count`/`read_vram`/
  `check_tool_support`) en un **hilo de fondo** (`prep_worker`) y reanuda en
  `_continue_send` vía `wx.CallAfter`. Guard de re-entrada `_preparing_send`. NO volver a
  poner esas llamadas síncronas en el hilo UI.
- **F2 lee SOLO cachés** (`_loaded_model_name`, `_server_state_cache`, `_vram_*`,
  `_fit_status`, `_active_persona_name`) — NUNCA HTTP/IO en el hilo UI. `_fetch_server_meta_async`
  puebla n_ctx+VRAM+fit. `"stream_options":{"include_usage":true}` SÍ se envía. Resetear
  tokens en `new_conversation`.
- **GPU/`-ngl`:** usar `-1` (auto-fit a la VRAM). Forzar `99` DESACTIVA el auto-fit
  (`common_fit_params`) → OOM. En `start_server`, `n_gpu_layers < 0` OMITE el flag.
  **Config por-modelo ya existe:** `config.model_tunings[basename]` guarda `ctx_size`/
  `n_gpu_layers`; se restaura al cargar (anuncio audible) y se guarda desde Preferencias.
- **Multimodal:** visión necesita un **mmproj SEPARADO** (`--mmproj`); auto-detección solo
  de sibling `mmproj-*`. Sin mmproj el modelo carga solo-texto. NO forzar diálogo de mmproj
  en cada carga (bug madre). Falta selector opt-in (ver roadmap).
- **Keymap:** teclas F de wxPython 4.2: F1=340, **F2=341**, …, F8=347 (estuvieron desfasadas
  en 1). HTML: NO usar extensión markdown `nl2br` (corta la lectura de NVDA).
- **Config/log:** `platformdirs`. Logs por sesión `<user-data>/logs/session_*.log` (poda 20).
- **Tests ui runtime:** wx.App de sesión + fixtures `_isolate_config`/`conftest.py` (redirigen
  `CONFIG_PATH` a tmp). Lista de chat vacía muestra una fila-hint (evita "desconocido" en NVDA);
  nunca entra en `get_history()`.

## Pendiente / roadmap (prioridad)

1. **Imágenes/visión** (prep para que Miguel pruebe): bajar el mmproj de GLM-4.6V con `hf`,
   selector opt-in de mmproj, **contenedor visible de adjuntos** en `chat_panel`. El send ya
   maneja `attached_images`+content-array+`_vision_capable`.
2. **CUDA por defecto:** detectar NVIDIA (ya se lee VRAM con nvidia-smi) y usar/ofrecer un
   **build CUDA** de llama-server por defecto (Miguel usa Vulkan, más lento). Idealmente
   automatizar la descarga.
3. **Limpieza tests + partir `main_window.py`:** podar los AST estáticos frágiles (~150-250,
   prueban forma no comportamiento) y modularizar `main_window`. Suite verde siempre.
4. **Roadmap:** buscar/descargar modelos con `hf` desde la app.

Hechos recientes (NO repetir): send-freeze, F2 cache+persona, keymap, tools+env-prompt,
auto-fit GPU, sonidos, model-switch, hint de lista vacía, config por-modelo audible.

## gh CLI — investigación sin clonar

`gh` autenticado (ambos entornos). `hf` (Hugging Face) también → modelos en `~/models`.
Hardware de Miguel: **RTX 2080, 8 GB VRAM, build Vulkan**.

- listar: `gh api repos/<o>/<r>/git/trees/<branch>?recursive=1 --jq '.tree[].path'`
- leer: `gh api repos/<o>/<r>/contents/<path>?ref=<branch> --jq '.content' | base64 -d`
- **Repos de referencia:** `aaclause/nvda-OpenAI` (wxPython accesible),
  `chigkim/VOLlama` (mismo stack), `ggml-org/llama.cpp` (`docs/function-calling.md`,
  caps de tools en `/props`), tool-prompts: `cline/cline`, `openai/codex`,
  `OpenInterpreter/open-interpreter`.

## Contexto profundo (gitignored, solo local)

`AGENTS.md` (arquitectura), `openspec/specs/` (specs), `CONOCIMIENTO_WXPYTHON_ACCESIBLE.md`
(accesibilidad wxPython/NVDA — leer antes de tocar cualquier control wx).
