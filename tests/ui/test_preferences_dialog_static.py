"""Static/AST tests for PreferencesDialog — accessibility compliance via source.

Tests verify: 5 tab labels present, no GridSizer, SetEscapeId set,
OK handler calls _apply_config before EndModal, every widget has name=.
"""

import ast
import pathlib
import re

import pytest


def _get_ui_path(filename: str) -> pathlib.Path:
    """Resolve the source file path for a UI module."""
    return (
        pathlib.Path(__file__).resolve().parent.parent.parent
        / "bellbird"
        / "ui"
        / filename
    )


def _get_func_name(node: ast.Call) -> str:
    """Extract the full function name from a Call node."""
    if isinstance(node.func, ast.Attribute):
        if isinstance(node.func.value, ast.Attribute):
            return f"{_get_attr_name(node.func.value)}.{node.func.attr}"
        elif isinstance(node.func.value, ast.Name):
            return f"{node.func.value.id}.{node.func.attr}"
        return node.func.attr
    elif isinstance(node.func, ast.Name):
        return node.func.id
    return "<unknown>"


def _get_attr_name(node: ast.AST) -> str:
    """Extract the dotted name from a nested attribute node."""
    if isinstance(node, ast.Attribute):
        return f"{_get_attr_name(node.value)}.{node.attr}"
    elif isinstance(node, ast.Name):
        return node.id
    return "<unknown>"


def test_all_tabs_present():
    """All five tab labels exist in the source (with & mnemonics)."""
    source_path = _get_ui_path("preferences_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    for label in ("General", "Modelo", "Herramientas", "Avanzado"):
        # Labels may have & prefix (e.g. "&General")
        assert label in source or f"&{label}" in source, (
            f"Tab label {label!r} not found in source"
        )
    # "Chat" is "C&hat" (mnemonic on 'h')
    assert "C&hat" in source, "Tab label 'Chat' (as C&hat) not found in source"


def test_no_grid_sizer():
    """No GridSizer/FlexGridSizer/GridBagSizer is used in the dialog."""
    source_path = _get_ui_path("preferences_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_sizers = {
        "wx.GridSizer",
        "wx.FlexGridSizer",
        "wx.GridBagSizer",
    }

    found_forbidden = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node)
            if func_name in forbidden_sizers:
                found_forbidden.append(f"Line {node.lineno}: {func_name}")

    assert not found_forbidden, (
        "Forbidden sizers found:\n" + "\n".join(found_forbidden)
    )


def test_set_escape_id_called():
    """SetEscapeId(wx.ID_CANCEL) is called in the dialog source.

    Verifies the specific argument wx.ID_CANCEL (not just any SetEscapeId call),
    so a future refactor that calls SetEscapeId(wx.ID_OK) — which would break
    Escape-key cancel — would fail this test.
    """
    import re
    source_path = _get_ui_path("preferences_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    pattern = r"SetEscapeId\s*\(\s*wx\.ID_CANCEL\s*\)"
    assert re.search(pattern, source), (
        "SetEscapeId(wx.ID_CANCEL) not found in preferences_dialog.py — "
        "Escape must cancel the dialog, not confirm it"
    )


def test_ok_handler_calls_apply_config_before_end_modal():
    """The OK button handler calls _apply_config() before EndModal(wx.ID_OK).

    This ensures config validation/writing happens before the dialog closes.
    The ordering matters: if EndModal fires before _apply_config, the edited
    config is silently discarded (regression guard).
    """
    source_path = _get_ui_path("preferences_dialog.py")
    source = source_path.read_text(encoding="utf-8")

    m = re.search(
        r"def _on_ok\(self.*?\).*?:.*?(?=\n    def |\nclass |\Z)",
        source,
        re.DOTALL,
    )
    assert m is not None, "_on_ok method not found in preferences_dialog.py"
    body = m.group(0)

    assert "_apply_config" in body, (
        "_on_ok must call _apply_config()"
    )
    assert "EndModal(wx.ID_OK)" in body, (
        "_on_ok must call EndModal(wx.ID_OK)"
    )
    # Ordering check: _apply_config must appear before EndModal
    assert body.index("_apply_config") < body.index("EndModal"), (
        "_apply_config() must be called BEFORE EndModal(wx.ID_OK) in _on_ok"
    )


def test_all_controls_have_name():
    """Every interactive widget has a name= parameter.

    Checks wx.Button, wx.Slider, wx.TextCtrl, wx.SpinCtrl, wx.ListBox,
    and wx.CheckBox constructor calls for a name= keyword argument.
    """
    source_path = _get_ui_path("preferences_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    widget_constructors = {
        "wx.Button",
        "wx.Slider",
        "wx.TextCtrl",
        "wx.SpinCtrl",
        "wx.ListBox",
        "wx.CheckBox",
    }

    calls_without_name = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node)
            if func_name in widget_constructors:
                has_name = any(
                    kw.arg == "name" for kw in node.keywords if kw.arg is not None
                )
                if not has_name:
                    calls_without_name.append(
                        f"Line {node.lineno}: {func_name} without name="
                    )

    assert not calls_without_name, (
        "Widgets missing name=:\n" + "\n".join(calls_without_name)
    )


