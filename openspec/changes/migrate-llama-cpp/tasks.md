# Tasks: migrate-llama-cpp

> **TDD discipline:** every implementation task in Phase 1 and Phase 2 is preceded by a test task. Test must be written, run (red), then implementation is added (green). Phases 3-5 are UI work covered by AST checks; no test-first TDD there, but the AST static checks must pass at the end of each phase.

> **Order constraint:** the deletion of old Ollama files (Phase 6) MUST be the last code change. Until then, old and new modules coexist so tests stay green at every step.

## Phase 0 — Setup (no code yet)

- [x] **0.1** Create `ollamachat/core/llama_client.py` with module docstring, top-level imports (`json`, `threading`, `typing`, `requests`), and a `LlamaClient` class skeleton (`__init__` only, with `base_url`, `session`, `_stop_event`, `_stream_thread`). All public methods stubbed to return safe defaults.
- [x] **0.2** Create `ollamachat/core/llama_runner.py` with module docstring, top-level imports (`subprocess`, `sys`, `os`, `time`, `pathlib`, `threading`), and module-level `_server_process: subprocess.Popen | None = None` plus `_lock = threading.Lock()`. All public functions stubbed to return safe defaults.
- [x] **0.3** Create `tests/core/test_llama_client.py` with the `ensure_wx` autouse fixture (copied from archived `test_ollama_client.py`), `mock_session` and `mock_call_after` fixtures, and an empty test class `TestLlamaClient`.

## Phase 1 — `core/llama_client.py` (TDD)

### REQ-LLAMA-001: Health check

- [x] **1.1** Add `test_check_running_returns_true_on_200_ok`: stub `GET /health` to return 200 with `{"status": "ok"}`, assert `LlamaClient(...).check_running() is True`. **Verify red.**
- [x] **1.2** Add `test_check_running_returns_false_on_connection_error`: stub `GET /health` to raise `ConnectionError`, assert `False`. **Verify red.**
- [x] **1.3** Add `test_check_running_returns_false_on_503`: stub `GET /health` to return 503, assert `False`. **Verify red.**
- [x] **1.4** Add `test_check_running_returns_false_on_timeout`: stub `GET /health` to raise `requests.exceptions.Timeout`, assert `False`. **Verify red.**
- [x] **1.5** Implement `LlamaClient.check_running` (GET `{base_url}/health` with timeout=5, return `status_code == 200` and `body["status"] == "ok"`; any exception returns False). **Verify green.**

### REQ-LLAMA-002: Loaded model

- [x] **1.6** Add `test_get_loaded_model_returns_id`: stub `GET /v1/models` to return 200 with `{"data": [{"id": "llama-3.1-8b-q4.gguf"}]}`, assert returned string is `"llama-3.1-8b-q4.gguf"`. **Verify red.**
- [x] **1.7** Add `test_get_loaded_model_returns_empty_on_error`: stub to raise `ConnectionError`, assert `""`. **Verify red.**
- [x] **1.8** Implement `LlamaClient.get_loaded_model` (GET `{base_url}/v1/models`, parse `data[0]["id"]`, return `""` on any error). **Verify green.**

### REQ-LLAMA-003 + REQ-LLAMA-014: Streaming chat (SSE + threading + CallAfter)

- [x] **1.9** Add `test_chat_stream_two_events_then_done`: stub `POST /v1/chat/completions` to yield two valid SSE events followed by `data: [DONE]`; assert exactly 2 `on_token` and 1 `on_done` invocations via the fake `CallAfter`, 0 `on_error`. **Verify red.**
- [x] **1.10** Add `test_chat_stream_post_raises_invokes_on_error`: stub `requests.Session.post` to raise `ConnectionError`; assert `on_error` called with a string containing `"ConnectionError"`; `on_done` NOT called. **Verify red.**
- [x] **1.11** Add `test_chat_stream_request_body_shape`: capture the `json=` kwarg of `POST`; assert it has `model="local"`, `stream=True`, `messages` verbatim, `temperature`, `top_p`, `top_k`, `repeat_penalty`, `max_tokens` (derived from `options["num_predict"]`), and NO `options` sub-object. **Verify red.**
- [x] **1.12** Add `test_chat_stream_skips_malformed_json`: yield `data: {not json}`, then a valid event, then `data: [DONE]`; assert the valid event is forwarded and no exception escapes. **Verify red.**
- [x] **1.13** Add `test_chat_stream_handles_partial_chunks`: configure the fake `iter_lines` to yield two pieces that, when concatenated, form a single SSE line; assert the token is forwarded exactly once. **Verify red.**
- [x] **1.14** Implement `LlamaClient.chat_stream` and `_stream_worker`. The worker imports `wx` locally, builds the body per the spec, posts with `stream=True, timeout=60`, iterates lines, dispatches via `wx.CallAfter`, and handles abort. **Verify green.**

