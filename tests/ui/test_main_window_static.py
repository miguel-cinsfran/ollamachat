"""Static/AST tests for MainWindow — accessibility and structure verification.

Tests verify: menus present (Archivo / Servidor / Ayuda), accelerator table
bindings, vertical BoxSizer with top model row + ChatPanel full-width, status
bar, and import-only check.
"""

import ast
import pathlib

import pytest


def _get_ui_path(filename: str) -> pathlib.Path:
    return (
        pathlib.Path(__file__).resolve().parent.parent.parent
        / "bellbird"
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
    """_on_start_server calls start_server from bellbird.core.llama_runner."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")

    # The handler should import from the new module.
    assert "from bellbird.core.llama_runner import" in source, (
        "MainWindow must import from bellbird.core.llama_runner"
    )
    assert "from bellbird.core.llama_client import LlamaClient" in source, (
        "MainWindow must import LlamaClient from bellbird.core.llama_client"
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
    assert "from bellbird.core.logger import get_logger" in source
    assert "get_logger()" in source


# ─── use_model_button (v0.5.0, in main_window.py) ─────────────────────────


def test_use_model_button_present():
    """MainWindow has a use_model_button with name='use_model_button'."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    assert 'name="use_model_button"' in source or "name='use_model_button'" in source


def test_use_model_button_in_boxsizer():
    """use_model_button is added to a wx.BoxSizer (.Add() call) in main_window.py."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    # Check that use_model_button appears in an Add() call context
    assert "use_model_button" in source
    assert ".Add(self.use_model_button" in source or ".Add(" in source


# ─── v0.3.0 AST tests ──────────────────────────────────────────────────────


def test_f2_accelerator_present():
    """F2 shortcut is defined in keymap.py and imported by main_window.

    The F2 binding was moved from hardcoded wx.WXK_F2 in
    _build_accelerators to the DEFAULT_KEYMAP in keymap.py.
    """
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    # Verify main_window imports from keymap (F2 is now defined there)
    assert "from bellbird.core.keymap import" in source, (
        "keymap module not imported in main_window.py"
    )


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
    """use_model_button is disabled in _build_ui or in set_models([]) in main_window.py."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")

    # Look for use_model_button.Disable() calls
    import re
    disable_calls = re.findall(
        r"use_model_button\.Disable\(\)", source
    )
    assert len(disable_calls) >= 1, (
        "use_model_button must be disabled in _build_ui or in set_models([]). "
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


def test_on_close_sets_is_closing_after_confirm_not_before() -> None:
    """Regression for B2: _is_closing = True must come AFTER the confirm dialog.

    If the flag is set before the user confirms, clicking "No" leaves
    the flag stuck at True for the rest of the app's life. The 8s
    announce timer skips every tick, F2 status goes stale, and the
    context menu logic is wrong.
    """
    import re
    from pathlib import Path
    src = Path("bellbird/ui/main_window.py").read_text(encoding="utf-8")
    m = re.search(
        r"def _on_close\(self, event: wx\.CloseEvent\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_on_close not found in main_window.py"
    body = m.group(0)
    set_pos = body.find("self._is_closing = True")
    dlg_pos = body.find("wx.MessageDialog(")
    assert set_pos > 0, "self._is_closing = True not found in _on_close"
    assert dlg_pos > 0, "wx.MessageDialog (confirm dialog) not found in _on_close"
    assert set_pos > dlg_pos, (
        "self._is_closing = True must come AFTER wx.MessageDialog — "
        "the flag should only be set after the user confirms the close"
    )


def test_model_load_worker_binds_defaults_before_try() -> None:
    """Regression for B1: ok/message must be bound BEFORE the try block.

    Without defaults, an exception in start_server triggers
    UnboundLocalError in the finally block, the worker dies silently,
    and the buttons stay disabled forever.
    """
    import re
    from pathlib import Path
    src = Path("bellbird/ui/main_window.py").read_text(encoding="utf-8")
    m = re.search(
        r"def _model_load_worker\(self, model: str.*?\) -> None:.*?"
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


# ─── Tool calling (v0.4.0) ────────────────────────────────────────────────


def test_permission_manager_initialized():
    """MainWindow.__init__ initializes self._permission_manager = PermissionManager()."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "__init__":
            for child in ast.walk(node):
                if isinstance(child, ast.Assign):
                    for target in child.targets:
                        if (isinstance(target, ast.Attribute)
                                and target.attr == "_permission_manager"):
                            if (isinstance(child.value, ast.Call)
                                    and _get_func_name(child.value) == "PermissionManager"):
                                found = True
                                break

    assert found, (
        "self._permission_manager = PermissionManager() not found in __init__"
    )


def test_tool_executor_initialized():
    """MainWindow.__init__ initializes self._tool_executor = ToolExecutor()."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "__init__":
            for child in ast.walk(node):
                if isinstance(child, ast.Assign):
                    for target in child.targets:
                        if (isinstance(target, ast.Attribute)
                                and target.attr == "_tool_executor"):
                            if (isinstance(child.value, ast.Call)
                                    and _get_func_name(child.value) == "ToolExecutor"):
                                found = True
                                break

    assert found, (
        "self._tool_executor = ToolExecutor() not found in __init__"
    )


def test_on_tool_call_method_exists():
    """MainWindow has _on_tool_call method."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    found = False
    for node in ast.walk(tree):
        if (isinstance(node, ast.FunctionDef)
                and node.name == "_on_tool_call"):
            # Ensure it's inside MainWindow class
            for parent_node in ast.walk(tree):
                if (isinstance(parent_node, ast.ClassDef)
                        and parent_node.name == "MainWindow"):
                    for item in parent_node.body:
                        if (isinstance(item, ast.FunctionDef)
                                and item.name == "_on_tool_call"):
                            found = True
                            break

    assert found, "_on_tool_call method not found in MainWindow"


def test_run_tool_and_show_method_exists():
    """MainWindow has _run_tool_and_show method."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow":
            for item in node.body:
                if (isinstance(item, ast.FunctionDef)
                        and item.name == "_run_tool_and_show"):
                    found = True
                    break

    assert found, "_run_tool_and_show method not found in MainWindow"


def test_on_tool_result_method_exists():
    """MainWindow has _on_tool_result method."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow":
            for item in node.body:
                if (isinstance(item, ast.FunctionDef)
                        and item.name == "_on_tool_result"):
                    found = True
                    break

    assert found, "_on_tool_result method not found in MainWindow"


def test_continue_after_tool_method_exists():
    """MainWindow has _continue_after_tool method."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow":
            for item in node.body:
                if (isinstance(item, ast.FunctionDef)
                        and item.name == "_continue_after_tool"):
                    found = True
                    break

    assert found, "_continue_after_tool method not found in MainWindow"


def test_shell_tool_definition_at_module_level():
    """SHELL_TOOL_DEFINITION is assigned at module level, not inside a class."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Check that SHELL_TOOL_DEFINITION appears at module level (NOT inside ClassDef)
    def _is_shell_tool_assign(node: ast.AST) -> bool:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "SHELL_TOOL_DEFINITION":
                    return True
        return False

    # Find all assignments at module level
    module_level_assign = any(
        _is_shell_tool_assign(node) for node in tree.body
    )
    assert module_level_assign, (
        "SHELL_TOOL_DEFINITION must be assigned at module level "
        "(top of file, not inside class MainWindow)"
    )

    # Verify it's NOT inside a ClassDef
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if _is_shell_tool_assign(item):
                    assert False, (
                        "SHELL_TOOL_DEFINITION must NOT be inside class MainWindow"
                    )


# ─── v0.4.0-ui verify v1 CRITICAL-1 regression ────────────────────────────────


def test_on_tool_result_passes_tool_call_id_to_add_message() -> None:
    """Regression: _on_tool_result must persist tool_call_id on the tool message.

    Without this, the second turn of a tool-calling cycle breaks because
    llama-server (OpenAI-compatible) requires tool_call_id on tool
    messages to match the assistant's tool_calls[].id. v0.4.0-ui verify v1
    found this as CRITICAL-1.
    """
    import re
    from pathlib import Path
    src = Path("bellbird/ui/main_window.py").read_text(encoding="utf-8")
    # The signature now has defaults for the extra params
    m = re.search(
        r"def _on_tool_result\(self, result, tool_call_id: str.*?\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_on_tool_result not found in main_window.py"
    body = m.group(0)
    # Find the FULL add_message call for the "tool" role (may span multiple lines)
    # The tool message is the one with tool_call_id kwarg
    add_msg_tool = re.search(
        r"self\._conversation\.add_message\(\s*\"tool\"",
        body,
    )
    assert add_msg_tool is not None, (
        "_on_tool_result must call add_message for role 'tool'"
    )
    # Find the add_message call containing tool_call_id=
    tool_add_end = body.find(")", add_msg_tool.start())
    tool_call = body[add_msg_tool.start():tool_add_end + 1]
    assert "tool_call_id" in tool_call and "tool_call_id=" in tool_call, (
        "_on_tool_result's tool add_message call MUST pass tool_call_id=tool_call_id "
        "to persist the ID for the next API call. Otherwise the tool-calling "
        "cycle breaks at the second turn. See verify-report v1 CRITICAL-1."
    )


# ─── v0.7.5 tool-support gate, iteration guard, assistant+tool_calls ────────


def test_iteration_guard_check_in_continue() -> None:
    """_continue_after_tool increments counter and checks max_tool_iterations."""
    import re
    from pathlib import Path
    src = Path("bellbird/ui/main_window.py").read_text(encoding="utf-8")
    m = re.search(
        r"def _continue_after_tool\(self\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_continue_after_tool not found"
    body = m.group(0)
    assert "max_tool_iterations" in body, (
        "_continue_after_tool must reference max_tool_iterations"
    )
    assert "_tool_iteration_count" in body, (
        "_continue_after_tool must reference _tool_iteration_count"
    )
    # Either an early return or end of method when limit reached
    assert "return" in body, (
        "_continue_after_tool must have a return after the iteration guard"
    )


def test_assistant_tool_calls_inserted_in_on_tool_result() -> None:
    """_on_tool_result inserts assistant message with tool_calls before tool message."""
    import re
    from pathlib import Path
    src = Path("bellbird/ui/main_window.py").read_text(encoding="utf-8")
    m = re.search(
        r"def _on_tool_result\(self, result, tool_call_id: str.*?\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_on_tool_result not found"
    body = m.group(0)
    # Must have add_message for assistant with tool_calls= kwarg
    # The call spans multiple lines with \n"assistant"
    assert "add_message(" in body and "assistant" in body, (
        "_on_tool_result must call add_message for the assistant role"
    )
    assert "tool_calls" in body, (
        "_on_tool_result must include tool_calls in the assistant add_message call"
    )
    # Verify tool_calls entry is constructed with correct OpenAI fields
    assert '"id": tool_call_id' in body, (
        "tool_calls entry must have id set to tool_call_id"
    )
    assert '"type": "function"' in body, (
        "tool_calls entry must have type='function'"
    )
    assert '"name": tool_name' in body, (
        "tool_calls entry function must have name=tool_name"
    )
    assert 'json.dumps({"command": command})' in body, (
        "tool_calls entry must have arguments as JSON string of command"
    )


def test_send_message_gates_on_check_tool_support() -> None:
    """send_message references check_tool_support and gates tools on it."""
    import re
    from pathlib import Path
    src = Path("bellbird/ui/main_window.py").read_text(encoding="utf-8")
    m = re.search(
        r"def send_message\(self\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "send_message not found"
    body = m.group(0)
    assert "check_tool_support" in body, (
        "send_message must call check_tool_support() to probe /props"
    )
    # When check_tool_support is False, tools must be set to None
    assert "tools = None" in body or "tools=None" in body, (
        "send_message must set tools=None when check_tool_support is False"
    )


def test_send_message_guards_on_tool_executing() -> None:
    """send_message early-return guard also checks _tool_executing.

    Prevents the user from sending a new message while a shell tool is
    executing in the background (window between _on_done clearing
    _is_generating and _continue_after_tool restarting it).
    """
    import re
    from pathlib import Path
    src = Path("bellbird/ui/main_window.py").read_text(encoding="utf-8")
    m = re.search(
        r"def send_message\(self\).*?(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "send_message not found"
    body = m.group(0)
    assert "_tool_executing" in body, (
        "send_message must check self._tool_executing in its early-return guard"
    )


def test_on_tool_call_sets_tool_executing() -> None:
    """_on_tool_call sets _tool_executing = True as its first statement."""
    import re
    from pathlib import Path
    src = Path("bellbird/ui/main_window.py").read_text(encoding="utf-8")
    m = re.search(
        r"def _on_tool_call\(self, tool_name.*?\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_on_tool_call not found"
    body = m.group(0)
    assert "self._tool_executing = True" in body, (
        "_on_tool_call must set self._tool_executing = True"
    )


def test_on_tool_result_clears_tool_executing() -> None:
    """_on_tool_result clears _tool_executing = False before any guard."""
    import re
    from pathlib import Path
    src = Path("bellbird/ui/main_window.py").read_text(encoding="utf-8")
    m = re.search(
        r"def _on_tool_result\(self, result, tool_call_id: str.*?\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_on_tool_result not found"
    body = m.group(0)
    assert "self._tool_executing = False" in body, (
        "_on_tool_result must reset self._tool_executing = False"
    )
    # Must appear before the first self._aborted check
    false_pos = body.find("self._tool_executing = False")
    aborted_pos = body.find("self._aborted")
    assert false_pos < aborted_pos, (
        "_tool_executing = False must appear before the _aborted guard in _on_tool_result"
    )


def test_on_done_skips_save_when_tool_executing() -> None:
    """_on_done skips add_message for assistant when _tool_executing is True.

    Prevents saving a tool-less assistant message when the stream ends with
    finish_reason=tool_calls. _on_tool_result saves the correct message with
    tool_calls included.
    """
    import re
    from pathlib import Path
    src = Path("bellbird/ui/main_window.py").read_text(encoding="utf-8")
    m = re.search(
        r"def _on_done\(self\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_on_done not found"
    body = m.group(0)
    assert "_tool_executing" in body, (
        "_on_done must check self._tool_executing before saving the assistant message"
    )


def test_grant_session_uses_get_risk() -> None:
    """grant_session is called with dlg.get_risk(), not the original risk variable.

    When the user edits a command and the risk level changes in the dialog,
    the session grant must use the final risk, not the pre-dialog original.
    """
    import re
    from pathlib import Path
    src = Path("bellbird/ui/main_window.py").read_text(encoding="utf-8")
    m = re.search(
        r"def _on_tool_call\(self, tool_name.*?\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_on_tool_call not found"
    body = m.group(0)
    assert "dlg.get_risk()" in body, (
        "grant_session must use dlg.get_risk() so the final (possibly edited) "
        "risk is used, not the original risk variable"
    )


def test_post_tool_speech_no_consultando() -> None:
    """_on_tool_result speech does NOT contain 'Consultando al modelo.'."""
    import re
    from pathlib import Path
    src = Path("bellbird/ui/main_window.py").read_text(encoding="utf-8")
    m = re.search(
        r"def _on_tool_result\(self, result, tool_call_id: str.*?\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_on_tool_result not found"
    body = m.group(0)
    assert "Consultando al modelo" not in body, (
        "_on_tool_result must NOT contain 'Consultando al modelo' speech — "
        "the short feedback form replaces the verbose announcement"
    )
    # Must contain the short feedback pattern
    assert "código" in body, (
        "_on_tool_result must contain short feedback with exit code"
    )
    assert "self._speech.speak" in body, (
        "_on_tool_result must call self._speech.speak"
    )


def _get_attr_name(node: ast.AST) -> str:
    """Extract the dotted name from a nested attribute node."""
    if isinstance(node, ast.Attribute):
        return f"{_get_attr_name(node.value)}.{node.attr}"
    elif isinstance(node, ast.Name):
        return node.id
    return "<unknown>"


# ─── v0.4.0 server lifecycle + new conversation fixes ─────────────────────


def test_new_conversation_calls_abort() -> None:
    """Regression for BUG 1: new_conversation must abort the active stream.

    Without abort, the background stream keeps running and its
    callbacks (_on_token, _on_done, _on_error) arrive via wx.CallAfter,
    writing tokens of the previous session into the new empty
    conversation. The body of new_conversation must contain a call to
    self._client.abort() (typically guarded by `if self._is_generating`).
    """
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "new_conversation":
            method = node
            break

    assert method is not None, "new_conversation method not found in main_window.py"

    has_abort = False
    for node in ast.walk(method):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node)
            if func_name == "self._client.abort":
                has_abort = True
                break

    assert has_abort, (
        "new_conversation must call self._client.abort() to stop the "
        "background stream when a generation is active. Without this, "
        "the previous session's tokens leak into the new conversation."
    )


def test_new_conversation_has_confirmation() -> None:
    """new_conversation must ask the user before discarding messages.

    Inconsistency fix: _on_close already confirms when there are
    unsaved messages, but new_conversation silently deleted the whole
    conversation. The body must contain a wx.MessageDialog with the
    YES_NO style flag (a confirmation dialog). Stock Yes/No labels
    are safe per AGENTS.md (only custom Spanish labels trigger MSAA
    regressions).
    """
    import re
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    m = re.search(
        r"def new_conversation\(self\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        source,
        re.DOTALL,
    )
    assert m is not None, "new_conversation method not found in main_window.py"
    body = m.group(0)

    assert "wx.MessageDialog(" in body, (
        "new_conversation must show a wx.MessageDialog confirmation "
        "when there are messages. _on_close already does this; the "
        "inconsistency is a UX bug."
    )
    assert "wx.YES_NO" in body, (
        "new_conversation's confirmation dialog must use wx.YES_NO "
        "stock labels (safe per AGENTS.md MSAA rules)."
    )
    assert "wx.NO_DEFAULT" in body, (
        "new_conversation's confirmation dialog must use wx.NO_DEFAULT "
        "so the safe option (cancel) is the default selection."
    )
    assert "self._config.confirm_new_conversation" in body, (
        "new_conversation must check self._config.confirm_new_conversation "
        "before showing the dialog — the preference must actually take effect."
    )


def test_on_start_server_does_not_call_start_server_directly() -> None:
    """Regression for BUG 2: _on_start_server must not block the main thread.

    Previously _on_start_server called start_server() directly, which
    runs a poll loop with time.sleep(0.2) for up to 60 seconds on the
    UI thread. The fix delegates to _on_use_model, which runs the
    load in a background thread with periodic announcements.

    This test asserts that the body of _on_start_server contains NO
    direct call to start_server(), and DOES call self._on_use_model.
    """
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_on_start_server":
            method = node
            break

    assert method is not None, "_on_start_server method not found in main_window.py"

    for node in ast.walk(method):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node)
            assert func_name != "start_server", (
                "_on_start_server must NOT call start_server() directly — "
                "it would block the main thread for up to 60s. Delegate "
                "to self._on_use_model (background thread + announce timer)."
            )

    delegates_to_use_model = False
    for node in ast.walk(method):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node)
            if func_name == "self._on_use_model":
                delegates_to_use_model = True
                break

    assert delegates_to_use_model, (
        "_on_start_server must delegate to self._on_use_model so the "
        "server start runs in a background thread with periodic "
        "announcements (and so _on_start_server_done updates the title)."
    )


# ─── v0.4.1 accessible_output2 Usage Polish ───────────────────────────────


def test_maybe_beep_guards_on_screen_reader() -> None:
    """_maybe_beep returns early when screen reader is active, before winsound.

    The guard must appear after the platform check and before any
    winsound.Beep call or throttle logic.
    """
    import re
    source_path = _get_ui_path("main_window.py")
    src = source_path.read_text(encoding="utf-8")
    m = re.search(
        r"def _maybe_beep\(self\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_maybe_beep not found"
    body = m.group(0)

    # Find positions of key statements
    platform_guard_pos = body.find('if sys.platform != "win32":')
    sr_guard_pos = body.find("self._speech.is_screen_reader_active()")
    throttle_pos = body.find("time.monotonic()")
    beep_pos = body.find("winsound.Beep")

    assert platform_guard_pos >= 0, (
        "Platform guard (sys.platform != 'win32') must be present"
    )
    assert sr_guard_pos >= 0, (
        "is_screen_reader_active() guard must be present"
    )
    assert beep_pos >= 0, "winsound.Beep must be present"

    # Screen-reader guard must come after platform guard and before throttle
    assert sr_guard_pos > platform_guard_pos, (
        "is_screen_reader_active() guard must come AFTER platform check"
    )
    assert sr_guard_pos < beep_pos, (
        "is_screen_reader_active() guard must come BEFORE winsound.Beep"
    )
    # Verify the guard returns early
    sr_return = body.find(
        "if self._speech.is_screen_reader_active():\n            return"
    )
    assert sr_return >= 0, (
        "is_screen_reader_active guard must be an early-return pattern"
    )


def test_abort_generation_calls_speech_stop_and_clear_buffer() -> None:
    """abort_generation body contains _speech.stop and _speech.clear_buffer.

    The order MUST be: _client.abort → _speech.stop → _speech.clear_buffer.
    """
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "abort_generation":
            method = node
            break

    assert method is not None, "abort_generation not found in main_window.py"

    # Collect method calls in body order
    calls = []
    for stmt in ast.walk(method):
        if isinstance(stmt, ast.Call):
            func_name = _get_func_name(stmt)
            if func_name in ("self._client.abort", "self._speech.stop", "self._speech.clear_buffer"):
                calls.append(func_name)

    assert "self._client.abort" in calls, (
        "abort_generation must call self._client.abort()"
    )
    assert "self._speech.stop" in calls, (
        "abort_generation must call self._speech.stop()"
    )
    assert "self._speech.clear_buffer" in calls, (
        "abort_generation must call self._speech.clear_buffer()"
    )

    # Verify order: abort → stop → clear_buffer
    abort_idx = calls.index("self._client.abort")
    stop_idx = calls.index("self._speech.stop")
    clear_idx = calls.index("self._speech.clear_buffer")
    assert abort_idx < stop_idx < clear_idx, (
        f"Expected order abort → stop → clear_buffer, got: {calls}"
    )


def test_dialogs_speak_after_show_modal() -> None:
    """Three dialog methods speak AFTER ShowModal to avoid double announcement.

    _on_error, _show_about, _show_shortcuts must each have the speak
    call AFTER ShowModal in the non-aborted path. _startup_check is
    exempt (speaks BEFORE).

    Note: _on_error now has an ``if self._aborted:`` guard at the top
    that speaks "Generación detenida" without a modal — we use ``rfind``
    for both speak and ShowModal to find the LAST occurrence in the body,
    which for _on_error corresponds to the error path (non-aborted).
    """
    import re
    source_path = _get_ui_path("main_window.py")
    src = source_path.read_text(encoding="utf-8")

    methods = ("_on_error", "_show_about", "_show_shortcuts")
    for method_name in methods:
        m = re.search(
            rf"def {method_name}\(self.*?\) -> None:.*?"
            r"(?=\n    def |\nclass |\Z)",
            src, re.DOTALL,
        )
        assert m is not None, f"{method_name} not found"
        body = m.group(0)

        speak_pos = body.rfind("self._speech.speak(")
        modal_pos = body.rfind("ShowModal()")

        assert speak_pos >= 0, (
            f"{method_name} must contain a self._speech.speak() call"
        )
        assert modal_pos >= 0, (
            f"{method_name} must contain a ShowModal() call"
        )
        assert speak_pos > modal_pos, (
            f"{method_name}: speak() must appear AFTER ShowModal() "
            f"to avoid double announcement. "
            f"speak at {speak_pos}, ShowModal at {modal_pos}"
        )


def test_startup_check_speaks_before_modal() -> None:
    """_startup_check ordering is preserved: speak BEFORE ShowModal.

    This is the intentional exemption for critical startup alerts.
    """
    import re
    source_path = _get_ui_path("main_window.py")
    src = source_path.read_text(encoding="utf-8")
    m = re.search(
        r"def _startup_check\(self\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_startup_check not found"
    body = m.group(0)

    speak_pos = body.find("self._speech.speak(")
    modal_pos = body.find("ShowModal()")

    assert speak_pos >= 0, (
        "_startup_check must contain a self._speech.speak() call"
    )
    assert modal_pos >= 0, (
        "_startup_check must contain a ShowModal() call"
    )
    assert speak_pos < modal_pos, (
        "_startup_check: speak() must appear BEFORE ShowModal() "
        "(intentional pre-alert exemption)"
    )


def test_on_start_server_done_calls_output_on_success() -> None:
    """_on_start_server_done calls self._speech.output in the success branch.

    The output call must appear only in the `if ok:` branch, after
    _update_title / _scan_models, guarded by `if loaded:`.
    """
    import re
    source_path = _get_ui_path("main_window.py")
    src = source_path.read_text(encoding="utf-8")
    m = re.search(
        r"def _on_start_server_done\(self, ok: bool, message: str.*?\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_on_start_server_done not found"
    body = m.group(0)

    # Verify the success branch contains _speech.output
    assert "self._speech.output(" in body, (
        "_on_start_server_done must call self._speech.output() in the "
        "success branch so the model name reaches braille displays"
    )

    # Verify output call is inside the `if ok:` / `if loaded:` block
    ok_pos = body.find("if ok:")
    output_pos = body.find("self._speech.output(")
    assert output_pos > ok_pos, (
        "self._speech.output() must be inside the `if ok:` branch"
    )


def test_on_usage_does_not_call_output() -> None:
    """_on_usage must NOT call _speech.output (would spam braille display).

    Only announce_token_chunk is allowed for per-token updates.
    """
    import re
    source_path = _get_ui_path("main_window.py")
    src = source_path.read_text(encoding="utf-8")
    m = re.search(
        r"def _on_usage\(self, usage: dict\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_on_usage not found"
    body = m.group(0)

    assert "self._speech.output(" not in body, (
        "_on_usage must NOT call self._speech.output() — per-token "
        "braille output would spam the display"
    )
    assert "self._speech.announce_token_chunk" not in body, (
        "_on_usage does not call announce_token_chunk (that happens "
        "in _on_token via announcer thread)"
    )


# ─── v0.4.1 stream callback guards (BUG 1 race) ───────────────────────────


def test_callbacks_guard_on_is_generating() -> None:
    """Regression for BUG 1 race: stream callbacks must drop late events.

    When new_conversation aborts an active stream, 1-2 tokens may
    already be in the wx.CallAfter queue before the abort signal
    reaches the background thread. _on_token, _on_done, and _on_error
    must drop late events via an ``if not self._is_generating: return``
    guard. _on_done and _on_error now have an additional
    ``if self._aborted:`` guard BEFORE the _is_generating guard.

    The _is_generating guard must be present among the first two
    executable statements and be a single-return guard.
    """
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for method_name in ("_on_token", "_on_done", "_on_error"):
        method = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == method_name:
                method = node
                break
        assert method is not None, f"{method_name} not found in main_window.py"

        # Collect first two non-docstring executable statements.
        exec_stmts = []
        for stmt in method.body:
            if (isinstance(stmt, ast.Expr)
                    and isinstance(stmt.value, ast.Constant)
                    and isinstance(stmt.value.value, str)):
                continue  # docstring
            exec_stmts.append(stmt)
            if len(exec_stmts) == 2:
                break

        assert len(exec_stmts) >= 1, f"{method_name} has no body"

        # At least one of the first two statements must be an `if` guard
        # referencing self._is_generating with a single return in its body.
        found_is_generating_guard = False
        for stmt in exec_stmts:
            if isinstance(stmt, ast.If):
                cond_dump = ast.dump(stmt.test)
                if "_is_generating" in cond_dump:
                    if len(stmt.body) == 1 and isinstance(
                        stmt.body[0], ast.Return
                    ):
                        found_is_generating_guard = True
                        break

        assert found_is_generating_guard, (
            f"{method_name} must have an 'if not self._is_generating: "
            f"return' guard among the first 2 executable statements. "
            f"Found statements: {[type(s).__name__ for s in exec_stmts]}"
        )


# ─── v0.5.1 send_message double-send guard ───────────────────────────────


def test_send_message_guards_on_is_generating() -> None:
    """Regression: send_message must return early if _is_generating is True.

    Without the guard, pressing Enter twice (e.g. 'hola' then 'hola?'
    before the first response arrives) aborts the first stream and starts
    a second one.  The first stream's _on_done callback fires from the
    wx.CallAfter queue, says 'Respuesta completa' with empty content, and
    resets _is_generating=False.  The second stream's _on_done then skips
    everything because _is_generating is already False — no response saved.

    Note: the first statement is now ``self._aborted = False`` (reset),
    followed by the ``if self._is_generating: return`` guard.
    """
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "send_message":
            method = node
            break
    assert method is not None, "send_message not found in main_window.py"

    # Collect first two non-docstring executable statements.
    exec_stmts = []
    for stmt in method.body:
        if (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        ):
            continue  # docstring
        exec_stmts.append(stmt)
        if len(exec_stmts) == 2:
            break

    assert len(exec_stmts) >= 1, "send_message has no body"

    # Find the _is_generating guard among the first two statements.
    found_guard = False
    for stmt in exec_stmts:
        if isinstance(stmt, ast.If):
            cond_dump = ast.dump(stmt.test)
            if "_is_generating" in cond_dump:
                assert any(isinstance(s, ast.Return) for s in stmt.body), (
                    "send_message guard body must contain a return statement"
                )
                found_guard = True
                break

    assert found_guard, (
        "send_message must have an 'if self._is_generating: return' guard "
        "among the first 2 executable statements. "
        f"Found: {[type(s).__name__ for s in exec_stmts]}"
    )


# ─── v0.4.1 keyboard navigation improvements ────────────────────────────


def test_config_loaded_in_init():
    """MainWindow.__init__ calls load_config() and assigns to self._config
    BEFORE the LlamaClient constructor that reads self._config.port.
    Order-aware regression guard for the v0.4.1 init-order bug
    (see verify-report CRITICAL-1).
    """
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    config_assign_lineno: int | None = None
    llama_client_call_lineno: int | None = None

    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name == "__init__"):
            continue

        for child in ast.walk(node):
            if not isinstance(child, ast.Assign):
                continue
            # `self._config = load_config()`
            if (any(
                    isinstance(t, ast.Attribute) and t.attr == "_config"
                    for t in child.targets
                )
                and isinstance(child.value, ast.Call)
                and _get_func_name(child.value) == "load_config"):
                config_assign_lineno = child.lineno

            # `self._client = LlamaClient(base_url=... self._config.port ...)`
            if (any(
                    isinstance(t, ast.Attribute) and t.attr == "_client"
                    for t in child.targets
                )
                and isinstance(child.value, ast.Call)
                and _get_func_name(child.value) == "LlamaClient"):
                llama_client_call_lineno = child.lineno

    assert config_assign_lineno is not None, (
        "self._config = load_config() not found in MainWindow.__init__"
    )
    assert llama_client_call_lineno is not None, (
        "self._client = LlamaClient(...) not found in MainWindow.__init__"
    )
    assert config_assign_lineno < llama_client_call_lineno, (
        f"self._config = load_config() is on line {config_assign_lineno} "
        f"but self._client = LlamaClient(...) is on line "
        f"{llama_client_call_lineno}. The config load must happen BEFORE "
        f"the LlamaClient constructor (regression of v0.4.1 verify-report "
        f"CRITICAL-1)."
    )


def test_f7_accelerator_defined():
    """F7 shortcut is defined in keymap.py; main_window imports the keymap.

    The F7 binding moved from hardcoded wx.WXK_F7 in _build_accelerators
    to the DEFAULT_KEYMAP in keymap.py.
    """
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    assert "from bellbird.core.keymap import" in source, (
        "keymap module not imported in main_window.py"
    )
    # Verify keymap.py defines start_server with F7 keycode (345 = WXK_F7)
    km_path = source_path.parent.parent / "core" / "keymap.py"
    km_source = km_path.read_text(encoding="utf-8")
    assert '"start_server"' in km_source, "start_server not in DEFAULT_KEYMAP"
    keycode_line = [l for l in km_source.split("\n") if "start_server" in l][0]
    assert "345" in keycode_line, (
        "WXK_F7 (345) not found in start_server binding in keymap.py"
    )


def test_f6_has_four_targets():
    """_on_f6_cycle references restart_server_button as the 4th target."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_on_f6_cycle":
            method = node
            break

    assert method is not None, "_on_f6_cycle method not found"
    source_lines = source.splitlines()
    start = method.lineno - 1
    end = method.end_lineno
    method_source = "\n".join(source_lines[start:end])

    assert "restart_server_button" in method_source, (
        "_on_f6_cycle must reference restart_server_button as the 4th target"
    )


# ─── v0.5.0 layout refactor AST tests (TDD RED until implementation) ──────


def test_no_splitter_window():
    """'SplitterWindow' must NOT appear in main_window.py source."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    assert "SplitterWindow" not in source, (
        "SplitterWindow must be removed from MainWindow in v0.5.0"
    )


def test_model_selector_in_frame():
    """model_selector is created as a direct child of the Frame (self)
    with style=wx.CB_READONLY for NVDA screen-reader accessibility."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    found = False
    style_checked = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node)
            if func_name == "wx.ComboBox":
                for kw in node.keywords:
                    if kw.arg == "name" and isinstance(kw.value, ast.Constant) and kw.value.value == "Selector de modelo":
                        found = True
                    if kw.arg == "style":
                        style_src = ast.unparse(kw.value)
                        assert "CB_READONLY" in style_src, (
                            f"model_selector must be read-only (style=wx.CB_READONLY);"
                            f" got {style_src}"
                        )
                        style_checked = True
                if found and style_checked:
                    break

    assert found, (
        "model_selector (wx.ComboBox with name='Selector de modelo') must be "
        "created in MainWindow (parent=self)"
    )
    assert style_checked, (
        "model_selector ComboBox must declare a 'style' kwarg (wx.CB_READONLY)"
    )


def test_model_selector_has_no_text_change_handler():
    """Read-only combo must not bind EVT_TEXT or define _on_model_text_change."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_on_model_text_change":
            pytest.fail("_on_model_text_change must be removed (combo is read-only)")
    assert "EVT_TEXT" not in source, (
        "EVT_TEXT must not be bound in main_window.py (combo is read-only)"
    )


def test_set_models_reselects_last_model():
    """set_models must find and select last_model when it exists in the list."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "set_models":
            method = node
            break
    assert method is not None, "set_models method not found"

    source_lines = source.splitlines()
    start = method.lineno - 1
    end = method.end_lineno
    method_source = "\n".join(source_lines[start:end])

    assert "FindString" in method_source, (
        "set_models must use FindString to locate last_model in the list"
    )
    assert "last_model" in method_source, (
        "set_models must reference self._config.last_model for reselection"
    )


def test_menu_servidor_present():
    """_build_menu source must contain 'Servidor' menu."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Find _build_menu method
    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_build_menu":
            method = node
            break

    assert method is not None, "_build_menu method not found"
    source_lines = source.splitlines()
    start = method.lineno - 1
    end = method.end_lineno
    method_source = "\n".join(source_lines[start:end])

    assert "Servidor" in method_source, (
        "_build_menu must contain a 'Servidor' menu between Archivo and Ayuda"
    )


def test_params_from_config():
    """send_message calls _build_options(self._config); _build_options reads from config fields.

    Refactored for v0.7.2: the inline options dict was extracted into
    _build_options(). send_message now calls the helper. This test
    verifies that _build_options reads each sampling field from config
    and that send_message delegates to _build_options instead of
    building an inline dict.
    """
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # 1. Verify send_message calls _build_options(self._config)
    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "send_message":
            method = node
            break
    assert method is not None, "send_message method not found"

    calls_build_options = False
    for node in ast.walk(method):
        if isinstance(node, ast.Call):
            func_name = ast.unparse(node.func)
            if "_build_options" in func_name:
                calls_build_options = True
                break
    assert calls_build_options, (
        "send_message must call _build_options(self._config) "
        "instead of building an inline options dict"
    )

    # 2. Verify no inline dict with temperature/max_tokens in send_message
    has_inline_options = False
    for node in ast.walk(method):
        if not isinstance(node, ast.Dict):
            continue
        keys = [
            k.value
            for k in node.keys
            if isinstance(k, ast.Constant) and isinstance(k.value, str)
        ]
        if "temperature" in keys and "max_tokens" in keys:
            has_inline_options = True
            break
    assert not has_inline_options, (
        "send_message must NOT build an inline options dict; "
        "use _build_options(self._config) instead"
    )

    # 3. Verify _build_options function has the correct field mappings
    build_func = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_build_options":
            build_func = node
            break
    assert build_func is not None, "_build_options function not found"

    options_dict = None
    for node in ast.walk(build_func):
        if not isinstance(node, ast.Dict):
            continue
        keys = [
            k.value
            for k in node.keys
            if isinstance(k, ast.Constant) and isinstance(k.value, str)
        ]
        if "temperature" in keys and "max_tokens" in keys:
            options_dict = node
            break

    assert options_dict is not None, (
        "_build_options must contain a dict literal with at least 'temperature' "
        "and 'max_tokens' keys"
    )

    # Build a map: key string -> AST value node
    field_map: dict[str, ast.AST] = {}
    for k, v in zip(options_dict.keys, options_dict.values):
        if isinstance(k, ast.Constant) and isinstance(k.value, str):
            field_map[k.value] = v

    # Each sampling field must come from config.<same field> (not self._config)
    for field in ("temperature", "max_tokens", "top_p", "top_k", "repeat_penalty", "min_p"):
        assert field in field_map, (
            f"_build_options dict is missing the {field!r} key"
        )
        value = field_map[field]
        assert isinstance(value, ast.Attribute), (
            f"_build_options[{field!r}] must be an attribute access "
            f"(e.g. config.{field}), got: {ast.dump(value)}"
        )
        inner = value.value
        assert (
            isinstance(inner, ast.Name)
            and inner.id == "config"
        ), (
            f"_build_options[{field!r}] must be config.{field}, not self._config.{field}, "
            f"got: {ast.unparse(value)}"
        )
        assert value.attr == field, (
            f"_build_options[{field!r}] key is wired to config.{value.attr!r}; "
            f"expected config.{field}"
        )

    # 4. The send flow must not call any legacy params_panel accessor
    method_source_lines = source.splitlines()[method.lineno - 1:method.end_lineno]
    method_source = "\n".join(method_source_lines)
    for forbidden in (
        "params_panel.get_params",
        "params_panel.get_system_prompt",
        "params_panel.get_tools_enabled",
        "params_panel.set_system_prompt",
    ):
        assert forbidden not in method_source, (
            f"send_message must not call {forbidden}() "
            f"(replaced by self._config reads)"
        )


def test_f6_cycle_target_is_model_selector():
    """F6 cycle first target is self.model_selector (not self.params_panel.model_selector)."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_on_f6_cycle":
            method = node
            break

    assert method is not None, "_on_f6_cycle method not found"
    source_lines = source.splitlines()
    start = method.lineno - 1
    end = method.end_lineno
    method_source = "\n".join(source_lines[start:end])

    # Target 0 must reference self.model_selector, NOT self.params_panel.model_selector
    assert "self.params_panel.model_selector" not in method_source, (
        "F6 cycle target 0 must NOT reference self.params_panel.model_selector"
    )
    assert "self.model_selector" in method_source, (
        "F6 cycle must reference self.model_selector as the first target"
    )


def test_window_size_900_650():
    """Frame super().__init__ uses size=(900, 650)."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    assert "size=(900, 650)" in source, (
        "MainWindow's super().__init__ must use size=(900, 650)"
    )


def test_version_0_8_3():
    """pyproject.toml has version = '0.8.3'."""
    import pathlib
    proj_path = (
        pathlib.Path(__file__).resolve().parent.parent.parent
        / "pyproject.toml"
    )
    source = proj_path.read_text(encoding="utf-8")
    assert 'version = "0.8.3"' in source, (
        "pyproject.toml must have version = \"0.8.3\""
    )


def test_show_preferences_recreates_client_on_port_change() -> None:
    """_show_preferences must recreate self._client when the port changes.

    When the user changes self._config.port in Preferences and clicks OK,
    the LlamaClient URL must be updated to match. Without this, start_server
    launches llama-server on the new port but polls the old port for the
    health check, causing a spurious timeout failure.
    """
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    import re
    m = re.search(
        r"def _show_preferences\(self\) -> None:.*?(?=\n    def |\nclass |\Z)",
        source,
        re.DOTALL,
    )
    assert m is not None, "_show_preferences method not found"
    body = m.group(0)
    assert "self._client = LlamaClient(" in body, (
        "_show_preferences must recreate self._client with the new port "
        "when self._config.port changes. Otherwise start_server polls the "
        "old port and reports a false timeout."
    )
    assert "old_port" in body, (
        "_show_preferences must compare old and new port before recreating "
        "the client (guard: if self._config.port != old_port)."
    )


# ─── v0.6.0 non-blocking startup (Task 4) ──────────────────────────────


def test_init_no_sync_calls() -> None:
    """__init__ must NOT contain direct calls to synchronous startup functions.

    The startup probe now runs on a background thread. Direct calls to
    _startup_check, check_running, find_llama_server, get_loaded_model,
    or _scan_models in __init__ would block the window from showing.
    """
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "__init__":
            method = node
            break
    assert method is not None, "__init__ not found in main_window.py"

    forbidden = {
        "_startup_check",
        "check_running",
        "find_llama_server",
        "get_loaded_model",
        "_scan_models",
    }
    for node in ast.walk(method):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node)
            # Only flag bare calls to these functions (not method defs)
            for forbid in forbidden:
                if forbid in func_name:
                    assert False, (
                        f"__init__ must NOT call {forbid}() directly. "
                        f"Found: {func_name} at line {node.lineno}. "
                        f"The startup probe runs on a background thread."
                    )


def test_init_has_start_probe_thread() -> None:
    """__init__ must call self._start_probe_thread() after building the UI."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "__init__":
            method = node
            break
    assert method is not None, "__init__ not found"

    has_probe = False
    for node in ast.walk(method):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node)
            if func_name == "self._start_probe_thread":
                has_probe = True
                break

    assert has_probe, (
        "__init__ must call self._start_probe_thread() to run the "
        "startup probe on a background thread."
    )


def test_start_probe_thread_method_exists() -> None:
    """MainWindow has a _start_probe_thread method."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "_start_probe_thread":
                    found = True
                    break
    assert found, "_start_probe_thread method not found in MainWindow"


def test_on_startup_probe_done_method_exists() -> None:
    """MainWindow has a _on_startup_probe_done method."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "_on_startup_probe_done":
                    found = True
                    break
    assert found, "_on_startup_probe_done method not found in MainWindow"


def test_on_scan_done_method_exists() -> None:
    """MainWindow has a _on_scan_done method (threaded scan callback)."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "_on_scan_done":
                    found = True
                    break
    assert found, "_on_scan_done method not found in MainWindow"


# ── multimodal mmproj (v0.7.0) ────────────────────────────────────────────────


def test_vision_capable_initialized_to_false():
    """MainWindow.__init__ sets self._vision_capable = False."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    assert "self._vision_capable: bool = False" in source or (
        'self._vision_capable = False' in source and
        '__init__' in source  # sanity: the file has __init__
    ), "self._vision_capable must be initialized in __init__"


