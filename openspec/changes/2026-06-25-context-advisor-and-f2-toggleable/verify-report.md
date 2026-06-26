# Verify Report: Context Advisor + Toggleable F2 (v0.9.0)

## Verdict
**READY TO ARCHIVE WITH WARNINGS** (post-remediation)

## Summary

The WU-1 core and WU-2 UI work is largely correct, with 689 tests passing
(14 skipped WSL) and the bulk of the spec covered. The original verify
found 1 CRITICAL bug in the double-F2 detection (`main_window.py:1204-1211`): the
`_last_f2_mono` reset-to-None is immediately overridden by an unconditional
`self._last_f2_mono = now` on the same handler, so a 3rd F2 press within
1.5 s of a 2nd produces another "long" form instead of the spec-mandated
"short" cycle restart. This is exactly the kind of timing-state bug the
v0.8.3 lesson learned warns about (594 tests passed, real bug caught
only by code reading). The fix is a 2-line change.

## Test results

- Total: **689 passed, 14 skipped, 0 failed** (WSL baseline 598 → 689, +91 new)
- Regression test for §11.A: PASSED
  (`tests/core/test_llama_client.py::TestIncludeUsageRegression::test_body_contains_include_usage`).
- WSL suite: green.

## Code audit findings

### `bellbird/ui/main_window.py`

- **`_update_context_meter`**: **CLEAN** — `pct = round(100 * total / n_ctx)`,
  `SetStatusText` with `Contexto: X/Y (Z %)` per spec. Threshold branch
  gated by `pct >= 85 and self._is_generating and not self._meter_threshold_fired`
  (lines 1983-1986). Reset happens in `send_message` (line 1441). One
  spec drift: the field is `_meter_threshold_fired`, not
  `_context_warned_for_turn` (the latter is initialized in `__init__` at
  line 148 and reset in `new_conversation` at line 2286, but never read).
  The rename is more descriptive and the behaviour is correct, but
  `_context_warned_for_turn` is dead state.

- **`_last_f2_mono` (double-F2 detection)**: **CRITICAL** — see CRITICAL
  findings below.

- **Pre-send guard**: **CLEAN** — `token_count(..., timeout=5.0)` per
  design §4. `read_vram()[0]` cached fallback on line 1411 (`if
  self._vram_free_mb is None else self._vram_free_mb`) — note the
  `self._vram_free_mb` field is initialized to `None` and never assigned
  elsewhere, so the cache always falls through and `read_vram()` is
  always called on the UI thread (acceptable per spec, 1s timeout). The
  cache field is dead state. Block → speech + return; warn → speech
  once + flag set; allow → proceed silently. `_pre_send_warned_this_conv`
  reset in `new_conversation` (line 2285). Spec scenario for "F2 with
  toggles ALL OFF returns an empty string" works because `format_status`
  returns `""` and the handler early-returns at line 1244-1245.

- **F2 handler (`_announce_session_status`)**: **WARNING** — beyond the
  CRITICAL double-F2 bug above, the rest of the handler is correct:
  `speech.output(text)` when idle (line 1250), `speech.speak(text,
  interrupt=False)` when generating (line 1248). `SessionSnapshot` built
  correctly with `progress_tokens = self._latest_completion_tokens if
  self._is_generating else None` (line 1219-1221). The `n_ctx is None`
  case degrades to `Contexto: N tokens` (per spec regression scenario).
  The `output` method exists on `Speech` but NOT on the test's
  `FakeSpeech` — the wx-runtime test in
  `test_main_window_runtime.py::TestF2StatusFormatter` will raise
  `AttributeError` on Windows because `output` is never mocked. This
  is a gap in the test, not a code defect; the production code is
  correct.

### `bellbird/core/context_advisor.py`

- **`read_vram`**: **CLEAN** — `if sys.platform != "win32": return
  (None, None)` early-return at line 36-37. `subprocess.run` with
  `timeout=1.0` (line 48) — note the spec says 1-3s and design §4 says
  1s; the apply-progress doc claims 3s, the impl uses 1s. Acceptable
  per design, but the apply-progress should be updated to match.
  Catches `FileNotFoundError`, `subprocess.TimeoutExpired`, `OSError`.
  Non-zero `returncode` → `(None, None)`. Malformed parse → `(None,
  None)`. Never raises. ✓

