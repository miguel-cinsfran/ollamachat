"""PreferencesDialog — preferences dialog with 7-tab notebook.

Reads/writes BellbirdConfig fields via wx.Notebook with 7 tabs:
General, Modelo, Chat, Herramientas, Avanzado, Atajos, Estado (F2).
Every control has name= and a preceding StaticText label. Speech resolution
for sliders walks the parent chain to find the MainWindow._speech attribute
(same pattern as MessageDetailDialog._on_open_browser).
"""

import dataclasses
from pathlib import Path

import wx

from bellbird.core.config import BellbirdConfig
from bellbird.core.keymap import (
    DEFAULT_KEYMAP,
    Keymap,
    _format_combo,
)
from bellbird.core.preset import ParamPreset, build_preset_from_config
from bellbird.core.status_formatter import DEFAULT_STATUS_TOGGLES
from bellbird.core.context_advisor import estimate_fit, read_vram
from bellbird.core.model_meta import read_gguf_metadata, estimate_size_bytes, GGUFMetadata


# ─── Spanish action labels (stable, one per DEFAULT_KEYMAP entry) ──────────────

_ACTION_LABELS: dict[str, str] = {
    "abort_generation": "&Detener generación",
    "announce_status": "&Estado de sesión",
    "copy_last": "&Copiar último mensaje",
    "cycle_panels": "C&iclar paneles",
    "delete_last_exchange": "E&liminar último intercambio",
    "edit_next": "Editar s&iguiente",
    "edit_previous": "Editar a&nterior",
    "exit": "&Salir",
    "focus_chat": "Enfocar cha&t",
    "focus_models": "Enfocar &modelos",
    "focus_params": "Enfocar &parámetros",
    "focus_server": "Enfocar ser&vidor",
    "new_conversation": "&Nueva conversación",
    "open_conversation": "Abrir conve&rsación",
    "preferences": "&Preferencias",
    "regenerate": "&Regenerar respuesta",
    "save_conversation": "&Guardar conversación",
    "scan_models": "&Buscar modelos",
    "read_selected_message": "&Leer mensaje seleccionado",
    "start_server": "&Iniciar servidor",
    "stop_server": "Detener servid&or",
}


# ─── HINTS table: tooltip + help text for every interactive control ──────────

HINTS = {
    # ── General ──────────────────────────────────────────────────────────
    "Carpetas de modelos adicionales":
        "Carpetas donde buscar modelos .gguf. Agregue o quite con los botones.",
    "pref_add_folder_button":
        "Agregar una carpeta de modelos al listado.",
    "pref_remove_folder_button":
        "Quitar la carpeta seleccionada del listado.",

    # ── Modelo ───────────────────────────────────────────────────────────
    "Prompt de sistema":
        "Instrucción del sistema. Texto libre que antecede a cada mensaje.",
    "pref_temp_slider":
        "Temperatura del modelo. Rango: 0.00 (determinista) a 2.00 (caótico).",
    "pref_min_p_slider":
        "Corte de probabilidad mínima. Rango: 0.00 a 1.00.",
    "pref_max_tokens_spin":
        "Máximo de tokens por respuesta. Rango: 64 a 8192.",

    # Presets sub-panel
    "pref_presets_list":
        "Lista de ajustes preestablecidos. Seleccione y aplique para cargar valores.",
    "pref_presets_apply":
        "Aplicar el preset seleccionado a los controles de esta pestaña.",
    "pref_presets_save":
        "Guardar los valores actuales como un nuevo preset.",
    "pref_presets_delete":
        "Borrar el preset seleccionado.",

    # ── Chat ─────────────────────────────────────────────────────────────
    "pref_confirm_new_conv":
        "Preguntar antes de iniciar una nueva conversación.",

    # ── Lectura (NEW tab) ────────────────────────────────────────────────
    "pref_filter_markdown":
        "Quitar formato markdown (negrita, enlaces, listas) al leer en voz alta.",
    "pref_filter_urls":
        "Quitar enlaces http(s) al leer en voz alta.",
    "pref_filter_emojis":
        "Quitar emojis al leer en voz alta.",
    "pref_filter_code_blocks":
        "Quitar bloques de código ```...``` al leer en voz alta.",

    # ── Herramientas ─────────────────────────────────────────────────────
    "pref_tools_checkbox":
        "Permitir al modelo ejecutar comandos PowerShell.",
    "pref_file_tools_checkbox":
        "Permitir al modelo leer, listar, escribir y editar archivos de texto.",

    # ── Avanzado ─────────────────────────────────────────────────────────
    "pref_top_p_slider":
        "Probabilidad acumulativa. Rango: 0.00 a 1.00.",
    "pref_top_k_spin":
        "Candidatos por paso. Rango: 1 a 200.",
    "pref_repeat_slider":
        "Penalización de repetición. Rango: 1.00 a 2.00.",
    "pref_seed_spin":
        "Semilla del generador. -1 = aleatorio. Rango: -1 a 2147483647.",
    "pref_stop_text":
        "Cadenas de parada (una por línea). El modelo detiene la generación al emitir una.",
    "pref_ctx_size_spin":
        "Tamaño del contexto en tokens. Rango: 512 a 131072.",
    "pref_gpu_layers_spin":
        "Capas GPU (0 = CPU, 99 = todas). Rango: 0 a 200.",
    "pref_port_spin":
        "Puerto del servidor llama-server. Rango: 1024 a 65535.",

    # ── Atajos ───────────────────────────────────────────────────────────
    "keymap_capture_button":
        "Abrir diálogo para capturar una nueva combinación de teclas.",
    "keymap_reset_button":
        "Restaurar la combinación por defecto de esta acción.",

    # ── Audio ────────────────────────────────────────────────────────────
    "pref_system_voice_choice":
        "Voz del sistema SAPI. Seleccione y pruebe antes de usar.",
    "pref_test_voice_button":
        "Reproducir una frase de prueba con la voz seleccionada.",
    "pref_select_voice_button":
        "Abrir selector detallado de voz y velocidad.",
    "pref_rate_slider":
        "Velocidad de la voz del sistema. Rango: -10 a +10.",
    "pref_auto_speak_checkbox":
        "Leer cada respuesta automáticamente con la voz del sistema.",
    "pref_notifications_checkbox":
        "Activar notificaciones del sistema (Windows toast).",
    "pref_sounds_checkbox":
        "Activar sonidos de eventos (inicio, error, mensaje).",
    "pref_sound_theme_choice":
        "Tema de sonido. 'default' = sonidos. 'none' = silencio.",

    # ── Estado (F2) ──────────────────────────────────────────────────────
    "chk_model_name":
        "Mostrar nombre del modelo en estado.",
    "chk_context_pct":
        "Mostrar porcentaje de contexto usado.",
    "chk_max_tokens":
        "Mostrar máximo de tokens por respuesta.",
    "chk_server":
        "Mostrar estado del servidor.",
    "chk_vram":
        "Mostrar VRAM libre.",
    "chk_fit":
        "Mostrar encaje del modelo en VRAM.",
    "chk_message_count":
        "Mostrar cantidad de mensajes.",
    "chk_temperature":
        "Mostrar temperatura activa.",
    "chk_top_p":
        "Mostrar Top-p activo.",
    "chk_tok_per_s":
        "Mostrar tokens por segundo de la última respuesta.",
    "chk_is_generating":
        "Mostrar si el modelo está generando.",

    # ── Capture dialog ───────────────────────────────────────
    "key_capture_accept_button":
        "Aceptar la combinación de teclas capturada.",
    "key_capture_cancel_button":
        "Cancelar la captura de combinación de teclas.",

    # ── Notebook ────────────────────────────────────────────────────────
    "preferences_notebook":
        "Panel de pestañas de preferencias. Use las teclas para navegar entre ellas.",

    # ── Dialog footer ────────────────────────────────────────────────────
    "pref_ok_button":
        "Guardar cambios y cerrar preferencias.",
    "pref_cancel_button":
        "Cancelar cambios y cerrar preferencias.",
}


