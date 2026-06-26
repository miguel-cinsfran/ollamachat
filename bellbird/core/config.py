"""Configuration persistence — wx-free, strict TDD."""

import json
import os
import shutil
from dataclasses import dataclass, field, asdict
from pathlib import Path

from bellbird.core.paths import user_data_dir
from bellbird.core.preset import ParamPreset
from bellbird.core.status_formatter import DEFAULT_STATUS_TOGGLES

CONFIG_PATH = user_data_dir() / "config.json"
LEGACY_CONFIG_PATH = Path(__file__).parent.parent / "data" / "config.json"


@dataclass
class BellbirdConfig:
    """User preferences persisted to data/config.json."""

    temperature: float = 0.70
    max_tokens: int = 4096
    top_p: float = 0.90
    top_k: int = 40
    repeat_penalty: float = 1.10
    min_p: float = 0.05
    seed: int = -1
    stop: list[str] = field(default_factory=list)
    system_prompt: str = ""
    last_model: str = ""
    extra_model_folders: list[str] = field(default_factory=list)
    ctx_size: int = 4096
    n_gpu_layers: int = 99
    port: int = 8080
    confirm_new_conversation: bool = True
    tools_enabled: bool = False
    model_mmproj: dict[str, str] = field(default_factory=dict)
    mmproj_offload: bool = True
    request_timeout: int = 120
    max_tool_iterations: int = 5
    keymap_overrides: dict[str, tuple[int, int]] = field(default_factory=dict)
    restore_last_session: bool = True
    last_session_path: str = ""
    recent_files: list[str] = field(default_factory=list)
    url_max_chars: int = 50000

    # v0.9.0: context advisor + toggleable F2
    safe_vram_mode: bool = False
    status_toggles: dict[str, bool] = field(
        default_factory=lambda: {t: True for t in DEFAULT_STATUS_TOGGLES}
    )
    model_tunings: dict[str, dict] = field(default_factory=dict)
    pre_send_warn: bool = True

    # v0.10.0: audio output (TTS + SAPI + notifications + sounds)
    system_voice_name: str = ""
    system_voice_rate: int = 0
    auto_speak_responses: bool = False
    notifications_enabled: bool = True
    sounds_enabled: bool = True
    sound_theme: str = "default"

    # v0.11.0: param presets + TTS reading filters
    param_presets: list[ParamPreset] = field(default_factory=list)
    filter_strip_markdown: bool = True
    filter_strip_urls: bool = True
    filter_strip_emojis: bool = True
    filter_strip_code_blocks: bool = True

    def status_toggles_as_set(self) -> set[str]:
        """Return the set of toggle names whose value is ``True``.

        Returns:
            Active toggle names, or an empty set when ``status_toggles``
            is empty (defensive).
        """
        return {k for k, v in self.status_toggles.items() if v}

    def get_mmproj_for(self, model_path: str | Path) -> str | None:
        """Look up the mmproj path for a model by basename.

        Returns the resolved absolute path if the stored file exists,
        or ``None`` if the key is missing or the file no longer exists.
        """
        key = Path(model_path).name
        val = self.model_mmproj.get(key)
        if val and Path(val).is_file():
            return str(Path(val).resolve())
        return None


_MIGRATIONS: dict[str, object] = {
    # max_tokens was 512 before v0.5.1 reasoning-model support. Any saved
    # config with the old default is silently bumped so reasoning models
    # can finish their thinking phase before producing output.
    "max_tokens": (512, 4096),
}


def migrate_legacy_config() -> None:
    """One-shot, best-effort migration of config from the package data dir
    to the new user-data dir. Idempotent: if the new file already exists,
    this is a no-op. Never raises.
    """
    if not LEGACY_CONFIG_PATH.is_file():
        return
    if CONFIG_PATH.is_file():
        return
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(LEGACY_CONFIG_PATH, CONFIG_PATH)
    except Exception:
        pass


def load_config() -> BellbirdConfig:
    """Load config from CONFIG_PATH. Returns BellbirdConfig() on missing/
    corrupt file. Unknown JSON keys filtered by __dataclass_fields__.
    Applies one-time migrations for fields whose old default is known.
    """
    migrate_legacy_config()
    if not CONFIG_PATH.is_file():
        return BellbirdConfig()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        known = {f.name for f in BellbirdConfig.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        # Normalise keymap_overrides from JSON lists to tuples
        if "keymap_overrides" in filtered:
            raw = filtered["keymap_overrides"]
            if isinstance(raw, dict):
                normalised: dict[str, tuple[int, int]] = {}
                for k, v in raw.items():
                    if isinstance(v, (list, tuple)) and len(v) == 2:
                        a, b = v
                        if isinstance(a, int) and isinstance(b, int):
                            normalised[k] = (a, b)
                        else:
                            raise TypeError(f"Non-int in keymap_overrides[{k!r}]: {v!r}")
                    else:
                        raise TypeError(f"Invalid keymap_overrides[{k!r}]: {v!r}")
                filtered["keymap_overrides"] = normalised
        # Normalise param_presets from JSON list-of-dicts to list of ParamPreset
        if "param_presets" in filtered:
            raw_presets = filtered["param_presets"]
            if isinstance(raw_presets, list):
                filtered["param_presets"] = [
                    ParamPreset.from_dict(item) if isinstance(item, dict) else item
                    for item in raw_presets
                ]
        for field_name, (old_val, new_val) in _MIGRATIONS.items():
            if filtered.get(field_name) == old_val:
                filtered[field_name] = new_val
        return BellbirdConfig(**filtered)
    except (json.JSONDecodeError, OSError, TypeError):
        return BellbirdConfig()


def save_config(config: BellbirdConfig, path: Path | None = None) -> None:
    """Atomic write of config to `path` (or CONFIG_PATH if None).

    Writes `.tmp` first, then `Path.replace` to target. Creates parent dir
    if missing. The `path` parameter exists for testability with `tmp_path`;
    the production call site uses the default (CONFIG_PATH).
    """
    target = path if path is not None else CONFIG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(asdict(config), f, indent=2, ensure_ascii=False)
    tmp.replace(target)


# ─── Recents helpers (v0.8.2) ────────────────────────────────────────────────

_MAX_RECENTS = 10


def update_recents(path: str, recent_files: list[str]) -> list[str]:
    """Add ``path`` to a MRU recent-files list: dedup, front-insert, cap.

    Args:
        path: File path to add (converted to absolute).
        recent_files: Current list of recent file paths.

    Returns:
        New list with ``path`` at the front, deduplicated, capped at
        ``_MAX_RECENTS`` entries.
    """
    abs_path = os.path.abspath(path)
    filtered = [p for p in recent_files if p != abs_path]
    filtered.insert(0, abs_path)
    return filtered[:_MAX_RECENTS]


def remove_from_recents(path: str, recent_files: list[str]) -> list[str]:
    """Remove ``path`` from a recent-files list (no-op if absent).

    Args:
        path: File path to remove.
        recent_files: Current list of recent file paths.

    Returns:
        New list without ``path``.
    """
    abs_path = os.path.abspath(path)
    return [p for p in recent_files if p != abs_path]


def should_auto_restore(config: BellbirdConfig) -> bool:
    """Check whether the app should auto-restore the last session.

    Returns ``True`` when **all** of these hold:
    - ``config.restore_last_session is True``
    - ``config.last_session_path`` is non-empty
    - The file at ``config.last_session_path`` exists on disk.
    """
    if not config.restore_last_session:
        return False
    if not config.last_session_path:
        return False
    return os.path.exists(config.last_session_path)
