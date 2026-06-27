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
    app = wx.GetApp()
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


class TestEmptyHint:
    """The empty-list hint row prevents NVDA reading 'desconocido' and keeps
    the message_list-index == _history-index invariant for real rows."""

    def test_hint_shown_on_empty_construction(self, panel):
        assert panel._hint_shown is True
        assert panel.message_list.GetCount() == 1
        assert len(panel._history) == 0
        assert "vacía" in panel.message_list.GetString(0).lower()

    def test_hint_dropped_on_first_user_message(self, panel):
        panel.append_user_message("Hola")
        assert panel._hint_shown is False
        assert panel.message_list.GetCount() == 1
        assert len(panel._history) == 1
        # Real row at index 0 — invariant intact
        assert panel.message_list.GetString(0).startswith("[Tú]")

    def test_hint_dropped_on_start_generation_keeps_streaming_index(self, panel):
        panel.start_generation()
        assert panel._hint_shown is False
        # Streaming index must point at the actual streaming row
        assert panel.message_list.GetString(panel._streaming_index) == "[IA] (generando…)"

    def test_hint_returns_after_clear(self, panel):
        panel.append_user_message("Hola")
        panel.clear()
        assert panel._hint_shown is True
        assert panel.message_list.GetCount() == 1
        assert len(panel._history) == 0

    def test_hint_returns_after_deleting_only_message(self, panel):
        panel._speech = FakeSpeech()  # _on_context_delete speaks on success
        panel.append_user_message("Hola")
        panel.message_list.SetSelection(0)
        panel._on_context_delete()
        assert panel._hint_shown is True
        assert len(panel._history) == 0
        assert panel.message_list.GetCount() == 1

    def test_delete_on_hint_row_is_noop(self, panel):
        # Land selection on the hint row and press delete — must not crash
        # (the guard returns before reaching speech)
        panel.message_list.SetSelection(0)
        panel._on_context_delete()
        assert len(panel._history) == 0
        assert panel._hint_shown is True

    def test_hint_not_in_get_history(self, panel):
        # The hint is UI-only and must never leak into saved sessions
        assert panel.get_history() == []


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


class TestAttachUrl:
    """ChatPanel.attach_url behavior."""

    def test_attach_url_sets_attached_text(self, panel):
        """attach_url sets _attached_text to the given text."""
        panel._attached_text = None
        panel._attached_images = []
        panel.attach_url("https://e.com", "Hello world", "e.com")
        assert panel._attached_text == "Hello world", (
            f"Expected 'Hello world', got {panel._attached_text!r}"
        )

    def test_attach_url_updates_label(self, panel):
        """attach_url updates attachment_label with origin_label."""
        panel._attached_text = None
        panel._attached_images = []
        panel.attach_url("https://e.com", "Hello", "Example (example.com)")
        assert panel.attachment_label.GetLabel() == "Example (example.com)", (
            f"Expected 'Example (example.com)', got "
            f"{panel.attachment_label.GetLabel()!r}"
        )

    def test_attach_url_empty_text_noop(self, panel):
        """Empty text does not modify _attached_text."""
        panel._attached_text = "existing"
        panel.attach_url("https://e.com", "", "e.com")
        assert panel._attached_text == "existing", (
            f"Expected 'existing' unchanged, got {panel._attached_text!r}"
        )

    def test_attach_url_replaces_image_with_speech(self, panel):
        """When images are attached, attach_url clears them and speaks."""
        panel._attached_images = [("base64data", "image/png")]
        panel._attached_text = None

        class FakeSpeech:
            def __init__(self):
                self.messages = []
            def speak(self, text, interrupt=False):
                self.messages.append(text)

        panel._speech = FakeSpeech()
        panel.attach_url("https://e.com", "text", "e.com")
        assert panel._attached_images == [], (
            f"Expected empty _attached_images, got {panel._attached_images}"
        )
        assert panel._attached_text == "text", (
            f"Expected 'text', got {panel._attached_text!r}"
        )
        assert "Imagen reemplazada" in panel._speech.messages, (
            f"Expected 'Imagen reemplazada' to be spoken, got "
            f"{panel._speech.messages!r}"
        )

    def test_attach_url_clears_images_no_speech_when_no_images(self, panel):
        """When no images attached, attach_url does not speak."""
        panel._attached_images = []
        panel._attached_text = None

        class FakeSpeech:
            def __init__(self):
                self.messages = []
            def speak(self, text, interrupt=False):
                self.messages.append(text)

        panel._speech = FakeSpeech()
        panel.attach_url("https://e.com", "text", "e.com")
        assert panel._attached_images == [], (
            "Expected _attached_images to remain empty"
        )
        assert panel._attached_text == "text", (
            f"Expected 'text', got {panel._attached_text!r}"
        )
        assert "Imagen reemplazada" not in panel._speech.messages, (
            "Should not speak 'Imagen reemplazada' when no images were attached"
        )
