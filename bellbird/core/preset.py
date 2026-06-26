"""Parameter presets for Bellbird — wx-free, strict TDD.

Defines ParamPreset, a frozen dataclass capturing the 7 sampler
parameters plus a user-supplied name. Provides build_preset_from_config
to snapshot the current config values into a named preset.

JSON round-trip contract: dataclasses.asdict(preset) → json.dump →
json.load → ParamPreset(**data). This is used by BellbirdConfig's
save_config/load_config pipeline via the __dataclass_fields__ filter.
"""

import dataclasses
from dataclasses import dataclass, fields as dataclass_fields
from typing import Any


@dataclass(frozen=True)
class ParamPreset:
    """A named snapshot of 7 sampler parameters.

    Frozen (immutable, hashable) so it can be stored safely in config
    and round-tripped via JSON. The ``seed`` field uses ``-1`` as the
    "aleatorio" (random) sentinel, matching BellbirdConfig.
    """

    name: str = ""
    temperature: float = 0.70
    min_p: float = 0.05
    max_tokens: int = 4096
    top_p: float = 0.90
    top_k: int = 40
    repeat_penalty: float = 1.10
    seed: int = -1

    def to_dict(self) -> dict[str, object]:
        """Serialize to a plain dict for JSON serialization.

        Returns:
            A dict with all 8 fields. Uses ``dataclasses.asdict``
            internally for correct handling of nested dataclasses
            (none currently, but future-proof).
        """
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ParamPreset":
        """Deserialize from a plain dict (from JSON).

        Args:
            data: A dict with keys matching the 8 dataclass fields.

        Returns:
            A new ParamPreset instance.
        """
        # Filter to only known fields for forward-compat safety
        known = {f.name for f in dataclass_fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


def build_preset_from_config(name: str, config: Any) -> ParamPreset:
    """Snapshot current sampler values from ``config`` into a named preset.

    Args:
        name: The user-supplied name for the preset.
        config: A BellbirdConfig (or any object with the 7 sampler
            attributes: temperature, min_p, max_tokens, top_p, top_k,
            repeat_penalty, seed).

    Returns:
        A new ParamPreset with the given name and the config's current
        sampler values.

    Note:
        This function is wx-free and does not import BellbirdConfig
        at the module level — it accepts any duck-typed config object.
    """
    return ParamPreset(
        name=name,
        temperature=config.temperature,
        min_p=config.min_p,
        max_tokens=config.max_tokens,
        top_p=config.top_p,
        top_k=config.top_k,
        repeat_penalty=config.repeat_penalty,
        seed=config.seed,
    )
