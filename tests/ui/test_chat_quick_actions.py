"""Windows-only tests for ChatPanel quick actions and extended context menu.

These tests require wxPython; skipped on WSL/Linux via
``pytest.importorskip("wx")``. They also run from ``run_tests.bat``
on Windows.
"""

import pytest

wx = pytest.importorskip("wx")


# ─── helpers ──────────────────────────────────────────────────────────────────


class FakeSpeech:
    """Minimal speech stub for testing."""
    def __init__(self):
        self.last_message = ""
        self.messages: list[str] = []

    def speak(self, text: str, interrupt: bool = False) -> None:
        self.last_message = text
        self.messages.append(text)


def _make_panel(on_send=None, on_delete=None, on_regenerate=None, on_truncate=None):
    """Create a ChatPanel with stubs for testing."""
    from bellbird.ui.chat_panel import ChatPanel

    app = wx.GetApp()
    frame = wx.Frame(None)
    speech = FakeSpeech()
    panel = ChatPanel(
        frame, speech,
        on_send=on_send,
        on_delete_message=on_delete,
        on_regenerate_send=on_regenerate,
        on_truncate_history=on_truncate,
    )
    return app, frame, panel, speech


# ══════════════════════════════════════════════════════════════════════════════
# copy_last_message
# ══════════════════════════════════════════════════════════════════════════════


class TestCopyLastMessage:
    """ChatPanel.copy_last_message copies the last message to clipboard."""

    def test_copies_last_assistant(self):
        """GIVEN history with user then assistant
        WHEN copy_last_message is called
        THEN clipboard has the FULL assistant text."""
        app, frame, panel, speech = _make_panel()
        panel._history = [("user", "Hola"), ("assistant", "Mundo, ¿qué tal?")]
        panel.copy_last_message()
        # Verify clipboard content
        if wx.TheClipboard.Open():
            data = wx.TextDataObject()
            wx.TheClipboard.GetData(data)
            assert data.GetText() == "Mundo, ¿qué tal?"
            wx.TheClipboard.Close()
        assert speech.last_message == "Último mensaje copiado"
        frame.Destroy()

    def test_falls_back_to_user(self):
        """GIVEN history with only a user message
        WHEN copy_last_message is called
        THEN clipboard has the user text."""
        app, frame, panel, speech = _make_panel()
        panel._history = [("user", "Pregunta única")]
        panel.copy_last_message()
        if wx.TheClipboard.Open():
            data = wx.TextDataObject()
            wx.TheClipboard.GetData(data)
            assert data.GetText() == "Pregunta única"
            wx.TheClipboard.Close()
        assert speech.last_message == "Último mensaje copiado"
        frame.Destroy()

    def test_empty_history_noop(self):
        """GIVEN empty history
        WHEN copy_last_message is called
        THEN clipboard is not modified and 'Nada que copiar' is spoken."""
        app, frame, panel, speech = _make_panel()
        panel._history = []
        # Clear clipboard first
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(""))
            wx.TheClipboard.Close()
        panel.copy_last_message()
        if wx.TheClipboard.Open():
            data = wx.TextDataObject()
            wx.TheClipboard.GetData(data)
            assert data.GetText() != "Nada que copiar"  # clipboard unaffected
            wx.TheClipboard.Close()
        assert speech.last_message == "Nada que copiar"
        frame.Destroy()


# ══════════════════════════════════════════════════════════════════════════════
# delete_last_exchange
# ══════════════════════════════════════════════════════════════════════════════


class TestDeleteLastExchange:
    """ChatPanel.delete_last_exchange removes the last user/assistant pair."""

    def test_pair_removed(self):
        """GIVEN history with two exchanges
        WHEN delete_last_exchange
        THEN last pair removed."""
        deleted = []

        def on_delete(index, role):
            deleted.append((index, role))

        app, frame, panel, speech = _make_panel(on_delete=on_delete)
        panel.set_history([
            ("user", "Q1"), ("assistant", "A1"),
            ("user", "Q2"), ("assistant", "A2"),
        ])
        panel.delete_last_exchange()
        assert len(panel._history) == 2
        assert panel._history == [("user", "Q1"), ("assistant", "A1")]
        assert len(deleted) == 2  # assistant A2 + user Q2
        assert speech.last_message == "Último intercambio eliminado"
        frame.Destroy()

    def test_single_user_removed(self):
        """GIVEN history ending with a lone user (no assistant yet)
        WHEN delete_last_exchange
        THEN trailing user removed."""
        deleted = []

        def on_delete(index, role):
            deleted.append((index, role))

        app, frame, panel, speech = _make_panel(on_delete=on_delete)
        panel.set_history([("user", "Q1"), ("assistant", "A1"), ("user", "Q2")])
        panel.delete_last_exchange()
        assert panel._history == [("user", "Q1"), ("assistant", "A1")]
        assert len(deleted) == 1
        frame.Destroy()

    def test_noop_mid_generation(self):
        """GIVEN _is_generating is True
        WHEN delete_last_exchange
        THEN history unchanged and 'Generación en curso' spoken."""
        app, frame, panel, speech = _make_panel()
        panel._history = [("user", "Q1"), ("assistant", "A1")]
        panel._is_generating = True
        panel.delete_last_exchange()
        assert len(panel._history) == 2
        assert speech.last_message == "Generación en curso"
        frame.Destroy()


