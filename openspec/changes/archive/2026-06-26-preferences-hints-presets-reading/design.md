# Design: Preferences Hints + Parameter Presets + Reading Filters

## 1. Architecture Overview

```
User opens PreferencesDialog
         │
         ▼
  ┌──────────────────────────────────────────────────────┐
  │ PreferencesDialog.__init__                           │
  │  dataclasses.replace(config) → self._config          │
  │  Resolve _speech from parent chain                   │
  │  _build_ui()                                         │
  │    ├─ _build_general_page  ── HINTS[control]         │
  │    ├─ _build_model_page    ── HINTS + preset sub-    │
  │    │                          panel (ListBox+3 btn)  │
  │    ├─ _build_chat_page     ── HINTS                  │
  │    ├─ _build_lectura_page  ── 4 checkbox filters     │
  │    ├─ _build_tools_page    ── HINTS                  │
  │    ├─ _build_advanced_page ── HINTS                  │
  │    ├─ _build_keymap_page   ── HINTS                  │
  │    ├─ _build_audio_page    ── HINTS (incl. sound_    │
  │    │                          theme hint)            │
  │    └─ _build_status_page   ── HINTS                  │
  │  SetSize(720, 600)                                   │
  │  wx.CallAfter(_focus_first_control)                  │
  └──────────────────────┬───────────────────────────────┘
                         │
              ┌──────────┴──────────┐
              │                     │
      "Aplicar preset"       "Guardar como…"
              │                     │
              ▼                     ▼
   apply_preset_to_controls   wx.TextEntryDialog →
   (reads ParamPreset,       validate name →
   sets 7 slider/spins)      append to config.param_presets
                                     │
                              "Borrar"
                                     │
                                     ▼
                          remove from list
                          + remove from config
                          
                          
  ┌──────────────────────────────────────────────────────┐
  │  _apply_config (on OK)                               │
  │    reads 4 filter checkbox values → self._config     │
  │    param_presets already mutated by UI handlers      │
  │  save_config(self._config)  ───  atomic .tmp+replace │
  └──────────────────────────────────────────────────────┘
                          

  At runtime (TTS path, future):
      Speech.speak_with_system_voice(text, sv)
        └─ apply_filters(text, config) ──► filtered text
             (pure function, wx-free, no threading)
```

**Data flow for `apply_filters`**:

```
text ──► strip_markdown ──► strip_urls ──► strip_emojis ──► strip_code_blocks ──► filtered
            │                    │               │                  │
           toggle ON?          toggle ON?      toggle ON?         toggle ON?
         (config.             (config.        (config.           (config.
          filter_strip_        filter_strip_   filter_strip_      filter_strip_
          markdown)            urls)           emojis)            code_blocks)
    OFF = identity       OFF = identity   OFF = identity      OFF = identity
```

---

## 2. Module Contracts

### `core/preset.py` (new, wx-free)

```python
@dataclass(frozen=True)
class ParamPreset:
    name: str
    temperature: float = 0.70
    min_p: float = 0.05
    max_tokens: int = 4096
    top_p: float = 0.90
    top_k: int = 40
    repeat_penalty: float = 1.10
    seed: int = -1          # -1 = random

def build_preset_from_config(name: str, config: BellbirdConfig) -> ParamPreset:
    """Snapshot current sampler values into a named preset."""
    ...
```

- `to_dict()` / `from_dict()`: use `dataclasses.asdict(p)` / `ParamPreset(**data)` — no custom methods needed.
- JSON round-trip: `asdict` → `json.dump` / `json.load` → `ParamPreset(**data)`.
- `frozen=True` — hashable, immutable. **Must test `frozen` with `pytest.raises(AttributeError)` on mutation attempt** (proposal R6).

### `core/text_filters.py` (new, wx-free)

