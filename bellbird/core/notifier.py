"""wx-free notification dispatcher for event-driven feedback.

Provides ``Notifier`` — a pure dispatcher that applies the focus-aware
and toggle-aware policy for toast + sound events. The actual OS-level
toast rendering and sound playback are delegated to injected objects.

Policy:
- When the app window IS focused → silent (no toast, no sound).
- When the app is NOT focused → fire toast (if enabled) AND sound (if enabled).
- ``notifications_enabled`` governs toasts only (sounds independent).
- ``sounds_enabled`` and ``sound_theme`` (``"none"`` = no playback)
  govern sounds only.

All public methods honour the never-crash contract.
No ``import wx`` at module scope.
"""

import logging

logger = logging.getLogger(__name__)


class Notifier:
    """Pure dispatcher for toast + sound event notifications.

    Args:
        focus_check: Callable returning ``True`` when the app window
            has OS focus.
        toast_sender: Object with a ``show(title, message)`` method,
            or ``None``. The production impl is ``WxToastSender``.
        sound_player: ``SoundPlayer`` instance, or ``None``.
        notifications_enabled: Master toggle for toast delivery.
        sounds_enabled: Master toggle for sound playback.
        sound_theme: Current sound theme string. ``"none"`` disables
            sound regardless of ``sounds_enabled``.
    """

    def __init__(
        self,
        focus_check: object,
        toast_sender: object,
        sound_player: object,
        notifications_enabled: bool = True,
        sounds_enabled: bool = True,
        sound_theme: str = "default",
    ) -> None:
        self._focus_check = focus_check
        self._toast_sender = toast_sender
        self._sound_player = sound_player
        self._notifications_enabled = notifications_enabled
        self._sounds_enabled = sounds_enabled
        self._sound_theme = sound_theme

    def notify(self, event: str, message: str) -> None:
        """Dispatch an event notification.

        Silent when the app window is focused (no toast, no sound).

        Args:
            event: Event name (e.g. ``"generation_complete"``).
            message: Human-readable summary
                (e.g. ``"Respuesta completa"``).

        Raises:
            Never.
        """
        try:
            is_focused = bool(self._focus_check())
        except Exception:
            is_focused = False

        if is_focused:
            return

        # Toast (notifications_enabled governs)
        if self._notifications_enabled:
            try:
                if self._toast_sender is not None:
                    self._toast_sender.show(event, message)
            except Exception:
                pass

        # Sound (sounds_enabled + theme govern)
        if self._sounds_enabled and self._sound_theme != "none":
            try:
                if self._sound_player is not None:
                    self._sound_player.play(event)
            except Exception:
                pass

    # ── Public properties for config sync ──────────────────────────────────

    @property
    def notifications_enabled(self) -> bool:
        return self._notifications_enabled

    @notifications_enabled.setter
    def notifications_enabled(self, value: bool) -> None:
        self._notifications_enabled = value

    @property
    def sounds_enabled(self) -> bool:
        return self._sounds_enabled

    @sounds_enabled.setter
    def sounds_enabled(self, value: bool) -> None:
        self._sounds_enabled = value

    @property
    def sound_theme(self) -> str:
        return self._sound_theme

    @sound_theme.setter
    def sound_theme(self, value: str) -> None:
        self._sound_theme = value
