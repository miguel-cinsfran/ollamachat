# Tasks: Context Advisor + Toggleable F2 Status (v0.9.0)

## Budget forecast

| Work Unit | Estimated lines | Budget risk |
|-----------|----------------|-------------|
| WU-1 (core + tests, WSL) | ~700-900 | **High** — exceeds 800 |
| WU-2 (UI + wx tests) | ~600-800 | **High** — approaches 800 |
| Total | ~1300-1700 | Both exceed 800 individually |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: size-exception
400-line budget risk: High

**Requires `size:exception` per `openspec/config.yaml` rules** (delivery.review_budget_lines: 800). Both WU-1 and WU-2 individually exceed the review budget. The 2-commit split (WU-1 → WU-2) is formalized in the design §5 and keeps each diff navigable.

Two sequential commits on `main`. No branches.

---

## WU-1: core + tests (WSL)

**~700-900 lines | strict TDD in `core/`**

All tasks in WU-1 run `uv run --no-sync pytest -xvs` on WSL. No wx imports.

- [x] T-WU1-01 — Add `read_gguf_metadata` + `estimate_size_bytes` to `core/model_meta.py`
  - **Files**: `bellbird/core/model_meta.py` (extend), `tests/core/test_model_meta.py` (extend)
  - **Acceptance**: `read_gguf_metadata(path) → GGUFMetadata | None`. Line-local `import gguf` inside function. Returns `None` on `ImportError` / `FileNotFoundError` / corrupt file. `estimate_size_bytes(path) → int | None`.
  - **Test plan**: 5 pytest cases — happy path (synthetic gguf if fixture available, else skip), ImportError fallback, missing file, corrupt file, file size estimate.
  - **Strict-TDD**: yes
  - **Depends on**: —

- [x] T-WU1-02 — Define `GGUFMetadata` frozen dataclass in `core/model_meta.py`
  - **Files**: `bellbird/core/model_meta.py`, `tests/core/test_model_meta.py`
  - **Acceptance**: `GGUFMetadata` is a frozen dataclass with `block_count: int | None`, `context_length: int | None`, `file_type: str | None`, `size_bytes: int | None`.
  - **Test plan**: `frozen=True` mutation raises `dataclasses.FrozenInstanceError`.
  - **Strict-TDD**: yes
  - **Depends on**: T-WU1-01 (same file, add next)

- [x] T-WU1-03 — Add `read_vram` to `core/context_advisor.py` (new file)
  - **Files**: `bellbird/core/context_advisor.py` (new), `tests/core/test_context_advisor.py` (new)
  - **Acceptance**: `read_vram() → tuple[int | None, int | None]`. Win32 guard `if sys.platform == "win32"` — non-Win32 returns `(None, None)` early. Hard timeout 1s. Catches `FileNotFoundError`, `subprocess.TimeoutExpired`, non-zero exit, `OSError`.
  - **Test plan**: 6 cases — win32 happy (mock subprocess), non-win32 returns (None,None), timeout, FileNotFoundError, non-zero exit, malformed output.
  - **Strict-TDD**: yes
  - **Depends on**: —

- [x] T-WU1-04 — Add `estimate_fit` + `FitReport` to `core/context_advisor.py`
  - **Files**: `bellbird/core/context_advisor.py`, `tests/core/test_context_advisor.py`
  - **Acceptance**: `estimate_fit(metadata, ctx_size, vram_free_mb) → FitReport`. Heuristic: weights ≈ size_bytes, KV ≈ linear in ctx. Returns frozen dataclass `FitReport(status: Literal["fits","spills","unknown"], reason_es: str, confidence: Literal["high","low"])`.
  - **Test plan**: 5 cases — fits (small ctx, plenty VRAM), spills (large ctx, little VRAM), unknown (vram_free is None), unknown (size_bytes is None), Spanish one-liner format.
  - **Strict-TDD**: yes
  - **Depends on**: T-WU1-02 (uses GGUFMetadata), T-WU1-03 (uses read_vram)

