"""MainWindow — top-level application shell for OllamaChat.

Integrates ParamsPanel (left) and ChatPanel (right) in a SplitterWindow,
manages menu bar, accelerator table, status bar, and coordinates the
full send/receive flow between OllamaClient, Conversation, and Speech.
"""

import wx

from ollamachat.core.conversation import Conversation
from ollamachat.core.logger import get_logger
from ollamachat.core.ollama_client import OllamaClient
from ollamachat.core.ollama_runner import start_ollama
from ollamachat.core.speech import Speech
from ollamachat.ui.chat_panel import ChatPanel
from ollamachat.ui.params_panel import ParamsPanel


class MainWindow(wx.Frame):
    """Top-level application window.

    Args:
        parent: Parent window (None for top-level).
        title: Window title.
    """

    def __init__(
        self, parent: wx.Window | None = None, title: str = "OllamaChat"
    ) -> None:
        super().__init__(parent, title=title, size=(1100, 700))
        self._client = OllamaClient()
        self._conversation = Conversation()
        self._speech = Speech()
        self._current_response: str = ""

        self._build_ui()
        self._build_menu()
        self._build_accelerators()
        self._create_status_bar()
        self._startup_check()

    # ── UI Construction ───────────────────────────────────────────────────

    def _build_ui(self) -> None:
        """Build the splitter layout with ParamsPanel and ChatPanel."""
        self.splitter = wx.SplitterWindow(self, name="main_splitter")
        self.splitter.SetMinimumPaneSize(280)

        self.params_panel = ParamsPanel(self.splitter, self._speech)
        self.chat_panel = ChatPanel(
            self.splitter, self._speech, on_send=self.send_message
        )

        self.splitter.SplitVertically(
            self.params_panel, self.chat_panel, sashPosition=280
        )

        # ── Top toolbar: start Ollama server ───────────────────────────
        self.start_ollama_button = wx.Button(
            self, label="Iniciar Ollama", name="start_ollama_button"
        )
        self.start_ollama_button.Bind(
            wx.EVT_BUTTON, lambda evt: self._on_start_ollama()
        )

        toolbar_sizer = wx.BoxSizer(wx.HORIZONTAL)
        toolbar_sizer.Add(
            wx.StaticText(self, label="Servidor:"),
            flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4,
        )
        toolbar_sizer.Add(
            self.start_ollama_button, flag=wx.ALIGN_CENTER_VERTICAL
        )

        # Wire up chat panel actions to MainWindow handlers
        self.chat_panel.send_button.Bind(wx.EVT_BUTTON, lambda evt: self.send_message())
        self.chat_panel.stop_button.Bind(
            wx.EVT_BUTTON, lambda evt: self.abort_generation()
        )
        self.chat_panel.clear_button.Bind(
            wx.EVT_BUTTON, lambda evt: self.new_conversation()
        )

        # Wire up refresh models button
        self.params_panel.refresh_models_button.Bind(
            wx.EVT_BUTTON, lambda evt: self._refresh_models()
        )

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(toolbar_sizer, flag=wx.ALL, border=8)
        sizer.Add(self.splitter, proportion=1, flag=wx.EXPAND)
        self.SetSizer(sizer)

    def _build_menu(self) -> None:
        """Build the menu bar with Archivo and Ayuda menus."""
        menu_bar = wx.MenuBar()

        # ── Archivo menu ──────────────────────────────────────────────
        archivo_menu = wx.Menu()
        menu_new = archivo_menu.Append(
            wx.ID_NEW, "Nueva conversación\tCtrl+N", "Comenzar una nueva conversación"
        )
        menu_new.SetName("menu_new")
        self.Bind(wx.EVT_MENU, lambda evt: self.new_conversation(), menu_new)

        menu_open = archivo_menu.Append(
            wx.ID_OPEN, "Abrir\tCtrl+O", "Abrir una conversación guardada"
        )
        menu_open.SetName("menu_open")
        self.Bind(wx.EVT_MENU, lambda evt: self.load_conversation(), menu_open)

        menu_save = archivo_menu.Append(
            wx.ID_SAVE, "Guardar\tCtrl+S", "Guardar la conversación actual"
        )
        menu_save.SetName("menu_save")
        self.Bind(wx.EVT_MENU, lambda evt: self.save_conversation(), menu_save)

        archivo_menu.AppendSeparator()

        menu_exit = archivo_menu.Append(
            wx.ID_EXIT, "Salir\tAlt+F4", "Salir de OllamaChat"
        )
        menu_exit.SetName("menu_exit")
        self.Bind(wx.EVT_MENU, lambda evt: self.Close(), menu_exit)

        menu_bar.Append(archivo_menu, "Archivo")

        # ── Ayuda menu ────────────────────────────────────────────────
        ayuda_menu = wx.Menu()
        menu_about = ayuda_menu.Append(
            wx.ID_ABOUT, "Acerca de", "Acerca de OllamaChat"
        )
        menu_about.SetName("menu_about")
        self.Bind(wx.EVT_MENU, lambda evt: self._show_about(), menu_about)

        menu_shortcuts = ayuda_menu.Append(
            wx.ID_PREFERENCES,
            "Atajos de teclado",
            "Ver atajos de teclado disponibles",
        )
        menu_shortcuts.SetName("menu_shortcuts")
        self.Bind(
            wx.EVT_MENU, lambda evt: self._show_shortcuts(), menu_shortcuts
        )

        menu_bar.Append(ayuda_menu, "Ayuda")

        self.SetMenuBar(menu_bar)

    def _build_accelerators(self) -> None:
        """Build accelerator table for keyboard shortcuts."""
        accel_entries = [
            wx.AcceleratorEntry(wx.ACCEL_CTRL, ord("N"), wx.ID_NEW),
            wx.AcceleratorEntry(wx.ACCEL_CTRL, ord("O"), wx.ID_OPEN),
            wx.AcceleratorEntry(wx.ACCEL_CTRL, ord("S"), wx.ID_SAVE),
            wx.AcceleratorEntry(wx.ACCEL_NORMAL, wx.WXK_F5, wx.ID_REFRESH),
            wx.AcceleratorEntry(wx.ACCEL_NORMAL, wx.WXK_ESCAPE, wx.ID_STOP),
        ]

        # Bind accelerators
        self.Bind(
            wx.EVT_MENU,
            lambda evt: self._refresh_models(),
            id=wx.ID_REFRESH,
        )
        self.Bind(
            wx.EVT_MENU,
            lambda evt: self.abort_generation(),
            id=wx.ID_STOP,
        )

        accel_table = wx.AcceleratorTable(accel_entries)
        self.SetAcceleratorTable(accel_table)

    def _create_status_bar(self) -> None:
        """Create status bar with 3 fields."""
        self.status_bar = self.CreateStatusBar(number=3, name="status_bar")
        self.status_bar.SetStatusText("Iniciando...", 0)
        self.status_bar.SetStatusText("", 1)
        self.status_bar.SetStatusText("", 2)

    # ── Startup ────────────────────────────────────────────────────────────

    def _startup_check(self) -> None:
        """Check if Ollama is running and populate model list."""
        log = get_logger()
        if self._client.check_running():
            log.info("Startup: Ollama detected")
            self.status_bar.SetStatusText("Conectado", 0)
            self._speech.speak("Conectado", interrupt=True)
            self._refresh_models()
        else:
            msg = (
                "No se puede conectar a Ollama en "
                "http://localhost:11434. "
                "Asegurate de que Ollama esté instalado y ejecutándose."
            )
            log.warning("Startup: Ollama not detected")
            self.status_bar.SetStatusText("Desconectado", 0)
            self._speech.speak(msg, interrupt=True)
            wx.MessageDialog(
                self,
                message=msg,
                caption="Ollama no detectado",
                style=wx.OK | wx.ICON_WARNING,
            ).ShowModal()

    def _refresh_models(self) -> None:
        """Refresh the model list from Ollama."""
        log = get_logger()
        models = self._client.list_models()
        self.params_panel.set_models(models)
        if models:
            log.info(f"Models refreshed: {len(models)} available")
            self.status_bar.SetStatusText(f"Modelo: {models[0]}", 1)
            self._speech.speak(f"Modelo: {models[0]}", interrupt=True)
        else:
            log.warning("No models returned from Ollama")

    def _on_start_ollama(self) -> None:
        """Start the Ollama server via subprocess.

        Delegates the actual subprocess work to
        :func:`ollamachat.core.ollama_runner.start_ollama` and only
        handles the UI side: logging, status bar updates, and the
        spoken announcement.
        """
        log = get_logger()
        log.info("Start Ollama button clicked")

        self.status_bar.SetStatusText("Iniciando Ollama...", 0)
        self._speech.speak("Iniciando Ollama", interrupt=True)

        ok, message = start_ollama(self._client)
        log.info(f"start_ollama returned ok={ok}, message={message!r}")
        self._speech.speak(message, interrupt=True)

        if ok:
            self.status_bar.SetStatusText("Conectado", 0)
            if "ya está" not in message:
                # Only refresh models if we just started the server
                self._refresh_models()
        else:
            self.status_bar.SetStatusText("Error", 0)

    # ── Message Send Flow ──────────────────────────────────────────────────

    def send_message(self) -> None:
        """Build API payload and start streaming."""
        # Read input and attachments
        user_text = self.chat_panel.get_input_text()
        if not user_text.strip():
            return

        # Build API messages
        api_messages = []

        # System prompt (if non-empty)
        system_prompt = self.params_panel.get_system_prompt()
        if system_prompt.strip():
            api_messages.append({"role": "system", "content": system_prompt})

        # Conversation history
        api_messages.extend(self._conversation.get_messages_for_api())

        # New user message
        user_msg: dict = {"role": "user", "content": user_text}
        attached_images = self.chat_panel.get_attached_images()
        attached_text = self.chat_panel.get_attached_text()
        if attached_text:
            user_msg["content"] = (
                f"{user_text}\n\n"
                f"[Contenido del archivo adjuntado]\n{attached_text}"
            )
        if attached_images:
            user_msg["images"] = attached_images
        api_messages.append(user_msg)

        # Clear input and attachment
        self.chat_panel._clear_input()
        self.chat_panel.clear_attachment()

        # Add to conversation and display (augmented content if text attached)
        self._conversation.add_message("user", user_msg["content"], images=attached_images)
        self.chat_panel.append_user_message(user_msg["content"])

        # Start generation
        model = self.params_panel.get_model()
        options = self.params_panel.get_params()
        self._current_response = ""

        self.chat_panel.start_generation()
        self.chat_panel.append_assistant_prefix()

        self.status_bar.SetStatusText("Generando respuesta...", 2)
        self._speech.speak("Generando respuesta...", interrupt=True)

        self._client.chat_stream(
            model=model,
            messages=api_messages,
            options=options,
            on_token=self._on_token,
            on_done=self._on_done,
            on_error=self._on_error,
        )

    def _on_token(self, token: str) -> None:
        """Handle a token fragment from the stream.

        Args:
            token: Token text from the LLM.
        """
        self._current_response += token
        self.chat_panel.append_assistant_chunk(token)
        self._speech.announce_token_chunk(token)

    def _on_done(self) -> None:
        """Handle stream completion."""
        self._speech.flush_token_buffer()
        self._speech.speak("Respuesta completa", interrupt=True)

        # Save assistant message to conversation
        if self._current_response.strip():
            self._conversation.add_message(
                "assistant", self._current_response
            )

        self.chat_panel.end_generation()
        self.status_bar.SetStatusText("", 2)
        self._current_response = ""

    def _on_error(self, error_text: str) -> None:
        """Handle stream error.

        Args:
            error_text: Error description.
        """
        self._current_response = ""
        self.chat_panel.append_assistant_chunk(f"\n[Error: {error_text}]")
        self.chat_panel.end_generation()
        self.status_bar.SetStatusText("Error", 2)
        self._speech.speak(error_text, interrupt=True)
        wx.MessageDialog(
            self,
            message=error_text,
            caption="Error",
            style=wx.OK | wx.ICON_ERROR,
        ).ShowModal()

    # ── Abort ──────────────────────────────────────────────────────────────

    def abort_generation(self) -> None:
        """Abort the current generation."""
        self._client.abort()

    # ── Save / Load ─────────────────────────────────────────────────────────

    def save_conversation(self) -> None:
        """Save the current conversation to a file."""
        dialog = wx.FileDialog(
            self,
            message="Guardar conversación",
            defaultDir="",
            defaultFile="conversacion.json",
            wildcard="Archivos JSON (*.json)|*.json",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )
        if dialog.ShowModal() == wx.ID_OK:
            filepath = dialog.GetPath()
            Conversation.save(self._conversation, filepath)
            self._speech.speak("Conversación guardada", interrupt=True)
        dialog.Destroy()

    def load_conversation(self) -> None:
        """Load a conversation from a file."""
        dialog = wx.FileDialog(
            self,
            message="Abrir conversación",
            defaultDir="",
            defaultFile="",
            wildcard="Archivos JSON (*.json)|*.json",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        )
        if dialog.ShowModal() == wx.ID_OK:
            filepath = dialog.GetPath()
            try:
                self._conversation = Conversation.load(filepath)
                # Rebuild display
                self.chat_panel.clear()
                for msg in self._conversation.messages:
                    if msg["role"] == "user":
                        self.chat_panel.append_user_message(msg["content"])
                    elif msg["role"] == "assistant":
                        self.chat_panel.append_assistant_chunk(
                            f"[Asistente] {msg['content']}\n"
                        )
                self._speech.speak("Conversación cargada", interrupt=True)
            except Exception as e:
                error_msg = f"No se pudo cargar la conversación: {e}"
                self._speech.speak(error_msg, interrupt=True)
                wx.MessageDialog(
                    self,
                    message=error_msg,
                    caption="Error",
                    style=wx.OK | wx.ICON_ERROR,
                ).ShowModal()
        dialog.Destroy()

    # ── New Conversation ────────────────────────────────────────────────────

    def new_conversation(self) -> None:
        """Start a new conversation, clearing current state."""
        self._conversation.clear()
        self.chat_panel.clear()
        self._current_response = ""
        self._speech.speak("Nueva conversación", interrupt=True)

    # ── Help Dialogs ────────────────────────────────────────────────────────

    def _show_about(self) -> None:
        """Show About dialog."""
        about_msg = (
            "OllamaChat v0.1.0\n\n"
            "Cliente accesible de chat para Ollama.\n"
            "Diseñado para usuarios de lectores de pantalla."
        )
        self._speech.speak(about_msg, interrupt=True)
        wx.MessageDialog(
            self,
            message=about_msg,
            caption="Acerca de OllamaChat",
            style=wx.OK | wx.ICON_INFORMATION,
        ).ShowModal()

    def _show_shortcuts(self) -> None:
        """Show keyboard shortcuts dialog."""
        shortcuts = (
            "Atajos de teclado:\n\n"
            "Ctrl+N: Nueva conversación\n"
            "Ctrl+O: Abrir conversación\n"
            "Ctrl+S: Guardar conversación\n"
            "F5: Actualizar modelos\n"
            "Escape: Detener generación\n"
            "Enter: Enviar mensaje\n"
            "Shift+Enter: Nueva línea en el input"
        )
        self._speech.speak(shortcuts, interrupt=True)
        wx.MessageDialog(
            self,
            message=shortcuts,
            caption="Atajos de teclado",
            style=wx.OK | wx.ICON_INFORMATION,
        ).ShowModal()
