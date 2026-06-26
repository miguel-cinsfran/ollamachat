"""MainWindow — top-level application shell for Bellbird.

Vertical BoxSizer layout: top row (model selector + server controls),
ChatPanel (full width). Coordinates the send/receive flow between
LlamaClient, LlamaRunner, Conversation, and Speech.
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser

import wx

from pathlib import Path

from bellbird.core.conversation import Conversation
from bellbird.core.llama_client import LlamaClient
from bellbird.core.llama_runner import (
    find_gguf_models,
    find_llama_server,
    get_install_command,
    start_server,
    stop_server,
)
from bellbird.core.html_render import render_message_html
from bellbird.core.startup import probe as startup_probe
from bellbird.core.logger import get_logger, get_log_path
from bellbird.core.speech import Speech
from bellbird.ui.chat_panel import ChatPanel
from bellbird.core.config import (
    BellbirdConfig,
    load_config,
    save_config,
    should_auto_restore,
    update_recents,
)
from bellbird.core.keymap import Keymap, DEFAULT_KEYMAP, KEYMAP_MOD_NONE
from bellbird.core.model_meta import find_mmproj_for_model
from bellbird.core.permission_manager import PermissionManager
from bellbird.core.tool_executor import ToolExecutor, ToolResult
from bellbird.ui.permission_dialog import PermissionDialog
from bellbird.ui.preferences_dialog import PreferencesDialog
from bellbird.ui.wx_notifier import WxToastSender
from bellbird.core.notifier import Notifier
from bellbird.core.system_voice import SystemVoice
from bellbird.core.sound_player import SoundPlayer
from bellbird.core.text_utils import strip_markdown
from bellbird.core.status_formatter import SessionSnapshot, format_status
from bellbird.core.context_advisor import read_vram, estimate_fit, pre_send_check, PreSendSnapshot, token_count
from bellbird.core.model_meta import read_gguf_metadata, estimate_size_bytes, GGUFMetadata
from bellbird.core.payload import build_options, build_api_messages

SHELL_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "shell_execute",
        "description": (
            "Ejecuta un comando en PowerShell en el sistema Windows del "
            "usuario. Usa esto para operaciones de archivos, sistema, o "
            "cuando el usuario lo pide explicitamente."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "El comando de PowerShell a ejecutar.",
                }
            },
            "required": ["command"],
        },
    },
}


class _NullToastSender:
    """No-op toast sender for non-win32 platforms."""

    def show(self, title: str, message: str, timeout: int = 5) -> None:
        pass


class MainWindow(wx.Frame):
    """Top-level application window.

    Args:
        parent: Parent window (None for top-level).
        title: Window title.
    """

    def __init__(
        self, parent: wx.Window | None = None, title: str = "Bellbird"
    ) -> None:
        super().__init__(parent, title=title, size=(900, 650))
        self._config = load_config()
        self._client = LlamaClient(
            base_url=f"http://localhost:{self._config.port}",
            request_timeout=getattr(
                self._config, "request_timeout", 120
            ),
        )
        self._conversation = Conversation()
        self._speech = Speech()

        # Audio output subsystems (v0.10.0)
        self._sound_player = SoundPlayer(
            theme=self._config.sound_theme,
        )
        self._system_voice = SystemVoice(
            voice_name=self._config.system_voice_name,
            rate=self._config.system_voice_rate,
        )
        if sys.platform == "win32":
            self._toast = WxToastSender(parent=self)
        else:
            self._toast = _NullToastSender()
        self._notifier = Notifier(
            focus_check=lambda: not self.IsActive(),
            toast_sender=self._toast,
            sound_player=self._sound_player,
            notifications_enabled=self._config.notifications_enabled,
            sounds_enabled=self._config.sounds_enabled,
            sound_theme=self._config.sound_theme,
        )
        self._current_response: str = ""
        self._current_reasoning: str = ""
        self._is_generating = False
        self._aborted = False
        self._is_closing = False
        self._temp_html_files: list[str] = []
        self._last_usage: dict | None = None
        self._permission_manager = PermissionManager()
        self._tool_executor = ToolExecutor()
        self._focus_cycle_index = 0
        self._last_beep_time = 0.0
        self._loading_timer: threading.Timer | None = None
        self._url_fetch_timer: threading.Timer | None = None
        self._model_load_thread: threading.Thread | None = None
        self._basename_to_path: dict[str, str] = {}
        self._vision_capable: bool = False
        self._tool_iteration_count: int = 0
        self._tool_executing: bool = False
        self._recent_items: dict[int, str] = {}
        self._recents_menu: wx.Menu | None = None
        self._archivo_menu: wx.Menu | None = None

        # v0.9.0: context advisor + toggleable F2 state
        self._latest_prompt_tokens: int | None = None
        self._latest_completion_tokens: int | None = None
        self._latest_tok_per_s: float | None = None
        self._current_n_ctx: int | None = None
        self._vram_free_mb: int | None = None
        self._vram_total_mb: int | None = None
        self._fit_status: str | None = None
        self._pre_send_warned_this_conv: bool = False
        self._context_warned_for_turn: bool = False
        self._last_f2_mono: float | None = None
        self._meter_threshold_fired: bool = False

        # Must be defined before _build_menu() which uses them for Append() IDs.
        self.ID_START_SERVER = wx.NewIdRef()
        self.ID_STOP_SERVER = wx.NewIdRef()

        # Keymap accelerator IDs — populated by _build_accelerators, reused on rebuild.
        # start_server/stop_server use the existing IDs so menu items keep working.
        self._action_ids: dict[str, wx.NewIdRef] = {
            "start_server": self.ID_START_SERVER,
            "stop_server": self.ID_STOP_SERVER,
        }
        self._keymap: Keymap = Keymap(DEFAULT_KEYMAP)

        self._build_ui()
        self._build_menu()
        self._build_accelerators()
        self._create_status_bar()
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self._start_probe_thread()
        wx.CallAfter(self._set_initial_focus)
        wx.CallAfter(self._auto_restore_last_session)

    # ── UI Construction ───────────────────────────────────────────────────

    def _build_ui(self) -> None:
        """Build the vertical BoxSizer layout: top row + ChatPanel."""
        # wx.Frame does not propagate Tab key to child controls on Windows.
        # All interactive controls must be children of this Panel, not the Frame.
        main_panel = wx.Panel(self)

        # ── Model selector ────────────────────────────────────────────
        # StaticText created BEFORE ComboBox: Windows UIA assigns accName by
        # z-order (creation order), not sizer order.
        modelo_label = wx.StaticText(main_panel, label="Modelo:")
        self.model_selector = wx.ComboBox(
            main_panel, name="Selector de modelo", style=wx.CB_READONLY
        )
        self.model_selector.Bind(wx.EVT_COMBOBOX, self._on_model_select)
        self.model_selector.SetToolTip(
            "Selecciona un modelo .gguf. Para rutas personalizadas usa Explorar..."
        )

        self.scan_models_button = wx.Button(
            main_panel, label="Buscar modelos", name="scan_models_button"
        )
        self.browse_model_button = wx.Button(
            main_panel, label="Explorar...", name="browse_model_button"
        )
        self.use_model_button = wx.Button(
            main_panel, label="Usar modelo", name="use_model_button"
        )
        self.use_model_button.Disable()

        # ── Server controls ───────────────────────────────────────────
        servidor_label = wx.StaticText(main_panel, label="Servidor:")
        self.restart_server_button = wx.Button(
            main_panel, label="Iniciar servidor", name="restart_server_button"
        )
        self.stop_server_button = wx.Button(
            main_panel, label="Detener servidor", name="stop_server_button"
        )
        self.stop_server_button.Disable()

        # ── Top row: model controls + server controls ─────────────────
        top_row = wx.BoxSizer(wx.HORIZONTAL)

        top_row.Add(modelo_label, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)
        top_row.Add(self.model_selector, proportion=1, flag=wx.EXPAND)
        top_row.Add(self.scan_models_button, flag=wx.LEFT, border=4)
        top_row.Add(self.browse_model_button, flag=wx.LEFT, border=4)
        top_row.Add(self.use_model_button, flag=wx.LEFT, border=4)

        top_row.AddSpacer(20)

        top_row.Add(servidor_label, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4)
        top_row.Add(
            self.restart_server_button, flag=wx.ALIGN_CENTER_VERTICAL
        )
        top_row.Add(
            self.stop_server_button,
            flag=wx.ALIGN_CENTER_VERTICAL | wx.LEFT, border=4,
        )

        # ── Chat panel ────────────────────────────────────────────────
        self.chat_panel = ChatPanel(
            main_panel, self._speech,
            on_send=self.send_message,
            on_delete_message=self._on_history_delete,
            on_regenerate_send=self._on_regenerate_send_callback,
            on_truncate_history=self._on_truncate_history_callback,
        )

        # ── Root vertical sizer ───────────────────────────────────────
        root_sizer = wx.BoxSizer(wx.VERTICAL)
        root_sizer.Add(top_row, flag=wx.EXPAND | wx.ALL, border=8)
        root_sizer.Add(self.chat_panel, proportion=1, flag=wx.EXPAND)
        main_panel.SetSizer(root_sizer)

        # ── Wire buttons ──────────────────────────────────────────────
        self.scan_models_button.Bind(
            wx.EVT_BUTTON, lambda evt: self._scan_models()
        )
        self.browse_model_button.Bind(
            wx.EVT_BUTTON, lambda evt: self._on_browse_model()
        )
        self.use_model_button.Bind(
            wx.EVT_BUTTON, lambda evt: self._on_use_model()
        )
        self.restart_server_button.Bind(
            wx.EVT_BUTTON, lambda evt: self._on_start_server()
        )
        self.stop_server_button.Bind(
            wx.EVT_BUTTON, lambda evt: self._on_stop_server()
        )
        self.chat_panel.send_button.Bind(
            wx.EVT_BUTTON, lambda evt: self.send_message()
        )
        self.chat_panel.stop_button.Bind(
            wx.EVT_BUTTON, lambda evt: self.abort_generation()
        )
        self.chat_panel.clear_button.Bind(
            wx.EVT_BUTTON, lambda evt: self.new_conversation()
        )

    # ── Model control helpers ──

    def set_models(self, paths: list[str]) -> None:
        """Populate the model selector with .gguf file basenames.

        Replaces the entire selection. Used by the "Buscar modelos" scan.
        After populating, selects the previously-used model (last_model)
        if it is in the list; otherwise selects the first entry.

        Args:
            paths: List of absolute paths to .gguf files.
        """
        self.model_selector.Clear()
        self._basename_to_path.clear()
        for path_str in paths:
            path = Path(path_str)
            self._basename_to_path[path.name] = str(path)
            self.model_selector.Append(path.name)
        if self.model_selector.GetCount() == 0:
            self.use_model_button.Disable()
            return
        preferred = self._config.last_model
        idx = self.model_selector.FindString(preferred) if preferred else wx.NOT_FOUND
        if idx == wx.NOT_FOUND:
            idx = 0
        self.model_selector.SetSelection(idx)
        self.use_model_button.Enable()

    def add_model(self, path_str: str) -> bool:
        """Add a single .gguf file to the selector without clearing.

        If a model with the same basename is already in the selector,
        the selection moves to it instead of duplicating.

        Args:
            path_str: Absolute path to a .gguf file.

        Returns:
            True if the model was added or already present. False if
            the path is not a .gguf file or does not exist.
        """
        path = Path(path_str)
        if path.suffix.lower() != ".gguf":
            return False
        if not path.is_file():
            return False

        basename = path.name
        if basename in self._basename_to_path:
            index = self.model_selector.FindString(basename)
            if index != wx.NOT_FOUND:
                self.model_selector.SetSelection(index)
            return True
        self._basename_to_path[basename] = str(path)
        self.model_selector.Append(basename)
        self.model_selector.SetSelection(self.model_selector.GetCount() - 1)
        self.use_model_button.Enable()
        return True

    def get_model(self) -> str:
        """Get the full absolute path of the selected model.

        The selector is read-only, so the value is always one of the
        basenames populated by set_models / add_model. Resolution is a
        single dict lookup; the typed-path rule from the editable era
        is gone (manual paths now go through Explorar... + add_model).

        Returns:
            Absolute path string, or '' if no valid model selected.
        """
        value = self.model_selector.GetStringSelection()
        if not value:
            return ""
        return self._basename_to_path.get(value, "")

    def _on_model_select(self, event: wx.CommandEvent) -> None:
        """Handle model selector selection change."""
        if self.model_selector.GetCount() > 0:
            self.use_model_button.Enable()
        else:
            self.use_model_button.Disable()

    # ── Menu Bar ─────────────────────────────────────────────────────────

    def _build_menu(self) -> None:
        """Build the menu bar with Archivo and Ayuda menus."""
        menu_bar = wx.MenuBar()

        # ── Archivo menu ──────────────────────────────────────────────
        archivo_menu = wx.Menu()
        menu_new = archivo_menu.Append(
            wx.ID_NEW, "&Nueva conversación\tCtrl+N", "Comenzar una nueva conversación"
        )
        self.Bind(wx.EVT_MENU, lambda evt: self.new_conversation(), menu_new)

        menu_open = archivo_menu.Append(
            wx.ID_OPEN, "&Abrir\tCtrl+O", "Abrir una conversación guardada"
        )
        self.Bind(wx.EVT_MENU, lambda evt: self.load_conversation(), menu_open)

        menu_save = archivo_menu.Append(
            wx.ID_SAVE, "&Guardar\tCtrl+S", "Guardar la conversación actual"
        )
        self.Bind(wx.EVT_MENU, lambda evt: self.save_conversation(), menu_save)

        archivo_menu.AppendSeparator()

        # ── Recientes submenu ─────────────────────────────────────────
        self._recents_menu = wx.Menu()
        archivo_menu.Append(
            wx.ID_ANY, "&Recientes", self._recents_menu,
            "Abrir una conversación reciente",
        )

        archivo_menu.AppendSeparator()

        # ── Exportar a Markdown ───────────────────────────────────────
        menu_export = archivo_menu.Append(
            wx.ID_ANY, "&Exportar a Markdown...",
            "Exportar la conversación actual a Markdown",
        )
        self.Bind(wx.EVT_MENU, lambda evt: self._on_export(), menu_export)

        # ── Adjuntar URL ──────────────────────────────────────────────────
        menu_attach_url = wx.MenuItem(
            archivo_menu, wx.ID_ANY, "&Adjuntar URL...\tCtrl+U",
            "Adjuntar contenido de una URL como contexto del mensaje",
            name="menu_attach_url",
        )
        archivo_menu.Append(menu_attach_url)
        self.Bind(
            wx.EVT_MENU, lambda evt: self._on_attach_url(), menu_attach_url
        )

        archivo_menu.AppendSeparator()

        menu_prefs = archivo_menu.Append(
            wx.ID_PREFERENCES, "&Preferencias\tCtrl+,",
            "Abrir el diálogo de preferencias",
        )
        self.Bind(wx.EVT_MENU, lambda evt: self._show_preferences(), menu_prefs)

        menu_exit = archivo_menu.Append(
            wx.ID_EXIT, "&Salir\tAlt+F4", "Salir de Bellbird"
        )
        self.Bind(wx.EVT_MENU, lambda evt: self.Close(), menu_exit)

        menu_bar.Append(archivo_menu, "&Archivo")

        # ── Servidor menu ─────────────────────────────────────────────
        servidor_menu = wx.Menu()

        servidor_menu.Append(
            self.ID_START_SERVER, "&Iniciar servidor\tF7",
            "Iniciar llama-server con el modelo seleccionado",
        )
        # Bound to _on_use_model via ID_START_SERVER in _build_accelerators

        servidor_menu.Append(
            self.ID_STOP_SERVER, "&Detener servidor\tCtrl+F7",
            "Detener llama-server",
        )
        # Bound to _on_stop_server via ID_STOP_SERVER in _build_accelerators

        servidor_menu.AppendSeparator()

        servidor_menu.Append(
            wx.ID_REFRESH, "&Buscar modelos\tF5",
            "Buscar modelos .gguf en el sistema",
        )
        # Bound to _scan_models via wx.ID_REFRESH in _build_accelerators

        menu_bar.Append(servidor_menu, "&Servidor")

        # ── Ayuda menu ────────────────────────────────────────────────
        ayuda_menu = wx.Menu()
        menu_about = ayuda_menu.Append(
            wx.ID_ABOUT, "&Acerca de", "Acerca de Bellbird"
        )
        self.Bind(wx.EVT_MENU, lambda evt: self._show_about(), menu_about)

        self.ID_SHORTCUTS = wx.NewIdRef()
        menu_shortcuts = ayuda_menu.Append(
            self.ID_SHORTCUTS,
            "A&tajos de teclado",
            "Ver atajos de teclado disponibles",
        )
        self.Bind(
            wx.EVT_MENU, lambda evt: self._show_shortcuts(), menu_shortcuts
        )

        self.ID_OPEN_LOG = wx.NewIdRef()
        menu_log = ayuda_menu.Append(
            self.ID_OPEN_LOG,
            "Log de depuración",
            "Abrir el archivo de registro en el editor de texto",
        )
        self.Bind(wx.EVT_MENU, lambda evt: self._open_log_file(), menu_log)

        menu_bar.Append(ayuda_menu, "A&yuda")

        self._archivo_menu = archivo_menu
        self.Bind(wx.EVT_MENU_OPEN, self._on_menu_open)

        self.SetMenuBar(menu_bar)

    def _build_accelerators(self) -> None:
        """Build accelerator table from the resolved keymap.

        Iterates ``Keymap(defaults=DEFAULT_KEYMAP, overrides=...)`` and
        creates one ``wx.AcceleratorEntry`` per action. Handlers are bound
        via EVT_MENU with the action's command ID. The ``exit`` action
        is handled by the window manager and is excluded from the table.
        """
        km = Keymap(DEFAULT_KEYMAP, overrides=self._config.keymap_overrides)
        self._keymap = km

        # Handler dispatch: action_id → callable.
        # These are the single source of truth for what each accelerator does.
        from collections.abc import Callable
        handlers: dict[str, Callable[[], None]] = {
            "new_conversation": lambda: self.new_conversation(),
            "open_conversation": lambda: self.load_conversation(),
            "save_conversation": lambda: self.save_conversation(),
            "preferences": lambda: self._show_preferences(),
            "exit": lambda: self.Close(),
            "announce_status": lambda: self._announce_session_status(),
            "scan_models": lambda: self._scan_models(),
            "cycle_panels": lambda: self._on_f6_cycle(),
            "start_server": lambda: self._on_use_model(),
            "stop_server": lambda: self._on_stop_server(),
            "abort_generation": lambda: self.abort_generation(),
            "focus_chat": lambda: self.chat_panel.message_input.SetFocus(),
            "focus_params": lambda: self._on_focus_list(),
            "focus_models": lambda: self.model_selector.SetFocus(),
            "focus_server": lambda: self._on_focus_use(),
            "copy_last": lambda: self._on_copy_last(),
            "delete_last_exchange": lambda: self._on_delete_last_exchange(),
            "edit_previous": lambda: self._on_edit_previous(),
            "edit_next": lambda: self._on_edit_next(),
            "regenerate": lambda: self._on_regenerate_last(),
            "find_in_history": lambda: self._on_find(),
            "attach_url": lambda: self._on_attach_url(),
            "read_selected_message": lambda: self._on_read_selected_message(),
        }

        accel_entries: list[wx.AcceleratorEntry] = []
        # exit is handled by the window manager — skip it in the accelerator table
        skip_actions = {"exit"}

        for action_id, binding in km.actions.items():
            if action_id in skip_actions:
                continue
            # Create or reuse the wx command ID for this action
            if action_id not in self._action_ids:
                self._action_ids[action_id] = wx.NewIdRef()
            cmd_id = self._action_ids[action_id]
            entry = wx.AcceleratorEntry(binding.modifiers, binding.keycode, cmd_id)
            accel_entries.append(entry)

            # Bind the handler — capture by value to avoid closure issues
            handler = handlers.get(action_id)
            if handler is not None:
                self.Bind(
                    wx.EVT_MENU,
                    lambda evt, h=handler: h(),
                    id=cmd_id,
                )

        accel_table = wx.AcceleratorTable(accel_entries)
        self.SetAcceleratorTable(accel_table)

    def rebuild_accelerator_table(self) -> None:
        """Re-run the keymap-to-AcceleratorTable conversion.

        Idempotent: ``wx.NewIdRef()`` instances created in ``__init__``
        are reused (rebuild does NOT leak new ids). Callable after
        ``__init__`` without restarting the process.
        """
        self._build_accelerators()

    # ── Quick-action handler stubs (chat_panel methods wired in v0.8.0) ──────

    def _on_copy_last(self) -> None:
        """Copy the last message in the chat history to clipboard."""
        self.chat_panel.copy_last_message()

    def _on_delete_last_exchange(self) -> None:
        """Remove the last user/assistant exchange pair."""
        self.chat_panel.delete_last_exchange()

    def _on_edit_previous(self) -> None:
        """Load the previous user message into the input for editing."""
        self.chat_panel.edit_message("prev")

    def _on_edit_next(self) -> None:
        """No-op: 'next' is ambiguous after truncation."""
        self.chat_panel.edit_message("next")

    def _on_regenerate_last(self) -> None:
        """Remove the last assistant response and re-send the same user prompt."""
        self.chat_panel.regenerate_last()

    def _on_read_selected_message(self) -> None:
        """Read the selected message using system voice (F8).

        Gates on mid-generation: if generating, speaks and returns.
        Silently returns when no message is selected or the selected
        text is empty (streaming placeholder).
        """
        if self.chat_panel._is_generating:
            self._speech.speak("Generación en curso", interrupt=False)
            return
        text = self.chat_panel.get_selected_message_text()
        if not text:
            self._speech.speak("Nada que leer", interrupt=False)
            return
        plain = strip_markdown(text)
        self._speech.speak_with_system_voice(plain, self._system_voice)

    def _on_regenerate_send_callback(self, text: str, user_idx: int) -> None:
        """Callback from ChatPanel.regenerate_last: re-attach images and send.

        Looks up the user message in ``Conversation.messages`` (adjusting for
        system rows in ``_history``) and re-attaches any stored images before
        calling ``send_message``.
        """
        # Compute conversation index (subtract system rows before the target)
        system_count = sum(
            1 for r, _ in self.chat_panel._history[:user_idx] if r == "system"
        )
        conv_idx = user_idx - system_count

        # Re-attach images from the stored user message if any
        if 0 <= conv_idx < len(self._conversation.messages):
            user_msg = self._conversation.messages[conv_idx]
            stored_images = user_msg.get("images")
            if stored_images:
                # Rebuild list of (base64, mime) tuples
                restored: list[tuple[str, str]] = []
                for img_b64 in stored_images:
                    restored.append((img_b64, "image/png"))
                self.chat_panel._attached_images = restored
                self.chat_panel.attachment_label.SetLabel(
                    f"[{len(restored)} image(s)]"
                )
            else:
                self.chat_panel._attached_images = []
                self.chat_panel.attachment_label.SetLabel("(ninguno)")

        # Trigger the send flow
        self.send_message()

    def _on_truncate_history_callback(self, conv_idx: int) -> None:
        """Callback from ChatPanel.edit_message: truncate Conversation."""
        if 0 <= conv_idx < len(self._conversation.messages):
            self._conversation.truncate_to(conv_idx)

    def _on_focus_list(self) -> None:
        """Focus the message list and announce the last item."""
        lst = self.chat_panel.message_list
        count = lst.GetCount()
        if count > 0:
            lst.SetSelection(count - 1)
        self._speech.speak(f"Historial, {count} mensajes", interrupt=True)
        lst.SetFocus()

    def _on_focus_use(self) -> None:
        """Focus the use_model_button, falling back to restart_server_button."""
        if self.use_model_button.IsEnabled():
            self.use_model_button.SetFocus()
        else:
            self.restart_server_button.SetFocus()

    def _on_find(self) -> None:
        """Open FindDialog and wire up history search.

        Creates a modal FindDialog. On each search action (button or
        Enter), calls ``chat_panel.find_and_select`` with the current
        query and direction. After closing, restores focus to the
        message list so the user can navigate results.
        """
        from bellbird.ui.find_dialog import FindDialog

        dlg = FindDialog(self)
        dlg.set_on_find(
            lambda direction: self.chat_panel.find_and_select(
                dlg.get_query(), direction,
            )
        )
        dlg.ShowModal()
        dlg.Destroy()

        # Restore focus to message list so NVDA can navigate results
        self.chat_panel.message_list.SetFocus()

    def _on_f6_cycle(self) -> None:
        """Cycle focus through main panels: model selector, list, input, server row."""
        targets = [
            self.model_selector,
            self.chat_panel.message_list,
            self.chat_panel.message_input,
            self.restart_server_button,
        ]
        panel_names = ["Modelos", "Historial", "Entrada", "Servidor"]
        # Keep panel_names in sync with the targets list above (same length, same order).
        self._focus_cycle_index = (self._focus_cycle_index + 1) % len(targets)
        target = targets[self._focus_cycle_index]
        wx.CallAfter(target.SetFocus)
        self._speech.speak(
            panel_names[self._focus_cycle_index],
            interrupt=True,
        )

    # ── Attach URL (Ctrl+U) ────────────────────────────────────────────────

    def _on_attach_url(self) -> None:
        """Open URL dialog and start fetch on a daemon thread (Ctrl+U).

        Gates on mid-generation: if generating, speaks and returns.
        After dialog closes, validates scheme, speaks, spawns timer and
        daemon thread. Never blocks the UI thread.
        """
        # Gate: no-op mid-generation
        if self.chat_panel._is_generating:
            try:
                self._speech.speak("Generación en curso", interrupt=False)
            except Exception:
                pass
            return

        from bellbird.ui.url_dialog import URLDialog

        dlg = URLDialog(self)
        result = dlg.ShowModal()
        url = dlg.get_url()
        dlg.Destroy()

        # Restore focus to message list
        self.chat_panel.message_list.SetFocus()

        if result != wx.ID_OK:
            return

        if not url:
            try:
                self._speech.speak("URL vacía", interrupt=False)
            except Exception:
                pass
            return

        # Pre-validate scheme (SSRF guard)
        import re
        if not re.match(r"^https?://", url, re.IGNORECASE):
            try:
                self._speech.speak(
                    "Solo URLs http o https", interrupt=False
                )
            except Exception:
                pass
            return

        # Immediate feedback + announce timer + daemon thread
        try:
            self._speech.speak("Descargando página", interrupt=False)
        except Exception:
            pass

        self._url_fetch_timer = self._make_announce_timer(
            phrase="Descargando página, por favor espera..."
        )
        max_chars = self._config.url_max_chars
        threading.Thread(
            target=self._fetch_url_worker,
            args=(url, max_chars),
            daemon=True,
        ).start()

    def _fetch_url_worker(self, url: str, max_chars: int) -> None:
        """Background thread: fetch URL text and post result to main thread.

        Args:
            url: The URL to fetch.
            max_chars: Maximum characters for the returned text.
        """
        from bellbird.core.web_fetch import fetch_text

        result = fetch_text(url, max_chars=max_chars)
        wx.CallAfter(self._on_fetch_complete, result)

    def _on_fetch_complete(self, result) -> None:
        """Handle the fetch result on the main thread.

        Cancels the announce timer, then attaches content or speaks error.
        Never shows a MessageDialog.
        """
        # Cancel announce timer
        if self._url_fetch_timer is not None:
            self._url_fetch_timer.cancel()
            self._url_fetch_timer = None

        if result.ok:
            origin_label = self._derive_origin_label(result.url)
            self.chat_panel.attach_url(
                result.url, result.text, origin_label=origin_label,
            )
            try:
                self._speech.speak("Página adjuntada", interrupt=False)
            except Exception:
                pass

            if result.truncated:
                try:
                    self._speech.speak(
                        f"Página grande, se truncó a "
                        f"{self._config.url_max_chars} caracteres",
                        interrupt=False,
                    )
                except Exception:
                    pass
        else:
            try:
                self._speech.speak(
                    f"Error al descargar: {result.error}", interrupt=True
                )
            except Exception:
                pass

    @staticmethod
    def _derive_origin_label(url: str) -> str:
        """Derive a human-readable origin label from a URL.

        Produces ``netloc + path`` (e.g. ``example.com/docs/page``),
        truncated to 60 characters if longer.

        Args:
            url: The URL string.

        Returns:
            Human-readable label string.
        """
        from urllib.parse import urlparse

        parsed = urlparse(url)
        label = f"{parsed.netloc}{parsed.path}"
        # Remove trailing slash for cleaner look
        if label.endswith("/"):
            label = label[:-1]
        if len(label) > 60:
            label = label[:57] + "..."
        return label

    def _create_status_bar(self) -> None:
        """Create status bar with 3 fields."""
        self.status_bar = self.CreateStatusBar(number=3, name="status_bar")
        self.status_bar.SetStatusText("Iniciando...", 0)
        self.status_bar.SetStatusText("", 1)
        self.status_bar.SetStatusText("", 2)

    def _sync_button_state(self, server_running: bool) -> None:
        """Sync start/stop button enable state with server running state."""
        self.restart_server_button.Enable()
        if server_running:
            self.stop_server_button.Enable()
        else:
            self.stop_server_button.Disable()

    def _on_use_model(self) -> None:
        """Start llama-server with the selected model in a background thread."""
        model = self.get_model()
        if not model or not Path(model).is_file():
            self._speech.speak("Archivo de modelo no encontrado", interrupt=True)
            return
        basename = Path(model).name

        # Resolve mmproj: config → auto-detect → FileDialog
        mmproj_path: str | None = self._config.get_mmproj_for(model)
        if mmproj_path is None:
            auto = find_mmproj_for_model(Path(model))
            if auto is not None:
                mmproj_path = str(auto)
            else:
                # Show FileDialog on the main thread
                model_dir = str(Path(model).parent) if Path(model).parent.exists() else ""
                dlg = wx.FileDialog(
                    self,
                    message="Seleccione el archivo mmproj",
                    defaultDir=model_dir,
                    defaultFile="",
                    wildcard="*.gguf",
                    style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
                )
                if dlg.ShowModal() == wx.ID_OK:
                    mmproj_path = dlg.GetPath()
                dlg.Destroy()

        # Persist manual selection
        if mmproj_path is not None:
            self._config.model_mmproj[basename] = str(Path(mmproj_path).resolve())
            try:
                save_config(self._config)
            except OSError:
                pass  # best-effort persistence

        # Restore per-model tunings (T-WU2-07)
        if basename in self._config.model_tunings:
            saved = self._config.model_tunings[basename]
            if "ctx_size" in saved:
                self._config.ctx_size = saved["ctx_size"]
            if "n_gpu_layers" in saved:
                self._config.n_gpu_layers = saved["n_gpu_layers"]

        self.use_model_button.Disable()
        self.restart_server_button.Disable()
        self._speech.speak(
            f"Iniciando servidor con {basename}...", interrupt=True
        )
        self.status_bar.SetStatusText("Iniciando servidor...", 0)
        self._loading_timer = self._make_announce_timer()
        self._model_load_thread = threading.Thread(
            target=self._model_load_worker,
            args=(model, mmproj_path),
            daemon=True,
        )
        self._model_load_thread.start()

    def _model_load_worker(self, model: str, mmproj_path: str | None = None) -> None:
        """Background thread worker for starting the server.

        `ok` and `message` are bound to safe defaults BEFORE the try so
        the finally block can call `_on_start_server_done` even if
        `start_server` raises. Without the defaults, an exception in
        `start_server` triggers `UnboundLocalError` in the finally
        block, the worker thread dies silently, and the buttons stay
        disabled forever.
        """
        ok = False
        message = "Error: start_server raised an exception"
        try:
            ok, message = start_server(
                model, self._client,
                port=self._config.port,
                ctx_size=self._config.ctx_size,
                n_gpu_layers=self._config.n_gpu_layers,
                mmproj=mmproj_path,
            )
        except Exception as e:
            message = f"Error: {type(e).__name__}: {e}"
        finally:
            if self._loading_timer is not None:
                self._loading_timer.cancel()
            vision_flag = ok and (mmproj_path is not None)
            wx.CallAfter(self._on_start_server_done, ok, message, vision_flag)

    def _make_announce_timer(
        self, phrase: str = "Cargando modelo, por favor espera..."
    ) -> threading.Timer:
        """Create a chained timer that announces a phrase every 8 seconds.

        Args:
            phrase: The text to announce each tick (default loading message).

        First tick fires after 8 seconds; re-arms itself every 8s.
        Cancelled when the owning worker completes.

        The re-arm writes to whichever slot the caller used to store the
        returned Timer. The convention is that the caller does
        ``self._<some_slot> = self._make_announce_timer(phrase=...)`` and
        then cancels ``self._<some_slot>`` on completion. This avoids the
        bug where two concurrent operations (e.g. model load + URL fetch)
        would race to overwrite ``self._loading_timer`` during re-arm,
        causing the cancel in one completion callback to miss the
        re-armed timer of the other.
        """
        # Detect which slot the caller used by scanning well-known attrs.
        # We pick the first slot whose current value is the timer we are
        # about to return. If none match (e.g. caller forgot to assign),
        # fall back to a private list to avoid leaking the re-arm.
        caller_slot: str | None = None
        for slot_name in ("_loading_timer", "_url_fetch_timer"):
            if getattr(self, slot_name, None) is None:
                caller_slot = slot_name
                break

        def _announce() -> None:
            if self._is_closing:
                return
            self._speech.speak(phrase, interrupt=False)
            next_t = threading.Timer(8.0, _announce)
            next_t.daemon = True
            if caller_slot is not None:
                # Only overwrite the slot if the current value is still
                # the previous timer we chained from. If the caller
                # already cancelled and reset the slot, the previous
                # timer is dead and we must not re-arm into it.
                current = getattr(self, caller_slot, None)
                if current is t or current is None:
                    setattr(self, caller_slot, next_t)
            next_t.start()

        t = threading.Timer(8.0, _announce)
        t.daemon = True
        t.start()
        return t

    def _on_start_server_done(self, ok: bool, message: str, vision_capable: bool = False) -> None:
        """Handle the result of background server start."""
        self._vision_capable = vision_capable
        if self._loading_timer is not None:
            self._loading_timer.cancel()
            self._loading_timer = None
        if self._is_closing:
            return
        if ok:
            self.status_bar.SetStatusText("Servidor listo", 0)
            loaded = self._client.get_loaded_model()
            self._update_title(loaded or None)
            if loaded:
                self._persist_last_model(Path(loaded).name)
            if "corriendo" not in message:
                self._scan_models()
            if loaded:
                self._speech.output(f"Modelo: {Path(loaded).stem}")
        else:
            self.status_bar.SetStatusText("Error al iniciar", 0)
        self._sync_button_state(ok)
        self._speech.speak(message, interrupt=True)
        if ok:
            self._notifier.notify("server_ready", "Servidor listo")

    def _persist_last_model(self, basename: str) -> None:
        """Save the just-loaded model basename to the persisted config.

        Called from the main thread (via wx.CallAfter) on successful load.
        Best-effort: a write failure is logged but never blocks the UI.
        """
        if basename and self._config.last_model != basename:
            self._config.last_model = basename
            try:
                save_config(self._config)
            except OSError as e:
                get_logger().warning(f"Failed to persist last_model: {e}")

    def _update_title(self, model: str | None) -> None:
        """Update the window title to show the loaded model."""
        if model:
            self.SetTitle(f"Bellbird — {Path(model).stem}")
        else:
            self.SetTitle("Bellbird")

    # ── Startup ────────────────────────────────────────────────────────────

    def _start_probe_thread(self) -> None:
        """Run the startup probe on a daemon thread.

        Spawns a daemon thread that calls ``core.startup.probe()`` and
        posts the result back via ``wx.CallAfter``. The window is already
        shown before any I/O, so the user sees "Iniciando…" immediately.
        """
        import bellbird.core.llama_runner as runner_mod

        def worker() -> None:
            result = startup_probe(self._client, runner_mod)
            wx.CallAfter(self._on_startup_probe_done, result)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def _on_startup_probe_done(self, result) -> None:
        """Handle the startup probe result on the main thread.

        Updates the status bar, speaks the outcome, and triggers a
        background model scan. Early-returns if the window is closing.
        """
        if self._is_closing:
            return

        log = get_logger()

        if result.server_path is None:
            log.warning("Startup: llama-server not installed")
            install_cmd = get_install_command()
            msg = (
                f"llama-server no instalado. "
                f"Instalalo con: {install_cmd}."
            )
            self.status_bar.SetStatusText("llama-server no instalado", 0)
            self._speech.speak(msg, interrupt=True)
            wx.MessageDialog(
                self,
                message=msg,
                caption="llama-server no instalado",
                style=wx.OK | wx.ICON_WARNING,
            ).ShowModal()
            # Still scan models — the user may have a portable install
            self._scan_models()
            return

        if not result.is_running:
            log.info("Startup: llama-server installed but not running")
            self.status_bar.SetStatusText("Servidor detenido", 0)
            self._speech.speak(
                "Servidor detenido. "
                "Selecciona un modelo y pulsa Iniciar servidor.",
                interrupt=True,
            )
            self._scan_models()
            return

        # Server is running and healthy
        loaded = result.loaded_model or ""
        log.info("Startup: connected, model=%r", loaded)
        if loaded:
            self.status_bar.SetStatusText(f"Conectado: {loaded}", 0)
        else:
            self.status_bar.SetStatusText("Conectado", 0)
        self._sync_button_state(True)
        if loaded:
            self._speech.output(f"Modelo: {Path(loaded).stem}")
            self._notifier.notify("model_loaded", Path(loaded).stem)
        else:
            self._speech.speak(
                "Conectado. Sin modelo cargado.", interrupt=True,
            )
        self._scan_models()

    def _scan_models(self) -> None:
        """Scan for .gguf files on a background thread.

        Launches a daemon thread that calls ``find_gguf_models()`` and
        posts the result via ``wx.CallAfter``. Avoids blocking the main
        thread during filesystem traversal.
        """
        def worker() -> None:
            paths = find_gguf_models()
            wx.CallAfter(self._on_scan_done, paths)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def _on_scan_done(self, paths: list[str]) -> None:
        """Handle the model scan result on the main thread."""
        if self._is_closing:
            return
        log = get_logger()
        self.set_models(paths)
        if paths:
            log.info(f"Scan: {len(paths)} .gguf file(s) found")
            self._speech.speak(
                f"{len(paths)} modelos encontrados", interrupt=True,
            )
        else:
            log.warning("Scan: no .gguf files found")
            self._speech.speak(
                "Ningún modelo .gguf encontrado", interrupt=True,
            )

    def _on_start_server(self) -> None:
        """Start llama-server with the selected model."""
        log = get_logger()
        log.info("Start server button clicked")

        model_path = self.get_model()
        if not model_path:
            msg = "Selecciona primero un modelo .gguf"
            self._speech.speak(msg, interrupt=True)
            return

        # D3: fail fast if the .gguf file does not exist on disk.
        # Otherwise llama-server would launch, fail to load the model,
        # and the user would wait the full 60-second timeout for nothing.
        if not Path(model_path).is_file():
            msg = f"No se encontró el archivo: {model_path}"
            log.error(f"Start server: model file not found: {model_path}")
            self._speech.speak(msg, interrupt=True)
            wx.MessageDialog(
                self,
                message=msg,
                caption="Archivo no encontrado",
                style=wx.OK | wx.ICON_ERROR,
            ).ShowModal()
            return

        self._on_use_model()

    def _on_stop_server(self) -> None:
        """Stop the running llama-server."""
        log = get_logger()
        log.info("Stop server button clicked")

        self._vision_capable = False
        self.status_bar.SetStatusText("Deteniendo servidor...", 0)
        self._speech.speak("Deteniendo servidor...", interrupt=True)

        stop_server()

        self.status_bar.SetStatusText("Servidor detenido", 0)
        self._speech.speak("Servidor detenido", interrupt=True)
        self._sync_button_state(False)
        self._update_title(None)

    # ── Session Status (F2) ──────────────────────────────────────────────────

    def _announce_session_status(self) -> None:
        """Announce the current session status via speech (F2).

        Uses ``SessionSnapshot`` + ``format_status`` to build the string.
        Routes through ``speech.output()`` (voz+braille) when idle and
        ``speech.speak(..., interrupt=False)`` during generation.

        Double-F2 within 1.5 s switches to ``mode="long"`` (full breakdown).
        """
        # Double-F2 detection (T-WU2-02)
        # When a 2nd press lands within 1.5s of the 1st, switch to "long"
        # and clear the timestamp so a 3rd press starts the "short" cycle
        # again. Do NOT overwrite the None reset on the next line.
        now = time.monotonic()
        if self._last_f2_mono is not None and (now - self._last_f2_mono) <= 1.5:
            mode: str = "long"
            self._last_f2_mono = None
        else:
            mode = "short"
            self._last_f2_mono = now

        # Build SessionSnapshot
        loaded = self._client.get_loaded_model()
        model_name = Path(loaded).stem if loaded else ""

        server_state = self._client.check_state()

        progress_tokens = (
            self._latest_completion_tokens if self._is_generating else None
        )

        snapshot = SessionSnapshot(
            model_name=model_name,
            n_ctx=self._current_n_ctx,
            prompt_tokens=self._latest_prompt_tokens,
            completion_tokens=self._latest_completion_tokens,
            progress_tokens=progress_tokens,
            last_tok_per_s=self._latest_tok_per_s,
            server_state=server_state,
            vram_free_mb=self._vram_free_mb,
            vram_total_mb=self._vram_total_mb,
            fit_status=self._fit_status,
            message_count=len(self._conversation.messages),
            temperature=self._config.temperature,
            top_p=self._config.top_p,
            max_tokens=self._config.max_tokens,
            is_generating=self._is_generating,
        )

        toggles = self._config.status_toggles_as_set()
        text = format_status(snapshot, toggles, mode)

        if not text:
            return  # all toggles off — no speech

        if self._is_generating:
            self._speech.speak(text, interrupt=False)
        else:
            self._speech.output(text)

    def _set_initial_focus(self) -> None:
        """Set initial focus based on model availability, without I/O.

        Called via wx.CallAfter after the window is shown. The startup
        probe runs on a background thread; focus is adjusted later when
        the probe result arrives.
        """
        if self.model_selector.GetCount() > 0:
            self.use_model_button.SetFocus()
        else:
            self.scan_models_button.SetFocus()

    def _maybe_beep(self) -> None:
        """Emit a Windows beep during token generation (throttled to 1/s)."""
        if sys.platform != "win32":
            return
        if self._speech.is_screen_reader_active():
            return
        now = time.monotonic()
        if now - self._last_beep_time < 1.0:
            return
        self._last_beep_time = now
        try:
            import winsound  # Windows-only; guarded by platform check above
            winsound.Beep(520, 50)
        except Exception:
            pass

    def _on_browse_model(self) -> None:
        """Open file dialog to pick a .gguf file and set it as the model."""
        wildcard = "Modelos GGUF (*.gguf)|*.gguf"
        dialog = wx.FileDialog(
            self,
            message="Seleccionar modelo .gguf",
            defaultDir="",
            defaultFile="",
            wildcard=wildcard,
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        )
        if dialog.ShowModal() == wx.ID_OK:
            filepath = dialog.GetPath()
            basename = Path(filepath).name
            if self.add_model(filepath):
                # D4: speak a confirmation so blind users get feedback.
                self._speech.speak(f"Modelo seleccionado: {basename}", interrupt=True)
            else:
                # D2: the path did not pass the .gguf / exists checks.
                self._speech.speak(
                    f"Archivo no válido: {basename}. Debe ser un .gguf existente.",
                    interrupt=True,
                )
        dialog.Destroy()

    # ── Message Send Flow ──────────────────────────────────────────────────

    def send_message(self) -> None:
        """Build API payload and start streaming.

        Accepts plain text, text with images, or images only. If neither
        text nor images are present, the message is ignored.
        """
        self._aborted = False  # Reset abort flag before each new generation
        if self._is_generating or self._tool_executing:
            self._speech.speak("Ya se está generando una respuesta", interrupt=False)
            return

        log = get_logger()

        # Read input and attachments
        user_text = self.chat_panel.get_input_text()
        attached_images = self.chat_panel.get_attached_images()
        attached_text = self.chat_panel.get_attached_text()

        # C3: allow empty text if there are images attached
        if not user_text.strip() and not attached_images:
            return

        # REQ-MULTI-003: drop images when model is not vision-capable
        if attached_images and not self._vision_capable:
            try:
                self._speech.speak(
                    "Aviso: el modelo actual no procesa imágenes. "
                    "Adjunto enviado sin imagen.",
                    interrupt=True,
                )
            except Exception:
                pass  # Speech failures must never crash the send path
            attached_images = []

        # Build API messages (system prompt + history; user message appended below)
        api_messages = build_api_messages(self._config, self._conversation)

        # New user message
        user_msg: dict
        if attached_images:
            # C5: build OpenAI content-array, incorporating text and attached_text
            parts: list[dict] = []
            if user_text.strip():
                parts.append({"type": "text", "text": user_text})
            if attached_text:
                parts.append({
                    "type": "text",
                    "text": f"[Contenido del archivo adjuntado]\n{attached_text}",
                })
            for b64, mime in attached_images:
                url = f"data:{mime};base64,{b64}"
                parts.append({
                    "type": "image_url",
                    "image_url": {"url": url},
                })
            user_msg = {"role": "user", "content": parts}
        else:
            # Plain text path (with or without attached_text)
            if attached_text:
                content = (
                    f"{user_text}\n\n"
                    f"[Contenido del archivo adjuntado]\n{attached_text}"
                )
            else:
                content = user_text
            user_msg = {"role": "user", "content": content}
        api_messages.append(user_msg)

        # Clear input and attachment
        self.chat_panel._clear_input()
        self.chat_panel.clear_attachment()

        # C4: store plain text in Conversation, NOT the content-array.
        # For image messages, store a short marker so the conversation log
        # round-trips and the user can see images were sent.
        if attached_images:
            n = len(attached_images)
            if user_text.strip():
                stored = f"{user_text} [imagen adjunta: {n}]"
            else:
                stored = f"[imagen adjunta: {n}]"
        else:
            stored = user_msg["content"]  # str in this branch
        self._conversation.add_message("user", stored)

        # Display: show the text or a marker when sending images only
        if user_text.strip():
            self.chat_panel.append_user_message(user_text)
        else:
            self.chat_panel.append_user_message("[imagen enviada]")

        # ── Pre-send guard (T-WU2-04) ──────────────────────────────────
        joined_text = user_text
        if attached_text:
            joined_text = f"{user_text}\n\n{attached_text}" if user_text.strip() else attached_text
        model_path = self.get_model()
        vram_free = read_vram()[0] if self._vram_free_mb is None else self._vram_free_mb
        model_bytes = estimate_size_bytes(model_path) if model_path else None
        token_est = token_count(
            joined_text, self._client.base_url, self._client._session, timeout=5.0
        ) or 0

        presend_snap = PreSendSnapshot(
            estimated_tokens=token_est,
            n_ctx=self._current_n_ctx,
            safe_mode=self._config.safe_vram_mode,
            warn_once=self._pre_send_warned_this_conv,
            vram_free_mb=vram_free,
            model_size_bytes=model_bytes,
        )
        verdict = pre_send_check(presend_snap)
        if verdict.decision == "block":
            self._speech.speak(
                verdict.reason_es or "Contexto lleno; iniciá nueva conversación",
                interrupt=True,
            )
            return
        elif verdict.decision == "warn":
            self._speech.speak(
                verdict.reason_es or "Vas a exceder el contexto",
                interrupt=True,
            )
            self._pre_send_warned_this_conv = True
        # "allow" → proceed silently

        # Reset context meter threshold for the new generation
        self._meter_threshold_fired = False

        # Start generation
        options = build_options(self._config)
        self._current_response = ""
        self._current_reasoning = ""

        self.chat_panel.start_generation()
        self._is_generating = True

        log.info(
            "send_message: user text=%r tools_enabled=%s",
            (user_text[:60] + "...") if len(user_text) > 60 else user_text,
            self._config.tools_enabled,
        )
        self.status_bar.SetStatusText("Generando respuesta...", 2)
        self._speech.speak("Generando respuesta...", interrupt=True)

        self._tool_iteration_count = 0
        tools = [SHELL_TOOL_DEFINITION] if self._config.tools_enabled else None
        if tools and not self._client.check_tool_support():
            tools = None
            try:
                self._speech.speak(
                    "Plantilla del modelo no soporta herramientas. Desactivado.",
                    interrupt=True,
                )
            except Exception:
                pass

        self._client.chat_stream(
            messages=api_messages,
            options=options,
            on_token=self._on_token,
            on_done=self._on_done,
            on_error=self._on_error,
            on_usage=self._on_usage,
            on_timings=self._on_timings,
            on_tool_call=self._on_tool_call,
            tools=tools,
            on_reasoning=self._on_reasoning,
        )

    def _on_history_delete(self, index: int, role: str) -> None:
        """Sync Conversation.messages with the deleted history entry.

        Called by ChatPanel._on_context_delete after the user deletes
        a message from the history list. System-role rows (tool blocked/
        denied) are UI-only and have no Conversation counterpart.

        Args:
            index: Pre-pop position in _history of the deleted entry.
            role: Role of the deleted entry.
        """
        if role == "system":
            return
        system_count = sum(
            1 for r, _ in self.chat_panel._history[:index] if r == "system"
        )
        conv_index = index - system_count
        if 0 <= conv_index < len(self._conversation.messages):
            self._conversation.messages.pop(conv_index)

    def _on_token(self, token: str) -> None:
        """Handle a content token fragment from the stream.

        Reasoning content is routed via ``_on_reasoning`` and must NOT
        reach this callback. The ``_stream_worker`` guarantees this:
        ``delta.reasoning_content`` and parser-emitted reasoning slices
        go to ``on_reasoning`` only.

        Args:
            token: Content token text from the LLM.
        """
        if not self._is_generating:
            return
        self._current_response += token
        self.chat_panel.update_streaming_preview(self._current_response)
        self._maybe_beep()
        self._speech.announce_token_chunk(token)

    def _on_reasoning(self, reasoning_text: str) -> None:
        """Handle a reasoning fragment from the stream.

        Reasoning is never read aloud by default. On the first chunk
        of a turn, ``"Pensando…"`` is spoken once to indicate the model
        is thinking. Subsequent chunks are accumulated silently.

        MUST NOT update ``_current_response`` and MUST NOT call
        ``chat_panel.update_streaming_preview`` — reasoning is not
        displayed in the chat list.

        Args:
            reasoning_text: A reasoning/chain-of-thought fragment.
        """
        if not self._is_generating:
            return
        if not self._current_reasoning:
            # First reasoning chunk of this turn — announce once
            self._speech.speak("Pensando…", interrupt=False)
        self._current_reasoning += reasoning_text

    def _on_done(self) -> None:
        """Handle stream completion or abort confirmation."""
        # Abort path: check FIRST so an aborted generation is never
        # saved as "Respuesta completa". This is additive to the
        # v0.4.1 two-layer race defense (self._is_generating guard).
        if self._aborted:
            self._speech.speak("Generación detenida", interrupt=True)
            self.chat_panel.end_generation()
            self._current_response = ""
            self._current_reasoning = ""
            self._aborted = False
            self.status_bar.SetStatusText("", 2)
            return

        if not self._is_generating:
            return
        log = get_logger()
        log.info("_on_done: response_len=%d chars", len(self._current_response))
        self._speech.flush_token_buffer()
        self._speech.speak("Respuesta completa", interrupt=True)
        self._notifier.notify("generation_complete", "Respuesta completa")

        # Save assistant message to conversation (including reasoning).
        # Skip when a tool call is pending: _on_tool_result will save the
        # correct assistant+tool_calls message with the full content.
        if self._current_response.strip() and not self._tool_executing:
            self._conversation.add_message(
                "assistant", self._current_response,
                reasoning=self._current_reasoning,
            )

        # Focus courtesy: capture the streaming index before it is
        # reset by end_generation(). Only SetSelection back to the
        # streaming row if the user is still on the placeholder.
        # If they navigated away, don't steal their position.
        cp = self.chat_panel
        last_streaming_idx = cp._streaming_index
        do_focus = (
            last_streaming_idx is not None
            and cp.message_list.GetSelection() == last_streaming_idx
        )

        # Promote placeholder to final preview
        self.chat_panel.end_generation(final_text=self._current_response)

        if do_focus:
            cp.message_list.SetSelection(last_streaming_idx)

        self._is_generating = False
        self.status_bar.SetStatusText("", 2)
        self._current_response = ""
        self._current_reasoning = ""

    # ── Tool calling (v0.4.0) ─────────────────────────────────────────────

    def _on_tool_call(self, tool_name: str, tool_call_id: str, args: dict) -> None:
        """Callback cuando el modelo solicita ejecutar una herramienta."""
        self._tool_executing = True
        command = args.get("command", str(args))

        if self._permission_manager.is_system_destructive(command):
            self._speech.speak(
                f"Comando bloqueado por seguridad: {command[:80]}", interrupt=True
            )
            self.chat_panel.append_tool_blocked(tool_name, command)
            return

        risk = self._permission_manager.classify_risk(command)

        if self._permission_manager.has_session_grant(tool_name, risk):
            self._speech.speak(
                f"Ejecutando {tool_name}: {command[:50]}", interrupt=True
            )
            self._run_tool_and_show(tool_name, tool_call_id, command)
            return

        self._speech.speak(
            "El modelo quiere ejecutar un comando. Escucha el comando y confirma.",
            interrupt=True,
        )
        self._notifier.notify(
            "tool_request", "El modelo quiere ejecutar un comando",
        )
        dlg = PermissionDialog(
            self, tool_name, command, risk,
            permission_manager=self._permission_manager,
            speech=self._speech,
        )
        result = dlg.ShowModal()
        edited_cmd = dlg.get_command()
        dlg.Destroy()

        if result == wx.ID_YES:
            self._run_tool_and_show(tool_name, tool_call_id, edited_cmd)
        elif result == wx.ID_OK:
            self._permission_manager.grant_session(tool_name, dlg.get_risk())
            self._run_tool_and_show(tool_name, tool_call_id, edited_cmd)
        else:
            self._speech.speak("Ejecucion denegada.", interrupt=True)
            self.chat_panel.append_tool_denied(tool_name)

    def _run_tool_and_show(
        self, tool_name: str, tool_call_id: str, command: str
    ) -> None:
        """Ejecuta la tool en hilo de fondo para no bloquear la UI."""
        def worker() -> None:
            result = self._tool_executor.run(tool_name, command)
            wx.CallAfter(
                self._on_tool_result, result, tool_call_id, tool_name, command,
            )
        threading.Thread(target=worker, daemon=True).start()

    def _on_tool_result(self, result, tool_call_id: str, tool_name: str = "", command: str = "") -> None:
        """Callback en hilo principal con el resultado de la herramienta."""
        self._tool_executing = False
        log = get_logger()
        if self._aborted:
            log.info("tool cancelled by user abort")
            self.chat_panel.append_tool_output(result.to_display_text())
            return
        if result.cancelled:
            log.info("tool cancelled by user abort")
            self.chat_panel.append_tool_output(result.to_display_text())
            self._speech.speak(
                "Generación detenida", interrupt=True
            )
            return
        self.chat_panel.append_tool_output(result.to_display_text())

        # Build and insert the assistant+tool_calls message (required by
        # the OpenAI contract for the 2nd turn).
        if tool_name:
            tool_call_entry = {
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": json.dumps({"command": command}),
                },
            }
            self._conversation.add_message(
                "assistant", self._current_response,
                tool_calls=[tool_call_entry],
            )

        # Short feedback announcement
        stdout_text = result.stdout.strip() if result.stdout else ""
        if stdout_text:
            first_line = stdout_text.split("\n")[0][:80]
            feedback = (
                f"Comando completado, código {result.returncode}. "
                f"Primeras líneas: {first_line}"
            )
        else:
            feedback = f"Comando completado, código {result.returncode}."
        self._speech.speak(feedback, interrupt=True)

        tool_msg = result.to_tool_message()
        tool_msg["tool_call_id"] = tool_call_id
        # Persist tool_call_id on the message so the next API call carries
        # the matching ID (required by the OpenAI-compatible API for the
        # tool-calling second turn). Without this, llama-server rejects
        # the request. v0.4.0-ui verify v1 CRITICAL-1.
        self._conversation.add_message(
            "tool", tool_msg["content"], tool_call_id=tool_call_id
        )
        self._continue_after_tool()

    def _continue_after_tool(self) -> None:
        """Reenvía la conversación al modelo con el resultado de la tool.

        Increments the tool iteration counter and checks against
        max_tool_iterations. If the limit is reached, appends a visible
        row and returns without calling chat_stream.
        """
        self._tool_iteration_count += 1
        if self._tool_iteration_count >= self._config.max_tool_iterations:
            msg = f"[Tool loop terminated: max iterations ({self._config.max_tool_iterations}) reached]"
            self.chat_panel.append_tool_output(msg)
            self._speech.speak(
                "Límite de iteraciones alcanzado", interrupt=True,
            )
            self._is_generating = False
            self.status_bar.SetStatusText("", 2)
            return

        self._aborted = False  # Reset abort flag before re-launching the stream
        api_messages = build_api_messages(self._config, self._conversation)

        tools = (
            [SHELL_TOOL_DEFINITION]
            if self._config.tools_enabled
            else None
        )

        self._current_response = ""
        self._current_reasoning = ""
        self.chat_panel.start_generation()
        self._is_generating = True
        self.status_bar.SetStatusText("Consultando al modelo...", 2)

        self._client.chat_stream(
            messages=api_messages,
            options=build_options(self._config),
            on_token=self._on_token,
            on_done=self._on_done,
            on_error=self._on_error,
            on_usage=self._on_usage,
            on_timings=self._on_timings,
            on_tool_call=self._on_tool_call,
            tools=tools,
            on_reasoning=self._on_reasoning,
        )

    def _on_error(self, error_text: str) -> None:
        """Handle stream error or abort confirmation.

        Args:
            error_text: Error description. Ignored when ``self._aborted``
                is True (the abort path takes precedence).
        """
        if self._aborted:
            self._speech.speak("Generación detenida", interrupt=True)
            self.chat_panel.end_generation()
            self._current_response = ""
            self._current_reasoning = ""
            self._aborted = False
            self.status_bar.SetStatusText("", 2)
            return

        if not self._is_generating:
            return
        log = get_logger()
        log.error("_on_error: %s", error_text)
        self._current_response = error_text
        self._current_reasoning = ""
        self.chat_panel.end_generation(final_text=error_text)
        self._is_generating = False
        self.status_bar.SetStatusText("Error", 2)

        # Watchdog: connection-class errors → check server state in background
        connection_markers = (
            "ConnectionError",
            "ConnectionRefusedError",
            "ReadTimeout",
            "ChunkedEncodingError",
        )
        if any(marker in error_text for marker in connection_markers):
            self._run_connection_watchdog(error_text)
            return

        # Existing error path for non-connection errors
        wx.MessageDialog(
            self,
            message=error_text,
            caption="Error",
            style=wx.OK | wx.ICON_ERROR,
        ).ShowModal()
        self._speech.speak(error_text, interrupt=True)
        self._notifier.notify("error", "Error")

    def _run_connection_watchdog(self, error_text: str) -> None:
        """Check server state on a daemon thread for connection errors.

        Spawns a daemon thread that calls ``check_state()`` and posts the
        result back via ``wx.CallAfter``. Never blocks the main thread.
        """
        def watchdog_worker() -> None:
            try:
                state = self._client.check_state()
            except Exception:
                state = "dead"
            wx.CallAfter(self._on_server_state_checked, state, error_text)

        t = threading.Thread(target=watchdog_worker, daemon=True)
        t.start()

    def _on_server_state_checked(
        self, state: str, error_text: str = ""
    ) -> None:
        """Handle the result of a connection watchdog server-state check.

        Args:
            state: One of ``"dead"``, ``"loading"``, or ``"ready"``.
            error_text: The original error text from the stream (for logging).
        """
        log = get_logger()
        log.info(
            "_on_server_state_checked: state=%r error=%r",
            state, error_text[:80] if error_text else "",
        )

        if state == "dead":
            self._speech.speak(
                "El servidor se detuvo. ¿Reiniciar?", interrupt=True
            )
            self._notifier.notify("error", "Servidor caído")
            self._show_restart_dialog()
        elif state == "loading":
            self._speech.speak(
                "Cargando modelo, por favor espera…", interrupt=True
            )
        else:
            # "ready" — transient error, show existing error dialog
            wx.MessageDialog(
                self,
                message=error_text,
                caption="Error",
                style=wx.OK | wx.ICON_ERROR,
            ).ShowModal()
            self._speech.speak(error_text, interrupt=True)

    def _show_restart_dialog(self) -> None:
        """Show a native wx.Dialog offering to restart the server.

        Uses only ``wx.BoxSizer`` (H/V), no ``wx.MessageDialog`` with
        custom Spanish labels (MSAA regression per AGENTS.md). Focus is
        set on the "Sí" button after ``Fit()``.
        """
        dlg = wx.Dialog(
            self,
            name="server_down_dialog",
            title="Servidor no disponible",
        )
        label = wx.StaticText(
            dlg, label="El servidor se detuvo. ¿Reiniciar?"
        )
        yes_btn = wx.Button(
            dlg, label="Sí, reiniciar", name="restart_yes_button"
        )
        no_btn = wx.Button(
            dlg, label="No, salir", name="restart_no_button"
        )

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.Add(yes_btn, flag=wx.RIGHT, border=8)
        btn_sizer.Add(no_btn)

        root_sizer = wx.BoxSizer(wx.VERTICAL)
        root_sizer.Add(
            label, flag=wx.ALL | wx.ALIGN_CENTER, border=16
        )
        root_sizer.Add(
            btn_sizer, flag=wx.ALIGN_CENTER | wx.BOTTOM, border=8
        )
        dlg.SetSizer(root_sizer)

        dlg.Fit()
        yes_btn.SetFocus()

        yes_btn.Bind(
            wx.EVT_BUTTON, lambda evt: dlg.EndModal(wx.ID_YES)
        )
        no_btn.Bind(
            wx.EVT_BUTTON, lambda evt: self._on_restart_no(dlg)
        )

        result = dlg.ShowModal()
        if result == wx.ID_YES:
            self._on_use_model()
        dlg.Destroy()

    def _on_restart_no(self, dlg: wx.Dialog) -> None:
        """User clicked 'No, salir' — clean up generation state."""
        self._is_generating = False
        self._current_response = ""
        self.status_bar.SetStatusText("Servidor detenido", 0)
        dlg.EndModal(wx.ID_NO)

    # ── Abort ──────────────────────────────────────────────────────────────

    def abort_generation(self) -> None:
        """Abort the current generation and drop the partial response.

        The flag order MUST be: _aborted = True → _is_generating = False
        → client.abort(), so by the time the stream worker fires
        _on_done via wx.CallAfter, both flags are already set and the
        partial response is discarded instead of being saved as
        "Respuesta completa".
        """
        self._aborted = True
        self._is_generating = False
        self._tool_executor.cancel()
        self._client.abort()
        self._speech.stop()
        self._speech.clear_buffer()
        self._current_reasoning = ""

    # ── Usage & Browser ─────────────────────────────────────────────────────

    def _on_timings(self, timings: dict) -> None:
        """Handle timings from the LLM stream.

        Args:
            timings: Dict with predicted_per_second (and possibly other fields).
        """
        tok_per_s = timings.get("predicted_per_second")
        if tok_per_s is not None:
            self._latest_tok_per_s = float(tok_per_s)

    def _on_usage(self, usage: dict) -> None:
        """Handle usage stats from the LLM stream.

        Args:
            usage: Dict with prompt_tokens, completion_tokens, total_tokens.
        """
        self._last_usage = usage
        pt = usage.get("prompt_tokens")
        ct = usage.get("completion_tokens")
        if pt is not None:
            self._latest_prompt_tokens = int(pt)
        if ct is not None:
            self._latest_completion_tokens = int(ct)
        self._update_context_meter(
            self._latest_prompt_tokens or 0,
            self._latest_completion_tokens or 0,
            self._current_n_ctx,
        )

    def _update_context_meter(
        self, prompt_tokens: int, completion_tokens: int, n_ctx: int | None
    ) -> None:
        """Update status bar field 1 with the live context meter.

        Called from ``_on_usage`` after caching the latest token counts.

        Args:
            prompt_tokens: Prompt token count.
            completion_tokens: Completion token count.
            n_ctx: Context window size, or ``None`` if unknown.
        """
        total = prompt_tokens + completion_tokens
        if n_ctx is None:
            self.status_bar.SetStatusText(f"Contexto: {total} tokens", 1)
            return

        pct = round(100 * total / n_ctx)
        self.status_bar.SetStatusText(
            f"Contexto: {total}/{n_ctx} ({pct} %)", 1
        )

        # Threshold announce: >= 85 %, one-shot per generation
        if pct >= 85 and self._is_generating and not self._meter_threshold_fired:
            self._speech.speak("Contexto casi lleno", interrupt=False)
            self._meter_threshold_fired = True

    def _open_message_in_browser(self, text: str, reasoning: str | None = None) -> None:
        """Open message content in the default browser via a temp HTML file.

        Args:
            text: Markdown text to render as HTML.
            reasoning: Optional reasoning/chain-of-thought text. When provided,
                wrapped in a ``<details>`` element above the content.
        """
        full_html = render_message_html(text, reasoning=reasoning)
        # Optional: unlink the previous tempfile to avoid tempdir accumulation
        if self._temp_html_files:
            try:
                os.unlink(self._temp_html_files[-1])
            except OSError:
                pass  # file already gone or locked; harmless
            self._temp_html_files.pop()
        with tempfile.NamedTemporaryFile(
            suffix=".html", delete=False, mode="w", encoding="utf-8"
        ) as f:
            f.write(full_html)
            temp_path = f.name
        self._temp_html_files.append(temp_path)
        webbrowser.open(f"file:///{temp_path}")

    # ── Recents submenu ────────────────────────────────────────────────────

    def _on_menu_open(self, event: wx.MenuEvent) -> None:
        """Rebuild the recents submenu whenever a menu opens."""
        self._refresh_recents_menu()

    def _refresh_recents_menu(self) -> None:
        """Rebuild the Recientes submenu from config.recent_files.

        Filters out non-existent paths, truncates labels, and populates
        the submenu. Called from ``_on_menu_open`` before the menu is shown.
        """
        if self._recents_menu is None:
            return
        menu = self._recents_menu
        menu.Clear()
        self._recent_items.clear()

        valid = [
            p for p in self._config.recent_files if os.path.exists(p)
        ]

        if not valid:
            item = menu.Append(wx.ID_ANY, "Sin recientes")
            item.Enable(False)
            return

        for path_str in valid:
            label = self._truncate_path(path_str, 60)
            item_id = wx.NewIdRef()
            menu.Append(item_id, label)
            self._recent_items[item_id.GetId()] = path_str
            self.Bind(wx.EVT_MENU, self._on_recent_click, id=item_id)

    @staticmethod
    def _truncate_path(path: str, max_len: int = 60) -> str:
        """Truncate a path with ellipsis in the middle if longer than max_len.

        Args:
            path: File path string.
            max_len: Maximum length before truncation.

        Returns:
            Truncated string with ``...`` in the middle, or the original
            if short enough.
        """
        if len(path) <= max_len:
            return path
        half = (max_len - 3) // 2
        return path[:half] + "..." + path[-half:]

    def _on_recent_click(self, event: wx.CommandEvent) -> None:
        """Handle click on a recent-file menu item.

        Looks up the path from ``self._recent_items`` by menu item ID
        and loads the conversation. Stale events from old menu items
        are silently ignored.
        """
        item_id = event.GetId()
        path = self._recent_items.get(item_id)
        if path is None:
            return
        self._load_recent(path)

    def _load_recent(self, path: str) -> None:
        """Load a conversation from a recent-file path.

        Args:
            path: Absolute path to a conversation JSON file.
        """
        try:
            conv, system_prompt = Conversation.load(Path(path))
            self._conversation = conv
            self._config.system_prompt = system_prompt
            self._config.last_session_path = os.path.abspath(path)
            self._config.recent_files = update_recents(
                path, self._config.recent_files,
            )
            try:
                save_config(self._config)
            except OSError:
                pass
            self.chat_panel.set_history(
                [(m["role"], m["content"]) for m in conv.messages]
            )
            try:
                self._speech.speak("Conversación cargada", interrupt=True)
            except Exception:
                pass
        except Exception as e:
            error_msg = f"No se pudo cargar la conversación: {e}"
            try:
                self._speech.speak(error_msg, interrupt=True)
            except Exception:
                pass

    # ── Export ──────────────────────────────────────────────────────────────

    def _on_export(self) -> None:
        """Export the current conversation to a Markdown file.

        Shows a ``wx.FileDialog`` with Markdown and Text wildcards.
        Writes UTF-8 content and announces the result via speech.
        Never crashes on failure.
        """
        dialog = wx.FileDialog(
            self,
            message="Exportar a Markdown",
            defaultDir="",
            defaultFile="",
            wildcard="Markdown (*.md)|*.md|Text (*.txt)|*.txt",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )
        if dialog.ShowModal() == wx.ID_OK:
            filepath = dialog.GetPath()
            try:
                md = self._conversation.to_markdown(
                    system_prompt=self._config.system_prompt,
                )
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(md)
                try:
                    self._speech.speak(
                        f"Exportado a {Path(filepath).name}",
                        interrupt=True,
                    )
                except Exception:
                    pass
            except Exception:
                try:
                    self._speech.speak(
                        "Error al exportar", interrupt=True,
                    )
                except Exception:
                    pass
        dialog.Destroy()

    # ── Auto-restore ────────────────────────────────────────────────────────

    def _auto_restore_last_session(self) -> None:
        """Restore the last session on startup if configured.

        Called via ``wx.CallAfter`` from ``__init__`` so the window is
        shown before any I/O. Never crashes on failure: errors are logged
        and the session path is cleared.
        """
        if not should_auto_restore(self._config):
            return
        path_str = self._config.last_session_path
        try:
            conv, system_prompt = Conversation.load(Path(path_str))
            self._conversation = conv
            self._config.system_prompt = system_prompt
            self.chat_panel.set_history(
                [(m["role"], m["content"]) for m in conv.messages]
            )
            try:
                self._speech.speak("Sesión restaurada", interrupt=True)
            except Exception:
                pass
        except Exception:
            self._config.last_session_path = ""
            try:
                save_config(self._config)
            except OSError:
                pass
            try:
                self._speech.speak(
                    "No se pudo restaurar la última sesión",
                    interrupt=True,
                )
            except Exception:
                pass

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
            Conversation.save(
                self._conversation, filepath,
                system_prompt=self._config.system_prompt,
            )
            # Persist session path and recents only on successful save
            self._config.last_session_path = os.path.abspath(filepath)
            self._config.recent_files = update_recents(
                filepath, self._config.recent_files,
            )
            try:
                save_config(self._config)
            except OSError:
                pass
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
                self._conversation, system_prompt = Conversation.load(filepath)
                self._config.system_prompt = system_prompt
                self._config.last_session_path = os.path.abspath(filepath)
                self._config.recent_files = update_recents(
                    filepath, self._config.recent_files,
                )
                save_config(self._config)
                self.chat_panel.set_history(
                    [(m["role"], m["content"]) for m in self._conversation.messages]
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
        """Start a new conversation, clearing current state.

        Confirm with the user when there are messages to discard, matching
        the _on_close pattern. Stock labels (Yes/No) are safe per AGENTS.md:
        only custom Spanish labels trigger MSAA regressions.
        """
        if self._conversation.messages and self._config.confirm_new_conversation:
            dlg = wx.MessageDialog(
                self,
                message=(
                    "¿Empezar nueva conversación? "
                    "Se perderá la conversación actual."
                ),
                caption="Nueva conversación",
                style=wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
            )
            result = dlg.ShowModal()
            dlg.Destroy()
            if result != wx.ID_YES:
                return

        if self._is_generating:
            self._client.abort()
            self._speech.stop()
            self._speech.clear_buffer()
            self._is_generating = False
        self._vision_capable = False
        self._conversation.clear()
        self.chat_panel.clear()
        self._current_response = ""
        self._tool_iteration_count = 0
        self._pre_send_warned_this_conv = False
        self._context_warned_for_turn = False
        self._speech.speak("Nueva conversación", interrupt=True)

    # ── Window Close ──────────────────────────────────────────────────────────

    def _on_close(self, event: wx.CloseEvent) -> None:
        """Handle window close with confirmation, cleanup, and abort.

        The confirm dialog runs FIRST; only after the user confirms
        do we set `_is_closing = True` to gate background threads.
        If the user cancels (No), the app stays fully functional:
        the 8s announce timer keeps firing, F2 status stays accurate,
        and the context menu continues to behave correctly. Setting
        the flag before the dialog would leave it stuck at True for
        the rest of the app's life after any cancelled close.
        """
        log = get_logger()
        log.info("Window close requested")

        # Confirm if there are unsaved messages
        if len(self._conversation.messages) > 0:
            dlg = wx.MessageDialog(
                self,
                message="¿Salir sin guardar la conversación actual?",
                caption="Confirmar salida",
                style=wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
            )
            result = dlg.ShowModal()
            dlg.Destroy()
            if result != wx.ID_YES:
                log.info("User cancelled close; app continues running")
                event.Veto()
                return

        # User confirmed (or no messages to save). NOW gate background threads.
        self._is_closing = True
        log.info("Aborting stream and stopping llama-server")
        self._client.abort()
        stop_server()

        # Cancel any in-flight URL fetch timer
        if self._url_fetch_timer is not None:
            self._url_fetch_timer.cancel()
            self._url_fetch_timer = None

        # Clean up temporary HTML files
        for p in self._temp_html_files:
            try:
                os.unlink(p)
            except OSError:
                pass
        self._temp_html_files.clear()

        event.Skip()

    # ── Help Dialogs ────────────────────────────────────────────────────────

    def _show_about(self) -> None:
        """Show About dialog."""
        about_msg = (
            "Bellbird v0.5.0\n\n"
            "Cliente accesible de chat para modelos locales .gguf\n"
            "usando llama-server (llama.cpp).\n"
            "Diseñado para usuarios de lectores de pantalla."
        )
        wx.MessageDialog(
            self,
            message=about_msg,
            caption="Acerca de Bellbird",
            style=wx.OK | wx.ICON_INFORMATION,
        ).ShowModal()
        self._speech.speak(about_msg, interrupt=True)

    def _show_shortcuts(self) -> None:
        """Show keymap-driven shortcuts dialog.

        Builds a ``wx.Dialog`` (NOT ``wx.MessageDialog`` per AGENTS.md)
        with a read-only multiline ``wx.TextCtrl`` body filled by
        ``Keymap.format_shortcuts_text()``. The dialog has a "Cerrar"
        button with ``name="close_shortcuts_button"`` and responds to
        Escape.
        """
        body_text = self._keymap.format_shortcuts_text()
        dlg = wx.Dialog(self, name="shortcuts_dialog", title="Atajos de teclado")

        root_sizer = wx.BoxSizer(wx.VERTICAL)

        label = wx.StaticText(dlg, label="Atajos de teclado disponibles:")
        root_sizer.Add(label, flag=wx.ALL, border=12)

        body = wx.TextCtrl(
            dlg,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2,
            name="shortcuts_text",
        )
        body.SetValue(body_text)
        root_sizer.Add(body, proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=12)

        close_btn = wx.Button(dlg, label="Cerrar", name="close_shortcuts_button")
        close_btn.Bind(wx.EVT_BUTTON, lambda evt: dlg.EndModal(wx.ID_OK))
        close_sizer = wx.BoxSizer(wx.HORIZONTAL)
        close_sizer.Add(close_btn, flag=wx.ALIGN_CENTER)
        root_sizer.Add(close_sizer, flag=wx.ALIGN_CENTER | wx.ALL, border=12)

        dlg.SetSizer(root_sizer)
        dlg.SetEscapeId(wx.ID_CANCEL)  # Escape closes the dialog
        dlg.SetInitialSize(wx.Size(500, 400))
        close_btn.SetFocus()

        dlg.ShowModal()
        self._speech.speak(body_text, interrupt=True)
        dlg.Destroy()

    def _open_log_file(self) -> None:
        """Open the debug log file in a text editor."""
        log_path = get_log_path()
        if log_path is None or not log_path.is_file():
            self._speech.speak("El archivo de log no existe aún", interrupt=True)
            return
        self._speech.speak(f"Abriendo log: {log_path.name}", interrupt=True)
        if sys.platform == "win32":
            subprocess.Popen(["notepad.exe", str(log_path)])
        else:
            subprocess.Popen(["xdg-open", str(log_path)])

    def _show_preferences(self) -> None:
        """Open the PreferencesDialog, persist on OK, leave untouched on Cancel.

        On OK, compares the previous ``keymap_overrides`` with the new ones
        returned by the dialog. If they differ, calls
        ``self.rebuild_accelerator_table()`` BEFORE assigning
        ``self._config`` so the new bindings are live without a restart.
        """
        # Snapshot keymap_overrides before the dialog modifies them
        old_overrides = dict(self._config.keymap_overrides)
        dlg = PreferencesDialog(self, self._config)
        if dlg.ShowModal() == wx.ID_OK:
            new_config = dlg.get_config()
            # Diff keymap_overrides — rebuild accelerator table if changed
            if new_config.keymap_overrides != old_overrides:
                self.rebuild_accelerator_table()
            old_port = self._config.port
            self._config = new_config
            save_config(self._config)
            if self._config.port != old_port:
                self._client = LlamaClient(
                    base_url=f"http://localhost:{self._config.port}"
                )
        dlg.Destroy()
