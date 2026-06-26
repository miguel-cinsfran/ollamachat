"""Context advisor — wx-free, strict TDD.

Provides VRAM probing (nvidia-smi on Windows), fit heuristics for
model + context size, token counting via POST /tokenize, and a
pre-send check that gates or warns before exceeding n_ctx or VRAM.

All public functions never raise — failures are returned as ``None``
/ ``(None, None)`` / structured verdicts.
"""

import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Literal

import requests

from bellbird.core.model_meta import GGUFMetadata


# ─── VRAM probe ───────────────────────────────────────────────────────────────


def read_vram() -> tuple[int | None, int | None]:
    """Probe VRAM via ``nvidia-smi`` (Windows only).

    Platform-guarded: returns ``(None, None)`` immediately on non-Windows.
    On Windows, runs ``nvidia-smi --query-gpu=memory.total,memory.free
    --format=csv,noheader,nounits`` with a 1-second timeout.

    Returns:
        ``(free_mb, total_mb)`` as ints from the first GPU, or
        ``(None, None)`` on any error (never raises).
    """
    if sys.platform != "win32":
        return (None, None)

    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return (None, None)

    if result.returncode != 0:
        return (None, None)

    try:
        parts = result.stdout.strip().split(", ")
        if len(parts) < 2:
            return (None, None)
        total = int(parts[0].strip())
        free = int(parts[1].strip())
        return (free, total)
    except (ValueError, IndexError):
        return (None, None)


# ─── Fit report ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FitReport:
    """Result of a model-vs-VRAM fit heuristic.

    Attributes:
        status: ``"fits"`` — fits entirely in VRAM; ``"spills"`` — may
            spill to system RAM; ``"unknown"`` — not enough data.
        reason_es: Spanish one-liner explaining the estimate.
        confidence: ``"high"`` when both weights and VRAM are known;
            ``"low"`` when either is unknown.
    """

    status: Literal["fits", "spills", "unknown"]
    reason_es: str
    confidence: Literal["high", "low"]


# Heuristic constants (conservative)
# Weights ≈ size_bytes (converted to MB).
# KV cache ≈ ctx_size / 1024 * 4 MB per 1024 tokens (rough factor for 7B-class models).
_KV_MB_PER_1K = 12  # MB per 1024 tokens of context (conservative, includes overhead)


def estimate_fit(
    model: GGUFMetadata,
    ctx_size: int,
    vram_free_mb: int | None,
) -> FitReport:
    """Estimate whether *model* fits in *vram_free_mb* at *ctx_size*.

    Conservative heuristic: weights ≈ ``size_bytes`` (converted to MB),
    KV ≈ linear in ``ctx_size``. When ``vram_free_mb is None``, the
    report returns ``unknown``. Pure function — no I/O, no time, no
    globals.

    Args:
        model: Parsed GGUF metadata.
        ctx_size: Requested context size in tokens.
        vram_free_mb: Free VRAM in MB, or ``None`` if unknown.

    Returns:
        A ``FitReport`` with the estimate.
    """
    if vram_free_mb is None:
        return FitReport(
            status="unknown",
            reason_es="VRAM desconocida: no se puede estimar el encaje.",
            confidence="low",
        )

    size_mb = model.size_bytes / (1024 * 1024) if model.size_bytes is not None else None

    if size_mb is None:
        return FitReport(
            status="unknown",
            reason_es="Tamaño del modelo desconocido: no se puede estimar el encaje.",
            confidence="low",
        )

    kv_mb = (ctx_size / 1024) * _KV_MB_PER_1K
    total_needed = size_mb + kv_mb

    gb = lambda b: f"{b / 1024:.1f}"

    if total_needed <= vram_free_mb:
        return FitReport(
            status="fits",
            reason_es=(
                f"Modelo {gb(size_mb)} GB; VRAM libre {gb(vram_free_mb)} GB;"
                f" a contexto {ctx_size} cabe en GPU con alta confianza."
            ),
            confidence="high",
        )
    else:
        return FitReport(
            status="spills",
            reason_es=(
                f"Modelo {gb(size_mb)} GB; VRAM libre {gb(vram_free_mb)} GB;"
                f" a contexto {ctx_size} podría desbordar a RAM."
            ),
            confidence="high",
        )


