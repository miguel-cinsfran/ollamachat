"""Tests for bellbird.core.config — strict TDD, wx-free.

Covers: missing file defaults, save+load round-trip, unknown key filtering,
per-instance list default, path location, legacy migration. All use
monkeypatch for CONFIG_PATH isolation.
"""

import importlib
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


def test_config_path_is_under_user_data_dir(monkeypatch, tmp_path):
    """GIVEN platformdirs.user_data_dir is monkeypatched to <tmp_path>/Bellbird
    WHEN bellbird.core.config is reloaded
    THEN CONFIG_PATH equals <tmp_path>/Bellbird/config.json
    AND does not contain bellbird/data."""
    import platformdirs

    monkeypatch.setattr(
        platformdirs,
        "user_data_dir",
        lambda app, appauthor: str(tmp_path / app),
    )
    from bellbird.core import config as config_module

    importlib.reload(config_module)

    expected = tmp_path / "Bellbird" / "config.json"
    assert config_module.CONFIG_PATH == expected
    assert "bellbird/data" not in str(config_module.CONFIG_PATH)
    assert "config.json" in str(config_module.CONFIG_PATH)


def test_migrate_legacy_legacy_exists_copies(monkeypatch, tmp_path):
    """GIVEN legacy config exists and new config does NOT
    WHEN migrate_legacy_config() runs
    THEN the new file is created with the legacy content
    AND the legacy file is NOT deleted."""
    import json

    from bellbird.core import config as config_module

    legacy = tmp_path / "data" / "config.json"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(json.dumps({"temperature": 0.42}), encoding="utf-8")

    new_dir = tmp_path / "Bellbird"
    new_config = new_dir / "config.json"
    assert not new_config.exists()

    monkeypatch.setattr(config_module, "LEGACY_CONFIG_PATH", legacy)
    monkeypatch.setattr(config_module, "CONFIG_PATH", new_config)

    config_module.migrate_legacy_config()

    assert new_config.exists()
    content = json.loads(new_config.read_text(encoding="utf-8"))
    assert content["temperature"] == 0.42
    # Legacy file must NOT be deleted
    assert legacy.exists()


def test_migrate_legacy_new_exists_no_overwrite(monkeypatch, tmp_path):
    """GIVEN both legacy and new config exist
    WHEN migrate_legacy_config() runs
    THEN new file is NOT overwritten."""
    import json

    from bellbird.core import config as config_module

    legacy = tmp_path / "data" / "config.json"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(json.dumps({"temperature": 0.42}), encoding="utf-8")

    new_dir = tmp_path / "Bellbird"
    new_dir.mkdir(parents=True, exist_ok=True)
    new_config = new_dir / "config.json"
    new_config.write_text(json.dumps({"temperature": 0.99}), encoding="utf-8")

    monkeypatch.setattr(config_module, "LEGACY_CONFIG_PATH", legacy)
    monkeypatch.setattr(config_module, "CONFIG_PATH", new_config)

    config_module.migrate_legacy_config()

    content = json.loads(new_config.read_text(encoding="utf-8"))
    # Must still have the original new value, NOT overwritten
    assert content["temperature"] == 0.99


def test_migrate_legacy_legacy_missing_noop(monkeypatch, tmp_path):
    """GIVEN legacy config does NOT exist
    WHEN migrate_legacy_config() runs
    THEN no exception is raised and no new file is created."""
    from bellbird.core import config as config_module

    new_dir = tmp_path / "Bellbird"
    new_config = new_dir / "config.json"
    assert not new_config.exists()

    # LEGACY_CONFIG_PATH points to non-existent file
    monkeypatch.setattr(config_module, "LEGACY_CONFIG_PATH", tmp_path / "nope.json")
    monkeypatch.setattr(config_module, "CONFIG_PATH", new_config)

    # Must not raise
    config_module.migrate_legacy_config()

    assert not new_config.exists()


def test_migrate_legacy_copy_raises_swallowed(monkeypatch, tmp_path):
    """GIVEN legacy exists but shutil.copy2 raises
    WHEN migrate_legacy_config() runs
    THEN no exception propagates (best-effort)."""
    from bellbird.core import config as config_module

    legacy = tmp_path / "data" / "config.json"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("{}", encoding="utf-8")

    new_dir = tmp_path / "Bellbird"
    new_config = new_dir / "config.json"

    monkeypatch.setattr(config_module, "LEGACY_CONFIG_PATH", legacy)
    monkeypatch.setattr(config_module, "CONFIG_PATH", new_config)

    # Make shutil.copy2 raise PermissionError
    import shutil

    original_copy2 = shutil.copy2

    def failing_copy2(src, dst, **kwargs):
        raise PermissionError("access denied")

    monkeypatch.setattr(shutil, "copy2", failing_copy2)

    # Must not raise
    config_module.migrate_legacy_config()


def test_extra_model_folders_default_is_empty_list():
    """GIVEN two fresh BellbirdConfig() instances
    WHEN one gets an appended folder
    THEN the other instance still has an empty list."""
    a = BellbirdConfig()
    b = BellbirdConfig()
    a.extra_model_folders.append("/x")
    assert b.extra_model_folders == []