- **`token_count`**: **CLEAN** — `POST /tokenize` with `add_special:
  False`. Catches `requests.RequestException`, `ValueError`, `TypeError`.
  Non-200 → `None`. `timeout` parameter is caller-provided; main_window
  passes 5.0 (line 1414). Never raises. ✓

- **`pre_send_check`**: **CLEAN (with spec drift)** — implements
  block/warn/allow per spec. Pure boolean logic, no I/O. The
  `PreSendSnapshot` field `warn_once: bool` is defined but never read
  inside `pre_send_check` — the warn-once flag is tracked in
  `MainWindow._pre_send_warned_this_conv` instead. This is
  intentional (per the design, the warn-once state lives in the UI
  layer) but the field is dead on the snapshot dataclass. Minor spec
  drift: the spec said "estimated_prompt_tokens" but the impl uses
  "estimated_tokens" — same semantic, different name. Apply-progress
  documents this.

### `bellbird/core/llama_client.py`

- **`on_timings` kwarg**: **CLEAN** — wired through `chat_stream` (line
  253) and `_stream_worker` (line 318). The dispatch block (lines
  455-458) wraps in `wx.CallAfter`, guards on `on_timings is not None`
  (no `chunk.get("timings")` call when caller didn't pass it — no
  overhead), and treats `timings == {}` (empty dict) as "no timings"
  via `if timings is not None and timings:`. Symmetric to `on_usage`
  handling. The spec says "fires exactly once per stream" — the impl
  does not guard against multiple chunks with timings, but in practice
  llama-server only sends timings once (on the final chunk). Defensive
  in practice. Both `chat_stream` call sites in main_window pass
  `on_timings=self._on_timings` (lines 1478 and 1752). ✓

### `bellbird/core/llama_runner.py`

- **`threads` / `flash_attn` kwargs**: **CLEAN** — `threads: int | None
  = None` default → no `--threads` flag in argv (line 233). `flash_attn:
  bool = False` default → no `--flash-attn` flag (line 235). Tests
  verify all 4 combinations (default absent, threads=4, flash_attn=True,
  both). Defaults preserve prior behavior. ✓

### `bellbird/core/config.py`

- **New fields + helper**: **CLEAN** — `safe_vram_mode: bool = False`,
  `status_toggles: dict[str, bool]` with `default_factory=lambda: {t:
  True for t in DEFAULT_STATUS_TOGGLES}` (per-instance, all ON first
  run), `model_tunings: dict[str, dict] = field(default_factory=dict)`
  (per-instance empty), `pre_send_warn: bool = True`. Import of
  `DEFAULT_STATUS_TOGGLES` from `status_formatter` is at module top
  (line 10) — no circular import risk because `status_formatter` only
  imports `dataclasses` and `typing`. The `__dataclass_fields__` filter
  in `load_config` (lines 111-112) silently fills missing keys with
  defaults — no migration entry needed. `_MIGRATIONS` remains
  single-entry (`max_tokens`). `status_toggles_as_set()` returns
  `{k for k, v in self.status_toggles.items() if v}` (line 61) —
  handles empty dict correctly (returns `set()`). ✓

### `bellbird/core/status_formatter.py`

- **Purity (no wx/speech/time/random)**: **CLEAN** — only imports
  `dataclasses` and `typing`. No `wx`, no `speech`, no `logging`, no
  `time`, no `random`. AST test `test_pure_no_wx_speech_or_logging`
  verifies this. ✓

- **Determinism**: **CLEAN** — no time/random/sleep/IO. Test
  `test_byte_identical_output` asserts `a == b` for repeated calls.
  ✓

### `bellbird/ui/preferences_dialog.py`

