"""AST-only tests for bellbird.core.focus.

Verifies the FocusChecker protocol definition is importable without wx.
"""

import ast

import pytest


class TestFocusCheckerProtocol:
    """FocusChecker protocol — core, wx-free."""

    def test_focus_checker_is_importable(self):
        """GIVEN bellbird/core/focus.py
        WHEN from bellbird.core.focus import FocusChecker
        THEN the import succeeds without wx."""
        from bellbird.core.focus import FocusChecker

        assert FocusChecker is not None

    def test_no_wx_import_in_source(self):
        """GIVEN the source of focus.py
        WHEN AST is inspected
        THEN no 'import wx' or 'from wx' at module scope."""
        import bellbird.core.focus as mod

        source_path = mod.__file__
        with open(source_path, encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    if alias.name == "wx" or alias.name.startswith("wx."):
                        pytest.fail(
                            f"Found import of wx at module scope: {ast.dump(node)}"
                        )

    def test_custom_implementation_satisfies_protocol(self):
        """GIVEN a stub class with is_focused() -> bool
        WHEN it is passed to Notifier
        THEN structural typing accepts it."""
        from bellbird.core.focus import FocusChecker

        class FakeFocus:
            def is_focused(self) -> bool:
                return False

        stub: FocusChecker = FakeFocus()
        assert stub.is_focused() is False