- [x] T-WU1-05 — Add `token_count` to `core/context_advisor.py`
  - **Files**: `bellbird/core/context_advisor.py`, `tests/core/test_context_advisor.py`
  - **Acceptance**: `token_count(text, base_url, session, timeout: float | None = None) → int | None`. Calls `POST /tokenize`. Returns `None` on any HTTP/JSON error.
  - **Test plan**: 5 cases — happy path, server down (ConnectionError), 4xx, 5xx, malformed JSON.
  - **Strict-TDD**: yes
  - **Depends on**: —

- [x] T-WU1-06 — Add `pre_send_check` + `PreSendSnapshot` + `PreSendVerdict`
  - **Files**: `bellbird/core/context_advisor.py`, `tests/core/test_context_advisor.py`
  - **Acceptance**: `PreSendVerdict(decision: Literal["allow","warn","block"], reason_es: str | None)` frozen. `pre_send_check(snapshot: PreSendSnapshot) → PreSendVerdict`. Safe mode ON → block; safe mode OFF → warn once per conv; over-budget defined as `estimated > n_ctx`.
  - **Test plan**: 7 cases — allow when fits, allow when fits+safe OFF, warn when overflows+safe OFF, block when overflows+safe ON, no double warn, no block when n_ctx None, allow when n_ctx None.
  - **Strict-TDD**: yes
  - **Depends on**: T-WU1-05 (uses token_count conceptually)

- [x] T-WU1-07 — Add `SessionSnapshot` + `DEFAULT_STATUS_TOGGLES` to `core/status_formatter.py` (new)
  - **Files**: `bellbird/core/status_formatter.py` (new), `tests/core/test_status_formatter.py` (new)
  - **Acceptance**: `SessionSnapshot` frozen dataclass with 16 fields (model_name, n_ctx, prompt_tokens, completion_tokens, progress_tokens, last_tok_per_s, server_state, vram_free_mb, vram_total_mb, fit_status, message_count, temperature, top_p, max_tokens, is_generating). `DEFAULT_STATUS_TOGGLES` = frozenset of 11 names in canonical order.
  - **Test plan**: 4 cases — frozen mutation raises, default set has 11 names, ordering stable, Snapshot constructible with all-None data.
  - **Strict-TDD**: yes
  - **Depends on**: —

- [x] T-WU1-08 — Add `format_status` to `core/status_formatter.py`
  - **Files**: `bellbird/core/status_formatter.py`, `tests/core/test_status_formatter.py`
  - **Acceptance**: Pure function `format_status(snapshot, toggles: set[str], mode="short") → str`. No wx, no speech, no logging, no time calls. Deterministic. Unknown toggle → ignored. None data → component omitted.
  - **Test plan**: 13 cases — each of 11 toggles ON produces expected substring, all-OFF → "", mode="long" produces full breakdown, mid-gen uses progress_tokens, None data omits component, deterministic.
  - **Strict-TDD**: yes
  - **Depends on**: T-WU1-07 (uses SessionSnapshot)

- [x] T-WU1-09 — Add `on_timings` kwarg to `chat_stream`
  - **Files**: `bellbird/core/llama_client.py` (extend), `tests/core/test_llama_client.py` (extend)
  - **Acceptance**: New `on_timings: Callable[[dict], None] | None = None` kwarg on `LlamaClient.chat_stream` and `_stream_worker`. Fires once on final SSE chunk's `timings` field. When `None`, no-op.
  - **Test plan**: 4 cases — callback fires with timings dict, None skips, fires after on_usage, multiple calls don't crash.
  - **Strict-TDD**: yes
  - **Depends on**: —

