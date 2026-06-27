"""Runtime tests for MessageDetailDialog — wx instantiation required (Windows only).

These tests require a wx application object and real wxPython.
They are skipped automatically on WSL/Linux via ``importorskip("wx")``.
Run via ``run_tests.bat`` on Windows.
"""

import pytest

pytest.importorskip("wx")

import wx


@pytest.fixture
def app():
    """Create a wx.App for the duration of each test."""
    app = wx.GetApp()
    yield app


class TestMessageDetailDialogRuntime:
    """Runtime tests for the reasoning section visibility."""

    def test_reasoning_text_visible_when_non_empty(self, app):
        """Dialog with non-empty reasoning shows reasoning_text."""
        from bellbird.ui.message_detail_dialog import MessageDetailDialog

        parent = wx.Frame(None)
        dlg = MessageDetailDialog(
            parent, "assistant", "Hello",
            reasoning="secret chain of thought",
        )
        try:
            assert hasattr(dlg, "reasoning_text"), (
                "Dialog with non-empty reasoning must have reasoning_text"
            )
            # Verify the text was set
            assert dlg.reasoning_text.GetValue() != "", (
                "reasoning_text should contain the reasoning content"
            )
        finally:
            dlg.Destroy()
        parent.Destroy()

    def test_reasoning_text_hidden_when_none(self, app):
        """Dialog with reasoning=None does NOT show reasoning_text."""
        from bellbird.ui.message_detail_dialog import MessageDetailDialog

        parent = wx.Frame(None)
        dlg = MessageDetailDialog(parent, "assistant", "Hello")
        try:
            assert not hasattr(dlg, "reasoning_text"), (
                "Dialog with reasoning=None should NOT have reasoning_text"
            )
        finally:
            dlg.Destroy()
        parent.Destroy()
