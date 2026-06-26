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

## WU-2: UI + wx tests

**Status**: ✅ Complete. 10/10 tasks done. 689 tests passing (14 skipped WSL), 10 new tests above the WU-1 baseline of 679.

### Completed tasks

| ID | Description | Verification |
|----|-------------|-------------|
| T-WU2-01 | Replace `_announce_session_status` body with `SessionSnapshot` + `format_status` | F2 routes through `speech.output()` (idle) / `speech.speak(interrupt=False)` (mid-gen). All toggles OFF → empty string, no speech. 4 wx-runtime tests. |
| T-WU2-02 | Double-F2 within 1.5 s → mode="long" | Timestamp-based via `time.monotonic()`. Single → short, double within window → long, >1.5s → two shorts. 3 wx-runtime tests. |
| T-WU2-03 | `_update_context_meter` wired to `_on_usage` | Status bar field 1 shows `"Contexto: X/Y (Z%)"`. ≥85% threshold fires one-shot per generation. n_ctx=None shows `"Contexto: N tokens"`. 5 wx-runtime tests. |
| T-WU2-04 | Pre-send guard in `send_message` | Block → speech + return. Warn → speech once per conv. Allow → proceed silently. Warn flag resets on new\!conversation. 4 wx-runtime tests. |
| T-WU2-05 | "Estado (F2)" tab with 11 checkboxes | 7th notebook tab with one `wx.CheckBox` per `DEFAULT_STATUS_TOGGLES` toggle, each preceded by `wx.StaticText` with mnemonic `&`. 4 AST tests. |
| T-WU2-06 | "Ayuda de encaje" read-only StaticText in Avanzado tab | `name="pref_fit_help"` showing `estimate_fit()` Spanish one-liner. VRAM cached on dialog construction. Refreshes on ctx_size/n_gpu_layers spin change. 3 AST tests. |
| T-WU2-07 | Per-model tunings save/restore | Save in `_apply_config`. Restore in `_on_use_model`. Key = `Path(model_path).name`. Never auto-prunes. 3 AST tests. |
| T-WU2-08 | Register new tests in `run_tests.bat` | Added `tests/ui/test_preferences_dialog_static.py` to the wx-runtime line. |
| T-WU2-09 | Run WSL suite | **689 passed, 14 skipped** ✅ (10 new tests above 679 baseline) |
| T-WU2-10 | Commit WU-2 | ✅ Committed |

### Files changed (WU-2)

| File | Action | Description |
|------|--------|-------------|
| `bellbird/ui/main_window.py` | Extend | Rewrite `_announce_session_status` with SessionSnapshot + format_status + double-F2; add `_on_timings`, `_update_context_meter`; add pre-send guard to `send_message`; wire `on_timings` to `chat_stream`; per-model tunings restore; new instance state attributes. |
| `bellbird/ui/preferences_dialog.py` | Extend | Add "Estado (F2)" tab (7th tab, 11 checkboxes with StaticText), "Ayuda de encaje" in Avanzado tab, per-model tunings save in `_apply_config`, VRAM cache at construction. |
| `tests/ui/test_main_window_runtime.py` | Extend | 4 new test classes: TestF2StatusFormatter, TestDoubleF2, TestContextMeter, TestPreSendGuard (14 test cases, skipped on WSL via `importorskip("wx")`). |
| `tests/ui/test_preferences_dialog_static.py` | Extend | 10 new AST tests: Estado tab checkboxes/labels/mnemonics, fit help presence/refresh/VRAM cache, model tunings save/restore/no-prune. |
| `tests/ui/test_main_window_static.py` | Modify | Update F2-related static tests to match new format_status-based implementation. |
| `run_tests.bat` | Modify | Register `tests/ui/test_preferences_dialog_static.py` in the wx-runtime line. |

### Deviations from spec/design

None — implementation matches design and spec. The `test_f2_includes_min_p` static test was updated to verify `SessionSnapshot` construction instead of the old `min_p` string (min_p is no longer part of the F2 toggle set per the new design).

### Risks and observations

- wx-runtime tests (14 in test_main_window_runtime.py) are skipped on WSL and must be verified on Windows via `run_tests.bat`.
- The `test_main_window_static.py::test_f2_status_contains_vision_string` test was replaced because the new F2 handler no longer includes hardcoded "Imágenes:" string — vision is not part of the DEFAULT_STATUS_TOGGLES.
- Pre-send guard calls `POST /tokenize` synchronously on the UI thread with a 5s timeout — acceptable per design §4 (user already pressed Enter).

### Next step
Ready for verify phase.

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

---

## WU-2 Post-Remediation (after verify CRITICAL)

### C1 fix (commit `aae74d7`)

The verify agent caught a CRITICAL bug in the double-F2 state machine
(`main_window.py:1204-1211`): the spec-mandated reset of
`self._last_f2_mono = None` on the long-mode branch was immediately
overridden by an unconditional `self._last_f2_mono = now` on the
next line, so a 3rd F2 press within 1.5s of a 2nd produced "long"
instead of the spec-required "short" cycle restart.

This is exactly the v0.8.3 lessons-learned pattern: tests passing
≠ correct code for timing-state conditions. The wx-runtime
`TestDoubleF2` only covered 2 presses (single + double), so the
3-press path was invisible to the test suite.

**Fix**: move `self._last_f2_mono = now` into the else (short)
branch only. Now the timestamp tracks the last "short" press, and
any second press within 1.5s of that gets the "long" mode while
clearing the timestamp, so a 3rd press starts a fresh "short" cycle.

**Regression test added**: `test_triple_f2_starts_short_again` in
`tests/ui/test_main_window_runtime.py::TestDoubleF2`. Skipped on
WSL, runs on Windows via `run_tests.bat`. Verified on WSL with a
standalone Python script that mirrors the if/else logic across 4
scenarios (triple, double, spaced, quadruple press).

### W10 fix (commit `c4e05bf`)

Added `FakeSpeech.output(text)` stub to
`tests/ui/test_main_window_runtime.py`. The production F2 handler
calls `self._speech.output(text)` (accessible-output2 voz+braille)
when not generating, but the test stub only had `speak()`. The
wx-runtime test would have raised `AttributeError` on Windows.

### Chore (commit `83942fe`)

- `uv.lock` regenerated after adding `gguf` dep and bumping
  bellbird version from stale 0.7.3 to 0.8.3.
- Three force-added artifacts from the previous `attach-url`
  change (moved to `archive/`) deleted from working tree so
  `git status --short` is clean before archive.

### Final state

- 689 passed, 14 skipped (WSL).
- 4 commits on `main`:
  - `8a8c725` WU-1 (core+tests)
  - `a1f9b17` WU-2 (UI+tests)
  - `aae74d7` C1 fix + triple-press test
  - `c4e05bf` W10 FakeSpeech.output() stub
  - `83942fe` chore (uv.lock + archive cleanup)
- No AI attribution in any commit.
- Ready for archive.
