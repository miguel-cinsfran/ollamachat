"""FindDialog — accessible search dialog for message history.

Accessible wx.Dialog with StaticText label, TextCtrl input, and three
native wx.Buttons. Uses only wx.BoxSizer (no grid sizers per AGENTS.md).
"""

import wx


class FindDialog(wx.Dialog):
    """Accessible Find dialog with Next/Previous navigation.

    Args:
        parent: Parent wx window.
    """

    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, title="Buscar en historial", name="find_dialog")
        self._callback = None
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the dialog layout with BoxSizers only."""
        sizer = wx.BoxSizer(wx.VERTICAL)

        # ── Search label + input ──────────────────────────────────────────
        sizer.Add(
            wx.StaticText(self, label="Buscar:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.find_text = wx.TextCtrl(
            self, name="find_text",
            style=wx.TE_PROCESS_ENTER,
        )
        self.find_text.Bind(wx.EVT_TEXT_ENTER, lambda evt: self._fire_callback(1))
        sizer.Add(self.find_text, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)

        # ── Buttons row ───────────────────────────────────────────────────
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.Add(
            wx.StaticText(self, label="Opciones:"),
            flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4,
        )

        self.find_next = wx.Button(
            self, label="Buscar siguiente", name="find_next",
        )
        self.find_next.Bind(wx.EVT_BUTTON, lambda evt: self._fire_callback(1))
        self.find_next.SetDefault()
        btn_sizer.Add(self.find_next, flag=wx.RIGHT, border=4)

        self.find_prev = wx.Button(
            self, label="Buscar anterior", name="find_prev",
        )
        self.find_prev.Bind(wx.EVT_BUTTON, lambda evt: self._fire_callback(-1))
        btn_sizer.Add(self.find_prev, flag=wx.RIGHT, border=4)

        self.close_btn = wx.Button(
            self, label="Cerrar", name="find_close", id=wx.ID_CANCEL,
        )
        self.close_btn.Bind(wx.EVT_BUTTON, lambda evt: self.EndModal(wx.ID_CANCEL))
        btn_sizer.Add(self.close_btn)

        sizer.Add(btn_sizer, flag=wx.ALL, border=8)

        self.SetSizer(sizer)
        self.SetEscapeId(wx.ID_CANCEL)

        # Focus on the text control so NVDA announces it on open
        self.find_text.SetFocus()

    def get_query(self) -> str:
        """Return the current search text.

        Returns:
            Current content of the search TextCtrl.
        """
        return self.find_text.GetValue()

    def set_on_find(self, callback) -> None:
        """Register a callback for find actions.

        The callback receives ``direction`` (+1 for next, -1 for previous).

        Args:
            callback: Callable(direction: int) -> None.
        """
        self._callback = callback

    def _fire_callback(self, direction: int) -> None:
        """Fire the registered callback with the given direction.

        Args:
            direction: +1 for next match, -1 for previous.
        """
        if self._callback is not None:
            self._callback(direction)
