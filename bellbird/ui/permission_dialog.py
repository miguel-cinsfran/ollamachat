"""PermissionDialog — accessible permission confirmation for tool execution.

Uses native wx.Dialog + wx.Button (no custom dialog with stock API) to avoid MSAA
label regression with Spanish labels. The command text is editable, risk is
re-evaluated on every keystroke, and default focus depends on risk level:
GREEN/YELLOW → allow_once_button, RED → deny_button.
"""

import sys

import wx

from bellbird.core.permission_manager import RiskLevel, PermissionManager


class PermissionDialog(wx.Dialog):
    """Dialog to confirm or deny tool execution.

    The command text is editable. Risk level and system-destructive status
    are re-evaluated on every keystroke. Default focus depends on risk level.

    Args:
        parent: Parent wx window.
        tool_name: Name of the tool to execute.
        command: The command string to display.
        risk_level: RiskLevel enum value for the command.
        permission_manager: Optional PermissionManager for re-classification.
        speech: Optional Speech instance for voice announcements.
    """

    def __init__(
        self,
        parent,
        tool_name: str,
        command: str,
        risk_level: RiskLevel,
        permission_manager: PermissionManager | None = None,
        speech: object | None = None,
    ):
        super().__init__(parent, title="Confirmar ejecución",
                         name="permission_dialog")
        self._permission_manager = permission_manager or PermissionManager()
        self._speech = speech
        self._is_system_destructive: bool = False
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
            style=wx.TE_MULTILINE,
            size=(-1, 80), name="command_text",
        )
        sizer.Add(self.command_text,
                  flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)

        risk_labels = {
            "GREEN":  "Operacion de lectura o creacion",
            "YELLOW": "Advertencia: operacion de modificacion",
            "RED":    "Advertencia: operacion irreversible (los archivos NO van a la Papelera)",
        }
        self._current_risk = risk_level
        risk_text = risk_labels.get(risk_level.name, "")
        if risk_text:
            self.risk_label = wx.StaticText(
                self, label=risk_text, name="risk_label",
            )
            sizer.Add(
                self.risk_label,
                flag=wx.LEFT | wx.TOP | wx.BOTTOM, border=8,
            )

        sizer.Add(
            wx.StaticText(self, label="Opciones:"),
            flag=wx.LEFT, border=8,
        )
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.allow_once_button = wx.Button(
            self, id=wx.ID_YES, label="&Permitir una vez",
            name="allow_once_button",
        )
        self.allow_once_button.Bind(
            wx.EVT_BUTTON, self._on_allow_once
        )
        btn_sizer.Add(self.allow_once_button, flag=wx.RIGHT, border=4)

        self.allow_session_button = wx.Button(
            self, label="Permitir en &sesión",
            name="allow_session_button",
        )
        self.allow_session_button.Bind(
            wx.EVT_BUTTON, self._on_allow_session
        )
        btn_sizer.Add(self.allow_session_button, flag=wx.RIGHT, border=4)

        self.deny_button = wx.Button(
            self, id=wx.ID_CANCEL, label="&Denegar",
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

        # Bind EVT_TEXT for live re-classify
        self.command_text.Bind(wx.EVT_TEXT, self._on_command_edited)

        # Set initial focus by risk level
        self._default_focus_for_risk(risk_level).SetFocus()

    def _on_command_edited(self, event: wx.CommandEvent) -> None:
        """Re-classify risk when the user edits the command text."""
        new_command = self.command_text.GetValue()
        new_risk = self._permission_manager.classify_risk(new_command)
        self._is_system_destructive = self._permission_manager.is_system_destructive(
            new_command
        )
        self._current_risk = new_risk

        # Update risk label
        risk_labels = {
            "GREEN":  "Operacion de lectura o creacion",
            "YELLOW": "Advertencia: operacion de modificacion",
            "RED":    "Advertencia: operacion irreversible (los archivos NO van a la Papelera)",
        }
        new_risk_text = risk_labels.get(new_risk.name, "")
        if new_risk_text and hasattr(self, "risk_label"):
            self.risk_label.SetLabel(new_risk_text)

        # Voice announce new risk level
        if self._speech is not None:
            try:
                self._speech.speak(
                    f"Riesgo: {new_risk.name}", interrupt=True
                )
            except Exception:
                pass

        # Flip focus for RED
        self._default_focus_for_risk(new_risk).SetFocus()

        event.Skip()

    def _default_focus_for_risk(self, risk: RiskLevel) -> wx.Window:
        """Return the button that should receive default focus for the given risk.

        GREEN / YELLOW → allow_once_button. RED → deny_button.
        """
        if risk == RiskLevel.RED:
            return self.deny_button
        return self.allow_once_button

    def _on_allow_once(self, event: wx.CommandEvent) -> None:
        """Handle allow-once click. Block when system-destructive."""
        if self._is_system_destructive:
            self._speak_blocked()
            return
        self.EndModal(wx.ID_YES)

    def _on_allow_session(self, event: wx.CommandEvent) -> None:
        """Handle allow-session click. Block when system-destructive."""
        if self._is_system_destructive:
            self._speak_blocked()
            return
        self.EndModal(wx.ID_OK)

    def _speak_blocked(self) -> None:
        """Speak a brief block message when a system-destructive command is rejected."""
        if self._speech is not None:
            try:
                self._speech.speak(
                    "Comando bloqueado por seguridad", interrupt=True
                )
            except Exception:
                pass

    def get_command(self) -> str:
        """Return the current (possibly edited) command text."""
        return self.command_text.GetValue()

    def get_risk(self) -> str:
        """Return the current (possibly re-evaluated) risk level."""
        return self._current_risk
