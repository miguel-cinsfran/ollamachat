"""ChatPanel — single-ListBox conversation display and message input.

Provides the main chat interface with one display area:
- message_list (ListBox): navigable history of message previews,
  including the in-progress streaming row (placeholder → preview → final).
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
                 on_send=None,
                 on_delete_message=None,
                 on_regenerate_send=None,
                 on_truncate_history=None) -> None:
        super().__init__(parent)
        self._speech = speech
        self._on_send_callback = on_send
        self._on_delete_callback = on_delete_message
        self._on_regenerate_send_callback = on_regenerate_send
        self._on_truncate_callback = on_truncate_history
        self._attached_images: list[tuple[str, str]] = []  # (base64, mime)
        self._attached_text: str | None = None
        self._history: list[tuple[str, str]] = []
        self._is_generating: bool = False
        self._streaming_index: int | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the chat panel layout with single-ListBox conversation display."""
        sizer = wx.BoxSizer(wx.VERTICAL)

        # ── History List (ListBox) ───────────────────────────────────────
        sizer.Add(
            wx.StaticText(self, label="Historial:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.message_list = wx.ListBox(
            self,
            name="Historial de mensajes",
        )
        self.message_list.Bind(wx.EVT_CONTEXT_MENU, self._on_message_context_menu)
        self.message_list.Bind(wx.EVT_KEY_DOWN, self._on_list_key)
        self.message_list.Bind(wx.EVT_LISTBOX_DCLICK, self._on_message_dclick)
        sizer.Add(self.message_list, proportion=1, flag=wx.EXPAND | wx.ALL, border=8)

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
            name="Campo de mensaje",
        )
        self.message_input.Bind(wx.EVT_TEXT_ENTER, self._on_input_enter)
        self.message_input.SetToolTip(
            "Escribe tu mensaje. Enter envía, Shift+Enter inserta nueva línea."
        )
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

    def get_selected_message_text(self) -> str:
        """Get the full text of the currently selected message.

        Returns empty string when no message is selected, when the
        selection is out of range, or when the streaming placeholder
        ``[IA] (generando…)`` is selected.

        Returns:
            Full text content of the selected message, or ``""``.
        """
        sel = self.message_list.GetSelection()
        if sel == wx.NOT_FOUND:
            return ""
        if 0 <= sel < len(self._history):
            text = self._history[sel][1]
            # Streaming placeholder check
            if text.startswith("[IA] (generando"):
                return ""
            return text
        return ""

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

    def start_generation(self) -> None:
        """Append a placeholder row and disable send/attach during generation."""
        self._is_generating = True
        self.send_button.Disable()
        self.attach_button.Disable()
        self.stop_button.Enable()
        self.message_list.Append("[IA] (generando…)")
        self._streaming_index = self.message_list.GetCount() - 1

    def update_streaming_preview(self, text: str) -> None:
        """Update the in-place preview of the streaming response.

        MUST NOT call ``SetSelection`` or ``SetFocus`` — the user may be
        navigating other messages.

        Args:
            text: The accumulated response text so far.
        """
        if self._streaming_index is None:
            return
        preview = f"[IA] {self._preview(strip_markdown(text))}"
        self.message_list.SetString(self._streaming_index, preview)

    def end_generation(self, final_text: str = "") -> None:
        """Promote or remove the placeholder row and re-enable buttons.

        Non-empty path: the placeholder is promoted to a final preview,
        the full text is appended to ``_history``.
        Empty path (aborted before first token): the placeholder is
        removed from ``message_list``.

        Args:
            final_text: The complete response text. When empty (default),
                the placeholder is deleted and nothing is appended to
                history.
        """
        if final_text:
            self._history.append(("assistant", final_text))
            preview = f"[IA] {self._preview(strip_markdown(final_text))}"
            self.message_list.SetString(self._streaming_index, preview)
        else:
            self.message_list.Delete(self._streaming_index)
        self._streaming_index = None
        self._is_generating = False
        self.send_button.Enable()
        self.attach_button.Enable()
        self.stop_button.Disable()

    # ── Search methods ────────────────────────────────────────────────────

    def select_and_announce_message(self, index: int) -> None:
        """Select, focus, and announce a message in the history list.

        Args:
            index: Zero-based index into _history. Out-of-range is a
                silent no-op.
        """
        if index < 0 or index >= len(self._history):
            return
        self.message_list.SetSelection(index)
        self.message_list.SetFocus()
        try:
            self._speech.speak(self._history[index][1], interrupt=False)
        except Exception:
            pass

    def find_and_select(self, text: str, direction: int) -> None:
        """Find text in history and select the matching message.

        Args:
            text: Search query. Empty string is a silent no-op.
            direction: +1 for next match (after current), -1 for previous.
        """
        if not text:
            return
        sel = self.message_list.GetSelection()
        if sel == wx.NOT_FOUND:
            start_index = 0 if direction > 0 else len(self._history)
        else:
            start_index = sel + 1 if direction > 0 else max(0, sel - 1)

        # Local import to keep core/ wx-free
        from bellbird.core.conversation import find_in_history

        idx = find_in_history(self._history, text, start_index, wrap=True)
        if idx >= 1:
            self.select_and_announce_message(idx - 1)
        else:
            try:
                self._speech.speak("Sin coincidencias", interrupt=False)
            except Exception:
                pass

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
        """Build the context menu for the message list (7 items when idle).

        Items:
        1. Copiar mensaje (Ctrl+C)
        2. Copiar último (Ctrl+Shift+C)
        3. Abrir en navegador (Ctrl+Enter)
        4. Editar mensaje anterior (Alt+Up)
        5. Eliminar mensaje (Supr) — removed mid-generation
        6. Borrar último intercambio (Ctrl+K) — removed mid-generation
        7. Regenerar última respuesta (Ctrl+R) — removed mid-generation
        """
        menu = wx.Menu()

        # 1. Copy selected message
        menu_copy = wx.MenuItem(menu, wx.ID_COPY, "&Copiar mensaje\tCtrl+C")
        menu.Append(menu_copy)
        self.Bind(wx.EVT_MENU, lambda evt: self._on_context_copy(), menu_copy)

        # 2. Copy last (Ctrl+Shift+C)
        menu_copy_last = wx.MenuItem(
            menu, wx.ID_ANY, "Copiar último\tCtrl+Shift+C",
            name="menu_copy_last",
        )
        menu.Append(menu_copy_last)
        self.Bind(
            wx.EVT_MENU, lambda evt: self.copy_last_message(), menu_copy_last,
        )

        # 3. Open in browser (Ctrl+Enter)
        menu_browser = wx.MenuItem(
            menu, wx.ID_ANY, "&Abrir en navegador\tCtrl+Enter",
            name="menu_open_browser",
        )
        menu.Append(menu_browser)
        self.Bind(wx.EVT_MENU, lambda evt: self._on_context_browser(), menu_browser)

        # 4. Edit previous message (Alt+Up)
        menu_edit = wx.MenuItem(
            menu, wx.ID_ANY, "&Editar mensaje anterior\tAlt+Up",
            name="menu_edit_message",
        )
        menu.Append(menu_edit)
        self.Bind(
            wx.EVT_MENU, lambda evt: self.edit_message("prev"), menu_edit,
        )

        if not self._is_generating:
            # 5. Delete message (Supr)
            menu_delete = wx.MenuItem(
                menu, wx.ID_DELETE, "&Eliminar mensaje",
                name="menu_delete_message",
            )
            menu.Append(menu_delete)
            self.Bind(
                wx.EVT_MENU, lambda evt: self._on_context_delete(), menu_delete,
            )

            # 6. Delete last exchange (Ctrl+K)
            menu_del_last = wx.MenuItem(
                menu, wx.ID_ANY, "Borrar último intercambio\tCtrl+K",
                name="menu_delete_last_exchange",
            )
            menu.Append(menu_del_last)
            self.Bind(
                wx.EVT_MENU,
                lambda evt: self.delete_last_exchange(),
                menu_del_last,
            )

            # 7. Regenerate last response (Ctrl+R)
            menu_regen = wx.MenuItem(
                menu, wx.ID_ANY, "Regenerar última respuesta\tCtrl+R",
                name="menu_regenerate_last",
            )
            menu.Append(menu_regen)
            self.Bind(
                wx.EVT_MENU,
                lambda evt: self.regenerate_last(),
                menu_regen,
            )

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

        # Delete (Supr) → remove the selected history row.
        # Gate on _is_generating to match the context-menu behavior: while
        # the model is streaming, the delete item is omitted from the menu,
        # and the Supr keyboard binding follows the same gate per the spec
        # scenario "Delete is a no-op during generation".
        if (
            key == wx.WXK_DELETE
            and not event.ControlDown()
            and not self._is_generating
        ):
            self._on_context_delete()
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
        # Look up reasoning from MainWindow._conversation
        reasoning: str | None = None
        parent = self.GetParent()
        while parent is not None and not hasattr(parent, "_conversation"):
            parent = parent.GetParent()
        if parent is not None:
            # Compute the conversation message index matching this history row.
            # System-role rows (tool blocked/denied) have no counterpart.
            if role != "system":
                system_count = sum(
                    1 for r, _ in self._history[:sel] if r == "system"
                )
                conv_index = sel - system_count
                if 0 <= conv_index < len(parent._conversation.messages):
                    reasoning = parent._conversation.messages[conv_index].get("reasoning") or None

        from bellbird.ui.message_detail_dialog import MessageDetailDialog

        dlg = MessageDetailDialog(self, role, text, reasoning=reasoning)
        dlg.ShowModal()
        dlg.Destroy()

    # ── Attachment methods (unchanged from v0.2.0) ──────────────────────────

    def _on_attach(self) -> None:
        """Open file dialog and handle attachment.

        Offers image/text, image folder, ZIP of images, or video.
        Folder and ZIP use core/media.py helpers.
        """
        choices = [
            "Imagen o archivo de texto",
            "Carpeta de imágenes",
            "ZIP de imágenes",
            "Video (requiere ffmpeg)",
        ]
        dlg = wx.SingleChoiceDialog(
            self, "¿Qué tipo de archivo adjuntar?", "Tipo de adjunto", choices
        )
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        choice_idx = dlg.GetSelection()
        dlg.Destroy()

        if choice_idx == 0:
            self._attach_single_file()
        elif choice_idx == 1:
            self._attach_folder()
        elif choice_idx == 2:
            self._attach_zip()
        elif choice_idx == 3:
            self._attach_video()

    def _attach_single_file(self) -> None:
        dialog = wx.FileDialog(
            self,
            message="Adjuntar archivo",
            defaultDir="",
            defaultFile="",
            wildcard="Todos los archivos (*.*)|*.*",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        )
        if dialog.ShowModal() == wx.ID_OK:
            self.attach_file(dialog.GetPath())
        dialog.Destroy()

    def _attach_folder(self) -> None:
        dlg = wx.DirDialog(self, "Seleccionar carpeta de imágenes", style=wx.DD_DEFAULT_STYLE)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        folder = dlg.GetPath()
        dlg.Destroy()
        self._speech.speak("Cargando imágenes de la carpeta...", interrupt=True)
        import threading
        def worker():
            from bellbird.core.media import images_from_folder
            images, err = images_from_folder(folder)
            wx.CallAfter(self._on_media_loaded, images, err, f"Carpeta: {Path(folder).name}")
        threading.Thread(target=worker, daemon=True).start()

    def _attach_zip(self) -> None:
        dlg = wx.FileDialog(
            self, "Seleccionar ZIP de imágenes", wildcard="ZIP (*.zip)|*.zip",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        )
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        zip_path = dlg.GetPath()
        dlg.Destroy()
        self._speech.speak("Descomprimiendo imágenes...", interrupt=True)
        import threading
        def worker():
            from bellbird.core.media import images_from_zip
            images, err = images_from_zip(zip_path)
            wx.CallAfter(self._on_media_loaded, images, err, Path(zip_path).name)
        threading.Thread(target=worker, daemon=True).start()

    def _attach_video(self) -> None:
        dlg = wx.FileDialog(
            self, "Seleccionar video",
            wildcard="Video (*.mp4;*.avi;*.mkv;*.mov)|*.mp4;*.avi;*.mkv;*.mov",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        )
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        video_path = dlg.GetPath()
        dlg.Destroy()
        self._speech.speak("Extrayendo frames del video...", interrupt=True)
        import threading
        def worker():
            from bellbird.core.media import keyframes_from_video
            images, err = keyframes_from_video(video_path)
            wx.CallAfter(self._on_media_loaded, images, err, Path(video_path).name)
        threading.Thread(target=worker, daemon=True).start()

    def _on_media_loaded(
        self, images: list, err: str | None, label: str
    ) -> None:
        """Called via wx.CallAfter after background media loading."""
        if err or not images:
            msg = err or "No se encontraron imágenes."
            self._speech.speak(f"Error al adjuntar: {msg}", interrupt=True)
            return
        self._attached_images = images
        self._attached_text = None
        n = len(images)
        self.attachment_label.SetLabel(f"{label} ({n} imágenes)")
        self._speech.speak(
            f"{n} {'imagen' if n == 1 else 'imágenes'} adjuntas desde {label}",
            interrupt=True,
        )

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

    def attach_url(self, url: str, text: str, origin_label: str) -> None:
        """Attach fetched web page text as message context.

        Mirrors the ``attach_file`` text path: stores the fetched text
        in ``_attached_text``, clears any previously attached images,
        and updates the attachment label.

        Empty text is a no-op — does not clear an existing attachment
        and does not speak.

        Args:
            url: The URL that was fetched (for potential future use).
            text: The fetched text content.
            origin_label: Human-readable label for the attachment
                (e.g. ``"example.com/docs/page"``).
        """
        if not text:
            return  # No-op for empty text

        # If there are attached images, announce replacement before clearing
        if self._attached_images:
            try:
                self._speech.speak("Imagen reemplazada", interrupt=False)
            except Exception:
                pass
            self._attached_images = []

        self._attached_text = text
        self.attachment_label.SetLabel(origin_label)
        # Spec contract (chat/spec.md scenario "select_and_announce for
        # attached URL"): announce the attachment with the origin label so
        # the screen reader user gets a clear confirmation of what was
        # attached. interrupt=True so the announcement is not lost in
        # background speech.
        try:
            self._speech.speak(
                f"Contenido adjunto: {origin_label}", interrupt=True
            )
        except Exception:
            pass

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
        self._streaming_index = None
        self.message_list.Clear()
        self._history.clear()
        self._clear_input()
        self.clear_attachment()

    # ── Quick actions (v0.8.0) ─────────────────────────────────────────────

    def copy_last_message(self) -> None:
        """Copy the FULL text of the last assistant (or user) message.

        - Last assistant row wins over last user row.
        - Empty history → no-op + ``"Nada que copiar"``.
        """
        if not self._history:
            self._speech.speak("Nada que copiar", interrupt=False)
            return
        # Find last assistant; fallback to last user
        text: str | None = None
        for role, t in reversed(self._history):
            if role == "assistant" and text is None:
                text = t
            if role == "user" and text is None:
                text = t
            if text is not None:
                break
        if text is None:
            self._speech.speak("Nada que copiar", interrupt=False)
            return
        # Copy FULL text to clipboard
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(text))
            wx.TheClipboard.Close()
        self._speech.speak("Último mensaje copiado", interrupt=False)

    def delete_last_exchange(self) -> None:
        """Remove the last user/assistant exchange pair.

        An "exchange" is either the last ``(user, assistant)`` pair or a
        single trailing ``(user, ...)`` when there is no matching assistant.
        No-op mid-generation with ``"Generación en curso"``.
        """
        if self._is_generating:
            self._speech.speak("Generación en curso", interrupt=False)
            return
        if len(self._history) < 1:
            return
        # Remove trailing assistant + user (or just trailing user)
        if len(self._history) >= 2 and self._history[-1][0] == "assistant":
            # Exchange: user + assistant at the end
            # Remove assistant first (capture role before pop)
            role_a = self._history[-1][0]
            index_a = len(self._history) - 1
            self._history.pop(index_a)
            self.message_list.Delete(index_a)
            if self._on_delete_callback:
                self._on_delete_callback(index_a, role_a)

            # Remove user
            role_u = self._history[-1][0]
            index_u = len(self._history) - 1
            self._history.pop(index_u)
            self.message_list.Delete(index_u)
            if self._on_delete_callback:
                self._on_delete_callback(index_u, role_u)
        else:
            # Single trailing user row
            role = self._history[-1][0]
            index = len(self._history) - 1
            self._history.pop(index)
            self.message_list.Delete(index)
            if self._on_delete_callback:
                self._on_delete_callback(index, role)

        # Update selection
        count = self.message_list.GetCount()
        if count > 0:
            self.message_list.SetSelection(count - 1)
        self._speech.speak("Último intercambio eliminado", interrupt=False)

    def edit_message(self, direction: str) -> None:
        """Load a previous user message into the input for editing.

        ``"prev"`` targets the last user message before the last assistant.
        ``"next"`` is a no-op with ``"No hay mensaje siguiente"``.
        """
        if direction == "next":
            self._speech.speak("No hay mensaje siguiente", interrupt=False)
            return

        # direction == "prev": find last user row that is not the very last row
        # (the last user row is the one we might be editing)
        user_idx: int | None = None
        for i in range(len(self._history) - 1, -1, -1):
            if self._history[i][0] == "user":
                user_idx = i
                break

        if user_idx is None:
            self._speech.speak("No hay mensaje anterior", interrupt=False)
            return

        text = self._history[user_idx][1]
        self.message_input.SetValue(text)
        self.message_input.SetInsertionPointEnd()
        self.message_input.SetFocus()

        # Compute conversation index (subtract system rows before the target)
        system_count = sum(
            1 for r, _ in self._history[:user_idx] if r == "system"
        )
        conv_idx = user_idx - system_count

        # Truncate Conversation via callback
        if self._on_truncate_callback:
            self._on_truncate_callback(conv_idx)

        # Trim _history and rebuild display
        new_history = self._history[: user_idx + 1]
        self.set_history(new_history)
        self._speech.speak("Mensaje cargado para editar", interrupt=False)

    def regenerate_last(self) -> None:
        """Pop the last assistant response and re-send the same user prompt.

        No-op mid-generation or when no assistant row exists.
        """
        if self._is_generating:
            self._speech.speak("Generación en curso", interrupt=False)
            return

        # Find the last assistant row
        assistant_idx: int | None = None
        for i in range(len(self._history) - 1, -1, -1):
            if self._history[i][0] == "assistant":
                assistant_idx = i
                break

        if assistant_idx is None:
            self._speech.speak("Nada que regenerar", interrupt=False)
            return

        # Find the user row that precedes this assistant
        user_idx: int | None = None
        for i in range(assistant_idx - 1, -1, -1):
            if self._history[i][0] == "user":
                user_idx = i
                break

        if user_idx is None:
            self._speech.speak("Nada que regenerar", interrupt=False)
            return

        user_text = self._history[user_idx][1]

        # Capture role before popping
        role = self._history[assistant_idx][0]
        index = assistant_idx

        # Pop assistant row from _history and message_list
        self._history.pop(index)
        self.message_list.Delete(index)

        # Sync Conversation
        if self._on_delete_callback:
            self._on_delete_callback(index, role)

        # Set input to user text and trigger send
        self.message_input.SetValue(user_text)
        self.message_input.SetInsertionPointEnd()

        # Call the regenerate send callback (handles image re-attachment)
        if self._on_regenerate_send_callback:
            self._on_regenerate_send_callback(user_text, user_idx)
        elif self._on_send_callback:
            self._on_send_callback()

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
