"""Runtime tests for VoiceDialog — wx instantiation required (Windows only).

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


def _make_dialog(app, voices=None, current_voice="", current_rate=0):
    """Create a VoiceDialog, show it non-modally, return it for inspection."""
    if voices is None:
        voices = ["Voice A", "Voice B"]
    from bellbird.ui.voice_dialog import VoiceDialog

    dlg = VoiceDialog(None, voices, current_voice=current_voice, current_rate=current_rate)
    dlg.Show()  # non-blocking — avoids hanging on WSL
    return dlg


class TestVoiceDialog:
    """VoiceDialog: construction, initial state, control manipulation."""

    def test_dialog_constructs_and_shows(self, app) -> None:
        """Creating and showing the dialog does not crash."""
        dlg = _make_dialog(app)
        try:
            assert isinstance(dlg, wx.Dialog), (
                "VoiceDialog must be a wx.Dialog"
            )
            assert dlg.GetName() == "voice_dialog", (
                f"Expected name='voice_dialog', got {dlg.GetName()!r}"
            )
        finally:
            dlg.Destroy()

    def test_get_voice_returns_initial_value(self, app) -> None:
        """get_voice() returns the current_voice passed at construction."""
        dlg = _make_dialog(app, current_voice="Voice A")
        try:
            assert dlg.get_voice() == "Voice A", (
                f"Expected 'Voice A', got {dlg.get_voice()!r}"
            )
        finally:
            dlg.Destroy()

    def test_get_rate_returns_initial_value(self, app) -> None:
        """get_rate() returns the current_rate passed at construction."""
        dlg = _make_dialog(app, current_rate=3)
        try:
            assert dlg.get_rate() == 3, (
                f"Expected 3, got {dlg.get_rate()}"
            )
        finally:
            dlg.Destroy()

    def test_set_voice_then_get_returns_new_value(self, app) -> None:
        """Selecting a different voice updates get_voice()."""
        dlg = _make_dialog(app, voices=["Voice A", "Voice B"], current_voice="Voice A")
        try:
            choice = dlg.FindWindowByName("voice_choice")
            assert choice is not None, "voice_choice not found"
            choice.SetStringSelection("Voice B")
            assert dlg.get_voice() == "Voice B", (
                f"Expected 'Voice B', got {dlg.get_voice()!r}"
            )
        finally:
            dlg.Destroy()

    def test_set_rate_then_get_returns_new_value(self, app) -> None:
        """Changing the rate slider updates get_rate()."""
        dlg = _make_dialog(app, current_rate=0)
        try:
            slider = dlg.FindWindowByName("rate_slider")
            assert slider is not None, "rate_slider not found"
            slider.SetValue(7)
            assert dlg.get_rate() == 7, (
                f"Expected 7, got {dlg.get_rate()}"
            )
        finally:
            dlg.Destroy()