# ─── Phase 4: samplers-modernos — min_p slider, seed spin, stop text (v0.7.2) ─


def _get_method_source(source: str, tree: ast.AST, method_name: str) -> str | None:
    """Extract raw source of a method from the PreferencesDialog class."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "PreferencesDialog":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    source_lines = source.splitlines()
                    return "\n".join(source_lines[item.lineno - 1:item.end_lineno])
    return None


def test_min_p_slider_present():
    """pref_min_p_slider exists with name= and preceded by StaticText(label='Min-p:')."""
    source_path = _get_ui_path("preferences_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Find _build_model_page
    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "PreferencesDialog":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "_build_model_page":
                    method = item
                    break
    assert method is not None, "_build_model_page method not found"

    # Check the raw source, not the ast-unparsed version (which normalizes quotes)
    source_lines = source.splitlines()
    start = method.lineno - 1
    end = method.end_lineno
    method_source = "\n".join(source_lines[start:end])
    assert 'name="pref_min_p_slider"' in method_source, (
        "pref_min_p_slider with name='pref_min_p_slider' must be in _build_model_page"
    )
    assert "Min-p:" in method_source, (
        "pref_min_p_slider must be preceded by wx.StaticText(label='Min-p:')"
    )


def test_seed_spin_present_in_advanced():
    """pref_seed_spin is constructed inside _build_advanced_page, not _build_model_page."""
    source_path = _get_ui_path("preferences_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Find both methods
    advanced = None
    model = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "PreferencesDialog":
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    if item.name == "_build_advanced_page":
                        advanced = item
                    elif item.name == "_build_model_page":
                        model = item

    assert advanced is not None, "_build_advanced_page not found"
    assert model is not None, "_build_model_page not found"

    source_lines = source.splitlines()
    advanced_src = "\n".join(source_lines[advanced.lineno - 1:advanced.end_lineno])
    model_src = "\n".join(source_lines[model.lineno - 1:model.end_lineno])

    assert 'name="pref_seed_spin"' in advanced_src, (
        "pref_seed_spin must be constructed inside _build_advanced_page"
    )
    assert 'name="pref_seed_spin"' not in model_src, (
        "pref_seed_spin must NOT be in _build_model_page"
    )
    assert "Semilla:" in advanced_src, (
        "pref_seed_spin must be preceded by wx.StaticText(label='Semilla:')"
    )


def test_stop_text_present_in_advanced():
    """pref_stop_text with style=wx.TE_MULTILINE is in _build_advanced_page."""
    source_path = _get_ui_path("preferences_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    advanced = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "PreferencesDialog":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "_build_advanced_page":
                    advanced = item
                    break

    assert advanced is not None, "_build_advanced_page not found"
    source_lines = source.splitlines()
    advanced_src = "\n".join(source_lines[advanced.lineno - 1:advanced.end_lineno])

    assert 'name="pref_stop_text"' in advanced_src, (
        "pref_stop_text with name='pref_stop_text' must be in _build_advanced_page"
    )
    assert "TE_MULTILINE" in advanced_src, (
        "pref_stop_text must use style=wx.TE_MULTILINE"
    )
    assert "Cadenas de parada" in advanced_src, (
        "pref_stop_text must be preceded by wx.StaticText with 'Cadenas de parada' label"
    )


def test_no_grid_sizer_in_preferences():
    """No GridSizer/FlexGridSizer/GridBagSizer in preferences_dialog.py."""
    source_path = _get_ui_path("preferences_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_sizers = {
        "wx.GridSizer",
        "wx.FlexGridSizer",
        "wx.GridBagSizer",
    }
    found_forbidden = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node)
            if func_name in forbidden_sizers:
                found_forbidden.append(f"Line {node.lineno}: {func_name}")

    assert not found_forbidden, (
        "Forbidden sizers found:\n" + "\n".join(found_forbidden)
    )


def test_top_p_k_repeat_moved_to_advanced():
    """top_p/top_k/repeat_penalty controls are in _build_advanced_page, NOT _build_model_page."""
    source_path = _get_ui_path("preferences_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    advanced = None
    model = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "PreferencesDialog":
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    if item.name == "_build_advanced_page":
                        advanced = item
                    elif item.name == "_build_model_page":
                        model = item

    assert advanced is not None, "_build_advanced_page not found"
    assert model is not None, "_build_model_page not found"

    source_lines = source.splitlines()
    advanced_src = "\n".join(source_lines[advanced.lineno - 1:advanced.end_lineno])
    model_src = "\n".join(source_lines[model.lineno - 1:model.end_lineno])

    for name in ("pref_top_p_slider", "pref_top_k_spin", "pref_repeat_slider"):
        assert f'name="{name}"' in advanced_src, (
            f"{name} must be in _build_advanced_page"
        )
        assert f'name="{name}"' not in model_src, (
            f"{name} must NOT be in _build_model_page"
        )


def test_max_tokens_stays_in_modelo():
    """pref_max_tokens_spin is in _build_model_page, NOT _build_advanced_page."""
    source_path = _get_ui_path("preferences_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    advanced = None
    model = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "PreferencesDialog":
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    if item.name == "_build_advanced_page":
                        advanced = item
                    elif item.name == "_build_model_page":
                        model = item

    assert advanced is not None, "_build_advanced_page not found"
    assert model is not None, "_build_model_page not found"

    source_lines = source.splitlines()
    model_src = "\n".join(source_lines[model.lineno - 1:model.end_lineno])
    advanced_src = "\n".join(source_lines[advanced.lineno - 1:advanced.end_lineno])

    assert 'name="pref_max_tokens_spin"' in model_src, (
        "pref_max_tokens_spin must be in _build_model_page"
    )
    assert 'name="pref_max_tokens_spin"' not in advanced_src, (
        "pref_max_tokens_spin must NOT be in _build_advanced_page"
    )


def test_apply_config_reads_new_fields():
    """_apply_config body has assignments to self._config.min_p, .seed, .stop."""
    source_path = _get_ui_path("preferences_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    method_source = _get_method_source(source, tree, "_apply_config")
    assert method_source is not None, "_apply_config method not found"

    assert "self._config.min_p" in method_source, (
        "_apply_config must assign to self._config.min_p"
    )
    assert "self._config.seed" in method_source, (
        "_apply_config must assign to self._config.seed"
    )
    assert "self._config.stop" in method_source, (
        "_apply_config must assign to self._config.stop"
    )


def test_min_p_value_label_present():
    """pref_min_p_label (min_p_value_label) is constructed in _build_model_page."""
    source_path = _get_ui_path("preferences_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    model = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "PreferencesDialog":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "_build_model_page":
                    model = item
                    break

    assert model is not None, "_build_model_page not found"
    source_lines = source.splitlines()
    model_src = "\n".join(source_lines[model.lineno - 1:model.end_lineno])

    assert 'name="min_p_value_label"' in model_src, (
        "pref_min_p_label with name='min_p_value_label' must be in _build_model_page"
    )


def test_max_tokens_spin_has_name_and_statictext():
    """pref_max_tokens_spin has name= and preceding StaticText with Spanish label."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    assert 'name="pref_max_tokens_spin"' in source, (
        "pref_max_tokens_spin must have name='pref_max_tokens_spin'"
    )
    assert "Má&ximo de tokens:" in source or "M\u00e1&ximo de tokens:" in source, (
        "pref_max_tokens_spin must be preceded by 'Má&ximo de tokens:' StaticText"
    )


