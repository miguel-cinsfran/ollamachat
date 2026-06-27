"""Status formatter — wx-free, pure, strict TDD.

Provides a single pure function ``format_status`` that turns a
``SessionSnapshot`` and a set of component toggles into a Spanish
status string. Used by the F2 handler, the live context meter in the
status bar, and any future notification layer.

The module NEVER imports ``wx``, ``speech``, or ``logging``. It is
deterministic — given identical inputs, it returns byte-identical
output.
"""

from dataclasses import dataclass
from typing import Literal


# ─── Session snapshot ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SessionSnapshot:
    """Immutable snapshot of the current session for formatting.

    Fields whose type includes ``None`` are omitted from the output
    when their value is ``None`` (degradación por componente).

    Attributes:
        model_name: Loaded model identifier.
        n_ctx: Context window size from GET /props, or ``None``.
        prompt_tokens: Prompt tokens from the last usage chunk.
        completion_tokens: Completion tokens from the last usage chunk.
        progress_tokens: Mid-generation progress tokens (overrides
            ``completion_tokens`` for percentage when generating).
        last_tok_per_s: Tokens/second from the last timings chunk.
        server_state: ``"ready"``, ``"loading"``, ``"dead"``, or ``"stopped"``.
        vram_free_mb: Free VRAM from ``read_vram()``, or ``None``.
        vram_total_mb: Total VRAM from ``read_vram()``, or ``None``.
        fit_status: ``"fits"``, ``"spills"``, or ``"unknown"``, or ``None``.
        message_count: Number of messages in the conversation.
        temperature: Sampling temperature.
        top_p: Nucleus sampling parameter.
        max_tokens: Maximum output tokens per response.
        is_generating: ``True`` while a stream is active.
        persona: Name of the active persona (custom system prompt), or
            ``""``. Optional/defaulted so existing positional construction
            keeps working.
    """

    model_name: str
    n_ctx: int | None
    prompt_tokens: int | None
    completion_tokens: int | None
    progress_tokens: int | None
    last_tok_per_s: float | None
    server_state: Literal["ready", "loading", "dead", "stopped"]
    vram_free_mb: int | None
    vram_total_mb: int | None
    fit_status: Literal["fits", "spills", "unknown"] | None
    message_count: int
    temperature: float
    top_p: float
    max_tokens: int
    is_generating: bool
    persona: str = ""
    vision_capable: bool = False


# ─── Default status toggles ───────────────────────────────────────────────────


# Canonical order: identity → capacity → environment → metrics → knobs.
DEFAULT_STATUS_TOGGLES: tuple[str, ...] = (
    "model_name",
    "persona",
    "vision",
    "context_pct",
    "max_tokens",
    "server",
    "vram",
    "fit",
    "message_count",
    "temperature",
    "top_p",
    "tok_per_s",
    "is_generating",
)


# ─── Formatting helpers ───────────────────────────────────────────────────────


def _fmt_temp(t: float) -> str:
    """Format temperature with Spanish locale (comma separator)."""
    return f"{t:.2f}".replace(".", ",")


def _fmt_top_p(p: float) -> str:
    return f"{p:.2f}".replace(".", ",")


def _fmt_pct(num: int, den: int) -> str:
    """Format a percentage, rounded."""
    if den <= 0:
        return "0"
    return str(round(100 * num / den))


# ─── Main formatter ───────────────────────────────────────────────────────────


def format_status(
    snapshot: SessionSnapshot,
    toggles: set[str],
    mode: Literal["short", "long"] = "short",
) -> str:
    """Build a Spanish status string from a snapshot and component toggles.

    Pure function — no I/O, no mutable global state, no ``wx``, no
    ``speech``, no ``logging``, no ``time`` calls. Deterministic:
    identical inputs produce byte-identical output.

    Args:
        snapshot: Current session state.
        toggles: Set of component names to include. Unknown names are
            silently ignored. When a toggle's underlying data is ``None``
            (e.g. ``vram_free_mb is None``), the component is omitted.
        mode: ``"short"`` — single Spanish sentence with ``"; "`` separators.
            ``"long"`` — multi-line breakdown with ``"\\n"`` separators.

    Returns:
        The formatted string, or ``""`` when no component produces output.
    """
    components: list[str] = []

    for name in DEFAULT_STATUS_TOGGLES:
        if name not in toggles:
            continue

        text = _render_component(name, snapshot, mode)
        if text:
            components.append(text)

    if mode == "short":
        if not components:
            return ""
        return " ".join(components) if _any_generando(components) else "; ".join(components) + "."
    else:
        return "\n".join(components)


