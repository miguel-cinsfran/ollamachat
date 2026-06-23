"""ChatPanel — dual view conversation display and message input.

Provides the main chat interface with two display areas:
- message_list (ListBox): navigable history of message previews
- stream_display (TextCtrl): live streaming response area (~4 lines)
Plus multiline message input with Enter/Shift+Enter handling,
and action buttons (send, stop, attach, clear).
"""

import base64
from pathlib import Path

import wx

from bellbird.core.text_utils import strip_markdown


class ChatPanel(wx.Panel):
    """Panel for conversation display, input, and action buttons.

    Args:
        parent: Parent wx window.
        speech: Speech instance for token announcements.
    """

    def __init__(self, parent: wx.Window, speech,
                 on_send: callable | None = None,
                 on_delete_message: callable | None = None) -> None:
        super().__init__(parent)
        self._speech = speech
        self._on_send_callback = on_send
        self._on_delete_callback = on_delete_message
        self._attached_images: list[tuple[str, str]] = []  # (base64, mime)
        self._attached_text: str | None = None
        self._history: list[tuple[str, str]] = []
        self._is_generating: bool = False
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the chat panel layout with dual view."""
        sizer = wx.BoxSizer(wx.VERTICAL)

        # ── History List (ListBox) ───────────────────────────────────────
        sizer.Add(
            wx.StaticText(self, label="Historial:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.message_list = wx.ListBox(
            self,
            name="message_list",
        )
        self.message_list.Bind(wx.EVT_CONTEXT_MENU, self._on_message_context_menu)
        self.message_list.Bind(wx.EVT_KEY_DOWN, self._on_list_key)
        self.message_list.Bind(wx.EVT_LISTBOX_DCLICK, self._on_message_dclick)
        sizer.Add(self.message_list, proportion=1, flag=wx.EXPAND | wx.ALL, border=8)

        # ── Stream Display (TextCtrl) ────────────────────────────────────
        sizer.Add(
            wx.StaticText(self, label="Respuesta actual:"),
            flag=wx.LEFT | wx.RIGHT, border=8,
        )
        self.stream_display = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2,
            name="stream_display",
            size=(-1, 80),
        )
        sizer.Add(self.stream_display, proportion=0, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)

        # ── Attachment Label ────────────────────────────────────────────────
        sizer.Add(
            wx.StaticText(self, label="Adjunto:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.attachment_label = wx.StaticText(
            self, label="(ninguno)", name="attachment_label"
        )
        sizer.Add(self.attachment_label, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)

        # ── Message Input ───────────────────────────────────────────────────
        sizer.Add(
            wx.StaticText(self, label="Mensaje:"),
            flag=wx.LEFT | wx.RIGHT, border=8,
        )
        self.message_input = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_PROCESS_ENTER,
            name="message_input",
        )
        self.message_input.Bind(wx.EVT_TEXT_ENTER, self._on_input_enter)
        sizer.Add(self.message_input, proportion=0, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)

        # ── Action Buttons ──────────────────────────────────────────────────
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.Add(
            wx.StaticText(self, label="Acciones:"),
            flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4,
        )

        self.send_button = wx.Button(self, label="Enviar", name="send_button")
        self.send_button.Bind(
            wx.EVT_BUTTON, lambda evt: self._on_send_callback() if self._on_send_callback else None
        )
        btn_sizer.Add(self.send_button, flag=wx.RIGHT, border=4)

        self.stop_button = wx.Button(self, label="Detener", name="stop_button")
        self.stop_button.Disable()
        # Stop button is bound externally by MainWindow
        btn_sizer.Add(self.stop_button, flag=wx.RIGHT, border=4)

        self.attach_button = wx.Button(self, label="Adjuntar", name="attach_button")
        self.attach_button.Bind(wx.EVT_BUTTON, lambda evt: self._on_attach())
        btn_sizer.Add(self.attach_button, flag=wx.RIGHT, border=4)

        self.clear_button = wx.Button(self, label="Limpiar", name="clear_button")
        self.clear_button.Bind(wx.EVT_BUTTON, lambda evt: self._on_clear())
        btn_sizer.Add(self.clear_button, flag=wx.RIGHT, border=4)

        sizer.Add(btn_sizer, flag=wx.ALL, border=8)

        self.SetSizer(sizer)

    # ── Preview helper ─────────────────────────────────────────────────────

    @staticmethod
    def _preview(text: str) -> str:
        """Generate a short preview (max 80 chars) for the message list.

        Args:
            text: Full message text.

        Returns:
            Truncated single-line string, suffixed with '...' if shortened.
        """
        cleaned = text.replace("\n", " ").strip()
        if len(cleaned) > 80:
            return cleaned[:80] + "..."
        return cleaned

    # ── History accessors ──────────────────────────────────────────────────

    def get_message_at(self, index: int) -> tuple[str, str]:
        """Get a (role, text) pair from the history.

        Args:
            index: Zero-based index into _history.

        Returns:
            Tuple of (role, content).

        Raises:
            IndexError: If index is out of range.
        """
        return self._history[index]

    def get_history(self) -> list[tuple[str, str]]:
        """Get a copy of the full history list.

        Returns:
            List of (role, content) tuples.
        """
        return list(self._history)

    def set_history(self, messages: list[tuple[str, str]]) -> None:
        """Replace the full history and repopulate the message list.

        Args:
            messages: List of (role, content) tuples.
        """
        self._history = list(messages)
        self.message_list.Clear()
        for role, text in self._history:
            prefix = "[Tú]" if role == "user" else "[IA]"
            self.message_list.Append(f"{prefix} {self._preview(text)}")
        if self._history:
            self.message_list.SetSelection(len(self._history) - 1)

    # ── Display methods ────────────────────────────────────────────────────

    def append_user_message(self, text: str) -> None:
        """Append a user message to the history and message list.

        Args:
            text: User message text.
        """
        self._history.append(("user", text))
        preview = f"[Tú] {self._preview(text)}"
        self.message_list.Append(preview)
        self.message_list.SetSelection(self.message_list.GetCount() - 1)
        self.stream_display.Clear()

    def append_assistant_prefix(self) -> None:
        """Clear the stream display and add the assistant prefix."""
        self.stream_display.Clear()
        self.stream_display.AppendText("[Asistente] ")

    def append_assistant_chunk(self, token: str) -> None:
        """Append a token fragment to the streaming display.

        Args:
            token: Token text from the LLM stream.
        """
        self.stream_display.AppendText(token)

    def start_generation(self) -> None:
        """Disable send and attach buttons during generation."""
        self._is_generating = True
        self.send_button.Disable()
        self.attach_button.Disable()
        self.stop_button.Enable()

    def end_generation(self) -> None:
        """Move stream content to history and re-enable buttons.

        If the stream is empty (e.g. aborted before the first token),
        no list item is added — prevents empty "[IA] [Asistente]"
        rows in the message list when the user aborts immediately.
        """
        final = self.stream_display.GetValue()
        PREFIX = "[Asistente] "
        if final.startswith(PREFIX):
            final = final[len(PREFIX):]
        final = final.rstrip("\n")
        if final.strip():
            self._history.append(("assistant", final))
            preview = f"[IA] {self._preview(final)}"
            self.message_list.Append(preview)
            self.message_list.SetSelection(self.message_list.GetCount() - 1)
        self.stream_display.Clear()
        self._is_generating = False
        self.send_button.Enable()
        self.attach_button.Enable()
        self.stop_button.Disable()

    # ── Input methods ──────────────────────────────────────────────────────

    def _on_input_enter(self, event: wx.CommandEvent) -> None:
        """Handle Enter key in message input.

        Enter (without Shift) sends the message.
        Shift+Enter inserts a newline.
        """
        if event.ShiftDown():
            # Shift+Enter: insert newline and let the event propagate
            event.Skip()
        else:
            # Enter: send message
            if self._on_send_callback:
                self._on_send_callback()

    def get_input_text(self) -> str:
        """Get the current message input text.

        Returns:
            Current text in the message input field.
        """
        return self.message_input.GetValue()

    def _clear_input(self) -> None:
        """Clear the message input field."""
        self.message_input.Clear()

    # ── Context menu ───────────────────────────────────────────────────────

    def _build_context_menu(self) -> wx.Menu:
        """Build the context menu for the message list.

        Returns:
            A wx.Menu with copy, browser, and conditional delete items.
        """
        menu = wx.Menu()
        menu_copy = wx.MenuItem(menu, wx.ID_COPY, "Copiar mensaje\tCtrl+C")
        menu_copy.SetName("menu_copy_message")
        menu.Append(menu_copy)
        self.Bind(wx.EVT_MENU, lambda evt: self._on_context_copy(), menu_copy)

        menu_browser = wx.MenuItem(
            menu, wx.ID_ANY, "Abrir en navegador\tCtrl+Enter"
        )
        menu_browser.SetName("menu_open_browser")
        menu.Append(menu_browser)
        self.Bind(wx.EVT_MENU, lambda evt: self._on_context_browser(), menu_browser)

        if not self._is_generating:
            menu_delete = wx.MenuItem(menu, wx.ID_DELETE, "Eliminar mensaje")
            menu_delete.SetName("menu_delete_message")
            menu.Append(menu_delete)
            self.Bind(wx.EVT_MENU, lambda evt: self._on_context_delete(), menu_delete)

        return menu

    def _on_message_context_menu(self, event: wx.ContextMenuEvent) -> None:
        """Show the context menu for the message list."""
        menu = self._build_context_menu()
        self.PopupMenu(menu)
        menu.Destroy()

    def _on_context_copy(self) -> None:
        """Copy the selected message to clipboard."""
        sel = self.message_list.GetSelection()
        if sel == wx.NOT_FOUND:
            return
        role, text = self._history[sel]
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(text))
            wx.TheClipboard.Close()
        self._speech.speak("Mensaje copiado", interrupt=False)

    def _on_context_browser(self) -> None:
        """Open the selected message in the browser (handled by MainWindow)."""
        sel = self.message_list.GetSelection()
        if sel == wx.NOT_FOUND:
            return
        role, text = self._history[sel]
        # Find the parent MainWindow to call _open_message_in_browser
        parent = self.GetParent()
        while parent is not None and not hasattr(parent, "_open_message_in_browser"):
            parent = parent.GetParent()
        if parent is not None:
            parent._open_message_in_browser(text)

    def _on_context_delete(self) -> None:
        """Delete the selected message from history."""
        sel = self.message_list.GetSelection()
        if sel == wx.NOT_FOUND:
            return
        role = self._history[sel][0]  # capture BEFORE pop
        self._history.pop(sel)
        self.message_list.Delete(sel)
        count = self.message_list.GetCount()
        if count > 0:
            new_sel = min(sel, count - 1)
            self.message_list.SetSelection(new_sel)
        if self._on_delete_callback:
            self._on_delete_callback(sel, role)
        self._speech.speak("Mensaje eliminado", interrupt=False)

    # ── Key routing ────────────────────────────────────────────────────────

    def _on_list_key(self, event: wx.KeyEvent) -> None:
        """Handle key events in the message list.

        Decision tree per design §3.2:
        - Ctrl+C → copy
        - Ctrl+Enter → browser
        - Enter → popup (MessageDetailDialog)
        - Printable → focus input and type
        - Else → Skip
        """
        key = event.GetKeyCode()

        if event.ControlDown() and key == ord("C"):
            self._on_context_copy()
            return

        if event.ControlDown() and key == wx.WXK_RETURN:
            self._on_context_browser()
            return

        if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and not event.ShiftDown():
            self._on_message_dclick()
            return

        # Printable character (no Ctrl/Alt/Meta)
        # Use GetUnicodeKey() instead of GetKeyCode() so non-ASCII chars
        # (ñ, á, é, í, ó, ú, ¿, ¡, etc.) route to the input correctly.
        # GetKeyCode() returns the virtual key code which is wrong for
        # non-ASCII chars on Windows; the user is Spanish-speaking so
        # this matters for the target audience.
        if not event.ControlDown() and not event.AltDown() and not event.MetaDown():
            unicode_key = event.GetUnicodeKey()
            if unicode_key != 0:
                char = chr(unicode_key)
                if char.isprintable() or char == " ":
                    self.message_input.SetFocus()
                    self.message_input.AppendText(char)
                    self.message_input.SetInsertionPointEnd()
                    return

        event.Skip()

    def _on_message_dclick(self, event=None) -> None:
        """Open the MessageDetailDialog for the selected message."""
        sel = self.message_list.GetSelection()
        if sel == wx.NOT_FOUND:
            return
        role, text = self._history[sel]
        from bellbird.ui.message_detail_dialog import MessageDetailDialog

        dlg = MessageDetailDialog(self, role, text)
        dlg.ShowModal()
        dlg.Destroy()

    # ── Attachment methods (unchanged from v0.2.0) ──────────────────────────

    def _on_attach(self) -> None:
        """Open file dialog and handle attachment."""
        wildcard = (
            "Todos los archivos (*.*)|*.*"
        )
        dialog = wx.FileDialog(
            self,
            message="Adjuntar archivo",
            defaultDir="",
            defaultFile="",
            wildcard=wildcard,
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        )
        if dialog.ShowModal() == wx.ID_OK:
            filepath = dialog.GetPath()
            self.attach_file(filepath)
        dialog.Destroy()

    def _on_clear(self) -> None:
        """Clear the conversation and attachment."""
        self.clear()

    def _infer_mime(self, ext: str) -> str:
        """Infer MIME type from file extension.

        Args:
            ext: Lowercase file extension without dot.

        Returns:
            MIME type string (e.g. 'image/jpeg').
        """
        mime_map = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "bmp": "image/bmp",
            "gif": "image/gif",
        }
        return mime_map.get(ext, "image/jpeg")

    def attach_file(self, filepath: str) -> None:
        """Attach a file to the next message.

        Image files (jpg, jpeg, png, bmp, gif) are base64-encoded and
        stored in _attached_images as (base64, mime) tuples. Other files
        are read as UTF-8 text.

        Args:
            filepath: Path to the file to attach.
        """
        path = Path(filepath)
        ext = path.suffix.lower().lstrip(".")

        if ext in ("jpg", "jpeg", "png", "bmp", "gif"):
            with open(path, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("utf-8")
            mime = self._infer_mime(ext)
            self._attached_images = [(encoded, mime)]
            self._attached_text = None
            self.attachment_label.SetLabel(path.name)
            self._speech.speak(f"Imagen adjuntada: {path.name}", interrupt=True)
        else:
            try:
                text_content = path.read_text(encoding="utf-8")
                self._attached_text = text_content
                self._attached_images = []
                self.attachment_label.SetLabel(path.name)
                self._speech.speak(
                    f"Archivo de texto adjuntado: {path.name}", interrupt=True
                )
            except Exception:
                self._speech.speak(
                    f"No se pudo adjuntar: {path.name}", interrupt=True
                )

    def get_attached_images(self) -> list[tuple[str, str]]:
        """Get the list of attached images as (base64, mime) tuples.

        Returns:
            List of (base64, mime) tuples.
        """
        return self._attached_images

    def get_attached_text(self) -> str | None:
        """Get the attached text file content, if any.

        Returns:
            Text content string, or None.
        """
        return self._attached_text

    def clear_attachment(self) -> None:
        """Clear the current attachment."""
        self._attached_images = []
        self._attached_text = None
        self.attachment_label.SetLabel("(ninguno)")

    def clear(self) -> None:
        """Clear the conversation display, input, and attachments.

        If a generation is in progress when clear is called, end it
        first so the buttons return to idle state. Otherwise the user
        would be stuck with send disabled until the in-flight stream
        completes (up to 60s for a long response). The stream is
        being torn down anyway because the user is starting fresh.
        """
        if self._is_generating:
            # Tear down the in-flight generation state synchronously
            self.send_button.Enable()
            self.attach_button.Enable()
            self.stop_button.Disable()
            self._is_generating = False
        self.message_list.Clear()
        self._history.clear()
        self.stream_display.Clear()
        self._clear_input()
        self.clear_attachment()

    # ── Tool output display (v0.4.0) ──────────────────────────────────────

    def append_tool_output(self, text: str) -> None:
        """Muestra el resultado de una herramienta en el historial."""
        self._history.append(("tool", text))
        preview = f"[Herramienta] {self._preview(text)}"
        self.message_list.Append(preview)
        self.message_list.SetSelection(self.message_list.GetCount() - 1)

    def append_tool_blocked(self, tool_name: str, command: str) -> None:
        """Muestra que un comando fue bloqueado por seguridad."""
        text = f"[Bloqueado] {tool_name}: {command}"
        self._history.append(("system", text))
        self.message_list.Append(f"[Bloqueado] {self._preview(text)}")
        self.message_list.SetSelection(self.message_list.GetCount() - 1)

    def append_tool_denied(self, tool_name: str) -> None:
        """Muestra que el usuario denegó la ejecución."""
        text = f"[Denegado] {tool_name}"
        self._history.append(("system", text))
        self.message_list.Append(text)
        self.message_list.SetSelection(self.message_list.GetCount() - 1)
