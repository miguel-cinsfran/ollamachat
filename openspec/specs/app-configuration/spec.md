# App Configuration Capability Specification

<!-- Added in v0.7.2 (samplers-modernos-min-p-seed-stop): min_p, seed, stop fields on BellbirdConfig; _MIGRATIONS regression guard. Merged from openspec/changes/archive/2026-06-25-samplers-modernos-min-p-seed-stop/specs/app-configuration/spec.md -->

## Purpose

Defines `BellbirdConfig`, a wx-free dataclass that persists user settings to `data/config.json` so users do not re-tune sliders and re-enter model folders on every launch. Loading MUST be best-effort: a missing or corrupt file MUST fall back to defaults without raising, because blind users have no way to fix a startup crash.

> **v0.8.0** — Added `keymap_overrides` field per `2026-06-25-keymap-core-and-quick-actions`. Merged from `openspec/changes/archive/2026-06-25-keymap-core-and-quick-actions/specs/app-configuration/spec.md`.

## Requirements

### Requirement: `BellbirdConfig` Field Shape and Defaults

`BellbirdConfig` SHALL be a `@dataclass` with the scalar fields
and defaults listed below. New fields added in this change are
flagged `[v0.7.2]`.

| Field | Type | Default | Note |
|---|---|---|---|
| `temperature` | `float` | `0.70` | unchanged |
| `max_tokens` | `int` | `4096` | unchanged |
| `top_p` | `float` | `0.90` | unchanged |
| `top_k` | `int` | `40` | unchanged |
| `repeat_penalty` | `float` | `1.10` | unchanged |
| `system_prompt` | `str` | `""` | unchanged |
| `last_model` | `str` | `""` | unchanged (absolute path of last loaded `.gguf`) |
| `extra_model_folders` | `list[str]` | `[]` via `field(default_factory=list)` | unchanged, per-instance |
| `ctx_size` | `int` | `4096` | unchanged |
| `n_gpu_layers` | `int` | `99` | unchanged |
| `port` | `int` | `8080` | unchanged |
| `confirm_new_conversation` | `bool` | `True` | unchanged |
| `tools_enabled` | `bool` | `False` | unchanged |
| `model_mmproj` | `dict[str, str]` | `{}` via `field(default_factory=dict)` | unchanged (v0.7.0) |
| `mmproj_offload` | `bool` | `True` | unchanged (v0.7.0) |
| `request_timeout` | `int` | `120` | unchanged (v0.7.1) |
| `min_p` `[v0.7.2]` | `float` | `0.05` | 2026 consensus; always sent in `options` |
| `seed` `[v0.7.2]` | `int` | `-1` | `-1` = "aleatorio" sentinel; values `>= 0` forwarded verbatim |
| `stop` `[v0.7.2]` | `list[str]` | `[]` via `field(default_factory=list)` | empty list = "no stop strings" sentinel; non-empty list forwarded verbatim |
| `keymap_overrides` `[v0.8.0]` | `dict[str, tuple[int, int]]` | `{}` via `field(default_factory=dict)` | new v0.8.0; persisted JSON: list-of-two-ints normalised to tuple |
| `restore_last_session` `[v0.8.2]` | `bool` | `True` | app-shell reads at startup; `False` disables auto-restore |
| `last_session_path` `[v0.8.2]` | `str` | `""` | absolute path of the most recently saved/opened conversation; `""` = none |
| `recent_files` `[v0.8.2]` | `list[str]` | `[]` via `field(default_factory=list)` | MRU, deduped, capped at 10 entries by the app-shell; the dataclass does NOT enforce the cap (test pins the cap in app-shell) |
| `url_max_chars` `[v0.8.3]` | `int` | `50000` | cap for `core.web_fetch.fetch_text`; >cap → truncate + speech `"Página truncada por tamaño"`. Configurable, conservative. |
| `safe_vram_mode` `[v0.9.0]` | `bool` | `False` | opt-in gate for the pre-send VRAM / context guard. `True` → `pre_send_check` verdict `"block"` short-circuits the send; `False` → verdict `"warn"` speaks once per conversation. |
| `status_toggles` `[v0.9.0]` | `dict[str, bool]` | `{t: True for t in DEFAULT_STATUS_TOGGLES}` (all ON first run) | per-component on/off flags for the F2 `format_status` output. `BellbirdConfig.status_toggles_as_set()` returns the active names (the dict's `True` keys). |
| `model_tunings` `[v0.9.0]` | `dict[str, dict]` | `{}` via `field(default_factory=dict)` | per-model `(ctx_size, n_gpu_layers, threads)` overrides. Key = `.gguf` basename, value = `{"ctx_size": int, "n_gpu_layers": int, "threads": int \| None}`. Entries are NEVER auto-pruned (the user cleans up manually). |
| `pre_send_warn` `[v0.9.0]` | `bool` | `True` | gate for the one-shot warning in non-safe mode; `False` silences the warn-and-proceed path entirely. |
| `system_voice_name` `[v0.10.0]` | `str` | `""` | SAPI voice name; `""` = first available. |
| `system_voice_rate` `[v0.10.0]` | `int` | `0` | SAPI rate, range `[-10, +10]`; the voice dialog validates the slider bounds. |
| `auto_speak_responses` `[v0.10.0]` | `bool` | `False` | **Off by default** — never auto-reads. Only explicit F8 (or a future button) calls `speak_with_system_voice`. |
| `notifications_enabled` `[v0.10.0]` | `bool` | `True` | Master toast toggle (see `notifications` spec). |
| `sounds_enabled` `[v0.10.0]` | `bool` | `True` | Master sound-cue toggle. |
| `sound_theme` `[v0.10.0]` | `str` | `"default"` | Subdir of `data/sounds/`. `"none"` → no playback. |

The field name `last_model` is intentional and MUST NOT be renamed
to `model_path` (that name is already used by
`LlamaRunner.start_server(model_path: str, ...)` for the per-call
`.gguf` path). `min_p`, `seed`, and `stop` MUST be persisted via
the existing `save_config` / `load_config` round-trip (atomic
write, UTF-8, `ensure_ascii=False`) and MUST be dropped silently
by a reverted build that does not know the fields
(forward-compat preserved by the existing `__dataclass_fields__`
filter).

(Previously: the dataclass had 16 fields ending at
`request_timeout`; the new fields `min_p`, `seed`, and `stop`
extend the shape additively with backward-compatible defaults.
After v0.8.2: 3 additive fields `restore_last_session`,
`last_session_path`, and `recent_files` — no fields removed or
renamed. After v0.8.3: 1 additive field `url_max_chars`.
After v0.9.0: 4 additive fields `safe_vram_mode`, `status_toggles`,
`model_tunings`, and `pre_send_warn` — no fields removed or
renamed. After v0.10.0: 6 additive fields `system_voice_name`,
`system_voice_rate`, `auto_speak_responses`, `notifications_enabled`,
`sounds_enabled`, and `sound_theme` — no fields removed or
renamed. Total: 34 fields.)

#### Scenario: Defaults match the documented values (updated)

- **GIVEN** a fresh `BellbirdConfig()`
- **WHEN** the field values are read
- **THEN** the pre-v0.7.2 fields are unchanged
  (`temperature == 0.70`, `max_tokens == 4096`, `top_p == 0.90`,
  `top_k == 40`, `repeat_penalty == 1.10`, `system_prompt == ""`,
  `last_model == ""`, `port == 8080`, `ctx_size == 4096`,
  `n_gpu_layers == 99`, `extra_model_folders == []`,
  `confirm_new_conversation is True`, `tools_enabled is False`,
  `model_mmproj == {}`, `mmproj_offload is True`,
  `request_timeout == 120`)
- **AND** `min_p == 0.05`, `seed == -1`, `stop == []` (v0.7.2)
- AND `restore_last_session is True` (v0.8.2)
- AND `last_session_path == ""` (v0.8.2)
- AND `recent_files == []` (v0.8.2)
- AND `url_max_chars == 50000` (v0.8.3)
- AND `safe_vram_mode is False` (v0.9.0)
- AND `status_toggles == {t: True for t in DEFAULT_STATUS_TOGGLES}` (v0.9.0, all ON first run)
- AND `model_tunings == {}` (v0.9.0)
- AND `pre_send_warn is True` (v0.9.0)

#### Scenario: `url_max_chars` is a plain int (regression guard)

- GIVEN a fresh `BellbirdConfig()`
- WHEN `cfg.url_max_chars` is read
- THEN it is an `int` AND the value is `50000` (no string
  parsing needed; the value flows into `fetch_text` and
  the truncate logic unchanged)

#### Scenario: round-trip preserves `url_max_chars`

- GIVEN `BellbirdConfig(url_max_chars=80000)` and `tmp_path`
- WHEN `save_config(cfg, tmp_path/"c.json")` runs and
  `load_config()` reads it back
- THEN the loaded `url_max_chars == 80000`

#### Scenario: missing `url_max_chars` in old config falls back to default

- GIVEN a `config.json` from v0.8.2 with NO `url_max_chars`
  key
- WHEN `load_config()` runs on v0.8.3
- THEN the loaded config equals `BellbirdConfig()` with
  `url_max_chars == 50000`
- AND no `KeyError` is raised

#### Scenario: unknown future keys in JSON are dropped (forward-compat)

- GIVEN a `config.json` containing `url_max_chars` AND a
  hypothetical `future_field` key
- WHEN `load_config()` runs
- THEN `url_max_chars` is loaded
- AND `future_field` is silently dropped
- AND no `AttributeError` is raised from the unknown key

#### Scenario: `stop` default is per-instance empty list (regression guard)

- **GIVEN** two fresh `BellbirdConfig()` instances `a` and `b`
- **WHEN** `a.stop.append("</s>")` executes
- **THEN** `b.stop == []` (not shared; `default_factory` honored)

#### Scenario: `recent_files` default is per-instance empty list (regression guard)

- GIVEN two fresh `BellbirdConfig()` instances `a` and `b`
- WHEN `a.recent_files.append("C:\\x.json")` executes
- THEN `b.recent_files == []` (not shared; `default_factory` honored)

#### Scenario: round-trip preserves the 3 v0.8.2 fields

- GIVEN `BellbirdConfig(restore_last_session=False, last_session_path="C:\\old.json", recent_files=["C:\\a.json","C:\\b.json"])` and `tmp_path`
- WHEN `save_config(cfg, tmp_path/"c.json")` runs and `load_config()` reads it back
- THEN the loaded `restore_last_session is False`
- AND the loaded `last_session_path == "C:\\old.json"`
- AND the loaded `recent_files == ["C:\\a.json", "C:\\b.json"]`

#### Scenario: missing v0.8.2 keys in old config fall back to defaults

- GIVEN a `config.json` from v0.8.1 with NO `restore_last_session`, `last_session_path`, or `recent_files` keys
- WHEN `load_config()` runs on v0.8.2
- THEN the loaded config equals `BellbirdConfig()` with the new defaults (`restore_last_session is True`, `last_session_path == ""`, `recent_files == []`)
- AND no `KeyError` is raised

#### Scenario: unknown future keys in JSON are dropped (forward-compat, regression guard for v0.8.2)

- GIVEN a `config.json` containing the new fields AND a hypothetical `future_field` key
- WHEN `load_config()` runs on v0.8.2
- THEN `restore_last_session`, `last_session_path`, `recent_files` are loaded
- AND `future_field` is silently dropped
- AND no `AttributeError` is raised

#### Scenario: round-trip preserves all three new fields

- **GIVEN** `BellbirdConfig(min_p=0.10, seed=42, stop=["</s>", "[/INST]"])`
  and `tmp_path`
- **WHEN** `save_config(cfg, tmp_path/"c.json")` runs and
  `load_config()` reads it back
- **THEN** the loaded `min_p == 0.10`
- **AND** the loaded `seed == 42`
- **AND** the loaded `stop == ["</s>", "[/INST]"]`

#### Scenario: missing new keys in old config fall back to defaults

- **GIVEN** a `config.json` from v0.7.1 with NO `min_p`, `seed`,
  or `stop` keys (only pre-v0.7.2 fields)
- **WHEN** `load_config()` runs on v0.7.2
- **THEN** the loaded config equals `BellbirdConfig()` with
  `min_p == 0.05`, `seed == -1`, `stop == []` (dataclass
  defaults applied; no `KeyError` raised)

#### Scenario: unknown new keys in JSON are dropped (forward-compat)

- **GIVEN** a `config.json` containing the new fields AND a
  hypothetical `future_field` key
- **WHEN** `load_config()` runs
- **THEN** `min_p`, `seed`, `stop` are loaded
- **AND** `future_field` is silently dropped
- **AND** no `AttributeError` is raised from the unknown key

### Requirement: `BellbirdConfig.keymap_overrides` [v0.8.0]

`BellbirdConfig` SHALL add a field
`keymap_overrides: dict[str, tuple[int, int]] = field(default_factory=dict)`
[v0.8.0]. The keys are action ids (must match an entry in
`DEFAULT_KEYMAP`); the values are `(modifiers, keycode)` int tuples
(the same shape produced by `Keymap.to_overrides_dict()`). The
field MUST be persisted via the existing `save_config` /
`load_config` round-trip. `load_config` MUST tolerate unknown
action ids at load time (forward-compat — a future build may have
renamed or removed an action, and the old keymap must not crash
the load). `load_config` MUST fall back to `BellbirdConfig()` (the
existing corrupt-config policy) if any value in the dict is not
`(int, int)`-shaped. The on-disk JSON form MAY serialise the
tuples as JSON arrays of two ints (the existing `asdict` /
`json.dump` round-trip); the load logic MUST normalise
list-of-two-ints back to a tuple before storing on the dataclass
(implementation choice; the resolved `Keymap.from_overrides_dict`
accepts either).

#### Scenario: Defaults applied when key absent

- GIVEN a `config.json` with no `keymap_overrides` key (e.g. a v0.7.x file)
- WHEN `load_config()` runs on v0.8.0
- THEN the loaded `cfg.keymap_overrides == {}` (empty dict, no `KeyError`)

#### Scenario: JSON round-trip preserves the dict

- GIVEN `cfg = BellbirdConfig(keymap_overrides={"copy_last": [1 | 2, ord("C")]})` and `tmp_path`
- WHEN `save_config(cfg, tmp_path/"c.json")` then `load_config()` runs
- THEN the loaded `cfg.keymap_overrides` round-trips to the same
  shape (the key is `"copy_last"`, the value is a two-int
  `(modifiers, keycode)`)

#### Scenario: Unknown action id is silently dropped at load time

- GIVEN `config.json` with `{"keymap_overrides": {"ghost_action": [0, 81]}}`
- WHEN `load_config()` runs
- THEN `cfg.keymap_overrides` either contains the unknown id (the
  drop is the `Keymap.from_overrides_dict` layer's job, not the
  config layer's) or is filtered to known ids — the load does
  NOT raise

#### Scenario: Non-int values fall back to defaults (corrupt-config policy)

- GIVEN `config.json` with `{"keymap_overrides": {"copy_last": "Ctrl+Shift+C"}}` (string instead of pair)
- WHEN `load_config()` runs
- THEN the result equals `BellbirdConfig()` (the existing
  corrupt-config fallback) and no `TypeError` is raised

#### Scenario: Default is per-instance empty dict (regression guard)

- GIVEN two fresh `BellbirdConfig()` instances `a` and `b`
- WHEN `a.keymap_overrides["copy_last"] = (3, 67)` executes
- THEN `b.keymap_overrides == {}` (not shared; `default_factory` honored)

### Requirement: `load_config()` Migrations Are Unchanged

`_MIGRATIONS: dict[str, object]` MUST continue to contain only
the existing `max_tokens: (512, 4096)` entry. This change MUST
NOT add new entries to `_MIGRATIONS` (the new field defaults are
the desired post-change values; no migration is needed for
`min_p`, `seed`, or `stop`). The existing
`max_tokens 512 -> 4096` migration MUST still apply for
v0.5.1-and-earlier configs.

(Previously: `_MIGRATIONS` had a single entry, `max_tokens`.)
(No behavior change; this requirement is a regression guard
documenting the explicit "do not add migrations" decision.)

> **v0.8.0**: The `keymap_overrides` field also has NO migration entry.
> The empty-dict default is the desired post-change value; existing config
> files silently gain `keymap_overrides == {}` on first read.
>
> **v0.8.1 (keymap-preferences-tab)**: `PreferencesDialog` now has a sixth "Atajos" tab with
> `KeyCaptureControl`. See the `## Added in v0.8.1` section below.
>
> **v0.8.3 (attach-url)**: The `url_max_chars` field also has NO migration entry.
> The default value 50000 is the desired post-change value; existing config
> files silently gain `url_max_chars == 50000` on first read.
>
> **v0.9.0 (context-advisor-and-f2-toggleable)**: The 4 new fields
> `safe_vram_mode`, `status_toggles`, `model_tunings`, and `pre_send_warn`
> also have NO migration entries. Each default value is the desired
> post-change value, and the existing `__dataclass_fields__` filter at
> `core/config.py:92-93` handles forward-compat automatically per the
> v0.8.2 lessons-learned entry. `status_toggles` is a per-instance
> `default_factory` dict; `model_tunings` never auto-prunes.

#### Scenario: max_tokens 512 -> 4096 migration still applies

- **GIVEN** a `config.json` persisted with the legacy
  `max_tokens: 512`
- **WHEN** `load_config()` runs
- **THEN** `result.max_tokens == 4096` (regression guard for the
  v0.5.1 migration)

#### Scenario: AST guard -- `_MIGRATIONS` has no new entries

- **GIVEN** the source of `bellbird/core/config.py`
- **WHEN** the AST test inspects the `_MIGRATIONS` dict literal
- **THEN** exactly one entry exists: `("max_tokens", (512, 4096))`
  - **AND** no entry references `min_p`, `seed`, `stop`, `keymap_overrides`, `restore_last_session`, `last_session_path`, `recent_files`, `url_max_chars`, `safe_vram_mode`, `status_toggles`, `model_tunings`, or `pre_send_warn`

### Requirement: `load_config()` Is Best-Effort and Never Raises

`load_config() -> BellbirdConfig` MUST read `CONFIG_PATH` and overlay on-disk values onto defaults. If the file is missing, corrupt, or fails to decode, the function MUST return `BellbirdConfig()` without raising. Keys not in `BellbirdConfig.__dataclass_fields__` MUST be silently dropped (forward-compat).

#### Scenario: Missing or corrupt file returns defaults

- GIVEN `CONFIG_PATH` does not exist OR contains `"{ not valid json"` OR contains `{}`
- WHEN `load_config()` is called
- THEN the result equals `BellbirdConfig()` and no exception is raised

#### Scenario: Unknown keys ignored (forward-compat)

- GIVEN `CONFIG_PATH` contains `{"port": 9090, "future_field": "x", "temperature": 0.5}`
- WHEN `load_config()` is called
- THEN `result.port == 9090` and `result.temperature == 0.5`
- AND no `AttributeError` is raised from the unknown key

### Requirement: `save_config()` Writes Atomically and Round-Trips

`save_config(config: BellbirdConfig, path: Path | None = None) -> None` MUST serialize with `indent=2` and `ensure_ascii=False`, encode UTF-8, and write atomically: write to `path.with_suffix(".tmp")` first, then `Path.replace` onto the target. Parent dir MUST be created (`path.parent.mkdir(parents=True, exist_ok=True)`). When `path` is `None`, `CONFIG_PATH` is used. The on-disk file MUST round-trip through `load_config()` to an equal `BellbirdConfig`.

#### Scenario: Atomic write via .tmp + replace

- GIVEN `BellbirdConfig(port=9090)` and a temp directory
- WHEN `save_config(cfg, tmp_path / "config.json")` runs
- THEN no `.tmp` file remains
- AND `json.loads((tmp_path / "config.json").read_text("utf-8"))["port"] == 9090`

#### Scenario: Parent directory created if missing

- GIVEN `tmp_path / "nested" / "config.json"` and the `nested/` directory do not exist
- WHEN `save_config(BellbirdConfig(), tmp_path / "nested" / "config.json")` runs
- THEN the call succeeds and the file is readable

#### Scenario: `ensure_ascii=False` preserves Spanish strings

- GIVEN a `BellbirdConfig` field set to `"Eres útil."`
- WHEN `save_config(cfg, tmp_path / "config.json")` runs
- THEN the file contains the literal substring `"Eres útil."` (not `\u00fatil`)

#### Scenario: Round-trip equals input

- GIVEN `BellbirdConfig(port=9090, ctx_size=8192, extra_model_folders=["D:\\llms"])`
- WHEN `save_config(cfg, p)` runs and `load_config()` reads `p`
- THEN `loaded == cfg`

### Requirement: `CONFIG_PATH` Resolves Under `data/`

`CONFIG_PATH: Path` SHALL be a module-level `pathlib.Path` resolved at import to `<project_root>/data/config.json`. The `data/` directory MUST NOT be assumed to exist at import; only `save_config` creates it.

#### Scenario: `CONFIG_PATH` ends with `data/config.json`

- GIVEN `bellbird.core.config` is imported
- WHEN `CONFIG_PATH` is read
- THEN `str(CONFIG_PATH).replace("\\", "/").endswith("data/config.json") is True`
- AND `CONFIG_PATH.parent.name == "data"`

### Requirement: Module Is wx-Free

`bellbird/core/config.py` MUST NOT import `wx` at module scope. Only `dataclasses`, `json`, and `pathlib` from the stdlib are permitted so the module imports cleanly on WSL/CI without wxPython.

#### Scenario: Module imports without wx

- GIVEN a Python environment without `wxPython` installed
- WHEN `import bellbird.core.config` runs
- THEN no `ModuleNotFoundError` for `wx` is raised

### Requirement: `PreferencesDialog` — Structure, Lifecycle, and Accessibility Scaffolding

`bellbird/ui/preferences_dialog.py` SHALL define `PreferencesDialog(wx.Dialog)` with `name="preferences_dialog"` and constructor `(self, parent, config: BellbirdConfig)`. The dialog MUST call `SetSize((520, 480))` and `SetEscapeId(wx.ID_CANCEL)`. It MUST use only `wx.BoxSizer`; `wx.GridSizer` and `wx.FlexGridSizer` MUST NOT appear in the file. Every interactive control (TextCtrl, Slider, SpinCtrl, CheckBox, ListBox, Button) MUST have `name=` and a preceding `wx.StaticText` label. The dialog MUST contain a `wx.Notebook` with exactly five pages in this order: **"General"**, **"Modelo"**, **"Chat"**, **"Herramientas"**, **"Avanzado"**.

The constructor MUST copy the input via `self._config = dataclasses.replace(config)` so `Cancel` and `Escape` are no-ops. The class MUST expose `get_config() -> BellbirdConfig`. The OK button handler MUST call `_apply_config()` (which writes every control into `self._config`) BEFORE `EndModal(wx.ID_OK)`; Cancel and Escape MUST `EndModal(wx.ID_CANCEL)` without touching `self._config`. The dialog MUST schedule `wx.CallAfter(self._focus_first_control)` to focus the first control of the first tab. `BellbirdConfig.last_model` is intentionally NOT exposed in any tab (set by the model-load flow).

#### Scenario: All five tab labels present in source

- GIVEN the source of `bellbird/ui/preferences_dialog.py`
- WHEN the AST test greps for the tab labels
- THEN `"General"`, `"Modelo"`, `"Chat"`, `"Herramientas"`, and `"Avanzado"` are all present

#### Scenario: No `GridSizer` in source (regression guard)

- GIVEN the dialog source
- WHEN the AST test greps for `GridSizer`
- THEN no match is found

#### Scenario: `SetEscapeId(wx.ID_CANCEL)` is called

- GIVEN the dialog source
- WHEN the AST test greps for `SetEscapeId`
- THEN a call `SetEscapeId(wx.ID_CANCEL)` is present

#### Scenario: OK handler runs `_apply_config()` before `EndModal`

- GIVEN the OK button handler in the source
- WHEN the AST test inspects the handler
- THEN `_apply_config` appears textually before `EndModal` in the same handler

#### Scenario: Cancel / Escape leave caller's config untouched

- GIVEN `BellbirdConfig(temperature=0.7, port=8080)` passed to the constructor
- WHEN the user edits a control and dismisses with Cancel or Escape
- THEN the caller's config is unchanged
- AND `dlg.ShowModal()` returns `wx.ID_CANCEL`

### Requirement: `PreferencesDialog` — Five Tabs Cover 12 Editable Fields

The five tabs MUST bind `BellbirdConfig` fields via the controls below. Every control MUST have `name=` and a preceding `wx.StaticText` label. Slider value labels MUST update on change and announce via `speech`, matching `ParamsPanel`. `last_model` is intentionally NOT exposed in any tab.

**General** — `extra_model_folders: list[str]`: `wx.ListBox` (`name="extra_folders_list"`) populated from the field; "Agregar carpeta" button opens `wx.DirDialog` and appends the path; "Quitar seleccionada" button removes the selected item. `~/, ~/Downloads` and standard paths continue to be scanned by `llama_runner._get_standard_paths`; this list is additive.

**Modelo** — system prompt + sampling:

| Control | Type / range | Default | `BellbirdConfig` field | Mapping |
|---|---|---|---|---|
| System prompt | `wx.TextCtrl` (multiline, `size=(-1, 80)`) | `""` | `system_prompt: str` | direct |
| Temperature | `wx.Slider` 0-200 + value `StaticText` | 70 | `temperature: float` | `value / 100.0` |
| Max tokens | `wx.SpinCtrl` 64-8192 | 512 | `max_tokens: int` | direct |
| Top-p | `wx.Slider` 0-100 + value `StaticText` | 90 | `top_p: float` | `value / 100.0` |
| Top-k | `wx.SpinCtrl` 1-200 | 40 | `top_k: int` | direct |
| Repeat penalty | `wx.Slider` 100-200 + value `StaticText` | 110 | `repeat_penalty: float` | `value / 100.0` |

**Chat** — `confirm_new_conversation: bool`: `wx.CheckBox` (`name="pref_confirm_new_conv"`, label "Confirmar al iniciar nueva conversación").

**Herramientas** — `tools_enabled: bool`: `wx.CheckBox` (`name="pref_tools_checkbox"`, label "Permitir herramientas (PowerShell)").

**Avanzado** — server fields:

| Control | Range | Inc | Default | `BellbirdConfig` field |
|---|---|---|---|---|
| Context size | 512-131072 | 512 | 4096 | `ctx_size: int` |
| GPU layers | 0-200 | 1 | 99 | `n_gpu_layers: int` |
| Server port | 1024-65535 | 1 | 8080 | `port: int` |

OK / Cancel buttons sit outside the Notebook at the footer: `wx.Button` (`name="pref_ok_button"`, id `wx.ID_OK`, label "Aceptar") and `wx.Button` (`name="pref_cancel_button"`, id `wx.ID_CANCEL`, label "Cancelar").

#### Scenario: `repeat_penalty` slider mapping (off-by-100 bug guard)

- GIVEN the repeat-penalty slider value is `150`
- WHEN `_apply_config()` runs
- THEN `self._config.repeat_penalty == 1.50` (NOT `150.0` and NOT `0.15`)

#### Scenario: `temperature` slider mapping

- GIVEN the temperature slider value is `80`
- WHEN `_apply_config()` runs
- THEN `self._config.temperature == 0.80`

#### Scenario: SpinCtrl values reflect config defaults

- GIVEN `BellbirdConfig(ctx_size=8192, n_gpu_layers=35, port=9090)`
- WHEN the dialog is constructed
- THEN `pref_ctx_size_spin.GetValue() == 8192`, `pref_gpu_layers_spin.GetValue() == 35`, `pref_port_spin.GetValue() == 9090`

#### Scenario: `extra_model_folders` initial population

- GIVEN `BellbirdConfig(extra_model_folders=["D:\\llms", "E:\\models"])`
- WHEN the dialog is constructed
- THEN `extra_folders_list.GetItems() == ["D:\\llms", "E:\\models"]`

#### Scenario: CheckBoxes reflect current values

- GIVEN `BellbirdConfig(confirm_new_conversation=False, tools_enabled=True)`
- WHEN the dialog is constructed
- THEN `pref_confirm_new_conv.GetValue() is False` and `pref_tools_checkbox.GetValue() is True`

## Added in v0.7.0 (multimodal-mmproj)

### REQ-APPCONF-MULTI-1: `model_mmproj` per-model pairing

`BellbirdConfig` SHALL add a field
`model_mmproj: dict[str, str] = field(default_factory=dict)`.
The key is the model file **basename**
(`Path(model_path).name`, e.g.
`"Llama-3.2-11B-Vision-Instruct-Q4_K_M.gguf"`) and the value
is the absolute path to the projector `.gguf` the user last
selected for that model. The field MUST be persisted via the
existing `save_config` / `load_config` round-trip (atomic
write, user-data dir) and MUST be dropped silently on a
reverted build that does not know the field (forward-compat
preserved). The basename-key decision is FINAL for this
change; any drift with `last_model` storage semantics is
deferred to a follow-up.

#### Scenario: default is empty per-instance dict
- **GIVEN** two fresh `BellbirdConfig()` instances `a` and `b`
- **WHEN** `a.model_mmproj["Llama-3.2-11B-Vision-Instruct-Q4_K_M.gguf"] = "C:\\m\\vl-mmproj.gguf"`
- **THEN** `b.model_mmproj == {}` (not shared; `default_factory` honored)

#### Scenario: round-trip preserves the dict
- **GIVEN** `BellbirdConfig(model_mmproj={"a.gguf": "C:\\p\\m.gguf"})` and `tmp_path`
- **WHEN** `save_config(cfg, tmp_path/"c.json")` runs and `load_config` reads it back
- **THEN** the loaded `model_mmproj` equals the input dict

#### Scenario: unknown key in JSON is dropped (forward-compat)
- **GIVEN** the JSON contains `model_mmproj` AND a `future_field` key
- **WHEN** `load_config()` runs
- **THEN** `model_mmproj` is loaded and `future_field` is silently dropped

#### Scenario: lookup is by basename equality
- **GIVEN** `cfg.model_mmproj["vl.gguf"] == "C:\\m\\p.gguf"`
- **WHEN** `cfg.model_mmproj[Path("D:\\other\\vl.gguf").name]` is read
- **THEN** it returns `"C:\\m\\p.gguf"` (basename key, not absolute)

### REQ-APPCONF-MULTI-2: `mmproj_offload` opt-in flag

`BellbirdConfig` SHALL add a field `mmproj_offload: bool = True`.
When `True` (default), `LlamaRunner.start_server` MUST NOT
append `--no-mmproj-offload` to argv. When `False`, the runner
MUST append `--no-mmproj-offload`. The default preserves v0.6.0
behavior; no UI exposure is required in this change (the
prompt-13 advisor may surface it later).

#### Scenario: default keeps GPU offload
- **GIVEN** a fresh `BellbirdConfig()`
- **THEN** `mmproj_offload is True`

#### Scenario: round-trip preserves the bool
- **GIVEN** `BellbirdConfig(mmproj_offload=False)` and `tmp_path`
- **WHEN** `save_config` + `load_config` runs
- **THEN** the loaded `mmproj_offload is False`

## Added in v0.8.1 (keymap-preferences-tab)

### Requirement: `PreferencesDialog` — Atajos Tab with Capture Control

`PreferencesDialog` SHALL add a sixth tab "Atajos" to the
existing `wx.Notebook` (after the five existing tabs from
v0.4.1 / v0.7.2). The tab SHALL contain a row per action id
in `DEFAULT_KEYMAP` (alphabetical for stability), each row
showing: the action id label (Spanish), the current binding
label, a "Cambiar" button (`name="keymap_capture_button"`),
and a "Restablecer" button
(`name="keymap_reset_button"`). Pressing "Cambiar" opens a
modal mini-dialog (`wx.Dialog` with
`name="keymap_capture_dialog"`, caption "Capturar atajo",
`SetEscapeId(wx.ID_CANCEL)`) that contains a single
`KeyCaptureControl`.

`KeyCaptureControl` SHALL be a `wx.Panel` with
`name="key_capture_panel"` and a preceding `wx.StaticText`
label ("Pulsa la combinación de teclas:"). The control SHALL
bind `EVT_KEY_DOWN` and, on the next event with a
non-modifier keycode (i.e. `event.GetKeyCode() not in
(WXK_SHIFT, WXK_CONTROL, WXK_ALT, WXK_MENU)`), SHALL read
`event.GetModifiers()` + `event.GetKeyCode()`, format a
Spanish label (e.g. `"Ctrl+Shift+C"`), display it in a
`wx.StaticText` (`name="key_capture_label"`), and call
`speech.speak(formatted_label, interrupt=True)`). The user
"Accept"s the capture by clicking an Aceptar button
(`name="key_capture_accept_button"`); the parent dialog
SHALL then validate the proposed `(modifiers, keycode)`
against `keymap.find_conflict(...)`. If the proposed combo
collides with another resolved binding, the dialog MUST
reject the change, speak
`"Combinación ya usada por <etiqueta>"` (interrupt=True),
and keep the previous binding. `Tab` and `Escape` are
reserved (`Tab` = focus-move; `Escape` = cancel capture) —
the capture control MUST ignore them with a Spanish
announcement (`"Tecla reservada"`) and MUST NOT advance
focus to the next control on `Tab`. The capture is
single-shot per click of "Cambiar"; subsequent captures
require a second click.

(Depends on the V1 change
`2026-06-25-keymap-core-and-quick-actions` for the `Keymap`
class, the `rebuild_accelerator_table()` method, and the
`keymap_overrides` field.)

#### Scenario: Capture accepts `Ctrl+Shift+C` for `copy_last` [windows-only]

- GIVEN the user is in the Atajos tab and clicks "Cambiar" on the `copy_last` row
- AND the modal capture dialog opens with focus on `key_capture_panel`
- WHEN the user presses `Ctrl+Shift+C` and clicks Aceptar
- THEN the proposed combo is `(KEYMAP_MOD_CTRL | KEYMAP_MOD_SHIFT, ord("C"))`
- AND `keymap.find_conflict(...)` reports no collision (assuming the default is being rebound and no other row uses the combo)
- AND the row's binding label updates to `"Ctrl+Shift+C"`
- AND `speech.speak("Ctrl+Shift+C", interrupt=True)` was called from the capture control

#### Scenario: Capture rejects a colliding combo with a Spanish announcement [windows-only]

- GIVEN `copy_last` is currently bound to `Ctrl+Shift+C`
- AND the user clicks "Cambiar" on `new_conversation` and presses `Ctrl+Shift+C`
- WHEN the user clicks Aceptar on the capture dialog
- THEN the capture is rejected
- AND `speech.speak("Combinación ya usada por copy_last", interrupt=True)` is called (or the action's Spanish label, not the id; implementation choice)
- AND the `new_conversation` row keeps its previous binding label (`Ctrl+N`)

#### Scenario: Tab and Escape are reserved; Tab does not advance focus [windows-only]

- GIVEN the capture dialog is open with focus on `key_capture_panel`
- WHEN the user presses `Tab`
- THEN focus stays on `key_capture_panel` (does NOT advance to the Aceptar button)
- AND `speech.speak("Tecla reservada", interrupt=True)` is called
- WHEN the user presses `Escape`
- THEN the capture dialog closes with `wx.ID_CANCEL`
- AND no override is saved

#### Scenario: `Restablecer` drops the override [windows-only]

- GIVEN `copy_last` has an override `Alt+C`
- WHEN the user clicks "Restablecer" on the `copy_last` row
- THEN the override is removed from `cfg.keymap_overrides`
- AND the row's binding label reverts to `"Ctrl+Shift+C"` (the default)
- AND the change is saved to `cfg` (and thus to `data/config.json` on OK)

#### Scenario: Seven tabs present in source [windows-only] (v0.9.0)

- GIVEN the source of `bellbird/ui/preferences_dialog.py`
- WHEN the AST test greps for the tab labels
- THEN the existing six labels ("General", "Modelo", "Chat", "Herramientas", "Avanzado", "Atajos") are present
- AND the new label "Estado (F2)" is present
- AND the order is "General" → "Modelo" → "Chat" → "Herramientas" → "Avanzado" → "Atajos" → "Estado (F2)"

#### Scenario: Conflict is rejected at the capture step, not at OK

- GIVEN the user has a pending change in the Atajos tab
- AND the change is for a combo that DOES NOT collide (the
  capture step already validated it)
- WHEN the user clicks Aceptar
- THEN no `MessageDialog` is shown for the conflict case (the
  conflict was rejected at the capture step, not at the OK
  step)
- AND the in-memory `cfg.keymap_overrides` is updated BEFORE
  `EndModal(wx.ID_OK)` is called

<!-- Merged from archive/2026-06-23-preferences-dialog/specs/app-configuration/spec.md on 2026-06-23 -->
<!-- Merged from openspec/changes/2026-06-25-attach-url/specs/app-configuration/spec.md on 2026-06-25 -->
<!-- Merged from openspec/changes/multimodal-mmproj/specs/app-configuration/spec.md on 2026-06-25 -->
<!-- Merged from openspec/changes/2026-06-25-keymap-preferences-tab/specs/app-configuration/spec.md on 2026-06-25 (v0.8.1) -->

## Added in v0.9.0 (context-advisor-and-f2-toggleable)

### Requirement: `BellbirdConfig` 4 new fields round-trip via the standard `__dataclass_fields__` filter

The 4 new fields `safe_vram_mode`, `status_toggles`, `model_tunings`,
and `pre_send_warn` SHALL round-trip via the existing `save_config` /
`load_config` pipeline. The `__dataclass_fields__` filter at
`core/config.py:92-93` (the v0.8.2 forward-compat mechanism) MUST
silently fill missing keys with the field defaults — no migration
entry in `_MIGRATIONS` is required, and `_MIGRATIONS` remains
single-entry (`max_tokens`). `status_toggles` SHALL be a per-instance
dict (each `BellbirdConfig()` instance gets a fresh `dict[str, bool]`
with every `DEFAULT_STATUS_TOGGLES` key set to `True`).
`model_tunings` SHALL be a per-instance dict that the runtime NEVER
auto-prunes when a model file disappears from disk (the user cleans
up manually — silent pruning would surprise the user, per the v0.8.2
recents-pattern decision).

#### Scenario: `status_toggles` default is per-instance dict with all keys True (v0.9.0)

- **GIVEN** two fresh `BellbirdConfig()` instances `a` and `b`
- **WHEN** `a.status_toggles["model_name"] = False` is executed
- **THEN** `b.status_toggles["model_name"] is True` (per-instance
  `default_factory` honored)
- **AND** every name in `DEFAULT_STATUS_TOGGLES` is present as a
  key in `b.status_toggles` (the all-ON first-run invariant)

#### Scenario: `model_tunings` default is per-instance empty dict (v0.9.0)

- **GIVEN** two fresh `BellbirdConfig()` instances `a` and `b`
- **WHEN** `a.model_tunings["phi-3.gguf"] = {"ctx_size": 8192, "n_gpu_layers": 35, "threads": 8}` is executed
- **THEN** `b.model_tunings == {}` (per-instance `default_factory` honored)

#### Scenario: 4 new fields round-trip through save+load (v0.9.0)

- **GIVEN** `BellbirdConfig(safe_vram_mode=True, status_toggles={"model_name": False}, model_tunings={"a.gguf": {"ctx_size": 4096, "n_gpu_layers": 35, "threads": 4}}, pre_send_warn=False)` and `tmp_path`
- **WHEN** `save_config(cfg, tmp_path/"c.json")` runs and
  `load_config()` reads it back
- **THEN** the loaded `safe_vram_mode is True`
- **AND** the loaded `status_toggles["model_name"] is False`
- **AND** the loaded `model_tunings["a.gguf"]["ctx_size"] == 4096`
- **AND** the loaded `pre_send_warn is False`

#### Scenario: missing new keys in old config fall back to defaults (v0.9.0)

- **GIVEN** a `config.json` from v0.8.3 with NO `safe_vram_mode`,
  `status_toggles`, `model_tunings`, or `pre_send_warn` keys
- **WHEN** `load_config()` runs on v0.9.0
- **THEN** the loaded config equals `BellbirdConfig()` with the new
  defaults (`safe_vram_mode is False`, `status_toggles` all ON,
  `model_tunings == {}`, `pre_send_warn is True`)
- **AND** no `KeyError` is raised

### Requirement: `BellbirdConfig.status_toggles_as_set()` returns active toggle names

`BellbirdConfig` SHALL expose a method
`status_toggles_as_set(self) -> set[str]` that returns the keys of
`self.status_toggles` whose value is `True` (the active component
names the F2 `format_status` call should include). When
`self.status_toggles` is empty (an old config that pre-dates the
field AND somehow bypassed the `default_factory` — defensive), the
method SHALL return an empty set (the formatter degrades to `""`).

#### Scenario: returns the True-valued keys

- **GIVEN** `BellbirdConfig(status_toggles={"model_name": True, "context_pct": False, "temperature": True})`
- **WHEN** `cfg.status_toggles_as_set()` is called
- **THEN** the result equals `{"model_name", "temperature"}`

#### Scenario: empty dict returns empty set (regression guard)

- **GIVEN** `BellbirdConfig(status_toggles={})` (constructed via
  `dataclasses.replace` or a hypothetical old config)
- **WHEN** `cfg.status_toggles_as_set()` is called
- **THEN** the result is `set()` and no error is raised

### Requirement: `PreferencesDialog` — Estado (F2) Tab [v0.9.0]

`PreferencesDialog` SHALL add a seventh tab "Estado (F2)" to the
existing `wx.Notebook`, AFTER "Atajos" (so the order ends
"… → Atajos → Estado (F2)"). The tab SHALL contain one
`wx.CheckBox` per name in `DEFAULT_STATUS_TOGGLES` (10 checkboxes in
the canonical order: `model_name`, `context_pct`, `max_tokens`,
`server`, `vram`, `fit`, `message_count`, `temperature`, `top_p`,
`tok_per_s`, `is_generating`), each preceded by a `wx.StaticText`
label with a mnemonic `&` (per AGENTS.md accessibility rule) and a
`name=` of the form `"pref_status_toggle_<toggle_name>"`. The
checkboxes SHALL bind to the `BellbirdConfig.status_toggles` dict:
checked ↔ `True`, unchecked ↔ `False`. The dialog's `_apply_config`
SHALL write the new dict back into `self._config.status_toggles`
BEFORE `EndModal(wx.ID_OK)`.

#### Scenario: 10 CheckBoxes in canonical order [windows-only]

- **GIVEN** `MainWindow` is constructed with default `BellbirdConfig`
- **WHEN** the test inspects the "Estado (F2)" tab
- **THEN** exactly 10 `wx.CheckBox` controls are present, with
  `name=` matching `^pref_status_toggle_` and names matching
  `model_name, context_pct, max_tokens, server, vram, fit,
  message_count, temperature, top_p, tok_per_s, is_generating`
- **AND** each CheckBox is preceded (in the sizer) by a
  `wx.StaticText` label with a mnemonic `&`

#### Scenario: changing a toggle takes effect on the next F2 (regression guard)

- **GIVEN** the user unchecks `model_name` in the "Estado (F2)" tab
  AND clicks Aceptar
- **WHEN** the user presses F2
- **THEN** the spoken / `speech.output` text does NOT contain
  `"model_name"`'s phrasing (the toggle was honored on the next
  F2 without a restart)

#### Scenario: Cancel leaves the dict untouched [windows-only]

- **GIVEN** `BellbirdConfig(status_toggles={t: True for t in DEFAULT_STATUS_TOGGLES})`
- **WHEN** the user unchecks a toggle and dismisses with Cancel
- **THEN** `self._config.status_toggles` is unchanged (the in-memory
  config and the on-disk `data/config.json` are both untouched)

### Requirement: Avanzado Tab — "Ayuda de encaje" StaticText [v0.9.0]

`PreferencesDialog` SHALL add a single read-only `wx.StaticText`
(`name="pref_fit_help"`, label initially `""`) to the existing
"Avanzado" tab, AFTER the GPU-layers spin and BEFORE the server-port
spin. The dialog's `ShowModal` lifecycle SHALL populate the
StaticText's label on dialog construction by calling
`ContextAdvisor.estimate_fit(...)` with the current `ctx_size` and
`n_gpu_layers` from `self._config` (plus a `GGUFMetadata` from
`read_gguf_metadata(self._config.last_model)` if available, else
`GGUFMetadata(size_bytes=estimate_size_bytes(self._config.last_model),
block_count=0, context_length=0, file_type="unknown")`) and writing
`report.message` into the label. The label SHALL be refreshed when
the user changes `ctx_size` or `n_gpu_layers` (a slider / spin
event handler) but MAY be lazy-refreshed when the tab is opened
(the 10 s TTL cache on `MainWindow._last_fit_check_mono` is the
canonical implementation; the dialog can call directly without the
cache). The StaticText is the read-only display of the heuristic
output — there is no "Aplicar" button (out of scope per the
proposal).

#### Scenario: "Ayuda de encaje" StaticText present with non-empty label [windows-only]

- **GIVEN** `MainWindow` is constructed with default `BellbirdConfig`
  (`ctx_size=4096`, `n_gpu_layers=99`) AND a `nvidia-smi` returning
  `(8192, 12288)` (or `(None, None)` on non-Windows — both are valid)
- **WHEN** the test inspects the "Avanzado" tab
- **THEN** a `wx.StaticText` with `name="pref_fit_help"` is present
- **AND** the label is a non-empty Spanish one-liner (the
  `estimate_fit` output)

#### Scenario: "Ayuda de encaje" refreshes when `ctx_size` changes [windows-only]

- **GIVEN** the "Avanzado" tab is open AND the user changes
  `ctx_size` from 4096 to 32768 (a 8x jump in KV pressure)
- **WHEN** the spin event fires
- **THEN** the `pref_fit_help` StaticText label is updated to a new
  Spanish one-liner (the estimate for the new `ctx_size`)
- **AND** no error is raised (the refresh is best-effort; if
  `read_vram` returns `(None, None)` the label may be unchanged)

#### Scenario: missing `last_model` does not break the StaticText [windows-only]

- **GIVEN** `self._config.last_model == ""` (no model loaded yet)
- **WHEN** the dialog constructs the Avanzado tab
- **THEN** `read_gguf_metadata` returns `None` AND
  `estimate_size_bytes("")` returns `None`
- **AND** `estimate_fit` is called with a sentinel
  `GGUFMetadata(size_bytes=0, block_count=0, context_length=0, file_type="unknown")`
- **AND** the StaticText label is the Spanish one-liner from the
  sentinel-driven estimate (not a crash, not a `wx.MessageDialog`)

## Test strategy

- WSL: extend `tests/core/test_config.py` with `TestV090Config`
  class — per-instance defaults, round-trip, missing-key
  forward-compat (4 scenarios). Add `TestStatusTogglesAsSet` to
  cover the helper method (2 scenarios).
- Windows (`run_tests.bat` wx-runtime block): extend
  `tests/ui/test_preferences_dialog_static.py` with
  `TestEstadoF2Tab` (10 CheckBoxes + StaticText labels + names) and
  `TestAvanzadoFitHelp` (`pref_fit_help` StaticText presence, refresh
  on spin change, missing `last_model` graceful). Both classes MUST
  be registered in `run_tests.bat` under the wx-runtime pytest
  block.

## ADDED Requirements

### Requirement: `BellbirdConfig` 4 new fields round-trip via the standard `__dataclass_fields__` filter

The 4 new fields `safe_vram_mode`, `status_toggles`, `model_tunings`,
and `pre_send_warn` SHALL round-trip via the existing `save_config` /
`load_config` pipeline. The `__dataclass_fields__` filter at
`core/config.py:92-93` (the v0.8.2 forward-compat mechanism) MUST
silently fill missing keys with the field defaults — no migration
entry in `_MIGRATIONS` is required, and `_MIGRATIONS` remains
single-entry (`max_tokens`). `status_toggles` SHALL be a per-instance
dict (each `BellbirdConfig()` instance gets a fresh `dict[str, bool]`
with every `DEFAULT_STATUS_TOGGLES` key set to `True`).
`model_tunings` SHALL be a per-instance dict that the runtime NEVER
auto-prunes when a model file disappears from disk (the user cleans
up manually — silent pruning would surprise the user, per the v0.8.2
recents-pattern decision).

#### Scenario: `status_toggles` default is per-instance dict with all keys True (v0.9.0)

- **GIVEN** two fresh `BellbirdConfig()` instances `a` and `b`
- **WHEN** `a.status_toggles["model_name"] = False` is executed
- **THEN** `b.status_toggles["model_name"] is True` (per-instance
  `default_factory` honored)
- **AND** every name in `DEFAULT_STATUS_TOGGLES` is present as a
  key in `b.status_toggles` (the all-ON first-run invariant)

#### Scenario: `model_tunings` default is per-instance empty dict (v0.9.0)

- **GIVEN** two fresh `BellbirdConfig()` instances `a` and `b`
- **WHEN** `a.model_tunings["phi-3.gguf"] = {"ctx_size": 8192, "n_gpu_layers": 35, "threads": 8}` is executed
- **THEN** `b.model_tunings == {}` (per-instance `default_factory` honored)

#### Scenario: 4 new fields round-trip through save+load (v0.9.0)

- **GIVEN** `BellbirdConfig(safe_vram_mode=True, status_toggles={"model_name": False}, model_tunings={"a.gguf": {"ctx_size": 4096, "n_gpu_layers": 35, "threads": 4}}, pre_send_warn=False)` and `tmp_path`
- **WHEN** `save_config(cfg, tmp_path/"c.json")` runs and
  `load_config()` reads it back
- **THEN** the loaded `safe_vram_mode is True`
- **AND** the loaded `status_toggles["model_name"] is False`
- **AND** the loaded `model_tunings["a.gguf"]["ctx_size"] == 4096`
- **AND** the loaded `pre_send_warn is False`

#### Scenario: missing new keys in old config fall back to defaults (v0.9.0)

- **GIVEN** a `config.json` from v0.8.3 with NO `safe_vram_mode`,
  `status_toggles`, `model_tunings`, or `pre_send_warn` keys
- **WHEN** `load_config()` runs on v0.9.0
- **THEN** the loaded config equals `BellbirdConfig()` with the new
  defaults (`safe_vram_mode is False`, `status_toggles` all ON,
  `model_tunings == {}`, `pre_send_warn is True`)
- **AND** no `KeyError` is raised

### Requirement: `BellbirdConfig.status_toggles_as_set()` returns active toggle names

`BellbirdConfig` SHALL expose a method
`status_toggles_as_set(self) -> set[str]` that returns the keys of
`self.status_toggles` whose value is `True` (the active component
names the F2 `format_status` call should include). When
`self.status_toggles` is empty (an old config that pre-dates the
field AND somehow bypassed the `default_factory` — defensive), the
method SHALL return an empty set (the formatter degrades to `""`).

#### Scenario: returns the True-valued keys

- **GIVEN** `BellbirdConfig(status_toggles={"model_name": True, "context_pct": False, "temperature": True})`
- **WHEN** `cfg.status_toggles_as_set()` is called
- **THEN** the result equals `{"model_name", "temperature"}`

#### Scenario: empty dict returns empty set (regression guard)

- **GIVEN** `BellbirdConfig(status_toggles={})` (constructed via
  `dataclasses.replace` or a hypothetical old config)
- **WHEN** `cfg.status_toggles_as_set()` is called
- **THEN** the result is `set()` and no error is raised

### Requirement: `PreferencesDialog` — Estado (F2) Tab [v0.9.0]

`PreferencesDialog` SHALL add a seventh tab "Estado (F2)" to the
existing `wx.Notebook`, AFTER "Atajos" (so the order ends
"… → Atajos → Estado (F2)"). The tab SHALL contain one
`wx.CheckBox` per name in `DEFAULT_STATUS_TOGGLES` (10 checkboxes in
the canonical order: `model_name`, `context_pct`, `max_tokens`,
`server`, `vram`, `fit`, `message_count`, `temperature`, `top_p`,
`tok_per_s`, `is_generating`), each preceded by a `wx.StaticText`
label with a mnemonic `&` (per AGENTS.md accessibility rule) and a
`name=` of the form `"pref_status_toggle_<toggle_name>"`. The
checkboxes SHALL bind to the `BellbirdConfig.status_toggles` dict:
checked ↔ `True`, unchecked ↔ `False`. The dialog's `_apply_config`
SHALL write the new dict back into `self._config.status_toggles`
BEFORE `EndModal(wx.ID_OK)`.

#### Scenario: 10 CheckBoxes in canonical order [windows-only]

- **GIVEN** `MainWindow` is constructed with default `BellbirdConfig`
- **WHEN** the test inspects the "Estado (F2)" tab
- **THEN** exactly 10 `wx.CheckBox` controls are present, with
  `name=` matching `^pref_status_toggle_` and names matching
  `model_name, context_pct, max_tokens, server, vram, fit,
  message_count, temperature, top_p, tok_per_s, is_generating`
- **AND** each CheckBox is preceded (in the sizer) by a
  `wx.StaticText` label with a mnemonic `&`

#### Scenario: changing a toggle takes effect on the next F2 (regression guard)

- **GIVEN** the user unchecks `model_name` in the "Estado (F2)" tab
  AND clicks Aceptar
- **WHEN** the user presses F2
- **THEN** the spoken / `speech.output` text does NOT contain
  `"model_name"`'s phrasing (the toggle was honored on the next F2
  without a restart)