```python
def apply_filters(text: str, config: BellbirdConfig) -> str:
    """Apply enabled filters in fixed order. Pure function, never raises."""
    ...

def _strip_urls(text: str) -> str:
    """Drop http(s):// URLs. Pure regex."""
    ...

def _strip_emojis(text: str) -> str:
    """Drop Unicode emoji ranges. Pure regex."""
    ...

def _strip_code_blocks(text: str) -> str:
    """Drop fenced ```...``` blocks (multiline). Pure regex."""
    ...
```

- Never-crash: wrapped in `try/except` that returns `text` on any error (caller in `speech.py` already follows this).
- Order fixed (R1): `strip_markdown` → `_strip_urls` → `_strip_emojis` → `_strip_code_blocks`.
- Each step checks `config.filter_strip_*` toggle; skip if `False`.
- Testable with no import of `wx`.

### `ui/preferences_dialog.py` — new methods

```python
def _apply_hint(self, control: wx.Window, hint_key: str) -> None:
    """Set both SetToolTip and SetHelpText from HINTS[hint_key].
    Never raises (try/except if key missing)."""
    ...

def _apply_preset_to_controls(self, preset: ParamPreset) -> None:
    """Read preset fields and set 7 slider/spin controls. Instance method, touches widgets."""
    ...

def _save_preset_dialog(self) -> bool:
    """Open wx.TextEntryDialog, validate name, append to self._config.param_presets.
    Returns True if added, False if cancelled/invalid."""
    ...

def _delete_selected_preset(self) -> None:
    """Remove selected preset from self._config.param_presets and from ListBox."""
    ...
```

- `HINTS: dict[str, str]` — module-level, not instance. Keyed by `name=` string.

---

## 3. Config Schema Delta

Inserted in `BellbirdConfig.__init__` after the `# v0.10.0` block, before the methods:

```python
# v0.11.0: param presets + TTS reading filters
param_presets: list[ParamPreset] = field(default_factory=list)
filter_strip_markdown: bool = True
filter_strip_urls: bool = True
filter_strip_emojis: bool = True
filter_strip_code_blocks: bool = True
```

Add `from bellbird.core.preset import ParamPreset` at the top of `config.py`. Load-time forward-compat is automatic via `__dataclass_fields__` filter in `load_config` — new fields with defaults require **zero migration**.

Total after v0.11.0: **39 fields** (34 + 5). Verification: AST test `test_apply_config_reads_new_fields` extended to cover all 5.

---

## 4. HINTS Table (exhaustive skeleton)

Keys are `name=` values of interactive controls. Labels from `name=` of sibling `wx.StaticText` (used for reference, not as key). ~40 entries.

