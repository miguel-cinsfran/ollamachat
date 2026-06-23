"""Static/AST tests for PermissionDialog — accessibility compliance via source inspection.

Tests verify: name= on command_text and 3 buttons, all widgets have name=,
only BoxSizer, zero MessageDialog tokens, risk_labels are pure ASCII.
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


def test_command_text_present():
    """A wx.TextCtrl with name='command_text' exists."""
    source_path = _get_ui_path("permission_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node)
            if func_name == "wx.TextCtrl":
                has_name = any(
                    kw.arg == "name"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value == "command_text"
                    for kw in node.keywords
                    if kw.arg is not None
                )
                if has_name:
                    found = True
                    break

    assert found, "No wx.TextCtrl with name='command_text' found"


def test_allow_once_button_present():
    """A wx.Button with name='allow_once_button' exists."""
    source_path = _get_ui_path("permission_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node)
            if func_name == "wx.Button":
                has_name = any(
                    kw.arg == "name"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value == "allow_once_button"
                    for kw in node.keywords
                    if kw.arg is not None
                )
                if has_name:
                    found = True
                    break

    assert found, "No wx.Button with name='allow_once_button' found"


def test_allow_session_button_present():
    """A wx.Button with name='allow_session_button' exists."""
    source_path = _get_ui_path("permission_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node)
            if func_name == "wx.Button":
                has_name = any(
                    kw.arg == "name"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value == "allow_session_button"
                    for kw in node.keywords
                    if kw.arg is not None
                )
                if has_name:
                    found = True
                    break

    assert found, "No wx.Button with name='allow_session_button' found"


def test_deny_button_present():
    """A wx.Button with name='deny_button' exists."""
    source_path = _get_ui_path("permission_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node)
            if func_name == "wx.Button":
                has_name = any(
                    kw.arg == "name"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value == "deny_button"
                    for kw in node.keywords
                    if kw.arg is not None
                )
                if has_name:
                    found = True
                    break

    assert found, "No wx.Button with name='deny_button' found"


def test_all_controls_have_name():
    """Every interactive widget has a name= parameter."""
    source_path = _get_ui_path("permission_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    widget_constructors = {
        "wx.Button",
        "wx.Slider",
        "wx.TextCtrl",
        "wx.SpinCtrl",
        "wx.Choice",
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
    source_path = _get_ui_path("permission_dialog.py")
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


def test_no_message_dialog():
    """No MessageDialog tokens anywhere in the file."""
    source_path = _get_ui_path("permission_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    assert "MessageDialog" not in source, (
        "MessageDialog is forbidden in permission_dialog.py — use wx.Dialog + wx.Button"
    )


def test_no_emoji_in_risk_labels():
    """risk_labels dict values in _build_ui are pure ASCII."""
    source_path = _get_ui_path("permission_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    risk_values: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_build_ui":
            for child in ast.walk(node):
                if isinstance(child, ast.Assign):
                    for target in child.targets:
                        if isinstance(target, ast.Name) and target.id == "risk_labels":
                            if isinstance(child.value, ast.Dict):
                                for val in child.value.values:
                                    if isinstance(val, ast.Constant) and isinstance(val.value, str):
                                        risk_values.append(val.value)

    assert len(risk_values) == 3, (
        f"Expected 3 risk_labels values, got {len(risk_values)}"
    )
    for v in risk_values:
        assert v.isascii(), f"risk_label value contains non-ASCII: {v!r}"


def test_all_statictext_labels_are_ascii():
    """All wx.StaticText label= arguments in permission_dialog.py are pure ASCII.

    NVDA reads non-ASCII characters (including emojis) letter-by-letter or by
    their Unicode description. Any non-ASCII character in a StaticText would
    produce unexpected announcements for blind users.
    """
    source_path = _get_ui_path("permission_dialog.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    non_ascii: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func_name = _get_func_name(node)
        if func_name not in ("wx.StaticText", "StaticText"):
            continue
        for kw in node.keywords:
            if kw.arg == "label" and isinstance(kw.value, ast.Constant):
                label = kw.value.value
                if isinstance(label, str) and not label.isascii():
                    non_ascii.append(label)

    assert non_ascii == [], (
        f"Non-ASCII StaticText labels found in permission_dialog.py: {non_ascii}"
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