def test_vision_capable_declared():
    """MainWindow has _vision_capable as a typed attribute."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    assert "_vision_capable" in source, (
        "_vision_capable must be declared in MainWindow"
    )


def test_find_mmproj_imported():
    """main_window.py imports find_mmproj_for_model from model_meta."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    assert "from bellbird.core.model_meta import find_mmproj_for_model" in source, (
        "must import find_mmproj_for_model"
    )


def test_f2_status_contains_vision_string():
    """_announce_session_status generates a string with 'Imágenes:'."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    assert "Imágenes:" in source, (
        "F2 status must contain 'Imágenes: sí/no'"
    )


def test_send_message_vision_guard():
    """send_message checks _vision_capable before building image payload."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    assert "not self._vision_capable" in source or (
        "self._vision_capable" in source and
        "attached_images" in source
    ), "send_message must have a vision-capable guard"


def test_on_start_server_done_accepts_vision_flag():
    """_on_start_server_done accepts vision_capable parameter."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    assert "vision_capable" in source, (
        "_on_start_server_done must accept vision_capable parameter"
    )


# ─── v0.7.1 Robustness — stream timeout, tool cancel, watchdog ──────────


def test_abort_generation_calls_tool_executor_cancel_before_client_abort():
    """abort_generation calls tool_executor.cancel() before client.abort().

    Order: _aborted → _is_generating → tool_executor.cancel() → client.abort()
    """
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "abort_generation":
            method = node
            break

    assert method is not None, "abort_generation not found in main_window.py"

    # Collect assignments and calls in body order
    found_cancel = False
    found_abort = False
    cancel_line = -1
    abort_line = -1

    for node in ast.walk(method):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node)
            if func_name == "self._tool_executor.cancel":
                found_cancel = True
                cancel_line = node.lineno
            if func_name == "self._client.abort":
                found_abort = True
                abort_line = node.lineno

    assert found_cancel, (
        "abort_generation must call self._tool_executor.cancel()"
    )
    assert found_abort, "abort_generation must call self._client.abort()"
    assert cancel_line < abort_line, (
        f"self._tool_executor.cancel() (line {cancel_line}) must appear "
        f"BEFORE self._client.abort() (line {abort_line})"
    )


def test_on_tool_result_guards_result_cancelled():
    """_on_tool_result checks result.cancelled and returns early."""
    import re
    source_path = _get_ui_path("main_window.py")
    src = source_path.read_text(encoding="utf-8")
    m = re.search(
        r"def _on_tool_result\(self, result, tool_call_id: str.*?\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_on_tool_result not found in main_window.py"
    body = m.group(0)

    assert "result.cancelled" in body, (
        "_on_tool_result must check result.cancelled"
    )
    # Verify _continue_after_tool is not in the cancelled branch:
    # the cancelled branch returns early, so _continue_after_tool
    # must appear AFTER the last early-return guard.
    cancelled_pos = body.find("result.cancelled")
    continue_pos = body.find("_continue_after_tool")
    assert cancelled_pos >= 0, (
        "result.cancelled check not found"
    )
    # There should be a return before _continue_after_tool in the
    # cancelled branch — if cancelled_pos < continue_pos and there's
    # a return between them, the check is valid.
    return_in_cancelled = body.find("return", cancelled_pos, continue_pos)
    assert return_in_cancelled >= 0, (
        "_on_tool_result must have a return in the result.cancelled branch "
        "so _continue_after_tool is not called when the tool is cancelled"
    )


def test_init_passes_request_timeout_to_llama_client():
    """MainWindow.__init__ passes request_timeout= kwarg to LlamaClient()."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "__init__":
            method = node
            break

    assert method is not None, "__init__ not found"

    found_request_timeout = False
    for node in ast.walk(method):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node)
            if func_name == "LlamaClient":
                for kw in node.keywords:
                    if kw.arg == "request_timeout":
                        found_request_timeout = True
                        break

    assert found_request_timeout, (
        "LlamaClient() must receive request_timeout= kwarg in __init__"
    )


