"""Static/AST tests for PreferencesDialog — accessibility compliance via source.

Tests verify: 5 tab labels present, no GridSizer, SetEscapeId set,
OK handler calls _apply_config before EndModal, every widget has name=.
"""

import ast
import pathlib
import re


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
    """All five tab labels exist in the source."""
    source_path = _get_ui_path("preferences_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    for label in ("General", "Modelo", "Chat", "Herramientas", "Avanzado"):
        assert label in source, f"Tab label {label!r} not found in source"


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
    """SetEscapeId(wx.ID_CANCEL) is called in the dialog source."""
    source_path = _get_ui_path("preferences_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    assert "SetEscapeId" in source, (
        "SetEscapeId not found in preferences_dialog.py"
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
