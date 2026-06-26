# Delta for `parameters` — v0.11.0 (preferences-hints-presets-reading)

> **Provenance**: `openspec/changes/2026-06-25-preferences-hints-presets-reading/proposal.md`
> § 4.2 (Parameter presets) and § 4.4 (Lectura tab — `text_utils.strip_markdown`
> reuse). Merges into the main `openspec/specs/parameters/spec.md` at archive
> time. Delta convention: ADDED sections only — the v0.3.0 / v0.7.2 fields
> and their scenarios are NOT touched.

## Added in v0.11.0 (preferences-hints-presets-reading)

### Requirement: `ParamPreset` dataclass schema (proposal §4.2)

`bellbird/core/preset.py` SHALL define `ParamPreset` as a
frozen `@dataclass(frozen=True)` with exactly 8 fields and the
documented types:

| Field | Type | Source mapping |
|---|---|---|
| `name` | `str` | user-supplied (TextEntryDialog) |
| `temperature` | `float` | `BellbirdConfig.temperature` |
| `min_p` | `float` | `BellbirdConfig.min_p` |
| `max_tokens` | `int` | `BellbirdConfig.max_tokens` |
| `top_p` | `float` | `BellbirdConfig.top_p` |
| `top_k` | `int` | `BellbirdConfig.top_k` |
| `repeat_penalty` | `float` | `BellbirdConfig.repeat_penalty` |
| `seed` | `int` | `BellbirdConfig.seed` (sentinel `-1` = aleatorio) |

The class MUST be wx-free (no `wx` import in
`bellbird/core/preset.py`, per AGENTS.md "core/ is wx-free").
A helper `build_preset_from_config(name: str, config:
BellbirdConfig) -> ParamPreset` SHALL copy the 7 sampler
fields from `config` into a new `ParamPreset(name, ...)`
value. `asdict(preset)` MUST round-trip back to a
`ParamPreset(**asdict(preset))` with equal values (regression
guard for JSON persistence via the `__dataclass_fields__`
filter in `core/config.py:92-93`).

#### Scenario: `ParamPreset` is a frozen dataclass with 8 fields

- GIVEN `from bellbird.core.preset import ParamPreset`
- WHEN the class is inspected
- THEN `dataclasses.fields(ParamPreset)` returns 8 `Field` entries
- AND the field names are exactly `{name, temperature, min_p, max_tokens, top_p, top_k, repeat_penalty, seed}` in that order
- AND the class is `frozen=True` (raising `dataclasses.FrozenInstanceError` on attribute assignment)

#### Scenario: `ParamPreset` is wx-free (regression guard)

- GIVEN the source of `bellbird/core/preset.py`
- WHEN the AST test greps for `import wx` or `from wx`
- THEN no match is found (the module imports only stdlib + `dataclasses`)

#### Scenario: `build_preset_from_config` copies the 7 sampler fields

- GIVEN `BellbirdConfig(temperature=1.10, min_p=0.08, max_tokens=2048, top_p=0.95, top_k=50, repeat_penalty=1.05, seed=42)`
- WHEN `preset = build_preset_from_config("experimento", config)` is called
- THEN `preset.name == "experimento"`
- AND `preset.temperature == 1.10`
- AND `preset.min_p == 0.08`
- AND `preset.max_tokens == 2048`
- AND `preset.top_p == 0.95`
- AND `preset.top_k == 50`
- AND `preset.repeat_penalty == 1.05`
- AND `preset.seed == 42`

#### Scenario: `build_preset_from_config` preserves the `seed == -1` sentinel

- GIVEN `BellbirdConfig(seed=-1)` (the "aleatorio" sentinel)
- WHEN `preset = build_preset_from_config("aleatorio", config)` is called
- THEN `preset.seed == -1` (NOT clamped to a non-negative value)

#### Scenario: `asdict(preset)` round-trips back to a `ParamPreset`

- GIVEN `preset = ParamPreset(name="x", temperature=0.7, min_p=0.05, max_tokens=512, top_p=0.9, top_k=40, repeat_penalty=1.1, seed=-1)`
- WHEN `asdict(preset)` is read
- AND `ParamPreset(**asdict(preset))` is constructed
- THEN the new `ParamPreset` has `name == "x"` AND equal 7 sampler fields (regression guard for JSON persistence)

#### Scenario: `ParamPreset` fields cannot be mutated (frozen contract)

- GIVEN `preset = ParamPreset(name="x", temperature=0.7, min_p=0.05, max_tokens=512, top_p=0.9, top_k=40, repeat_penalty=1.1, seed=-1)`
- WHEN `preset.temperature = 0.9` is attempted
- THEN `dataclasses.FrozenInstanceError` is raised (regression guard for frozen contract)

### Requirement: `_apply_preset_to_controls` semantics (proposal §4.2)

`bellbird/ui/preferences_dialog.py` SHALL define
`_apply_preset_to_controls(self, preset: ParamPreset) -> None`
as a private instance method on `PreferencesDialog` that
writes the 7 sampler fields into the matching widget
referenced by `self.pref_*` (the canonical `name=` strings
on the Modelo tab widgets). The method MUST NOT touch
`system_prompt`, `confirm_new_conversation`,
`tools_enabled`, or any other non-sampler field. The method
MUST NOT modify `self._config` — apply is in-memory only
until Aceptar is clicked (per the
`PreferencesDialog — Preset sub-panel` requirement in the
`app-configuration` delta).

The instance-method form is preferred over a free function
because the widgets are direct attributes of
`PreferencesDialog` (`self.pref_temp_slider`, etc.) and
passing them in a `controls` dict would be redundant.

#### Scenario: `_apply_preset_to_controls` updates the 7 sampler widgets