### REQ-LLAMA-004: Abort

- [x] **1.15** Add `test_abort_stops_stream_between_chunks`: stub stream to yield 100 tokens slowly; call `abort()` after the third token is observed; assert at most 3 `on_token` calls, exactly 1 `on_done`, 0 `on_error`. **Verify red.**
- [x] **1.16** Add `test_abort_is_noop_when_idle`: call `abort()` on a fresh client; assert no exception and no callback. **Verify red.**
- [x] **1.17** Implement `LlamaClient.abort` (sets `self._stop_event`). **Verify green.**

### Module-level check

- [x] **1.18** Run `grep -n '^import wx\|^from wx' ollamachat/core/llama_client.py` and assert zero matches at module level. The wx import must live inside `_stream_worker` only.

## Phase 2 — `core/llama_runner.py` (TDD)

### REQ-LLAMA-005: Find llama-server

- [x] **2.1** Add `test_find_llama_server_found_in_path`: monkeypatch `shutil.which` to return a path; assert `find_llama_server()` returns it. **Verify red.**
- [x] **2.2** Add `test_find_llama_server_returns_none`: monkeypatch `shutil.which` to return `None`; assert `find_llama_server()` returns `None`. **Verify red.**
- [x] **2.3** Implement `find_llama_server` (use `shutil.which("llama-server")`, resolve to absolute path, return `None` if not found). **Verify green.**

### REQ-LLAMA-006: Find .gguf models

- [x] **2.4** Add `test_find_gguf_models_filters_extensions`: create a tempdir with `a.gguf`, `b.gguf`, `c.safetensors`; call `find_gguf_models(extra_paths=[str(tempdir)])`; assert the two `.gguf` files are returned sorted by basename, the `.safetensors` is excluded. **Verify red.**
- [x] **2.5** Add `test_find_gguf_models_skips_nonexistent_dirs`: pass `extra_paths=["/does/not/exist"]`; assert `[]` and no exception. **Verify red.**
- [x] **2.6** Add `test_find_gguf_models_extra_paths`: tempdir with `phi-3.gguf`; assert it appears in the result. **Verify red.**
- [x] **2.7** Add `test_find_gguf_models_non_windows_returns_empty`: monkeypatch `os.name = "posix"`; assert `find_gguf_models()` returns `[]` even with `extra_paths` containing a real `.gguf` (on non-Windows, extra_paths is also skipped to keep behavior deterministic in CI; or alternatively scanned — pick one and document in the test name).
- [x] **2.8** Add `test_find_gguf_models_respects_recursive_depth`: build a fake HF cache tree with `.gguf` files at depths 1, 3, 5, and 7; assert only the files at depth <= 5 are returned. **Verify red.**
- [x] **2.9** Implement `find_gguf_models` per the design (5 standard Windows paths + `extra_paths`; depth-5 cap on the HF cache; sort by basename; dedupe). **Verify green.**

### REQ-LLAMA-009: Install command

- [x] **2.10** Add `test_get_install_command_returns_literal`: assert the function returns exactly `"winget install ggml.llamacpp"`. **Verify red.**
- [x] **2.11** Implement `get_install_command` (return the literal). **Verify green.**

### REQ-LLAMA-007: Start server

- [x] **2.12** Add `test_start_server_already_running_no_popen`: client `check_running` returns `True`; assert `start_server(...)` returns `(True, "ya está...")` and `subprocess.Popen` is NOT called. **Verify red.**
- [x] **2.13** Add `test_start_server_spawns_with_documented_argv`: assert `Popen` is called with the argv list exactly as specified in design §5. **Verify red.**
- [x] **2.14** Add `test_start_server_success_after_3_polls`: `check_running` returns `False, False, False, True`; assert `(True, "Servidor listo")` and Popen was called once. **Verify red.**
- [x] **2.15** Add `test_start_server_timeout`: `check_running` always `False`; assert `(False, "...timeout...")`. **Verify red.**
- [x] **2.16** Add `test_start_server_popen_failure`: `Popen` raises `FileNotFoundError`; assert `(False, "...no se encontró...")`. **Verify red.**
- [x] **2.17** Add `test_start_server_stops_before_respawning`: simulate a previously-spawned process that is alive; call `start_server` again with a new `model_path`; assert `terminate()` was called on the old Popen before the new `Popen(...)` call. **Verify red.**
- [x] **2.18** Implement `start_server` per the design (lock, stop-then-spawn, fast-path, poll at 0.2s, timeout=60 default). **Verify green.**