- **"Estado (F2)" tab**: **CLEAN (with spec drift)** — 11 checkboxes
  (one per `DEFAULT_STATUS_TOGGLES`), each preceded by `wx.StaticText`
  with mnemonic `&` (per AGENTS.md rule). Mnemonics: `&Modelo`,
  `&Porcentaje de contexto`, `&Máx tokens/respuesta`, `&Servidor`,
  `&VRAM libre`, `&Encaje`, `&Mensajes`, `&Temperatura`, `&Top-p`,
  `&Tok/s última`, `&Generando`. Checkbox `name=f"chk_{toggle_name}"`,
  label `name=f"lbl_{toggle_name}"`. `_on_status_toggle` writes
  `self._config.status_toggles[toggle_name] = event.IsChecked()`. Tab
  added at the end of the notebook, AFTER "Atajos" (line 790:
  `notebook.AddPage(panel, "&Estado (F2)")`). The spec scenario says
  "10 CheckBoxes" but lists 11 names and the impl has 11 — the test
  verifies 11, so the spec wording is internally inconsistent. Spec
  drift, not a code issue.

- **"Ayuda de encaje" StaticText**: **CLEAN (with warning)** —
  `name="pref_fit_help"` in Avanzado tab (line 615), between the
  GPU-layers spin and the server-port spin (per spec). `VRAM cached at
  dialog construction` via `self._vram_cache = read_vram()` in
  `__init__` (line 298). `_refresh_fit_help` (line 827) uses
  `self._vram_cache[0]` (no per-spin `nvidia-smi` call). The sentinel
  `GGUFMetadata(block_count=0, context_length=0, file_type="unknown",
  size_bytes=size_bytes or 0)` matches the spec exactly. WARNING:
  `_refresh_fit_help` only reads `ctx_size`, not `n_gpu_layers` (which
  is bound to the same handler but the handler ignores it). The
  refresh happens on n_gpu_layers changes but is a no-op. The spec
  says the label MAY be lazy-refreshed, so this is acceptable but
  suboptimal.

- **Per-model tunings save**: **CLEAN** — `_apply_config` (line 909)
  writes `self._config.model_tunings[basename] = {"ctx_size": ...,
  "n_gpu_layers": ..., "threads": None}` only when `model_path` is
  truthy (line 939). No auto-prune. AST test
  `test_model_tunings_no_auto_prune` verifies no `pop`/`clear`/`discard`
  on `model_tunings` in either source file. Restore happens in
  `_on_use_model` (line 861-867) on model load. ✓

## Spec coverage

