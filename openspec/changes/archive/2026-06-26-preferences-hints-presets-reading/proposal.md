# Proposal: Preferences Hints + Parameter Presets + Reading Filters

## Title & Status

**Change**: `2026-06-25-preferences-hints-presets-reading` → bumps Bellbird to **v0.11.0**.
**Status**: Proposal — ready for `sdd-spec` + `sdd-design` (parallel).

## Context & Problem

Bellbird's `PreferencesDialog` has grown to 8 tabs across v0.7–v0.10.0, but its accessibility surface is uneven: some controls have tooltips, most do not, ranges are inferred from widget bounds rather than declared, and there is no way to save a tuned sampler set. For a blind user navigating with NVDA, every unlabeled control is a "what does this do?" moment. This change consolidates the dialog: every control gets a one-sentence hint (function + range), every Spanish label gets a `&` mnemonic, a new **Lectura** tab exposes TTS filters, and a **presets** list lets users save and re-apply sampler sets. The `sound_theme` selector is already wired in the v0.10.0 Audio tab — we just confirm the coverage.

## Goal & Non-Goals

**Goal**
- A. **Uniform hints** — every control in all 8 tabs gets a short hint (function + range) via `SetToolTip` AND `SetHelpText`. Centralised in a `HINTS: dict[str, str]` table.
- B. **Parameter presets** — `BellbirdConfig.param_presets: list[ParamPreset]` with UI to create / select / apply / delete named sampler sets.
- C. **`&` mnemonics** — every Spanish label in all 8 tabs gets an accelerator hint (NVDA reads it, Alt+letter focuses the next control).
- D. **Lectura tab** — 4 toggles (markdown, URLs, emojis, code blocks) consumed by the TTS path.
- E. **Verify `sound_theme`** — confirm the v0.10.0 Audio-tab selector is covered by AST tests; no new UI work.

**Non-Goals**
- Do NOT rewrite the notebook to a flat `ParametersDialog`-style list (lesson §9.5: less accessible than the notebook with sliders/spins).
- Do NOT introduce a system-prompt / **personas** system (that is a separate future change). Presets and personas are explicitly distinct: presets = sampler set, personas = system prompt.
- Do NOT implement TTS call-site integration of the new filters in `Speech.speak` (the live screen-reader channel — applying filters there would break streaming per AGENTS.md lesson v0.6.0). The TTS hookup in `speak_with_system_voice` is **suggested** but non-critical for this change.
- Do NOT touch the v0.10.0 Audio tab's existing controls (voice, rate, notifications, sounds, sound_theme) — only add the missing hints and `&` mnemonics.

## Approach

### 4.1 Uniform hint per control
- New module-level `HINTS: dict[str, str]` in `bellbird/ui/preferences_dialog.py`. Keys are the existing `name=` strings (`pref_temp_slider`, `pref_max_tokens_spin`, `pref_seed_spin`, `pref_sound_theme_choice`, …). Values are exactly one Spanish sentence: `Función. Rango válido.`
- Helper `_apply_hint(control, hint_key: str) -> None` that sets both `SetToolTip(control, HINTS[hint_key])` and `SetHelpText(control, HINTS[hint_key])`. Called from each `_build_*_page` after the control is constructed.
- Hints are short — detailed documentation lives in `docs/` and README per `AGENTS.md` ("explicaciones largas fuera de la UI; los tooltips son cortos, la doc va a README").
- Coverage is auditable via the AST test: every control whose `name=` is in `HINTS` must be present in the dialog; every control present must be in `HINTS`.

### 4.2 Parameter presets
- New `core/preset.py`: `ParamPreset` = `@dataclass(frozen=True)` with `name: str` plus the 7 sampler fields — `temperature: float`, `min_p: float`, `max_tokens: int`, `top_p: float`, `top_k: int`, `repeat_penalty: float`, `seed: int`. Pure value type, no wx.
- Helper `build_preset_from_config(name: str, config: BellbirdConfig) -> ParamPreset` and `apply_preset_to_controls(preset: ParamPreset, controls: dict[str, wx.Window]) -> None` (the latter lives in `ui/preferences_dialog.py` because it touches widgets).
- New `BellbirdConfig` field: `param_presets: list[ParamPreset] = field(default_factory=list)`. Persists via the existing `save_config` / `load_config` round-trip (atomic write, UTF-8, `ensure_ascii=False`); `asdict()` serialises the dataclass.
- **UI**: in the **Modelo** tab, add a sub-panel "Ajustes preestablecidos" BELOW the existing samplers. `wx.ListBox` of preset names + 3 buttons (`Aplicar`, `Guardar actual como…`, `Borrar`). "Aplicar" fills the sampler controls + the `Ayuda de encaje` is unchanged. "Guardar" opens `wx.TextEntryDialog` for a name (validate: non-empty, not duplicate); empty name → speak "Nombre vacío", no-op. "Borrar" removes the selected preset from the in-memory list.
- Preset ↔ persona: a preset can be applied while a persona is active; the persona system (future change) reads `config.param_presets` and may reference a preset by name.

