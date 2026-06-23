# Spec: llama-integration

## Purpose

Defines the `LlamaClient` and `LlamaRunner` headless modules that talk to a
local `llama-server` (llama.cpp's OpenAI-compatible HTTP server on port 8080).
The client must (1) detect whether the server is healthy, (2) report the loaded
model, (3) stream chat completions token-by-token via SSE in a background
thread, and (4) hand a usable `.gguf` path and lifecycle controls to the UI
through a small, testable surface. Both modules are wx-free and therefore
fully unit-tested with stubbed HTTP responses and a fake subprocess.

## Requirements

### REQ-LLAMA-001: Health check
**Statement**: `LlamaClient.check_running()` MUST issue `GET {base_url}/health`
with a 5-second timeout and return `True` iff the response is HTTP 200 with
body `{"status": "ok"}`; any other outcome (connection refused, timeout,
non-200, malformed body) MUST return `False` without raising.
**Rationale**: Blind users cannot see a process icon. The app MUST determine
server state programmatically and announce it by voice.

- GIVEN a stubbed session whose `GET /health` returns 200 with body `{"status": "ok"}`
- WHEN `check_running()` is called
- THEN it returns `True` and does not raise

- GIVEN a stubbed session whose `GET /health` raises `ConnectionError`
- WHEN `check_running()` is called
- THEN it returns `False` and does not raise

- GIVEN a stubbed session whose `GET /health` returns 503
- WHEN `check_running()` is called
- THEN it returns `False` and does not raise

- GIVEN a stubbed session whose `GET /health` raises `requests.exceptions.Timeout`
- WHEN `check_running()` is called
- THEN it returns `False` and does not raise

### REQ-LLAMA-002: List the loaded model
**Statement**: `LlamaClient.get_loaded_model()` MUST issue `GET {base_url}/v1/models`
with a 5-second timeout and return the `id` field of the first entry in the
`data` array; on any error, timeout, or non-200 response the method MUST
return the empty string `""` without raising.
**Rationale**: The model basename is needed for the status bar and voice
announcement on startup; failure must be silent so the app keeps booting.

- GIVEN a stubbed session whose `GET /v1/models` returns 200 with body `{"data": [{"id": "llama-3.1-8b-instruct-q4_k_m.gguf"}]}`
- WHEN `get_loaded_model()` is called
- THEN it returns `"llama-3.1-8b-instruct-q4_k_m.gguf"`

- GIVEN a stubbed session that raises `ConnectionError`
- WHEN `get_loaded_model()` is called
- THEN it returns `""` and does not raise

### REQ-LLAMA-003: Stream chat completions
**Statement**: `LlamaClient.chat_stream(messages, options, on_token, on_done, on_error, on_usage: Callable[[dict], None] | None = None)`
MUST spawn a daemon `threading.Thread` and POST `{base_url}/v1/chat/completions`
with a JSON body that contains `messages`, `stream: true`, `model: "local"`,
and the sampling parameters at the **root** of the body (NOT nested in an
`options` sub-object): `temperature`, `top_p`, `top_k`, `repeat_penalty`, and
`max_tokens` (derived from `options["num_predict"]`). The worker MUST parse
the SSE response line by line: lines beginning with `data: ` are stripped of
the prefix, JSON-decoded, and the `choices[0].delta.content` value is
forwarded to `on_token`; lines equal to `data: [DONE]` terminate the stream
without an error; blank lines and lines that fail JSON decoding are skipped
silently. The worker MUST handle SSE lines that span multiple `recv()` calls
by buffering until a newline is seen.

Inside `_stream_worker`, when an SSE chunk's decoded JSON contains an `"usage"` key, the worker MUST call `wx.CallAfter(on_usage, chunk["usage"])` IF `on_usage is not None`. The absence of a `"usage"` key in any chunk MUST be silent (no error, no callback). The original `on_token` / `on_done` / `on_error` contract, the daemon thread, the SSE parser, the abort event, and the body shape are unchanged.
**Rationale**: Token-by-token streaming is required for responsive speech
synthesis; SSE is the only transport the OpenAI-compatible endpoint exposes.
The optional `on_usage` callback allows the UI to capture and display token-usage statistics reported by `llama-server` in the final SSE chunk.
**Decision locked**: the client itself invokes `wx.CallAfter` (importing `wx`
inside the worker function only) — this mirrors the existing
`OllamaClient` pattern and keeps the orchestrator simple.

- GIVEN a stubbed stream that yields two SSE events followed by `[DONE]`
- WHEN `chat_stream(...)` is called with a fake `wx.CallAfter` that records calls
- THEN exactly two `CallAfter` invocations to `on_token` are recorded
- AND one `CallAfter` invocation to `on_done` is recorded
- AND no `CallAfter` invocation to `on_error` is recorded

- GIVEN a stubbed stream whose final SSE event is `{"usage": {"prompt_tokens": 12, "completion_tokens": 80, "total_tokens": 92}}`
- AND `on_usage` is a fake recording function
- WHEN `chat_stream(..., on_usage=on_usage)` is called
- THEN `on_usage` is invoked exactly once
- AND the argument is the dict `{"prompt_tokens": 12, "completion_tokens": 80, "total_tokens": 92}`
- AND the invocation is wrapped in `wx.CallAfter`

- GIVEN a `requests.post` that raises `ConnectionError`
- WHEN `chat_stream(...)` is called
- THEN `on_error` receives a string containing `"ConnectionError"`
- AND `on_done` is NOT invoked

- GIVEN options `{"temperature": 0.7, "num_predict": 256, "top_p": 0.9, "top_k": 40, "repeat_penalty": 1.1}`
- WHEN `chat_stream` builds the request body
- THEN the body contains `temperature=0.7`, `top_p=0.9`, `top_k=40`, `repeat_penalty=1.1`, `max_tokens=256`
- AND the body contains `"model": "local"`
- AND the body contains `"stream": true`
- AND the body contains `messages` verbatim
- AND the body does NOT contain an `options` sub-object

- GIVEN a stubbed stream that yields `data: {not json}` then a valid event then `[DONE]`
- WHEN the stream is parsed
- THEN the malformed line is skipped without raising
- AND the valid event's token is forwarded

- GIVEN a stubbed stream whose bytes arrive in two `recv()` chunks that split a single SSE line
- WHEN the stream is parsed
- THEN the line is reassembled and the token is forwarded

- GIVEN a stream that yields no `"usage"` key in any chunk
- AND `on_usage` is `None`
- WHEN `chat_stream(...)` is called
- THEN no exception is raised
- AND `on_token` and `on_done` are invoked as before

- GIVEN `chat_stream(messages, options, on_token, on_done, on_error)` is called WITHOUT `on_usage`
- WHEN the stream yields a usage chunk
- THEN no `TypeError` is raised
- AND the stream completes normally

### REQ-LLAMA-004: Abort an in-flight stream
**Statement**: `LlamaClient.abort()` MUST set an internal `threading.Event`
that the streaming loop checks between SSE chunks (not between bytes). When
the event is set, the loop MUST exit cleanly, invoke `on_done` (not
`on_error`), and not invoke any further `on_token` callbacks. Calling `abort()`
when no stream is running MUST be a no-op.
**Rationale**: The "Detener" button must stop generation within one token of
the user pressing it; abort between chunks keeps the boundary atomic.

- GIVEN a stubbed stream that yields 100 tokens slowly and the client is running
- WHEN `abort()` is called after 3 tokens have been received
- THEN at most 3 `on_token` callbacks fire
- AND `on_done` is invoked exactly once
- AND `on_error` is NOT invoked

- GIVEN no stream is running
- WHEN `abort()` is called
- THEN no exception is raised
- AND no callback is invoked

### REQ-LLAMA-005: Find llama-server executable
**Statement**: `LlamaRunner.find_llama_server()` MUST return the absolute
path to the `llama-server` binary (or `llama-server.exe` on Windows) as a
string if it can be located via the `PATH` environment variable or in any
well-known install location the runner knows about; otherwise it MUST return
`None` without raising.
**Rationale**: The app needs to know whether to show the install dialog
or the normal startup flow.

- GIVEN `PATH` contains a directory holding `llama-server.exe`
- WHEN `find_llama_server()` is called on Windows
- THEN it returns the absolute path to that executable

- GIVEN `llama-server` is not in `PATH` and no fallback directory contains it
- WHEN `find_llama_server()` is called
- THEN it returns `None` and does not raise

### REQ-LLAMA-006: Find .gguf models on disk
**Statement**: `LlamaRunner.find_gguf_models(extra_paths: list[str] | None = None) -> list[str]`
MUST scan the standard Windows model locations (`%USERPROFILE%\models\`,
`%USERPROFILE%\Downloads\`, `%USERPROFILE%\.cache\huggingface\hub\` recursive
to depth 5, `%USERPROFILE%\.lmstudio\models\`, and `%LOCALAPPDATA%\nomic.ai\GPT4All\`)
plus any paths in `extra_paths`, and return a list of absolute paths to
`.gguf` files sorted by basename (ascending). Directories that do not exist
MUST be skipped silently. Files with any extension other than `.gguf` MUST
be ignored. On non-Windows platforms (e.g. WSL Ubuntu), the function MUST
return `[]` because the standard Windows paths are absent; the function
remains wx-free and platform-aware via `os.name`.
**Rationale**: The ComboBox model selector must show the user's installed
`.gguf` files; the app cannot ask the server for a list of files on disk.

- GIVEN a directory `C:\Users\me\models\` containing `b.gguf`, `a.gguf`, and `c.safetensors`
- WHEN `find_gguf_models()` is called on Windows
- THEN it returns `[".../models/a.gguf", ".../models/b.gguf"]`
- AND the `.safetensors` file is excluded

- GIVEN none of the standard paths exist
- WHEN `find_gguf_models()` is called
- THEN it returns `[]` and does not raise

- GIVEN `extra_paths=["D:\\llms"]` and that directory contains `phi-3.gguf`
- WHEN `find_gguf_models(extra_paths=["D:\\llms"])` is called
- THEN the returned list includes the absolute path to `phi-3.gguf`

- GIVEN the current OS is `posix` (Linux/WSL)
- WHEN `find_gguf_models()` is called
- THEN it returns `[]` and does not raise

### REQ-LLAMA-007: Start llama-server with a model
**Statement**: `LlamaRunner.start_server(model_path, client, port=8080, ctx_size=4096, n_gpu_layers=99, timeout=60.0) -> tuple[bool, str]`
MUST (1) call `stop_server()` if a process is already tracked, (2) call
`client.check_running()` and return `(True, "...ya está corriendo...")` if the
server already responds without spawning a new process, (3) spawn
`llama-server --model {model_path} --port {port} --host 127.0.0.1 --ctx-size {ctx_size} --n-gpu-layers {n_gpu_layers} --jinja`
via `subprocess.Popen` with `stdout=DEVNULL`, `stderr=DEVNULL`, `stdin=DEVNULL`,
and on Windows `creationflags=CREATE_NO_WINDOW`, (4) poll `client.check_running()`
every 0.2 seconds for up to `timeout` seconds, and (5) return `(True, "<ready>")`
on success or `(False, "<reason>")` on `FileNotFoundError`, `OSError`, or
timeout. The PID of the spawned process MUST be tracked at module scope for
`stop_server()`.
**Rationale**: Large `.gguf` files take 10-60 seconds to load; blind users
need a clear "loading" voice announcement and a deterministic timeout.

- GIVEN `client.check_running()` returns `True` before any spawn
- WHEN `start_server(...)` is called
- THEN it returns `(True, "...ya está corriendo...")`
- AND `subprocess.Popen` is NOT called

- GIVEN a valid `model_path` and a stubbed `check_running` that returns `True` after 3 polls
- WHEN `start_server(...)` is called
- THEN it returns `(True, "<ready>")`
- AND `subprocess.Popen` was called once with the documented argv
- AND on Windows the call included `creationflags=CREATE_NO_WINDOW`

- GIVEN `check_running` always returns `False`
- WHEN `start_server(..., timeout=1.0)` is called
- THEN it returns `(False, ...)` and the message contains a timeout indicator

- GIVEN a previous `start_server` succeeded and a second `start_server` is called with a new `model_path`
- WHEN the second call runs
- THEN `stop_server()` runs first (the old process is terminated) before the new Popen

### REQ-LLAMA-008: Stop llama-server
**Statement**: `LlamaRunner.stop_server()` MUST send a terminate signal to the
tracked subprocess if one is running, wait up to 5 seconds for graceful
shutdown, fall back to a hard kill if termination does not complete in that
window, clear the tracked PID, and be idempotent (a no-op when no process is
tracked). On Linux, terminate uses `SIGTERM` then `SIGKILL`; on Windows, it
uses `process.terminate()` then `process.kill()`.
**Rationale**: A running `llama-server` holds VRAM; the user must be able to
free it without killing the app.

- GIVEN a tracked subprocess that exits within 1 second of `terminate()`
- WHEN `stop_server()` is called
- THEN the process terminates gracefully
- AND no `kill` is required
- AND the tracked PID is cleared

- GIVEN a tracked subprocess that ignores `terminate()`
- WHEN `stop_server()` is called
- THEN after 5 seconds `kill()` is invoked
- AND the tracked PID is cleared

- GIVEN no tracked subprocess
- WHEN `stop_server()` is called
- THEN no exception is raised and the call is a no-op

### REQ-LLAMA-009: Provide the install command
**Statement**: `LlamaRunner.get_install_command()` MUST return the exact
string `"winget install ggml.llamacpp"`. The result MUST be stable across
calls and platform-independent.
**Rationale**: The "not installed" dialog must show the user a single
copy-pasteable install command, which NVDA will read verbatim.

- GIVEN any call
- WHEN `get_install_command()` is invoked
- THEN it returns the string `"winget install ggml.llamacpp"`

### REQ-LLAMA-010: Model selector UX (accessibility)
**Statement**: `params_panel` MUST expose the model selector as a
`wx.ComboBox` (NOT `wx.Choice`) with `name="model_selector"`, immediately
preceded in the sizer by a `wx.StaticText` labelled `"Modelo (.gguf):"`.
The ComboBox MUST display only the basename of each `.gguf` file; the
mapping from basename to absolute path MUST be stored internally in
`self._basename_to_path: dict[str, str]`. `get_model()` MUST return the
full absolute path of the selected model (or the user-typed path verbatim
if the user typed a full path). `set_models(paths: list[str])` MUST accept
absolute paths and repopulate the ComboBox with their basenames. The panel
MUST also include:
- a "Buscar modelos" button with `name="scan_models_button"` that calls
  `LlamaRunner.find_gguf_models()` and announces the resulting count by
  voice (`"N modelos encontrados"`);
- an "Explorar..." button with `name="browse_model_button"` that opens a
  `wx.FileDialog` with wildcard `*.gguf` and stores the chosen path.

Manual path entry in the ComboBox MUST be resolvable to a full path: if the
user types a basename that exists in `_basename_to_path`, that path is used;
if the user types a full path that exists on disk, that path is used as-is.
**Rationale**: ComboBox allows type-ahead for blind users who cannot browse
a dropdown; basenames keep the spoken list short; the full path is needed
at the call site to spawn the server.

- GIVEN `set_models(["C:\\models\\a.gguf", "C:\\models\\b.gguf"])` is called
- WHEN the ComboBox is inspected
- THEN it contains the strings `"a.gguf"` and `"b.gguf"`
- AND `self._basename_to_path == {"a.gguf": "C:\\models\\a.gguf", "b.gguf": "C:\\models\\b.gguf"}`

- GIVEN the ComboBox selection is `"a.gguf"`
- WHEN `get_model()` is called
- THEN it returns `"C:\\models\\a.gguf"`

- GIVEN the StaticText label is `"Modelo (.gguf):"` and the ComboBox has `name="model_selector"`
- WHEN the panel is rendered
- THEN the StaticText immediately precedes the ComboBox in the sizer
- AND MSAA exposes the StaticText as the accessible name for the ComboBox

- GIVEN the user types a basename that exists in `_basename_to_path`
- WHEN `get_model()` is called
- THEN it returns the mapped full path

- GIVEN the user types a full path that exists on disk
- WHEN `get_model()` is called
- THEN it returns the typed full path verbatim

- GIVEN the "Buscar modelos" button is pressed
- WHEN the handler runs
- THEN `LlamaRunner.find_gguf_models()` is called
- AND the ComboBox is repopulated
- AND the speech engine announces `"N modelos encontrados"` with the new count

### REQ-LLAMA-011: Server start/stop button UX (accessibility)
**Statement**: `main_window` MUST include two toolbar buttons with the
following labels, names, and behaviour:
- `"Iniciar servidor"` with `name="start_server_button"` — calls
  `LlamaRunner.start_server(model_path, client)` with the current model from
  `params_panel.get_model()`; MUST be disabled while a start is in progress.
- `"Detener servidor"` with `name="stop_server_button"` — calls
  `LlamaRunner.stop_server()`; MUST be disabled when the server is not
  running.

Each button MUST have a preceding `wx.StaticText` label (or be inside a
labelled toolbar group) so MSAA exposes the action. Both buttons MUST
announce their state transitions by voice (`"Iniciando servidor..."`,
`"Servidor listo"`, `"Deteniendo servidor..."`, `"Servidor detenido"`).
**Rationale**: A blind user has no way to discover server state from an
icon; the buttons themselves are the source of truth and MUST speak.

- GIVEN no server is running
- WHEN the toolbar is rendered
- THEN `start_server_button` is enabled
- AND `stop_server_button` is disabled

- GIVEN the user clicks `start_server_button` and the server is not already up
- WHEN the click handler runs
- THEN `LlamaRunner.start_server(...)` is called with the path from `params_panel.get_model()`
- AND `start_server_button` becomes disabled
- AND the speech engine announces `"Iniciando servidor..."`

- GIVEN a server is running
- WHEN the user clicks `stop_server_button`
- THEN `LlamaRunner.stop_server()` is called
- AND the speech engine announces `"Deteniendo servidor..."` then `"Servidor detenido"`
- AND `start_server_button` becomes enabled
- AND `stop_server_button` becomes disabled

### REQ-LLAMA-012: Three server states
**Statement**: At startup, `main_window` MUST classify the system into one
of three states and announce the state by voice (and write a parallel
status-bar message):

| State | Detection | Voice announcement | Status bar (field 0) |
|-------|-----------|--------------------|----------------------|
| Not installed | `LlamaRunner.find_llama_server() is None` | `"llama-server no instalado. Instalalo con: winget install ggml.llamacpp."` | shows the same text |
| Stopped | `find_llama_server()` found but `check_running()` is `False` | `"Servidor detenido. Seleccioná un modelo y pulsá Iniciar servidor."` | `"Servidor detenido"` |
| Running | `check_running()` is `True` | `"Conectado. Modelo cargado: <basename>."` | `"Conectado: <basename>"` |

The "Not installed" state MUST additionally open a `wx.MessageDialog` with
the install command so the user has a copy-pasteable reference. Voice
announcements are emitted exactly once at startup for the detected state;
no further announcements happen until the state changes.
**Rationale**: The three states cover the entire lifecycle; blind users
must hear the current state explicitly because they cannot see the
status bar.

- GIVEN `find_llama_server()` returns `None` at startup
- WHEN `main_window` initialises
- THEN the speech engine announces the "no instalado" message
- AND a `wx.MessageDialog` is shown with the install command

- GIVEN `find_llama_server()` returns a path and `check_running()` returns `False`
- WHEN `main_window` initialises
- THEN the speech engine announces the "Servidor detenido" message
- AND the status bar (field 0) reads `"Servidor detenido"`
- AND no dialog is shown

- GIVEN `check_running()` returns `True` and `get_loaded_model()` returns `"phi-3.gguf"`
- WHEN `main_window` initialises
- THEN the speech engine announces `"Conectado. Modelo cargado: phi-3.gguf."`
- AND the status bar (field 0) reads `"Conectado: phi-3.gguf"`

### REQ-LLAMA-013: Image attachments preserved
**Statement**: Image-bearing messages MUST be encoded in the OpenAI
content-array format and forwarded to `LlamaClient.chat_stream` as-is.
Specifically, when a user message has one or more attached images, the
`chat_panel` MUST construct a message dict whose `content` is a list of
parts: `{"type": "text", "text": "..."}` for the user text followed by one
`{"type": "image_url", "image_url": {"url": "data:image/<mime>;base64,<data>"}}`
block per image. The `<mime>` is `jpeg` or `png` (or `image/<mime>` matching
the actual encoding). Messages without images MUST remain plain strings (or
single-part text content) — the previous Ollama `images=...` key is
removed and MUST NOT appear in the outgoing body.
**Rationale**: llama.cpp's multimodal support uses the OpenAI image-url
format; dropping images would be a regression of an existing user flow.

- GIVEN a user message with one attached JPEG image (base64 `iVBOR...`)
- WHEN `chat_panel` builds the message dict
- THEN the message is
  `{"role": "user", "content": [{"type": "text", "text": "..."}, {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,iVBOR..."}}]}`
- AND no top-level `images` key is present

- GIVEN `LlamaClient.chat_stream` receives a messages list containing the above message
- WHEN the POST body is built
- THEN the `content` array is forwarded verbatim (no reshaping)
- AND the request body has no `images` key at any level

### REQ-LLAMA-014: Threading and wx.CallAfter contract
**Statement**: All public callbacks from `LlamaClient` (`on_token`, `on_done`,
`on_error`) MUST be invoked via `wx.CallAfter` so they run on the wx main
thread. The implementation MUST import `wx` only inside the worker function
(never at module level) so that `core/llama_client.py` remains importable on
systems without wxPython (e.g. CI / WSL). The streaming network I/O MUST run
on a per-request `threading.Thread` with `daemon=True`. The abort event MUST
be checked between SSE chunks, never between bytes.
**Rationale**: The `core/` layer must stay headless-testable on WSL while
still delivering callbacks safely to the wx main thread on Windows.

- GIVEN the streaming worker is emitting a token
- WHEN the worker invokes the callback
- THEN the call shape is `wx.CallAfter(on_token, token)`
- AND `wx` is imported inside the worker function (verified by AST check that
  the module-level imports do NOT include `wx`)

- GIVEN a slow stubbed stream is being processed
- WHEN `abort()` is called
- THEN the worker checks the event only after a full SSE line has been
  parsed, not inside `recv()`

### REQ-LLAMA-015: Encoding and Python 3.12
**Statement**: All file reads and writes performed by `LlamaRunner` and
`LlamaClient` (e.g. reading model directory listings or persisting install
hints) MUST use explicit `encoding="utf-8"`. The implementation MUST NOT
use Python 3.13+ syntax (e.g. the `type` PEP 695 statement, PEP 742
`TypeIs`, PEP 695 generic syntax). The package MUST be compatible with
`requires-python = ">=3.12"`.
**Rationale**: WSL runs Python 3.12; the project pins `>=3.12` in
`pyproject.toml`; silent syntax upgrades would break CI on the dev box.

- GIVEN the project is installed with `requires-python = ">=3.12"`
- WHEN `uv run --no-sync pytest -xvs` runs
- THEN no `SyntaxError` or `ImportError` is raised

### REQ-LLAMA-016: Test coverage contract
**Statement**: The new test files `tests/core/test_llama_client.py` and
`tests/core/test_llama_runner.py` MUST mirror the mocking patterns from
the archived `test_ollama_client.py` / `test_ollama_runner.py`:
- `mock_session` fixture built on `Mock(spec=requests.Session)` for the
  client;
- `mock_call_after` fixture that replaces `wx.CallAfter` with a
  record-and-invoke fake (autouse `ensure_wx` fixture that materialises a
  fake `wx` module);
- `time.sleep(0.1)` after `chat_stream(...)` to let the daemon thread
  finish;
- `patch("ollamachat.core.llama_runner.subprocess.Popen")` for the runner.

Coverage minima:
- Every public method of `LlamaClient` has at least 3 tests (happy path,
  error path, edge case);
- Every public function of `LlamaRunner` has at least 2 tests (happy path
  + error/edge case);
- The SSE parser has dedicated tests for: normal `data:` lines, the
  `data: [DONE]` terminator, blank lines, partial chunks, malformed JSON;
- `find_gguf_models` has tests for: empty directory, mixed extensions,
  missing standard paths, recursive depth limit, `extra_paths` parameter;
- `start_server` has tests for: already-running case (no duplicate
  Popen), `Popen` failure case, timeout case (mocked).

**Rationale**: Strict TDD is active (`openspec/config.yaml`); the
replacement must keep the same testing rigor as the archived code.

- GIVEN the new `test_llama_client.py` is run
- WHEN pytest finishes
- THEN every public method of `LlamaClient` has at least 3 passing tests
- AND the SSE parser has dedicated tests for `[DONE]`, partial chunks, and malformed JSON

- GIVEN the new `test_llama_runner.py` is run
- WHEN pytest finishes
- THEN `start_server` has tests for the "already running" path, the
  Popen-failure path, and the timeout path
- AND `find_gguf_models` has tests covering all five scenarios in the
  statement above