def test_on_slider_change_dispatches_min_p():
    """_on_slider_change has an elif branch for pref_min_p_slider."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    assert "pref_min_p_slider" in source, (
        "_on_slider_change must dispatch on pref_min_p_slider"
    )


# ─── WU-2: Estado (F2) tab (T-WU2-05) ──────────────────────────────────────────


def test_estado_f2_tab_has_11_checkboxes():
    """Estado (F2) tab has exactly 11 CheckBox controls with chk_ names."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    # Verify the iteration over DEFAULT_STATUS_TOGGLES creates checkboxes
    assert "for toggle_name in DEFAULT_STATUS_TOGGLES" in source, (
        "Estado tab must iterate DEFAULT_STATUS_TOGGLES"
    )
    # Verify CheckBox creation with chk_ pattern
    assert 'name=f"chk_{toggle_name}"' in source, (
        "CheckBox creation with chk_ pattern not found in _build_status_page"
    )
    # Verify StaticText labels are also created with lbl_ pattern
    assert 'name=f"lbl_{toggle_name}"' in source, (
        "StaticText label with lbl_ pattern not found"
    )
    # Verify all 11 toggle labels are present in _build_status_page
    expected_labels = [
        "&Modelo", "&Porcentaje de contexto", "&Máx tokens/respuesta",
        "&Servidor", "&VRAM libre", "&Encaje", "&Mensajes",
        "&Temperatura", "&Top-p", "&Tok/s última", "&Generando",
    ]
    for label in expected_labels:
        assert label in source, (
            f"Status tab is missing label: {label!r}"
        )