```python
HINTS: dict[str, str] = {
    # ── General ──────────────────────────────────────────────────────
    "Carpetas de modelos adicionales":  # ListBox (uses Spanish name=)
        "Carpetas donde buscar modelos .gguf. Agregue o quite con los botones.",
    "pref_add_folder_button":
        "Agregar una carpeta de modelos al listado.",
    "pref_remove_folder_button":
        "Quitar la carpeta seleccionada del listado.",

    # ── Modelo ───────────────────────────────────────────────────────
    "Prompt de sistema":  # TextCtrl (uses Spanish name=, no "pref_" prefix)
        "Instrucción del sistema. Texto libre que antecede a cada mensaje.",
    "pref_temp_slider":
        "Temperatura del modelo. Rango: 0.00 (determinista) a 2.00 (caótico).",
    "pref_min_p_slider":
        "Corte de probabilidad mínima. Rango: 0.00 a 1.00.",
    "pref_max_tokens_spin":
        "Máximo de tokens por respuesta. Rango: 64 a 8192.",

    # NEW: presets sub-panel
    "pref_presets_list":
        "Lista de ajustes preestablecidos. Seleccione y aplique para cargar valores.",
    "pref_presets_apply":
        "Aplicar el preset seleccionado a los controles de esta pestaña.",
    "pref_presets_save":
        "Guardar los valores actuales como un nuevo preset.",
    "pref_presets_delete":
        "Borrar el preset seleccionado.",

    # ── Chat ─────────────────────────────────────────────────────────
    "pref_confirm_new_conv":
        "Preguntar antes de iniciar una nueva conversación.",

    # ── Lectura (NEW tab) ────────────────────────────────────────────
    "pref_filter_markdown":
        "Quitar formato markdown (negrita, enlaces, listas) al leer en voz alta.",
    "pref_filter_urls":
        "Quitar enlaces http(s) al leer en voz alta.",
    "pref_filter_emojis":
        "Quitar emojis al leer en voz alta.",
    "pref_filter_code_blocks":
        "Quitar bloques de código ```...``` al leer en voz alta.",

    # ── Herramientas ─────────────────────────────────────────────────
    "pref_tools_checkbox":
        "Permitir al modelo ejecutar comandos PowerShell.",

    # ── Avanzado ─────────────────────────────────────────────────────
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

    # ── Atajos ───────────────────────────────────────────────────────
    "keymap_capture_button":
        "Abrir diálogo para capturar una nueva combinación de teclas.",
    "keymap_reset_button":
        "Restaurar la combinación por defecto de esta acción.",

    # ── Audio ────────────────────────────────────────────────────────
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

    # ── Estado (F2) ──────────────────────────────────────────────────
    "chk_model_name":            "Mostrar nombre del modelo en estado.",
    "chk_context_pct":          "Mostrar porcentaje de contexto usado.",
    "chk_max_tokens":           "Mostrar máximo de tokens por respuesta.",
    "chk_server":               "Mostrar estado del servidor.",
    "chk_vram":                 "Mostrar VRAM libre.",
    "chk_fit":                  "Mostrar encaje del modelo en VRAM.",
    "chk_message_count":        "Mostrar cantidad de mensajes.",
    "chk_temperature":          "Mostrar temperatura activa.",
    "chk_top_p":                "Mostrar Top-p activo.",
    "chk_tok_per_s":            "Mostrar tokens por segundo de la última respuesta.",
    "chk_is_generating":        "Mostrar si el modelo está generando.",

    # ── Dialog footer ────────────────────────────────────────────────
    "pref_ok_button":
        "Guardar cambios y cerrar preferencias.",
    "pref_cancel_button":
        "Descartar cambios y cerrar preferencias.",
}
```

Coverage is **bidirectional**: AST test verifies every `name=` in source has a `HINTS` key, and every `HINTS` key appears as `name=` in source.

---

## 5. Preset UI Sub-Panel (Modelo Tab)

Inserted BELOW the existing max_tokens spin, ABOVE `sizer.AddStretchSpacer()`:

```
┌─────────────────────────────────────────────────────┐
│  [StaticText: &Ajustes preestablecidos:]             │
│                                                      │
│  ┌─────────────────────────────────────────────┐    │
│  │  wx.ListBox(name="pref_presets_list")        │    │
│  │  [preset 1                                   │    │
│  │   preset 2                                   │    │
│  │   preset 3]                                  │    │
│  └─────────────────────────────────────────────┘    │
│                                                      │
│  [Aplicar (name="pref_presets_apply")]               │
│  [Guardar actual como… (name="pref_presets_save")]   │
│  [Borrar (name="pref_presets_delete")]               │
└─────────────────────────────────────────────────────┘
```

- `StaticText` with `&Ajustes preestablecidos:` — mnemonic collision check: Alt+A is NOT used by any other `&` in Modelo tab.
- `wx.ListBox` — height ~80px, populated from `self._config.param_presets` (`.name` strings).
- Three buttons in horizontal sizer below the list box.
- "Aplicar" calls `_apply_preset_to_controls(preset)`: reads preset fields, calls `SetValue()` on the 7 sampler controls + speaks "Aplicado {name}".
- "Guardar actual como…" opens `wx.TextEntryDialog("Nombre del preset:")`, validates non-empty + no duplicate, then appends `build_preset_from_config(name, self._config)` to `self._config.param_presets`. Duplicate name → speak "Ya existe un preset con ese nombre", no-op.
- "Borrar" removes selected preset from ListBox and `self._config.param_presets`. If nothing selected, no-op.

---

## 6. Lectura Tab Structure

New tab inserted between Chat and Herramientas in `_build_ui()`:

