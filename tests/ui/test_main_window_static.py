"""Static/AST regression guards for MainWindow — accessibility, ordering, and
behavioral invariants. Tests here verify non-obvious properties that are easy
to break silently: flag-ordering, threading safety, API call structure, and
accessibility rules. Pure form/existence checks have been removed; those
belong in runtime tests or are covered by the type checker.
"""

import ast
import pathlib

import pytest


class _CombinedPath:
    """Wraps a pathlib.Path but reads combined source for main_window.py.

    Mixin methods live in _server_mixin.py / _stream_mixin.py; static tests
    that search main_window.py source now transparently include those files
    so all AST/regex guards remain valid after the split.
    """
    _MIXIN_FILES = ("_server_mixin.py", "_stream_mixin.py")

    def __init__(self, path: pathlib.Path) -> None:
        self._path = path

    def read_text(self, encoding: str = "utf-8") -> str:
        source = self._path.read_text(encoding=encoding)
        if self._path.name == "main_window.py":
            ui_dir = self._path.parent
            for mixin in self._MIXIN_FILES:
                p = ui_dir / mixin
                if p.exists():
                    source += "\n" + p.read_text(encoding=encoding)
        return source

    def __truediv__(self, other):
        return _CombinedPath(self._path / other)

    def __getattr__(self, name):
        return getattr(self._path, name)


def _get_ui_path(filename: str) -> _CombinedPath:
    return _CombinedPath(
        pathlib.Path(__file__).resolve().parent.parent.parent
        / "bellbird"
        / "ui"
        / filename
    )


def _get_func_name(node: ast.Call) -> str:
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
    if isinstance(node, ast.Attribute):
        return f"{_get_attr_name(node.value)}.{node.attr}"
    elif isinstance(node, ast.Name):
        return node.id
    return "<unknown>"


def _get_payload_func() -> tuple[ast.FunctionDef, ast.AST]:
    payload_path = (
        pathlib.Path(__file__).resolve().parent.parent.parent
        / "bellbird" / "core" / "payload.py"
    )
    tree = ast.parse(payload_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "build_options":
            return node, tree
    raise AssertionError("build_options not found in core/payload.py")


# ─── Basic structure ──────────────────────────────────────────────────────────


def test_import_only():
    """Module can be parsed without wx instantiation."""
    ast.parse(_get_ui_path("main_window.py").read_text(encoding="utf-8"))


def test_menus_structure():
    """Menus Archivo, Servidor, and Ayuda with expected items present."""
    source = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    found_strings: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found_strings.add(node.value)

    expected = {
        "Nueva conversación", "Abrir", "Guardar", "Salir",
        "Acerca de", "Atajos de teclado",
    }
    missing = [k for k in expected if not any(k in s for s in found_strings)]
    assert not missing, f"Menu items missing in source: {missing}"

    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_build_menu":
            method = node
            break
    assert method is not None, "_build_menu not found"
    src_lines = source.splitlines()
    method_src = "\n".join(src_lines[method.lineno - 1:method.end_lineno])
    assert "Servidor" in method_src, "Servidor menu missing from _build_menu"


def test_restart_server_button_present():
    """A 'Reiniciar servidor' button with name=restart_server_button is built."""
    source = _get_ui_path("main_window.py").read_text(encoding="utf-8")
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

    assert found_start, "No wx.Button with name='restart_server_button' found in source"
    assert found_stop, "No wx.Button with name='stop_server_button' found in source"


def test_start_server_handler_invokes_runner():
    """_on_start_server calls start_server from bellbird.core.llama_runner."""
    source = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    assert "from bellbird.core.llama_runner import" in source
    assert "from bellbird.core.llama_client import LlamaClient" in source
    assert "start_server(" in source
    assert "stop_server()" in source


def test_use_model_button():
    """use_model_button has name=, is disabled initially, and enabled when models load."""
    source = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    assert 'name="use_model_button"' in source or "name='use_model_button'" in source
    assert "use_model_button.Disable()" in source
    assert "use_model_button.Enable()" in source or "use_model_button.Enable" in source


def test_winsound_imported_inside_function():
    """winsound is imported inside _maybe_beep, not at module level."""
    source = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    assert "import winsound" in source
    lines = source.splitlines()
    winsound_line = next((i for i, l in enumerate(lines) if "import winsound" in l), None)
    func_line = next((i for i, l in enumerate(lines) if "def _maybe_beep" in l), None)
    assert winsound_line is not None, "import winsound not found"
    assert func_line is not None, "_maybe_beep method not found"
    assert winsound_line > func_line, "winsound import must be inside _maybe_beep"


# ─── Init ordering (regression guards) ───────────────────────────────────────


def test_config_loaded_in_init():
    """self._config = load_config() must come BEFORE self._client = LlamaClient(...).

    Regression for v0.4.1 verify-report CRITICAL-1.
    """
    source = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    config_assign_lineno: int | None = None
    llama_client_call_lineno: int | None = None

    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name == "__init__"):
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Assign):
                continue
            if (
                any(isinstance(t, ast.Attribute) and t.attr == "_config" for t in child.targets)
                and isinstance(child.value, ast.Call)
                and _get_func_name(child.value) == "load_config"
            ):
                config_assign_lineno = child.lineno
            if (
                any(isinstance(t, ast.Attribute) and t.attr == "_client" for t in child.targets)
                and isinstance(child.value, ast.Call)
                and _get_func_name(child.value) == "LlamaClient"
            ):
                llama_client_call_lineno = child.lineno

    assert config_assign_lineno is not None, "self._config = load_config() not found in __init__"
    assert llama_client_call_lineno is not None, "self._client = LlamaClient(...) not found in __init__"
    assert config_assign_lineno < llama_client_call_lineno, (
        f"self._config = load_config() (line {config_assign_lineno}) must come BEFORE "
        f"self._client = LlamaClient() (line {llama_client_call_lineno})"
    )