#### Scenario: Cancel leaves the dict untouched [windows-only]

- **GIVEN** `BellbirdConfig(status_toggles={t: True for t in DEFAULT_STATUS_TOGGLES})`
- **WHEN** the user unchecks a toggle and dismisses with Cancel
- **THEN** `self._config.status_toggles` is unchanged (the in-memory
  config and the on-disk `data/config.json` are both untouched)

### Requirement: Avanzado Tab — "Ayuda de encaje" StaticText [v0.9.0]

`PreferencesDialog` SHALL add a single read-only `wx.StaticText`
(`name="pref_fit_help"`, label initially `""`) to the existing
"Avanzado" tab, AFTER the GPU-layers spin and BEFORE the server-port
spin. The dialog's `ShowModal` lifecycle SHALL populate the
StaticText's label on dialog construction by calling
`ContextAdvisor.estimate_fit(...)` with the current `ctx_size` and
`n_gpu_layers` from `self._config` (plus a `GGUFMetadata` from
`read_gguf_metadata(self._config.last_model)` if available, else
`GGUFMetadata(size_bytes=estimate_size_bytes(self._config.last_model),
block_count=0, context_length=0, file_type="unknown")`) and writing
`report.message` into the label. The label SHALL be refreshed when
the user changes `ctx_size` or `n_gpu_layers` (a slider / spin
event handler) but MAY be lazy-refreshed when the tab is opened
(the 10 s TTL cache on `MainWindow._last_fit_check_mono` is the
canonical implementation; the dialog can call directly without the
cache). The StaticText is the read-only display of the heuristic
output — there is no "Aplicar" button (out of scope per the
proposal).

