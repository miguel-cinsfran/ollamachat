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

from bellbird import __version__ as _BELLBIRD_VERSION
from bellbird.core.conversation import Conversation
from bellbird.core.llama_client import LlamaClient
from bellbird.core.llama_runner import (
    auto_cuda_binary,
    download_server_binary,
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
from bellbird.ui.personas_dialog import PersonasDialog
from bellbird.core.personas import load_personas, find_by_id
from bellbird.ui.wx_notifier import WxToastSender
from bellbird.core.notifier import Notifier
from bellbird.core.system_voice import SystemVoice
from bellbird.core.sound_player import SoundPlayer
from bellbird.core.text_utils import strip_markdown
from bellbird.core.status_formatter import SessionSnapshot, format_status
from bellbird.core.context_advisor import read_vram, estimate_fit, pre_send_check, PreSendSnapshot, token_count
from bellbird.core.model_meta import read_gguf_metadata, estimate_size_bytes, GGUFMetadata
from bellbird.core.payload import build_options, build_api_messages
from bellbird.core.tool_catalog import (
    SHELL_TOOL,
    FILE_TOOL_NAMES,
    FILE_TOOL_RISK,
    display_command,
    get_enabled_tools,
)


from bellbird.ui._server_mixin import ServerMixin
from bellbird.ui._stream_mixin import StreamMixin


class _NullToastSender:
    """No-op toast sender for non-win32 platforms."""

    def show(self, title: str, message: str, timeout: int = 5) -> None:
        pass


class MainWindow(ServerMixin, StreamMixin, wx.Frame):
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
            # Notifier contract: focus_check returns True when the window HAS
            # focus (it stays silent in that case). IsActive() is already that
            # predicate — negating it inverted notifications (fired while
            # focused, silent while in the background).
            focus_check=lambda: self.IsActive(),
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
        self._loading_timer: "_PeriodicAnnouncer | None" = None
        self._url_fetch_timer: "_PeriodicAnnouncer | None" = None
        self._model_load_thread: threading.Thread | None = None
        self._is_loading_model: bool = False
        # Models whose template was already reported as not supporting tools,
        # so the warning is announced once per model instead of on every send.
        self._tool_support_warned: set[str] = set()
        self._basename_to_path: dict[str, str] = {}
        self._vision_capable: bool = False
        self._tool_iteration_count: int = 0
        self._tool_executing: bool = False
        # True while the pre-send checks (token_count/VRAM/tool-support) run on
        # a background thread. Blocks re-entrant sends without faking a stream.
        self._preparing_send: bool = False
        self._recent_items: dict[int, str] = {}
        self._recents_menu: wx.Menu | None = None
        self._archivo_menu: wx.Menu | None = None

        # v0.9.0: context advisor + toggleable F2 state
        self._latest_prompt_tokens: int | None = None
        self._latest_completion_tokens: int | None = None
        self._latest_tok_per_s: float | None = None
        self._current_n_ctx: int | None = None
        # Cached so F2 never does blocking HTTP on the UI thread (it felt
        # sluggish/"useless"). Refreshed on load / stop / watchdog.
        self._loaded_model_name: str = ""
        self._server_state_cache: str = "dead"
        self._vram_free_mb: int | None = None
        self._vram_total_mb: int | None = None
        self._fit_status: str | None = None
        self._pre_send_warned_this_conv: bool = False
        # Cached active-persona name so F2 never reads personas.json on the UI
        # thread. Refreshed at startup and whenever the personas dialog closes.
        self._active_persona_name: str = ""
        self._context_warned_for_turn: bool = False
        self._last_f2_mono: float | None = None
        self._meter_threshold_fired: bool = False
        self._downloading_gpu: bool = False
        self._gpu_progress_dlg: "wx.ProgressDialog | None" = None

        # Must be defined before _build_menu() which uses them for Append() IDs.
        self.ID_START_SERVER = wx.NewIdRef()
        self.ID_STOP_SERVER = wx.NewIdRef()
        self.ID_MMPROJ_SELECT = wx.NewIdRef()
        self.ID_CLEAR_MMPROJ = wx.NewIdRef()
        self.ID_DOWNLOAD_GPU = wx.NewIdRef()
        self.ID_USE_SYSTEM_SERVER = wx.NewIdRef()

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
        self._refresh_active_persona_name()
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
        # AppendSubMenu is the non-deprecated way to attach a submenu;
        # Menu.Append(id, text, submenu, help) is deprecated in wxPython 4.2.x.
        archivo_menu.AppendSubMenu(
            self._recents_menu, "&Recientes",
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

        servidor_menu.AppendSeparator()
        menu_mmproj = servidor_menu.Append(
            self.ID_MMPROJ_SELECT, "Seleccionar mm&proj para modelo actual...",
            "Asignar archivo mmproj al modelo cargado (necesario para imágenes/visión)",
        )
        self.Bind(wx.EVT_MENU, lambda evt: self._on_select_mmproj(), menu_mmproj)

        menu_clear_mmproj = servidor_menu.Append(
            self.ID_CLEAR_MMPROJ, "&Quitar mmproj del modelo actual",
            "Eliminar la asignación de mmproj guardada para el modelo seleccionado",
        )
        self.Bind(wx.EVT_MENU, lambda evt: self._on_clear_mmproj(), menu_clear_mmproj)

        servidor_menu.AppendSeparator()
        menu_download_gpu = servidor_menu.Append(
            self.ID_DOWNLOAD_GPU, "Descargar llama-server &CUDA (GPU, RTX)...",
            "Descargar build CUDA de llama-server para NVIDIA (~550 MB). Máxima velocidad en RTX.",
        )
        self.Bind(wx.EVT_MENU, lambda evt: self._on_download_gpu_server("cuda"), menu_download_gpu)

        self.ID_DOWNLOAD_VULKAN = wx.NewIdRef()
        menu_download_vulkan = servidor_menu.Append(
            self.ID_DOWNLOAD_VULKAN, "Descargar llama-server &Vulkan (GPU, ~32 MB)...",
            "Descargar build Vulkan de llama-server. Funciona con NVIDIA, AMD e Intel.",
        )
        self.Bind(wx.EVT_MENU, lambda evt: self._on_download_gpu_server("vulkan"), menu_download_vulkan)

        menu_use_system = servidor_menu.Append(
            self.ID_USE_SYSTEM_SERVER, "Usar llama-server del &sistema",
            "Volver al llama-server instalado en el sistema (winget, solo CPU)",
        )
        self.Bind(wx.EVT_MENU, lambda evt: self._on_use_system_server(), menu_use_system)

        menu_bar.Append(servidor_menu, "&Servidor")

        # ── Personas menu ─────────────────────────────────────────────
        personas_menu = wx.Menu()
        self.ID_PERSONAS = wx.NewIdRef()
        menu_personas = personas_menu.Append(
            self.ID_PERSONAS, "&Gestionar personas...\tCtrl+Shift+P",
            "Seleccionar o editar personas / asistentes",
        )
        self.Bind(wx.EVT_MENU, lambda evt: self._show_personas(), menu_personas)
        menu_bar.Append(personas_menu, "&Personas")

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

    def _make_announce_timer(
        self, phrase: str = "Cargando modelo, por favor espera..."
    ) -> "_PeriodicAnnouncer":
        """Return a started, self-cancelling periodic announcer.

        The caller stores it in a slot (``self._loading_timer`` /
        ``self._url_fetch_timer``) and calls ``.cancel()`` on completion. The
        announcer self-cancels via an internal flag, so cancellation is robust
        regardless of how many ticks have fired (see ``_PeriodicAnnouncer``).
        """
        return _PeriodicAnnouncer(
            self._speech, phrase, 8.0, lambda: self._is_closing
        ).start()

    # ── Session Status (F2) ──────────────────────────────────────────────────

    def _refresh_active_persona_name(self) -> None:
        """Resolve config.persona_activa (an id) to a display name and cache it.

        Does a small local read of personas.json — cheap, never HTTP — so it
        runs on the UI thread safely. F2 reads only the cached result. When no
        persona is active (no-persona mode), caches "Sin persona".
        """
        pid = self._config.persona_activa
        if not pid:
            self._active_persona_name = "Sin persona"
            return
        try:
            persona = find_by_id(load_personas(), pid)
            self._active_persona_name = persona.nombre if persona else pid
        except Exception:
            self._active_persona_name = pid


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

        # Build SessionSnapshot from CACHED values only — F2 must never block
        # the UI thread on HTTP (that was the lag the user felt on every press).
        # The model name and server state are refreshed on load/stop/watchdog.
        loaded = self._loaded_model_name
        model_name = Path(loaded).stem if loaded else ""

        server_state = self._server_state_cache

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
            persona=self._active_persona_name,
            vision_capable=self._vision_capable,
            server_backend=self._active_server_backend(),
        )

        toggles = self._config.status_toggles_as_set()
        text = format_status(snapshot, toggles, mode)
        get_logger().info(
            "F2 announce_status: mode=%s toggles=%d text=%r",
            mode, len(toggles), text[:160],
        )

        if not text:
            return  # all toggles off — no speech

        if self._is_generating:
            self._speech.speak(text, interrupt=False)
        else:
            self._speech.output(text)

    def _set_initial_focus(self) -> None:
        """Land initial focus on the model selector.

        Called via wx.CallAfter after the window is shown. The selector is
        the natural first stop — the user picks a model and presses "Usar
        modelo" — so focus lands there even while it is still empty (the
        async scan populates it a moment later). Previously focus went to a
        button, which felt like being dropped mid-toolbar.
        """
        self.model_selector.SetFocus()

    def _play_cue(self, event: str) -> None:
        """Play a local sound cue for *event*, honouring the sound settings.

        For UI feedback that is NOT a background notification (so it should
        not also raise a toast). Notification-class events keep going through
        ``self._notifier.notify(...)``, which plays the same WAV plus a toast.
        Never raises.
        """
        if self._config.sounds_enabled and self._config.sound_theme != "none":
            try:
                self._sound_player.play(event)
            except Exception:
                pass

    def _play_loop(self, event: str) -> None:
        """Start a looping sound cue (e.g. the "connecting" pad). Never raises."""
        if self._config.sounds_enabled and self._config.sound_theme != "none":
            try:
                self._sound_player.play_loop(event)
            except Exception:
                pass

    def _stop_loop(self) -> None:
        """Stop any looping/async sound cue. Never raises."""
        try:
            self._sound_player.stop()
        except Exception:
            pass

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
        # wx.Menu has no Clear(); remove items explicitly and drop their
        # EVT_MENU bindings so they don't accumulate on every menu open.
        for old_id in self._recent_items:
            self.Unbind(wx.EVT_MENU, id=old_id)
        for item in list(menu.GetMenuItems()):
            menu.Delete(item)
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
            try:
                Conversation.save(
                    self._conversation, filepath,
                    system_prompt=self._config.system_prompt,
                )
            except Exception as e:
                # Disk full, permission denied, etc. Announce via speech
                # (primary feedback for screen-reader users) and leave config
                # untouched — never crash on a failed save.
                self._speech.speak(
                    f"No se pudo guardar la conversación: {e}",
                    interrupt=True,
                )
            else:
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
                err_dlg = wx.MessageDialog(
                    self,
                    message=error_msg,
                    caption="Error",
                    style=wx.OK | wx.ICON_ERROR,
                )
                err_dlg.ShowModal()
                err_dlg.Destroy()
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
        # Reset the context meter so F2 doesn't report the previous chat's usage.
        self._latest_prompt_tokens = None
        self._latest_completion_tokens = None
        self._latest_tok_per_s = None
        self.status_bar.SetStatusText("", 1)
        self._play_cue("new_conversation")
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
            f"Bellbird v{_BELLBIRD_VERSION}\n\n"
            "Cliente accesible de chat para modelos locales .gguf\n"
            "usando llama-server (llama.cpp).\n"
            "Diseñado para usuarios de lectores de pantalla."
        )
        dlg = wx.MessageDialog(
            self,
            message=about_msg,
            caption="Acerca de Bellbird",
            style=wx.OK | wx.ICON_INFORMATION,
        )
        dlg.ShowModal()
        dlg.Destroy()
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
            self._refresh_active_persona_name()
            if self._config.port != old_port:
                self._client = LlamaClient(
                    base_url=f"http://localhost:{self._config.port}"
                )
        dlg.Destroy()

    def _show_personas(self) -> None:
        """Open the PersonasDialog to select or manage personas."""
        dlg = PersonasDialog(self, self._config)
        dlg.ShowModal()
        dlg.save_if_dirty()
        dlg.Destroy()
        save_config(self._config)
        self._refresh_active_persona_name()


