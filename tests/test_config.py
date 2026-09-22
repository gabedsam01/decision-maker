from pathlib import Path

import pytest

from decisors.config import ConfigStore, Settings
from decisors.errors import ConfigurationError


def test_default_is_local_laya(tmp_path: Path) -> None:
    store = ConfigStore(tmp_path / "config.toml")
    settings = store.load()
    assert settings.provider == "laya"
    assert settings.model == "auto"
    assert settings.device == "auto"


def test_round_trip_and_update(tmp_path: Path) -> None:
    store = ConfigStore(tmp_path / "config.toml")
    store.save(Settings())
    updated = store.update(provider="openrouter", model="typesafe/jev-1.13")
    assert updated.provider == "openrouter"
    assert store.load().model == "typesafe/jev-1.13"
    assert (tmp_path / "config.toml").stat().st_mode & 0o777 == 0o600


def test_rejects_unknown_provider(tmp_path: Path) -> None:
    store = ConfigStore(tmp_path / "config.toml")
    with pytest.raises(ConfigurationError, match="Unknown provider"):
        store.save(Settings(provider="mystery"))
