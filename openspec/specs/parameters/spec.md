# Parameters Capability Specification

<!-- Added in v0.7.2 (samplers-modernos-min-p-seed-stop): min_p, seed, stop sampling controls; two-perilla Modelo tab; Avanzado absorbs top_p/k/repeat + seed/stop. Merged from openspec/changes/archive/2026-06-25-samplers-modernos-min-p-seed-stop/specs/parameters/spec.md -->

## Purpose

Defines the model selection controls and the `options` dict built at send time. The model selector (`wx.ComboBox`), scan, browse, and use-model buttons occupy a top horizontal `wx.BoxSizer` row preceded by `wx.StaticText` labels. All sampling/parameter fields are editable through the `PreferencesDialog` and read at send time from `self._config`. The `options` dict is consumed by `LlamaClient.chat_stream` and forwarded verbatim to the OpenAI-compatible endpoint.

The 2026 sampling consensus is `temperature + min_p`; the **Modelo** tab exposes only those two primary knobs (plus `system_prompt` and `max_tokens`). The **Avanzado** tab holds the remaining samplers (`top_p`, `top_k`, `repeat_penalty`) plus reproducibility and output-shape controls (`seed`, `stop`). The two `options`-building sites in `send_message` and `_continue_after_tool` produce byte-identical dicts.

## Requirements

### Requirement: Model Selector and Refresh

The model selector SHALL be a `wx.ComboBox` named `model_selector` created as a direct child of the `MainWindow` Frame (parent=`self`), placed in the top horizontal `BoxSizer` row. The selector SHALL be preceded in the sizer by `wx.StaticText("Modelo:")`. A `wx.Button` named `scan_models_button` with the label `"Buscar modelos"` SHALL be placed adjacent in the same row. A `wx.Button` named `browse_model_button` with the label `"Explorar..."` SHALL also be in the same row, opening a file picker for `.gguf` files. The selector SHALL maintain a `_basename_to_path` map (Frame-level attribute) that resolves a selected basename or typed value to an absolute path.

(Previously: both the selector and the refresh button were children of `ParamsPanel`, the selector was a `wx.Choice`, and the refresh button was named `refresh_models_button`. `ParamsPanel` is deleted by this refactor.)

#### Scenario: Initial model selector

- GIVEN a fresh `MainWindow`
- WHEN the frame is constructed
- THEN `model_selector` is a child of the Frame (not of any child panel)
- AND `model_selector.GetCount() == 0`
- AND `scan_models_button.GetLabel() == "Buscar modelos"`
- AND `model_selector.GetName() == "model_selector"`
- AND `scan_models_button.GetName() == "scan_models_button"`

#### Scenario: `set_models` repopulates and selects first

- GIVEN `model_selector` is empty
- WHEN `main_window.set_models(["llama3:latest", "llava:13b"])` is called
- THEN `model_selector.GetCount() == 2`
- AND `model_selector.GetString(0) == "llama3:latest"`
- AND `model_selector.GetSelection() == 0`
- AND `self._basename_to_path["llama3:latest"]` resolves to the absolute path the basename was mapped from

#### Scenario: Scan button emits event [windows-only]

- GIVEN `scan_models_button` has focus
- WHEN the user activates it (Enter or Space)
- THEN an `EVT_BUTTON` event fires
- AND `MainWindow._scan_models` calls `LlamaClient.list_models()` (or the local model-folder scan) and feeds the result back to `self.set_models(...)` (Frame-level method, not a panel method)

### Requirement: `MainWindow.get_model` Accessor

`MainWindow.get_model() -> str` SHALL return the absolute path of the currently selected model, resolved through `self._basename_to_path` if the selector's current value is a basename from the dropdown, or returned verbatim if the user typed/pasted an absolute path. If the trimmed value is empty or the basename is not in the map, the method SHALL return `""`.