- [x] T-WU1-10 — Add pinning regression test for `include_usage` wire contract
  - **Files**: `tests/core/test_llama_client.py` (extend only, no source change)
  - **Acceptance**: Asserts request body sent to mock server contains `"stream_options": {"include_usage": True}`.
  - **Test plan**: 1 case that captures the sent body JSON and asserts the key/value.
  - **Strict-TDD**: yes (test-only)
  - **Depends on**: T-WU1-09 (same test file)

- [x] T-WU1-11 — Add `threads` + `flash_attn` kwargs to `llama_runner.start_server`
  - **Files**: `bellbird/core/llama_runner.py` (extend), `tests/core/test_llama_runner.py` (extend)
  - **Acceptance**: `start_server(..., threads: int | None = None, flash_attn: bool = False)`. Defaults preserve current argv (no `--threads`, no `--flash-attn`).
  - **Test plan**: 4 cases — no flags by default, threads=4 → `--threads 4`, flash_attn=True → `--flash-attn`, both together.
  - **Strict-TDD**: yes
  - **Depends on**: —

- [x] T-WU1-12 — Add 4 new fields to `BellbirdConfig`
  - **Files**: `bellbird/core/config.py` (extend), `tests/core/test_config.py` (extend)
  - **Acceptance**: 4 new fields: `safe_vram_mode: bool = False`, `status_toggles: dict[str, bool]` (default: all True), `model_tunings: dict[str, dict] = field(default_factory=dict)`, `pre_send_warn: bool = True`. No migration entry. Forward-compat via `__dataclass_fields__` filter.
  - **Test plan**: 5 cases — defaults, loading v0.8.3 config without new fields returns defaults, `status_toggles_as_set()` helper, model_tunings JSON roundtrip, pre_send_warn defaults True.
  - **Strict-TDD**: yes
  - **Depends on**: T-WU1-07 (for DEFAULT_STATUS_TOGGLES import)

- [x] T-WU1-13 — Bump version from 0.8.3 to 0.9.0
  - **Files**: `pyproject.toml` (modify 1 line)
  - **Acceptance**: `version = "0.9.0"`.
  - **Test plan**: 1 test that imports `bellbird` and asserts `__version__ == "0.9.0"` (add `bellbird/__init__.py` exposing `__version__` if missing).
  - **Strict-TDD**: no (config-only)
  - **Depends on**: —

- [x] T-WU1-14 — Run WSL test suite
  - **Files**: none (verification)
  - **Acceptance**: `uv run --no-sync pytest -xvs` green. Zero failures, zero errors. 598+ new tests pass.
  - **Strict-TDD**: N/A
  - **Depends on**: T-WU1-01 through T-WU1-13

- [x] T-WU1-15 — Commit WU-1
  - **Files**: `git add -f` for `apply-progress.md` and `tasks.md` (per lessons-learned pattern, `openspec/` is gitignored)
  - **Acceptance**: `git log --oneline -1` shows `feat(core): context advisor + status formatter (v0.9.0 WU-1)`. `git status --short` clean. NO AI attribution, NO `Co-Authored-By`.
  - **Strict-TDD**: N/A
  - **Depends on**: T-WU1-14 (tests green)

---

## WU-2: UI + tests wx

**~600-800 lines | Depends on WU-1 — all WU-1 tasks committed and green.**

- [x] T-WU2-01 — Replace `_announce_session_status` body with `SessionSnapshot` + `format_status`
  - **Files**: `bellbird/ui/main_window.py` (extend), `tests/ui/test_main_window_runtime.py` (extend)
  - **Acceptance**: Handler reads `self._config.status_toggles_as_set()`, builds `SessionSnapshot`, calls `format_status(snapshot, toggles, "short")`, then `speech.output(text)` if not generating else `speech.speak(text, interrupt=False)`.
  - **Test plan**: 4 wx-runtime cases (importorskip) — F2 with ALL toggles ON, F2 with ALL toggles OFF → no speech, F2 mid-gen uses interrupt=False, F2 mid-gen uses progress_tokens.
  - **Strict-TDD**: yes
  - **Depends on**: T-WU1-07, T-WU1-08, T-WU1-12

