"""Static/AST tests for FindDialog — accessibility compliance via source.

Tests verify: name= on all controls, BoxSizer only, no MessageDialog,
no grid sizers.
"""

import ast
import pathlib


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


def test_import_only():
    """Import-only check: module can be parsed without wx instantiation."""
    source_path = _get_ui_path("find_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    ast.parse(source)


def test_all_controls_have_name():
    """Every interactive widget has a name= parameter."""
    source_path = _get_ui_path("find_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    widget_constructors = {
        "wx.Button",
        "wx.TextCtrl",
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


def test_only_boxsizer_used():
    """No GridSizer/FlexGridSizer/GridBagSizer is used."""
    source_path = _get_ui_path("find_dialog.py")
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


def test_no_webview():
    """No wx.WebView references anywhere in the file."""
    source_path = _get_ui_path("find_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    webview_refs = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node)
            if "WebView" in func_name:
                webview_refs.append(f"Line {node.lineno}: {func_name}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if "wx.html" in alias.name or "wx.webkit" in alias.name:
                    webview_refs.append(f"Line {node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module and ("wx.html" in node.module or "wx.webkit" in node.module):
                webview_refs.append(f"Line {node.lineno}: from {node.module}")

    assert not webview_refs, (
        "WebView references found:\n" + "\n".join(webview_refs)
    )


def test_no_message_dialog():
    """No wx.MessageDialog used in find_dialog.py (per AGENTS.md ban)."""
    source_path = _get_ui_path("find_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    assert "MessageDialog" not in source, (
        "FindDialog must NOT use wx.MessageDialog"
    )


def test_find_text_has_process_enter():
    """Find text TextCtrl uses TE_PROCESS_ENTER style for Enter key."""
    source_path = _get_ui_path("find_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    assert "TE_PROCESS_ENTER" in source, (
        "find_text must use TE_PROCESS_ENTER to handle Enter key"
    )


def test_static_text_labels_present():
    """FindDialog has 'Buscar:' and 'Opciones:' StaticText labels."""
    source_path = _get_ui_path("find_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    assert "Buscar:" in source, "StaticText 'Buscar:' label not found"
    assert "Opciones:" in source, "StaticText 'Opciones:' label not found"
