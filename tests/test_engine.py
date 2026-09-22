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


def test_engine_status_follows_credential_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    engine = DecisionEngine(ConfigStore(tmp_path / "config.toml"))
    engine.configure(provider="openrouter")
    assert engine.status()["provider_status"]["ready"] is False

    auth = tmp_path / ".pi" / "agent" / "auth.json"
    auth.parent.mkdir(parents=True)
    auth.write_text('{"openrouter": {"key": "from-file"}}', encoding="utf-8")
    assert engine.status()["provider_status"]["ready"] is True


def test_referee_local_reuses_one_loaded_judge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[FakeLaya] = []

    class FakeJudge(FakeLaya):
        def evaluate(self, request: Any) -> dict[str, Any]:
            qid = next(iter(request.questions))
            text = request.questions[qid]["instructions"]
            score = 0.9 if "alpha" in text else 0.3
            return {
                "provider": "laya",
                "model": "fake",
                "usage": {"input_tokens": 3, "output_tokens": 0},
                "answers": {qid: {"type": "noul", "noul": score}},
            }

    def factory(settings: Any) -> FakeLaya:
        fake = FakeJudge(settings)
        created.append(fake)
        return fake

    monkeypatch.setattr(engine_module, "LayaProvider", factory)
    engine = DecisionEngine(ConfigStore(tmp_path / "config.toml"))
    engine.configure(provider="openrouter")

    for _ in range(2):
        picked = engine.referee("conclude", {"options": ["alpha", "beta"]})
        assert picked["choice"] == "alpha"

    assert len(created) == 1
    engine.stop()
    assert created[0].stopped is True