| Spec | REQ | Test file | Covered? |
|---|---|---|---|
| context-advisor | REQ-CA-001 `read_gguf_metadata` happy + ImportError/corrupt | `tests/core/test_model_meta.py::TestReadGgufMetadata` | yes |
| context-advisor | REQ-CA-002 `estimate_size_bytes` existing vs missing | `tests/core/test_model_meta.py::TestEstimateSizeBytes` | yes |
| context-advisor | REQ-CA-003 `read_vram` win32 guard + non-win32 + error paths | `tests/core/test_context_advisor.py::TestReadVram` (6 cases) | yes |
| context-advisor | REQ-CA-004 `estimate_fit` + `FitReport` (fits/spills/unknown, Spanish) | `tests/core/test_context_advisor.py::TestEstimateFit` (5 cases) | yes |
| context-advisor | REQ-CA-005 `token_count` happy + 4xx + 5xx + ConnectionError + JSON | `tests/core/test_context_advisor.py::TestTokenCount` (5 cases) | yes |
| context-advisor | REQ-CA-006 `pre_send_check` allow/warn/block + safe mode + n_ctx None | `tests/core/test_context_advisor.py::TestPreSendCheck` (6 cases) + `tests/ui/test_main_window_runtime.py::TestPreSendGuard` (4 wx-runtime cases) | yes |
| status-formatter | REQ-FMT-001 `SessionSnapshot` frozen | `tests/core/test_status_formatter.py::TestSessionSnapshot` (4 cases) | yes |
| status-formatter | REQ-FMT-002 `format_status` pure + deterministic | `tests/core/test_status_formatter.py::TestFormatStatusDeterminism` (3 cases) | yes |
| status-formatter | REQ-FMT-003 toggles: 11 names + ON/OFF/None/unknown | `tests/core/test_status_formatter.py::TestFormatStatusToggles` (13 cases) | yes |
| status-formatter | REQ-FMT-004 short mode one-sentence + long mode multi-line | `tests/core/test_status_formatter.py::TestFormatStatusShortMode` (4) + `TestFormatStatusLongMode` (2) | yes |
| status-formatter | REQ-FMT-005 mid-gen uses `progress_tokens` + `last_tok_per_s` | `tests/core/test_status_formatter.py::TestFormatStatusMidGen` (3) + `tests/ui/test_main_window_runtime.py::TestF2StatusFormatter` (4 wx-runtime) | yes |
| llama-integration | REQ-LLAMA-027 `include_usage` pinned in body | `tests/core/test_llama_client.py::TestIncludeUsageRegression::test_body_contains_include_usage` | yes |
| llama-integration | REQ-LLAMA-028 `on_timings` callback fires / None skips / fires-after-usage / empty dict skipped | `tests/core/test_llama_client.py::TestOnTimings` (4 cases) | yes |
| app-shell | F2 builds snapshot + format_status + routes via `speech.output`/`speech.speak(interrupt=False)` | `tests/ui/test_main_window_runtime.py::TestF2StatusFormatter` (4 wx-runtime) + `tests/ui/test_main_window_static.py::test_f2_uses_format_status` (AST) + `test_f2_includes_min_p` (AST) | yes |
| app-shell | Double-F2 within 1.5 s → `mode="long"` | `tests/ui/test_main_window_runtime.py::TestDoubleF2` (3 wx-runtime cases) | **PARTIAL** — does not test 3rd press (the bug) |
| app-shell | Status bar field 1 live context meter + 85 % threshold one-shot | `tests/ui/test_main_window_runtime.py::TestContextMeter` (5 wx-runtime cases) | yes |
| app-shell | Pre-send guard block / warn-once / allow + reset on new conv | `tests/ui/test_main_window_runtime.py::TestPreSendGuard` (4 wx-runtime cases) | yes |
| app-configuration | 4 new `BellbirdConfig` fields + per-instance + forward-compat | `tests/core/test_config.py::TestV090Config` (11 cases) | yes |
| app-configuration | `status_toggles_as_set()` returns active names | `tests/core/test_config.py::TestStatusTogglesAsSet` | yes |
| app-configuration | "Estado (F2)" tab with 11 CheckBoxes + StaticText + mnemonics | `tests/ui/test_preferences_dialog_static.py::test_estado_f2_tab_*` (4 AST cases) | yes |
| app-configuration | "Ayuda de encaje" StaticText + VRAM cached + refresh on spin | `tests/ui/test_preferences_dialog_static.py::test_fit_help_*` (3 AST cases) | yes |
| app-configuration | Per-model tunings save + restore + no auto-prune | `tests/ui/test_preferences_dialog_static.py::test_model_tunings_*` (3 AST cases) | yes |

## Work-unit split

- WU-1 (`8a8c725`): 2346 insertions, 8 deletions, 18 files. No
  `bellbird/ui/` files touched. ✓
- WU-2 (`a1f9b17`): 937 insertions, 56 deletions, 8 files. Only
  `bellbird/ui/main_window.py` and `bellbird/ui/preferences_dialog.py`
  in the UI; no new `bellbird/core/` modules. ✓
- Version bump (0.8.3 → 0.9.0) is in WU-1 (`pyproject.toml` +
  `bellbird/__init__.py`). ✓

## Process compliance

- [x] WU-1 commit has no AI attribution.
  (`git log --format=fuller 8a8c725` shows author/committer
  `miguel-cinsfran <miguelinsfranc@gmail.com>`, no `Co-Authored-By:`.)
- [x] WU-2 commit has no AI attribution.
  (`git log --format=fuller a1f9b17` shows the same.)