# Defined AFTER MainWindow so MainWindow.__init__ remains the first __init__ in
# the module (some AST tests locate "the first __init__" by walk order).
# _make_announce_timer references this lazily at call time, so definition order
# does not matter at runtime.
class _PeriodicAnnouncer:
    """Re-announce a phrase every ``interval`` seconds until cancelled.

    Replaces an earlier chained-``threading.Timer`` design whose re-arm logic
    only tracked the FIRST tick: it compared the live timer against a stale
    closure variable, so from the second tick onward the running timer became
    untracked and ``cancel()`` silently missed it. The symptom was the
    "Cargando modelo, por favor espera…" announcement looping forever after a
    model load finished or failed.

    Cancellation here is driven by an instance flag checked before every
    re-arm, so it is robust no matter how many ticks have fired or which
    attribute slot on ``MainWindow`` holds the announcer.
    """

    def __init__(self, speech, phrase: str, interval: float, is_closing) -> None:
        self._speech = speech
        self._phrase = phrase
        self._interval = interval
        self._is_closing = is_closing  # callable -> bool
        self._cancelled = False
        self._timer: threading.Timer | None = None

    def start(self) -> "_PeriodicAnnouncer":
        self._arm()
        return self

    def _arm(self) -> None:
        if self._cancelled:
            return
        t = threading.Timer(self._interval, self._tick)
        t.daemon = True
        self._timer = t
        t.start()

    def _tick(self) -> None:
        if self._cancelled or self._is_closing():
            return
        try:
            self._speech.speak(self._phrase, interrupt=False)
        except Exception:
            pass
        self._arm()

    def cancel(self) -> None:
        self._cancelled = True
        if self._timer is not None:
            self._timer.cancel()