- GIVEN `preset = ParamPreset(name="creativo", temperature=1.10, min_p=0.08, max_tokens=2048, top_p=0.95, top_k=50, repeat_penalty=1.05, seed=42)`
- WHEN `dialog._apply_preset_to_controls(preset)` runs
- THEN `dialog.pref_temp_slider.GetValue() == 110` (i.e. `1.10 * 100`)
- AND `dialog.pref_min_p_slider.GetValue() == 8`
- AND `dialog.pref_max_tokens_spin.GetValue() == 2048`
- AND `dialog.pref_top_p_slider.GetValue() == 95`
- AND `dialog.pref_top_k_spin.GetValue() == 50`
- AND `dialog.pref_repeat_slider.GetValue() == 105`
- AND `dialog.pref_seed_spin.GetValue() == 42`

#### Scenario: `_apply_preset_to_controls` does NOT touch non-sampler fields (regression guard)

- GIVEN `BellbirdConfig(system_prompt="Eres útil", confirm_new_conversation=False, tools_enabled=True)`
- AND a preset is applied
- WHEN the dialog reads `self._config`
- THEN `self._config.system_prompt == "Eres útil"` (unchanged)
- AND `self._config.confirm_new_conversation is False` (unchanged)
- AND `self._config.tools_enabled is True` (unchanged)

#### Scenario: `_apply_preset_to_controls` is wx-side (regression guard)

- GIVEN the source of `bellbird/ui/preferences_dialog.py`
- WHEN the AST test greps for `def _apply_preset_to_controls`
- THEN a definition is present on the `PreferencesDialog` class
- AND the function is NOT defined in `core/preset.py` (the wx-widget write lives in `ui/`, not `core/`)

### Requirement: Modelo tab Preset sub-panel UI (proposal §4.2)

The **Modelo** tab SHALL contain a preset sub-panel
(`name="pref_presets_subpanel"`) BELOW the existing
`pref_max_tokens_spin` (and the `pref_presets_list`,
`pref_preset_apply_button`, `pref_preset_save_button`,
`pref_preset_delete_button` controls). The sub-panel
contracts (apply / save / delete) live in the
`app-configuration` delta; this requirement asserts only the
sub-panel structure and the 3-button order.

#### Scenario: preset sub-panel is below `pref_max_tokens_spin` (regression guard)

- GIVEN the source of `_build_model_page` in `bellbird/ui/preferences_dialog.py`
- WHEN the AST test inspects the order of `sizer.Add(...)` calls
- THEN the `pref_max_tokens_spin` Add call appears BEFORE any `pref_presets_*` Add call
- AND the `pref_presets_list`, `pref_preset_apply_button`, `pref_preset_save_button`, `pref_preset_delete_button` controls are present in that order

#### Scenario: 3 preset buttons are present in the Modelo tab [windows-only]

- GIVEN `MainWindow` is constructed with default `BellbirdConfig`
- WHEN the test inspects the "Modelo" tab
- THEN `pref_preset_apply_button` exists with label `"&Aplicar"`
- AND `pref_preset_save_button` exists with label `"&Guardar actual como…"`
- AND `pref_preset_delete_button` exists with label `"&Borrar"`
- AND each button is a direct descendant of the model_page panel

### Requirement: Lectura tab — `text_utils.strip_markdown` reuse (proposal §4.4)

The `filter_strip_markdown` toggle binds the Lectura tab to
the existing `core.text_utils.strip_markdown` function (no
new markdown-stripping implementation). The other 3
filters (`strip_urls`, `strip_emojis`, `strip_code_blocks`)
are regex-based and live in the new
`bellbird/core/text_filters.py` module. The full filter
pipeline (`apply_filters`) is defined in the new
`text-filters` capability spec; this requirement only
asserts the markdown-strip reuse (regression guard: the
existing `strip_markdown` is the canonical implementation,
no duplicate).

#### Scenario: `core/text_filters.py` does not redefine `strip_markdown` (regression guard)

- GIVEN the source of `bellbird/core/text_filters.py`
- WHEN the AST test greps for `def strip_markdown`
- THEN no match is found (markdown-stripping is imported from `core.text_utils`)
- AND the AST test greps for `from bellbird.core.text_utils import` AND finds `strip_markdown` in the import list

#### Scenario: `text_utils.strip_markdown` behavior is unchanged (regression guard)

- GIVEN `"**bold**"` as input
- WHEN `text_utils.strip_markdown("**bold**")` is called
- THEN the result is `"bold"` (the existing v0.3.0 contract is preserved)

#### Scenario: AST guard — `core/text_filters.py` is wx-free (regression guard)

- GIVEN the source of `bellbird/core/text_filters.py`
- WHEN the AST test greps for `import wx` or `from wx`
- THEN no match is found (the new module imports only stdlib + `core.config` + `core.text_utils`)

## Test strategy

- WSL: add `tests/core/test_preset.py` — `ParamPreset` frozen,
  8-field shape, `build_preset_from_config` copies the 7
  fields, `asdict` round-trip, wx-free (AST). The Lectura
  tab `strip_markdown` reuse lives in `tests/core/test_text_filters.py`
  (see the `text-filters` capability).
- Windows (`run_tests.bat` wx-runtime block): extend
  `tests/ui/test_preferences_dialog_static.py` with
  `TestV0110PresetSubpanel` (sub-panel order, 3 buttons,
  apply/save/delete behaviors). The `apply_preset_to_controls`
  wx-runtime coverage is part of `TestV0110PresetsSubpanel`
  in the `app-configuration` delta. Both classes MUST be
  registered in `run_tests.bat` under the wx-runtime
  pytest block.
