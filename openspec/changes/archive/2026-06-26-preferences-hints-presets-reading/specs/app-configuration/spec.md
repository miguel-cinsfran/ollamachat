# Delta for `app-configuration` — v0.11.0 (preferences-hints-presets-reading)

> **Provenance**: `openspec/changes/2026-06-25-preferences-hints-presets-reading/proposal.md`
> § 4.1 (Uniform hint per control), § 4.2 (Parameter presets), § 4.4 (Pestaña "Lectura").
> Merges into the main `openspec/specs/app-configuration/spec.md` at archive time.
> Delta convention: ADDED sections only — the existing v0.7.0 → v0.10.0 fields
> and their scenarios are NOT touched. Total post-v0.11.0: **39 fields**
> (34 + 5: `param_presets` + 4 `filter_strip_*` toggles).

## Added in v0.11.0 (preferences-hints-presets-reading)

### Requirement: `param_presets` round-trips via the standard `__dataclass_fields__` filter (proposal §4.2)

`BellbirdConfig` SHALL add the field
`param_presets: list[ParamPreset] = field(default_factory=list)` [v0.11.0],
where `ParamPreset` is a frozen dataclass defined in
`bellbird/core/preset.py` with the 7 sampler fields
(`temperature`, `min_p`, `max_tokens`, `top_p`, `top_k`,
`repeat_penalty`, `seed`) plus a `name: str`. The field MUST
round-trip via the existing `save_config` / `load_config`
pipeline (atomic write, UTF-8, `ensure_ascii=False`); the
`__dataclass_fields__` filter at `core/config.py:92-93` is the
forward-compat mechanism. NO entry is added to `_MIGRATIONS`
(per the v0.8.2 / v0.9.0 / v0.10.0 forward-compat pattern).
The default empty list is per-instance (each fresh
`BellbirdConfig()` gets its own `list[ParamPreset]`).

#### Scenario: default is per-instance empty list (regression guard)

- GIVEN two fresh `BellbirdConfig()` instances `a` and `b`
- WHEN `a.param_presets.append(ParamPreset(name="x", temperature=0.7, min_p=0.05, max_tokens=512, top_p=0.9, top_k=40, repeat_penalty=1.1, seed=-1))` runs
- THEN `b.param_presets == []` (not shared; `default_factory` honored)

#### Scenario: round-trip preserves `param_presets` (JSON form)

- GIVEN `BellbirdConfig(param_presets=[ParamPreset(name="creativo", temperature=1.10, min_p=0.08, max_tokens=2048, top_p=0.95, top_k=50, repeat_penalty=1.05, seed=42)])` and `tmp_path`
- WHEN `save_config(cfg, tmp_path/"c.json")` runs and `load_config()` reads it back
- THEN the loaded `param_presets` has length `1`
- AND the loaded `param_presets[0].name == "creativo"`
- AND the loaded `param_presets[0].temperature == 1.10`
- AND the loaded `param_presets[0].seed == 42`
- AND the loaded `param_presets[0].max_tokens == 2048`

#### Scenario: missing `param_presets` in old config falls back to default

- GIVEN a `config.json` from v0.10.0 with NO `param_presets` key
- WHEN `load_config()` runs on v0.11.0
- THEN the loaded `param_presets == []` (dataclass default applied; no `KeyError` raised)

#### Scenario: unknown future keys in JSON are dropped (forward-compat, v0.11.0)

- GIVEN a `config.json` containing `param_presets` AND a hypothetical `future_field` key
- WHEN `load_config()` runs
- THEN `param_presets` is loaded
- AND `future_field` is silently dropped
- AND no `AttributeError` is raised

#### Scenario: AST guard — `_MIGRATIONS` has no new entry for `param_presets`

- GIVEN the source of `bellbird/core/config.py`
- WHEN the AST test inspects the `_MIGRATIONS` dict literal
- THEN exactly one entry exists: `("max_tokens", (512, 4096))`
- AND no entry references `param_presets`, `filter_strip_markdown`, `filter_strip_urls`, `filter_strip_emojis`, or `filter_strip_code_blocks`

### Requirement: 4 reading-filter toggles default to ON (proposal §4.4)