def _parse_stop_text(text: str) -> list[str]:
    """Parse multiline stop-strings text into a cleaned list.

    Strips whitespace per line, drops empty lines, handles \\r\\n.
    """
    return [line.strip() for line in text.splitlines() if line.strip()]


# ─── Key capture controls ─────────────────────────────────────────────────────


class KeyCaptureControl(wx.Panel):
    """Single-shot key capture panel.

    Binds ``EVT_KEY_DOWN`` and, on the next event with a non-modifier
    keycode, displays a formatted label and speaks it. ``Tab`` and
    ``Escape`` are reserved: Tab speaks "Tecla reservada" and does NOT
    advance focus; Escape closes the parent dialog. Single-shot per
    construction — re-show the control for a new capture.

    Args:
        parent: Parent wx window (the capture mini-dialog).
        speech: Speech instance (or anything with a ``speak`` method).
    """

    def __init__(self, parent: wx.Window, speech: object) -> None:
        super().__init__(parent, name="key_capture_panel")
        self._speech = speech
        self._captured_modifiers: int = 0
        self._captured_keycode: int = 0
        self._captured: bool = False

        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.Add(
            wx.StaticText(self, label="Pulsa la combinación de teclas:"),
            flag=wx.ALL, border=8,
        )
        self._capture_label = wx.StaticText(
            self, label="", name="key_capture_label",
        )
        sizer.Add(self._capture_label, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)

        self.SetSizer(sizer)
        self.Bind(wx.EVT_KEY_DOWN, self._on_key_down)

    # ── Properties ──────────────────────────────────────────────────────

    @property
    def captured(self) -> bool:
        """True if a non-modifier key has been captured."""
        return self._captured

    @property
    def captured_modifiers(self) -> int:
        """Captured modifier bitmask."""
        return self._captured_modifiers

    @property
    def captured_keycode(self) -> int:
        """Captured keycode."""
        return self._captured_keycode

    # ── Event handler ───────────────────────────────────────────────────

    def _on_key_down(self, event: wx.KeyEvent) -> None:
        """Handle EVT_KEY_DOWN: capture the next non-modifier key."""
        keycode = event.GetKeyCode()
        modifiers = event.GetModifiers()

        # Reserved keys
        if keycode == wx.WXK_TAB:
            self._speak("Tecla reservada")
            return  # Consumed — do NOT advance focus

        if keycode == wx.WXK_ESCAPE:
            self._speak("Tecla reservada")
            wx.CallAfter(self._close_parent_dialog)
            return

        # Modifier-only keys — ignore, wait for the next key
        if keycode in (wx.WXK_SHIFT, wx.WXK_CONTROL, wx.WXK_ALT, wx.WXK_MENU):
            return

        # Capture this key
        self._captured_modifiers = modifiers
        self._captured_keycode = keycode
        self._captured = True

        label = _format_combo(modifiers, keycode)
        self._capture_label.SetLabel(label)
        self._speak(label)

        # Let the event propagate so it doesn't interfere with other controls
        event.Skip()

    # ── Helpers ──────────────────────────────────────────────────────────

    def _speak(self, text: str) -> None:
        """Announce text via speech, if available."""
        if self._speech is not None:
            try:
                self._speech.speak(text, interrupt=True)
            except Exception:
                pass

    def _close_parent_dialog(self) -> None:
        """Close the parent mini-dialog with wx.ID_CANCEL (Escape path)."""
        parent = self.GetParent()
        if isinstance(parent, wx.Dialog):
            parent.EndModal(wx.ID_CANCEL)


class _CaptureDialog(wx.Dialog):
    """Modal mini-dialog for capturing a key combination.

    Contains a ``KeyCaptureControl``, an "Aceptar" button, and a
    "Cancelar" button. On Accept, validates the captured combo against
    ``keymap.find_conflict()``. On collision, speaks a Spanish message,
    closes with ``wx.ID_CANCEL``, and keeps the previous binding.

    Args:
        parent: Parent wx window.
        keymap: ``Keymap`` instance (resolved state for conflict
                detection).
        action_id: The action id being rebound.
        speech: Speech instance for announcements.
    """

    def __init__(
        self,
        parent: wx.Window,
        keymap: Keymap,
        action_id: str,
        speech: object,
    ) -> None:
        super().__init__(
            parent, name="keymap_capture_dialog", title="Capturar atajo",
        )
        self._keymap = keymap
        self._action_id = action_id
        self._speech = speech

        root = wx.BoxSizer(wx.VERTICAL)

        # Capture panel
        self._capture = KeyCaptureControl(self, speech)
        root.Add(self._capture, flag=wx.EXPAND | wx.ALL, border=8)

        # ── Buttons ─────────────────────────────────────────────────────
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.accept_btn = wx.Button(
            self, label="Aceptar", name="key_capture_accept_button",
        )
        self.accept_btn.Bind(wx.EVT_BUTTON, self._on_accept)
        self.accept_btn.Disable()  # Enabled after capture
        btn_sizer.Add(self.accept_btn, flag=wx.RIGHT, border=4)

        self.cancel_btn = wx.Button(
            self, label="Cancelar", name="key_capture_cancel_button",
        )
        self.cancel_btn.Bind(
            wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CANCEL),
        )
        btn_sizer.Add(self.cancel_btn)

        root.Add(btn_sizer, flag=wx.ALIGN_CENTER | wx.BOTTOM, border=8)

        self.SetSizer(root)
        self.SetEscapeId(wx.ID_CANCEL)
        self.Fit()
        self.SetInitialSize()
        # Focus the capture panel so EVT_KEY_DOWN fires immediately
        wx.CallAfter(self._capture.SetFocus)

    # ── Event handlers ──────────────────────────────────────────────────

    def _on_accept(self, event: wx.CommandEvent) -> None:
        """Validate the captured combo and close with ID_OK or ID_CANCEL."""
        if not self._capture.captured:
            return  # Should not happen (button is disabled), but guard

        mod = self._capture.captured_modifiers
        kc = self._capture.captured_keycode

        # Check for conflicts excluding the action itself
        conflict = self._keymap.find_conflict(mod, kc)
        if conflict is not None and conflict != self._action_id:
            label = _ACTION_LABELS.get(conflict, conflict)
            msg = f"Combinación ya usada por {label}"
            self._speak(msg)
            self.EndModal(wx.ID_CANCEL)
            return

        self.EndModal(wx.ID_OK)

    def get_captured_combo(self) -> tuple[int, int]:
        """Return the captured ``(modifiers, keycode)`` pair."""
        return (self._capture.captured_modifiers, self._capture.captured_keycode)

    def _speak(self, text: str) -> None:
        """Announce text via speech, if available."""
        if self._speech is not None:
            try:
                self._speech.speak(text, interrupt=True)
            except Exception:
                pass