### REQ-LLAMA-008: Stop server

- [x] **2.19** Add `test_stop_server_graceful_exit`: tracked process exits within 1s of `terminate()`; assert `kill()` is NOT called and the process handle is cleared. **Verify red.**
- [x] **2.20** Add `test_stop_server_kill_fallback`: tracked process ignores `terminate()`; assert `kill()` is called within 5s and the handle is cleared. **Verify red.**
- [x] **2.21** Add `test_stop_server_no_op_when_idle`: no tracked process; assert no exception. **Verify red.**
- [x] **2.22** Implement `stop_server` per the design. **Verify green.**

### Module-level check

- [x] **2.23** Run `grep -n '^import wx\|^from wx' ollamachat/core/llama_runner.py` and assert zero matches.

## Phase 3 — `ui/params_panel.py`

- [x] **3.1** Update `tests/ui/test_params_panel_static.py`: add an AST assertion that `scan_models_button` and `browse_model_button` are present, and that `refresh_models_button` is NOT present in the source.
- [x] **3.2** Replace `wx.Choice` with `wx.ComboBox` (name `model_selector` preserved). Update the StaticText label to `"Modelo (.gguf):"`.
- [x] **3.3** Add `scan_models_button` (label `"Buscar modelos"`, name `"scan_models_button"`).
- [x] **3.4** Add `browse_model_button` (label `"Explorar..."`, name `"browse_model_button"`).
- [x] **3.5** Add `self._basename_to_path: dict[str, str] = {}` in `__init__`.
- [x] **3.6** Rewrite `set_models(paths)` to store basenames in the ComboBox and full paths in `_basename_to_path`.
- [x] **3.7** Rewrite `get_model()` to apply the three-rule resolution (basename lookup → typed-path validation → empty).
- [x] **3.8** Update `get_params()` to return `"max_tokens"` (renamed from `"num_predict"`).
- [x] **3.9** Run `uv run --no-sync pytest tests/ui/test_params_panel_static.py -xvs` to verify AST checks pass.

## Phase 4 — `ui/chat_panel.py`

- [x] **4.1** Change `self._attached_images: list[str]` to `self._attached_images: list[tuple[str, str]]` (b64, mime).
- [x] **4.2** Update `attach_file` to record the MIME based on the file extension (`jpg/jpeg → image/jpeg`, `png → image/png`, `bmp/gif → image/bmp` or `image/gif`).
- [x] **4.3** Update `get_attached_images` to return `list[tuple[str, str]]`.
- [x] **4.4** Run `uv run --no-sync pytest tests/ui/test_chat_panel_static.py -xvs` to verify AST checks still pass with the new tuple shape.

## Phase 5 — `ui/main_window.py`

- [x] **5.1** Update imports: `OllamaClient` → `LlamaClient`; `start_ollama` → `start_server, stop_server, find_gguf_models, find_llama_server, get_install_command`.
- [x] **5.2** Update `_build_ui`: rename `start_ollama_button` → `start_server_button` with new label `"Iniciar servidor"`.
- [x] **5.3** Add `stop_server_button` (label `"Detener servidor"`, name `"stop_server_button"`, initially disabled).
- [x] **5.4** Update toolbar sizer: StaticText + start + stop in a horizontal BoxSizer.
- [x] **5.5** Replace `_startup_check` with the three-state version per design §7.
- [x] **5.6** Replace `_refresh_models` with `_scan_models` per design §7.
- [x] **5.7** Replace `_on_start_ollama` with `_on_start_server` per design §7. Wire `start_server_button` to the new handler. Disable `start_server_button` while starting; enable it back on success/failure.
- [x] **5.8** Add `_on_stop_server`: speak `"Deteniendo servidor..."`, call `stop_server()`, on return speak `"Servidor detenido"`, toggle button states.
- [x] **5.9** Update `send_message`: drop `model=` kwarg; build OpenAI content-array when images are attached (per design §8). Use the new `list[tuple[str, str]]` shape from `get_attached_images`.
- [x] **5.10** Add `_on_close` handler that calls `stop_server()`. Bind it with `self.Bind(wx.EVT_CLOSE, self._on_close)`.
- [x] **5.11** Update `tests/ui/test_main_window_static.py` if its AST checks look for `start_ollama_button` (replace with `start_server_button`).
- [x] **5.12** Run `uv run --no-sync pytest tests/ui/ -xvs` to verify all UI AST checks pass.

