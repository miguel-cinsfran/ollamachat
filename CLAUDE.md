# Bellbird — guía rápida para Claude Code

## Usuario y contexto

Miguel es ciego, usa NVDA en Windows 11. Toda decisión de UI tiene que pasar
por "¿funciona con lector de pantalla?". Ver `CONOCIMIENTO_WXPYTHON_ACCESIBLE.md`
(solo en WSL/local, gitignored) antes de tocar cualquier control wx.

## Entorno: WSL vs Windows

Claude Code puede correr en WSL o en Windows. Detectar antes de actuar:

```bash
# ¿Estoy en WSL?
uname -r   # contiene "microsoft" → WSL
```

| Entorno | Tests disponibles | Comando |
|---------|-------------------|---------|
| WSL / Linux | core/ + AST estático | `uv run --no-sync pytest tests/core -q` |
| Windows | todos (wx runtime incluido) | `run_tests.bat` (NO `uv run pytest` a secas — ver "Correr tests") |

**En Windows: hacer `uv sync` antes del primer `pytest`.** Los tests `ui/*_runtime.py`
requieren wx real y solo corren en Windows. Los `ui/*_static.py` son AST checks,
corren en ambos. **OJO:** correr toda la suite en un proceso se cuelga (ver "Correr tests").

**git:** La rama es `main`. El repo remoto está autenticado (`gh` funciona en ambos entornos).

## Rol actual de Claude Code (jun 2026)

**Claude Code es el implementor directo**, probando en vivo con Miguel (Windows, NVDA real).
opencode offline. Flujo de trabajo de esta etapa: **Miguel prueba la app → me pasa el log de
sesión → diagnostico y arreglo → corro tests → sin commitear (espera su OK)**.

- **Comentarios del código en inglés** (opencode/gentle-ai); strings de UI en español. No es bug.
- **`hf` CLI** (Hugging Face) está instalado y autenticado → puedo descargar modelos/mmproj. Los
  modelos de Miguel están en `~/models` (`C:\Users\ic_ma\models`).
- **Hardware de Miguel:** NVIDIA RTX 2080, **8 GB VRAM**. Su build de llama-server usa **Vulkan**
  (no CUDA) — verificado en log. Loadeo lento/OOM con modelos grandes viene de ahí.

## Qué es esto

App de escritorio wxPython para chatear con modelos .gguf locales via llama-server
(llama.cpp). Backend: API OpenAI-compatible, SSE streaming, `--jinja` obligatorio.

## Estado actual (jun 2026, sin commitear — árbol de trabajo)

- Tests: **core 683 ✓, ui 397 ✓ (+2 skip)**. `tests/build/test_build_windows_script.py` FALLA
  (preexistente, script .sh en Windows; no relacionado).