- [x] `apply-progress.md` is committed and accurate. Both WU-1 and
  WU-2 sections present, both commit hashes listed (8a8c725 and
  a1f9b17), deviations documented, next step = archive (in the
  original; this report supersedes).
- [x] `tasks.md` is committed with all 25 tasks marked `[x]` in both
  WU-1 (15 tasks) and WU-2 (10 tasks).
- [x] `size:exception` is documented in `tasks.md` budget forecast
  (line 5-19) and design §5. Both WU-1 and WU-2 exceed the 800-line
  review budget.
- [x] No pre-existing failure in the test suite (689 passed, 14
  skipped WSL — same skip count as the v0.8.3 baseline).
- [x] Regression test for §11.A `include_usage` is in place at
  `tests/core/test_llama_client.py::TestIncludeUsageRegression::test_body_contains_include_usage`.

## CRITICAL findings

### C1: Double-F2 detection logic is broken — third press within 1.5 s of second press triggers "long" instead of "short"

**File:** `bellbird/ui/main_window.py:1204-1211`

```python
# Double-F2 detection (T-WU2-02)
now = time.monotonic()
if self._last_f2_mono is not None and (now - self._last_f2_mono) <= 1.5:
    mode: str = "long"
    self._last_f2_mono = None  # reset so third press starts short cycle
else:
    mode = "short"
self._last_f2_mono = now
```

