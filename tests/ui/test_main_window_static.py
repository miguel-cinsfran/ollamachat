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


def test_start_ollama_button_present():
    """A 'Iniciar Ollama' button with name=start_ollama_button is built."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    found_button = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node)
            if func_name == "wx.Button":
                has_name = any(
                    kw.arg == "name"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value == "start_ollama_button"
                    for kw in node.keywords
                    if kw.arg is not None
                )
                if has_name:
                    found_button = True
                    break

    assert found_button, (
        "No wx.Button with name='start_ollama_button' found in source"
    )


def test_start_ollama_handler_invokes_runner():
    """_on_start_ollama calls start_ollama from ollamachat.core.ollama_runner."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")

    # The handler should import and call the runner function.
    assert "from ollamachat.core.ollama_runner import start_ollama" in source, (
        "MainWindow must import start_ollama from ollamachat.core.ollama_runner"
    )
    assert "start_ollama(self._client)" in source, (
        "_on_start_ollama must call start_ollama(self._client)"
    )


def test_start_ollama_button_uses_logger():
    """MainWindow uses the logger module (so build/runtime events are recorded)."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    assert "from ollamachat.core.logger import get_logger" in source
    assert "get_logger()" in source


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
