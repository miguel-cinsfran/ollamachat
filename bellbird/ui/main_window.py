"""MainWindow — top-level application shell for Bellbird.

Vertical BoxSizer layout: top row (model selector + server controls),
ChatPanel (full width). Coordinates the send/receive flow between
LlamaClient, LlamaRunner, Conversation, and Speech.
"""

import os
import sys
import tempfile
import threading
import time
import webbrowser

import wx

from pathlib import Path

import markdown

from bellbird.core.conversation import Conversation
from bellbird.core.llama_client import LlamaClient
from bellbird.core.llama_runner import (
    find_gguf_models,
    find_llama_server,
    get_install_command,
    start_server,
    stop_server,
)
from bellbird.core.logger import get_logger
from bellbird.core.speech import Speech
from bellbird.ui.chat_panel import ChatPanel
from bellbird.core.config import load_config
from bellbird.core.permission_manager import PermissionManager
from bellbird.core.tool_executor import ToolExecutor, ToolResult
from bellbird.ui.permission_dialog import PermissionDialog
from bellbird.ui.preferences_dialog import PreferencesDialog
from bellbird.core.config import save_config

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
            base_url=f"http://localhost:{self._config.port}"
        )
        self._conversation = Conversation()
        self._speech = Speech()
        self._current_response: str = ""
        self._is_generating = False
        self._is_closing = False
        self._temp_html_files: list[str] = []
        self._last_usage: dict | None = None
        self._permission_manager = PermissionManager()
        self._tool_executor = ToolExecutor()
        self._focus_cycle_index = 0
        self._last_beep_time = 0.0
        self._loading_timer: threading.Timer | None = None
        self._model_load_thread: threading.Thread | None = None
        self._basename_to_path: dict[str, str] = {}

        self._build_ui()
        self._build_menu()
        self._build_accelerators()
        self._create_status_bar()
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self._startup_check()
        wx.CallAfter(self._set_initial_focus)

    # ── UI Construction ───────────────────────────────────────────────────

    def _build_ui(self) -> None:
        """Build the vertical BoxSizer layout: top row + ChatPanel."""
        # ── Model selector (Frame child) ──────────────────────────────
        self.model_selector = wx.ComboBox(self, name="model_selector")
        if self._config.last_model:
            self.model_selector.SetValue(self._config.last_model)
        self.model_selector.Bind(wx.EVT_COMBOBOX, self._on_model_select)
        self.model_selector.Bind(wx.EVT_TEXT, self._on_model_text_change)

        self.scan_models_button = wx.Button(
            self, label="Buscar modelos", name="scan_models_button"
        )
        self.browse_model_button = wx.Button(
            self, label="Explorar...", name="browse_model_button"
        )
        self.use_model_button = wx.Button(
            self, label="Usar modelo", name="use_model_button"
        )
        self.use_model_button.Disable()

        # ── Server controls (Frame children) ──────────────────────────
        self.restart_server_button = wx.Button(
            self, label="Iniciar servidor", name="restart_server_button"
        )
        self.stop_server_button = wx.Button(
            self, label="Detener servidor", name="stop_server_button"
        )
        self.stop_server_button.Disable()

        # ── Top row: model controls + server controls ─────────────────
        top_row = wx.BoxSizer(wx.HORIZONTAL)

        top_row.Add(
            wx.StaticText(self, label="Modelo:"),
            flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4,
        )
        top_row.Add(self.model_selector, proportion=1, flag=wx.EXPAND)
        top_row.Add(self.scan_models_button, flag=wx.LEFT, border=4)
        top_row.Add(self.browse_model_button, flag=wx.LEFT, border=4)
        top_row.Add(self.use_model_button, flag=wx.LEFT, border=4)

        top_row.AddSpacer(20)

        top_row.Add(
            wx.StaticText(self, label="Servidor:"),
            flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=4,
        )
        top_row.Add(
            self.restart_server_button, flag=wx.ALIGN_CENTER_VERTICAL
        )
        top_row.Add(
            self.stop_server_button,
            flag=wx.ALIGN_CENTER_VERTICAL | wx.LEFT, border=4,
        )

        # ── Chat panel (Frame child, full width) ──────────────────────
        self.chat_panel = ChatPanel(
            self, self._speech,
            on_send=self.send_message,
            on_delete_message=self._on_history_delete,
        )

        # ── Root vertical sizer ───────────────────────────────────────
        root_sizer = wx.BoxSizer(wx.VERTICAL)
        root_sizer.Add(top_row, flag=wx.EXPAND | wx.ALL, border=8)
        root_sizer.Add(self.chat_panel, proportion=1, flag=wx.EXPAND)
        self.SetSizer(root_sizer)

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

    # ── Model control helpers (inlined from params_panel.py) ────────────

    def set_models(self, paths: list[str]) -> None:
        """Populate the model selector with .gguf file basenames.

        Replaces the entire selection. Used by the "Buscar modelos" scan.

        Args:
            paths: List of absolute paths to .gguf files.
        """
        self.model_selector.Clear()
        self._basename_to_path.clear()
        for path_str in paths:
            path = Path(path_str)
            self._basename_to_path[path.name] = str(path)
            self.model_selector.Append(path.name)
        if paths:
            self.model_selector.SetSelection(0)
            self.use_model_button.Enable()
        else:
            self.use_model_button.Disable()

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

        Resolution order:
        1. If the ComboBox value matches a key in _basename_to_path,
           return the mapped absolute path.
        2. If the value looks like a path (contains /, \\, or :) and
           the file exists on disk, return it verbatim.
        3. Otherwise return ''.

        Returns:
            Absolute path string, or '' if no valid model selected.
        """
        value = self.model_selector.GetValue()
        if not value:
            return ""

        # Rule 1: basename lookup
        if value in self._basename_to_path:
            return self._basename_to_path[value]

        # Rule 2: typed path
        if any(c in value for c in ("\\", "/", ":")):
            p = Path(value)
            if p.is_file():
                return str(p.resolve())

        # Rule 3: not found
        return ""

    def _on_model_select(self, event: wx.CommandEvent) -> None:
        """Handle model selector selection change."""
        if self.model_selector.GetCount() > 0:
            self.use_model_button.Enable()
        else:
            self.use_model_button.Disable()

    def _on_model_text_change(self, event: wx.CommandEvent) -> None:
        """Enable use_model_button when the combo box has any non-empty text."""
        value = self.model_selector.GetValue().strip()
        if value:
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

        menu_prefs = archivo_menu.Append(
            wx.ID_PREFERENCES, "Preferencias\tCtrl+,",
            "Abrir el diálogo de preferencias",
        )
        menu_prefs.SetName("menu_preferences")
        self.Bind(wx.EVT_MENU, lambda evt: self._show_preferences(), menu_prefs)

        menu_exit = archivo_menu.Append(
            wx.ID_EXIT, "Salir\tAlt+F4", "Salir de Bellbird"
        )
        menu_exit.SetName("menu_exit")
        self.Bind(wx.EVT_MENU, lambda evt: self.Close(), menu_exit)

        menu_bar.Append(archivo_menu, "Archivo")

        # ── Servidor menu ─────────────────────────────────────────────
        servidor_menu = wx.Menu()

        menu_start = servidor_menu.Append(
            self.ID_START_SERVER, "Iniciar servidor\tF7",
            "Iniciar llama-server con el modelo seleccionado",
        )
        menu_start.SetName("menu_start_server")
        # Bound to _on_use_model via ID_START_SERVER in _build_accelerators

        menu_stop = servidor_menu.Append(
            self.ID_STOP_SERVER, "Detener servidor\tCtrl+F7",
            "Detener llama-server",
        )
        menu_stop.SetName("menu_stop_server")
        # Bound to _on_stop_server via ID_STOP_SERVER in _build_accelerators

        servidor_menu.AppendSeparator()

        menu_scan = servidor_menu.Append(
            wx.ID_REFRESH, "Buscar modelos\tF5",
            "Buscar modelos .gguf en el sistema",
        )
        menu_scan.SetName("menu_scan_models")
        # Bound to _scan_models via wx.ID_REFRESH in _build_accelerators

        menu_bar.Append(servidor_menu, "Servidor")

        # ── Ayuda menu ────────────────────────────────────────────────
        ayuda_menu = wx.Menu()
        menu_about = ayuda_menu.Append(
            wx.ID_ABOUT, "Acerca de", "Acerca de Bellbird"
        )
        menu_about.SetName("menu_about")
        self.Bind(wx.EVT_MENU, lambda evt: self._show_about(), menu_about)

        self.ID_SHORTCUTS = wx.NewIdRef()
        menu_shortcuts = ayuda_menu.Append(
            self.ID_SHORTCUTS,
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
        # Define custom IDs for new accelerators
        self.ID_FOCUS_INPUT = wx.NewIdRef()
        self.ID_FOCUS_LIST = wx.NewIdRef()
        self.ID_FOCUS_MODEL = wx.NewIdRef()
        self.ID_FOCUS_TEMP = wx.NewIdRef()
        self.ID_FOCUS_SYSPROMPT = wx.NewIdRef()
        self.ID_FOCUS_USE = wx.NewIdRef()
        self.ID_F2 = wx.NewIdRef()
        self.ID_F6 = wx.NewIdRef()
        self.ID_START_SERVER = wx.NewIdRef()
        self.ID_STOP_SERVER = wx.NewIdRef()

        accel_entries = [
            wx.AcceleratorEntry(wx.ACCEL_CTRL, ord("N"), wx.ID_NEW),
            wx.AcceleratorEntry(wx.ACCEL_CTRL, ord("O"), wx.ID_OPEN),
            wx.AcceleratorEntry(wx.ACCEL_CTRL, ord("S"), wx.ID_SAVE),
            wx.AcceleratorEntry(wx.ACCEL_NORMAL, wx.WXK_F5, wx.ID_REFRESH),
            wx.AcceleratorEntry(wx.ACCEL_NORMAL, wx.WXK_ESCAPE, wx.ID_STOP),
            wx.AcceleratorEntry(wx.ACCEL_ALT, ord("1"), self.ID_FOCUS_INPUT),
            wx.AcceleratorEntry(wx.ACCEL_ALT, ord("2"), self.ID_FOCUS_LIST),
            wx.AcceleratorEntry(wx.ACCEL_ALT, ord("3"), self.ID_FOCUS_MODEL),
            # Alt+4 and Alt+5 removed in v0.5.0 (controls moved to PrefsDialog)
            wx.AcceleratorEntry(wx.ACCEL_ALT, ord("6"), self.ID_FOCUS_USE),
            wx.AcceleratorEntry(wx.ACCEL_NORMAL, wx.WXK_F2, self.ID_F2),
            wx.AcceleratorEntry(wx.ACCEL_NORMAL, wx.WXK_F6, self.ID_F6),
            wx.AcceleratorEntry(wx.ACCEL_NORMAL, wx.WXK_F7, self.ID_START_SERVER),
            wx.AcceleratorEntry(wx.ACCEL_CTRL, wx.WXK_F7, self.ID_STOP_SERVER),
            wx.AcceleratorEntry(wx.ACCEL_CTRL, ord(","), wx.ID_PREFERENCES),
        ]

        # Bind standard accelerators
        self.Bind(
            wx.EVT_MENU,
            lambda evt: self._scan_models(),
            id=wx.ID_REFRESH,
        )
        self.Bind(
            wx.EVT_MENU,
            lambda evt: self.abort_generation(),
            id=wx.ID_STOP,
        )

        # Bind new focus accelerators
        self.Bind(
            wx.EVT_MENU,
            lambda evt: self.chat_panel.message_input.SetFocus(),
            id=self.ID_FOCUS_INPUT,
        )
        self.Bind(
            wx.EVT_MENU,
            lambda evt: self._on_focus_list(),
            id=self.ID_FOCUS_LIST,
        )
        self.Bind(
            wx.EVT_MENU,
            lambda evt: self.model_selector.SetFocus(),
            id=self.ID_FOCUS_MODEL,
        )
        # Alt+4 (ID_FOCUS_TEMP) and Alt+5 (ID_FOCUS_SYSPROMPT) removed in
        # v0.5.0 — those controls live in PreferencesDialog now.
        self.Bind(
            wx.EVT_MENU,
            lambda evt: self._on_focus_use(),
            id=self.ID_FOCUS_USE,
        )
        self.Bind(
            wx.EVT_MENU,
            lambda evt: self._announce_session_status(),
            id=self.ID_F2,
        )
        self.Bind(
            wx.EVT_MENU,
            lambda evt: self._on_f6_cycle(),
            id=self.ID_F6,
        )
        self.Bind(
            wx.EVT_MENU,
            lambda evt: self._on_use_model(),
            id=self.ID_START_SERVER,
        )
        self.Bind(
            wx.EVT_MENU,
            lambda evt: self._on_stop_server(),
            id=self.ID_STOP_SERVER,
        )

        accel_table = wx.AcceleratorTable(accel_entries)
        self.SetAcceleratorTable(accel_table)

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
        self.use_model_button.Disable()
        self.restart_server_button.Disable()
        self._speech.speak(
            f"Iniciando servidor con {basename}...", interrupt=True
        )
        self.status_bar.SetStatusText("Iniciando servidor...", 0)
        self._loading_timer = self._make_announce_timer()
        self._model_load_thread = threading.Thread(
            target=self._model_load_worker,
            args=(model,),
            daemon=True,
        )
        self._model_load_thread.start()

    def _model_load_worker(self, model: str) -> None:
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
            )
        except Exception as e:
            message = f"Error: {type(e).__name__}: {e}"
        finally:
            if self._loading_timer is not None:
                self._loading_timer.cancel()
            wx.CallAfter(self._on_start_server_done, ok, message)

    def _make_announce_timer(self) -> threading.Timer:
        """Create a chained timer that announces loading progress.

        First tick fires after 8 seconds; re-arms itself every 8s.
        Cancelled when the load worker completes.
        """
        def _announce() -> None:
            if self._is_closing:
                return
            self._speech.speak(
                "Cargando modelo, por favor espera...", interrupt=False
            )
            self._loading_timer = threading.Timer(8.0, _announce)
            self._loading_timer.daemon = True
            self._loading_timer.start()

        t = threading.Timer(8.0, _announce)
        t.daemon = True
        t.start()
        return t

    def _on_start_server_done(self, ok: bool, message: str) -> None:
        """Handle the result of background server start."""
        if self._loading_timer is not None:
            self._loading_timer.cancel()
            self._loading_timer = None
        if self._is_closing:
            return
        if ok:
            self.status_bar.SetStatusText("Servidor listo", 0)
            loaded = self._client.get_loaded_model()
            self._update_title(loaded or None)
            if "corriendo" not in message:
                self._scan_models()
            if loaded:
                self._speech.output(f"Modelo: {Path(loaded).stem}")
        else:
            self.status_bar.SetStatusText("Error al iniciar", 0)
        self._sync_button_state(ok)
        self._speech.speak(message, interrupt=True)

    def _update_title(self, model: str | None) -> None:
        """Update the window title to show the loaded model."""
        if model:
            self.SetTitle(f"Bellbird — {Path(model).stem}")
        else:
            self.SetTitle("Bellbird")

    # ── Startup ────────────────────────────────────────────────────────────

    def _startup_check(self) -> None:
        """Classify server state into three states and announce."""
        log = get_logger()
        install_cmd = get_install_command()

        if find_llama_server() is None:
            log.warning("Startup: llama-server not installed")
            msg = (
                f"llama-server no instalado. Instalalo con: {install_cmd}."
            )
            self.status_bar.SetStatusText("llama-server no instalado", 0)
            self._speech.speak(msg, interrupt=True)
            wx.MessageDialog(
                self,
                message=msg,
                caption="llama-server no instalado",
                style=wx.OK | wx.ICON_WARNING,
            ).ShowModal()
            return

        if not self._client.check_running():
            log.info("Startup: llama-server installed but not running")
            self.status_bar.SetStatusText("Servidor detenido", 0)
            self._speech.speak(
                "Servidor detenido. Selecciona un modelo y pulsa Iniciar servidor.",
                interrupt=True,
            )
            return

        loaded = self._client.get_loaded_model()
        log.info(f"Startup: connected, model={loaded!r}")
        self.status_bar.SetStatusText(f"Conectado: {loaded}", 0)
        self._speech.speak(
            f"Conectado. Modelo cargado: {loaded}.", interrupt=True
        )
        self._sync_button_state(True)
        self._scan_models()

    def _scan_models(self) -> None:
        """Scan for .gguf files and populate the model selector."""
        log = get_logger()
        paths = find_gguf_models()
        self.set_models(paths)
        if paths:
            log.info(f"Scan: {len(paths)} .gguf file(s) found")
            self._speech.speak(
                f"{len(paths)} modelos encontrados", interrupt=True
            )
        else:
            log.warning("Scan: no .gguf files found")
            self._speech.speak(
                "Ningún modelo .gguf encontrado", interrupt=True
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

        self.status_bar.SetStatusText("Deteniendo servidor...", 0)
        self._speech.speak("Deteniendo servidor...", interrupt=True)

        stop_server()

        self.status_bar.SetStatusText("Servidor detenido", 0)
        self._speech.speak("Servidor detenido", interrupt=True)
        self._sync_button_state(False)
        self._update_title(None)

    # ── Session Status (F2) ──────────────────────────────────────────────────

    def _announce_session_status(self) -> None:
        """Announce the current session status via speech (F2)."""
        model_str = "sin modelo cargado"
        loaded = self._client.get_loaded_model()
        if loaded:
            model_str = Path(loaded).stem

        server_str = (
            "en ejecución" if self._client.check_running() else "detenido"
        )

        msg_count = len(self._conversation.messages) // 2
        msg_str = f"{msg_count} mensajes" if msg_count > 0 else "sin mensajes"

        tokens_str = "Tokens: sin información"
        if self._last_usage:
            total = self._last_usage.get("total_tokens", 0)
            tokens_str = f"{total} tokens"

        temp = self._config.temperature
        topp = self._config.top_p
        temp_str = f"{temp:.2f}".replace(".", ",")
        topp_str = f"{topp:.2f}".replace(".", ",")

        gen_str = "Generando: Sí" if self._is_generating else "Generando: No"

        text = (
            f"Modelo {model_str}. {server_str}. {msg_str}. {tokens_str}. "
            f"Temperatura {temp_str}. Top-p {topp_str}. {gen_str}."
        )
        self._speech.speak(text, interrupt=True)

    def _set_initial_focus(self) -> None:
        """Set initial focus based on server state."""
        if self._client.check_running():
            self.chat_panel.message_input.SetFocus()
        elif self.model_selector.GetCount() > 0:
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
        # Read input and attachments
        user_text = self.chat_panel.get_input_text()
        attached_images = self.chat_panel.get_attached_images()
        attached_text = self.chat_panel.get_attached_text()

        # C3: allow empty text if there are images attached
        if not user_text.strip() and not attached_images:
            return

        # Build API messages
        api_messages = []

        # System prompt (if non-empty)
        system_prompt = self._config.system_prompt
        if system_prompt.strip():
            api_messages.append({"role": "system", "content": system_prompt})

        # Conversation history
        api_messages.extend(self._conversation.get_messages_for_api())

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

        # Start generation
        options = {
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens,
            "top_p": self._config.top_p,
            "top_k": self._config.top_k,
            "repeat_penalty": self._config.repeat_penalty,
        }
        self._current_response = ""

        self.chat_panel.start_generation()
        self._is_generating = True
        self.chat_panel.append_assistant_prefix()

        self.status_bar.SetStatusText("Generando respuesta...", 2)
        self._speech.speak("Generando respuesta...", interrupt=True)

        tools = [SHELL_TOOL_DEFINITION] if self._config.tools_enabled else None

        self._client.chat_stream(
            messages=api_messages,
            options=options,
            on_token=self._on_token,
            on_done=self._on_done,
            on_error=self._on_error,
            on_usage=self._on_usage,
            on_tool_call=self._on_tool_call,
            tools=tools,
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
        """Handle a token fragment from the stream.

        Args:
            token: Token text from the LLM.
        """
        if not self._is_generating:
            return
        self._current_response += token
        self.chat_panel.append_assistant_chunk(token)
        self._maybe_beep()
        self._speech.announce_token_chunk(token)

    def _on_done(self) -> None:
        """Handle stream completion."""
        if not self._is_generating:
            return
        self._speech.flush_token_buffer()
        self._speech.speak("Respuesta completa", interrupt=True)

        # Save assistant message to conversation
        if self._current_response.strip():
            self._conversation.add_message(
                "assistant", self._current_response
            )

        # Separate assistant response from the next user message visually.
        self.chat_panel.append_assistant_chunk("\n")
        self.chat_panel.end_generation()
        self._is_generating = False
        self.status_bar.SetStatusText("", 2)
        self._current_response = ""

    # ── Tool calling (v0.4.0) ─────────────────────────────────────────────

    def _on_tool_call(self, tool_name: str, tool_call_id: str, args: dict) -> None:
        """Callback cuando el modelo solicita ejecutar una herramienta."""
        command = args.get("command", str(args))

        if self._permission_manager.is_system_destructive(command):
            self._speech.speak(
                f"Comando bloqueado por seguridad: {command[:80]}", interrupt=True
            )
            self.chat_panel.append_tool_blocked(tool_name, command)
            return

        if self._permission_manager.has_session_grant(tool_name):
            self._speech.speak(
                f"Ejecutando {tool_name}: {command[:50]}", interrupt=True
            )
            self._run_tool_and_show(tool_name, tool_call_id, command)
            return

        self._speech.speak(
            "El modelo quiere ejecutar un comando. Escucha el comando y confirma.",
            interrupt=True,
        )
        risk = self._permission_manager.classify_risk(command)
        dlg = PermissionDialog(self, tool_name, command, risk)
        result = dlg.ShowModal()
        dlg.Destroy()

        if result == wx.ID_YES:
            self._run_tool_and_show(tool_name, tool_call_id, command)
        elif result == wx.ID_OK:
            self._permission_manager.grant_session(tool_name)
            self._run_tool_and_show(tool_name, tool_call_id, command)
        else:
            self._speech.speak("Ejecucion denegada.", interrupt=True)
            self.chat_panel.append_tool_denied(tool_name)

    def _run_tool_and_show(
        self, tool_name: str, tool_call_id: str, command: str
    ) -> None:
        """Ejecuta la tool en hilo de fondo para no bloquear la UI."""
        def worker() -> None:
            result = self._tool_executor.run(tool_name, command)
            wx.CallAfter(self._on_tool_result, result, tool_call_id)
        threading.Thread(target=worker, daemon=True).start()

    def _on_tool_result(self, result, tool_call_id: str) -> None:
        """Callback en hilo principal con el resultado de la herramienta."""
        self.chat_panel.append_tool_output(result.to_display_text())
        self._speech.speak(
            f"Comando completado, codigo {result.returncode}. Consultando al modelo.",
            interrupt=True,
        )
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
        """Reenvía la conversación al modelo con el resultado de la tool."""
        api_messages = []
        system_prompt = self._config.system_prompt
        if system_prompt.strip():
            api_messages.append({"role": "system", "content": system_prompt})
        api_messages.extend(self._conversation.get_messages_for_api())

        tools = (
            [SHELL_TOOL_DEFINITION]
            if self._config.tools_enabled
            else None
        )

        self._current_response = ""
        self.chat_panel.start_generation()
        self._is_generating = True
        self.chat_panel.append_assistant_prefix()
        self.status_bar.SetStatusText("Consultando al modelo...", 2)

        self._client.chat_stream(
            messages=api_messages,
            options={
                "temperature": self._config.temperature,
                "max_tokens": self._config.max_tokens,
                "top_p": self._config.top_p,
                "top_k": self._config.top_k,
                "repeat_penalty": self._config.repeat_penalty,
            },
            on_token=self._on_token,
            on_done=self._on_done,
            on_error=self._on_error,
            on_usage=self._on_usage,
            on_tool_call=self._on_tool_call,
            tools=tools,
        )

    def _on_error(self, error_text: str) -> None:
        """Handle stream error.

        Args:
            error_text: Error description.
        """
        if not self._is_generating:
            return
        self._current_response = ""
        self.chat_panel.append_assistant_chunk(f"\n[Error: {error_text}]")
        self.chat_panel.end_generation()
        self._is_generating = False
        self.status_bar.SetStatusText("Error", 2)
        wx.MessageDialog(
            self,
            message=error_text,
            caption="Error",
            style=wx.OK | wx.ICON_ERROR,
        ).ShowModal()
        self._speech.speak(error_text, interrupt=True)

    # ── Abort ──────────────────────────────────────────────────────────────

    def abort_generation(self) -> None:
        """Abort the current generation with full silence.

        The sequence MUST be: abort → stop → clear_buffer so the network
        request is cancelled first, then the speech engine stops any
        current utterance, then the token-chunk buffer is discarded
        without speaking.
        """
        self._client.abort()
        self._speech.stop()
        self._speech.clear_buffer()

    # ── Usage & Browser ─────────────────────────────────────────────────────

    def _on_usage(self, usage: dict) -> None:
        """Handle usage stats from the LLM stream.

        Args:
            usage: Dict with prompt_tokens, completion_tokens, total_tokens.
        """
        self._last_usage = usage
        self.status_bar.SetStatusText(
            f"Tokens: {usage.get('total_tokens', 0)}", 1
        )

    def _open_message_in_browser(self, text: str) -> None:
        """Open message content in the default browser via a temp HTML file.

        Args:
            text: Markdown text to render as HTML.
        """
        html = markdown.markdown(text, extensions=[])
        full_html = (
            "<!doctype html><meta charset='utf-8'>"
            f"<body>{html}</body>"
        )
        with tempfile.NamedTemporaryFile(
            suffix=".html", delete=False, mode="w", encoding="utf-8"
        ) as f:
            f.write(full_html)
            temp_path = f.name
        self._temp_html_files.append(temp_path)
        webbrowser.open(f"file:///{temp_path}")

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
        if self._conversation.messages:
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
        self._conversation.clear()
        self.chat_panel.clear()
        self._current_response = ""
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
        """Show keyboard shortcuts dialog."""
        shortcuts = (
            "Atajos de teclado:\n\n"
            "Alt+1: Foco en campo de mensaje\n"
            "Alt+2: Foco en historial\n"
            "Alt+3: Foco en selector de modelo\n"
            "Alt+4: Foco en temperatura\n"
            "Alt+5: Foco en prompt de sistema\n"
            "Alt+6: Foco en usar modelo\n"
            "Ctrl+N: Nueva conversación\n"
            "Ctrl+O: Abrir conversación\n"
            "Ctrl+S: Guardar conversación\n"
            "F2: Anunciar estado de sesión\n"
            "F5: Buscar modelos\n"
            "F6: Ciclar paneles\n"
            "Escape: Detener generación\n"
            "Enter: Enviar mensaje\n"
            "Shift+Enter: Nueva línea en el input\n"
            "F7: Iniciar servidor\n"
            "Ctrl+F7: Detener servidor\n"
            "Ctrl+Enter (en historial): Abrir en navegador\n"
            "Supr (en historial): Eliminar mensaje\n"
        )
        wx.MessageDialog(
            self,
            message=shortcuts,
            caption="Atajos de teclado",
            style=wx.OK | wx.ICON_INFORMATION,
        ).ShowModal()
        self._speech.speak(shortcuts, interrupt=True)

    def _show_preferences(self) -> None:
        """Open the PreferencesDialog, persist on OK, leave untouched on Cancel."""
        dlg = PreferencesDialog(self, self._config)
        if dlg.ShowModal() == wx.ID_OK:
            self._config = dlg.get_config()
            save_config(self._config)
        dlg.Destroy()