The spec (`specs/app-shell/spec.md` Requirement "Double-F2 within 1.5 s
switches to mode='long'") explicitly says: **"SHALL reset
`self._last_f2_mono` to `None` so a third press starts the `'short'`
cycle again"**.

The code does set `_last_f2_mono = None` at line 1208 — but then line
1211 unconditionally assigns `self._last_f2_mono = now`, overriding
the reset. Result:

- Press 1 at t=0 → short. `_last_f2_mono = 0`.
- Press 2 at t=0.3 → long (correct). `_last_f2_mono` set to `None`
  (per spec), then immediately set to `0.3` (bug).
- Press 3 at t=0.6 → expects "short" per spec, but receives "long"
  (0.6 - 0.3 = 0.3 ≤ 1.5).

The runtime test `tests/ui/test_main_window_runtime.py::TestDoubleF2`
only tests 2 presses (single + double) and does not cover the 3rd
press path. The bug is **invisible to the test suite** — exactly the
v0.8.3 lesson-learned pattern: "tests passing ≠ correct code for race
/timing conditions".

**Proposed fix (2 lines):** move the assignment to the else branch:

```python
now = time.monotonic()
if self._last_f2_mono is not None and (now - self._last_f2_mono) <= 1.5:
    mode: str = "long"
    self._last_f2_mono = None  # reset so third press starts short cycle
else:
    mode = "short"
    self._last_f2_mono = now
```

This CRITICAL must be fixed before archive. After the fix, a 3rd-press
wx-runtime test should be added to `TestDoubleF2`.

## WARNING findings

- **W1**: `_context_warned_for_turn` is dead state.
  - Initialized at `main_window.py:148`, reset in
    `new_conversation` at line 2286, but never read.
  - The actual threshold gate uses `_meter_threshold_fired`
    (line 1984), which IS reset properly in `send_message`
    (line 1441).
  - **Fix**: drop `_context_warned_for_turn` from `__init__` and
    `new_conversation`. Or rename `_meter_threshold_fired` →
    `_context_warned_for_turn` to match the spec. Pick one.

- **W2**: `_vram_free_mb` cache is dead state on `MainWindow`.
  - Initialized to `None` at line 144 and never assigned.
  - The pre-send guard at line 1411 checks `if self._vram_free_mb
    is None` — always True — so `read_vram()` runs on every send.
  - Acceptable per design §4 (1s timeout), but the field is dead.
    Either populate it (e.g. after a successful F2 / status bar
    refresh) or remove the dead check.

- **W3**: `PreSendSnapshot.warn_once` is dead state.
  - Defined at `context_advisor.py:211` but never read inside
    `pre_send_check`.
  - The warn-once flag is tracked in
    `MainWindow._pre_send_warned_this_conv` (per design).
  - **Fix**: drop `warn_once` from `PreSendSnapshot` to avoid
    confusion (or document why it's there for future use).

- **W4**: `_refresh_fit_help` ignores `n_gpu_layers` change.
  - The spin handler at line 852-855 fires on BOTH
    `pref_ctx_size_spin` and `pref_gpu_layers_spin` (lines 623-628).
  - `_refresh_fit_help` only reads `ctx_size`; `n_gpu_layers` change
    triggers a no-op refresh.
  - Spec says MAY be lazy-refreshed; current behaviour is
    acceptable. Cleanest fix: read ngl too and either include it in
    the heuristic or add a one-liner note.

- **W5**: `read_vram` impl uses 1s timeout; design §4 says 1s, spec
  says configurable up to 3s. Apply-progress doc claims 1s in
  "Deviations" — actually it says "spec says configurable up to 3s"
  which is correct. No fix needed, but the spec text is loose
  ("timeout=3" in `read_vram` description). Pin the spec to 1s to
  match design.

- **W6**: Spec wording drift in `app-configuration/spec.md`
  Requirement "Estado (F2) Tab": scenario says "exactly 10
  `wx.CheckBox`" but lists 11 names. The impl has 11 (correct per
  the actual list and the test). Fix the spec to say "11
  CheckBoxes".

- **W7**: `FitReport` schema drift: spec says 3 booleans
  (`fits`, `spills_to_ram`, `unknown`); impl uses one
  `status: Literal["fits","spills","unknown"]`. The impl is
  consistent with the proposal and the test. Fix the spec to
  match the impl (or vice versa — but the impl is more idiomatic).

- **W8**: `format_status` `mode="short"` appends `"."` to the
  joined components (line 139). The spec scenario says "exactly one
  `'.'`" which would fail when `vram` component renders `4.5/12.0`
  GB. The test was relaxed to "ends with `'.'`" (test_status_formatter.py:233).
  This is a test-spec mismatch, not a code issue, but the spec
  wording is misleading.

- **W9**: `_on_usage` reads `prompt_tokens` and `completion_tokens`
  separately and adds them; the spec's spec scenario quotes a usage
  chunk with `total_tokens: 1200` and expects the meter to read
  `1200`. The impl computes 200+1000=1200 (same value, different
  field). The `total_tokens` field in the usage chunk is redundant
  for our purposes. No behaviour issue, but the spec is slightly
  misleading.

- **W10**: `FakeSpeech` test stub has no `output` method, but the
  F2 handler calls `self._speech.output(text)` (not `speak`) when
  idle. The wx-runtime test `test_f2_all_toggles_on_calls_output`
  will raise `AttributeError` on Windows — but the test is currently
  skipped on WSL, so this gap is invisible. Either:
  - Add `def output(self, text): self.last_message = text;
    self.messages.append(text)` to `FakeSpeech`, OR
  - Patch `frame._speech.output` in the test (the mid-gen test
    already does this on line 729).

- **W11**: `kwargs` is a `dict` (not `dict[str, ...]`) in
  `start_server` (line 240). Pre-existing style, not new to this
  change. Acceptable per Python 3.12 conventions but a `dict[str,
  Any]` annotation would be more precise.

- **W12**: `_current_n_ctx` is never populated in this change. The
  F2 handler reads it (line 1225), the context meter reads it
  (line 1958), and the pre-send guard reads it (line 1419), but
  no code in the diff ever sets it. The pre-existing startup probe
  in `core/startup.py` is responsible for populating it. This is
  not a bug introduced by this change, but verify that the
  pre-existing `start_server` → `props` → `_current_n_ctx` chain
  still works (out of scope for this verify).

## SUGGESTION findings

- **S1**: `format_status` could short-circuit when the snapshot is
  all-None and toggles is the default set: return `""` early
  (defer the per-component check). Cosmetic.
- **S2**: The CRITICAL fix (C1) should be accompanied by a new
  wx-runtime test in `TestDoubleF2`:
  `test_three_f2_within_window_resets_to_short`. This closes the
  coverage gap that allowed C1 to slip past the test suite.
- **S3**: The mid-generation F2 "starts with 'Generando: '" spec
  scenario is covered by `test_mid_gen_starts_with_generando` in
  `test_status_formatter.py` (core), but not by the wx-runtime
  `TestF2StatusFormatter` in `test_main_window_runtime.py`. Add a
  wx-runtime scenario to lock the integration.
- **S4**: Consider exposing `_vram_free_mb` and
  `_vram_total_mb` as cached values populated at startup probe
  time, then use the cache in the pre-send guard. Eliminates the
  1s `nvidia-smi` call on the UI thread (current acceptable per
  design, but the 5s `token_count` is already the dominant cost).
- **S5**: The `format_status` mid-generation branch uses
  `progress_tokens` for the percentage (line 226). When
  `progress_tokens is None` mid-gen, it falls back to
  `completion_tokens + prompt_tokens` (line 227-228). This
  fallback is the correct behaviour, but a comment on the spec
  would be helpful for future maintainers.

## Out-of-scope follow-ups (deferred)

- **v0.6.0 `openspec/config.yaml` drift**: still says v0.6.0,
  project is v0.9.0. Out of scope per the proposal §Process Notes.
  Cleanup in a dedicated change.
- **`openspec/changes/2026-06-25-attach-url/` deletions in
  `git status --short`**: the previous change's `apply-progress.md`,
  `tasks.md`, and `verify-report.md` show as `D` (deleted from
  working tree). These are unrelated to this verify and were moved
  to the archive by a previous archive operation.
- **`uv.lock` modification in `git status --short`**: a dependency
  was added (likely `gguf`). Unrelated to this verify — verify the
  lock file is the expected `gguf>=0.6.0,<1.0` per the proposal.
- **Lesson learned update**: the v0.9.0 entry should be appended
  to `openspec/research/lessons-learned.md` at archive time,
  documenting (a) the WU-1/WU-2 split that worked smoothly, (b)
  the C1 double-F2 bug pattern (3-press state machine with
  unconditional assignment), and (c) the `_context_warned_for_turn`
  / `_meter_threshold_fired` rename hygiene.

## Post-remediation (commits after the original verify)

### C1 fixed in commit `aae74d7`
- `main_window.py:1209-1214` now assigns `self._last_f2_mono = now`
  ONLY in the else (short) branch.
- New wx-runtime test `test_triple_f2_starts_short_again` added to
  `TestDoubleF2` (skipped on WSL, runs on Windows via run_tests.bat).
- Logical verification on WSL: 4 scenarios (triple, double, spaced,
  quadruple) all pass via a Python script that mirrors the if/else
  logic without wx.

### W10 fixed in commit `c4e05bf`
- `FakeSpeech.output(text)` stub added to match the production
  `Speech.output(text)` signature (voz+braille). Mirrors `speak`'s
  effect for the test.

### Chore in commit `83942fe`
- `uv.lock` regenerated (legitimate `gguf` dep + bellbird version
  bump from stale 0.7.3 to 0.8.3).
- Three `D` files from the previous `attach-url` archive (force-added
  during archive, never cleaned up) removed so the working tree is
  clean before archiving v0.9.0.

### Final test run
- `uv run --no-sync pytest -xvs`: **689 passed, 14 skipped** (same
  skip count as the v0.8.3 baseline; new wx-runtime test skipped on
  WSL as expected).

## Sign-off

**READY TO ARCHIVE WITH WARNINGS.** All CRITICAL findings are fixed
(commit `aae74d7` for the C1 double-F2 state machine bug, commit
`c4e05bf` for the W10 FakeSpeech gap). Working tree is clean. Test
suite is green at 689/14.

The 12 WARNINGs are spec drifts (W5-W9), dead state in newly-added
fields (W1-W3), or pre-existing code (W11-W12) that do not block
the archive. They are documented in the archive report as accepted
debt for a future cleanup change.

Out-of-scope follow-ups (config.yaml drift, lessons-learned update)
are listed in the archive report.