```
┌─────────────────────────────────────────────────────┐
│  [StaticText: "Filtros de lectura                    │
│   (al leer en voz &alta con SAPI):"]                 │
│                                                      │
│  ☑ [CheckBox label="&Quitar markdown al leer"       │
│     name="pref_filter_markdown"]                     │
│                                                      │
│  ☑ [CheckBox label="&Quitar URLs al leer"           │
│     name="pref_filter_urls"]                         │
│                                                      │
│  ☑ [CheckBox label="&Quitar emojis al leer"         │
│     name="pref_filter_emojis"]                       │
│                                                      │
│  ☑ [CheckBox label="&Quitar bloques de código al    │
│     leer" name="pref_filter_code_blocks"]            │
│                                                      │
└─────────────────────────────────────────────────────┘
```

- StaticText label `"Filtros de lectura (al leer en voz &alta con SAPI):"` using `&A` on "alta" — avoids collision with the 4 checkbox `&Q` prefixes.
- Each CheckBox has its own `name=`, all default ON (`True`).
- BoxSizer vertical, no grid. `AddStretchSpacer()` at the bottom.
- Tab label: `"&Lectura"` (Alt+L activates tab).
- `notebook.AddPage` order: `_build_chat_page` → `_build_lectura_page` → `_build_tools_page`.

---

## 7. `&` Mnemonic Audit Table

Every `wx.StaticText` label and `wx.CheckBox` label (the label= argument) needs a `&` prefixing a unique letter **within each tab**. Collisions across tabs are OK since only the active tab's `&` accelerators are active.