# ─── Token count ──────────────────────────────────────────────────────────────


def token_count(
    text: str,
    base_url: str,
    session: requests.Session,
    timeout: float | None = None,
) -> int | None:
    """Estimate token count by calling ``POST /tokenize``.

    Args:
        text: Text to tokenize.
        base_url: Server base URL (e.g. ``http://localhost:8080``).
        session: ``requests.Session`` for the HTTP call.
        timeout: Optional per-request timeout in seconds.

    Returns:
        Number of tokens (``len(tokens)``), or ``None`` on any error.
    """
    try:
        response = session.post(
            f"{base_url}/tokenize",
            json={"content": text, "add_special": False},
            timeout=timeout,
        )
        if response.status_code != 200:
            return None
        body = response.json()
        tokens = body.get("tokens")
        if tokens is None or not isinstance(tokens, list):
            return None
        return len(tokens)
    except (requests.RequestException, ValueError, TypeError):
        return None


# ─── Pre-send snapshot + verdict ──────────────────────────────────────────────


@dataclass(frozen=True)
class PreSendSnapshot:
    """Snapshot of pre-send state for the guard check.

    Attributes:
        estimated_tokens: Estimated prompt + history tokens.
        n_ctx: Model context window size, or ``None`` if unknown.
        safe_mode: When ``True``, overflow blocks the send.
        warn_once: When ``True``, a one-shot warning was already shown.
        vram_free_mb: Free VRAM in MB, or ``None`` if unknown.
        model_size_bytes: Model file size in bytes, or ``None`` if unknown.
    """

    estimated_tokens: int
    n_ctx: int | None
    safe_mode: bool
    warn_once: bool
    vram_free_mb: int | None = None
    model_size_bytes: int | None = None


@dataclass(frozen=True)
class PreSendVerdict:
    """Verdict from ``pre_send_check``.

    Attributes:
        decision: ``"allow"`` — proceed; ``"warn"`` — warn and proceed;
            ``"block"`` — abort.
        reason_es: Spanish reason string, or ``""`` when ``decision`` is
            ``"allow"``.
    """

    decision: Literal["allow", "warn", "block"]
    reason_es: str | None


def pre_send_check(snapshot: PreSendSnapshot) -> PreSendVerdict:
    """Decide whether the send should be allowed, warned, or blocked.

    Rules:
    - ``n_ctx is None`` → always ``allow`` (defer to server).
    - Over-budget AND ``safe_mode`` → ``block``.
    - Over-budget AND NOT ``safe_mode`` → ``warn``.
    - Under-budget → ``allow``.

    "Over-budget" means ``estimated_tokens > n_ctx`` OR
    (``model_size_bytes`` and ``vram_free_mb`` known and
    ``model_size_bytes > vram_free_mb * 1024 * 1024``).

    Args:
        snapshot: Current pre-send state.

    Returns:
        A ``PreSendVerdict`` with decision and reason.
    """
    estimated = snapshot.estimated_tokens
    n_ctx = snapshot.n_ctx

    # Check context overflow
    ctx_overflow = n_ctx is not None and estimated > n_ctx

    # Check VRAM overflow
    vram_overflow = False
    if (
        snapshot.vram_free_mb is not None
        and snapshot.model_size_bytes is not None
    ):
        vram_overflow = snapshot.model_size_bytes > snapshot.vram_free_mb * 1024 * 1024

    if ctx_overflow or vram_overflow:
        if snapshot.safe_mode:
            return PreSendVerdict(
                decision="block",
                reason_es="Contexto lleno; iniciá nueva conversación.",
            )
        elif snapshot.warn_once:
            # User already acknowledged the risk this conversation — allow silently.
            return PreSendVerdict(decision="allow", reason_es="")
        else:
            return PreSendVerdict(
                decision="warn",
                reason_es=(
                    "Vas a desbordar el contexto;"
                    " continuá bajo tu responsabilidad."
                ),
            )

    return PreSendVerdict(decision="allow", reason_es="")
