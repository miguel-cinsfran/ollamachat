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
        frame.Show()
        return True


def main() -> None:
    """Launch the Bellbird application."""
    app = BellbirdApp()
    app.MainLoop()


if __name__ == "__main__":
    main()
