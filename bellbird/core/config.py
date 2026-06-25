"""Configuration persistence — wx-free, strict TDD."""

import json
import shutil
from dataclasses import dataclass, field, asdict
from pathlib import Path

from bellbird.core.paths import user_data_dir

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
        for field_name, (old_val, new_val) in _MIGRATIONS.items():
            if filtered.get(field_name) == old_val:
                filtered[field_name] = new_val
        return BellbirdConfig(**filtered)
    except (json.JSONDecodeError, OSError):
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