def test_estado_f2_tab_each_checkbox_has_statictext():
    """Each CheckBox in Estado tab has a preceding wx.StaticText label."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    # Checkboxes use f"chk_{toggle_name}" pattern; labels use f"lbl_{toggle_name}"
    # Verify lbl_ prefix exists in _build_status_page
    assert "lbl_" in source, (
        "Missing lbl_ prefix for StaticText labels in Estado tab"
    )
    # Verify labels are created in the loop before checkboxes
    method = re.search(
        r"def _build_status_page\(self.*?\).*?:.*?(?=\n    def |\nclass |\Z)",
        source,
        re.DOTALL,
    )
    assert method is not None, "_build_status_page method not found"
    body = method.group(0)
    assert "wx.StaticText" in body, (
        "_build_status_page must create wx.StaticText controls"
    )


def test_estado_f2_tab_checkboxes_have_name():
    """Every CheckBox in Estado tab has a name= attribute."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    # Checkboxes use f"chk_{toggle_name}" — verify the pattern
    assert 'name=f"chk_{toggle_name}"' in source, (
        "CheckBox name= must be defined with f-string chk_ prefix"
    )
    # Verify _status_checkboxes dict maps toggle names to CheckBox widgets
    # (this proves 11 checkbox instances are tracked)
    method = re.search(
        r"def _build_status_page\(self.*?\).*?:.*?(?=\n    def |\nclass |\Z)",
        source,
        re.DOTALL,
    )
    assert method is not None, "_build_status_page method not found"
    body = method.group(0)
    # Count wx.CheckBox calls in the method
    checkbox_calls = body.count("wx.CheckBox")
    assert checkbox_calls >= 1, (
        "_build_status_page must create wx.CheckBox controls"
    )


def test_estado_f2_tab_has_mnemonics():
    """Estado tab labels contain mnemonic '&' characters."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    # The labels are defined in the toggle_labels dict inside _build_status_page
    # Check each expected label has '&' in the toggle_labels dict
    expected_mnemonics = [
        "&Modelo", "&Porcentaje", "&Máx tokens", "&Servidor",
        "&VRAM", "&Encaje", "&Mensajes", "&Temperatura",
        "&Top-p", "&Tok/s", "&Generando",
    ]
    for mnemonic in expected_mnemonics:
        assert mnemonic in source, (
            f"Expected mnemonic label {mnemonic!r} not found in _build_status_page"
        )


# ─── WU-2: Ayuda de encaje (T-WU2-06) ──────────────────────────────────────────


def test_fit_help_statictext_present():
    """Avanzado tab has wx.StaticText with name='pref_fit_help'."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    assert 'name="pref_fit_help"' in source, (
        "pref_fit_help StaticText not found in preferences_dialog.py"
    )
    assert "Ayuda de encaje" in source, (
        "Ayuda de encaje label not found in preferences_dialog.py"
    )


