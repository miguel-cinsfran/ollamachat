"""wx-free startup probe and stderr parser for llama-server.

Provides:
- ``parse_stderr_line(line)`` — classify a stderr line from llama-server.
- ``probe(client, runner)`` — combine health checks in one wx-free call.

This module intentionally imports nothing from ``wx`` so it can be
unit-tested in environments (e.g. WSL) that do not have wxPython.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


StderrVerdict = Literal["OK", "FAIL", "NEUTRAL"]


@dataclass(frozen=True)
class ProbeResult:
    """Result of the startup health probe.

    Attributes:
        server_path: Absolute path to llama-server binary, or None.
        is_running: True if the server responds to GET /health.
        loaded_model: Model id string from GET /v1/models, or None.
        error: Human-readable error message, or None on success.
    """

    server_path: Path | None = None
    is_running: bool = False
    loaded_model: str | None = None
    error: str | None = None


# Known failure tokens: (compiled_regex, human_readable_reason).
# The regex is searched (case-insensitive) against the stripped line.
_FAIL_TOKENS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"error loading model", re.IGNORECASE), "Error al cargar el modelo"),
    (re.compile(r"failed to load", re.IGNORECASE), "Error al cargar el modelo"),
    (re.compile(r"unable to load model", re.IGNORECASE), "Error al cargar el modelo"),
    (re.compile(r"out of memory", re.IGNORECASE), "Memoria insuficiente"),
    (re.compile(r"unknown (model )?architecture", re.IGNORECASE),
     "Arquitectura no soportada"),
]

# Known success signals (case-insensitive substring match).
_OK_TOKENS: list[re.Pattern] = [
    re.compile(r"model loaded", re.IGNORECASE),
    re.compile(r"listo", re.IGNORECASE),
    re.compile(r"llama server listening", re.IGNORECASE),
]


def parse_stderr_line(line: str) -> tuple[StderrVerdict, str]:
    """Classify a single ``stderr`` line from ``llama-server``.

    Args:
        line: Raw line from ``stderr`` (may include a trailing newline).

    Returns:
        ``(verdict, reason)`` where:
        - ``"FAIL"`` + the matched line (stripped) when a known error is found.
        - ``"OK"`` + ``""`` when a known success signal is found.
        - ``"NEUTRAL"`` + ``""`` for anything else.

    Matching is case-insensitive. Empty lines are always ``NEUTRAL``.
    """
    stripped = line.strip()
    if not stripped:
        return "NEUTRAL", ""

    # Check FAIL tokens first — errors are more important to surface.
    for pattern, _reason in _FAIL_TOKENS:
        if pattern.search(stripped):
            return "FAIL", stripped

    # Check OK tokens.
    for pattern in _OK_TOKENS:
        if pattern.search(stripped):
            return "OK", ""

    return "NEUTRAL", ""


def probe(client, runner) -> ProbeResult:
    """Combine the three startup checks in one wx-free call.

    Args:
        client: An instance of ``LlamaClient`` for health / model queries.
        runner: The ``llama_runner`` module (or a test double) providing
            ``find_llama_server()``.

    Returns:
        A ``ProbeResult``. Never raises: any exception is swallowed and
        stored in the ``error`` field.
    """
    # Step 1: find the binary.
    try:
        server_path = runner.find_llama_server()
    except Exception as e:
        return ProbeResult(error=f"{type(e).__name__}: {e}")

    if server_path is None:
        return ProbeResult(error="llama-server not found")

    # Step 2: health check.
    try:
        is_running = client.check_running()
    except Exception as e:
        return ProbeResult(
            server_path=Path(server_path),
            error=f"{type(e).__name__}: {e}",
        )

    if not is_running:
        return ProbeResult(
            server_path=Path(server_path),
            is_running=False,
        )

    # Step 3: get the loaded model.
    try:
        loaded_model = client.get_loaded_model()
    except Exception as e:
        return ProbeResult(
            server_path=Path(server_path),
            is_running=True,
            error=f"{type(e).__name__}: {e}",
        )

    return ProbeResult(
        server_path=Path(server_path),
        is_running=True,
        loaded_model=loaded_model or None,
    )
