# Changelog

Todas las versiones notables del proyecto OllamaChat.

## [0.2.0] - 2026-06-22

### Cambiado
- Backend migrado de Ollama a llama.cpp (`llama-server` vía HTTP en `localhost:8080`)
- `ollamachat/core/ollama_client.py` reemplazado por `llama_client.py` (API OpenAI-compatible con SSE)
- `ollamachat/core/ollama_runner.py` reemplazado por `llama_runner.py` (lifecycle PID trackeado + `.gguf` discovery)
- `wx.Choice` cambiado a `wx.ComboBox` en el selector de modelo, con botones "Buscar modelos" y "Explorar..."
- Toolbar: "Iniciar Ollama" renombrado a "Iniciar servidor"; nuevo botón "Detener servidor"
- `send_message` ya no pasa `model=`; usa content-array OpenAI para adjuntos de imagen
- Parámetro `num_predict` renombrado a `max_tokens`
- Startup detecta 3 estados: no instalado (dialog con `winget`), detenido, corriendo
- `_on_close` detiene `llama-server` al cerrar la ventana

### Agregado
- 13 tests nuevos para `LlamaClient` (health check, model listing, SSE streaming, abort)
- 17 tests nuevos para `LlamaRunner` (find/start/stop, gguf discovery, install command)
- `_on_browse_model`: diálogo para seleccionar `.gguf` manualmente

### Eliminado
- `ollamachat/core/ollama_client.py`, `ollamachat/core/ollama_runner.py`
- `tests/core/test_ollama_client.py`, `tests/core/test_ollama_runner.py`
- Soporte para API NDJSON de Ollama (`/api/chat`, `/api/tags`)

### Conocido
- 4 tareas `[windows-only]` de verificación manual: instalar `llama-server` via `winget`, probar streaming, switch de modelo, detener servidor

## [0.1.1] - 2026-06-22

### Agregado
- Boton "Iniciar Ollama" en MainWindow con etiqueta StaticText "Servidor:" antes
- Modulo `ollamachat/core/ollama_runner.py` (wx-free) que lanza `ollama serve` con `CREATE_NO_WINDOW` en Windows y hace poll hasta 5 segundos
- Modulo `ollamachat/core/logger.py` con file logger a `data/ollamachat.log` (utf-8, never-crash, sentinel para idempotencia)
- Metodo `Speech.is_screen_reader_active()` que distingue NVDA/JAWS real de TTS fallback via `is_system_output()`
- Script `scripts/build_windows.sh` que corre pytest, copia el source excluyendo dev, escribe `build.bat` + `ollamachat.spec` + `LEEME.txt`, y zipea en `dist/`
- `LEEME.txt` generado en cada kit con instrucciones breves en espanol para end users
- 21 tests nuevos: 6 logger + 8 ollama_runner + 4 speech.is_screen_reader_active + 3 main_window AST

### Cambiado
- `build.bat` ahora intenta uv primero, cae a venv+pip si no esta uv
- `ChatPanel.__init__` acepta callback `on_send` (era no-op; ver fix de v0.1.0)
- Adjuntar archivo de texto ahora se incluye en el contenido del mensaje del usuario, no como mensaje separado

### Arreglado
- v0.1.0 CRIT-1: Enter key en message_input no enviaba (handler no-op)
- v0.1.0 CRIT-2: attached text file content nunca llegaba a la API
- v0.1.0 CRIT-3: boton Limpiar no limpiaba conversation history
- v0.1.0 CRIT-4: about y shortcuts dialogs no se anunciaban por voz
- v0.1.0 WARN-1: Shift key detection usaba wx.GetKeyState en vez de event.ShiftDown()
- v0.1.0 WARN-2: status bar model update no hablaba
- v0.1.0 WARN-3: on_error no mostraba wx.MessageDialog
- v0.1.0 WARN-4: _current_response no se limpiaba en error

## [0.1.0] - 2026-06-22

### Agregado
- Implementacion inicial MVP
- `ollamachat/core/speech.py`: wrapper accessible-output2 con never-crash contract
- `ollamachat/core/conversation.py`: persistencia JSON con atomic write
- `ollamachat/core/ollama_client.py`: REST + NDJSON streaming con threading.Event abort
- `ollamachat/ui/main_window.py`: SplitterWindow, menu bar, AcceleratorTable, status bar, startup check
- `ollamachat/ui/chat_panel.py`: TE_RICH2 display, TE_PROCESS_ENTER input, file attach
- `ollamachat/ui/params_panel.py`: model selector, system prompt, sliders con speech feedback
- 7 capability specs en `openspec/specs/`
- 72 tests pasan (52 core/smoke + 20 AST static)

### Conocido
- 4 tareas `[windows-only]` requieren verificacion manual con NVDA en Windows 11
- 3 SUGGESTION no bloqueantes del verify (ver AGENTS.md)