- [x] T-WU2-02 — Add double-F2 detection
  - **Files**: `bellbird/ui/main_window.py`, `tests/ui/test_main_window_runtime.py`
  - **Acceptance**: 1.5s window via `time.monotonic()`. First F2 = "short", second F2 within window = "long". After 1.5s window resets.
  - **Test plan**: 3 cases — single F2 = short, two F2s within 1.5s = long, two F2s 2s apart = two shorts.
  - **Strict-TDD**: yes
  - **Depends on**: T-WU2-01

- [x] T-WU2-03 — Add `_update_context_meter` wired to `_on_usage`
  - **Files**: `bellbird/ui/main_window.py`, `tests/ui/test_main_window_runtime.py`
  - **Acceptance**: Sets status bar field 1 to `"Contexto: 1200/4096 (29 %)"`. Triggers `speech.speak(..., interrupt=False)` at ≥85% threshold (one-shot per generation, resets on new generation).
  - **Test plan**: 5 cases — happy update, threshold fires once, no refire same gen, n_ctx None shows "Contexto: ?", threshold reset on new generation.
  - **Strict-TDD**: yes
  - **Depends on**: T-WU1-07, T-WU1-08, T-WU2-01

- [x] T-WU2-04 — Add pre-send guard in `send_message`
  - **Files**: `bellbird/ui/main_window.py`, `tests/ui/test_main_window_runtime.py`
  - **Acceptance**: Calls `ContextAdvisor.pre_send_check(snapshot)` before posting. Block → speech + return. Warn → speech once. Allow → proceed. Warn resets per conversation.
  - **Test plan**: 4 cases — allow path, warn path (no re-warn), block path (returns early), warn resets on new conversation.
  - **Strict-TDD**: yes
  - **Depends on**: T-WU1-06, T-WU1-12

- [x] T-WU2-05 — Add "Estado (F2)" tab in preferences with 11 checkboxes
  - **Files**: `bellbird/ui/preferences_dialog.py` (extend), `tests/ui/test_preferences_dialog_static.py` (extend)
  - **Acceptance**: New notebook tab "Estado (F2)" with one `wx.CheckBox` per toggle, each preceded by `wx.StaticText` (AGENTS.md rule). Order matches `DEFAULT_STATUS_TOGGLES`. Mnemónicos `&` on labels.
  - **Test plan**: 4 AST cases — 11 checkboxes present, each has StaticText label, each has `name=`, mnemonics valid.
  - **Strict-TDD**: yes (AST + importorskip)
  - **Depends on**: T-WU1-07, T-WU1-12

- [x] T-WU2-06 — Add "Ayuda de encaje" StaticText to "Avanzado" tab
  - **Files**: `bellbird/ui/preferences_dialog.py`, `tests/ui/test_preferences_dialog_static.py`
  - **Acceptance**: Read-only `wx.StaticText` showing fit heuristic result. VRAM cached at dialog construction (no per-spin subprocess). Re-evaluates `estimate_fit` on ctx_size/n_gpu_layers spin change.
  - **Test plan**: 3 cases — StaticText read-only, VRAM fetched once (not per spin), fit refreshes on spin change.
  - **Strict-TDD**: yes (AST + importorskip)
  - **Depends on**: T-WU1-03, T-WU1-04, T-WU1-12

- [x] T-WU2-07 — Wire per-model tunings (save/restore)
  - **Files**: `bellbird/ui/preferences_dialog.py`, `bellbird/ui/main_window.py`, `tests/ui/test_preferences_dialog_static.py`
  - **Acceptance**: Save to `model_tunings` dict in `_apply_config`. Restore on model load / app startup. Key = `Path(model_path).name`. Never auto-prune.
  - **Test plan**: 3 cases — save writes to config, restore loads from config, no auto-prune on missing file.
  - **Strict-TDD**: yes
  - **Depends on**: T-WU1-12, T-WU2-05

