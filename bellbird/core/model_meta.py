"""Model metadata utilities — wx-free, strict TDD.

Provides auto-detection of multimodal projector (.mmproj) files
sibling to a given model file, plus GGUF header reading and file-size
estimation. The module is intentionally wx-free so it can be unit-tested
in environments without wxPython (e.g. WSL).
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GGUFMetadata:
    """Frozen dataclass holding key metadata from a .gguf file header.

    Fields are ``None`` when the corresponding key is missing from
    the file header or the ``gguf`` package ``ImportError``'d.
    """

    block_count: int | None = None
    context_length: int | None = None
    file_type: str | None = None
    size_bytes: int | None = None


def _mmproj_name_prefix(name: str) -> str:
    """Extract the model-name prefix from an mmproj filename (lowercase).

    E.g. ``"GLM-4.6V-Flash-mmproj-F16.gguf"`` → ``"glm-4.6v-flash-"``.
    Returns ``""`` if "mmproj" does not appear in the name.
    """
    lower = name.lower()
    idx = lower.find("mmproj")
    if idx <= 0:
        return ""
    return lower[:idx].rstrip("-_.")


def find_mmproj_for_model(model_path: Path) -> Path | None:
    """Auto-detect an mmproj sibling file in the same directory as *model_path*.

    Patterns are checked in priority order (first match wins):
    0. Name-prefix match: mmproj whose name starts with the model's base name.
       Handles co-located multi-mmproj directories (e.g. ``~/models/``).
    1. ``mmproj-*.gguf`` — generic prefix, multi-match guard (returns ``None``
       when ambiguous to protect blind users from a wrong projector).
    2. ``*mmproj*.gguf`` — contains "mmproj" anywhere.
    3. ``*.mmproj.gguf`` — lowest priority suffix.

    Args:
        model_path: Path to the model .gguf file.

    Returns:
        Resolved absolute ``Path`` to the detected mmproj file, or
        ``None`` if no unambiguous match is found.
    """
    parent = model_path.resolve().parent if model_path.parent != model_path else None
    if parent is None or not parent.is_dir():
        return None

    model_name = model_path.resolve().name
    model_lower = model_name.lower()

    # Pattern 0: name-prefix match.
    # Find mmproj files whose name-before-"mmproj" is a prefix of the model name.
    # E.g. "GLM-4.6V-Flash-mmproj-F16.gguf" has prefix "glm-4.6v-flash-" which
    # matches model "GLM-4.6V-Flash-Q4_K_M.gguf". Single match wins; multiple
    # matches fall through (ambiguous).
    pattern0 = sorted(
        p for p in parent.glob("*mmproj*.gguf")
        if p.name != model_name and _mmproj_name_prefix(p.name) and model_lower.startswith(_mmproj_name_prefix(p.name))
    )
    if len(pattern0) == 1:
        return pattern0[0].resolve()

    # Pattern 1: mmproj-*.gguf (highest priority, multi-match guard)
    pattern1 = sorted(p for p in parent.glob("mmproj-*.gguf") if p.name != model_name)
    if len(pattern1) == 1:
        return pattern1[0].resolve()
    if len(pattern1) > 1:
        return None  # Refuse to auto-pick — blind users must never get a wrong projector

    # Pattern 2: *mmproj*.gguf (contains "mmproj" anywhere, alphabetical tiebreak)
    pattern2 = sorted(
        p for p in parent.glob("*mmproj*.gguf")
        if p.name != model_name and not p.name.startswith("mmproj-")
    )
    if len(pattern2) >= 1:
        return pattern2[0].resolve()

    # Pattern 3: *.mmproj.gguf (suffix, lowest priority)
    pattern3 = sorted(
        p for p in parent.glob("*.mmproj.gguf")
        if p.name != model_name and "mmproj" not in p.name.replace(".mmproj.gguf", "")
    )
    if len(pattern3) >= 1:
        return pattern3[0].resolve()

    return None


# ─── GGUF metadata (v0.9.0) ──────────────────────────────────────────────────


def read_gguf_metadata(path: str | Path) -> GGUFMetadata | None:
    """Read key metadata from a .gguf file header.

    Uses the ``gguf`` package (GGUFReader) — imported line-locally so the
    module stays import-clean if the dep is missing. Returns ``None`` on
    ``ImportError``, ``FileNotFoundError``, corrupt data, or any other
    failure (never raises).

    Args:
        path: Path to the .gguf file (string or ``Path``).

    Returns:
        A ``GGUFMetadata`` with parsed header fields and file size, or
        ``None`` if the file could not be read.
    """
    try:
        import gguf  # line-local — module stays clean if dep is missing
    except ImportError:
        return None

    try:
        resolved = Path(path).resolve()
        reader = gguf.GGUFReader(str(resolved))

        # Read architecture to access arch-specific keys
        arch_field = reader.fields.get("general.architecture")
        if arch_field is None:
            return GGUFMetadata(size_bytes=_try_getsize(resolved))

        arch = arch_field.contents()
        if isinstance(arch, bytes):
            arch_name = arch.decode("utf-8", errors="replace")
        else:
            arch_name = str(arch)

        # Block count
        block_count: int | None = None
        bc_key = f"{arch_name}.block_count"
        if bc_key in reader.fields:
            block_count = int(reader.fields[bc_key].contents())

        # Context length
        context_length: int | None = None
        cl_key = f"{arch_name}.context_length"
        if cl_key in reader.fields:
            context_length = int(reader.fields[cl_key].contents())

        # File type (map integer to LlamaFileType name if possible)
        file_type: str | None = None
        if "general.file_type" in reader.fields:
            ft_val = int(reader.fields["general.file_type"].contents())
            try:
                file_type = gguf.LlamaFileType(ft_val).name
            except (ValueError, TypeError):
                file_type = f"type_{ft_val}"

        size = _try_getsize(resolved)

        return GGUFMetadata(
            block_count=block_count,
            context_length=context_length,
            file_type=file_type,
            size_bytes=size,
        )
    except Exception:
        return None


def estimate_size_bytes(path: str | Path) -> int | None:
    """Return the file size in bytes, or ``None`` if the path is missing /
    unreadable (never raises).

    Args:
        path: Path to the file (string or ``Path``).

    Returns:
        Size in bytes as an ``int``, or ``None`` on ``OSError``.
    """
    return _try_getsize(path)


def _try_getsize(path: str | Path) -> int | None:
    """Internal helper — ``os.path.getsize`` with ``None`` fallback."""
    try:
        return os.path.getsize(path)
    except OSError:
        return None
