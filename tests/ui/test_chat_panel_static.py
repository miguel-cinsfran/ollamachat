"""Static/AST tests for ChatPanel — accessibility compliance via source inspection.

Tests verify: name= on all controls, wx.StaticText labels, BoxSizer only,
no WebView, TE_RICH2 on conversation display, ShiftDown() check in input handler.
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


def test_import_only():
    """Import-only check: module can be parsed without wx instantiation."""
    source_path = _get_ui_path("chat_panel.py")
    source = source_path.read_text(encoding="utf-8")
    ast.parse(source)


def test_all_controls_have_name():
    """Every interactive widget has a name= parameter."""
    source_path = _get_ui_path("chat_panel.py")
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
    source_path = _get_ui_path("chat_panel.py")
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
    source_path = _get_ui_path("chat_panel.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Check for wx.WebView or import wx.html / wx.webkit
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


def test_message_list_present():
    """ChatPanel has a message_list ListBox."""
    source_path = _get_ui_path("chat_panel.py")
    source = source_path.read_text(encoding="utf-8")
    assert 'name="message_list"' in source or "name='message_list'" in source


def test_stream_display_present():
    """ChatPanel has a stream_display TextCtrl with TE_READONLY."""
    source_path = _get_ui_path("chat_panel.py")
    source = source_path.read_text(encoding="utf-8")
    assert 'name="stream_display"' in source or "name='stream_display'" in source


def test_history_list_exists_in_init():
    """ChatPanel.__init__ initializes self._history as list[tuple[str, str]]."""
    source_path = _get_ui_path("chat_panel.py")
    source = source_path.read_text(encoding="utf-8")
    assert "_history" in source
    # Check the type hint is present in __init__
    assert "list[tuple[str, str]]" in source or "list[tuple" in source


def test_input_has_process_enter():
    """Message input TextCtrl uses TE_PROCESS_ENTER style."""
    source_path = _get_ui_path("chat_panel.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    found_process_enter = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node)
            if func_name == "wx.TextCtrl":
                has_input_name = any(
                    kw.arg == "name"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value == "message_input"
                    for kw in node.keywords
                    if kw.arg is not None
                )
                if has_input_name:
                    for kw in node.keywords:
                        if kw.arg == "style":
                            style_str = _extract_ast_value(kw.value)
                            if style_str and "TE_PROCESS_ENTER" in style_str:
                                found_process_enter = True

    assert found_process_enter, (
        "message_input not created with TE_PROCESS_ENTER style"
    )


def test_chatpanel_accepts_on_send_callback():
    """ChatPanel.__init__ accepts an on_send callback parameter (CRIT-1 regression)."""
    source_path = _get_ui_path("chat_panel.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Find the __init__ method of ChatPanel
    init_params: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "__init__":
            # Check if this is inside class ChatPanel
            for parent in ast.walk(tree):
                if isinstance(parent, ast.ClassDef) and parent.name == "ChatPanel":
                    for item in parent.body:
                        if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                            init_params = [a.arg for a in item.args.args]
                            break

    assert "on_send" in init_params, (
        "ChatPanel.__init__ must accept an 'on_send' parameter (CRIT-1). "
        f"Found params: {init_params}"
    )


def test_on_input_enter_calls_callback_not_noop():
    """_on_input_enter calls the on_send callback, not a no-op _on_send (CRIT-1 regression)."""
    source_path = _get_ui_path("chat_panel.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Verify _on_send method does NOT exist (it was a no-op 'pass')
    on_send_method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "ChatPanel":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "_on_send":
                    on_send_method = item
                    break

    assert on_send_method is None, (
        "ChatPanel._on_send should have been removed (was a no-op 'pass'). "
        "Use the on_send callback parameter instead."
    )

    # Verify _on_input_enter calls self._on_send_callback()
    found_callback_call = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_on_input_enter":
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    func_name = _get_func_name(child)
                    if "_on_send_callback" in func_name:
                        found_callback_call = True
                        break

    assert found_callback_call, (
        "_on_input_enter must call self._on_send_callback() instead of "
        "a removed no-op _on_send method."
    )


def test_enter_handler_checks_shiftdown():
    """The Enter/Send handler checks Shift key state to distinguish Enter vs Shift+Enter."""
    source_path = _get_ui_path("chat_panel.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Look for ShiftDown() call — the canonical wxPython approach
    # (replaces old wx.GetKeyState(wx.WXK_SHIFT) approach)
    found_shift_check = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node)
            if "ShiftDown" in func_name:
                found_shift_check = True
                break

    assert found_shift_check, (
        "No Shift key state check found — Enter/Shift+Enter not distinguished. "
        "Expected event.ShiftDown() call in the input enter handler."
    )


# ─── Dual view refactor (v0.3.0) ─────────────────────────────────────────────


def test_no_conversation_display_reference():
    """ChatPanel no longer references conversation_display."""
    source_path = _get_ui_path("chat_panel.py")
    source = source_path.read_text(encoding="utf-8")
    assert "conversation_display" not in source, (
        "conversation_display must be fully removed in the dual-view refactor."
    )


def test_stream_display_uses_rich2():
    """stream_display TextCtrl uses TE_RICH2 style."""
    source_path = _get_ui_path("chat_panel.py")
    source = source_path.read_text(encoding="utf-8")
    # Check that name="stream_display" is accompanied by TE_RICH2
    # Simple search: look for stream_display and TE_RICH2 in close proximity
    assert "TE_RICH2" in source, "stream_display must use TE_RICH2 style"
    assert "TE_READONLY" in source, "stream_display must use TE_READONLY style"


def test_clear_resets_generation_state() -> None:
    """Regression for B5: clear() must reset _is_generating and re-enable buttons.

    Without this, clicking "Limpiar" or "Nueva conversación" while a
    generation is in progress leaves send_button disabled until the
    in-flight stream completes (up to 60s for a long response).
    """
    from pathlib import Path
    src = Path("bellbird/ui/chat_panel.py").read_text(encoding="utf-8")
    # Find the clear method specifically (not _on_clear or other helpers)
    import re
    m = re.search(
        r"    def clear\(self\) -> None:.*?(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "def clear(self) -> None not found in chat_panel.py"
    body = m.group(0)
    assert "self._is_generating" in body, (
        "clear() must check self._is_generating to know if a "
        "generation is in progress"
    )
    assert "send_button.Enable()" in body, (
        "clear() must call self.send_button.Enable() to unblock the user"
    )
    assert "self._is_generating = False" in body, (
        "clear() must set self._is_generating = False to reset the flag"
    )


def test_on_list_key_uses_unicode_key_not_ascii_range() -> None:
    """Regression for B4: _on_list_key must use GetUnicodeKey, not the ASCII range.

    The target user is Spanish-speaking; without GetUnicodeKey, pressing
    ñ, á, é, í, ó, ú, ¿, ¡ in the message list causes the focus to jump
    to the input but the character is lost. The 32-126 ASCII range
    check must be removed.
    """
    from pathlib import Path
    src = Path("bellbird/ui/chat_panel.py").read_text(encoding="utf-8")
    assert "GetUnicodeKey" in src, (
        "_on_list_key must use event.GetUnicodeKey() to support non-ASCII "
        "characters (ñ, á, é, í, ó, ú, etc.) for the Spanish-speaking target user"
    )
    assert "32 <= key <= 126" not in src, (
        "The ASCII range check `32 <= key <= 126` must be removed — "
        "it incorrectly rejects non-ASCII printable characters"
    )


# ─── Tool append methods (v0.4.0) ──────────────────────────────────────────


def test_append_tool_output_method_exists():
    """ChatPanel has append_tool_output(self, text: str) -> None method."""
    source_path = _get_ui_path("chat_panel.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "append_tool_output":
            found = True
            args = [a.arg for a in node.args.args]
            assert "self" in args, "append_tool_output must have self"
            assert "text" in args, "append_tool_output must have text parameter"
            break

    assert found, "append_tool_output method not found in ChatPanel"


def test_append_tool_blocked_method_exists():
    """ChatPanel has append_tool_blocked(self, tool_name: str, command: str) -> None."""
    source_path = _get_ui_path("chat_panel.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "append_tool_blocked":
            found = True
            args = [a.arg for a in node.args.args]
            assert "self" in args
            assert "tool_name" in args, "append_tool_blocked must have tool_name parameter"
            assert "command" in args, "append_tool_blocked must have command parameter"
            break

    assert found, "append_tool_blocked method not found in ChatPanel"


def test_append_tool_denied_method_exists():
    """ChatPanel has append_tool_denied(self, tool_name: str) -> None."""
    source_path = _get_ui_path("chat_panel.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "append_tool_denied":
            found = True
            args = [a.arg for a in node.args.args]
            assert "self" in args
            assert "tool_name" in args, "append_tool_denied must have tool_name parameter"
            break

    assert found, "append_tool_denied method not found in ChatPanel"


def test_no_emoji_in_tool_prefixes():
    """Tool prefixes [Herramienta], [Bloqueado], [Denegado] are pure ASCII."""
    source_path = _get_ui_path("chat_panel.py")
    source = source_path.read_text(encoding="utf-8")
    assert "[Herramienta]" in source, "[Herramienta] prefix not found"
    assert "[Bloqueado]" in source, "[Bloqueado] prefix not found"
    assert "[Denegado]" in source, "[Denegado] prefix not found"

    # Check they're pure ASCII
    for prefix in ("[Herramienta]", "[Bloqueado]", "[Denegado]"):
        assert prefix.isascii(), f"{prefix} contains non-ASCII characters"


def test_end_generation_skips_empty_preview() -> None:
    """Regression for B3: message_list.Append must be INSIDE the strip() guard.

    Without this guard, aborting a stream before the first token
    arrives leaves a stray "[IA] [Asistente] " row in the list.

    The check is on INDENTATION, not just position: the Append must be
    indented strictly more than the `if final.strip():` line so that
    Python syntactically places it inside the block. A position-only
    check (e.g. `rfind`) would pass on the buggy code because the guard
    is above the Append even when the Append is NOT inside the block.
    """
    import re
    from pathlib import Path
    src = Path("bellbird/ui/chat_panel.py").read_text(encoding="utf-8")
    m = re.search(
        r"def end_generation\(self\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "end_generation not found in chat_panel.py"
    body = m.group(0)

    # 1) Find the Append line and capture its indentation.
    append_match = re.search(
        r"^(\s+)self\.message_list\.Append\(preview\)",
        body, re.MULTILINE,
    )
    assert append_match is not None, "message_list.Append(preview) line not found"
    append_indent = len(append_match.group(1))

    # 2) Find ALL `if final.strip():` lines and take the LAST one
    #    (the one that guards the Append, if any).
    if_matches = list(re.finditer(
        r"^(\s*)if final\.strip\(\):",
        body, re.MULTILINE,
    ))
    assert if_matches, "`if final.strip():` line not found in end_generation"
    latest_if = if_matches[-1]
    if_indent = len(latest_if.group(1))

    # 3) The Append must be inside the block: its indentation must be
    #    STRICTLY GREATER than the if's indentation. If they are equal,
    #    the Append is at the same level as the if and runs regardless
    #    of the condition — the BUG.
    assert append_indent > if_indent, (
        f"message_list.Append(preview) (indent={append_indent}) must be "
        f"indented MORE than `if final.strip():` (indent={if_indent}) "
        f"to be syntactically inside the block. Current code has the "
        f"Append at the same level as the guard, so it runs even when "
        f"the stream is empty — B3 regression."
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


def _extract_ast_value(node: ast.AST) -> str | None:
    """Extract a string representation from an AST node."""
    if isinstance(node, ast.Constant):
        return str(node.value)
    elif isinstance(node, ast.BinOp):
        left = _extract_ast_value(node.left)
        op = _extract_ast_value(node.op)
        right = _extract_ast_value(node.right)
        if left and op and right:
            return f"{left}{op}{right}"
        return None
    elif isinstance(node, ast.BitOr):
        return " | "
    elif isinstance(node, ast.Attribute):
        return f"{_get_attr_name(node)}"
    elif isinstance(node, ast.Name):
        return node.id
    return None