| Tab | Control (label) | New label | Mnemonic |
|-----|----------------|-----------|----------|
| **General** | `StaticText("Carpetas de modelos adicionales:")` | `"&Carpetas de modelos adicionales:"` | C |
| | `Button("Agregar carpeta")` | `"&Agregar carpeta"` | A |
| | `Button("Quitar seleccionada")` | `"&Quitar seleccionada"` | Q |
| **Modelo** | `StaticText("Prompt de sistema:")` | `"&Prompt de sistema:"` | P |
| | `StaticText("Temperatura:")` | `"&Temperatura:"` | T |
| | `StaticText("Min-p:")` | `"&Min-p:"` | M |
| | `StaticText("Máximo de tokens:")` | `"Má&ximo de tokens:"` | x |
| | `StaticText("Ajustes preestablecidos:")` | `"&Ajustes preestablecidos:"` | A |
| **Chat** | `StaticText("Comportamiento:")` | `"&Comportamiento:"` | C |
| | `CheckBox("Confirmar al iniciar nueva conversación")` | `"&Confirmar al iniciar nueva conversación"` | C |
| **Lectura** | `CheckBox("Quitar markdown al leer")` | `"&Quitar markdown al leer"` | Q |
| | `CheckBox("Quitar URLs al leer")` | `"&Quitar URLs al leer"` | U |
| | `CheckBox("Quitar emojis al leer")` | `"Q&uitar emojis al leer"` | u |
| | `CheckBox("Quitar bloques de código al leer")` | `"&Quitar bloques de código al leer"` | Q |
| | (Need collision resolution: Lectura has 3 `&Q` + 1 `&U`. Options: `&Q`, `&U`, `&e` (emojis), `&b` (bloques).) | — | — |
| **Herramientas** | `StaticText("PowerShell:")` | `"&PowerShell:"` | P |
| | `CheckBox("Permitir herramientas (PowerShell)")` | `"&Permitir herramientas (PowerShell)"` | P |
| **Avanzado** | `StaticText("Top-p:")` | `"&Top-p:"` | T |
| | `StaticText("Top-k:")` | `"Top-&k:"` | k |
| | `StaticText("Penalización de repetición:")` | `"&Penalización de repetición:"` | P |
| | `StaticText("Semilla:")` | `"&Semilla:"` | S |
| | `StaticText("Cadenas de parada (una por línea):")` | `"&Cadenas de parada (una por línea):"` | C |
| | `StaticText("Tamaño de contexto (tokens):")` | `"&Tamaño de contexto (tokens):"` | T |
| | `StaticText("Capas GPU (0 = CPU, 99 = todas):")` | `"&Capas GPU (0 = CPU, 99 = todas):"` | C |
| | `StaticText("Puerto del servidor:")` | `"&Puerto del servidor:"` | P |
| **Atajos** | `StaticText("Atajos de teclado...:")` | Already has no `&`? Add `"&Atajos de teclado (pulsa Cambiar para reasignar):"` | A |
| | `_ACTION_LABELS` (21 entries) | Prepend `&` to first letter not colliding within tab | varies |
| **Audio** | `StaticText("Voz del sistema:")` | `"&Voz del sistema:"` | V |
| | `StaticText("Voz:")` | `"&Voz:"` | V — **collision** → change first to `"&Voz del sistema:"`, second to `"&Voz:"` (same letter, different binding order — BUT same tab collision is forbidden). Fix: second → `"&Seleccionar voz:"` or drop `&` on the group label |
| | `StaticText("Velocidad:")` | `"&Velocidad:"` | V — **triple collision in Audio!** |
| | `StaticText("Lectura automática:")` | `"&Lectura automática:"` | L |
| | `CheckBox("Leer respuestas automáticamente...")` | `"&Leer respuestas automáticamente..."` | L — **collision** |
| | `StaticText("Notificaciones:")` | `"&Notificaciones:"` | N |
| | `CheckBox("Notificaciones del sistema")` | `"&Notificaciones del sistema"` | N — **collision** |
| | `CheckBox("Sonidos")` | `"&Sonidos"` | S |
| | `StaticText("Tema de sonido:")` | `"&Tema de sonido:"` | T — **collision with "Temperatura" in Modelo?** Not same tab, OK. |
| **Estado** | Already has `&` on all toggle_labels (11 entries) | No change | Already active |
| | Tab labels: `"General"`, `"Modelo"`, `"Chat"`, `"Herramientas"`, `"Avanzado"`, `"Atajos"`, `"Audio"`, `"&Estado (F2)"` | Add `&` to tab labels: `"&General"`, `"&Modelo"`, `"&Chat"`, `"&Herramientas"`, `"&Avanzado"`, `"&Atajos"`, `"&Audio"`, plus `"&Lectura"` (new), keep `"&Estado (F2)"` | G, M, C, H, A, A(Lectura), A(Audio), L, E — **collisions!** Tab mnemonics must be unique within the notebook. Fix: `"&General"` (G), `"&Modelo"` (M), `"C&hat"` (h), `"&Herramientas"` (H), `"&Avanzado"` (A), `"&Atajos"` (t), `"&Audio"` (u), `"&Lectura"` (L), `"&Estado (F2)"` (E). |

**Tab mnemonic resolution**: The notebook tabs share one namespace (Ctrl+Tab cycles, but Alt+letter focuses the tab directly). The resolved set:
- G - General
- M - Modelo  
- h - Chat (C&hat)
- H - Herramientas
- A - Avanzado
- t - Atajos (a&tajos or A&tajos)
- u - Audio (A&udio)
- L - Lectura (&Lectura)
- E - Estado (&Estado (F2))

---

## 8. Dialog Size

Current: `self.SetSize((620, 520))` on line 302.

New: `self.SetSize((720, 600))` — wider and taller to fit:
- 9th tab (Lectura, ~120px)
- Preset sub-panel in Modelo tab (~160px including list + buttons + label)

AST test asserts the size literal `(720, 600)` is present in `__init__`.

---

## 9. Wiring in `_apply_config`

5 new field reads appended after the `# v0.10.0` block (before the model_tunings save):

```python
# v0.11.0: TTS reading filters (Lectura tab)
self._config.filter_strip_markdown = self.pref_filter_markdown.GetValue()
self._config.filter_strip_urls = self.pref_filter_urls.GetValue()
self._config.filter_strip_emojis = self.pref_filter_emojis.GetValue()
self._config.filter_strip_code_blocks = self.pref_filter_code_blocks.GetValue()
```