#### Scenario: "Ayuda de encaje" StaticText present with non-empty label [windows-only]

- **GIVEN** `MainWindow` is constructed with default `BellbirdConfig`
  (`ctx_size=4096`, `n_gpu_layers=99`) AND a `nvidia-smi` returning
  `(8192, 12288)` (or `(None, None)` on non-Windows — both are valid)
- **WHEN** the test inspects the "Avanzado" tab
- **THEN** a `wx.StaticText` with `name="pref_fit_help"` is present
- **AND** the label is a non-empty Spanish one-liner (the
  `estimate_fit` output)

#### Scenario: "Ayuda de encaje" refreshes when `ctx_size` changes [windows-only]

- **GIVEN** the "Avanzado" tab is open AND the user changes
  `ctx_size` from 4096 to 32768 (a 8x jump in KV pressure)
- **WHEN** the spin event fires
- **THEN** the `pref_fit_help` StaticText label is updated to a new
  Spanish one-liner (the estimate for the new `ctx_size`)
- **AND** no error is raised (the refresh is best-effort; if
  `read_vram` returns `(None, None)` the label may be unchanged)

#### Scenario: missing `last_model` does not break the StaticText [windows-only]

- **GIVEN** `self._config.last_model == ""` (no model loaded yet)
- **WHEN** the dialog constructs the Avanzado tab
- **THEN** `read_gguf_metadata` returns `None` AND
  `estimate_size_bytes("")` returns `None`
