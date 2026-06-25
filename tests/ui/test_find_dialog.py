"""Runtime tests for FindDialog — wx instantiation required (Windows only).

These tests require wxPython; skipped on WSL/Linux via
``importorskip("wx")``. Run via ``run_tests.bat`` on Windows.
"""

import pytest

pytest.importorskip("wx")

import wx


def _make_dialog():
    """Create a FindDialog for testing."""
    from bellbird.ui.find_dialog import FindDialog

    app = wx.App()
    parent = wx.Frame(None)
    dlg = FindDialog(parent)
    return app, parent, dlg


class TestFindDialog:
    """FindDialog accessibility and API tests."""

    def test_find_dialog_instantiates(self):
        """FindDialog can be created without errors."""
        app, parent, dlg = _make_dialog()
        try:
            assert hasattr(dlg, "find_text"), "find_text attribute missing"
            assert hasattr(dlg, "find_next"), "find_next button missing"
            assert hasattr(dlg, "find_prev"), "find_prev button missing"
            assert hasattr(dlg, "close_btn"), "close_btn button missing"
        finally:
            dlg.Destroy()
            parent.Destroy()

    def test_find_dialog_focus_on_textctrl(self):
        """On creation, focus is set to the search TextCtrl."""
        app, parent, dlg = _make_dialog()
        try:
            assert dlg.find_text.HasFocus(), (
                "FindDialog must set focus to find_text on creation"
            )
        finally:
            dlg.Destroy()
            parent.Destroy()

    def test_find_dialog_get_query(self):
        """get_query returns the current text from the TextCtrl."""
        app, parent, dlg = _make_dialog()
        try:
            dlg.find_text.SetValue("test query")
            assert dlg.get_query() == "test query"
        finally:
            dlg.Destroy()
            parent.Destroy()

    def test_find_dialog_get_query_empty_default(self):
        """get_query returns empty string when the TextCtrl is empty."""
        app, parent, dlg = _make_dialog()
        try:
            assert dlg.get_query() == ""
        finally:
            dlg.Destroy()
            parent.Destroy()

    def test_find_dialog_set_on_find_fires_next(self):
        """set_on_find callback fires with +1 for 'Buscar siguiente'."""
        app, parent, dlg = _make_dialog()
        try:
            results = []
            dlg.set_on_find(lambda direction: results.append(direction))
            dlg._fire_callback(1)
            assert results == [1], f"Expected [1], got {results}"
        finally:
            dlg.Destroy()
            parent.Destroy()

    def test_find_dialog_set_on_find_fires_prev(self):
        """set_on_find callback fires with -1 for 'Buscar anterior'."""
        app, parent, dlg = _make_dialog()
        try:
            results = []
            dlg.set_on_find(lambda direction: results.append(direction))
            dlg._fire_callback(-1)
            assert results == [-1], f"Expected [-1], got {results}"
        finally:
            dlg.Destroy()
            parent.Destroy()

    def test_find_dialog_close_button_exists(self):
        """Close button has correct label and is a native wx.Button."""
        app, parent, dlg = _make_dialog()
        try:
            assert dlg.close_btn.GetLabel() == "Cerrar"
            assert isinstance(dlg.close_btn, wx.Button)
        finally:
            dlg.Destroy()
            parent.Destroy()

    def test_find_dialog_button_labels(self):
        """Find buttons have correct Spanish labels."""
        app, parent, dlg = _make_dialog()
        try:
            assert dlg.find_next.GetLabel() == "Buscar siguiente"
            assert dlg.find_prev.GetLabel() == "Buscar anterior"
        finally:
            dlg.Destroy()
            parent.Destroy()