## Phase 6 — Cleanup (last code change)

- [x] **6.1** Delete `ollamachat/core/ollama_client.py`.
- [x] **6.2** Delete `ollamachat/core/ollama_runner.py`.
- [x] **6.3** Delete `tests/core/test_ollama_client.py`.
- [x] **6.4** Delete `tests/core/test_ollama_runner.py`.
- [x] **6.5** Run `uv run --no-sync pytest -xvs` to confirm the full suite passes without the old files.

## Phase 7 — Verify + release

- [x] **7.1** Bump version in `pyproject.toml` from `0.1.1` to `0.2.0`.
- [x] **7.2** Add a `[0.2.0]` entry at the top of `CHANGELOG.md` summarizing the backend swap.
- [-] **7.3** (Windows-only) Run `scripts/build_windows.sh` to produce the dist kit.
- [-] **7.4** (Windows-only) Manual verification — 4 tasks:
  - Install `llama-server` via `winget install ggml.llamacpp`.
  - Start the app, point at a real `.gguf`, start the server, send a message, verify streaming.
  - Switch the model via the ComboBox, click "Iniciar servidor" again, verify the restart.
  - Click "Detener servidor", verify the process exits and the start button is re-enabled.

## Review workload forecast

- **Estimated changed lines:** ~1,130 (rough breakdown below).
  - `core/llama_client.py`: NEW, ~180 lines
  - `core/llama_runner.py`: NEW, ~150 lines
  - `tests/core/test_llama_client.py`: NEW, ~280 lines
  - `tests/core/test_llama_runner.py`: NEW, ~280 lines
  - `ui/params_panel.py`: ~80 lines changed
  - `ui/chat_panel.py`: ~25 lines changed
  - `ui/main_window.py`: ~120 lines changed
  - `tests/ui/test_*_static.py`: ~10 lines changed
  - `pyproject.toml`: 1 line changed
  - `CHANGELOG.md`: ~10 lines added
  - `core/ollama_client.py`, `core/ollama_runner.py`, `tests/core/test_ollama_client.py`, `tests/core/test_ollama_runner.py`: DELETED (~ −700 lines)
  - **Net diff:** ~+430 / −700, totaling **~1,130 lines of diff**
- **`review_budget_lines: 400` from `openspec/config.yaml`.** The change **exceeds** the budget by ~2.8x.
- **Decision (2026-06-22, user):** `size:exception` granted. Apply proceeds on `main` with work-unit commits per the plan below. No branches, no worktrees, no chained PRs — every commit lands directly on `main`.

## Work unit commits

Suggested commit slices (each must leave the test suite green except for the explicit "delete" commit):

1. **"test: scaffold llama_client + llama_runner test files"** — Phase 0 + skeleton test files; old tests still pass.
2. **"feat(core): add LlamaClient with health check, model listing, and SSE streaming"** — Phase 1 tests + impl.
3. **"feat(core): add LlamaRunner with find/start/stop and gguf discovery"** — Phase 2 tests + impl.
4. **"feat(ui): params_panel uses ComboBox + scan/explore buttons"** — Phase 3.
5. **"feat(ui): chat_panel tracks image MIME for OpenAI content-array"** — Phase 4.
6. **"feat(ui): main_window three-state startup, start/stop toolbar, image content-array"** — Phase 5.
7. **"refactor: delete ollama_client/ollama_runner modules and their tests"** — Phase 6 (intentionally leaves suite red at HEAD before tests re-run).
8. **"chore: bump version to 0.2.0 and update CHANGELOG"** — Phase 7 (no code change).

## Skill resolution

- `paths-injected` — `sdd-tasks` and `_shared` were loaded from `/home/ic_ma/.config/opencode/skills/` per orchestrator injection.