`param_presets` is **already mutated** by `_save_preset_dialog()` and `_delete_selected_preset()` — no read needed in `_apply_config`. The list reference is shared with the config copy.

---

## 10. TTS Filter Integration (SUGGESTION — NOT applied in this change)

```python
# In bellbird/core/speech.py, inside speak_with_system_voice:
def speak_with_system_voice(self, text, system_voice):
    try:
        from bellbird.core.text_filters import apply_filters
        from bellbird.core.config import load_config
        cfg = load_config()
        filtered = apply_filters(text, cfg)
    except Exception:
        filtered = text
    try:
        system_voice.speak(filtered)
    except Exception:
        pass
```

This is **deferred** — the change can land without it. The verify report will file it as a **suggestion** (not a blocking issue). The `Speech.speak` path (live screen-reader) is **not touched** per AGENTS.md / lesson v0.6.0 (filters would break streaming).

---

## 11. Workload Forecast & WU Split

| Work Unit | Scope | Est. LOC | Key files |
|-----------|-------|----------|-----------|
| **WU-1** (core + tests) | preset.py, text_filters.py, config.py fields, all core tests | ~500 | 4 new files + 3 extended |
| **WU-2** (UI + wx-tests) | preferences_dialog.py changes, static/lectura AST tests, pyproject.toml, run_tests.bat | ~450-500 | 3 files modified, 1 new test, 1 extended test |

WU-1 is fully WSL-runnable (no wx). WU-2 requires Windows for wx-runtime tests but AST tests run in WSL.

**Recommendation**: Serial WU-1 → WU-2. If WU-2 exceeds ~450 LOC, split further (WU-2a: HINTS + `&` mnemonics + size bump; WU-2b: presets UI + Lectura tab).

---

## 12. Risks & Mitigations

| ID | Risk | Impact | Mitigation |
|----|------|--------|------------|
| **R1** | Filter order: strip_markdown FIRST turns `[text](url)` into `text`, so URL regex doesn't catch the URL | Wrong filter output | Order documented in the spec and enforced in code. Unit test proves: input `"[link](https://x.com)"` after markdown strip = `"link"`; after URL strip = `"link"` (URL is gone BEFORE URL filter runs). No regression. |
| **R2** | Emoji regex is locale-sensitive; test with `👋`, `🚀`, `✓` | Missed emojis | Use canonical Unicode ranges: `\U0001F300-\U0001F9FF`, `\U00002600-\U000027BF`, `\U0000FE00-\U0000FE0F` (variation selectors), `\U0000200D` (ZWJ). Test with exact codepoints. |
| **R3** | Code-block regex false-positives on inline backticks | Strips `code` inline | Use multiline fenced pattern only: `` ```[\w]*\n?[\s\S]*?``` `` — same pattern as `strip_markdown`. Inline backticks are NOT affected. |
| **R4** | `&` mnemonic collisions within a tab | Alt+letter focuses wrong control | Audit before apply. Documented collisions in §7 resolved by choosing alternative letters (e.g., `C&hat` for Chat tab, `A&tajos` for Atajos, `A&udio` for Audio). Unique per tab. |
| **R5** | Dialog size 720×600 may not fit small screens | Dialog clipped | This is the planned post-bump size. Test on 1366×768 (smallest common). If clipped, reduce Lectura tab height or use scroll. |
| **R6** | `ParamPreset` JSON round-trip with `frozen=True`+`asdict` | Serialization fails with `field()` types | `asdict()` handles all field types natively (str, int, float, bool). `json.dump` with `indent=2, ensure_ascii=False`. Test: create preset, save, load, assert fields match. |
| **R7** | Lectura filters apply to TTS only (SAPI), not live screen-reader | Blind user expects filters everywhere | Documented per AGENTS.md / lesson v0.6.0. The SAPI path is a separate channel (`speak_with_system_voice`). The live `speak` path must NOT filter (breaks streaming). Explicit `# NOT touched` comment in spec. |
