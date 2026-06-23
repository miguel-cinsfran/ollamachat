# parameters Spec — Delta for v0.3.0

## Purpose

Adds the `use_model_button` (action button that loads the selected model and starts the server in one step), renames `start_server_button` to `restart_server_button`, and tightens the `use_model_button` enable/disable rules so the button is only active when a model is selected. `get_system_prompt()` / `set_system_prompt()` already exist in the main spec and remain unchanged.

## ADDED Requirements

### Requirement: `use_model_button` Loads and Starts in One Click

`ParamsPanel` SHALL provide a `wx.Button` named `use_model_button` with label `"Usar modelo"`, placed in the same horizontal sizer row as `scan_models_button` and `browse_model_button`. The button MUST be preceded by a `wx.StaticText("Acciones del modelo:")` (or grouped under a parent label) and MUST use only `wx.BoxSizer` for that row.

`MainWindow._on_use_model` SHALL: (1) call `params_panel.get_model()` to obtain the path, (2) disable `use_model_button` and `restart_server_button`, (3) speak `"Iniciando servidor con <basename>..."`, (4) call `LlamaRunner.start_server(...)` in a background thread (see app-shell delta), and (5) on completion re-enable or remain disabled per the result.

#### Scenario: Button is present and named

- **GIVEN** a fresh `ParamsPanel`
- **WHEN** the source is inspected
- **THEN** `use_model_button.GetName() == "use_model_button"`
- **AND** the button is in a `wx.BoxSizer` row
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
- **WHEN** `add_model("C:\\m\\b.gguf")` is called
- **THEN** `use_model_button.IsEnabled() is True`

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
