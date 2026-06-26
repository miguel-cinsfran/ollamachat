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
| WSL / Linux | core/ + AST estático | `uv run --no-sync pytest -xvs` |
| Windows | todos (wx runtime incluido) | `run_tests.bat` o `uv run pytest -xvs` |

**En Windows: hacer `uv sync` antes del primer `pytest`.** Los tests `ui/*_runtime.py`
requieren wx real y solo corren en Windows. Los `ui/*_static.py` son AST checks,
corren en ambos.

**git:** La rama es `main`. El repo remoto está autenticado (`gh` funciona en ambos entornos).

## Rol actual de Claude Code (junio–julio 2026)

opencode alcanzó el límite mensual (~25 jun 2026) y vuelve ~mediados julio.
**Claude Code actúa como implementor directo** mientras tanto — no solo revisor.

- **Trabajo realizado:** review pass 3 completo (10 bugs corregidos, ver commits
  `1fa31f5` y `f1ad6c3`). Root cleanup en `b970768`.
- **Pendiente cuando vuelva opencode:** Opus hará una revisión completa del codebase.
- **AGENTS.md** (gitignored, solo en WSL): reglas detalladas para opencode. En Windows
  Claude Code no lo tendrá — este CLAUDE.md es la guía principal.
- **Comentarios del código en inglés**: opencode/gentle-ai los generó en inglés.
  Las strings de UI están en español (verificado). No es un bug, es la realidad.

## Qué es esto

App de escritorio wxPython para chatear con modelos .gguf locales via llama-server
(llama.cpp). Backend: API OpenAI-compatible, SSE streaming, `--jinja` obligatorio.

## Estado actual

- Versión: **0.11.0**, tests **918/19** (passing/skipped). Backend: llama-server.
- Bugs conocidos corregidos en v0.11.0: tool-executing stuck, _on_done falso durante
  tool turn, warn_once ignorado, versión hardcodeada, file_tools sin UI.
- Verificación con NVDA real en Windows: **pendiente** (nunca probado en vivo).
  Probar antes de publicar.

## Correr tests

```bash
# WSL / Linux
uv run --no-sync pytest -xvs

# Windows (en PowerShell, desde la raíz del repo)
uv sync
uv run pytest -xvs        # o simplemente: run_tests.bat
```

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
  **granular por riesgo**, no por nombre de tool.
- **Contexto/F2:** el cliente envía `"stream_options": {"include_usage":true}` (sin eso
  `usage` NO llega en streaming y el % de contexto no funciona).
- **Multimodal:** `start_server` pasa `--mmproj` para activar visión; empareja mmproj
  por modelo; avisa si se adjunta imagen a un modelo sin visión.
- **Config/log:** `platformdirs` — jamás escribir dentro del paquete ni en `Program Files`.
- **API llama.cpp:** tok/s = `timings.predicted_per_second`; `n_ctx`/`meta` por `GET /props`.
  CLI: `-c/--ctx-size`, `-ngl/--n-gpu-layers`, `--jinja`.

## gh CLI — tareas e investigación

`gh` está autenticado con la cuenta de Miguel. Funciona en WSL y en Windows.
- **Tareas:** `gh repo view`, `gh issue list`, `gh pr list/view <n>`, `gh run list`.
- **Investigación sin clonar:**
  - listar archivos: `gh api repos/<o>/<r>/git/trees/<branch>?recursive=1 --jq '.tree[].path'`
  - leer archivo: `gh api repos/<o>/<r>/contents/<path>?ref=<branch> --jq '.content' | base64 -d`
  - buscar repos: `gh search repos "<términos>"`
- **Repos de referencia:**
  - `aaclause/nvda-OpenAI` (AIHub) — wxPython accesible; razonamiento `apiclient/_think_tags.py`.
  - `chigkim/VOLlama` — competidor, mismo stack (wxPython+accessible_output2).
  - `ggml-org/llama.cpp` — `docs/function-calling.md`, `tools/server/README.md`.
  - `miguel-cinsfran/ytchat-tts` — repo propio: menú contextual, temas de sonido.

## Contexto profundo (en WSL/local, gitignored)

1. `AGENTS.md` — reglas completas de arquitectura y diseño (para opencode)
2. `openspec/specs/` — specs por capability
3. `openspec/research/2026-06-24-investigacion-ux-y-toolcalling.md` — análisis UX/roadmap
4. `CONOCIMIENTO_WXPYTHON_ACCESIBLE.md` — referencia completa accesibilidad wxPython/NVDA