### 4.3 `&` mnemonics
- Audit shows `&` already on: `Estado (F2)` tab (full `toggle_labels`), `Avanzado`'s `&Ayuda de encaje`. The remaining 6 tabs (`General`, `Modelo`, `Chat`, `Herramientas`, `Atajos`, `Audio`) need `&` added to every `StaticText` and `CheckBox` label.
- The `&` is placed in the human-readable label (e.g. `label="&Temperatura:"`); the existing `name=` strings stay as-is (the `&` is not part of the MSAA name).
- The `&` is a non-printing accelerator — Alt+T focuses the next interactive control after the label per wx convention. Test: every Spanish label literal contains exactly one `&` preceding the mnemonic letter, and the letter is unique within the tab.

### 4.4 Pestaña "Lectura"
- Insert a new tab between **Chat** and **Herramientas** (preserves the current Audio/Atajos/Estado order at the end). Title: `"&Lectura"`.
- Controls — 4 `wx.CheckBox` with preceding `wx.StaticText` labels (each `&`-prefixed):
  - `&Quitar markdown al leer` → `filter_strip_markdown` (default ON; calls `text_utils.strip_markdown`).
  - `&Quitar URLs al leer` → `filter_strip_urls` (default ON; regex `https?://\S+` → `""`).
  - `&Quitar emojis al leer` → `filter_strip_emojis` (default ON; matches Unicode emoji ranges).
  - `&Quitar bloques de código al leer` → `filter_strip_code_blocks` (default ON; matches triple-backtick fences).
- New module `bellbird/core/text_filters.py`: `apply_filters(text: str, config: BellbirdConfig) -> str` — pure function, wx-free, returns the filtered text. **Order is fixed** (see Risk R1): `strip_markdown` → `strip_urls` → `strip_emojis` → `strip_code_blocks`. When a filter toggle is OFF, the corresponding step is a pass-through.
- `Speech.speak_with_system_voice` may call `apply_filters` before delegating to `SystemVoice.speak` (SUGGESTION, not CRITICAL — mark in the verify report). `Speech.speak` (the live screen-reader channel) is NOT touched.

### 4.5 Tema de sonido
- Already present: `BellbirdConfig.sound_theme: str = "default"` and `pref_sound_theme_choice` in the Audio tab (v0.10.0). NO new field, NO new UI. This change adds a hint entry to the `HINTS` table and the `&` mnemonic, and the AST test confirms coverage.

## Config fields

New fields on `BellbirdConfig` (`bellbird/core/config.py`, no migration needed — additive defaults):

| Field | Type | Default | Notes |
|---|---|---|---|
| `param_presets` `[v0.11.0]` | `list[ParamPreset]` | `[]` via `field(default_factory=list)` | named sampler sets; `ParamPreset` defined in `bellbird/core/preset.py` |
| `filter_strip_markdown` `[v0.11.0]` | `bool` | `True` | passes through `core.text_utils.strip_markdown` |
| `filter_strip_urls` `[v0.11.0]` | `bool` | `True` | drops `https?://\S+` |
| `filter_strip_emojis` `[v0.11.0]` | `bool` | `True` | drops Unicode emoji ranges |
| `filter_strip_code_blocks` `[v0.11.0]` | `bool` | `True` | drops triple-backtick fences |

`sound_theme` is unchanged (already in v0.10.0). Total after v0.11.0: **39 fields** (34 + 5).

## Files to add / modify

**Add (core, wx-free)**
- `bellbird/core/preset.py` — `ParamPreset` frozen dataclass + `build_preset_from_config` helper.
- `bellbird/core/text_filters.py` — `apply_filters(text, config)` pure function with the 4 filter steps.

**Add (ui, wx)**
- `bellbird/ui/lectura_panel.py` (optional split) — `_build_lectura_page` extracted if `_build_chat_page` becomes too long; otherwise inline in `preferences_dialog.py`.

**Modify**
- `bellbird/core/config.py` — add the 5 fields + import `ParamPreset`.
- `bellbird/core/speech.py` — OPTIONAL `speak_with_system_voice` calls `apply_filters` (SUGGESTION).
- `bellbird/ui/preferences_dialog.py` — `HINTS` dict + `_apply_hint` helper, `&` on every label, presets sub-panel in **Modelo**, **Lectura** tab, hint + mnemonic for the Audio tab's `sound_theme` control.
- `pyproject.toml` — bump `version = "0.11.0"`.

