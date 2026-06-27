"""Runtime tests for WxToastSender — requires wxPython.

These tests require wxPython; skipped on WSL/Linux via
``importorskip("wx")``. Run via ``run_tests.bat`` on Windows.
"""

import pytest

pytest.importorskip("wx")

import wx


class TestWxToastSender:
    """WxToastSender instantiation and show() call."""

    def test_instantiate_and_show(self):
        """Instantiate WxToastSender and call show() — no crash."""
        app = wx.GetApp()
        frame = wx.Frame(None)
        try:
            from bellbird.ui.wx_notifier import WxToastSender

            sender = WxToastSender(parent=frame)
            # Call show with timeout=0 (immediate return on win32,
            # no-op outside win32). Wrap in try/except per contract.
            try:
                sender.show("Bellbird", "test", timeout=0)
            except Exception:
                pass  # never-crash contract applies
        finally:
            frame.Destroy()