# ══════════════════════════════════════════════════════════════════════════════
# edit_message
# ══════════════════════════════════════════════════════════════════════════════


class TestEditMessage:
    """ChatPanel.edit_message navigates and loads user messages."""

    def test_prev_loads_last_user_before_assistant(self):
        """GIVEN history with two exchanges
        WHEN edit_message('prev')
        THEN message_input has 'Q2' and history is truncated."""
        truncated = []

        def on_truncate(conv_idx):
            truncated.append(conv_idx)

        app, frame, panel, speech = _make_panel(on_truncate=on_truncate)
        panel._history = [
            ("user", "Q1"), ("assistant", "A1"),
            ("user", "Q2"), ("assistant", "A2"),
        ]
        panel.message_input.SetValue("current text")
        panel.edit_message("prev")
        assert panel.message_input.GetValue() == "Q2"
        assert panel._history == [("user", "Q1"), ("assistant", "A1"), ("user", "Q2")]
        assert len(truncated) == 1
        assert truncated[0] == 2  # conv_idx = index - system_count
        frame.Destroy()

    def test_next_is_noop(self):
        """GIVEN any history
        WHEN edit_message('next')
        THEN no-op with 'No hay mensaje siguiente'."""
        app, frame, panel, speech = _make_panel()
        panel._history = [("user", "Q1"), ("assistant", "A1")]
        original = list(panel._history)
        panel.edit_message("next")
        assert panel._history == original
        assert speech.last_message == "No hay mensaje siguiente"
        frame.Destroy()

    def test_no_previous_when_empty(self):
        """GIVEN empty history
        WHEN edit_message('prev')
        THEN no-op with guard message."""
        app, frame, panel, speech = _make_panel()
        panel.edit_message("prev")
        assert speech.last_message == "No hay mensaje anterior"
        frame.Destroy()


# ══════════════════════════════════════════════════════════════════════════════
# regenerate_last
# ══════════════════════════════════════════════════════════════════════════════


class TestRegenerateLast:
    """ChatPanel.regenerate_last re-sends the last user prompt."""

    def test_assistant_removed_and_send_fired(self):
        """GIVEN history with user+assistant
        WHEN regenerate_last
        THEN assistant removed and send fired with user text."""
        send_args = []
        deleted = []

        def on_send():
            send_args.append(True)

        def on_delete(index, role):
            deleted.append((index, role))

        def on_regenerate(text, user_idx):
            send_args.append((text, user_idx))

        app, frame, panel, speech = _make_panel(
            on_send=on_send,
            on_delete=on_delete,
            on_regenerate=on_regenerate,
        )
        panel.set_history([("user", "Q1"), ("assistant", "A1")])
        panel.regenerate_last()
        assert panel._history == [("user", "Q1")]
        assert len(deleted) == 1
        assert len(send_args) == 1
        assert send_args[0] == ("Q1", 0)  # (text, user_idx)
        frame.Destroy()

    def test_no_assistant_noop(self):
        """GIVEN no assistant row
        WHEN regenerate_last
        THEN no-op with 'Nada que regenerar'."""
        app, frame, panel, speech = _make_panel()
        panel._history = [("user", "Q1")]
        panel.regenerate_last()
        assert len(panel._history) == 1
        assert speech.last_message == "Nada que regenerar"
        frame.Destroy()

    def test_noop_mid_generation(self):
        """GIVEN _is_generating is True
        WHEN regenerate_last
        THEN no-op with 'Generación en curso'."""
        app, frame, panel, speech = _make_panel()
        panel._history = [("user", "Q1"), ("assistant", "A1")]
        panel._is_generating = True
        panel.regenerate_last()
        assert len(panel._history) == 2
        assert speech.last_message == "Generación en curso"
        frame.Destroy()


# ══════════════════════════════════════════════════════════════════════════════
# Context menu items (7 when idle, 4 mid-generation)
# ══════════════════════════════════════════════════════════════════════════════


class TestContextMenuCount:
    """Context menu has the correct number of items depending on generation state."""

    def test_7_items_when_idle(self):
        """GIVEN idle state
        WHEN building context menu
        THEN 7 items are present."""
        app, frame, panel, speech = _make_panel()
        menu = panel._build_context_menu()
        count = menu.GetMenuItemCount()
        menu.Destroy()
        assert count == 7, f"Expected 7 items when idle, got {count}"
        frame.Destroy()

    def test_4_items_mid_generation(self):
        """GIVEN _is_generating is True
        WHEN building context menu
        THEN 4 items are present (delete items removed)."""
        app, frame, panel, speech = _make_panel()
        panel._is_generating = True
        menu = panel._build_context_menu()
        count = menu.GetMenuItemCount()
        menu.Destroy()
        assert count == 4, f"Expected 4 items mid-generation, got {count}"
        frame.Destroy()
