"""PermissionDialog — accessible permission confirmation for tool execution.

Uses native wx.Dialog + wx.Button (no custom dialog with stock API) to avoid MSAA
label regression with Spanish labels. Focus goes to command_text
so NVDA reads the command before the buttons.
"""

import sys

import wx

from bellbird.core.permission_manager import RiskLevel


class PermissionDialog(wx.Dialog):
    """Dialog to confirm or deny tool execution.

    Args:
        parent: Parent wx window.
        tool_name: Name of the tool to execute.
        command: The command string to display.
        risk_level: RiskLevel enum value for the command.
    """

    def __init__(self, parent, tool_name: str, command: str, risk_level: RiskLevel):
        super().__init__(parent, title="Confirmar ejecución",
                         name="permission_dialog")
        self._build_ui(tool_name, command, risk_level)

    def _build_ui(self, tool_name: str, command: str, risk_level: RiskLevel) -> None:
        """Build the dialog layout with command display, risk label, and buttons."""
        if sys.platform == "win32":
            try:
                import winsound  # type: ignore[import-untyped]
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except Exception:
                pass

        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.Add(
            wx.StaticText(self, label="El modelo quiere ejecutar:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.command_text = wx.TextCtrl(
            self, value=command,
            style=wx.TE_MULTILINE | wx.TE_READONLY,
            size=(-1, 80), name="command_text",
        )
        sizer.Add(self.command_text,
                  flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)

        risk_labels = {
            "GREEN":  "Operacion de lectura o creacion",
            "YELLOW": "Advertencia: operacion de modificacion",
            "RED":    "Advertencia: operacion irreversible (los archivos NO van a la Papelera)",
        }
        risk_text = risk_labels.get(risk_level.name, "")
        if risk_text:
            sizer.Add(
                wx.StaticText(self, label=risk_text, name="risk_label"),
                flag=wx.LEFT | wx.TOP | wx.BOTTOM, border=8,
            )

        sizer.Add(
            wx.StaticText(self, label="Opciones:"),
            flag=wx.LEFT, border=8,
        )
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.allow_once_button = wx.Button(
            self, id=wx.ID_YES, label="Permitir una vez",
            name="allow_once_button",
        )
        self.allow_once_button.Bind(
            wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_YES)
        )
        btn_sizer.Add(self.allow_once_button, flag=wx.RIGHT, border=4)

        self.allow_session_button = wx.Button(
            self, label="Permitir en esta sesion",
            name="allow_session_button",
        )
        self.allow_session_button.Bind(
            wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_OK)
        )
        btn_sizer.Add(self.allow_session_button, flag=wx.RIGHT, border=4)

        self.deny_button = wx.Button(
            self, id=wx.ID_CANCEL, label="Denegar",
            name="deny_button",
        )
        self.deny_button.Bind(
            wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CANCEL)
        )
        btn_sizer.Add(self.deny_button)

        sizer.Add(btn_sizer, flag=wx.ALL, border=8)
        self.SetSizer(sizer)
        self.Fit()
        self.SetEscapeId(wx.ID_CANCEL)
        self.command_text.SetFocus()
