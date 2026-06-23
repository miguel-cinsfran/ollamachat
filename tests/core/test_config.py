"""Tests for bellbird.core.config — strict TDD, wx-free.

Covers: missing file defaults, save+load round-trip, unknown key filtering,
per-instance list default. All use monkeypatch for CONFIG_PATH isolation.
"""

import json

import pytest

from bellbird.core.config import BellbirdConfig, load_config, save_config


def test_load_config_returns_defaults_on_missing_file(monkeypatch, tmp_path):
    """GIVEN CONFIG_PATH is a non-existent path
    WHEN load_config() is called
    THEN return BellbirdConfig() with no exception."""
    from bellbird.core import config as config_module

    monkeypatch.setattr(config_module, "CONFIG_PATH", tmp_path / "nope.json")
    result = load_config()
    assert result == BellbirdConfig()


def test_save_and_load_roundtrip(monkeypatch, tmp_path):
    """GIVEN a BellbirdConfig with non-default values
    WHEN save_config then load_config
    THEN the loaded config equals the original."""
    cfg = BellbirdConfig(
        port=9090,
        ctx_size=8192,
        extra_model_folders=["D:\\llms"],
    )
    path = tmp_path / "config.json"
    save_config(cfg, path)
    from bellbird.core import config as config_module

    monkeypatch.setattr(config_module, "CONFIG_PATH", path)
    loaded = load_config()
    assert loaded == cfg


def test_load_config_ignores_unknown_keys(monkeypatch, tmp_path):
    """GIVEN a JSON file with extra unknown keys
    WHEN load_config() is called
    THEN known fields are loaded and unknown keys are silently dropped."""
    path = tmp_path / "config.json"
    data = {
        "port": 9090,
        "future_field": "x",
        "temperature": 0.5,
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    from bellbird.core import config as config_module

    monkeypatch.setattr(config_module, "CONFIG_PATH", path)
    result = load_config()
    assert result.port == 9090
    assert result.temperature == 0.5
    assert result.max_tokens == 4096


def test_extra_model_folders_default_is_empty_list():
    """GIVEN two fresh BellbirdConfig() instances
    WHEN one gets an appended folder
    THEN the other instance still has an empty list."""
    a = BellbirdConfig()
    b = BellbirdConfig()
    a.extra_model_folders.append("/x")
    assert b.extra_model_folders == []