`BellbirdConfig` SHALL add the 4 boolean fields
`filter_strip_markdown`, `filter_strip_urls`,
`filter_strip_emojis`, `filter_strip_code_blocks` [v0.11.0],
all with default `True`. The fields MUST round-trip via the
existing `save_config` / `load_config` pipeline with no
`_MIGRATIONS` entry (forward-compat per the v0.8.2
`__dataclass_fields__` pattern). When all 4 toggles are
`True`, the TTS path applies the corresponding filter step
in the fixed order: `strip_markdown` → `strip_urls` →
`strip_emojis` → `strip_code_blocks` (proposal R1). When
all 4 toggles are `False`, `apply_filters` MUST be a no-op
that returns the input unchanged (see the
`text-filters` capability).

#### Scenario: 4 new filter toggles default to True

- GIVEN a fresh `BellbirdConfig()`
- WHEN the field values are read
- THEN `filter_strip_markdown is True`
- AND `filter_strip_urls is True`
- AND `filter_strip_emojis is True`
- AND `filter_strip_code_blocks is True`

#### Scenario: 4 new filter toggles round-trip via save+load

- GIVEN `BellbirdConfig(filter_strip_markdown=False, filter_strip_urls=True, filter_strip_emojis=False, filter_strip_code_blocks=True)` and `tmp_path`
- WHEN `save_config(cfg, tmp_path/"c.json")` runs and `load_config()` reads it back
- THEN the loaded `filter_strip_markdown is False`
- AND the loaded `filter_strip_urls is True`
- AND the loaded `filter_strip_emojis is False`
- AND the loaded `filter_strip_code_blocks is True`

#### Scenario: missing filter toggles in old config fall back to True

- GIVEN a `config.json` from v0.10.0 with NO `filter_strip_*` keys
- WHEN `load_config()` runs on v0.11.0
- THEN all 4 toggles default to `True` (the all-ON first-run invariant — proposal §4.4)

### Requirement: `PreferencesDialog` — Lectura Tab with 4 toggles (proposal §4.4)

`PreferencesDialog` SHALL insert a new tab labeled `"&Lectura"`
BETWEEN "Chat" and "Herramientas" in the `wx.Notebook`. The
post-v0.11.0 tab order MUST be: **General → Modelo → Chat →
Lectura → Herramientas → Avanzado → Atajos → Audio → Estado
(F2)** (9 tabs total). The Lectura tab SHALL contain 4
`wx.CheckBox` controls (one per filter toggle), each preceded
in the sizer by a `wx.StaticText` label with a mnemonic `&`,
and each MUST have the `name=` strings exactly
`"pref_filter_strip_markdown"`, `"pref_filter_strip_urls"`,
`"pref_filter_strip_emojis"`,
`"pref_filter_strip_code_blocks"`. The dialog's
`_apply_config` MUST write the 4 boolean values into
`self._config.filter_strip_*` BEFORE `EndModal(wx.ID_OK)`.

#### Scenario: Lectura tab is the third tab in source (regression guard)

- GIVEN the source of `bellbird/ui/preferences_dialog.py`
- WHEN the AST test greps for `notebook.AddPage(panel, "...")` calls in `_build_ui`
- THEN `"Chat"` is at position 3 and `"&Lectura"` is at position 4
- AND `"Herramientas"` is at position 5 (Lectura inserted BETWEEN Chat and Herramientas)

#### Scenario: 4 CheckBoxes exist with the documented `name=` strings [windows-only]

- GIVEN `MainWindow` is constructed with default `BellbirdConfig`
- WHEN the test inspects the "Lectura" tab
- THEN exactly 4 `wx.CheckBox` controls are present
- AND their `name=` attributes are `pref_filter_strip_markdown`, `pref_filter_strip_urls`, `pref_filter_strip_emojis`, `pref_filter_strip_code_blocks` in that order
- AND each CheckBox is preceded (in the sizer) by a `wx.StaticText` label with a mnemonic `&`

#### Scenario: 4 CheckBoxes reflect the current config defaults (all ON) [windows-only]

- GIVEN `BellbirdConfig()` (defaults: all 4 toggles True)
- WHEN the dialog is constructed
- THEN `pref_filter_strip_markdown.GetValue() is True`
- AND `pref_filter_strip_urls.GetValue() is True`
- AND `pref_filter_strip_emojis.GetValue() is True`
- AND `pref_filter_strip_code_blocks.GetValue() is True`

#### Scenario: unchecking a filter toggle takes effect on the next read (regression guard) [windows-only]

- GIVEN the user unchecks `pref_filter_strip_urls` and clicks Aceptar
- WHEN the next TTS read happens
- THEN `cfg.filter_strip_urls is False` (the toggle was persisted)