def test_init_passes_request_timeout_to_llama_client():
    """MainWindow.__init__ passes request_timeout= kwarg to LlamaClient()."""
    source = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "__init__":
            method = node
            break
    assert method is not None

    found = False
    for node in ast.walk(method):
        if isinstance(node, ast.Call) and _get_func_name(node) == "LlamaClient":
            for kw in node.keywords:
                if kw.arg == "request_timeout":
                    found = True
    assert found, "LlamaClient() must receive request_timeout= kwarg in __init__"


def test_init_startup_threading():
    """__init__ must NOT call sync startup functions directly; must call _start_probe_thread().

    Regression: direct calls block the window from showing.
    """
    source = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "__init__":
            method = node
            break
    assert method is not None

    forbidden = {"_startup_check", "check_running", "find_llama_server", "get_loaded_model", "_scan_models"}
    for node in ast.walk(method):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node)
            for f in forbidden:
                if f in func_name:
                    pytest.fail(f"__init__ must NOT call {f}() directly (blocks UI thread)")

    has_probe = any(
        isinstance(node, ast.Call) and _get_func_name(node) == "self._start_probe_thread"
        for node in ast.walk(method)
    )
    assert has_probe, "__init__ must call self._start_probe_thread()"


# ─── Close / server lifecycle (regression guards) ────────────────────────────


