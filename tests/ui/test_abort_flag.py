"""Static/AST tests for the _aborted abort flag in MainWindow.

Covers Task 4 (attribute declaration) and Task 5 (abort flow ordering).

All tests parse bellbird/ui/main_window.py and verify structure via AST
and regex, without importing wx at module level.
"""

import ast
import re
from pathlib import Path


def _get_source() -> str:
    """Return combined source: main_window.py + server/stream mixins."""
    ui_dir = Path(__file__).resolve().parent.parent.parent / "bellbird" / "ui"
    parts = [ui_dir / "main_window.py", ui_dir / "_server_mixin.py", ui_dir / "_stream_mixin.py"]
    return "\n".join(p.read_text(encoding="utf-8") for p in parts if p.exists())


def _get_func_body(func_name: str, src: str) -> str:
    """Extract the full body of a method from main_window.py via regex."""
    m = re.search(
        rf"def {func_name}\(self.*?\) -> None:.*?"
        r"(?=\n    def |\nclass |\Z)",
        src, re.DOTALL,
    )
    assert m is not None, f"{func_name} not found in main_window.py"
    return m.group(0)


# ─── Task 4: attribute declared ──────────────────────────────────────────


def test_aborted_attr_declared_in_init() -> None:
    """MainWindow.__init__ declares self._aborted = False."""
    src = _get_source()
    tree = ast.parse(src)

    init_method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "__init__":
            init_method = node
            break

    assert init_method is not None, "__init__ not found"

    found = False
    for stmt in ast.walk(init_method):
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if (isinstance(target, ast.Attribute)
                        and target.attr == "_aborted"
                        and isinstance(stmt.value, ast.Constant)
                        and stmt.value.value is False):
                    found = True
                    break

    assert found, (
        "self._aborted = False must be declared in MainWindow.__init__"
    )


# ─── Task 5: abort flow ordering ───────────────────────────────────────


def test_abort_generation_sets_aborted_before_is_generating() -> None:
    """abort_generation sets self._aborted = True BEFORE self._is_generating = False.

    The order guarantees the flag is already raised by the time the
    stream worker's _on_done callback checks it.
    """
    src = _get_source()
    body = _get_func_body("abort_generation", src)

    # Find the positions of each assignment
    aborted_true = body.find("self._aborted = True")
    generating_false = body.find("self._is_generating = False")
    abort_call = body.find("self._client.abort()")

    assert aborted_true >= 0, (
        "abort_generation must set self._aborted = True"
    )
    assert generating_false >= 0, (
        "abort_generation must set self._is_generating = False"
    )
    assert abort_call >= 0, (
        "abort_generation must call self._client.abort()"
    )

    # Order: _aborted first, then _is_generating, then client.abort
    assert aborted_true < generating_false, (
        "self._aborted = True must appear BEFORE self._is_generating = False"
    )
    assert generating_false < abort_call, (
        "self._is_generating = False must appear BEFORE self._client.abort()"
    )


def test_on_done_aborted_guard_returns_early() -> None:
    """_on_done opens with `if self._aborted:` returning without saving."""
    src = _get_source()
    body = _get_func_body("_on_done", src)

    # First if should be _aborted check
    lines = [l.strip() for l in body.split("\n") if l.strip()]
    first_if = None
    for line in lines:
        if line.startswith("if "):
            first_if = line
            break
    assert first_if is not None, "_on_done has no if statement"
    assert "self._aborted" in first_if, (
        f"_on_done first if must check self._aborted, got: {first_if}"
    )
    assert "Generación detenida" in body, (
        "_on_done aborted path must speak 'Generación detenida'"
    )
    # _speech.speak("Respuesta completa") must NOT appear before the _aborted guard
    pre_aborted = body.split("self._aborted")[0]
    assert 'speak("Respuesta completa"' not in pre_aborted, (
        "_speech.speak('Respuesta completa') must NOT appear before "
        "the _aborted guard"
    )


def test_on_error_aborted_guard() -> None:
    """_on_error opens with `if self._aborted:`."""
    src = _get_source()
    body = _get_func_body("_on_error", src)

    assert "self._aborted" in body, (
        "_on_error must check self._aborted at the top"
    )

    # First if should be _aborted check
    lines = [l.strip() for l in body.split("\n") if l.strip()]
    first_if = None
    for line in lines:
        if line.startswith("if "):
            first_if = line
            break
    assert first_if is not None, "_on_error has no if statement"
    assert "self._aborted" in first_if, (
        f"_on_error first if must check self._aborted, got: {first_if}"
    )


def test_send_message_resets_aborted() -> None:
    """send_message resets self._aborted = False before the _is_generating guard."""
    src = _get_source()
    body = _get_func_body("send_message", src)

    assert "self._aborted = False" in body, (
        "send_message must reset self._aborted = False before starting "
        "the generation"
    )


def test_continue_after_tool_resets_aborted() -> None:
    """_continue_after_tool resets self._aborted = False before re-launch."""
    src = _get_source()
    body = _get_func_body("_continue_after_tool", src)

    assert "self._aborted = False" in body, (
        "_continue_after_tool must reset self._aborted = False before "
        "re-launching the chat stream"
    )
