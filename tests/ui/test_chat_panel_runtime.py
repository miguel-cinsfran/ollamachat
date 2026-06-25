"""Runtime tests for ChatPanel — wx instantiation required (Windows only).

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
    app = wx.App()
    yield app
    # wxPython cleanup is handled by ref-counting


@pytest.fixture
def panel(app):
    """Create a ChatPanel for testing."""
    from bellbird.ui.chat_panel import ChatPanel

    frame = wx.Frame(None)
    speech = None  # Speech mock — we only test visual widgets
    panel = ChatPanel(frame, speech)
    yield panel
    frame.Destroy()


class TestChatPanelRuntime:
    """Runtime tests that verify stream_display absence and streaming state."""

    def test_stream_display_absent(self, panel):
        """ChatPanel no longer has a stream_display attribute."""
        assert not hasattr(panel, "stream_display"), (
            "stream_display attribute must be removed"
        )

    def test_streaming_index_on_start_generation(self, panel):
        """start_generation sets _streaming_index to a valid int."""
        panel.start_generation()
        assert isinstance(panel._streaming_index, int), (
            f"_streaming_index should be int, got {type(panel._streaming_index)}"
        )
        assert panel._streaming_index >= 0

    def test_placeholder_on_start(self, panel):
        """start_generation appends '[IA] (generando…)' placeholder."""
        panel.start_generation()
        idx = panel._streaming_index
        text = panel.message_list.GetString(idx)
        assert text == "[IA] (generando…)", (
            f"Placeholder text mismatch: {text!r}"
        )


# ─── FakeSpeech helper ──────────────────────────────────────────────────────


class FakeSpeech:
    """Minimal speech stub for testing select_and_announce_message."""
    def __init__(self):
        self.last_message = ""
        self.messages: list[str] = []

    def speak(self, text: str, interrupt: bool = False) -> None:
        self.last_message = text
        self.messages.append(text)


class TestSelectAndAnnounce:
    """ChatPanel.select_and_announce_message selects, focuses, and speaks."""

    def test_select_and_announce_sets_selection_and_focus(self, panel):
        """GIVEN history with messages
        WHEN select_and_announce_message with valid index
        THEN SetSelection and SetFocus are called."""
        panel._history = [("user", "Hola"), ("assistant", "Mundo")]
        panel.message_list.Append("[Tú] Hola")
        panel.message_list.Append("[IA] Mundo")
        panel.select_and_announce_message(1)
        assert panel.message_list.GetSelection() == 1
        assert panel.message_list.HasFocus()

    def test_select_and_announce_speaks_content(self, panel):
        """GIVEN history with messages
        WHEN select_and_announce_message with valid index
        THEN speech.speak is called with the full message text."""
        panel._history = [("user", "Hola"), ("assistant", "Mundo")]
        panel.message_list.Append("[Tú] Hola")
        panel.message_list.Append("[IA] Mundo")
        panel._speech = FakeSpeech()
        panel.select_and_announce_message(1)
        assert panel._speech.last_message == "Mundo"

    def test_select_and_announce_speech_failure_no_crash(self, panel):
        """GIVEN speech.speak raises an exception
        WHEN select_and_announce_message is called
        THEN no exception propagates (never-crash contract)."""
        class BrokenSpeech:
            def speak(self, text, interrupt=False):
                raise RuntimeError("TTS failure")

        panel._history = [("user", "Hola")]
        panel.message_list.Append("[Tú] Hola")
        panel._speech = BrokenSpeech()
        # Must not raise
        panel.select_and_announce_message(0)

    def test_select_and_announce_out_of_range_noop(self, panel):
        """GIVEN index out of range
        WHEN select_and_announce_message is called
        THEN selection remains unchanged (silent no-op)."""
        panel._history = [("user", "Hola")]
        panel.message_list.Append("[Tú] Hola")
        panel.message_list.SetSelection(0)
        panel.select_and_announce_message(5)
        assert panel.message_list.GetSelection() == 0