def test_fit_help_refresh_called_on_spin_change():
    """_on_advanced_spin_change calls _refresh_fit_help."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    import re
    m = re.search(
        r"def _on_advanced_spin_change.*?:.*?(?=\n    def |\nclass |\Z)",
        source,
        re.DOTALL,
    )
    assert m is not None, "_on_advanced_spin_change method not found"
    body = m.group(0)
    assert "_refresh_fit_help" in body, (
        "_on_advanced_spin_change must call _refresh_fit_help"
    )


def test_fit_help_uses_cached_vram():
    """_refresh_fit_help uses self._vram_cache (not read_vram direct)."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    import re
    m = re.search(
        r"def _refresh_fit_help.*?:.*?(?=\n    def |\nclass |\Z)",
        source,
        re.DOTALL,
    )
    assert m is not None, "_refresh_fit_help method not found"
    body = m.group(0)
    assert "self._vram_cache" in body, (
        "_refresh_fit_help must use cached VRAM, not call read_vram()"
    )


# ─── WU-2: Per-model tunings (T-WU2-07) ───────────────────────────────────────


def test_model_tunings_saved_in_apply_config():
    """_apply_config writes to self._config.model_tunings."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    import re
    m = re.search(
        r"def _apply_config.*?:.*?(?=\n    def |\nclass |\Z)",
        source,
        re.DOTALL,
    )
    assert m is not None, "_apply_config method not found"
    body = m.group(0)
    assert "model_tunings" in body, (
        "_apply_config must write to model_tunings"
    )


def test_model_tunings_restored_in_main_window():
    """main_window.py _on_use_model reads model_tunings."""
    source_path = (
        pathlib.Path(__file__).resolve().parent.parent.parent
        / "bellbird"
        / "ui"
        / "main_window.py"
    )
    source = source_path.read_text(encoding="utf-8")
    assert "model_tunings" in source, (
        "main_window.py must reference model_tunings"
    )


def test_model_tunings_no_auto_prune():
    """Neither save nor restore auto-prunes model_tunings entries."""
    source_path = (
        pathlib.Path(__file__).resolve().parent.parent.parent
        / "bellbird"
        / "ui"
        / "main_window.py"
    )
    source = source_path.read_text(encoding="utf-8")
    # Verify there's no pop() or clear() on model_tunings
    import ast
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("pop", "clear", "discard"):
                for child in ast.walk(node):
                    if isinstance(child, ast.Attribute) and child.attr == "model_tunings":
                        pytest.fail(
                            f"Auto-prune found at line {node.lineno}: {node.func.attr} on model_tunings"
                        )
    # Also check preferences_dialog.py
    pref_source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    pref_tree = ast.parse(pref_source)
    for node in ast.walk(pref_tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("pop", "clear", "discard"):
                for child in ast.walk(node):
                    if isinstance(child, ast.Attribute) and child.attr == "model_tunings":
                        pytest.fail(
                            f"Auto-prune found at line {node.lineno}: {node.func.attr} on model_tunings in preferences"
                        )


# ─── WU-2: Audio tab (v0.10.0) ──────────────────────────────────────────────────


def test_audio_tab_exists():
    """Audio tab is present in the preferences notebook."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    assert 'name="audio_page"' in source, (
        "Audio tab page must have name='audio_page'"
    )
    assert 'A&udio' in source or 'notebook.AddPage(panel, "A&udio")' in source, (
        "Audio tab must be added to the notebook with label 'A&udio'"
    )
    assert "_build_audio_page" in source, (
        "Audio tab must be built by _build_audio_page method"
    )


def test_audio_tab_controls_have_names():
    """Audio tab controls have the expected name= attributes."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    expected_names = [
        "pref_system_voice_choice",
        "pref_test_voice_button",
        "pref_select_voice_button",
        "pref_rate_slider",
        "pref_rate_label",
        "pref_auto_speak_checkbox",
        "pref_notifications_checkbox",
        "pref_sounds_checkbox",
        "pref_sound_theme_choice",
    ]
    for name in expected_names:
        assert f'name="{name}"' in source, (
            f"Audio tab is missing control with {name!r}"
        )


def test_audio_tab_controls_preceded_by_statictext():
    """Each Audio tab interactive control has a preceding wx.StaticText."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    import re
    m = re.search(
        r"def _build_audio_page\(self.*?\).*?:.*?(?=\n    def |\nclass |\Z)",
        source,
        re.DOTALL,
    )
    assert m is not None, "_build_audio_page method not found"
    body = m.group(0)
    assert "wx.StaticText" in body, (
        "_build_audio_page must create wx.StaticText labels"
    )