def test_on_close_sets_is_closing_after_confirm_not_before():
    """Regression B2: _is_closing = True must come AFTER the confirm dialog.

    If set before, clicking No leaves the flag stuck at True.
    """
    import re
    src = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    m = re.search(
        r"def _on_close\(self, event: wx\.CloseEvent\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_on_close not found"
    body = m.group(0)
    set_pos = body.find("self._is_closing = True")
    dlg_pos = body.find("wx.MessageDialog(")
    assert set_pos > 0, "self._is_closing = True not found"
    assert dlg_pos > 0, "wx.MessageDialog not found in _on_close"
    assert set_pos > dlg_pos, "_is_closing = True must come AFTER MessageDialog"


def test_model_load_worker_binds_defaults_before_try():
    """Regression B1: ok/message must be bound BEFORE the try block.

    Without defaults, an exception in start_server triggers
    UnboundLocalError in the finally block, silently locking the buttons.
    """
    import re
    src = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    m = re.search(
        r"def _model_load_worker\(self, model: str.*?\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_model_load_worker not found"
    body = m.group(0)
    ok_pos = body.find("ok = False")
    msg_pos = body.find('message = "Error: start_server raised')
    try_pos = body.find("try:")
    assert ok_pos > 0, "ok = False must be bound before try"
    assert msg_pos > 0, 'message = "Error..." must be bound before try'
    assert ok_pos < try_pos
    assert msg_pos < try_pos


def test_on_start_server_does_not_call_start_server_directly():
    """Regression BUG 2: _on_start_server must not block the main thread.

    Must delegate to _on_use_model (background thread).
    """
    source = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_on_start_server":
            method = node
            break
    assert method is not None

    for node in ast.walk(method):
        if isinstance(node, ast.Call):
            assert _get_func_name(node) != "start_server", (
                "_on_start_server must NOT call start_server() directly"
            )

    delegates = any(
        isinstance(node, ast.Call) and _get_func_name(node) == "self._on_use_model"
        for node in ast.walk(method)
    )
    assert delegates, "_on_start_server must delegate to self._on_use_model"


def test_on_start_server_done_calls_output_on_success():
    """_on_start_server_done calls self._speech.output in the success branch."""
    import re
    src = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    m = re.search(
        r"def _on_start_server_done\(self, ok: bool, message: str.*?\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_on_start_server_done not found"
    body = m.group(0)
    assert "self._speech.output(" in body
    ok_pos = body.find("if ok:")
    output_pos = body.find("self._speech.output(")
    assert output_pos > ok_pos, "output() must be inside the if ok: branch"


def test_on_usage_does_not_call_output():
    """_on_usage must NOT call _speech.output (would spam braille display)."""
    import re
    src = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    m = re.search(
        r"def _on_usage\(self, usage: dict\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_on_usage not found"
    body = m.group(0)
    assert "self._speech.output(" not in body
    assert "self._speech.announce_token_chunk" not in body


# ─── Stream callback safety (race condition guards) ───────────────────────────


def test_callbacks_guard_on_is_generating():
    """Regression BUG 1 race: stream callbacks must check _is_generating on entry."""
    source = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    for method_name in ("_on_token", "_on_done", "_on_error"):
        method = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == method_name:
                method = node
                break
        assert method is not None, f"{method_name} not found"

        exec_stmts = []
        for stmt in method.body:
            if (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)
                    and isinstance(stmt.value.value, str)):
                continue
            exec_stmts.append(stmt)
            if len(exec_stmts) == 2:
                break

        found = any(
            isinstance(stmt, ast.If)
            and "_is_generating" in ast.dump(stmt.test)
            and len(stmt.body) == 1
            and isinstance(stmt.body[0], ast.Return)
            for stmt in exec_stmts
        )
        assert found, (
            f"{method_name} must have an 'if not self._is_generating: return' guard "
            f"among the first 2 executable statements"
        )


def test_send_message_guards_on_is_generating():
    """Regression: send_message must return early if _is_generating is True."""
    source = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "send_message":
            method = node
            break
    assert method is not None

    exec_stmts = []
    for stmt in method.body:
        if (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)
                and isinstance(stmt.value.value, str)):
            continue
        exec_stmts.append(stmt)
        if len(exec_stmts) == 2:
            break

    found_guard = any(
        isinstance(stmt, ast.If)
        and "_is_generating" in ast.dump(stmt.test)
        and any(isinstance(s, ast.Return) for s in stmt.body)
        for stmt in exec_stmts
    )
    assert found_guard, "send_message must have an _is_generating early-return guard"


# ─── Conversation lifecycle ───────────────────────────────────────────────────


def test_new_conversation_calls_abort():
    """Regression BUG 1: new_conversation must abort the active stream."""
    source = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "new_conversation":
            method = node
            break
    assert method is not None, "new_conversation not found"

    has_abort = any(
        isinstance(node, ast.Call) and _get_func_name(node) == "self._client.abort"
        for node in ast.walk(method)
    )
    assert has_abort, "new_conversation must call self._client.abort()"


def test_new_conversation_has_confirmation():
    """new_conversation must confirm before discarding messages."""
    import re
    source = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    m = re.search(
        r"def new_conversation\(self\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        source, re.DOTALL,
    )
    assert m is not None, "new_conversation not found"
    body = m.group(0)
    assert "wx.MessageDialog(" in body
    assert "wx.YES_NO" in body
    assert "wx.NO_DEFAULT" in body
    assert "self._config.confirm_new_conversation" in body


# ─── Accessibility rules ──────────────────────────────────────────────────────


def test_maybe_beep_guards_on_screen_reader():
    """_maybe_beep: screen-reader guard must come AFTER platform check, BEFORE Beep."""
    import re
    src = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    m = re.search(
        r"def _maybe_beep\(self\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_maybe_beep not found"
    body = m.group(0)
    platform_pos = body.find('if sys.platform != "win32":')
    sr_pos = body.find("self._speech.is_screen_reader_active()")
    beep_pos = body.find("winsound.Beep")
    assert platform_pos >= 0 and sr_pos >= 0 and beep_pos >= 0
    assert sr_pos > platform_pos, "SR guard must come after platform check"
    assert sr_pos < beep_pos, "SR guard must come before Beep"
    sr_return = body.find(
        "if self._speech.is_screen_reader_active():\n            return"
    )
    assert sr_return >= 0, "SR guard must be an early-return pattern"


def test_dialogs_speak_after_show_modal():
    """_on_error, _show_about, _show_shortcuts: speak AFTER ShowModal."""
    import re
    src = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    for method_name in ("_on_error", "_show_about", "_show_shortcuts"):
        m = re.search(
            rf"def {method_name}\(self.*?\) -> None:.*?"
            r"(?=\n    def |\nclass |\Z)",
            src, re.DOTALL,
        )
        assert m is not None, f"{method_name} not found"
        body = m.group(0)
        speak_pos = body.rfind("self._speech.speak(")
        modal_pos = body.rfind("ShowModal()")
        assert speak_pos >= 0 and modal_pos >= 0
        assert speak_pos > modal_pos, (
            f"{method_name}: speak() must appear AFTER ShowModal() to avoid double announcement"
        )


def test_startup_probe_done_speaks_before_modal():
    """_on_startup_probe_done: speak BEFORE ShowModal (intentional pre-alert)."""
    import re
    src = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    m = re.search(r"def _on_startup_probe_done\(self.*?\n    def ", src, re.DOTALL)
    assert m is not None, "_on_startup_probe_done not found"
    body = m.group(0)
    speak_pos = body.find("self._speech.speak(")
    modal_pos = body.find("ShowModal()")
    assert speak_pos >= 0 and modal_pos >= 0
    assert speak_pos < modal_pos, "_on_startup_probe_done: speak must be BEFORE ShowModal"


def test_restart_dialog_uses_wx_dialog_not_message_dialog():
    """Restart dialog uses wx.Dialog with named buttons (not MessageDialog)."""
    src = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    assert "wx.Dialog(" in src
    assert 'name="server_down_dialog"' in src
    assert 'name="restart_yes_button"' in src
    assert 'name="restart_no_button"' in src


def test_model_selector_accessible():
    """model_selector is a CB_READONLY ComboBox; no EVT_TEXT binding."""
    source = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _get_func_name(node) == "wx.ComboBox":
            for kw in node.keywords:
                if kw.arg == "name" and isinstance(kw.value, ast.Constant) and kw.value.value == "Selector de modelo":
                    found = True
                if kw.arg == "style":
                    style_src = ast.unparse(kw.value)
                    assert "CB_READONLY" in style_src, f"model_selector must be CB_READONLY; got {style_src}"
    assert found, "model_selector (wx.ComboBox name='Selector de modelo') not found"

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_on_model_text_change":
            pytest.fail("_on_model_text_change must be removed (combo is read-only)")
    assert "EVT_TEXT" not in source, "EVT_TEXT must not be bound for a read-only combo"


def test_set_models_reselects_last_model():
    """set_models uses FindString to reselect the previously loaded model."""
    source = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "set_models":
            method = node
            break
    assert method is not None, "set_models not found"
    src_lines = source.splitlines()
    method_src = "\n".join(src_lines[method.lineno - 1:method.end_lineno])
    assert "FindString" in method_src
    assert "last_model" in method_src


def test_f6_cycle_structure():
    """_on_f6_cycle references restart_server_button and self.model_selector (not params_panel)."""
    source = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_on_f6_cycle":
            method = node
            break
    assert method is not None, "_on_f6_cycle not found"
    src_lines = source.splitlines()
    method_src = "\n".join(src_lines[method.lineno - 1:method.end_lineno])
    assert "restart_server_button" in method_src
    assert "self.model_selector" in method_src
    assert "self.params_panel.model_selector" not in method_src


# ─── Tool-calling invariants ──────────────────────────────────────────────────


def test_permission_manager_initialized():
    """MainWindow.__init__ initializes self._permission_manager = PermissionManager()."""
    source = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "__init__":
            for child in ast.walk(node):
                if (isinstance(child, ast.Assign)
                        and any(isinstance(t, ast.Attribute) and t.attr == "_permission_manager" for t in child.targets)
                        and isinstance(child.value, ast.Call)
                        and _get_func_name(child.value) == "PermissionManager"):
                    found = True
    assert found, "self._permission_manager = PermissionManager() not found in __init__"


def test_tool_executor_initialized():
    """MainWindow.__init__ initializes self._tool_executor = ToolExecutor()."""
    source = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "__init__":
            for child in ast.walk(node):
                if (isinstance(child, ast.Assign)
                        and any(isinstance(t, ast.Attribute) and t.attr == "_tool_executor" for t in child.targets)
                        and isinstance(child.value, ast.Call)
                        and _get_func_name(child.value) == "ToolExecutor"):
                    found = True
    assert found, "self._tool_executor = ToolExecutor() not found in __init__"


def test_shell_tool_definition_in_catalog():
    """SHELL_TOOL is defined at module level in core/tool_catalog.py."""
    catalog_path = (
        pathlib.Path(__file__).resolve().parent.parent.parent
        / "bellbird" / "core" / "tool_catalog.py"
    )
    source = catalog_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    found = any(
        (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "SHELL_TOOL" for t in n.targets))
        or (isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id == "SHELL_TOOL")
        for n in tree.body
    )
    assert found, "SHELL_TOOL must be defined at module level in core/tool_catalog.py"


def test_on_tool_result_passes_tool_call_id_to_add_message():
    """Regression CRITICAL-1: _on_tool_result must persist tool_call_id on tool message."""
    import re
    src = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    m = re.search(
        r"def _on_tool_result\(self, result, tool_call_id: str.*?\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_on_tool_result not found"
    body = m.group(0)
    add_msg_tool = re.search(r'self\._conversation\.add_message\(\s*"tool"', body)
    assert add_msg_tool is not None, "_on_tool_result must call add_message for role 'tool'"
    tool_add_end = body.find(")", add_msg_tool.start())
    tool_call = body[add_msg_tool.start():tool_add_end + 1]
    assert "tool_call_id" in tool_call and "tool_call_id=" in tool_call


def test_iteration_guard_check_in_continue():
    """_continue_after_tool increments counter and checks max_tool_iterations."""
    import re
    src = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    m = re.search(
        r"def _continue_after_tool\(self\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_continue_after_tool not found"
    body = m.group(0)
    assert "max_tool_iterations" in body
    assert "_tool_iteration_count" in body
    assert "return" in body


def test_assistant_tool_calls_inserted_in_on_tool_result():
    """_on_tool_result inserts assistant message with tool_calls before tool message."""
    import re
    src = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    m = re.search(
        r"def _on_tool_result\(self, result, tool_call_id: str.*?\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_on_tool_result not found"
    body = m.group(0)
    assert "add_message(" in body and "assistant" in body
    assert "tool_calls" in body
    assert '"id": tool_call_id' in body
    assert '"type": "function"' in body
    assert '"name": tool_name' in body
    assert 'json.dumps({"command": command})' in body


def test_send_message_gates_on_check_tool_support():
    """Tool support is probed in send_message prep; _continue_send gates on result."""
    import re
    src = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    send_m = re.search(r"def send_message\(self\) -> None:.*?(?=\n    def |\nclass |\Z)", src, re.DOTALL)
    assert send_m is not None, "send_message not found"
    assert "check_tool_support" in send_m.group(0)
    cont_m = re.search(r"def _continue_send\(.*?(?=\n    def |\nclass |\Z)", src, re.DOTALL)
    assert cont_m is not None, "_continue_send not found"
    assert "tools = None" in cont_m.group(0) or "tools=None" in cont_m.group(0)


def test_send_message_guards_on_tool_executing():
    """send_message early-return guard checks _tool_executing (race condition)."""
    import re
    src = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    m = re.search(r"def send_message\(self\).*?(?=\n    def |\nclass |\Z)", src, re.DOTALL)
    assert m is not None, "send_message not found"
    assert "_tool_executing" in m.group(0)


def test_on_tool_call_sets_tool_executing():
    """_on_tool_call sets _tool_executing = True as its first statement."""
    import re
    src = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    m = re.search(
        r"def _on_tool_call\(self, tool_name.*?\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_on_tool_call not found"
    assert "self._tool_executing = True" in m.group(0)


def test_on_tool_result_clears_tool_executing():
    """_on_tool_result clears _tool_executing = False before any guard."""
    import re
    src = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    m = re.search(
        r"def _on_tool_result\(self, result, tool_call_id: str.*?\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_on_tool_result not found"
    body = m.group(0)
    assert "self._tool_executing = False" in body
    false_pos = body.find("self._tool_executing = False")
    aborted_pos = body.find("self._aborted")
    assert false_pos < aborted_pos, "_tool_executing = False must appear before _aborted guard"


def test_on_done_skips_save_when_tool_executing():
    """_on_done checks _tool_executing before saving assistant message (race condition)."""
    import re
    src = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    m = re.search(r"def _on_done\(self\) -> None:.*?(?=\n    def |\nclass |\Z)", src, re.DOTALL)
    assert m is not None, "_on_done not found"
    assert "_tool_executing" in m.group(0)


def test_grant_session_uses_get_risk():
    """grant_session must use dlg.get_risk() (post-edit risk), not original risk."""
    import re
    src = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    m = re.search(
        r"def _on_tool_call\(self, tool_name.*?\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_on_tool_call not found"
    assert "dlg.get_risk()" in m.group(0)


def test_post_tool_speech_no_consultando():
    """_on_tool_result speech must NOT contain 'Consultando al modelo'."""
    import re
    src = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    m = re.search(
        r"def _on_tool_result\(self, result, tool_call_id: str.*?\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_on_tool_result not found"
    body = m.group(0)
    assert "Consultando al modelo" not in body
    assert "código" in body, "_on_tool_result must contain exit code feedback"
    assert "self._speech.speak" in body


def test_abort_generation_calls_speech_stop_and_clear_buffer():
    """abort_generation: order must be abort → stop → clear_buffer."""
    source = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "abort_generation":
            method = node
            break
    assert method is not None

    calls = []
    for stmt in ast.walk(method):
        if isinstance(stmt, ast.Call):
            fn = _get_func_name(stmt)
            if fn in ("self._client.abort", "self._speech.stop", "self._speech.clear_buffer"):
                calls.append(fn)

    assert "self._client.abort" in calls
    assert "self._speech.stop" in calls
    assert "self._speech.clear_buffer" in calls
    abort_idx = calls.index("self._client.abort")
    stop_idx = calls.index("self._speech.stop")
    clear_idx = calls.index("self._speech.clear_buffer")
    assert abort_idx < stop_idx < clear_idx, f"Expected abort→stop→clear, got: {calls}"


def test_abort_generation_calls_tool_executor_cancel_before_client_abort():
    """abort_generation: tool_executor.cancel() must come before client.abort()."""
    source = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "abort_generation":
            method = node
            break
    assert method is not None

    cancel_line = -1
    abort_line = -1
    for node in ast.walk(method):
        if isinstance(node, ast.Call):
            fn = _get_func_name(node)
            if fn == "self._tool_executor.cancel":
                cancel_line = node.lineno
            if fn == "self._client.abort":
                abort_line = node.lineno

    assert cancel_line >= 0, "abort_generation must call self._tool_executor.cancel()"
    assert abort_line >= 0, "abort_generation must call self._client.abort()"
    assert cancel_line < abort_line, "tool_executor.cancel() must appear BEFORE client.abort()"


def test_on_tool_result_guards_result_cancelled():
    """_on_tool_result checks result.cancelled and returns before _continue_after_tool."""
    import re
    src = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    m = re.search(
        r"def _on_tool_result\(self, result, tool_call_id: str.*?\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_on_tool_result not found"
    body = m.group(0)
    assert "result.cancelled" in body
    cancelled_pos = body.find("result.cancelled")
    continue_pos = body.find("_continue_after_tool")
    return_in_cancelled = body.find("return", cancelled_pos, continue_pos)
    assert return_in_cancelled >= 0, "Must have a return in the result.cancelled branch"


# ─── Connection watchdog ──────────────────────────────────────────────────────


def test_on_error_has_connection_watchdog():
    """_on_error contains connection-error markers for the watchdog branch."""
    src = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    assert "ConnectionError" in src
    assert "_run_connection_watchdog" in src
    assert "_on_server_state_checked" in src


def test_on_server_state_checked_handles_dead_and_loading():
    """_on_server_state_checked handles 'dead' and 'loading' states."""
    import re
    src = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    m = re.search(
        r"def _on_server_state_checked\(.*?\) -> None:.*?(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, "_on_server_state_checked not found"
    body = m.group(0)
    assert 'if state == "dead":' in body
    assert 'elif state == "loading":' in body


# ─── Config / preferences ─────────────────────────────────────────────────────


def test_show_preferences_recreates_client_on_port_change():
    """_show_preferences must recreate self._client when the port changes."""
    import re
    source = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    m = re.search(
        r"def _show_preferences\(self\) -> None:.*?(?=\n    def |\nclass |\Z)",
        source, re.DOTALL,
    )
    assert m is not None, "_show_preferences not found"
    body = m.group(0)
    assert "self._client = LlamaClient(" in body
    assert "old_port" in body


def test_attached_text_included_in_user_msg():
    """send_message includes attached_text in user_msg content (CRIT-2 regression)."""
    source = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

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

    assert "get_attached_text()" in send_source or "attached_text" in send_source, (
        "send_message must reference get_attached_text()"
    )

    has_separate_add = False
    for node in ast.walk(send_method):
        if isinstance(node, ast.Call):
            func_name = _get_func_name(node)
            if "add_message" in func_name:
                for child in ast.walk(node):
                    if isinstance(child, ast.Constant) and isinstance(child.value, str):
                        if "Contenido del archivo adjuntado" in child.value:
                            has_separate_add = True

    assert not has_separate_add, (
        "Attached text must be in user_msg['content'], not a separate add_message call"
    )


# ─── Sampler options (payload) ────────────────────────────────────────────────


def test_params_from_config():
    """_continue_send calls build_options(self._config); payload.py wires all fields."""
    source = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_continue_send":
            method = node
            break
    assert method is not None, "_continue_send not found"

    calls_build_options = any(
        isinstance(node, ast.Call) and "build_options" in ast.unparse(node.func)
        for node in ast.walk(method)
    )
    assert calls_build_options, "_continue_send must call build_options()"

    has_inline = any(
        isinstance(node, ast.Dict)
        and "temperature" in [k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        and "max_tokens" in [k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        for node in ast.walk(method)
    )
    assert not has_inline, "_continue_send must NOT inline the options dict"

    payload_path = (
        pathlib.Path(__file__).resolve().parent.parent.parent
        / "bellbird" / "core" / "payload.py"
    )
    payload_tree = ast.parse(payload_path.read_text(encoding="utf-8"))
    build_func = next(
        (n for n in payload_tree.body if isinstance(n, ast.FunctionDef) and n.name == "build_options"),
        None,
    )
    assert build_func is not None, "build_options not found in core/payload.py"

    options_dict = None
    for node in ast.walk(build_func):
        if isinstance(node, ast.Dict):
            keys = [k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            if "temperature" in keys and "max_tokens" in keys:
                options_dict = node
                break
    assert options_dict is not None, "build_options must have a dict with temperature+max_tokens"

    field_map = {
        k.value: v
        for k, v in zip(options_dict.keys, options_dict.values)
        if isinstance(k, ast.Constant) and isinstance(k.value, str)
    }
    for field in ("temperature", "max_tokens", "top_p", "top_k", "repeat_penalty", "min_p"):
        assert field in field_map, f"build_options dict missing {field!r}"
        val = field_map[field]
        assert isinstance(val, ast.Attribute), f"build_options[{field!r}] must be an attribute access"
        inner = val.value
        assert isinstance(inner, ast.Name) and inner.id == "config", (
            f"build_options[{field!r}] must be config.{field}"
        )
        assert val.attr == field

    src_lines = source.splitlines()
    method_source = "\n".join(src_lines[method.lineno - 1:method.end_lineno])
    for forbidden in ("params_panel.get_params", "params_panel.get_system_prompt",
                      "params_panel.get_tools_enabled", "params_panel.set_system_prompt"):
        assert forbidden not in method_source, f"_continue_send must not call {forbidden}()"


def test_build_options_dict_contains_min_p():
    """build_options dict literal always includes min_p key."""
    func, _ = _get_payload_func()
    found_min_p = False
    for node in ast.walk(func):
        if isinstance(node, ast.Dict):
            keys = [k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            if "temperature" in keys and "max_tokens" in keys:
                found_min_p = "min_p" in keys
                break
    assert found_min_p, "build_options dict must include 'min_p'"


def test_build_options_seed_conditional():
    """build_options has 'if config.seed >= 0:' guard for seed key."""
    func, _ = _get_payload_func()
    has_guard = any(
        isinstance(node, ast.If) and "seed" in ast.unparse(node.test) and ">= 0" in ast.unparse(node.test)
        for node in ast.walk(func)
    )
    assert has_guard, "build_options must have 'if config.seed >= 0:' guard"


def test_build_options_stop_conditional():
    """build_options has 'if config.stop:' guard for stop key."""
    func, _ = _get_payload_func()
    has_guard = any(
        isinstance(node, ast.If) and ast.unparse(node.test) == "config.stop"
        for node in ast.walk(func)
    )
    assert has_guard, "build_options must have 'if config.stop:' guard"


def test_both_call_sites_use_build_options():
    """Both _continue_send and _continue_after_tool call build_options."""
    source = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    def _has_build_options(method_name: str) -> bool:
        for cls_node in ast.walk(tree):
            if not isinstance(cls_node, ast.ClassDef):
                continue
            for item in cls_node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return any(
                        isinstance(call, ast.Call) and "build_options" in ast.unparse(call.func)
                        for call in ast.walk(item)
                    )
        return False

    assert _has_build_options("_continue_send"), "_continue_send must call build_options()"
    assert _has_build_options("_continue_after_tool"), "_continue_after_tool must call build_options()"


def test_f2_includes_min_p():
    """_announce_session_status passes temperature/top_p/max_tokens to SessionSnapshot."""
    source = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "_announce_session_status":
                    method = item
    assert method is not None, "_announce_session_status not found"
    src_lines = source.splitlines()
    method_src = "\n".join(src_lines[method.lineno - 1:method.end_lineno])
    assert "SessionSnapshot(" in method_src
    assert "self._config.temperature" in method_src
    assert "self._config.top_p" in method_src
    assert "self._config.max_tokens" in method_src
    assert "format_status(" in method_src


# ─── F2 status ────────────────────────────────────────────────────────────────


def test_f2_uses_format_status():
    """_announce_session_status uses format_status + SessionSnapshot + status_toggles_as_set."""
    source = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    assert "format_status" in source
    assert "SessionSnapshot" in source
    assert "status_toggles_as_set" in source


# ─── Focus courtesy (D8) ──────────────────────────────────────────────────────


def test_focus_courtesy_only_when_user_still_on_placeholder():
    """_on_done must guard SetSelection with GetSelection equality check."""
    import re
    src = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    m = re.search(r"def _on_done\(self\) -> None:.*?(?=\n    def |\nclass |\Z)", src, re.DOTALL)
    assert m is not None, "_on_done not found"
    body = m.group(0)
    get_pos = body.find(".GetSelection()")
    set_pos = body.find(".SetSelection(")
    assert get_pos >= 0, "GetSelection() not in _on_done"
    assert set_pos >= 0, "SetSelection() not in _on_done"
    assert set_pos > get_pos
    assert "if " in body[get_pos:set_pos], "SetSelection must be inside a conditional"


# ─── Browser HTML viewer ──────────────────────────────────────────────────────


def test_open_message_in_browser_calls_render_message_html():
    """_open_message_in_browser delegates HTML generation to render_message_html."""
    src = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    method = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_open_message_in_browser"),
        None,
    )
    assert method is not None, "_open_message_in_browser not found"
    src_lines = src.splitlines()
    method_src = "\n".join(src_lines[method.lineno - 1:method.end_lineno])
    assert "render_message_html" in method_src


def test_open_message_in_browser_calls_webbrowser_open():
    """_open_message_in_browser calls webbrowser.open to show the HTML file."""
    src = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    method = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_open_message_in_browser"),
        None,
    )
    assert method is not None
    src_lines = src.splitlines()
    method_src = "\n".join(src_lines[method.lineno - 1:method.end_lineno])
    assert "webbrowser.open" in method_src


def test_open_message_in_browser_does_not_call_markdown():
    """_open_message_in_browser does NOT call markdown.markdown( directly."""
    src = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    method = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_open_message_in_browser"),
        None,
    )
    assert method is not None
    src_lines = src.splitlines()
    method_src = "\n".join(src_lines[method.lineno - 1:method.end_lineno])
    assert "markdown.markdown(" not in method_src


def test_open_message_in_browser_uses_named_temporary_file():
    """_open_message_in_browser uses NamedTemporaryFile to write HTML."""
    src = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    method = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_open_message_in_browser"),
        None,
    )
    assert method is not None
    src_lines = src.splitlines()
    method_src = "\n".join(src_lines[method.lineno - 1:method.end_lineno])
    assert "NamedTemporaryFile" in method_src


# ─── URL fetch feature ────────────────────────────────────────────────────────


def test_no_message_dialog_in_attach_url_paths():
    """_on_attach_url, _on_fetch_complete, _fetch_url_worker must use speech.speak, not MessageDialog."""
    import re
    src = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    for method_name in ("_on_attach_url", "_on_fetch_complete", "_fetch_url_worker"):
        m = re.search(
            rf"def {method_name}\(.*?\) -> None:.*?"
            r"(?=\n    def |\nclass |\Z)",
            src, re.DOTALL,
        )
        assert m is not None, f"{method_name} not found"
        assert "wx.MessageDialog" not in m.group(0), (
            f"{method_name} must NOT contain wx.MessageDialog"
        )


# ─── Vision support ───────────────────────────────────────────────────────────


def test_send_message_vision_guard():
    """send_message checks _vision_capable before building image payload."""
    source = _get_ui_path("main_window.py").read_text(encoding="utf-8")
    assert "not self._vision_capable" in source or (
        "self._vision_capable" in source and "attached_images" in source
    )