#### Scenario: Cancel leaves the 4 toggles untouched [windows-only]

- GIVEN `BellbirdConfig(filter_strip_urls=False)`
- WHEN the user unchecks `pref_filter_strip_markdown` and dismisses with Cancel
- THEN the caller's `filter_strip_markdown` is unchanged (still `True`) AND the caller's `filter_strip_urls` is unchanged (still `False`)

### Requirement: `PreferencesDialog` — Preset sub-panel in Modelo tab (proposal §4.2)

`PreferencesDialog._build_model_page` SHALL add a sub-panel
"Ajustes preestablecidos" BELOW the existing samplers (below
`pref_max_tokens_spin`) containing: a `wx.ListBox`
(`name="pref_presets_list"`) populated from
`self._config.param_presets` (each entry shows
`preset.name`), and 3 `wx.Button` controls:
`"pref_presets_apply"` (label `"&Aplicar"`),
`"pref_presets_save"` (label `"&Guardar actual
como…"`), and `"pref_presets_delete"` (label
`"&Borrar"`). "Aplicar" fills the sampler sliders/spins
with the selected preset's values IN-MEMORY (does NOT modify
`self._config` until Aceptar). "Guardar actual como…"
opens a `wx.TextEntryDialog` for a name; empty name → speak
`"Nombre vacío"`, no-op; duplicate name → speak
`"Ya existe"`, no-op; valid name → appends a new
`ParamPreset` built from the current sampler control values
to `self._config.param_presets`. "Borrar" removes the
selected preset from `self._config.param_presets`; empty
selection → no-op.

#### Scenario: preset ListBox reflects `param_presets` (regression guard) [windows-only]

- GIVEN `BellbirdConfig(param_presets=[ParamPreset(name="creativo", temperature=1.1, min_p=0.08, max_tokens=2048, top_p=0.95, top_k=50, repeat_penalty=1.05, seed=42)])`
- WHEN the dialog is constructed
- THEN `pref_presets_list.GetItems() == ["creativo"]`

#### Scenario: Aplicar fills samplers in-memory, does NOT touch config [windows-only]

- GIVEN a preset `"creativo"` is selected in `pref_presets_list`
- WHEN the user clicks `pref_presets_apply`
- THEN `pref_temp_slider.GetValue() == 110` (i.e. `1.10 * 100`)
- AND `pref_min_p_slider.GetValue() == 8`
- AND `pref_max_tokens_spin.GetValue() == 2048`
- AND `pref_seed_spin.GetValue() == 42`
- AND `self._config.temperature == 0.70` (UNCHANGED — apply is in-memory only)
- AND `self._config.min_p == 0.05` (UNCHANGED)
- AND `self._config.seed == -1` (UNCHANGED)

#### Scenario: Aplicar does NOT touch `system_prompt` or non-sampler fields [windows-only]

- GIVEN `BellbirdConfig(system_prompt="Eres útil", confirm_new_conversation=False)`
- AND a preset is selected and the user clicks `pref_presets_apply`
- THEN `self._config.system_prompt == "Eres útil"` (NOT touched)
- AND `self._config.confirm_new_conversation is False` (NOT touched)

#### Scenario: Guardar actual como… with empty name is a no-op [windows-only]

- GIVEN a fresh dialog
- WHEN the user clicks `pref_presets_save` AND enters `""` in the TextEntryDialog AND clicks OK
- THEN `self._config.param_presets == []` (no preset added)
- AND `speech.speak("Nombre vacío", interrupt=False)` is called (or would be if `speech` is wired; OK to call with the parent chain)

#### Scenario: Guardar actual como… with duplicate name is a no-op [windows-only]

- GIVEN `BellbirdConfig(param_presets=[ParamPreset(name="creativo", ...)])`
- WHEN the user clicks `pref_presets_save` AND enters `"creativo"` AND clicks OK
- THEN `len(self._config.param_presets) == 1` (no duplicate)
- AND `speech.speak("Ya existe", interrupt=False)` is called

#### Scenario: Guardar actual como… with valid name appends a new preset [windows-only]