- **AND** `estimate_fit` is called with a sentinel
  `GGUFMetadata(size_bytes=0, block_count=0, context_length=0, file_type="unknown")`
- **AND** the StaticText label is the Spanish one-liner from the
  sentinel-driven estimate (not a crash, not a `wx.MessageDialog`)

## Added in v0.10.0 (audio-output-tts-notifications)

<!-- Merged from `openspec/changes/archive/2026-06-25-audio-output-tts-notifications/specs/app-configuration/spec.md` -->

### Requirement: Audio Output Fields (v0.10.0)

`BellbirdConfig` MUST gain the following six fields, all
additive:

| Field | Type | Default | Notes |
|---|---|---|---|
| `system_voice_name` `[v0.10.0]` | `str` | `""` | SAPI voice name; `""` = first available. |
| `system_voice_rate` `[v0.10.0]` | `int` | `0` | SAPI rate, range `[-10, +10]`; the voice dialog validates the slider bounds. |
| `auto_speak_responses` `[v0.10.0]` | `bool` | `False` | **Off by default** — never auto-reads. Only explicit F8 (or a future button) calls `speak_with_system_voice`. |
| `notifications_enabled` `[v0.10.0]` | `bool` | `True` | Master toast toggle (see `notifications` spec). |
| `sounds_enabled` `[v0.10.0]` | `bool` | `True` | Master sound-cue toggle. |
| `sound_theme` `[v0.10.0]` | `str` | `"default"` | Subdir of `data/sounds/`. `"none"` → no playback. |