(Previously: `ParamsPanel.get_model()` returned the selector's string verbatim; the basename-to-path resolution did not exist. The new method enforces absolute-path semantics.)

#### Scenario: Selected model resolves to absolute path

- GIVEN `set_models(["C:\\m\\a.gguf"])` was called and the user selected `"a.gguf"`
- WHEN `main_window.get_model()` is called
- THEN the result is `"C:\\m\\a.gguf"` (the absolute path the basename was mapped from)

#### Scenario: Empty selection returns `""`

- GIVEN the selector is empty
- WHEN `main_window.get_model()` is called
- THEN the result is `""`

#### Scenario: Typed absolute path is returned verbatim

- GIVEN the user typed `"D:\\models\\phi-3.gguf"` directly into the selector
- WHEN `main_window.get_model()` is called
- THEN the result is `"D:\\models\\phi-3.gguf"`

## Added in v0.3.0

### Requirement: `use_model_button` Loads and Starts in One Click

`MainWindow` SHALL provide a `wx.Button` named `use_model_button` with the label `"Usar modelo"`, placed in the same top horizontal `BoxSizer` row as `model_selector`, `scan_models_button`, and `browse_model_button`. The button MUST be preceded in the sizer by a `wx.StaticText` label (or grouped under a parent label) and MUST use only `wx.BoxSizer` for the row.

`MainWindow._on_use_model` SHALL: (1) call `self.get_model()` (Frame-level) to obtain the path, (2) disable `use_model_button` and `restart_server_button`, (3) speak `"Iniciando servidor con <basename>..."`, (4) call `LlamaRunner.start_server(...)` in a background thread (see `app-shell` v0.3.0 Background-Thread Model Loading), and (5) on completion re-enable or remain disabled per the result.

`model_selector` is a `wx.ComboBox` and MUST bind BOTH `EVT_COMBOBOX` and `EVT_TEXT`. The enable logic for `use_model_button` MUST re-evaluate whenever either event fires: the button is enabled if and only if the trimmed value of `model_selector.GetValue()` resolves via `_basename_to_path` OR is itself an absolute path to an existing `.gguf` file.

(Previously: the button was a child of `ParamsPanel`. The handler still lived on `MainWindow` but read the path through `params_panel.get_model()`. `ParamsPanel` is deleted by this refactor.)

#### Scenario: Button is present and named

- **GIVEN** a fresh `MainWindow`
- **WHEN** the source is inspected
- **THEN** `use_model_button.GetName() == "use_model_button"`
- **AND** the button is a direct child of the Frame (parent=`self`)
- **AND** a `wx.StaticText` label precedes the row

#### Scenario: Disabled when no model selected

- **GIVEN** `set_models([])` was called and the selector is empty
- **WHEN** `use_model_button` is checked
- **THEN** `use_model_button.IsEnabled() is False`

#### Scenario: Enabled when a model is selected

- **GIVEN** `set_models(["C:\\m\\a.gguf"])` and selection is index 0
- **WHEN** `use_model_button` is checked
- **THEN** `use_model_button.IsEnabled() is True`

#### Scenario: `add_model` re-evaluates enable state

- **GIVEN** the selector had 0 items and `use_model_button` was disabled
- **WHEN** `MainWindow.add_model("C:\\m\\b.gguf")` is called
- **THEN** `use_model_button.IsEnabled() is True`

#### Scenario: User types or pastes a path directly

- **GIVEN** the selector is empty and `use_model_button` is disabled
- **WHEN** the user types `"C:\\m\\c.gguf"` directly into `model_selector` (or pastes it)
- **THEN** the `EVT_TEXT` handler fires
- **AND** the trimmed value is non-empty and resolves to an existing path
- **AND** `use_model_button.IsEnabled() is True`
- **AND** the user can activate the button (Enter, Space, or Alt+6) to call `_on_use_model` with the typed/pasted path

### Requirement: `restart_server_button` Label and Name

The button previously known as `start_server_button` SHALL be renamed to `restart_server_button` with label `"Reiniciar servidor"`. The `MainWindow` handler MUST invoke `LlamaRunner.stop_server()` followed by `LlamaRunner.start_server(...)` with the current model. The button MUST be disabled while a start is in progress and MUST be enabled when the server is not running.

#### Scenario: Button label and name

- **GIVEN** `MainWindow` is constructed
- **WHEN** the restart button is inspected
- **THEN** `restart_server_button.GetName() == "restart_server_button"`
- **AND** `restart_server_button.GetLabel() == "Reiniciar servidor"`

#### Scenario: Click restarts the server

- **GIVEN** a server is currently running
- **WHEN** the user clicks `restart_server_button`
- **THEN** `LlamaRunner.stop_server()` is called
- **AND** `LlamaRunner.start_server(model, client)` is called
- **AND** the button is disabled during the operation

## Added in v0.7.2 (samplers-modernos-min-p-seed-stop)

### Requirement: `options` dict -- min_p always, seed and stop conditional

`MainWindow.send_message` and `MainWindow._continue_after_tool` MUST
build an `options: dict[str, object]` for `LlamaClient.chat_stream`
with the following inclusion rules:

| Key | Source | Inclusion rule |
|---|---|---|
| `temperature` | `self._config.temperature` (float) | always |
| `max_tokens` | `self._config.max_tokens` (int) | always |
| `top_p` | `self._config.top_p` (float) | always |
| `top_k` | `self._config.top_k` (int) | always |
| `repeat_penalty` | `self._config.repeat_penalty` (float) | always |
| `min_p` | `self._config.min_p` (float) | always (always-sent) |
| `seed` | `self._config.seed` (int) | only if `self._config.seed >= 0` |
| `stop` | `self._config.stop` (list[str]) | only if `self._config.stop` is non-empty |

`min_p` is always sent because omitting the field disables
sampler-side filtering entirely (the server default is not the 2026
recommended `0.05`). The sentinel `seed == -1` means "aleatorio" and
MUST NOT appear in `options`. The sentinel `stop == []` means "no
stop strings" and MUST NOT appear in `options`. No other negative
or empty values have special meaning. Key insertion order in the
dict is not asserted; tests MUST be key-set based.

#### Scenario: min_p is always in options, seed=-1 and stop=[] are dropped

- **GIVEN** `BellbirdConfig(min_p=0.05, seed=-1, stop=[])` and a
  stubbed `MainWindow`
- **WHEN** the call site (`send_message` or `_continue_after_tool`)
  builds `options`
- **THEN** `options["min_p"] == 0.05`
- **AND** `"seed"` is NOT in `options`
- **AND** `"stop"` is NOT in `options`

#### Scenario: seed >= 0 is forwarded verbatim

- **GIVEN** `BellbirdConfig(min_p=0.05, seed=1234, stop=[])`
- **WHEN** the call site builds `options`
- **THEN** `options["seed"] == 1234`
- **AND** `options["min_p"] == 0.05`
- **AND** `"stop"` is NOT in `options`

#### Scenario: stop non-empty list is forwarded verbatim

- **GIVEN** `BellbirdConfig(min_p=0.05, seed=-1, stop=["</s>", "[/INST]"])`
- **WHEN** the call site builds `options`
- **THEN** `options["stop"] == ["</s>", "[/INST]"]`
- **AND** `options["min_p"] == 0.05`
- **AND** `"seed"` is NOT in `options`

#### Scenario: all three new fields populated at once

- **GIVEN** `BellbirdConfig(min_p=0.10, seed=42, stop=["USER:"])`
- **WHEN** the call site builds `options`
- **THEN** `options["min_p"] == 0.10`
- **AND** `options["seed"] == 42`
- **AND** `options["stop"] == ["USER:"]`

#### Scenario: seed=0 is forwarded (boundary)

- **GIVEN** `BellbirdConfig(seed=0, stop=[])` (the smallest
  non-sentinel seed)
- **WHEN** the call site builds `options`
- **THEN** `options["seed"] == 0`
- **AND** `"stop"` is NOT in `options`

#### Scenario: stop with one entry is forwarded (boundary)

- **GIVEN** `BellbirdConfig(stop=["</s>"], seed=-1)` (single-element
  stop list)
- **WHEN** the call site builds `options`
- **THEN** `options["stop"] == ["</s>"]`
- **AND** `"seed"` is NOT in `options`

### Requirement: `options` dict is byte-identical between the two call sites

`MainWindow.send_message` and `MainWindow._continue_after_tool` MUST
produce **byte-identical** `options` dicts for the same
`self._config` state. "Byte-identical" means equal as Python dicts
(`a == b`): same key set, same values per key. Insertion order is
preserved by CPython 3.7+ but the contract is value equality, not
positional equality. A unit test MUST compare the two dicts (or
construct the expected dict and assert equality with each call
site's output) and pass.

#### Scenario: identical config -> identical options at both sites

- **GIVEN** `BellbirdConfig(temperature=0.7, min_p=0.05, seed=1234,
  stop=["</s>"], max_tokens=512, top_p=0.9, top_k=40,
  repeat_penalty=1.1)`
- **WHEN** `send_message` and `_continue_after_tool` are each
  called with the same `self._config` and stubbed I/O
- **THEN** the `options` dict each site builds is `==` to the
  expected dict (same key set, same values)
- **AND** the two dicts are equal to each other
- **AND** the dicts contain exactly the keys
  `{"temperature", "max_tokens", "top_p", "top_k", "repeat_penalty",
  "min_p", "seed", "stop"}` (no extra keys, no missing keys)

#### Scenario: AST guard -- both sites have an `options=...` kwarg

- **GIVEN** the source of `bellbird/ui/main_window.py`
- **WHEN** the AST test inspects the `client.chat_stream(...)` calls
- **THEN** the call inside `send_message` passes a keyword
  argument named `options`
- **AND** the call inside `_continue_after_tool` passes a keyword
  argument named `options`

#### Scenario: AST guard -- both sites reference the new config fields

- **GIVEN** the source of `bellbird/ui/main_window.py`
- **WHEN** the AST test inspects the bodies of `send_message` and
  `_continue_after_tool`
- **THEN** both bodies reference `self._config.min_p`
- **AND** both bodies reference `self._config.seed`
- **AND** both bodies reference `self._config.stop`

### Requirement: PreferencesDialog -- Modelo tab has exactly two primary samplers

The **Modelo** tab in `PreferencesDialog` MUST expose exactly two
sampling controls as primary knobs (per the 2026 `temp + min_p`
consensus): `temperature` (existing) and `min_p` (new). The
`system_prompt` textbox and the existing `max_tokens` SpinCtrl
remain in Modelo (the moved-to-Avanzado
sampling controls are `top_p`, `top_k`, and `repeat_penalty`).
The new `min_p` control MUST be a `wx.Slider` with
`minValue=0`, `maxValue=100`, integer division by `100` producing
a `float` in the `[0.0, 1.0]` range, and `name="pref_min_p_slider"`.
The control MUST be preceded in the sizer by a `wx.StaticText`
labelled `"Min-p:"`, and a `wx.StaticText` value label
(`name="min_p_value_label"`) MUST update on slider change. The
slider's change handler MUST update the value label and call
`self._speech.speak(...)` with `interrupt=False`, matching the
pattern of the existing temperature slider.

#### Scenario: min_p slider range and default

- **GIVEN** a fresh `BellbirdConfig()` (default `min_p=0.05`)
- **WHEN** the dialog is constructed
- **THEN** `pref_min_p_slider.GetName() == "pref_min_p_slider"`
- **AND** `pref_min_p_slider.GetMin() == 0`
- **AND** `pref_min_p_slider.GetMax() == 100`
- **AND** `pref_min_p_slider.GetValue() == 5` (round of
  `0.05 * 100`)
- **AND** the preceding `wx.StaticText` has label `"Min-p:"`

#### Scenario: min_p slider value -> config float (mapping)

- **GIVEN** the min-p slider value is `12`
- **WHEN** `_apply_config()` runs
- **THEN** `self._config.min_p == 0.12` (NOT `12.0` and NOT `1.2`)

#### Scenario: min_p value label speaks the new float

- **GIVEN** a fake recording `speech.speak`
- **WHEN** the user moves the min_p slider
- **THEN** `speak` is called with the formatted float
  `f"{value/100.0:.2f}"` and `interrupt=False`
- **AND** `min_p_value_label.SetLabel(...)` is called with the
  same formatted string

#### Scenario: Modelo tab has exactly two sampling sliders (regression guard)

- **GIVEN** the source of `_build_model_page` in
  `bellbird/ui/preferences_dialog.py`
- **WHEN** the AST test searches for `wx.Slider` constructors
  whose `name=` starts with `pref_` and ends with `_slider`
- **THEN** exactly two matches exist: `pref_temp_slider` and
  `pref_min_p_slider`
- **AND** `pref_top_p_slider` is NOT in the Modelo page body
- **AND** `pref_top_k_spin` is NOT in the Modelo page body
- **AND** `pref_repeat_slider` is NOT in the Modelo page body
- **AND** `pref_max_tokens_spin` IS in the Modelo page body
  (regression guard: `max_tokens` stays in Modelo, NOT moved)

### Requirement: PreferencesDialog -- Avanzado tab gains seed and stop and absorbs the moved samplers

The **Avanzado** tab MUST contain the moved sampling controls plus
the new `seed` and `stop` controls, in addition to the existing
server fields (`ctx_size`, `n_gpu_layers`, `port`). The moved
sampling controls are `top_p`, `top_k`, and `repeat_penalty`
(`max_tokens` stays in Modelo). The full set of controls in Avanzado MUST be:

| Control | Type / range | Default | `BellbirdConfig` field | Mapping |
|---|---|---|---|---|
| Top-p (moved) | `wx.Slider` 0-100 + value label | 90 | `top_p: float` | `value / 100.0` |
| Top-k (moved) | `wx.SpinCtrl` 1-200 | 40 | `top_k: int` | direct |
| Repeat penalty (moved) | `wx.Slider` 100-200 + value label | 110 | `repeat_penalty: float` | `value / 100.0` |
| Seed (new) | `wx.SpinCtrl` `-1` to `2**31-1` | -1 | `seed: int` | direct |
| Stop strings (new) | `wx.TextCtrl` (multiline) | empty | `stop: list[str]` | one entry per non-empty line, lines `.strip()`-trimmed, empty lines skipped |
| Context size (existing) | `wx.SpinCtrl` 512-131072 | 4096 | `ctx_size: int` | direct |
| GPU layers (existing) | `wx.SpinCtrl` 0-200 | 99 | `n_gpu_layers: int` | direct |
| Server port (existing) | `wx.SpinCtrl` 1024-65535 | 8080 | `port: int` | direct |

The new `seed` SpinCtrl MUST have `name="pref_seed_spin"`, the new
`stop` TextCtrl MUST have `name="pref_stop_text"`. Both MUST be
preceded in the sizer by a `wx.StaticText` label (Spanish
descriptive text per AGENTS.md MSAA association). The seed SpinCtrl
MUST allow `-1` (the "aleatorio" sentinel) as the lower bound. The
`_on_slider_change` handler MUST dispatch on `pref_min_p_slider` in
the same pattern as `pref_temp_slider` / `pref_top_p_slider` /
`pref_repeat_slider` (value label update + `speak(..., interrupt=False)`).

#### Scenario: seed SpinCtrl range and default

- **GIVEN** a fresh `BellbirdConfig()` (default `seed=-1`)
- **WHEN** the dialog is constructed
- **THEN** `pref_seed_spin.GetName() == "pref_seed_spin"`
- **AND** `pref_seed_spin.GetMin() == -1`
- **AND** `pref_seed_spin.GetMax() >= 2**31 - 1`
- **AND** `pref_seed_spin.GetValue() == -1`

#### Scenario: stop TextCtrl initial value is empty string

- **GIVEN** a fresh `BellbirdConfig()` (default `stop=[]`)
- **WHEN** the dialog is constructed
- **THEN** `pref_stop_text.GetName() == "pref_stop_text"`
- **AND** `pref_stop_text.GetValue() == ""`

#### Scenario: stop multiline -> list[str] parse

- **GIVEN** `pref_stop_text.GetValue() == "</s>\n[/INST]\nUSER:\n"`
- **WHEN** `_apply_config()` runs
- **THEN** `self._config.stop == ["</s>", "[/INST]", "USER:"]`

#### Scenario: stop whitespace lines are skipped

- **GIVEN** `pref_stop_text.GetValue() == "  </s>  \n\n   \n[/INST]\n"`
- **WHEN** `_apply_config()` runs
- **THEN** `self._config.stop == ["</s>", "[/INST]"]`
  (whitespace-only lines dropped, leading/trailing whitespace
  stripped per entry)

#### Scenario: stop empty text -> empty list

- **GIVEN** `pref_stop_text.GetValue() == ""`
- **WHEN** `_apply_config()` runs
- **THEN** `self._config.stop == []` (sentinel value restored)

#### Scenario: new controls have preceding StaticText (regression guard)

- **GIVEN** the source of `_build_advanced_page` in
  `bellbird/ui/preferences_dialog.py`
- **WHEN** the AST test inspects the source
- **THEN** a `wx.StaticText` with a Spanish descriptive label
  (e.g. `"Semilla:"` / `"Cadenas de parada..."`) appears in the
  sizer before `pref_seed_spin`
- **AND** a `wx.StaticText` with a Spanish descriptive label
  appears in the sizer before `pref_stop_text`
- **AND** there is no `GridSizer` or `FlexGridSizer` anywhere in
  the file (AGENTS.md regression guard)

#### Scenario: max_tokens SpinCtrl STAYS in Modelo (regression guard)

- **GIVEN** the source of `bellbird/ui/preferences_dialog.py`
- **WHEN** the AST test locates the `pref_max_tokens_spin`
  constructor
- **THEN** the constructor call is in `_build_model_page` and
  NOT in `_build_advanced_page`
- **AND** the constructor call is preceded by a `wx.StaticText`
  with a Spanish label

### Requirement: `_apply_config` reads the three new fields

`PreferencesDialog._apply_config` MUST read `min_p`, `seed`, and
`stop` from the new controls and assign them to `self._config`
BEFORE `EndModal(wx.ID_OK)` runs (per the existing
"`_apply_config()` before `EndModal`" contract in
`app-configuration`). The mappings MUST be:

| Control | Assignment |
|---|---|
| `pref_min_p_slider` | `self._config.min_p = slider.GetValue() / 100.0` |
| `pref_seed_spin` | `self._config.seed = spin.GetValue()` |
| `pref_stop_text` | `self._config.stop = [line.strip() for line in text.GetValue().splitlines() if line.strip()]` |

#### Scenario: all three new fields read on OK

- **GIVEN** `pref_min_p_slider.GetValue() == 12`,
  `pref_seed_spin.GetValue() == 1234`, and
  `pref_stop_text.GetValue() == "</s>\n[/INST]"`
- **WHEN** the user clicks "Aceptar"
- **THEN** the dialog returns `wx.ID_OK`
- **AND** `dlg.get_config().min_p == 0.12`
- **AND** `dlg.get_config().seed == 1234`
- **AND** `dlg.get_config().stop == ["</s>", "[/INST]"]`

#### Scenario: `_apply_config` order is preserved (regression guard)

- **GIVEN** the source of `_apply_config` in
  `bellbird/ui/preferences_dialog.py`
- **WHEN** the AST test inspects the handler
- **THEN** the assignments to `self._config.min_p`,
  `self._config.seed`, and `self._config.stop` appear in the
  same handler body as the existing field assignments
- **AND** the handler is invoked from `_on_ok` BEFORE
  `EndModal(wx.ID_OK)`

#### Scenario: Cancel / Escape leave the new fields untouched (regression guard)

- **GIVEN** `BellbirdConfig(min_p=0.10, seed=42, stop=["</s>"])`
  passed to the dialog constructor
- **WHEN** the user edits the new controls and dismisses with
  Cancel or Escape
- **THEN** the caller's config is unchanged
  (`temperature`, `min_p`, `seed`, `stop` are the original
  values, NOT the edited ones)
- **AND** `dlg.ShowModal()` returns `wx.ID_CANCEL`

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