def _any_generando(components: list[str]) -> bool:
    """Check if the first component starts with 'Generando:'.

    When true, the components are concatenated with spaces instead of
    ``"; "`` separators, because the first one already ends with ':'.
    """
    return bool(components and components[0].startswith("Generando:"))


def _render_component(
    name: str,
    snap: SessionSnapshot,
    mode: Literal["short", "long"],
) -> str:
    """Render a single component to a string, or ``""`` if data is missing."""
    if name == "model_name":
        return snap.model_name  # may be empty string

    elif name == "persona":
        if not snap.persona:
            return ""
        return f"Persona: {snap.persona}"

    elif name == "vision":
        if not snap.vision_capable:
            return ""
        return "Visión activa"

    elif name == "context_pct":
        return _render_context_pct(snap, mode)

    elif name == "max_tokens":
        return f"Máx {snap.max_tokens} tok" if mode == "short" else f"Máx tokens: {snap.max_tokens}"

    elif name == "server":
        state_map = {
            "ready": "Listo",
            "loading": "Cargando",
            "dead": "Caído",
            "stopped": "Detenido",
        }
        label = state_map.get(snap.server_state, snap.server_state)
        return f"Servidor {label}" if mode == "short" else f"Servidor: {label}"

    elif name == "vram":
        if snap.vram_free_mb is None or snap.vram_total_mb is None:
            return ""
        free_gb = snap.vram_free_mb / 1024
        total_gb = snap.vram_total_mb / 1024
        return (
            f"VRAM {free_gb:.1f}/{total_gb:.1f} GB"
            if mode == "short"
            else f"VRAM: {free_gb:.1f}/{total_gb:.1f} GB"
        )

    elif name == "fit":
        if snap.fit_status is None:
            return ""
        status_map = {"fits": "Cabe", "spills": "Desborda", "unknown": "?"}
        label = status_map.get(snap.fit_status, "?")
        return f"Encaje {label}" if mode == "short" else f"Encaje: {label}"

    elif name == "message_count":
        return f"{snap.message_count} msgs" if mode == "short" else f"Mensajes: {snap.message_count}"

    elif name == "temperature":
        return f"Temperatura {_fmt_temp(snap.temperature)}" if mode == "short" else f"Temperatura: {_fmt_temp(snap.temperature)}"

    elif name == "top_p":
        return f"Top P {_fmt_top_p(snap.top_p)}" if mode == "short" else f"Top P: {_fmt_top_p(snap.top_p)}"

    elif name == "tok_per_s":
        if snap.last_tok_per_s is None:
            return ""
        rate = round(snap.last_tok_per_s)
        return f"{rate} tok/s" if mode == "short" else f"Velocidad: {rate} tok/s"

    elif name == "is_generating":
        if not snap.is_generating:
            return ""
        return "Generando" if mode == "short" else "Generando: sí"

    return ""


def _render_context_pct(snap: SessionSnapshot, mode: Literal["short", "long"]) -> str:
    """Render context usage percentage or token count."""
    if snap.n_ctx is None:
        return ""

    # Mid-generation: use progress_tokens
    if snap.is_generating and snap.progress_tokens is not None:
        tokens = snap.progress_tokens
    elif snap.completion_tokens is not None:
        tokens = snap.completion_tokens + (snap.prompt_tokens or 0)
    else:
        return ""

    pct = _fmt_pct(tokens, snap.n_ctx)

    if snap.is_generating:
        return f"Generando: {tokens}/{snap.n_ctx} ({pct} %)"
    else:
        return f"Contexto {tokens}/{snap.n_ctx} ({pct} %)" if mode == "short" else f"Contexto: {tokens}/{snap.n_ctx} ({pct} %)"