- [x] T-WU2-08 — Register new wx-runtime tests in `run_tests.bat`
  - **Files**: `run_tests.bat` (modify)
  - **Acceptance**: Append test file paths for the new wx-runtime tests to the existing line (currently L23).
  - **Strict-TDD**: N/A
  - **Depends on**: T-WU2-01 through T-WU2-07

- [x] T-WU2-09 — Run WSL suite again
  - **Files**: none
  - **Acceptance**: `uv run --no-sync pytest -xvs` green, zero failures/errors. All WU-1 + WU-2 WSL-compatible tests pass.
  - **Strict-TDD**: N/A
  - **Depends on**: T-WU2-08

- [x] T-WU2-10 — Commit WU-2
  - **Files**: `git add -f` for updated `apply-progress.md` and `tasks.md`
  - **Acceptance**: `git log --oneline -1` shows `feat(ui): toggleable F2 + context meter + pre-send guard (v0.9.0 WU-2)`. `git status --short` clean. NO AI attribution.
  - **Strict-TDD**: N/A
  - **Depends on**: T-WU2-09 (tests green)

---

## Summary

| Phase | Tasks | Focus |
|-------|-------|-------|
| WU-1 | 15 | Core modules + tests (WSL, strict TDD) |
| WU-2 | 10 | UI wiring + wx-runtime tests |
| **Total** | **25** | |

Dependency order: WU-1 → WU-2 (core before UI). No circular dependencies found.

## Files in this change

| WU | Path | Action | Description |
|-----|------|--------|-------------|
| WU-1 | `bellbird/core/model_meta.py` | Extend | Add `GGUFMetadata`, `read_gguf_metadata`, `estimate_size_bytes` |
| WU-1 | `bellbird/core/context_advisor.py` | **New** | `read_vram`, `estimate_fit`, `token_count`, `pre_send_check` |
| WU-1 | `bellbird/core/status_formatter.py` | **New** | `SessionSnapshot`, `DEFAULT_STATUS_TOGGLES`, `format_status` |
| WU-1 | `bellbird/core/llama_client.py` | Extend | Add `on_timings` kwarg |
| WU-1 | `bellbird/core/llama_runner.py` | Extend | Add `threads`, `flash_attn` kwargs |
| WU-1 | `bellbird/core/config.py` | Extend | 4 new fields for v0.9.0 |
| WU-1 | `pyproject.toml` | Modify | Bump version to 0.9.0 |
| WU-1 | `bellbird/__init__.py` | **New** | Expose `__version__` for test |
| WU-1 | `tests/core/test_model_meta.py` | Extend | GGUF read + size tests |
| WU-1 | `tests/core/test_context_advisor.py` | **New** | VRAM, fit, token_count, pre_send_check tests |
| WU-1 | `tests/core/test_status_formatter.py` | **New** | 13 format_status test cases |
| WU-1 | `tests/core/test_llama_client.py` | Extend | on_timings + include_usage regression |
| WU-1 | `tests/core/test_llama_runner.py` | Extend | threads/flash_attn tests |
| WU-1 | `tests/core/test_config.py` | Extend | 4 new field roundtrip + forward-compat |
| WU-2 | `bellbird/ui/main_window.py` | Extend | F2 rewrite, double-F2, context meter, pre-send guard |
| WU-2 | `bellbird/ui/preferences_dialog.py` | Extend | "Estado (F2)" tab + Ayuda de encaje |
| WU-2 | `tests/ui/test_main_window_runtime.py` | Extend | F2, double-F2, context meter, guard tests |
| WU-2 | `tests/ui/test_preferences_dialog_static.py` | Extend | Estado tab + fit help AST checks |
| WU-2 | `run_tests.bat` | Modify | Register new wx-runtime tests |