# ─── PreferencesDialog ─────────────────────────────────────────────────────────


class PreferencesDialog(wx.Dialog):
    """Preferences dialog with 6-tab notebook editing BellbirdConfig.

    Args:
        parent: Parent wx window.
        config: BellbirdConfig to edit (copied via dataclasses.replace
                so Cancel/Escape are no-ops).
    """

    def __init__(self, parent: wx.Window, config: BellbirdConfig) -> None:
        super().__init__(parent, title="Preferencias",
                         name="preferences_dialog")
        self._config = dataclasses.replace(config)

        # Resolve speech from parent chain. Walk up the parent tree until
        # we find an object with _speech (MainWindow exposes _speech).
        # If not found, self._speech stays None and speak() is skipped
        # defensively. Same pattern as MessageDetailDialog._on_open_browser.
        self._speech = None
        p = parent
        while p is not None:
            if hasattr(p, "_speech"):
                self._speech = p._speech
                break
            p = p.GetParent()

        # Keymap for Atajos tab — rebuilt from config overrides
        self._keymap = Keymap(DEFAULT_KEYMAP,
                              overrides=self._config.keymap_overrides)
        # Row widgets keyed by action_id: {action_id: {...}}
        self._keymap_rows: dict[str, dict[str, wx.Window]] = {}

        # Cache VRAM once at dialog construction for Avanzado's Ayuda de encaje
        self._vram_cache: tuple[int | None, int | None] = read_vram()

        self._build_ui()
        self.SetSize((720, 600))
        wx.CallAfter(self._focus_first_control)

    def _build_ui(self) -> None:
        """Build the dialog layout: notebook + OK/Cancel footer."""
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        notebook = wx.Notebook(self, name="preferences_notebook")

        self._build_general_page(notebook)
        self._build_model_page(notebook)
        self._build_chat_page(notebook)
        self._build_lectura_page(notebook)
        self._build_tools_page(notebook)
        self._build_advanced_page(notebook)
        self._build_keymap_page(notebook)
        self._build_audio_page(notebook)
        self._build_status_page(notebook)

        main_sizer.Add(notebook, proportion=1,
                       flag=wx.EXPAND | wx.ALL, border=8)

        # ── Footer: OK / Cancel ────────────────────────────────────────
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.ok_button = wx.Button(
            self, id=wx.ID_OK, label="&Aceptar", name="pref_ok_button",
        )
        self._apply_hint(self.ok_button, "pref_ok_button")
        self.ok_button.Bind(wx.EVT_BUTTON, self._on_ok)
        btn_sizer.Add(self.ok_button, flag=wx.RIGHT, border=4)

        self.cancel_button = wx.Button(
            self, id=wx.ID_CANCEL, label="&Cancelar", name="pref_cancel_button",
        )
        self._apply_hint(self.cancel_button, "pref_cancel_button")
        self.cancel_button.Bind(
            wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CANCEL)
        )
        btn_sizer.Add(self.cancel_button)

        main_sizer.Add(btn_sizer, flag=wx.ALIGN_RIGHT | wx.ALL, border=8)

        self.SetSizer(main_sizer)
        self.SetEscapeId(wx.ID_CANCEL)

    def _build_general_page(self, notebook: wx.Notebook) -> None:
        """Build General tab: extra model folders list + add/remove buttons."""
        panel = wx.Panel(notebook, name="general_page")
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.Add(
            wx.StaticText(panel, label="&Carpetas de modelos adicionales:"),
            flag=wx.LEFT | wx.TOP | wx.BOTTOM, border=8,
        )

        self.extra_folders_list = wx.ListBox(
            panel, name="Carpetas de modelos adicionales",
            choices=self._config.extra_model_folders,
        )
        self._apply_hint(self.extra_folders_list, "Carpetas de modelos adicionales")
        sizer.Add(self.extra_folders_list, proportion=1,
                  flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)

        folder_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.add_folder_button = wx.Button(
            panel, label="&Agregar carpeta", name="pref_add_folder_button",
        )
        self._apply_hint(self.add_folder_button, "pref_add_folder_button")
        self.add_folder_button.Bind(wx.EVT_BUTTON, self._on_add_folder)
        folder_btn_sizer.Add(self.add_folder_button, flag=wx.RIGHT, border=4)

        self.remove_folder_button = wx.Button(
            panel, label="&Quitar seleccionada",
            name="pref_remove_folder_button",
        )
        self._apply_hint(self.remove_folder_button, "pref_remove_folder_button")
        self.remove_folder_button.Bind(
            wx.EVT_BUTTON, self._on_remove_folder
        )
        folder_btn_sizer.Add(self.remove_folder_button)

        sizer.Add(folder_btn_sizer,
                  flag=wx.LEFT | wx.TOP | wx.BOTTOM, border=8)

        panel.SetSizer(sizer)
        notebook.AddPage(panel, "&General")

    def _build_model_page(self, notebook: wx.Notebook) -> None:
        """Build Modelo tab: system prompt + 2 primary samplers (temp + min_p) + max_tokens + presets."""
        panel = wx.Panel(notebook, name="model_page")
        sizer = wx.BoxSizer(wx.VERTICAL)

        # ── System prompt ──────────────────────────────────────────────
        sizer.Add(
            wx.StaticText(panel, label="&Prompt de sistema:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.pref_system_prompt = wx.TextCtrl(
            panel, value=self._config.system_prompt,
            style=wx.TE_MULTILINE, size=(-1, 80), name="Prompt de sistema",
        )
        self._apply_hint(self.pref_system_prompt, "Prompt de sistema")
        sizer.Add(self.pref_system_prompt,
                  flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)

        # ── Temperature slider ─────────────────────────────────────────
        sizer.Add(
            wx.StaticText(panel, label="&Temperatura:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        temp_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.pref_temp_slider = wx.Slider(
            panel, minValue=0, maxValue=200,
            value=int(self._config.temperature * 100),
            name="pref_temp_slider", style=wx.SL_HORIZONTAL,
        )
        self._apply_hint(self.pref_temp_slider, "pref_temp_slider")
        self.pref_temp_label = wx.StaticText(
            panel, label=f"{self._config.temperature:.2f}",
            name="temp_value_label",
        )
        temp_sizer.Add(self.pref_temp_slider, proportion=1, flag=wx.EXPAND)
        temp_sizer.Add(self.pref_temp_label, flag=wx.LEFT, border=4)
        sizer.Add(temp_sizer, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)
        self.pref_temp_slider.Bind(wx.EVT_SLIDER, self._on_slider_change)

        # ── Min-p slider ───────────────────────────────────────────────
        sizer.Add(
            wx.StaticText(panel, label="&Min-p:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        min_p_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.pref_min_p_slider = wx.Slider(
            panel, minValue=0, maxValue=100,
            value=int(self._config.min_p * 100),
            name="pref_min_p_slider", style=wx.SL_HORIZONTAL,
        )
        self._apply_hint(self.pref_min_p_slider, "pref_min_p_slider")
        self.pref_min_p_label = wx.StaticText(
            panel, label=f"{self._config.min_p:.2f}",
            name="min_p_value_label",
        )
        min_p_sizer.Add(self.pref_min_p_slider, proportion=1, flag=wx.EXPAND)
        min_p_sizer.Add(self.pref_min_p_label, flag=wx.LEFT, border=4)
        sizer.Add(min_p_sizer, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)
        self.pref_min_p_slider.Bind(wx.EVT_SLIDER, self._on_slider_change)

        # ── Max tokens ─────────────────────────────────────────────────
        sizer.Add(
            wx.StaticText(panel, label="Má&ximo de tokens:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.pref_max_tokens_spin = wx.SpinCtrl(
            panel, min=64, max=8192,
            initial=self._config.max_tokens,
            name="pref_max_tokens_spin",
        )
        self._apply_hint(self.pref_max_tokens_spin, "pref_max_tokens_spin")
        sizer.Add(self.pref_max_tokens_spin,
                  flag=wx.LEFT | wx.RIGHT, border=8)

        # ── Presets sub-panel ──────────────────────────────────────────
        sizer.Add(
            wx.StaticText(panel, label="&Ajustes preestablecidos:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.pref_presets_list = wx.ListBox(
            panel, name="pref_presets_list",
            choices=[p.name for p in self._config.param_presets],
        )
        self._apply_hint(self.pref_presets_list, "pref_presets_list")
        sizer.Add(self.pref_presets_list,
                  flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)

        preset_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.pref_presets_apply = wx.Button(
            panel, label="&Aplicar", name="pref_presets_apply",
        )
        self._apply_hint(self.pref_presets_apply, "pref_presets_apply")
        self.pref_presets_apply.Bind(wx.EVT_BUTTON, self._on_apply_preset)
        preset_btn_sizer.Add(self.pref_presets_apply, flag=wx.RIGHT, border=4)

        self.pref_presets_save = wx.Button(
            panel, label="&Guardar actual como…", name="pref_presets_save",
        )
        self._apply_hint(self.pref_presets_save, "pref_presets_save")
        self.pref_presets_save.Bind(wx.EVT_BUTTON, self._on_save_preset)
        preset_btn_sizer.Add(self.pref_presets_save, flag=wx.RIGHT, border=4)

        self.pref_presets_delete = wx.Button(
            panel, label="&Borrar", name="pref_presets_delete",
        )
        self._apply_hint(self.pref_presets_delete, "pref_presets_delete")
        self.pref_presets_delete.Bind(wx.EVT_BUTTON, self._on_delete_preset)
        preset_btn_sizer.Add(self.pref_presets_delete)

        sizer.Add(preset_btn_sizer,
                  flag=wx.LEFT | wx.TOP | wx.BOTTOM, border=8)

        sizer.AddStretchSpacer()
        panel.SetSizer(sizer)
        notebook.AddPage(panel, "&Modelo")

    def _build_chat_page(self, notebook: wx.Notebook) -> None:
        """Build Chat tab: confirm_new_conversation checkbox."""
        panel = wx.Panel(notebook, name="chat_page")
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.Add(
            wx.StaticText(panel, label="&Comportamiento:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.pref_confirm_new_conv = wx.CheckBox(
            panel, label="C&onfirmar al iniciar nueva conversación",
            name="pref_confirm_new_conv",
        )
        self._apply_hint(self.pref_confirm_new_conv, "pref_confirm_new_conv")
        self.pref_confirm_new_conv.SetValue(
            self._config.confirm_new_conversation
        )
        sizer.Add(self.pref_confirm_new_conv,
                  flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)

        sizer.AddStretchSpacer()
        panel.SetSizer(sizer)
        notebook.AddPage(panel, "C&hat")

    def _build_lectura_page(self, notebook: wx.Notebook) -> None:
        """Build Lectura tab: 4 reading-filter checkboxes."""
        panel = wx.Panel(notebook, name="lectura_page")
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.Add(
            wx.StaticText(panel, label="Filtros de lectura (al leer en voz &alta con SAPI):"),
            flag=wx.LEFT | wx.TOP | wx.BOTTOM, border=8,
        )

        self.pref_filter_markdown = wx.CheckBox(
            panel, label="&Quitar markdown al leer",
            name="pref_filter_markdown",
        )
        self.pref_filter_markdown.SetValue(self._config.filter_strip_markdown)
        self._apply_hint(self.pref_filter_markdown, "pref_filter_markdown")
        sizer.Add(self.pref_filter_markdown,
                  flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)

        self.pref_filter_urls = wx.CheckBox(
            panel, label="Quitar &URLs al leer",
            name="pref_filter_urls",
        )
        self.pref_filter_urls.SetValue(self._config.filter_strip_urls)
        self._apply_hint(self.pref_filter_urls, "pref_filter_urls")
        sizer.Add(self.pref_filter_urls,
                  flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)

        self.pref_filter_emojis = wx.CheckBox(
            panel, label="Quitar &emojis al leer",
            name="pref_filter_emojis",
        )
        self.pref_filter_emojis.SetValue(self._config.filter_strip_emojis)
        self._apply_hint(self.pref_filter_emojis, "pref_filter_emojis")
        sizer.Add(self.pref_filter_emojis,
                  flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)

        self.pref_filter_code_blocks = wx.CheckBox(
            panel, label="Quitar &bloques de código al leer",
            name="pref_filter_code_blocks",
        )
        self.pref_filter_code_blocks.SetValue(
            self._config.filter_strip_code_blocks
        )
        self._apply_hint(self.pref_filter_code_blocks, "pref_filter_code_blocks")
        sizer.Add(self.pref_filter_code_blocks,
                  flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)

        sizer.AddStretchSpacer()
        panel.SetSizer(sizer)
        notebook.AddPage(panel, "&Lectura")

    def _build_tools_page(self, notebook: wx.Notebook) -> None:
        """Build Herramientas tab: tools_enabled and file_tools_enabled checkboxes."""
        panel = wx.Panel(notebook, name="tools_page")
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.Add(
            wx.StaticText(panel, label="&PowerShell:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.pref_tools_checkbox = wx.CheckBox(
            panel, label="Permitir herramient&as (PowerShell)",
            name="pref_tools_checkbox",
        )
        self._apply_hint(self.pref_tools_checkbox, "pref_tools_checkbox")
        self.pref_tools_checkbox.SetValue(self._config.tools_enabled)
        sizer.Add(self.pref_tools_checkbox,
                  flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)

        sizer.Add(
            wx.StaticText(panel, label="Arc&hivos:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.pref_file_tools_checkbox = wx.CheckBox(
            panel, label="Permitir leer/listar/escr&ibir archivos",
            name="pref_file_tools_checkbox",
        )
        self._apply_hint(self.pref_file_tools_checkbox, "pref_file_tools_checkbox")
        self.pref_file_tools_checkbox.SetValue(self._config.file_tools_enabled)
        sizer.Add(self.pref_file_tools_checkbox,
                  flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)

        sizer.AddStretchSpacer()
        panel.SetSizer(sizer)
        notebook.AddPage(panel, "&Herramientas")

    def _build_advanced_page(self, notebook: wx.Notebook) -> None:
        """Build Avanzado tab: moved samplers + seed + stop + server fields."""
        panel = wx.Panel(notebook, name="advanced_page")
        sizer = wx.BoxSizer(wx.VERTICAL)

        # ── Top-p slider (moved from Modelo) ───────────────────────────
        sizer.Add(
            wx.StaticText(panel, label="&Top-p:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        top_p_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.pref_top_p_slider = wx.Slider(
            panel, minValue=0, maxValue=100,
            value=int(self._config.top_p * 100),
            name="pref_top_p_slider", style=wx.SL_HORIZONTAL,
        )
        self._apply_hint(self.pref_top_p_slider, "pref_top_p_slider")
        self.pref_top_p_label = wx.StaticText(
            panel, label=f"{self._config.top_p:.2f}",
            name="top_p_value_label",
        )
        top_p_sizer.Add(self.pref_top_p_slider, proportion=1, flag=wx.EXPAND)
        top_p_sizer.Add(self.pref_top_p_label, flag=wx.LEFT, border=4)
        sizer.Add(top_p_sizer, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)
        self.pref_top_p_slider.Bind(wx.EVT_SLIDER, self._on_slider_change)

        # ── Top-k (moved from Modelo) ──────────────────────────────────
        sizer.Add(
            wx.StaticText(panel, label="Top-&k:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.pref_top_k_spin = wx.SpinCtrl(
            panel, min=1, max=200,
            initial=self._config.top_k,
            name="pref_top_k_spin",
        )
        self._apply_hint(self.pref_top_k_spin, "pref_top_k_spin")
        sizer.Add(self.pref_top_k_spin,
                  flag=wx.LEFT | wx.RIGHT, border=8)

        # ── Repeat penalty slider (moved from Modelo) ──────────────────
        sizer.Add(
            wx.StaticText(panel, label="&Penalización de repetición:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        rp_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.pref_repeat_slider = wx.Slider(
            panel, minValue=100, maxValue=200,
            value=int(self._config.repeat_penalty * 100),
            name="pref_repeat_slider", style=wx.SL_HORIZONTAL,
        )
        self._apply_hint(self.pref_repeat_slider, "pref_repeat_slider")
        self.pref_repeat_label = wx.StaticText(
            panel, label=f"{self._config.repeat_penalty:.2f}",
            name="repeat_value_label",
        )
        rp_sizer.Add(self.pref_repeat_slider, proportion=1, flag=wx.EXPAND)
        rp_sizer.Add(self.pref_repeat_label, flag=wx.LEFT, border=4)
        sizer.Add(rp_sizer, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)
        self.pref_repeat_slider.Bind(wx.EVT_SLIDER, self._on_slider_change)

        # ── Seed spin (new) ────────────────────────────────────────────
        sizer.Add(
            wx.StaticText(panel, label="&Semilla:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.pref_seed_spin = wx.SpinCtrl(
            panel, min=-1, max=2147483647,
            initial=self._config.seed,
            name="pref_seed_spin",
        )
        self._apply_hint(self.pref_seed_spin, "pref_seed_spin")
        sizer.Add(self.pref_seed_spin,
                  flag=wx.LEFT | wx.RIGHT, border=8)

        # ── Stop text (new) ────────────────────────────────────────────
        sizer.Add(
            wx.StaticText(panel, label="&Cadenas de parada (una por línea):"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.pref_stop_text = wx.TextCtrl(
            panel, value="\n".join(self._config.stop),
            style=wx.TE_MULTILINE, size=(-1, 60),
            name="pref_stop_text",
        )
        self._apply_hint(self.pref_stop_text, "pref_stop_text")
        sizer.Add(self.pref_stop_text,
                  flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)

        # ── Context size ───────────────────────────────────────────────
        sizer.Add(
            wx.StaticText(panel, label="Tamaño &de contexto (tokens):"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.pref_ctx_size_spin = wx.SpinCtrl(
            panel, min=512, max=131072,
            initial=self._config.ctx_size,
            name="pref_ctx_size_spin",
        )
        self._apply_hint(self.pref_ctx_size_spin, "pref_ctx_size_spin")
        sizer.Add(self.pref_ctx_size_spin,
                  flag=wx.LEFT | wx.RIGHT, border=8)

        # ── GPU layers ─────────────────────────────────────────────────
        sizer.Add(
            wx.StaticText(panel, label="Capas GPU (0 = CPU, 99 = t&odas):"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.pref_gpu_layers_spin = wx.SpinCtrl(
            panel, min=0, max=200,
            initial=self._config.n_gpu_layers,
            name="pref_gpu_layers_spin",
        )
        self._apply_hint(self.pref_gpu_layers_spin, "pref_gpu_layers_spin")
        sizer.Add(self.pref_gpu_layers_spin,
                  flag=wx.LEFT | wx.RIGHT, border=8)

        # ── Ayuda de encaje (T-WU2-06) ────────────────────────────────
        sizer.Add(
            wx.StaticText(panel, label="&Ayuda de encaje:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.pref_fit_help = wx.StaticText(
            panel, label="",
            name="pref_fit_help",
        )
        sizer.Add(self.pref_fit_help,
                  flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)

        # Refresh fit help on context size or GPU layer changes
        self.pref_ctx_size_spin.Bind(
            wx.EVT_SPINCTRL, self._on_advanced_spin_change,
        )
        self.pref_gpu_layers_spin.Bind(
            wx.EVT_SPINCTRL, self._on_advanced_spin_change,
        )

        # ── Server port ────────────────────────────────────────────────
        sizer.Add(
            wx.StaticText(panel, label="Puerto del serv&idor:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.pref_port_spin = wx.SpinCtrl(
            panel, min=1024, max=65535,
            initial=self._config.port,
            name="pref_port_spin",
        )
        self._apply_hint(self.pref_port_spin, "pref_port_spin")
        sizer.Add(self.pref_port_spin,
                  flag=wx.LEFT | wx.RIGHT, border=8)

        sizer.AddStretchSpacer()
        panel.SetSizer(sizer)
        # Populate the fit help with the initial estimate
        self._refresh_fit_help()
        notebook.AddPage(panel, "&Avanzado")

    def _build_keymap_page(self, notebook: wx.Notebook) -> None:
        """Build Atajos tab: one row per DEFAULT_KEYMAP entry.

        Each row has a Spanish action-label StaticText, the current binding
        StaticText, a "Cambiar" button, and a "Restablecer" button.
        Actions are sorted alphabetically by action_id for stability.
        """
        panel = wx.Panel(notebook, name="keymap_page")
        outer_sizer = wx.BoxSizer(wx.VERTICAL)

        outer_sizer.Add(
            wx.StaticText(panel, label="&Atajos de teclado (pulsa Cambiar para reasignar):"),
            flag=wx.LEFT | wx.TOP | wx.BOTTOM, border=8,
        )

        # Scrollable container for the row list
        scroll = wx.ScrolledWindow(panel, name="keymap_scroll")
        scroll_sizer = wx.BoxSizer(wx.VERTICAL)

        sorted_ids = sorted(DEFAULT_KEYMAP.keys())
        for action_id in sorted_ids:
            row_sizer = wx.BoxSizer(wx.HORIZONTAL)

            # Spanish action label
            action_label = _ACTION_LABELS.get(action_id, action_id)
            label_st = wx.StaticText(scroll, label=action_label,
                                     name=f"keymap_action_{action_id}")
            row_sizer.Add(label_st, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=8)

            # Current binding display (computed from resolved combo, not label)
            resolved = self._keymap.actions.get(action_id)
            binding_text = (
                _format_combo(resolved.modifiers, resolved.keycode)
                if resolved else ""
            )
            binding_st = wx.StaticText(scroll, label=binding_text,
                                       name=f"keymap_binding_{action_id}")
            row_sizer.Add(binding_st, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=8)

            # Cambiar button
            cambiar_btn = wx.Button(
                scroll, label="&Cambiar", name="keymap_capture_button",
            )
            self._apply_hint(cambiar_btn, "keymap_capture_button")
            cambiar_btn.Bind(
                wx.EVT_BUTTON,
                lambda e, aid=action_id: self._on_cambiar(aid),
            )
            row_sizer.Add(cambiar_btn, flag=wx.RIGHT, border=4)

            # Restablecer button
            restablecer_btn = wx.Button(
                scroll, label="&Restablecer", name="keymap_reset_button",
            )
            self._apply_hint(restablecer_btn, "keymap_reset_button")
            restablecer_btn.Bind(
                wx.EVT_BUTTON,
                lambda e, aid=action_id: self._on_restablecer(aid),
            )
            row_sizer.Add(restablecer_btn)

            scroll_sizer.Add(row_sizer, flag=wx.ALL, border=4)

            self._keymap_rows[action_id] = {
                "label": label_st,
                "binding": binding_st,
                "cambiar": cambiar_btn,
                "restablecer": restablecer_btn,
            }

        scroll.SetSizer(scroll_sizer)

        # Configure scroll rate and auto-scroll
        scroll.SetScrollRate(0, 16)
        scroll_sizer.Fit(scroll)

        outer_sizer.Add(scroll, proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)

        panel.SetSizer(outer_sizer)
        notebook.AddPage(panel, "A&tajos")

    def _build_audio_page(self, notebook: wx.Notebook) -> None:
        """Build Audio tab: voice, rate, auto-speak, notifications, sounds.

        Four groups, no grid sizers per AGENTS.md.
        """
        panel = wx.Panel(notebook, name="audio_page")
        sizer = wx.BoxSizer(wx.VERTICAL)

        # ── "Voz del sistema" group ────────────────────────────────────
        sizer.Add(
            wx.StaticText(panel, label="&Voz del sistema:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )

        sizer.Add(
            wx.StaticText(panel, label="&Seleccionar voz:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.pref_system_voice_choice = wx.Choice(
            panel, choices=[], name="pref_system_voice_choice",
        )
        self._apply_hint(self.pref_system_voice_choice, "pref_system_voice_choice")
        sizer.Add(
            self.pref_system_voice_choice,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8,
        )

        voice_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.pref_test_voice_button = wx.Button(
            panel, label="&Probar", name="pref_test_voice_button",
        )
        self._apply_hint(self.pref_test_voice_button, "pref_test_voice_button")
        self.pref_test_voice_button.Bind(
            wx.EVT_BUTTON, self._on_test_voice,
        )
        voice_btn_sizer.Add(
            self.pref_test_voice_button, flag=wx.RIGHT, border=4,
        )

        self.pref_select_voice_button = wx.Button(
            panel, label="&Seleccionar voz...",
            name="pref_select_voice_button",
        )
        self._apply_hint(self.pref_select_voice_button, "pref_select_voice_button")
        self.pref_select_voice_button.Bind(
            wx.EVT_BUTTON, self._on_select_voice,
        )
        voice_btn_sizer.Add(self.pref_select_voice_button)

        sizer.Add(voice_btn_sizer, flag=wx.LEFT | wx.TOP, border=8)

        sizer.Add(
            wx.StaticText(panel, label="V&elocidad:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        rate_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.pref_rate_slider = wx.Slider(
            panel, minValue=-10, maxValue=10,
            value=self._config.system_voice_rate,
            name="pref_rate_slider", style=wx.SL_HORIZONTAL,
        )
        self._apply_hint(self.pref_rate_slider, "pref_rate_slider")
        self.pref_rate_label = wx.StaticText(
            panel,
            label=str(self._config.system_voice_rate),
            name="pref_rate_label",
        )
        rate_sizer.Add(self.pref_rate_slider, proportion=1, flag=wx.EXPAND)
        rate_sizer.Add(self.pref_rate_label, flag=wx.LEFT, border=4)
        sizer.Add(rate_sizer, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)
        self.pref_rate_slider.Bind(wx.EVT_SLIDER, self._on_voice_rate_change)

        # ── "Lectura automática" group ─────────────────────────────────
        sizer.Add(
            wx.StaticText(panel, label="&Lectura automática:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.pref_auto_speak_checkbox = wx.CheckBox(
            panel,
            label="Leer res&puestas automáticamente con la voz del sistema",
            name="pref_auto_speak_checkbox",
        )
        self._apply_hint(self.pref_auto_speak_checkbox, "pref_auto_speak_checkbox")
        self.pref_auto_speak_checkbox.SetValue(
            self._config.auto_speak_responses,
        )
        sizer.Add(
            self.pref_auto_speak_checkbox,
            flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8,
        )

        # ── "Notificaciones" group ─────────────────────────────────────
        sizer.Add(
            wx.StaticText(panel, label="&Notificaciones:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.pref_notifications_checkbox = wx.CheckBox(
            panel, label="Notificaciones &del sistema",
            name="pref_notifications_checkbox",
        )
        self._apply_hint(self.pref_notifications_checkbox, "pref_notifications_checkbox")
        self.pref_notifications_checkbox.SetValue(
            self._config.notifications_enabled,
        )
        sizer.Add(
            self.pref_notifications_checkbox,
            flag=wx.LEFT | wx.RIGHT, border=8,
        )

        self.pref_sounds_checkbox = wx.CheckBox(
            panel, label="S&onidos",
            name="pref_sounds_checkbox",
        )
        self._apply_hint(self.pref_sounds_checkbox, "pref_sounds_checkbox")
        self.pref_sounds_checkbox.SetValue(self._config.sounds_enabled)
        sizer.Add(
            self.pref_sounds_checkbox,
            flag=wx.LEFT | wx.RIGHT, border=8,
        )

        sizer.Add(
            wx.StaticText(panel, label="&Tema de sonido:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.pref_sound_theme_choice = wx.Choice(
            panel, choices=["default", "none"],
            name="pref_sound_theme_choice",
        )
        self._apply_hint(self.pref_sound_theme_choice, "pref_sound_theme_choice")
        self.pref_sound_theme_choice.SetStringSelection(
            self._config.sound_theme,
        )
        sizer.Add(
            self.pref_sound_theme_choice,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8,
        )

        sizer.AddStretchSpacer()
        panel.SetSizer(sizer)
        notebook.AddPage(panel, "A&udio")

    def _build_status_page(self, notebook: wx.Notebook) -> None:
        """Build Estado (F2) tab: one CheckBox per status toggle.

        Each toggle has a preceding ``wx.StaticText`` label with a mnemonic
        ``&`` per AGENTS.md accessibility rules. CheckBox name pattern:
        ``pref_status_toggle_<toggle_name>``.
        """
        panel = wx.Panel(notebook, name="status_page")
        outer_sizer = wx.BoxSizer(wx.VERTICAL)

        outer_sizer.Add(
            wx.StaticText(
                panel, label="&Componentes del estado de sesión (F2):"
            ),
            flag=wx.LEFT | wx.TOP | wx.BOTTOM, border=8,
        )

        # Labels in Spanish, same order as DEFAULT_STATUS_TOGGLES
        toggle_labels: dict[str, str] = {
            "model_name": "&Modelo",
            "context_pct": "&Porcentaje de contexto",
            "max_tokens": "&Máx tokens/respuesta",
            "server": "&Servidor",
            "vram": "&VRAM libre",
            "fit": "&Encaje",
            "message_count": "&Mensajes",
            "temperature": "&Temperatura",
            "top_p": "&Top-p",
            "tok_per_s": "&Tok/s última",
            "is_generating": "&Generando",
        }

        self._status_checkboxes: dict[str, wx.CheckBox] = {}

        for toggle_name in DEFAULT_STATUS_TOGGLES:
            row_sizer = wx.BoxSizer(wx.HORIZONTAL)

            label_text = toggle_labels.get(toggle_name, toggle_name)
            lbl = wx.StaticText(
                panel, label=label_text,
                name=f"lbl_{toggle_name}",
            )
            row_sizer.Add(lbl, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=8)

            chk = wx.CheckBox(
                panel, name=f"chk_{toggle_name}",
            )
            self._apply_hint(chk, f"chk_{toggle_name}")
            chk.SetValue(self._config.status_toggles.get(toggle_name, True))
            chk.Bind(
                wx.EVT_CHECKBOX,
                lambda evt, t=toggle_name: self._on_status_toggle(t, evt),
            )
            row_sizer.Add(chk, flag=wx.ALIGN_CENTER_VERTICAL)

            outer_sizer.Add(
                row_sizer, flag=wx.LEFT | wx.RIGHT | wx.TOP, border=8,
            )

            self._status_checkboxes[toggle_name] = chk

        outer_sizer.AddStretchSpacer()
        panel.SetSizer(outer_sizer)
        notebook.AddPage(panel, "&Estado (F2)")

    # ── Atajos tab event handlers ──────────────────────────────────────────

    def _on_cambiar(self, action_id: str) -> None:
        """Open capture dialog for ``action_id`` and apply the captured combo."""
        dlg = _CaptureDialog(self, self._keymap, action_id, self._speech)
        result = dlg.ShowModal()
        if result == wx.ID_OK:
            mod, kc = dlg.get_captured_combo()
            # Update in-memory config override
            self._config.keymap_overrides[action_id] = (mod, kc)
            # Rebuild keymap and update row display
            self._rebuild_keymap_row(action_id)
        dlg.Destroy()

    def _on_restablecer(self, action_id: str) -> None:
        """Remove the override for ``action_id``, reverting to default."""
        self._config.keymap_overrides.pop(action_id, None)
        self._rebuild_keymap_row(action_id)

    def _rebuild_keymap_row(self, action_id: str) -> None:
        """Rebuild the resolved keymap and update the row for ``action_id``."""
        self._keymap = Keymap(DEFAULT_KEYMAP,
                              overrides=self._config.keymap_overrides)
        row = self._keymap_rows.get(action_id)
        if row is None:
            return
        resolved = self._keymap.actions.get(action_id)
        binding_text = (
            _format_combo(resolved.modifiers, resolved.keycode)
            if resolved else ""
        )
        row["binding"].SetLabel(binding_text)

    # ── Audio tab event handlers ──────────────────────────────────────────────

    def _on_test_voice(self, event: wx.CommandEvent) -> None:
        """Play a test phrase with the currently selected voice/rate."""
        from bellbird.core.system_voice import SystemVoice

        voice_name = self.pref_system_voice_choice.GetStringSelection()
        rate = self.pref_rate_slider.GetValue()
        sv = SystemVoice(voice_name=voice_name, rate=rate)
        sv.speak("Esta es una prueba de la voz del sistema")

    def _on_select_voice(self, event: wx.CommandEvent) -> None:
        """Open the VoiceDialog to select voice and rate."""
        from bellbird.ui.voice_dialog import VoiceDialog
        from bellbird.core.system_voice import SystemVoice

        voices = SystemVoice.voices()
        current_voice = self.pref_system_voice_choice.GetStringSelection()
        current_rate = self.pref_rate_slider.GetValue()
        dlg = VoiceDialog(
            self, voices,
            current_voice=current_voice,
            current_rate=current_rate,
        )
        if dlg.ShowModal() == wx.ID_OK:
            selected_voice = dlg.get_voice()
            selected_rate = dlg.get_rate()
            if selected_voice in voices:
                self.pref_system_voice_choice.SetStringSelection(
                    selected_voice,
                )
            self.pref_rate_slider.SetValue(selected_rate)
            self.pref_rate_label.SetLabel(str(selected_rate))
        dlg.Destroy()

    def _on_voice_rate_change(self, event: wx.CommandEvent) -> None:
        """Update the rate label as the voice-rate slider moves."""
        self.pref_rate_label.SetLabel(str(self.pref_rate_slider.GetValue()))

    # ── Advanced tab helpers ───────────────────────────────────────────────────

    def _refresh_fit_help(self) -> None:
        """Re-evaluate the fit heuristic and update the help StaticText.

        Uses cached VRAM (probed once at dialog construction) to avoid
        ``nvidia-smi`` overhead on every spin click. Reads the model
        metadata if available; falls back to a sentinel when no model is
        loaded.
        """
        ctx_size = self.pref_ctx_size_spin.GetValue()
        vram_free = self._vram_cache[0]

        model_path = self._config.last_model
        meta: GGUFMetadata | None = None
        if model_path:
            meta = read_gguf_metadata(model_path)
        if meta is None:
            size_bytes = estimate_size_bytes(model_path) if model_path else None
            meta = GGUFMetadata(
                block_count=0, context_length=0, file_type="unknown",
                size_bytes=size_bytes or 0,
            )

        report = estimate_fit(meta, ctx_size, vram_free)
        self.pref_fit_help.SetLabel(report.reason_es)

    def _on_advanced_spin_change(self, event: wx.CommandEvent) -> None:
        """Handle spin changes on ctx_size or n_gpu_layers: refresh fit help."""
        event.Skip()  # let the spin control process the value change
        self._refresh_fit_help()

    # ── Status tab event handlers ─────────────────────────────────────────────

    def _on_status_toggle(self, toggle_name: str, event: wx.CommandEvent) -> None:
        """Update the in-memory config when a status toggle checkbox changes."""
        self._config.status_toggles[toggle_name] = event.IsChecked()

    # ── Event Handlers ─────────────────────────────────────────────────────

    def _on_add_folder(self, event: wx.CommandEvent) -> None:
        """Open DirDialog to add a model folder path."""
        dlg = wx.DirDialog(
            self, message="Seleccione una carpeta de modelos",
        )
        if dlg.ShowModal() == wx.ID_OK:
            self.extra_folders_list.Append(dlg.GetPath())
        dlg.Destroy()

    def _on_remove_folder(self, event: wx.CommandEvent) -> None:
        """Remove the selected folder from the extra_folders_list."""
        sel = self.extra_folders_list.GetSelection()
        if sel != wx.NOT_FOUND:
            self.extra_folders_list.Delete(sel)

    def _on_slider_change(self, event: wx.CommandEvent) -> None:
        """Handle slider value change: update label and speak."""
        slider = event.GetEventObject()
        label = None
        fmt_value = ""

        if slider == self.pref_temp_slider:
            label = self.pref_temp_label
            fmt_value = f"{slider.GetValue() / 100.0:.2f}"
        elif slider == self.pref_min_p_slider:
            label = self.pref_min_p_label
            fmt_value = f"{slider.GetValue() / 100.0:.2f}"
        elif slider == self.pref_top_p_slider:
            label = self.pref_top_p_label
            fmt_value = f"{slider.GetValue() / 100.0:.2f}"
        elif slider == self.pref_repeat_slider:
            label = self.pref_repeat_label
            fmt_value = f"{slider.GetValue() / 100.0:.2f}"

        if label is not None:
            label.SetLabel(fmt_value)
            if self._speech is not None:
                self._speech.speak(fmt_value, interrupt=False)

    def _on_ok(self, event: wx.CommandEvent) -> None:
        """Apply config changes and close with wx.ID_OK."""
        self._apply_config()
        self.EndModal(wx.ID_OK)

    def _apply_config(self) -> None:
        """Read all user-editable controls into self._config.

        BellbirdConfig.last_model is intentionally NOT exposed here —
        it is set by the model-load flow (MainWindow._on_start_server_done).
        """
        self._config.system_prompt = self.pref_system_prompt.GetValue()
        # Editing the system prompt directly detaches any active persona
        # so persona_activa doesn't point to a mismatched prompt.
        self._config.persona_activa = None
        self._config.temperature = self.pref_temp_slider.GetValue() / 100.0
        self._config.max_tokens = self.pref_max_tokens_spin.GetValue()
        self._config.min_p = self.pref_min_p_slider.GetValue() / 100.0
        self._config.top_p = self.pref_top_p_slider.GetValue() / 100.0
        self._config.top_k = self.pref_top_k_spin.GetValue()
        self._config.repeat_penalty = (
            self.pref_repeat_slider.GetValue() / 100.0
        )
        self._config.seed = self.pref_seed_spin.GetValue()
        self._config.stop = _parse_stop_text(self.pref_stop_text.GetValue())
        self._config.extra_model_folders = list(
            self.extra_folders_list.GetItems()
        )
        self._config.confirm_new_conversation = (
            self.pref_confirm_new_conv.GetValue()
        )
        self._config.tools_enabled = self.pref_tools_checkbox.GetValue()
        self._config.file_tools_enabled = self.pref_file_tools_checkbox.GetValue()
        self._config.ctx_size = self.pref_ctx_size_spin.GetValue()
        self._config.n_gpu_layers = self.pref_gpu_layers_spin.GetValue()
        self._config.port = self.pref_port_spin.GetValue()

        # v0.10.0: audio output
        self._config.system_voice_name = (
            self.pref_system_voice_choice.GetStringSelection()
        )
        self._config.system_voice_rate = self.pref_rate_slider.GetValue()
        self._config.auto_speak_responses = (
            self.pref_auto_speak_checkbox.GetValue()
        )
        self._config.notifications_enabled = (
            self.pref_notifications_checkbox.GetValue()
        )
        self._config.sounds_enabled = self.pref_sounds_checkbox.GetValue()
        self._config.sound_theme = (
            self.pref_sound_theme_choice.GetStringSelection()
        )

        # v0.11.0: TTS reading filters (Lectura tab)
        self._config.filter_strip_markdown = (
            self.pref_filter_markdown.GetValue()
        )
        self._config.filter_strip_urls = (
            self.pref_filter_urls.GetValue()
        )
        self._config.filter_strip_emojis = (
            self.pref_filter_emojis.GetValue()
        )
        self._config.filter_strip_code_blocks = (
            self.pref_filter_code_blocks.GetValue()
        )

        # Save per-model tunings (T-WU2-07)
        model_path = self._config.last_model
        if model_path:
            basename = Path(model_path).name
            self._config.model_tunings[basename] = {
                "ctx_size": self._config.ctx_size,
                "n_gpu_layers": self._config.n_gpu_layers,
                "threads": None,
            }

    def _apply_hint(self, control: wx.Window, hint_key: str) -> None:
        """Set both SetToolTip and SetHelpText from HINTS[hint_key].
        Never raises (try/except if key missing)."""
        try:
            text = HINTS[hint_key]
            control.SetToolTip(text)
            control.SetHelpText(text)
        except Exception:
            pass

    # ── Preset handlers ──────────────────────────────────────────────────────

    def _on_apply_preset(self, event: wx.CommandEvent) -> None:
        """Read the listbox selection, look up the preset, apply to controls."""
        sel = self.pref_presets_list.GetSelection()
        if sel == wx.NOT_FOUND:
            return
        name = self.pref_presets_list.GetString(sel)
        for preset in self._config.param_presets:
            if preset.name == name:
                self._apply_preset_to_controls(preset)
                if self._speech is not None:
                    self._speech.speak(f"Aplicado {name}", interrupt=False)
                return

    def _on_save_preset(self, event: wx.CommandEvent) -> None:
        """Open wx.TextEntryDialog, validate name, append to param_presets."""
        dlg = wx.TextEntryDialog(
            self, "Nombre del preset:", "Guardar preset",
        )
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        name = dlg.GetValue().strip()
        dlg.Destroy()
        if not name:
            if self._speech is not None:
                self._speech.speak("Nombre vacío", interrupt=False)
            return
        # Check for duplicate
        for p in self._config.param_presets:
            if p.name == name:
                if self._speech is not None:
                    self._speech.speak("Ya existe", interrupt=False)
                return
        new_preset = build_preset_from_config(name, self._config)
        self._config.param_presets.append(new_preset)
        self.pref_presets_list.Append(name)
        if self._speech is not None:
            self._speech.speak("Guardado", interrupt=False)

    def _on_delete_preset(self, event: wx.CommandEvent) -> None:
        """Remove the selected preset from param_presets and the listbox."""
        sel = self.pref_presets_list.GetSelection()
        if sel == wx.NOT_FOUND:
            return
        name = self.pref_presets_list.GetString(sel)
        self._config.param_presets = [
            p for p in self._config.param_presets if p.name != name
        ]
        self.pref_presets_list.Delete(sel)
        if self._speech is not None:
            self._speech.speak("Borrado", interrupt=False)

    def _apply_preset_to_controls(self, preset: ParamPreset) -> None:
        """Write preset sampler values to the 7 slider/spin widgets."""
        self.pref_temp_slider.SetValue(int(preset.temperature * 100))
        self.pref_temp_label.SetLabel(f"{preset.temperature:.2f}")
        self.pref_min_p_slider.SetValue(int(preset.min_p * 100))
        self.pref_min_p_label.SetLabel(f"{preset.min_p:.2f}")
        self.pref_max_tokens_spin.SetValue(preset.max_tokens)
        self.pref_top_p_slider.SetValue(int(preset.top_p * 100))
        self.pref_top_p_label.SetLabel(f"{preset.top_p:.2f}")
        self.pref_top_k_spin.SetValue(preset.top_k)
        self.pref_repeat_slider.SetValue(int(preset.repeat_penalty * 100))
        self.pref_repeat_label.SetLabel(f"{preset.repeat_penalty:.2f}")
        self.pref_seed_spin.SetValue(preset.seed)

    def get_config(self) -> BellbirdConfig:
        """Return the (possibly edited) config copy.

        Call only after ShowModal() returns wx.ID_OK.
        """
        return self._config

    def _focus_first_control(self) -> None:
        """Focus the first interactive control of the first tab."""
        self.extra_folders_list.SetFocus()
