"""PreferencesDialog — preferences dialog with 5-tab notebook.

Reads/writes BellbirdConfig fields via wx.Notebook with 5 tabs:
General, Modelo, Chat, Herramientas, Avanzado. Every control has name=
and a preceding StaticText label. Speech resolution for sliders walks
the parent chain to find the MainWindow._speech attribute (same pattern
as MessageDetailDialog._on_open_browser).
"""

import dataclasses

import wx

from bellbird.core.config import BellbirdConfig


class PreferencesDialog(wx.Dialog):
    """Preferences dialog with 5-tab notebook editing BellbirdConfig.

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

        self._build_ui()
        self.SetSize((520, 480))
        wx.CallAfter(self._focus_first_control)

    def _build_ui(self) -> None:
        """Build the dialog layout: notebook + OK/Cancel footer."""
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        notebook = wx.Notebook(self, name="preferences_notebook")

        self._build_general_page(notebook)
        self._build_model_page(notebook)
        self._build_chat_page(notebook)
        self._build_tools_page(notebook)
        self._build_advanced_page(notebook)

        main_sizer.Add(notebook, proportion=1,
                       flag=wx.EXPAND | wx.ALL, border=8)

        # ── Footer: OK / Cancel ────────────────────────────────────────
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.ok_button = wx.Button(
            self, id=wx.ID_OK, label="Aceptar", name="pref_ok_button",
        )
        self.ok_button.Bind(wx.EVT_BUTTON, self._on_ok)
        btn_sizer.Add(self.ok_button, flag=wx.RIGHT, border=4)

        self.cancel_button = wx.Button(
            self, id=wx.ID_CANCEL, label="Cancelar", name="pref_cancel_button",
        )
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
            wx.StaticText(panel, label="Carpetas de modelos adicionales:"),
            flag=wx.LEFT | wx.TOP | wx.BOTTOM, border=8,
        )

        self.extra_folders_list = wx.ListBox(
            panel, name="extra_folders_list",
            choices=self._config.extra_model_folders,
        )
        sizer.Add(self.extra_folders_list, proportion=1,
                  flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)

        folder_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.add_folder_button = wx.Button(
            panel, label="Agregar carpeta", name="pref_add_folder_button",
        )
        self.add_folder_button.Bind(wx.EVT_BUTTON, self._on_add_folder)
        folder_btn_sizer.Add(self.add_folder_button, flag=wx.RIGHT, border=4)

        self.remove_folder_button = wx.Button(
            panel, label="Quitar seleccionada",
            name="pref_remove_folder_button",
        )
        self.remove_folder_button.Bind(
            wx.EVT_BUTTON, self._on_remove_folder
        )
        folder_btn_sizer.Add(self.remove_folder_button)

        sizer.Add(folder_btn_sizer,
                  flag=wx.LEFT | wx.TOP | wx.BOTTOM, border=8)

        panel.SetSizer(sizer)
        notebook.AddPage(panel, "General")

    def _build_model_page(self, notebook: wx.Notebook) -> None:
        """Build Modelo tab: system prompt + 6 sampling controls."""
        panel = wx.Panel(notebook, name="model_page")
        sizer = wx.BoxSizer(wx.VERTICAL)

        # ── System prompt ──────────────────────────────────────────────
        sizer.Add(
            wx.StaticText(panel, label="Prompt de sistema:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.pref_system_prompt = wx.TextCtrl(
            panel, value=self._config.system_prompt,
            style=wx.TE_MULTILINE, size=(-1, 80), name="pref_system_prompt",
        )
        sizer.Add(self.pref_system_prompt,
                  flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)

        # ── Temperature slider ─────────────────────────────────────────
        sizer.Add(
            wx.StaticText(panel, label="Temperatura:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        temp_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.pref_temp_slider = wx.Slider(
            panel, minValue=0, maxValue=200,
            value=int(self._config.temperature * 100),
            name="pref_temp_slider", style=wx.SL_HORIZONTAL,
        )
        self.pref_temp_label = wx.StaticText(
            panel, label=f"{self._config.temperature:.2f}",
            name="temp_value_label",
        )
        temp_sizer.Add(self.pref_temp_slider, proportion=1, flag=wx.EXPAND)
        temp_sizer.Add(self.pref_temp_label, flag=wx.LEFT, border=4)
        sizer.Add(temp_sizer, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)
        self.pref_temp_slider.Bind(wx.EVT_SLIDER, self._on_slider_change)

        # ── Max tokens ─────────────────────────────────────────────────
        sizer.Add(
            wx.StaticText(panel, label="Máximo de tokens:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.pref_max_tokens_spin = wx.SpinCtrl(
            panel, min=64, max=8192,
            initial=self._config.max_tokens,
            name="pref_max_tokens_spin",
        )
        sizer.Add(self.pref_max_tokens_spin,
                  flag=wx.LEFT | wx.RIGHT, border=8)

        # ── Top-p slider ───────────────────────────────────────────────
        sizer.Add(
            wx.StaticText(panel, label="Top-p:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        top_p_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.pref_top_p_slider = wx.Slider(
            panel, minValue=0, maxValue=100,
            value=int(self._config.top_p * 100),
            name="pref_top_p_slider", style=wx.SL_HORIZONTAL,
        )
        self.pref_top_p_label = wx.StaticText(
            panel, label=f"{self._config.top_p:.2f}",
            name="top_p_value_label",
        )
        top_p_sizer.Add(self.pref_top_p_slider, proportion=1, flag=wx.EXPAND)
        top_p_sizer.Add(self.pref_top_p_label, flag=wx.LEFT, border=4)
        sizer.Add(top_p_sizer, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)
        self.pref_top_p_slider.Bind(wx.EVT_SLIDER, self._on_slider_change)

        # ── Top-k ──────────────────────────────────────────────────────
        sizer.Add(
            wx.StaticText(panel, label="Top-k:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.pref_top_k_spin = wx.SpinCtrl(
            panel, min=1, max=200,
            initial=self._config.top_k,
            name="pref_top_k_spin",
        )
        sizer.Add(self.pref_top_k_spin,
                  flag=wx.LEFT | wx.RIGHT, border=8)

        # ── Repeat penalty slider ──────────────────────────────────────
        sizer.Add(
            wx.StaticText(panel, label="Penalización de repetición:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        rp_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.pref_repeat_slider = wx.Slider(
            panel, minValue=100, maxValue=200,
            value=int(self._config.repeat_penalty * 100),
            name="pref_repeat_slider", style=wx.SL_HORIZONTAL,
        )
        self.pref_repeat_label = wx.StaticText(
            panel, label=f"{self._config.repeat_penalty:.2f}",
            name="repeat_value_label",
        )
        rp_sizer.Add(self.pref_repeat_slider, proportion=1, flag=wx.EXPAND)
        rp_sizer.Add(self.pref_repeat_label, flag=wx.LEFT, border=4)
        sizer.Add(rp_sizer, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)
        self.pref_repeat_slider.Bind(wx.EVT_SLIDER, self._on_slider_change)

        sizer.AddStretchSpacer()
        panel.SetSizer(sizer)
        notebook.AddPage(panel, "Modelo")

    def _build_chat_page(self, notebook: wx.Notebook) -> None:
        """Build Chat tab: confirm_new_conversation checkbox."""
        panel = wx.Panel(notebook, name="chat_page")
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.Add(
            wx.StaticText(panel, label="Comportamiento:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.pref_confirm_new_conv = wx.CheckBox(
            panel, label="Confirmar al iniciar nueva conversación",
            name="pref_confirm_new_conv",
        )
        self.pref_confirm_new_conv.SetValue(
            self._config.confirm_new_conversation
        )
        sizer.Add(self.pref_confirm_new_conv,
                  flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)

        sizer.AddStretchSpacer()
        panel.SetSizer(sizer)
        notebook.AddPage(panel, "Chat")

    def _build_tools_page(self, notebook: wx.Notebook) -> None:
        """Build Herramientas tab: tools_enabled checkbox."""
        panel = wx.Panel(notebook, name="tools_page")
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.Add(
            wx.StaticText(panel, label="PowerShell:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.pref_tools_checkbox = wx.CheckBox(
            panel, label="Permitir herramientas (PowerShell)",
            name="pref_tools_checkbox",
        )
        self.pref_tools_checkbox.SetValue(self._config.tools_enabled)
        sizer.Add(self.pref_tools_checkbox,
                  flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)

        sizer.AddStretchSpacer()
        panel.SetSizer(sizer)
        notebook.AddPage(panel, "Herramientas")

    def _build_advanced_page(self, notebook: wx.Notebook) -> None:
        """Build Avanzado tab: ctx_size, GPU layers, Port spin controls."""
        panel = wx.Panel(notebook, name="advanced_page")
        sizer = wx.BoxSizer(wx.VERTICAL)

        # ── Context size ───────────────────────────────────────────────
        sizer.Add(
            wx.StaticText(panel, label="Tamaño de contexto (tokens):"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.pref_ctx_size_spin = wx.SpinCtrl(
            panel, min=512, max=131072,
            initial=self._config.ctx_size,
            name="pref_ctx_size_spin",
        )
        sizer.Add(self.pref_ctx_size_spin,
                  flag=wx.LEFT | wx.RIGHT, border=8)

        # ── GPU layers ─────────────────────────────────────────────────
        sizer.Add(
            wx.StaticText(panel, label="Capas GPU (0 = CPU, 99 = todas):"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.pref_gpu_layers_spin = wx.SpinCtrl(
            panel, min=0, max=200,
            initial=self._config.n_gpu_layers,
            name="pref_gpu_layers_spin",
        )
        sizer.Add(self.pref_gpu_layers_spin,
                  flag=wx.LEFT | wx.RIGHT, border=8)

        # ── Server port ────────────────────────────────────────────────
        sizer.Add(
            wx.StaticText(panel, label="Puerto del servidor:"),
            flag=wx.LEFT | wx.TOP, border=8,
        )
        self.pref_port_spin = wx.SpinCtrl(
            panel, min=1024, max=65535,
            initial=self._config.port,
            name="pref_port_spin",
        )
        sizer.Add(self.pref_port_spin,
                  flag=wx.LEFT | wx.RIGHT, border=8)

        sizer.AddStretchSpacer()
        panel.SetSizer(sizer)
        notebook.AddPage(panel, "Avanzado")

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
        """Read all 12 user-editable controls into self._config.

        BellbirdConfig.last_model is intentionally NOT exposed here —
        it is set by the model-load flow (MainWindow._on_start_server_done).
        """
        self._config.system_prompt = self.pref_system_prompt.GetValue()
        self._config.temperature = self.pref_temp_slider.GetValue() / 100.0
        self._config.max_tokens = self.pref_max_tokens_spin.GetValue()
        self._config.top_p = self.pref_top_p_slider.GetValue() / 100.0
        self._config.top_k = self.pref_top_k_spin.GetValue()
        self._config.repeat_penalty = (
            self.pref_repeat_slider.GetValue() / 100.0
        )
        self._config.extra_model_folders = list(
            self.extra_folders_list.GetItems()
        )
        self._config.confirm_new_conversation = (
            self.pref_confirm_new_conv.GetValue()
        )
        self._config.tools_enabled = self.pref_tools_checkbox.GetValue()
        self._config.ctx_size = self.pref_ctx_size_spin.GetValue()
        self._config.n_gpu_layers = self.pref_gpu_layers_spin.GetValue()
        self._config.port = self.pref_port_spin.GetValue()

    def get_config(self) -> BellbirdConfig:
        """Return the (possibly edited) config copy.

        Call only after ShowModal() returns wx.ID_OK.
        """
        return self._config

    def _focus_first_control(self) -> None:
        """Focus the first interactive control of the first tab."""
        self.extra_folders_list.SetFocus()