- GIVEN a fresh dialog with `pref_temp_slider.GetValue() == 80`
- AND `pref_min_p_slider.GetValue() == 10`
- AND `pref_max_tokens_spin.GetValue() == 1024`
- AND `pref_top_p_slider.GetValue() == 95`
- AND `pref_top_k_spin.GetValue() == 50`
- AND `pref_repeat_slider.GetValue() == 110`
- AND `pref_seed_spin.GetValue() == 42`
- WHEN the user clicks `pref_presets_save` AND enters `"experimento"` AND clicks OK
- THEN `len(self._config.param_presets) == 1`
- AND `self._config.param_presets[0].name == "experimento"`
- AND `self._config.param_presets[0].temperature == 0.80`
- AND `self._config.param_presets[0].seed == 42`
- AND `self._config.param_presets[0].max_tokens == 1024`

#### Scenario: Borrar with selection removes the preset [windows-only]

- GIVEN `BellbirdConfig(param_presets=[ParamPreset(name="a", ...), ParamPreset(name="b", ...)])`
- AND `pref_presets_list.GetSelection() == 1` (`"b"` selected)
- WHEN the user clicks `pref_presets_delete`
- THEN `len(self._config.param_presets) == 1`
- AND `self._config.param_presets[0].name == "a"`

#### Scenario: Borrar with no selection is a no-op [windows-only]

- GIVEN `BellbirdConfig(param_presets=[ParamPreset(name="a", ...)])`
- AND `pref_presets_list.GetSelection() == wx.NOT_FOUND`
- WHEN the user clicks `pref_presets_delete`
- THEN `len(self._config.param_presets) == 1` (no removal)

### Requirement: `HINTS` table — uniform hint per control (proposal §4.1)

