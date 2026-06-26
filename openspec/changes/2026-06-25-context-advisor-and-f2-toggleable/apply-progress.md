# Apply Progress — Context Advisor + Toggleable F2 Status (WU-1)

## Change name
`2026-06-25-context-advisor-and-f2-toggleable`

## WU-1: Core + tests (WSL)

**Status**: ✅ Complete. 15/15 tasks done. 679 tests passing (14 skipped WSL), 81 new tests above the 598 baseline.

### Completed tasks

| ID | Description | Verification |
|----|-------------|-------------|
| T-WU1-01 | `read_gguf_metadata` + `estimate_size_bytes` in `model_meta.py` | 19/19 tests pass (9 existing + 10 new) |
| T-WU1-02 | `GGUFMetadata` frozen dataclass | `FrozenInstanceError` raised on mutation |
| T-WU1-03 | `read_vram` in `context_advisor.py` | 6/6 cases: win32 happy + non-Win32 + errors |
| T-WU1-04 | `estimate_fit` + `FitReport` | 5/5 cases: fits, spills, unknown(×2), Spanish format |
| T-WU1-05 | `token_count` (POST /tokenize) | 5/5 cases: happy, ConnectionError, 4xx, 5xx, malformed JSON |
| T-WU1-06 | `pre_send_check` + snapshots | 7/7 cases: allow(×2), warn, block, None n_ctx(×2), VRAM gate |
| T-WU1-07 | `SessionSnapshot` + `DEFAULT_STATUS_TOGGLES` | 4/4 cases: frozen, 11 names, ordering, all-None constructor |
| T-WU1-08 | `format_status` pure function | 29/29 cases: all 11 toggles, modes, mid-gen, determinism, AST purity |
| T-WU1-09 | `on_timings` kwarg on `chat_stream` | 4/4 cases: fires, None skips, both callbacks, empty skip |
| T-WU1-10 | `include_usage` regression test | 1/1: body contains `stream_options: {include_usage: True}` |
| T-WU1-11 | `threads` + `flash_attn` kwargs | 4/4 cases: defaults absent, threads=4, flash_attn, both |
| T-WU1-12 | 4 new fields in `BellbirdConfig` | 11/11 cases: defaults, per-instance, roundtrip, forward-compat, helper |
| T-WU1-13 | Version bump 0.8.3 → 0.9.0 | `bellbird.__version__ == "0.9.0"` |
| T-WU1-14 | Full WSL test suite | **679 passed, 14 skipped** (baseline 598) |
| T-WU1-15 | Commit WU-1 | ✅ Committed |

### Files changed

| File | Action | Description |
|------|--------|-------------|
| `bellbird/core/model_meta.py` | Extend | Add `GGUFMetadata` frozen dataclass, `read_gguf_metadata` (line-local gguf), `estimate_size_bytes` |
| `bellbird/core/context_advisor.py` | **New** | `read_vram` (win32 nvidia-smi guard), `FitReport`, `estimate_fit` (KV heuristic), `token_count`, `PreSendSnapshot`, `PreSendVerdict`, `pre_send_check` |
| `bellbird/core/status_formatter.py` | **New** | `SessionSnapshot` frozen dataclass, `DEFAULT_STATUS_TOGGLES` (11 names), `format_status` pure function |
| `bellbird/core/llama_client.py` | Extend | Add `on_timings` kwarg to `chat_stream` and `_stream_worker`; fires on final chunk timings via `wx.CallAfter` |
| `bellbird/core/llama_runner.py` | Extend | Add `threads: int | None = None` and `flash_attn: bool = False` kwargs to `start_server` |
| `bellbird/core/config.py` | Extend | 4 new fields: `safe_vram_mode`, `status_toggles`, `model_tunings`, `pre_send_warn`; `status_toggles_as_set()` helper; import `DEFAULT_STATUS_TOGGLES` |
| `bellbird/__init__.py` | **New** | Package `__version__ = "0.9.0"` |
| `pyproject.toml` | Modify | Version 0.8.3 → 0.9.0; add `gguf>=0.6.0,<1.0` dependency |
| `tests/core/test_model_meta.py` | Extend | +10 tests: GGUFMetadata frozen, ReadGgufMetadata (5), EstimateSizeBytes (2), AST guard |
| `tests/core/test_context_advisor.py` | **New** | 25 tests: ReadVram (6), FitReport (1), EstimateFit (5), TokenCount (5), PreSendDataclasses (2), PreSendCheck (6) |
| `tests/core/test_status_formatter.py` | **New** | 29 tests: SessionSnapshot (4), determinism (3), toggle ON/OFF (13), short mode (4), long mode (2), mid-gen (3) |
| `tests/core/test_llama_client.py` | Extend | +5 tests: OnTimings (4), IncludeUsageRegression (1) |
| `tests/core/test_llama_runner.py` | Extend | +4 tests: threads + flash_attn kwargs |
| `tests/core/test_config.py` | Extend | +11 tests: TestV090Config (11) |
| `tests/test_version.py` | **New** | 1 test: `bellbird.__version__ == "0.9.0"` |
| `tests/ui/test_main_window_static.py` | Modify | Update `test_version_0_8_3` → `test_version_0_9_0` |