(Previously: the dataclass had 28 fields ending at `pre_send_warn`;
the six new fields extend the shape additively. After v0.10.0:
**34 fields** total.)

#### Scenario: All six new fields exist with documented defaults

- GIVEN a fresh `BellbirdConfig()`
- WHEN the field values are read
- THEN `system_voice_name == ""`
- AND `system_voice_rate == 0`
- AND `auto_speak_responses is False`
- AND `notifications_enabled is True`
- AND `sounds_enabled is True`
- AND `sound_theme == "default"`

#### Scenario: save/load round-trip preserves the new fields

- GIVEN a `BellbirdConfig` with `auto_speak_responses=True`,
  `sound_theme="custom"`, `system_voice_rate=3`,
  `notifications_enabled=False`
- WHEN `save_config(cfg, path)` then `load_config(path)` runs
- THEN the loaded config equals the original
  (all 6 new fields round-trip, no data loss)

#### Scenario: forward-compat — unknown keys are silently dropped (regression guard)

- GIVEN a JSON config file with a `future_field` key that no
  build knows about
- WHEN `load_config` runs
- THEN no exception is raised
- AND the known 6 new fields load with their stored values
- AND `future_field` is dropped silently
  (the `__dataclass_fields__` filter, unchanged from v0.8.2,
  protects the round-trip in both directions)

#### Scenario: `auto_speak_responses=False` is the safe default (regression guard)

- GIVEN a fresh `BellbirdConfig()` (no user edits)
- WHEN the application reads the config
- THEN `auto_speak_responses is False`
- AND no code path in `core/` or `ui/` auto-calls
  `speak_with_system_voice` on generation completion
  (the existing `speech.speak("Respuesta completa")` is the
  only on-done voice output; the new channel fires only on
  explicit F8 — see `app-shell` v0.10.0)

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
