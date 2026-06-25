"""Static/AST tests for bellbird/core/html_render.py — no wx in new code.

Tests verify that the module does not import wx, reference WebView,
HtmlWindow, or RichTextCtrl/richtext, and does use the markdown library.
"""

import ast
import pathlib


def _get_core_path(filename: str) -> pathlib.Path:
    return (
        pathlib.Path(__file__).resolve().parent.parent.parent
        / "bellbird"
        / "core"
        / filename
    )


def test_no_wx_import():
    """bellbird/core/html_render.py does NOT contain 'import wx'."""
    source_path = _get_core_path("html_render.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "wx", (
                    "html_render.py must NOT import wx at module level"
                )
        if isinstance(node, ast.ImportFrom):
            assert node.module != "wx", (
                "html_render.py must NOT import from wx"
            )


def test_no_webview():
    """bellbird/core/html_render.py does NOT contain 'WebView'."""
    source_path = _get_core_path("html_render.py")
    source = source_path.read_text(encoding="utf-8")
    assert "WebView" not in source, (
        "html_render.py must NOT reference WebView"
    )


def test_no_htmlwindow():
    """bellbird/core/html_render.py does NOT contain 'HtmlWindow'."""
    source_path = _get_core_path("html_render.py")
    source = source_path.read_text(encoding="utf-8")
    assert "HtmlWindow" not in source, (
        "html_render.py must NOT reference HtmlWindow"
    )


def test_no_richtext():
    """bellbird/core/html_render.py does NOT contain 'RichTextCtrl' or 'richtext'."""
    source_path = _get_core_path("html_render.py")
    source = source_path.read_text(encoding="utf-8")
    assert "RichTextCtrl" not in source, (
        "html_render.py must NOT reference RichTextCtrl"
    )
    assert "richtext" not in source, (
        "html_render.py must NOT reference richtext"
    )


def test_uses_markdown_library():
    """bellbird/core/html_render.py DOES import markdown and call markdown.markdown()."""
    source_path = _get_core_path("html_render.py")
    source = source_path.read_text(encoding="utf-8")
    assert "import markdown" in source, (
        "html_render.py must import the markdown library"
    )
    assert "markdown.markdown(" in source, (
        "html_render.py must call markdown.markdown()"
    )