`bellbird/ui/preferences_dialog.py` SHALL define a module-level
`HINTS: dict[str, str]` whose keys are the existing
control `name=` strings (e.g. `pref_temp_slider`,
`pref_max_tokens_spin`, `pref_seed_spin`,
`pref_sound_theme_choice`) and whose values are exactly one
Spanish sentence: `Función. Rango válido.` (function + valid
range, per `AGENTS.md`'s "tooltips cortos, la doc va a
README" rule). A helper `_apply_hint(control, hint_key: str)
-> None` SHALL set both `SetToolTip(control, HINTS[hint_key])`
AND `SetHelpText(control, HINTS[hint_key])` and SHALL be
called from each `_build_*_page` after the control is
constructed. Coverage MUST be auditable via AST: every
control whose `name=` is in `HINTS` MUST be present in the
dialog; every control present MUST be in `HINTS` (no
orphans, no missing entries).

#### Scenario: every HINTS key matches a control `name=` in the dialog source (AST guard)

- GIVEN the source of `bellbird/ui/preferences_dialog.py`
- WHEN the AST test extracts the `HINTS` dict keys
- AND the AST test extracts all `name=` arguments in `wx.Slider`, `wx.SpinCtrl`, `wx.CheckBox`, `wx.ListBox`, `wx.Button`, `wx.TextCtrl`, `wx.Choice` constructors (excludes `wx.StaticText` which is not interactive; includes `wx.Notebook`)
- THEN `set(HINTS.keys()) <= set(control_name_values)` (no orphan hint)
- AND `set(control_name_values) <= set(HINTS.keys())` (no control without a hint)

#### Scenario: HINTS values are non-empty Spanish sentences

- GIVEN the `HINTS` dict
- WHEN each value is read
- THEN it is a non-empty string
- AND it contains at least one Spanish character (regex `[áéíóúñü¿¡]` or similar — the regression guard against English-only entries)

#### Scenario: `pref_temp_slider` hint mentions the range

- GIVEN a fresh `PreferencesDialog` instance
- WHEN `pref_temp_slider.GetToolTipText()` is read
- THEN it contains `"Temperatura"` (the function name) AND a range hint covering `0.00 a 2.00`

#### Scenario: `pref_max_tokens_spin` hint mentions the range

- GIVEN a fresh `PreferencesDialog` instance
- WHEN `pref_max_tokens_spin.GetToolTipText()` is read
- THEN it contains `"tokens"` AND a range hint covering `64 a 8192`

#### Scenario: `pref_sound_theme_choice` hint exists (regression guard, v0.10.0 control) [windows-only]

- GIVEN a fresh `PreferencesDialog` instance
- WHEN `pref_sound_theme_choice.GetToolTipText()` is read
- THEN it is a non-empty Spanish sentence (the v0.10.0 control has a hint in v0.11.0)
- AND the help text (`GetHelpText()`) is the same string

### Requirement: `&` mnemonics on every Spanish label (proposal §4.3)

Every `wx.StaticText` and `wx.CheckBox` label literal in all
9 tabs of `preferences_dialog.py` SHALL contain exactly one
`&` character preceding a non-space letter, where the
letter is unique within the tab (per proposal R7).
Regression guards: existing `&`s in **Estado (F2)** (full
`toggle_labels` set) and the `&Ayuda de encaje` StaticText
in **Avanzado** MUST be preserved. The `&` is placed in the
human-readable label (e.g. `label="&Temperatura:"`); the
existing `name=` strings stay as-is (`&` is not part of the
MSAA name).

#### Scenario: every `StaticText` and `CheckBox` `label=` contains exactly one `&` (AST guard)

- GIVEN the source of `bellbird/ui/preferences_dialog.py`
- WHEN the AST test extracts the `label=` argument of every `wx.StaticText`, `wx.CheckBox` constructor
- THEN every literal matches `re.search(r"&[^& ]", label)` exactly once
- AND every literal contains the `&` character

#### Scenario: `&` letter is unique within the tab (AST guard, proposal R2)

- GIVEN the source of `bellbird/ui/preferences_dialog.py`
- WHEN the AST test groups `&`-prefixed labels by `_build_*_page` method
- THEN no two labels in the same method share the same letter immediately after `&` (e.g. `&Temperatura` and `&Texto` would collide on `T`)

#### Scenario: existing `&Ayuda de encaje` is preserved (regression guard)

- GIVEN the source of `bellbird/ui/preferences_dialog.py`
- WHEN the AST test greps for `label="&Ayuda de encaje:"` in `_build_advanced_page`
- THEN exactly one match is found (regression guard: the v0.9.0 `&` is not removed)

#### Scenario: Estado (F2) `&` mnemonics are preserved (regression guard, v0.9.0)

- GIVEN the source of `bellbird/ui/preferences_dialog.py`
- WHEN the AST test greps for `toggle_labels` in `_build_status_page`
- THEN all 11 `&`-prefixed labels (`&Modelo`, `&Porcentaje de contexto`, `&Máx tokens/respuesta`, `&Servidor`, `&VRAM libre`, `&Encaje`, `&Mensajes`, `&Temperatura`, `&Top-p`, `&Tok/s última`, `&Generando`) are present

### Requirement: Dialog size bumped to (720, 600) (proposal R6)

`PreferencesDialog.__init__` SHALL call `self.SetSize((720, 600))`
(after the v0.10.0 default of `(620, 520)`). The 9-tab layout
with the Lectura tab (~120 px tall) and the Modelo-tab preset
sub-panel (~140 px) requires the additional ~100 px of height
and ~100 px of width.

#### Scenario: dialog size is (720, 600) (regression guard)

- GIVEN the source of `bellbird/ui/preferences_dialog.py`
- WHEN the AST test greps for `SetSize(`
- THEN a call `SetSize((720, 600))` is present in `__init__`
- AND the call is the last `SetSize(` call (no override after)

#### Scenario: dialog size after `__init__` matches the documented size [windows-only]

- GIVEN a `PreferencesDialog` is constructed
- WHEN `dlg.GetSize()` is read
- THEN it is `(720, 600)` (or `wx.Size(720, 600)`-equivalent)

## Test strategy

- WSL: extend `tests/core/test_config.py` with `TestV0110Config`
  class — `param_presets` round-trip, missing-key forward-compat,
  per-instance default; `filter_strip_*` defaults all True, round-trip,
  missing-key forward-compat. Extend the AST guard to confirm
  `_MIGRATIONS` has no new entry.
- WSL: add `tests/core/test_preset.py` — `ParamPreset` frozen,
  `build_preset_from_config` copies the 7 fields, `asdict` round-trip.
- WSL: add `tests/core/test_text_filters.py` — see the
  `text-filters` capability.
- Windows (`run_tests.bat` wx-runtime block): extend
  `tests/ui/test_preferences_dialog_static.py` with
  `TestV0110HINTS` (HINTS coverage), `TestV0110Mnemonics`
  (`&` count + uniqueness + Estado regression guard),
  `TestV0110DialogSize` (size pin), `TestV0110PresetsSubpanel`
  (apply/save/delete behaviors), `TestV0110LecturaTab`
  (4 checkboxes + name= + order). All 5 classes MUST be
  registered in `run_tests.bat` under the wx-runtime pytest block.