**Tests**
- `tests/core/test_preset.py` (new) — round-trip `ParamPreset` + `build_preset_from_config` + `asdict` JSON.
- `tests/core/test_text_filters.py` (new) — 4 filters ON / OFF, order respected, no-op when all OFF, idempotent.
- `tests/core/test_config.py` (extend) — defaults match the table above; forward-compat (`__dataclass_fields__` filter accepts the 5 new field names).
- `tests/ui/test_preferences_dialog_static.py` (extend) — every control's `name=` is in `HINTS`; every `StaticText` / `CheckBox` label contains exactly one `&`; `param_presets` list persists.
- `tests/ui/test_lectura_tab_static.py` (new) — Lectura tab present, 4 checkboxes exist with the right `name=` + `&` prefix.
- `run_tests.bat` — register any new wx-runtime tests (the WSL loop is unchanged: `core/` + AST of UI).

**Specs (delta)**
- `openspec/specs/app-configuration/spec.md` — add the 5 new fields to the field table.
- `openspec/specs/parameters/spec.md` — delta: presets in the sampler context (presets are named sets of the same 7 fields).
- `openspec/specs/text-filters/spec.md` (NEW capability) — `apply_filters` order, toggles, idempotence.

## Open questions & risks

- **R1** — `apply_filters` **order matters**: strip markdown first (removes code fences, links), then URLs (avoid the link-text issue), then emojis, then code blocks (catches residual fences). Documented in the new `text-filters` spec.
- **R2** — Some labels are already long (e.g. `"Penalización de repetición:"`); `&` does not change display but is required for NVDA. Pick mnemonic letters that do not clash within the same tab (audit collision: `&M` and `&M` for Mensajes + Modelo across tabs is fine because Alt+letter navigation is per-dialog and per-focus-context, but a within-tab collision is not).
- **R3** — **Audio** vs **Lectura** naming: Audio = voz del sistema + notificaciones + sonidos (output channel). Lectura = filtros de TTS (text shaping). Complementary, not duplicate. Documented in the Audio tab help text.
- **R4** — `ParamPreset.seed` is a sentinel `-1` (aleatorio). The existing `pref_seed_spin` already allows `min=-1` (Avanzado tab). When a preset is applied, the spin updates to the preset's value verbatim.
- **R5** — `apply_filters` is pure and wx-free. Full coverage runs in WSL.
- **R6** — The dialog currently fits at `620x520` with 8 tabs. The 9th tab (Lectura, ~120px tall) and the Modelo-tab preset sub-panel (~140px) push the height past 520. Bump to `720x600` and add an AST test that asserts the size in `__init__` is `(720, 600)`.
- **R7** — `&` collision check: at most one `&` per label literal; verify in the AST test that `re.search(r"&[^& ]", label)` matches exactly once per Spanish label.

## Acceptance criteria

- [ ] `uv run --no-sync pytest -xvs` green in WSL.
- [ ] Every control in `preferences_dialog.py` has a hint entry in `HINTS` AND `SetToolTip` + `SetHelpText` are set.
- [ ] `param_presets` round-trips through `save_config` / `load_config` (JSON file → list of `ParamPreset`).
- [ ] **Lectura** tab exists, inserted between Chat and Herramientas, with 4 toggles.
- [ ] Every Spanish label literal in all 9 tabs has exactly one `&` preceding a non-space letter.
- [ ] `apply_filters` is unit-tested for: 4 filters ON, 4 filters OFF, order preserved, idempotent, handles empty input.
- [ ] Dialog size bumped to `(720, 600)` and the AST test pins it.

## Workload forecast

Estimated **~800-1100 LOC** total (presets: ~150, text_filters: ~120, config: ~30, preferences dialog: ~400-500 incl. hints & mnemonics, tests: ~300, spec deltas: ~50). Two work units recommended:

- **WU-1 (core + tests, ~500 LOC)**: `core/preset.py`, `core/text_filters.py`, `core/config.py` (5 fields), `tests/core/test_preset.py`, `tests/core/test_text_filters.py`, `tests/core/test_config.py` extension. Pure, wx-free, fully WSL-runnable.
- **WU-2 (UI + wx-tests + spec deltas, ~500 LOC)**: `preferences_dialog.py` (HINTS, `&`, presets sub-panel, Lectura tab, size bump), `tests/ui/test_preferences_dialog_static.py` extension, `tests/ui/test_lectura_tab_static.py`, 3 spec deltas, `pyproject.toml` bump, `run_tests.bat` registration.

400-line budget risk: **Medium** (each WU is at the budget edge). Recommend serial WU-1 → WU-2 delivery; the spec/design phases can run in parallel after the proposal.