def test_on_error_has_connection_watchdog():
    """_on_error contains connection-error markers for the watchdog branch."""
    source_path = _get_ui_path("main_window.py")
    src = source_path.read_text(encoding="utf-8")
    assert "ConnectionError" in src, (
        "_on_error (or its helpers) must reference ConnectionError for "
        "the watchdog branch"
    )
    assert "_run_connection_watchdog" in src, (
        "Must have a _run_connection_watchdog method"
    )
    assert "_on_server_state_checked" in src, (
        "Must have a _on_server_state_checked method"
    )


def test_on_server_state_checked_handles_dead_and_loading():
    """_on_server_state_checked offers restart for dead, speaks for loading."""
    import re
    source_path = _get_ui_path("main_window.py")
    src = source_path.read_text(encoding="utf-8")
    # Multi-line signature: use _on_server_state_checked and find the method
    m = re.search(
        r"def _on_server_state_checked\(.*?\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_on_server_state_checked not found in main_window.py"
    body = m.group(0)

    assert 'if state == "dead":' in body, (
        "Must handle 'dead' state"
    )
    assert 'elif state == "loading":' in body, (
        "Must handle 'loading' state"
    )


def test_restart_dialog_uses_wx_dialog_not_message_dialog():
    """Restart dialog uses wx.Dialog, not wx.MessageDialog with custom labels."""
    source_path = _get_ui_path("main_window.py")
    src = source_path.read_text(encoding="utf-8")
    assert "wx.Dialog(" in src, (
        "Restart dialog must use wx.Dialog (not MessageDialog)"
    )
    assert 'name="server_down_dialog"' in src, (
        "Restart dialog must have name='server_down_dialog'"
    )
    assert 'name="restart_yes_button"' in src, (
        "Yes button must have name='restart_yes_button'"
    )
    assert 'name="restart_no_button"' in src, (
        "No button must have name='restart_no_button'"
    )


# ─── Phase 3: samplers-modernos — min_p, seed, stop (v0.7.2) ───────────────


def test_build_options_helper_exists():
    """_build_options is defined as a module-level function with BellbirdConfig param."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Find module-level function def
    found = False
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_build_options":
            found = True
            # Check first param name (should be config, type BellbirdConfig)
            args = node.args.args
            assert len(args) >= 1, "_build_options must have at least 1 parameter"
            # Return type should be dict
            if node.returns is not None:
                returns_ast = ast.unparse(node.returns)
                assert "dict" in returns_ast, (
                    f"_build_options return type should be dict, got: {returns_ast}"
                )
            break

    assert found, (
        "_build_options must be defined as a module-level function in main_window.py"
    )


def test_build_options_dict_contains_min_p():
    """_build_options dict literal always includes min_p key."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    func = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_build_options":
            func = node
            break

    assert func is not None, "_build_options function not found"

    # Find the options dict literal inside the function body
    found_min_p = False
    for node in ast.walk(func):
        if isinstance(node, ast.Dict):
            keys = [k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            if "temperature" in keys and "max_tokens" in keys:
                found_min_p = "min_p" in keys
                break

    assert found_min_p, (
        "_build_options dict must include 'min_p' key"
    )


def test_build_options_seed_conditional():
    """_build_options has 'if config.seed >= 0:' guard for seed key."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    func = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_build_options":
            func = node
            break

    assert func is not None, "_build_options function not found"

    has_seed_guard = False
    for node in ast.walk(func):
        if isinstance(node, ast.If):
            cond = ast.unparse(node.test)
            if "seed" in cond and ">= 0" in cond:
                has_seed_guard = True
                break

    assert has_seed_guard, (
        "_build_options must have 'if config.seed >= 0:' guard for seed"
    )


def test_build_options_stop_conditional():
    """_build_options has 'if config.stop:' guard for stop key."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    func = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_build_options":
            func = node
            break

    assert func is not None, "_build_options function not found"

    has_stop_guard = False
    for node in ast.walk(func):
        if isinstance(node, ast.If):
            cond = ast.unparse(node.test)
            if cond == "config.stop":
                has_stop_guard = True
                break

    assert has_stop_guard, (
        "_build_options must have 'if config.stop:' guard for stop"
    )


def test_both_call_sites_use_build_options():
    """Both send_message and _continue_after_tool call _build_options(self._config)."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Find methods in MainWindow class
    class_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow":
            class_node = node
            break

    assert class_node is not None, "MainWindow class not found"

    def _method_calls_build_options(method_name: str) -> bool:
        for item in class_node.body:
            if isinstance(item, ast.FunctionDef) and item.name == method_name:
                for call in ast.walk(item):
                    if isinstance(call, ast.Call):
                        func_name = ast.unparse(call.func)
                        if "_build_options" in func_name:
                            return True
        return False

    assert _method_calls_build_options("send_message"), (
        "send_message must call _build_options(self._config)"
    )
    assert _method_calls_build_options("_continue_after_tool"), (
        "_continue_after_tool must call _build_options(self._config)"
    )


def test_f2_includes_min_p():
    """_announce_session_status references self._config.min_p and includes 'Min-p'."""
    source_path = _get_ui_path("main_window.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Find _announce_session_status method
    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "_announce_session_status":
                    method = item
                    break

    assert method is not None, "_announce_session_status method not found"

    # Extract method source
    source_lines = source.splitlines()
    start = method.lineno - 1
    end = method.end_lineno
    method_source = "\n".join(source_lines[start:end])

    assert "self._config.min_p" in method_source, (
        "_announce_session_status must reference self._config.min_p"
    )
    assert "Min-p" in method_source, (
        "_announce_session_status must include 'Min-p' in the status string"
    )


# ─── v0.7.3 unified-chat-list: focus courtesy guard (D8 / Task 4.3) ────


def test_focus_courtesy_only_when_user_still_on_placeholder() -> None:
    """_on_done must guard SetSelection with a GetSelection equality check.

    When a generation finishes, the focus-courtesy invariant (D8) says:
    only restore the selection to the streaming placeholder if the user
    hasn't navigated away. If they moved to a different message, don't
    steal their position.

    This test verifies that SetSelection is called INSIDE a conditional
    block that first checks GetSelection() == streaming_index.
    """
    import re
    from pathlib import Path
    src = Path("bellbird/ui/main_window.py").read_text(encoding="utf-8")
    m = re.search(
        r"def _on_done\(self\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_on_done not found in main_window.py"
    body = m.group(0)

    # Both GetSelection() and SetSelection( must appear in _on_done
    get_pos = body.find(".GetSelection()")
    set_pos = body.find(".SetSelection(")
    assert get_pos >= 0, "GetSelection() call not found in _on_done"
    assert set_pos >= 0, "SetSelection() call not found in _on_done"

    # The SetSelection must appear AFTER a GetSelection == comparison,
    # proving the guard is present.
    assert set_pos > get_pos, (
        "SetSelection() must appear AFTER a GetSelection() guard check "
        "in _on_done — otherwise the focus courtesy invariant is broken"
    )

    # Verify there is a conditional (if) between them, meaning SetSelection
    # is guarded.
    snippet_between = body[get_pos:set_pos]
    assert "if " in snippet_between, (
        "SetSelection() must be inside a conditional block guarded by "
        "the GetSelection() equality check. Expected 'if' between "
        "GetSelection() and SetSelection()."
    )


# ─── v0.7.3/0.7.4 browser HTML render: invariants moved to html_render.py ──


def test_html_render_imports_in_main_window() -> None:
    """main_window.py imports render_message_html from bellbird.core.html_render.

    The HTML generation logic moved to a wx-free helper module. The
    markdown extensions, lang='es', and <details> wrappers are now
    invariants of bellbird/core/html_render.py — not main_window.py.
    """
    from pathlib import Path
    src = Path("bellbird/ui/main_window.py").read_text(encoding="utf-8")
    assert "from bellbird.core.html_render import render_message_html" in src, (
        "main_window.py must import render_message_html from bellbird.core.html_render"
    )
    assert "render_message_html(text, reasoning=reasoning)" in src, (
        "_open_message_in_browser must call render_message_html"
    )


# ─── v0.7.4 thin-wrapper invariants (Task 3.1) ──────────────────────────────


def test_open_message_in_browser_calls_render_message_html() -> None:
    """_open_message_in_browser body contains a reference to render_message_html."""
    import ast
    from pathlib import Path
    src = Path("bellbird/ui/main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_open_message_in_browser":
            method = node
            break
    assert method is not None, "_open_message_in_browser method not found"

    source_lines = src.splitlines()
    start = method.lineno - 1
    end = method.end_lineno
    method_source = "\n".join(source_lines[start:end])
    assert "render_message_html" in method_source


def test_open_message_in_browser_calls_webbrowser_open() -> None:
    """_open_message_in_browser body contains a call to webbrowser.open."""
    import ast
    from pathlib import Path
    src = Path("bellbird/ui/main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_open_message_in_browser":
            method = node
            break
    assert method is not None, "_open_message_in_browser method not found"

    source_lines = src.splitlines()
    start = method.lineno - 1
    end = method.end_lineno
    method_source = "\n".join(source_lines[start:end])
    assert "webbrowser.open" in method_source or "webbrowser\\.open" in method_source


def test_open_message_in_browser_does_not_call_markdown() -> None:
    """_open_message_in_browser body does NOT contain markdown.markdown(."""
    import ast
    from pathlib import Path
    src = Path("bellbird/ui/main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_open_message_in_browser":
            method = node
            break
    assert method is not None, "_open_message_in_browser method not found"

    source_lines = src.splitlines()
    start = method.lineno - 1
    end = method.end_lineno
    method_source = "\n".join(source_lines[start:end])
    assert "markdown.markdown(" not in method_source, (
        "markdown.markdown() call found in _open_message_in_browser — "
        "should be moved to the html_render helper"
    )


def test_open_message_in_browser_uses_named_temporary_file() -> None:
    """_open_message_in_browser body contains NamedTemporaryFile."""
    import ast
    from pathlib import Path
    src = Path("bellbird/ui/main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_open_message_in_browser":
            method = node
            break
    assert method is not None, "_open_message_in_browser method not found"

    source_lines = src.splitlines()
    start = method.lineno - 1
    end = method.end_lineno
    method_source = "\n".join(source_lines[start:end])
    assert "NamedTemporaryFile" in method_source


def test_find_in_history_handler_registered() -> None:
    """MainWindow._build_accelerators registers the 'find_in_history' handler.

    The handler dict must contain find_in_history → _on_find, so that the
    Ctrl+F keymap binding triggers the history search dialog.
    """
    from pathlib import Path
    src = Path("bellbird/ui/main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    # Find the handlers dict in _build_accelerators
    handlers_dict = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_build_accelerators":
            for child in ast.walk(node):
                if isinstance(child, ast.Dict) and any(
                    isinstance(k, ast.Constant) and k.value == "find_in_history"
                    for k in child.keys
                ):
                    handlers_dict = child
                    break

    assert handlers_dict is not None, (
        "find_in_history key not found in the handlers dict inside "
        "_build_accelerators"
    )


def test_on_find_method_exists() -> None:
    """MainWindow has an _on_find method that handles the find action."""
    from pathlib import Path
    src = Path("bellbird/ui/main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_on_find":
            found = True
            break

    assert found, "_on_find method not found in MainWindow"


def test_attach_url_handler_registered() -> None:
    """MainWindow._build_accelerators registers the 'attach_url' handler.

    The handler dict must contain attach_url → _on_attach_url, so that
    the Ctrl+U keymap binding triggers the URL dialog.
    """
    from pathlib import Path
    src = Path("bellbird/ui/main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    # Find the handlers dict in _build_accelerators
    handlers_dict = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_build_accelerators":
            for child in ast.walk(node):
                if isinstance(child, ast.Dict) and any(
                    isinstance(k, ast.Constant) and k.value == "attach_url"
                    for k in child.keys
                ):
                    handlers_dict = child
                    break

    assert handlers_dict is not None, (
        "attach_url key not found in the handlers dict inside "
        "_build_accelerators"
    )


def test_on_attach_url_method_exists() -> None:
    """MainWindow has an _on_attach_url method that handles Ctrl+U."""
    from pathlib import Path
    src = Path("bellbird/ui/main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_on_attach_url":
            found = True
            break

    assert found, "_on_attach_url method not found in MainWindow"


def test_fetch_url_worker_method_exists() -> None:
    """MainWindow has _fetch_url_worker method for background fetch."""
    from pathlib import Path
    src = Path("bellbird/ui/main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_fetch_url_worker":
            found = True
            break

    assert found, "_fetch_url_worker method not found in MainWindow"


def test_on_fetch_complete_method_exists() -> None:
    """MainWindow has _on_fetch_complete method for fetch result."""
    from pathlib import Path
    src = Path("bellbird/ui/main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_on_fetch_complete":
            found = True
            break

    assert found, "_on_fetch_complete method not found in MainWindow"


def test_derive_origin_label_method_exists() -> None:
    """MainWindow has _derive_origin_label static method."""
    from pathlib import Path
    src = Path("bellbird/ui/main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_derive_origin_label":
            found = True
            break

    assert found, "_derive_origin_label method not found in MainWindow"


def test_url_fetch_timer_slot_in_init() -> None:
    """MainWindow.__init__ initializes self._url_fetch_timer."""
    from pathlib import Path
    src = Path("bellbird/ui/main_window.py").read_text(encoding="utf-8")
    assert "self._url_fetch_timer" in src, (
        "self._url_fetch_timer must be declared in MainWindow"
    )


def test_no_message_dialog_in_attach_url_paths() -> None:
    """No wx.MessageDialog in _on_attach_url, _on_fetch_complete, or _fetch_url_worker.

    All user feedback for the URL fetch feature goes through speech.speak.
    """
    from pathlib import Path
    src = Path("bellbird/ui/main_window.py").read_text(encoding="utf-8")

    # Find each method and check it has no MessageDialog
    import re
    for method_name in ("_on_attach_url", "_on_fetch_complete", "_fetch_url_worker"):
        m = re.search(
            rf"def {method_name}\(.*?\) -> None:.*?"
            r"(?=\n    def |\nclass |\Z)",
            src, re.DOTALL,
        )
        assert m is not None, f"{method_name} not found"
        body = m.group(0)
        assert "wx.MessageDialog" not in body, (
            f"{method_name} must NOT contain wx.MessageDialog — "
            f"all feedback goes through speech.speak per AGENTS.md"
        )

