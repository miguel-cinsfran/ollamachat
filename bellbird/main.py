"""Bellbird — accessible desktop chat for blind users.

Entry point for the Bellbird application.
"""

import wx

from bellbird.ui.main_window import MainWindow


class BellbirdApp(wx.App):
    """Application class for Bellbird."""

    def OnInit(self) -> bool:
        """Initialize the application and show the main window.

        Returns:
            True to continue the application event loop.
        """
        frame = MainWindow(None, title="Bellbird")
        # SetTopWindow + Raise make the frame the clean foreground window so
        # NVDA announces "Bellbird" on launch. Without Raise() the console that
        # started us can keep the foreground, and the screen reader never reads
        # the new window's title — it jumps straight to the focused control.
        self.SetTopWindow(frame)
        frame.Show()
        frame.Raise()
        return True


def main() -> None:
    """Launch the Bellbird application."""
    app = BellbirdApp()
    app.MainLoop()


if __name__ == "__main__":
    main()
