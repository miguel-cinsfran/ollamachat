"""Tests for bellbird.core.notifier — strict TDD, RED first, then GREEN.

Covers: focus-aware dispatch, notifications_enabled toggle, sounds_enabled
toggle, sound_theme="none", never-crash contract, no notifier reasoning path.
"""

from unittest.mock import MagicMock

import pytest


class TestNotifier:
    """Notifier focus-aware event dispatch."""

    # ── Helpers ────────────────────────────────────────────────────────────

    @pytest.fixture
    def stubs(self):
        """Return a dict of stubbed dependencies."""
        focus_check = MagicMock()
        toast_sender = MagicMock()
        sound_player = MagicMock()
        return {
            "focus_check": focus_check,
            "toast_sender": toast_sender,
            "sound_player": sound_player,
        }

    # ── Focus-aware dispatch ───────────────────────────────────────────────

    def test_silent_when_focused(self, stubs):
        """GIVEN focus_check returns True (focused)
        WHEN notify is called
        THEN toast and sound are NOT called."""
        from bellbird.core.notifier import Notifier

        stubs["focus_check"].return_value = True
        notifier = Notifier(**stubs)
        notifier.notify("generation_complete", "Listo")

        stubs["toast_sender"].show.assert_not_called()
        stubs["sound_player"].play.assert_not_called()

    def test_fires_toast_and_sound_when_not_focused(self, stubs):
        """GIVEN focus_check returns False (not focused)
        WHEN notify is called
        THEN toast and sound ARE called."""
        from bellbird.core.notifier import Notifier

        stubs["focus_check"].return_value = False
        notifier = Notifier(**stubs)
        notifier.notify("generation_complete", "Listo")

        stubs["toast_sender"].show.assert_called_once_with(
            "generation_complete", "Listo"
        )
        stubs["sound_player"].play.assert_called_once_with("generation_complete")

    # ── notifications_enabled master toggle ────────────────────────────────

    def test_notifications_disabled_silences_toast(self, stubs):
        """GIVEN notifications_enabled=False
        WHEN notify is called (not focused)
        THEN toast is NOT called, but sound IS called."""
        from bellbird.core.notifier import Notifier

        stubs["focus_check"].return_value = False
        notifier = Notifier(**stubs, notifications_enabled=False)
        notifier.notify("generation_complete", "Listo")

        stubs["toast_sender"].show.assert_not_called()
        stubs["sound_player"].play.assert_called_once_with("generation_complete")

    def test_notifications_enabled_fires_toast(self, stubs):
        """GIVEN notifications_enabled=True (default)
        WHEN notify is called (not focused)
        THEN toast IS called."""
        from bellbird.core.notifier import Notifier

        stubs["focus_check"].return_value = False
        notifier = Notifier(**stubs, notifications_enabled=True)
        notifier.notify("generation_complete", "Listo")

        stubs["toast_sender"].show.assert_called_once()

    # ── sounds_enabled master toggle ───────────────────────────────────────

    def test_sounds_disabled_silences_sound(self, stubs):
        """GIVEN sounds_enabled=False
        WHEN notify is called (not focused)
        THEN sound is NOT called, but toast IS called."""
        from bellbird.core.notifier import Notifier

        stubs["focus_check"].return_value = False
        notifier = Notifier(**stubs, sounds_enabled=False)
        notifier.notify("generation_complete", "Listo")

        stubs["toast_sender"].show.assert_called_once()
        stubs["sound_player"].play.assert_not_called()

    def test_sounds_disabled_still_fires_toast(self, stubs):
        """GIVEN sounds_enabled=False
        WHEN notify is called (not focused)
        THEN toast IS called."""
        from bellbird.core.notifier import Notifier

        stubs["focus_check"].return_value = False
        notifier = Notifier(**stubs, sounds_enabled=False)
        notifier.notify("generation_complete", "Listo")

        stubs["toast_sender"].show.assert_called_once()

    # ── sound_theme="none" ─────────────────────────────────────────────────

    def test_sound_theme_none_silences_sound(self, stubs):
        """GIVEN sound_theme='none'
        WHEN notify is called (not focused)
        THEN sound is NOT called, toast IS called."""
        from bellbird.core.notifier import Notifier

        stubs["focus_check"].return_value = False
        notifier = Notifier(
            **stubs,
            sound_theme="none",
        )
        notifier.notify("generation_complete", "Listo")

        stubs["toast_sender"].show.assert_called_once()
        stubs["sound_player"].play.assert_not_called()

    def test_sound_theme_default_still_plays_sound(self, stubs):
        """GIVEN sound_theme='default'
        WHEN notify is called (not focused)
        THEN sound IS called."""
        from bellbird.core.notifier import Notifier

        stubs["focus_check"].return_value = False
        notifier = Notifier(**stubs, sound_theme="default")
        notifier.notify("generation_complete", "Listo")

        stubs["sound_player"].play.assert_called_once()

    # ── never-crash ────────────────────────────────────────────────────────

    def test_toast_sender_raises_is_caught(self, stubs):
        """GIVEN toast_sender.show raises
        WHEN notify is called
        THEN no exception propagates."""
        from bellbird.core.notifier import Notifier

        stubs["focus_check"].return_value = False
        stubs["toast_sender"].show.side_effect = RuntimeError("toast failed")
        notifier = Notifier(**stubs)
        notifier.notify("generation_complete", "Listo")  # must not raise

    def test_sound_player_raises_is_caught(self, stubs):
        """GIVEN sound_player.play raises
        WHEN notify is called
        THEN no exception propagates."""
        from bellbird.core.notifier import Notifier

        stubs["focus_check"].return_value = False
        stubs["sound_player"].play.side_effect = RuntimeError("sound failed")
        notifier = Notifier(**stubs)
        notifier.notify("generation_complete", "Listo")  # must not raise

    def test_notify_never_raises(self, stubs):
        """GIVEN any combination of failure modes
        WHEN notify is called
        THEN no exception propagates."""
        from bellbird.core.notifier import Notifier

        stubs["focus_check"].return_value = False
        stubs["toast_sender"].show.side_effect = RuntimeError("fail")
        stubs["sound_player"].play.side_effect = RuntimeError("fail")
        notifier = Notifier(**stubs)
        notifier.notify("generation_complete", "Listo")  # must not raise

    # ── No reasoning path ──────────────────────────────────────────────────

    def test_no_notify_reasoning_method(self):
        """GIVEN the Notifier class
        WHEN checking for methods
        THEN there is no 'notify_reasoning' method (reasoning is never
        surfaced through the notification system)."""
        from bellbird.core.notifier import Notifier

        assert not hasattr(Notifier, "notify_reasoning")
        assert not hasattr(Notifier, "notify_reason")