def test_audio_tab_has_spanish_labels():
    """Audio tab contains the expected Spanish labels (with & mnemonics)."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    expected_labels = [
        "Voz del sistema",
        "Seleccionar voz",
        "V&elocidad:",
        "Lectura automática",
        "Notificaciones:",
        "Tema de sonido:",
    ]
    for label in expected_labels:
        assert label in source, (
            f"Audio tab is missing label: {label!r}"
        )


def test_audio_tab_no_grid_sizer():
    """Audio tab (and whole file) has no GridSizer."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_sizers = {
        "wx.GridSizer",
        "wx.FlexGridSizer",
        "wx.GridBagSizer",
    }
    found_forbidden = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node)
            if func_name in forbidden_sizers:
                found_forbidden.append(f"Line {node.lineno}: {func_name}")
    assert not found_forbidden, (
        "Forbidden sizers found:\n" + "\n".join(found_forbidden)
    )


def test_audio_tab_apply_config_wired():
    """_apply_config saves the 6 new audio fields."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    import re
    m = re.search(
        r"def _apply_config.*?:.*?(?=\n    def |\nclass |\Z)",
        source,
        re.DOTALL,
    )
    assert m is not None, "_apply_config method not found"
    body = m.group(0)
    audio_fields = [
        "system_voice_name",
        "system_voice_rate",
        "auto_speak_responses",
        "notifications_enabled",
        "sounds_enabled",
        "sound_theme",
    ]
    for field in audio_fields:
        assert f"self._config.{field}" in body, (
            f"_apply_config must save {field}"
        )


def test_read_selected_message_label_exists():
    """_ACTION_LABELS has an entry for read_selected_message."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    assert '"read_selected_message": "&Leer mensaje seleccionado"' in source, (
        "_ACTION_LABELS must include 'read_selected_message' "
        "with Spanish label (with & mnemonic)"
    )


