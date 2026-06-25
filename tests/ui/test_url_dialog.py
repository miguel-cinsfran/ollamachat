"""Runtime tests for URLDialog — wx instantiation required (Windows only).

These tests require a wx application object and real wxPython.
They are skipped automatically on WSL/Linux via ``importorskip("wx")``.
Run via ``run_tests.bat`` on Windows.
"""

import pytest

pytest.importorskip("wx")

import wx


@pytest.fixture(scope="module")
def app():
    """Create a wx.App for the test module."""
    return wx.App()


class TestURLDialog:
    """URLDialog: instantiation, focus, get_url, close behavior."""

    def test_url_dialog_instantiates(self, app) -> None:
        """Creating and showing the dialog does not crash."""
        from bellbird.ui.url_dialog import URLDialog

        dlg = URLDialog(None)
        try:
            assert isinstance(dlg, wx.Dialog), (
                "URLDialog must be a wx.Dialog"
            )
            assert dlg.GetTitle() == "Adjuntar URL", (
                f"Expected 'Adjuntar URL', got {dlg.GetTitle()!r}"
            )
            assert dlg.GetName() == "url_dialog", (
                f"Expected name='url_dialog', got {dlg.GetName()!r}"
            )
        finally:
            dlg.Destroy()

    def test_url_dialog_focus_on_textctrl(self, app) -> None:
        """When dialog opens, focus is on the URL TextCtrl."""
        from bellbird.ui.url_dialog import URLDialog

        dlg = URLDialog(None)
        try:
            focused = dlg.FindFocus()
            assert focused == dlg.url_input, (
                f"Focus should be on url_input, got {focused}"
            )
        finally:
            dlg.Destroy()

    def test_url_dialog_get_url(self, app) -> None:
        """get_url returns the text content, stripped."""
        from bellbird.ui.url_dialog import URLDialog

        dlg = URLDialog(None)
        try:
            dlg.url_input.SetValue("  https://example.com  ")
            assert dlg.get_url() == "https://example.com", (
                f"Expected 'https://example.com', got {dlg.get_url()!r}"
            )
        finally:
            dlg.Destroy()

    def test_url_dialog_get_url_empty(self, app) -> None:
        """Empty input returns empty string."""
        from bellbird.ui.url_dialog import URLDialog

        dlg = URLDialog(None)
        try:
            assert dlg.get_url() == "", (
                f"Expected empty string, got {dlg.get_url()!r}"
            )
        finally:
            dlg.Destroy()

    def test_url_dialog_close_destroys(self, app) -> None:
        """ShowModal + Destroy works without error."""
        from bellbird.ui.url_dialog import URLDialog

        dlg = URLDialog(None)
        result = dlg.ShowModal()
        dlg.Destroy()
        # Just checking no crash — result can be ID_CANCEL if Escape
        assert result in (wx.ID_OK, wx.ID_CANCEL), (
            f"ShowModal returned unexpected result: {result}"
        )

    def test_url_dialog_buttons_have_names(self, app) -> None:
        """Buttons have correct name attributes."""
        from bellbird.ui.url_dialog import URLDialog

        dlg = URLDialog(None)
        try:
            assert dlg.attach_btn.GetName() == "url_attach_button", (
                f"Expected 'url_attach_button', got {dlg.attach_btn.GetName()!r}"
            )
            assert dlg.cancel_btn.GetName() == "url_cancel_button", (
                f"Expected 'url_cancel_button', got {dlg.cancel_btn.GetName()!r}"
            )
        finally:
            dlg.Destroy()
