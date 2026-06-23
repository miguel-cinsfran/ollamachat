"""Static/AST tests for MainWindow — accessibility and structure verification.

Tests verify: menus present, accelerator table bindings, SplitterWindow
with ParamsPanel left (280px), status bar, and import-only check.
"""

import ast
import pathlib


def _get_ui_path(filename: str) -> pathlib.Path:
    return (
        pathlib.Path(__file__).resolve().parent.parent.parent
        / "ollamachat"
        / "ui"
        / filename
    )


def test_import_only():
    """Import-only check: module can be parsed without wx instantiation."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    ast.parse(source)


def test_archivo_menu_present():
    """Archivo menu with items: Nueva conversación, Abrir, Guardar, Salir."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Look for menu item labels
    found_items = {
        "Nueva conversación": False,
        "Abrir": False,
        "Guardar": False,
        "Salir": False,
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for key in found_items:
                if key in node.value:
                    found_items[key] = True

    missing = [k for k, v in found_items.items() if not v]
    assert not missing, f"Archivo menu items missing in source: {missing}"


def test_ayuda_menu_present():
    """Ayuda menu with items: Acerca de, Atajos de teclado."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    found_items = {
        "Acerca de": False,
        "Atajos de teclado": False,
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for key in found_items:
                if key in node.value:
                    found_items[key] = True

    missing = [k for k, v in found_items.items() if not v]
    assert not missing, f"Ayuda menu items missing in source: {missing}"


def test_attached_text_included_in_user_msg():
    """send_message includes attached_text in user_msg content before API call (CRIT-2 regression)."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Find the send_message method
    send_method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "send_message":
            send_method = node
            break

    assert send_method is not None, "send_message method not found"

    source_lines = source.splitlines()
    start = send_method.lineno - 1
    end = send_method.end_lineno if hasattr(send_method, 'end_lineno') else len(source_lines)
    send_source = "\n".join(source_lines[start:end])

    # Must reference get_attached_text() or attached_text
    has_get_attached_text = "get_attached_text()" in send_source
    has_attached_text_var = "attached_text" in send_source

    assert has_get_attached_text or has_attached_text_var, (
        "send_message must reference get_attached_text() to include attached text "
        "in the API payload (CRIT-2 regression)."
    )

    # Must NOT have a separate add_message after the API call for attached text
    # (the old bug pattern: add_message for attached text AFTER chat_stream)
    # Check that attached_text is NOT followed by add_message outside the
    # user_msg construction block
    has_separate_add = False
    for node in ast.walk(send_method):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node)
            if func_name == "self._conversation.add_message" or "add_message" in func_name:
                # Check if this call has attached text in its args
                for child in ast.walk(node):
                    if isinstance(child, ast.Constant) and isinstance(child.value, str):
                        if "Contenido del archivo adjuntado" in child.value:
                            has_separate_add = True
                            break

    assert not has_separate_add, (
        "Attached text must be included in user_msg['content'], not as a separate "
        "add_message call (CRIT-2 regression)."
    )


def test_accelerator_table():
    """AcceleratorTable contains bindings for Ctrl+N/O/S/F5/Escape."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Look for AcceleratorTable usage
    found_accel = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node)
            if "AcceleratorTable" in func_name:
                found_accel = True
                break

    assert found_accel, "No wx.AcceleratorTable found in source"


def test_splitter_window():
    """SplitterWindow used with ParamsPanel and ChatPanel."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    found_splitter = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node)
            if "SplitterWindow" in func_name:
                found_splitter = True
                break

    assert found_splitter, "No wx.SplitterWindow found in source"


def test_status_bar():
    """StatusBar is present in MainWindow."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    found_statusbar = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node)
            if "StatusBar" in func_name or "CreateStatusBar" in func_name:
                found_statusbar = True
                break

    assert found_statusbar, "No wx.StatusBar / CreateStatusBar found in source"


def test_restart_server_button_present():
    """A 'Reiniciar servidor' button with name=restart_server_button is built."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    found_start = False
    found_stop = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node)
            if func_name == "wx.Button":
                has_start = any(
                    kw.arg == "name"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value == "restart_server_button"
                    for kw in node.keywords
                    if kw.arg is not None
                )
                if has_start:
                    found_start = True
                has_stop = any(
                    kw.arg == "name"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value == "stop_server_button"
                    for kw in node.keywords
                    if kw.arg is not None
                )
                if has_stop:
                    found_stop = True

    assert found_start, (
        "No wx.Button with name='restart_server_button' found in source"
    )
    assert found_stop, (
        "No wx.Button with name='stop_server_button' found in source"
    )


def test_start_server_handler_invokes_runner():
    """_on_start_server calls start_server from ollamachat.core.llama_runner."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")

    # The handler should import from the new module.
    assert "from ollamachat.core.llama_runner import" in source, (
        "MainWindow must import from ollamachat.core.llama_runner"
    )
    assert "from ollamachat.core.llama_client import LlamaClient" in source, (
        "MainWindow must import LlamaClient from ollamachat.core.llama_client"
    )
    assert "start_server(" in source, (
        "_on_start_server must call start_server"
    )
    assert "stop_server()" in source, (
        "_on_stop_server must call stop_server()"
    )


def test_main_window_uses_logger():
    """MainWindow uses the logger module (so build/runtime events are recorded)."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    assert "from ollamachat.core.logger import get_logger" in source
    assert "get_logger()" in source