def test_audio_tab_built_after_keymap_before_status():
    """_build_audio_page is called between keymap and status pages."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    assert "_build_keymap_page(notebook)" in source
    assert "_build_audio_page(notebook)" in source
    assert "_build_status_page(notebook)" in source
    keymap_idx = source.index("_build_keymap_page(notebook)")
    audio_idx = source.index("_build_audio_page(notebook)")
    status_idx = source.index("_build_status_page(notebook)")
    assert keymap_idx < audio_idx, (
        "Audio tab must be AFTER Atajos tab"
    )
    assert audio_idx < status_idx, (
        "Audio tab must be BEFORE Estado (F2) tab"
    )


# ─── WU-2 v0.11.0: HINTS coverage (T2A) ──────────────────────────────────────


def _get_method_body(source: str, method_name: str) -> str | None:
    """Extract the body of a method by name from the source string."""
    import re
    m = re.search(
        rf"def {method_name}\(self.*?\).*?:.*?(?=\n    def |\nclass |\Z)",
        source,
        re.DOTALL,
    )
    if m:
        return m.group(0)
    return None


def test_hints_bidirectional_coverage():
    """Every name= in widget constructors has a HINTS key and vice versa.

    Parses all wx.Window constructor calls (CheckBox, Slider, SpinCtrl,
    TextCtrl, Choice, ListBox, Button, Notebook) for name= kwarg values,
    then verifies HINTS keys are a superset (no orphan hint) and subset
    (no uncovered control).
    """
    source_path = _get_ui_path("preferences_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Collect HINTS keys from the module-level dict
    hints_keys: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "HINTS":
                    if isinstance(node.value, ast.Dict):
                        for key in node.value.keys:
                            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                                hints_keys.add(key.value)

    # Collect all name= values from widget constructors
    widget_types = {
        "wx.CheckBox", "wx.Slider", "wx.SpinCtrl", "wx.TextCtrl",
        "wx.Choice", "wx.ListBox", "wx.Button", "wx.Notebook",
    }
    control_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node)
            if func_name in widget_types:
                for kw in node.keywords:
                    if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                        control_names.add(str(kw.value.value))

    # Compute f-string-generated names from DEFAULT_STATUS_TOGGLES pattern
    # Patterns in source: name=f"chk_{toggle_name}" and name=f"lbl_{toggle_name}"
    fstring_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "name" and isinstance(kw.value, ast.JoinedStr):
                    parts = kw.value.values
                    if len(parts) == 3:  # f"prefix_{var}suffix" or f"prefix_{var}"
                        p0 = parts[0]
                        p2 = parts[2] if len(parts) > 2 else None
                        if (isinstance(p0, ast.Constant) and isinstance(p0.value, str)
                                and (p2 is None or (isinstance(p2, ast.Constant) and isinstance(p2.value, str)))):
                            prefix = p0.value
                            suffix = p2.value if p2 else ""
                            # Add a sentinel pattern — we'll match dynamically
                            fstring_names.add(f"{prefix}<dynamic>{suffix}")

    # Also add the known f-string generated names from the source patterns
    # by looking for the toggle iteration source
    for toggle_name in ("model_name", "context_pct", "max_tokens", "server",
                        "vram", "fit", "message_count", "temperature",
                        "top_p", "tok_per_s", "is_generating"):
        fstring_names.add(f"chk_{toggle_name}")
        fstring_names.add(f"lbl_{toggle_name}")

    combined_control_names = control_names | fstring_names

    # Bidirectional check: every HINTS key must match a known control name
    orphan_hints = hints_keys - combined_control_names
    # Every control name must have a HINTS entry (excluding f-string patterns)
    uncovered = control_names - hints_keys

    assert not orphan_hints, (
        f"HINTS keys with no matching control name=:\n"
        + "\n".join(sorted(orphan_hints))
    )
    assert not uncovered, (
        f"Controls without HINTS entry:\n"
        + "\n".join(sorted(uncovered))
    )


# ─── WU-2 v0.11.0: & mnemonics (T2C) ──────────────────────────────────────────


def _collect_method_bodies(source: str, class_name: str = "PreferencesDialog") -> dict[str, str]:
    """Collect method sources keyed by method name for a given class."""
    import re
    tree = ast.parse(source)
    methods: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    source_lines = source.splitlines()
                    body = "\n".join(source_lines[item.lineno - 1:item.end_lineno])
                    methods[item.name] = body
    return methods


def test_ampersand_mnemonics_each_label_has_exactly_one():
    """Every StaticText and CheckBox label= literal in PreferencesDialog
    _build_*_page methods contains exactly one &."""
    import textwrap

    source_path = _get_ui_path("preferences_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Collect all _build_*_page methods (excluding _build_ui)
    build_methods: list[ast.FunctionDef] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "PreferencesDialog":
            for item in node.body:
                if (isinstance(item, ast.FunctionDef)
                        and item.name.startswith("_build_")
                        and item.name != "_build_ui"):
                    build_methods.append(item)

    errors: list[str] = []
    for method in build_methods:
        source_lines = source.splitlines()
        method_src = "\n".join(source_lines[method.lineno - 1:method.end_lineno])
        method_src = textwrap.dedent(method_src)
        inner_tree = ast.parse(method_src)
        for node in ast.walk(inner_tree):
            if isinstance(node, ast.Call):
                func_name = _get_func_name(node)
                if func_name in ("wx.StaticText", "wx.CheckBox"):
                    label_value = None
                    for kw in node.keywords:
                        if kw.arg == "label" and isinstance(kw.value, ast.Constant):
                            label_value = str(kw.value.value)
                            break
                    if label_value is not None and label_value != "":
                        count = label_value.count("&")
                        if count != 1:
                            errors.append(
                                f"Method {method.name} line {node.lineno}: "
                                f"{func_name} label={label_value!r} "
                                f"has {count} & (expected exactly 1)"
                            )
    assert not errors, "\n".join(errors)


def test_ampersand_mnemonics_unique_within_tab():
    """Within each _build_*_page method, & letters are unique (case-insensitive)."""
    import textwrap

    source_path = _get_ui_path("preferences_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    build_methods = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name.startswith("_build_")
        and node.name != "_build_ui"
    ]

    errors: list[str] = []
    for method in build_methods:
        source_lines = source.splitlines()
        method_src = "\n".join(source_lines[method.lineno - 1:method.end_lineno])
        method_src = textwrap.dedent(method_src)
        inner_tree = ast.parse(method_src)
        labels_in_method: dict[str, int] = {}  # &letter → line
        for node in ast.walk(inner_tree):
            if isinstance(node, ast.Call):
                func_name = _get_func_name(node)
                if func_name in ("wx.StaticText", "wx.CheckBox"):
                    for kw in node.keywords:
                        if kw.arg == "label" and isinstance(kw.value, ast.Constant):
                            label = str(kw.value.value)
                            if "&" in label:
                                idx = label.index("&")
                                if idx + 1 < len(label) and label[idx + 1].strip():
                                    letter = label[idx + 1].lower()
                                    if letter in labels_in_method:
                                        errors.append(
                                            f"Method {method.name}: "
                                            f"&{letter} collision between "
                                            f"line {labels_in_method[letter]} and "
                                            f"line {node.lineno} ({label!r})"
                                        )
                                    else:
                                        labels_in_method[letter] = node.lineno
                                else:
                                    errors.append(
                                        f"Method {method.name} line {node.lineno}: "
                                        f"& not followed by a letter in {label!r}"
                                    )
    assert not errors, "\n".join(errors)


def test_ampersand_ayuda_de_encaje_preserved():
    """Existing &Ayuda de encaje is preserved in _build_advanced_page."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    method = _get_method_body(source, "_build_advanced_page")
    assert method is not None, "_build_advanced_page not found"
    assert "&Ayuda de encaje" in method, (
        "&Ayuda de encaje must be preserved in _build_advanced_page"
    )


