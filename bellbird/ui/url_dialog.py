"""URLDialog — accessible dialog for entering a URL to attach.

Accessible wx.Dialog with StaticText label, TextCtrl input, and two native
wx.Buttons. Uses only wx.BoxSizer (no grid sizers per AGENTS.md).
Mirrors the FindDialog pattern.
"""

import wx


class URLDialog(wx.Dialog):
    """Accessible URL entry dialog with Adjuntar/Cancelar buttons.

    Args:
        parent: Parent wx window.
    """

    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, title="Adjuntar URL", name="url_dialog")
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the dialog layout with BoxSizers only."""
        sizer = wx.BoxSizer(wx.VERTICAL)

        # ── URL label + input ─────────────────────────────────────────────
        sizer.Add(
            wx.StaticText(self, label="URL:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.url_input = wx.TextCtrl(
            self, name="url_input",
            style=wx.TE_PROCESS_ENTER,
        )
        sizer.Add(
            self.url_input,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8,
        )

        # ── Buttons row ───────────────────────────────────────────────────
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.Add(
            wx.StaticText(self, label="Opciones:"),
            flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4,
        )

        self.attach_btn = wx.Button(
            self, label="Adjuntar", name="url_attach_button", id=wx.ID_OK,
        )
        self.attach_btn.SetDefault()
        btn_sizer.Add(self.attach_btn, flag=wx.RIGHT, border=4)

        self.cancel_btn = wx.Button(
            self, label="Cancelar", name="url_cancel_button", id=wx.ID_CANCEL,
        )
        btn_sizer.Add(self.cancel_btn)

        sizer.Add(btn_sizer, flag=wx.ALL, border=8)

        self.SetSizer(sizer)
        self.SetEscapeId(wx.ID_CANCEL)

        # Focus on the text control so NVDA announces it on open
        self.url_input.SetFocus()

    def get_url(self) -> str:
        """Return the current URL text, stripped.

        Returns:
            Current content of the URL TextCtrl, with leading/trailing
            whitespace removed.
        """
        return self.url_input.GetValue().strip()
