"""Static/AST tests for the Lectura tab in PreferencesDialog — v0.11.0.

Tests verify: tab label "&Lectura" between Chat and Herramientas,
4 CheckBox controls with correct name= attributes, each with & in label.
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


def _get_method_body(source: str, method_name: str) -> str | None:
    """Extract the body of a method by name from the source string."""
    m = re.search(
        rf"def {method_name}\(self.*?\).*?:.*?(?=\n    def |\nclass |\Z)",
        source,
        re.DOTALL,
    )
    if m:
        return m.group(0)
    return None


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


def test_lectura_tab_present():
    """Dialog has a page labeled "&Lectura"."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    assert '"&Lectura"' in source or "'&Lectura'" in source, (
        'Tab label "&Lectura" not found in preferences_dialog.py'
    )


def test_lectura_tab_between_chat_and_herramientas():
    """Lectura tab is between Chat and Herramientas in _build_ui."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    # Find the _build_ui method
    m = re.search(
        r"def _build_ui\(self.*?\).*?:.*?(?=\n    def |\nclass |\Z)",
        source,
        re.DOTALL,
    )
    assert m is not None, "_build_ui method not found"
    body = m.group(0)

    assert "_build_chat_page(notebook)" in body
    assert "_build_lectura_page(notebook)" in body
    assert "_build_tools_page(notebook)" in body
    chat_idx = body.index("_build_chat_page(notebook)")
    lectura_idx = body.index("_build_lectura_page(notebook)")
    tools_idx = body.index("_build_tools_page(notebook)")
    assert chat_idx < lectura_idx, (
        "Lectura tab must be AFTER Chat tab"
    )
    assert lectura_idx < tools_idx, (
        "Lectura tab must be BEFORE Herramientas tab"
    )


def test_lectura_tab_has_build_method():
    """_build_lectura_page method exists."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    method = _get_method_body(source, "_build_lectura_page")
    assert method is not None, "_build_lectura_page method not found"


def test_lectura_tab_has_four_filter_checkboxes():
    """Lectura tab has 4 CheckBox with correct name= attributes."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    method = _get_method_body(source, "_build_lectura_page")
    assert method is not None, "_build_lectura_page method not found"

    expected_names = [
        "pref_filter_markdown",
        "pref_filter_urls",
        "pref_filter_emojis",
        "pref_filter_code_blocks",
    ]
    for name in expected_names:
        assert f'name="{name}"' in method, (
            f"CheckBox with name='{name}' not found in _build_lectura_page"
        )


def test_lectura_tab_checkboxes_have_ampersand():
    """Each filter CheckBox label contains a & character."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    method = _get_method_body(source, "_build_lectura_page")
    assert method is not None, "_build_lectura_page method not found"

    tree = ast.parse(method)
    checkbox_labels = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node)
            if func_name == "wx.CheckBox":
                for kw in node.keywords:
                    if kw.arg == "label" and isinstance(kw.value, ast.Constant):
                        checkbox_labels.append(str(kw.value.value))

    assert len(checkbox_labels) == 4, (
        f"Expected 4 CheckBox labels in _build_lectura_page, got {len(checkbox_labels)}"
    )
    for label in checkbox_labels:
        assert "&" in label, (
            f"CheckBox label {label!r} must contain a & mnemonic"
        )
        count = label.count("&")
        assert count == 1, (
            f"CheckBox label {label!r} must contain exactly one &, got {count}"
        )


def test_lectura_tab_statictext_header():
    """Lectura tab has StaticText header with &."""
    source = _get_ui_path("preferences_dialog.py").read_text(encoding="utf-8")
    method = _get_method_body(source, "_build_lectura_page")
    assert method is not None, "_build_lectura_page method not found"
    assert "StaticText" in method, (
        "_build_lectura_page must contain StaticText"
    )
    # Verify some Spanish text about filters
    assert "Filtros" in method or "lectura" in method.lower(), (
        "_build_lectura_page must contain Spanish text about reading filters"
    )