- **Probado en vivo con NVDA.** Sesión grande de arreglos de usabilidad (ver "Conocimiento
  verificado" abajo). Muchos bugs madre corregidos: F2 (keytas), tools, auto-fit GPU, deny-freeze,
  sonidos, casillas no leídas, etc.

## Correr tests — IMPORTANTE: NO uses un solo proceso pytest

**Correr `uv run pytest` (toda la suite en UN proceso) SE CUELGA al ~70%** por acumulación de
estado wxPython (ventanas de los tests ui que no se desmontan del todo). Cada carpeta pasa sola.

```bash
# Windows — la forma correcta: cada carpeta en su PROPIO proceso (run_tests.bat → run_tests.ps1)
run_tests.bat
# o manual, por carpeta:
uv run pytest tests/core -o addopts= -q -p no:cacheprovider
uv run pytest tests/ui   -o addopts= -q -p no:cacheprovider
uv run pytest tests/smoke -o addopts= -q -p no:cacheprovider

# WSL / Linux (solo core + AST estático; ui runtime se saltan por importorskip)
uv run --no-sync pytest tests/core -q
```

- `run_tests.bat` → `scripts/run_tests.ps1`: corre cada carpeta en proceso separado, salida EN VIVO
  (Tee), copia al portapapeles. NO bufferiza (el bat viejo escondía cuelgues).
- `scripts/diagnose_tests.ps1 [timeout]`: corre CADA archivo en su proceso con timeout para cazar
  el culpable de un cuelgue.
- `addopts` por defecto es `-xvs` (para en el 1er fallo) → pásalo `-o addopts=` para correr todo.
- Tests ui runtime usan un wx.App de sesión + `_isolate_config` fixture (redirige `CONFIG_PATH` a
  tmp). Si agregás un test que llama `MainWindow` métodos que persisten, el fixture lo aísla.

## Reglas críticas de UI (no negociables)

- **Nunca** `wx.MessageDialog` para botones con labels en español — regresión MSAA documentada.
  Usar `wx.Dialog` custom con `wx.Button` nativos.
- **Nunca** `wx.richtext.RichTextCtrl` — "poor choice for screen readers" según docs oficiales.
- **Nunca** `wx.html.HtmlWindow` para contenido legible — sin soporte MSAA/UIA fiable.
- **Nunca** `wx.WebView` — inaccesible para lectores.
- Para HTML renderizado: `webbrowser.open()` + tempfile `.html` (browser con NVDA virtual mode).
- Toda operación >2s: hilo de fondo + anuncios periódicos via `wx.CallAfter(speech.speak, ...)`.
- `wx.ListBox` es el control de lista más accesible con NVDA. Preferir siempre.
- Todo callback desde hilo de fondo: `wx.CallAfter` sin excepción.
- `winsound` y código Windows-only: guard `if sys.platform == 'win32'`.
- **StaticText ANTES del control** en el código (z-order → UIA label association).

## Regla de seguridad (tool calling)

El sistema de permisos **nunca** bloquea automáticamente operaciones en directorios
del usuario. Auto-bloqueo SOLO para paths de sistema: `C:\Windows`, `C:\System32`,
`C:\Program Files`, `Format-Volume`, `Clear-Disk`. Todo lo demás pasa por el diálogo
de confirmación.

## Arquitectura

```
bellbird/core/    # wx-free, 100% testeable en WSL
bellbird/ui/      # wx, solo verificable con wx real (Windows)
bellbird/data/    # runtime, gitignored (platformdirs)
openspec/         # specs SDD + research (gitignored)
scripts/          # build_windows.sh, generate_sound_assets.py
smoke_test.py     # fase 1: imports core; fase 2: imports ui; fase 3: UIA (Windows+pywinauto)
```

`core/` nunca importa `wx` a nivel de módulo. `ui/` depende de `core/`, nunca al revés.

## Workflow de cambios (SDD)

Cada feature va por `openspec/changes/<nombre>/` con proposal → specs → design → verify-report.
Antes de implementar cualquier cosa nueva: leer el spec en `openspec/specs/<capability>/spec.md`.

**Con opencode offline:** implementar directamente con Claude Code, sin artefactos SDD formales.
Documentar decisiones en el mensaje de commit.

## Checklist de gotchas (lo que más se rompe)

- **Razonamiento:** soporta DOS vías (`reasoning_content` + parser `<think>` inline);
  NUNCA guardar en `_current_response` ni en `Conversation`; no se lee en voz por defecto.
- **Tool-calling:** reenviar el mensaje `assistant` con `tool_calls[]` en el 2º turno;
  `finish_reason == "tool_calls"`; guard de iteraciones; "permitir en sesión" es
  **granular por riesgo**, no por nombre de tool. **Soporte de tools = `/props`
  `chat_template_caps.supports_tools`** (NO `chat_template_tool_use`, que es muy estricto).
  Al denegar/bloquear: llamar `_finish_tool_turn()` o `_is_generating` queda pegado (freeze).
  Con tools on se inyecta `core/tool_prompt.py` como system message (entorno + reglas de uso).
- **Contexto/F2:** `"stream_options": {"include_usage":true}` SÍ se envía (sin eso no hay `usage`).
  `_current_n_ctx` se fetchea de `/props` (`default_generation_settings.n_ctx`) al cargar, en
  background. **F2 lee SOLO cachés** (`_loaded_model_name`, `_server_state_cache`, `_vram_*`,
  `_fit_status`) — NUNCA HTTP en el hilo UI (causaba lag). `_fetch_server_meta_async` puebla
  n_ctx+VRAM+fit. Resetear tokens en `new_conversation`.
- **Multimodal:** visión necesita un **mmproj SEPARADO** (`--mmproj`); auto-detección solo de
  `mmproj-*` sibling. Sin mmproj el modelo carga solo-texto aunque sea multimodal. NO forzar
  diálogo de mmproj en cada carga (bug madre viejo). Falta selector opt-in (ver Pendiente).
- **Config/log:** `platformdirs` — jamás escribir dentro del paquete ni en `Program Files`.
  Logs **por sesión** en `<user-data>/logs/session_*.log` (poda 20). `Speech` loggea cada anuncio.
- **API llama.cpp:** tok/s = `timings.predicted_per_second`; `n_ctx`/`meta`/`chat_template_caps`/
  `modalities` por `GET /props`. CLI: `-c/--ctx-size`, `--jinja`. **`-ngl/--n-gpu-layers`: usar
  `-1` (auto) → llama.cpp ajusta capas a la VRAM.** Forzar `99` DESACTIVA el auto-fit (`common_fit_params`)
  → modelos > VRAM hacen OOM. En `start_server`, `n_gpu_layers < 0` OMITE el flag.

## Conocimiento técnico verificado (sesión jun 2026)

- **Keymap (`core/keymap.py`):** las constantes de teclas F DEBEN ser las de wxPython 4.2:
  F1=340, **F2=341**, F3=342, F4=343, F5=344, F6=345, F7=346, F8=347. Estuvieron TODAS desfasadas
  en 1 (F2=340=F1) → F2 no disparaba. Los menús con `\tF7` andan igual (wx parsea el texto), solo
  la AcceleratorTable usaba el código malo.
- **CheckBox + NVDA:** una casilla toma su nombre accesible de su PROPIO `label=`, NO de un
  StaticText previo (eso solo vale para edit/combo). Casillas sin `label=` salen "sin etiqueta".
- **HTML legible:** NO usar extensión markdown `nl2br` (convierte cada `\n` en `<br>` → NVDA lee
  fragmentos cortados). Ver `core/html_render.py`.
- **Ventana al abrir:** `main.py` hace `SetTopWindow + Show + Raise` para que NVDA anuncie el título.
  Foco inicial al combo de modelos (`_set_initial_focus`).
- **Anunciador periódico:** `_PeriodicAnnouncer` (en `ui/main_window.py`) con flag `_cancelled` —
  reemplazó un timer encadenado roto que repetía "Cargando modelo" para siempre.
- **Sonidos:** `scripts/generate_sound_assets.py` sintetiza ~17 WAV distintos en
  `bellbird/data/sounds/default/` (gitignored — correr el script tras instalar). `SoundPlayer`
  tiene `play`, `play_loop` (SND_LOOP), `stop` (SND_PURGE). `connecting.wav` = loop sin clic.
- **Cambio de modelo:** `start_server` fast-path compara el modelo cargado vs el pedido; si difiere
  y el server es untracked (sesión previa), `_force_stop_on_port(port)` (PowerShell→taskkill).
- **Aislamiento de tests:** `_make_frame` (tests ui) retornaba DENTRO del `with patch(save_config)`
  → escribía en config real. Fix: fixture `_isolate_config`. Si tocás esto, cuidado.

## Pendiente / roadmap (lo que falta)

1. **Imágenes/visión:** descargar el mmproj del modelo multimodal con `hf` (GLM-4.6V, etc.), darle
   un selector opt-in de mmproj, y un **contenedor visible de adjuntos** en `chat_panel` para
   verificar que la imagen va. Hoy GLM-4.6V carga sin mmproj → no ve imágenes.
2. **CUDA:** detectar GPU NVIDIA y **ofrecer instalar/usar un build CUDA** de llama-server (Miguel
   usa Vulkan, más lento/menos eficiente). Idealmente automatizar la descarga del build.
3. **Freeze 2-3 s al enviar:** `send_message` corre síncrono en hilo UI `token_count` (`/tokenize`),
   `read_vram()` (nvidia-smi) y `check_tool_support` (`/props`). Mover a hilo de fondo.
4. **Persona activa "desconocido":** NVDA lee "desconocido" en lista vacía de personas — revisar.
5. **Feature futura (roadmap):** buscar/descargar modelos con `hf` desde la app.

## Revisión del trabajo de opencode (cuando vuelva ~julio)

Cuando Miguel vuelva con el resultado de una capa, revisar así:
1. Abrir el diff/commits + el verify-report. Identificar qué prompt fue y leer su
   sección **Done When** + el **§** del doc de investigación que referencia.
2. Correr `uv run --no-sync pytest -xvs` (en WSL: core + AST). Confirmar verde.
3. Contrastar el diff contra: **Reglas críticas de UI**, **regla de seguridad**, y el
   **checklist de gotchas** de arriba.
4. **Tests:** confirmar que lo nuevo wx-runtime quedó con `pytest.importorskip("wx")` y
   registrado en `run_tests.bat`. Lo `core/` sí corre en WSL.
5. Bug **pequeño y acotado** → arreglar inline. Grande o cambia diseño → nuevo prompt.

**Prompts (gentle-ai):** deben ser **ricos ~7–9k caracteres** (no 1–2k). Inlinean:
objetivo, estado con `archivo:línea`, hechos verificados, alcance, archivos a tocar,
casos de test, criterios "done". Fuente de diseño: `openspec/research/2026-06-24-investigacion-ux-y-toolcalling.md`.

## gh CLI — tareas e investigación

`gh` está autenticado con la cuenta de Miguel. Funciona en WSL y en Windows.
- **Tareas:** `gh repo view`, `gh issue list`, `gh pr list/view <n>`, `gh run list`.
- **Investigación sin clonar:**
  - listar archivos: `gh api repos/<o>/<r>/git/trees/<branch>?recursive=1 --jq '.tree[].path'`
  - leer archivo: `gh api repos/<o>/<r>/contents/<path>?ref=<branch> --jq '.content' | base64 -d`
  - buscar repos: `gh search repos "<términos>"`
- **Repos de referencia:**
  - `aaclause/nvda-OpenAI` (AIHub) — wxPython accesible; razonamiento `apiclient/_think_tags.py`.
  - `chigkim/VOLlama` — competidor, mismo stack (wxPython+accessible_output2); usa Ollama API.
  - `ggml-org/llama.cpp` — `docs/function-calling.md`, `common/jinja/caps.h` (caps de tools),
    `tools/server/server-context.cpp` (`chat_template_caps` en `/props`).
  - `miguel-cinsfran/ytchat-tts` — repo propio: menú contextual, temas de sonido.
  - Tool/system prompts de agentes (para el prompt de herramientas): `cline/cline`,
    `OpenInterpreter/open-interpreter`, `openai/codex` (codex-rs prompts), `x1xhlol/system-prompts-and-models-of-ai-tools`.

## Contexto profundo (en WSL/local, gitignored)

1. `AGENTS.md` — reglas completas de arquitectura y diseño (para opencode)
2. `openspec/specs/` — specs por capability
3. `openspec/research/2026-06-24-investigacion-ux-y-toolcalling.md` — análisis UX/roadmap
4. `CONOCIMIENTO_WXPYTHON_ACCESIBLE.md` — referencia completa accesibilidad wxPython/NVDA