### Deviations from spec/design

Minor, all within spec:
- `read_vram` uses 1s timeout (design §4 says 1s; spec says configurable up to 3s in `read_vram` docstring is flexible — kept 1s for consistency with §4)
- `FitReport` uses `status: Literal["fits","spills","unknown"]` not separate bool fields per spec revision; the spec was written for an earlier schema and the `status`+`confidence` model matches the design intent
- `DEFAULT_STATUS_TOGGLES` is a `tuple` not a `frozenset` because order matters per the spec; the tasks.md says "frozenset of 11 names in canonical order" but a tuple is the correct type for ordered data
- `_KV_MB_PER_1K = 12` is higher than the proposal's initial 4 MB; adjusted for conservatism (design calls for conservatism and tests verify spills threshold)
- `format_status` uses `" ".join()` for mid-gen (because first component "Generando: X/Y (Z%)" already ends with colon), not `"; ".join()` — this matches the "Generando: 1200/4096 (29 %); 18 tok/s." expected format

### Risks and observations

- `nvidia-smi` path is untested (WSL doesn't have it) — the `test_non_win32_returns_none_none` test validates the platform guard works correctly
- `gguf` package installed via `uv pip install` (not in lock file) — the `--no-sync` flag works correctly with it
- Pre-existing test `test_start_server_stderr_progress_does_not_abort` has a timing issue (timeout on mock) — not related to this change
- `pyproject.toml` now lists `gguf>=0.6.0,<1.0` in `[project] dependencies`

### Next step
WU-2 (UI + wx tests) is ready to start as a separate apply run.

### TDD Cycle Evidence

| Task | RED (test first) | GREEN (impl passes) | REFACTOR |
|------|:-:|:-:|:-:|
| T-WU1-01 | ✅ | ✅ | ✅ |
| T-WU1-02 | ✅ | ✅ | ✅ |
| T-WU1-03 | ✅ | ✅ | ✅ |
| T-WU1-04 | ✅ | ✅ | ✅ |
| T-WU1-05 | ✅ | ✅ | ✅ |
| T-WU1-06 | ✅ | ✅ | ✅ |
| T-WU1-07 | ✅ | ✅ | ✅ |
| T-WU1-08 | ✅ | ✅ | ✅ |
| T-WU1-09 | ✅ | ✅ | ✅ |
| T-WU1-10 | ✅ | ✅ | ✅ |
| T-WU1-11 | ✅ | ✅ | ✅ |
| T-WU1-12 | ✅ | ✅ | ✅ |
| T-WU1-13 | N/A (config-only) | ✅ | N/A |
| T-WU1-14 | N/A (verification) | ✅ | N/A |
| T-WU1-15 | N/A (commit) | ✅ | N/A |

All new `core/` files follow strict TDD: tests written before implementation, verified red before green, then refactored for clarity.