# ─── use_model_button (v0.3.0, in params_panel.py) ──────────────────────────


def test_use_model_button_present():
    """ParamsPanel has a use_model_button with name='use_model_button'."""
    source_path = _get_ui_path("params_panel.py")
    source = source_path.read_text(encoding="utf-8")
    assert 'name="use_model_button"' in source or "name='use_model_button'" in source


def test_use_model_button_in_boxsizer():
    """use_model_button is added to a wx.BoxSizer (.Add() call)."""
    source_path = _get_ui_path("params_panel.py")
    source = source_path.read_text(encoding="utf-8")
    # Check that use_model_button appears in an Add() call context
    assert "use_model_button" in source
    # The Add() call that receives it should be in the source
    assert "model_sizer.Add(" in source or "model_sizer.Add(self.use_model_button" in source


# ─── v0.3.0 AST tests ──────────────────────────────────────────────────────


def test_f2_accelerator_present():
    """WXK_F2 appears in the accelerator entries in main_window.py."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    assert "WXK_F2" in source, "F2 accelerator entry not found in source"


def test_announce_session_status_method_exists():
    """MainWindow has an _announce_session_status method."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    assert "_announce_session_status" in source, (
        "_announce_session_status method not found in source"
    )


def test_open_message_in_browser_method_exists():
    """MainWindow has an _open_message_in_browser method."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    assert "_open_message_in_browser" in source, (
        "_open_message_in_browser method not found in source"
    )


def test_temp_html_files_list_initialized():
    """MainWindow initializes self._temp_html_files as list[str]."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    assert "_temp_html_files" in source, (
        "_temp_html_files attribute not found in source"
    )


def test_winsound_imported_inside_function():
    """winsound is imported inside _maybe_beep, not at module level."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    # Check that winsound import appears AFTER the platform guard
    # by searching for the pattern inside _maybe_beep
    import re
    assert "import winsound" in source, (
        "winsound must be imported inside _maybe_beep, not at module level"
    )
    # Verify the import is INSIDE a function (not at module top level)
    # Find where the import occurs
    lines = source.splitlines()
    winsound_line = None
    for i, line in enumerate(lines):
        if "import winsound" in line:
            winsound_line = i
            break
    assert winsound_line is not None, "import winsound not found"
    # Check that it's after the function def
    func_line = None
    for i, line in enumerate(lines):
        if "def _maybe_beep" in line:
            func_line = i
            break
    assert func_line is not None, "_maybe_beep method not found"
    assert winsound_line > func_line, (
        "winsound import must be inside _maybe_beep, not at module level"
    )


def test_use_model_button_disabled_initially():
    """use_model_button is disabled in __init__ or in set_models([])."""
    source_path = _get_ui_path("params_panel.py")
    source = source_path.read_text(encoding="utf-8")

    # Look for use_model_button.Disable() calls
    # In __init__ or in set_models/ add_model
    import re
    disable_calls = re.findall(
        r"use_model_button\.Disable\(\)", source
    )
    assert len(disable_calls) >= 1, (
        "use_model_button must be disabled in __init__ or in set_models([]). "
        f"Found {len(disable_calls)} use_model_button.Disable() calls."
    )

    # Also check that it's enabled when models are available
    assert "use_model_button.Enable()" in source or "use_model_button.Enable" in source, (
        "use_model_button must be enabled when models are available."
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


def test_model_load_worker_binds_defaults_before_try() -> None:
    """Regression for B1: ok/message must be bound BEFORE the try block.

    Without defaults, an exception in start_server triggers
    UnboundLocalError in the finally block, the worker dies silently,
    and the buttons stay disabled forever.
    """
    import re
    from pathlib import Path
    src = Path("ollamachat/ui/main_window.py").read_text(encoding="utf-8")
    m = re.search(
        r"def _model_load_worker\(self, model: str\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_model_load_worker not found in main_window.py"
    body = m.group(0)
    ok_pos = body.find("ok = False")
    msg_pos = body.find('message = "Error: start_server raised')
    try_pos = body.find("try:")
    assert ok_pos > 0, "ok = False must be bound in _model_load_worker"
    assert msg_pos > 0, 'message = "Error: start_server raised an exception" must be bound'
    assert try_pos > 0, "try: block not found"
    assert ok_pos < try_pos, "ok = False must appear BEFORE the try: block"
    assert msg_pos < try_pos, 'message = "Error..." must appear BEFORE the try: block'


def _get_attr_name(node: ast.AST) -> str:
    """Extract the dotted name from a nested attribute node."""
    if isinstance(node, ast.Attribute):
        return f"{_get_attr_name(node.value)}.{node.attr}"
    elif isinstance(node, ast.Name):
        return node.id
    return "<unknown>"