def test_estado_f2_mnemonics_preserved():
    """Estado (F2) tab & mnemonics are preserved in toggle_labels."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    method = _get_method_body(source, "_build_status_page")
    assert method is not None, "_build_status_page not found"
    expected = [
        "&Modelo", "&Porcentaje de contexto", "&Máx tokens/respuesta",
        "&Servidor", "&VRAM libre", "&Encaje", "&Mensajes",
        "&Temperatura", "&Top-p", "&Tok/s última", "&Generando",
    ]
    for label in expected:
        assert label in method, (
            f"Estado tab is missing label: {label!r}"
        )


# ─── WU-2 v0.11.0: Presets sub-panel (T2E) ────────────────────────────────────


def test_presets_sub_panel_has_listbox():
    """_build_model_page contains a wx.ListBox with name='pref_presets_list'."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    method = _get_method_body(source, "_build_model_page")
    assert method is not None, "_build_model_page not found"
    assert 'name="pref_presets_list"' in method, (
        "presets ListBox with name='pref_presets_list' must be in _build_model_page"
    )
    assert "wx.ListBox" in method, (
        "wx.ListBox must be present in _build_model_page"
    )


def test_presets_sub_panel_has_three_buttons():
    """_build_model_page has 3 preset buttons with the correct names."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    method = _get_method_body(source, "_build_model_page")
    assert method is not None, "_build_model_page not found"
    expected_names = [
        "pref_presets_apply",
        "pref_presets_save",
        "pref_presets_delete",
    ]
    for name in expected_names:
        assert f'name="{name}"' in method, (
            f"Preset button with name='{name}' not found in _build_model_page"
        )


def test_presets_sub_panel_statictext_before_controls():
    """Each preset control has a preceding wx.StaticText."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    method = _get_method_body(source, "_build_model_page")
    assert method is not None, "_build_model_page not found"
    assert "Ajustes preestablecidos" in method, (
        "StaticText 'Ajustes preestablecidos' must be in _build_model_page"
    )


def test_presets_sub_panel_below_max_tokens():
    """presets sub-panel is below pref_max_tokens_spin in _build_model_page."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    method = _get_method_body(source, "_build_model_page")
    assert method is not None, "_build_model_page not found"
    max_tokens_idx = method.find('name="pref_max_tokens_spin"')
    presets_idx = method.find('name="pref_presets_list"')
    assert max_tokens_idx >= 0, "pref_max_tokens_spin not found"
    assert presets_idx >= 0, "pref_presets_list not found"
    assert max_tokens_idx < presets_idx, (
        "pref_max_tokens_spin must appear BEFORE the presets sub-panel"
    )


# ─── WU-2 v0.11.0: Dialog size (T2K) ─────────────────────────────────────────


def test_dialog_size_is_720_600():
    """SetSize((720, 600)) must be present in PreferencesDialog.__init__."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    method_src = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "PreferencesDialog":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    source_lines = source.splitlines()
                    method_src = "\n".join(
                        source_lines[item.lineno - 1:item.end_lineno]
                    )
                    break
    assert method_src is not None, "PreferencesDialog.__init__ not found"
    assert "SetSize((720, 600))" in method_src, (
        "SetSize((720, 600)) must be called in PreferencesDialog.__init__"
    )

