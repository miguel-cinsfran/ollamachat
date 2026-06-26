"""Tests for bellbird.core.preset — strict TDD, wx-free.

Covers: ParamPreset frozen dataclass, to_dict / from_dict round-trip,
build_preset_from_config copies 7 sampler fields, AST guard for no wx import.
"""

import ast
import dataclasses

import pytest


class TestParamPreset:
    """ParamPreset: frozen dataclass, 8 fields, JSON round-trip."""

    def test_param_preset_is_frozen(self):
        """GIVEN a ParamPreset instance
        WHEN attempting to mutate a field
        THEN FrozenInstanceError is raised (or AttributeError via frozen)."""
        from bellbird.core.preset import ParamPreset

        p = ParamPreset(name="X", temperature=0.7)
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            p.temperature = 0.9  # type: ignore[misc]

    def test_to_dict_returns_dict_with_all_fields(self):
        """GIVEN ParamPreset with all 8 fields
        WHEN to_dict() is called
        THEN the dict has all 8 expected keys."""
        from bellbird.core.preset import ParamPreset

        p = ParamPreset(
            name="creativo",
            temperature=1.10,
            min_p=0.08,
            max_tokens=2048,
            top_p=0.95,
            top_k=50,
            repeat_penalty=1.05,
            seed=42,
        )
        d = p.to_dict()
        expected_keys = {
            "name", "temperature", "min_p", "max_tokens",
            "top_p", "top_k", "repeat_penalty", "seed",
        }
        assert set(d.keys()) == expected_keys

    def test_from_dict_round_trip(self):
        """GIVEN a ParamPreset instance
        WHEN serialized to dict and back via from_dict
        THEN the round-tripped instance equals the original."""
        from bellbird.core.preset import ParamPreset

        p = ParamPreset(
            name="creativo",
            temperature=1.10,
            min_p=0.08,
            max_tokens=2048,
            top_p=0.95,
            top_k=50,
            repeat_penalty=1.05,
            seed=42,
        )
        d = p.to_dict()
        p2 = ParamPreset.from_dict(d)
        assert p == p2

    def test_to_dict_handles_negative_seed(self):
        """GIVEN ParamPreset with seed=-1 (the sentinel)
        WHEN to_dict() is called
        THEN seed round-trips as -1 (not dropped or coerced)."""
        from bellbird.core.preset import ParamPreset

        p = ParamPreset(
            name="aleatorio",
            temperature=0.7,
            min_p=0.05,
            max_tokens=512,
            top_p=0.9,
            top_k=40,
            repeat_penalty=1.1,
            seed=-1,
        )
        d = p.to_dict()
        assert d["seed"] == -1
        p2 = ParamPreset.from_dict(d)
        assert p2.seed == -1


class TestBuildPresetFromConfig:
    """build_preset_from_config: snapshot current config values."""

    def test_build_preset_from_config_copies_7_fields(self):
        """GIVEN a BellbirdConfig with specific sampler values
        WHEN build_preset_from_config is called with a name
        THEN all 7 sampler fields match the config, name matches the arg."""
        from bellbird.core.config import BellbirdConfig
        from bellbird.core.preset import build_preset_from_config

        cfg = BellbirdConfig(
            temperature=0.42,
            min_p=0.07,
            max_tokens=2048,
            top_p=0.85,
            top_k=50,
            repeat_penalty=1.15,
            seed=42,
        )
        preset = build_preset_from_config("test", cfg)
        assert preset.name == "test"
        assert preset.temperature == 0.42
        assert preset.min_p == 0.07
        assert preset.max_tokens == 2048
        assert preset.top_p == 0.85
        assert preset.top_k == 50
        assert preset.repeat_penalty == 1.15
        assert preset.seed == 42

    def test_build_preset_from_config_preserves_negative_seed(self):
        """GIVEN BellbirdConfig with seed=-1
        WHEN build_preset_from_config is called
        THEN the preset seed is -1 (the sentinel is preserved)."""
        from bellbird.core.config import BellbirdConfig
        from bellbird.core.preset import build_preset_from_config

        cfg = BellbirdConfig(seed=-1)
        preset = build_preset_from_config("aleatorio", cfg)
        assert preset.seed == -1

    def test_asdict_round_trip(self):
        """GIVEN a ParamPreset instance
        WHEN dataclasses.asdict is used and ParamPreset(**dict) reconstructs
        THEN the new instance equals the original (JSON round-trip contract)."""
        import dataclasses
        from bellbird.core.preset import ParamPreset

        p = ParamPreset(
            name="x",
            temperature=0.7,
            min_p=0.05,
            max_tokens=512,
            top_p=0.9,
            top_k=40,
            repeat_penalty=1.1,
            seed=-1,
        )
        d = dataclasses.asdict(p)
        p2 = ParamPreset(**d)
        assert p == p2


class TestPresetASTGuards:
    """AST-level guards: no wx import, correct field count."""

    def test_ast_no_wx_import(self):
        """GIVEN the source of bellbird/core/preset.py
        WHEN parsed with ast
        THEN no Import or ImportFrom node references 'wx'."""
        source = (__file__.replace("tests/core/test_preset.py", "bellbird/core/preset.py"))
        with open(source, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    assert "wx" not in alias.name, (
                        f"wx import found in preset.py: {alias.name}"
                    )

    def test_8_fields(self):
        """GIVEN the ParamPreset dataclass
        THEN it has exactly 8 fields (name + 7 samplers)."""
        from bellbird.core.preset import ParamPreset

        fields = dataclasses.fields(ParamPreset)
        assert len(fields) == 8
        field_names = [f.name for f in fields]
        expected = [
            "name", "temperature", "min_p", "max_tokens",
            "top_p", "top_k", "repeat_penalty", "seed",
        ]
        assert field_names == expected
