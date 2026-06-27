"""FocusChecker protocol for the wx-free notifier dispatcher.

Defines a single-method ``Protocol`` that the ``Notifier`` uses to
check whether the application window currently has OS focus. The
production implementation lives in ``MainWindow``:

    focus_check = lambda: self.IsActive()

It must return ``True`` when the window HAS focus (the Notifier stays
silent in that case and only fires toasts/sounds when unfocused).
On non-Windows or in tests, a stub can always return ``False``.
"""

from typing import Protocol


class FocusChecker(Protocol):
    """Protocol for checking whether the app window has OS focus.

    The production impl is a lambda in ``MainWindow.__init__``:
    ``lambda: self.IsActive()`` — returns ``True`` when focused.

    Structural typing — any object with ``def is_focused(self) -> bool``
    satisfies the protocol.
    """

    def is_focused(self) -> bool:
        """Return ``True`` when the app window currently has focus."""
        ...
