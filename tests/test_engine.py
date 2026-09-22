from pathlib import Path
from typing import Any

import pytest

import decisors.engine as engine_module
from decisors.config import ConfigStore
from decisors.engine import DecisionEngine
from decisors.errors import NotStartedError


class FakeLaya:
    name = "laya"

    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self.stopped = False

    def prepare(self) -> dict[str, Any]:
        return {"provider": "laya", "model": "fake", "ready": True}

    def evaluate(self, request: Any) -> dict[str, Any]:
        qid = next(iter(request.questions))
        return {
            "provider": "laya",
            "model": "fake",
            "usage": {"input_tokens": 3, "output_tokens": 0},
            "answers": {qid: {"type": "noul", "noul": 0.9}},
        }

    def stop(self) -> None:
        self.stopped = True

    def status(self) -> dict[str, Any]:
        return {"provider": "laya", "ready": not self.stopped, "model": "fake"}


def test_requires_start_and_keeps_provider_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(engine_module, "LayaProvider", FakeLaya)
    engine = DecisionEngine(ConfigStore(tmp_path / "config.toml"))

    with pytest.raises(NotStartedError):
        engine.evaluate("x", {"ok": {"type": "noul", "instructions": "Is it ok?"}})

    initialized = engine.initialize()
    assert initialized["initialized"] is True
    assert engine.status()["ready"] is True
    assert engine.status()["active"] is False

    engine.start()
    result = engine.evaluate("x", {"ok": {"type": "noul", "instructions": "Is it ok?"}})
    assert result["answers"]["ok"]["noul"] == 0.9

    engine.stop()
    assert engine.status()["active"] is False


def test_status_catalog_does_not_load_a_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        engine_module,
        "cached_checkpoints",
        lambda root=None: {"english": False, "multilingual": True, "typed-decisions": False},
    )
    engine = DecisionEngine(ConfigStore(tmp_path / "config.toml"))

    status = engine.status()

    assert status["active"] is False
    assert status["ready"] is False
    assert status["catalog"]["cached"]["multilingual"] is True
    assert "openrouter" in status["catalog"]["credentials"]
    assert status["catalog"]["warmup_model"] in {"english", "multilingual"}


def test_provider_change_never_falls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine_module, "LayaProvider", FakeLaya)
    engine = DecisionEngine(ConfigStore(tmp_path / "config.toml"))
    engine.initialize()
    status = engine.configure(provider="openrouter")
    assert status["config"]["provider"] == "openrouter"
    assert status["active"] is False
    assert status["ready"] is False


def test_probe_does_not_initialize(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "decisors.devices.probe_devices",
        lambda: {"recommended": "cpu", "mode": "sequential", "lay": ["ok"]},
    )
    engine = DecisionEngine(ConfigStore(tmp_path / "config.toml"))
    result = engine.probe()
    assert result["recommended"] == "cpu"
    assert engine.settings.initialized is False
    assert not (tmp_path / "config.toml").exists()
