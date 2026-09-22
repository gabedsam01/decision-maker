from pathlib import Path
from typing import Any

from decisors.config import Settings
from decisors.providers.laya import LayaProvider, cached_checkpoints


class FakeRouter:
    def __init__(self) -> None:
        self.models = {"english": "convaiinnovations/laya"}
        self.loaded: list[str] = []
        self.predictions: list[tuple[Any, Any, str | None]] = []

    def route(
        self,
        state: Any,
        questions: Any,
        model: str | None = None,
    ) -> dict[str, str]:
        return {"model": model or "english"}

    def load(self, name: str) -> object:
        self.loaded.append(name)
        return object()

    def predict(
        self,
        state: Any,
        questions: Any,
        model: str | None = None,
    ) -> dict[str, Any]:
        self.predictions.append((state, questions, model))
        return {"model": "fake", "usage": {"input_tokens": 1, "output_tokens": 0}, "answers": {}}

    def unload(self) -> None:
        self.loaded.clear()


def test_router_is_local_lazy_and_never_auto_selects_typed_decisions() -> None:
    captured: dict[str, Any] = {}

    class FakeLaya:
        @staticmethod
        def Router(**kwargs: Any) -> FakeRouter:
            captured.update(kwargs)
            return FakeRouter()

    provider = LayaProvider(Settings())
    provider._laya = lambda: FakeLaya()  # type: ignore[method-assign]
    provider._ensure_router()

    assert captured["standalone_repos"] is True
    assert captured["auto_task_detection"] is False
    assert captured["max_loaded"] == 1


def test_prepare_loads_target_and_runs_warmup() -> None:
    router = FakeRouter()
    provider = LayaProvider(Settings())
    provider._router = router

    result = provider.prepare()

    assert router.loaded == ["english"]
    assert len(router.predictions) == 1
    _, questions, model = router.predictions[0]
    assert set(questions) == {"team", "duplicate_charge"}
    assert model == "english"
    assert result["warmup_ok"] is True
    assert result["model"] == "english"


def test_status_reports_resolved_checkpoint_not_auto() -> None:
    router = FakeRouter()
    router.loaded = ["multilingual"]
    provider = LayaProvider(Settings(model="auto"))
    provider._router = router

    status = provider.status()

    assert status["configured_model"] == "auto"
    assert status["loaded"] == ["multilingual"]
    assert status["resolved_model"] == "english"
    assert status["model"] == "english"
    assert status["model"] != "auto"


def test_cached_checkpoints_follow_real_safetensors(tmp_path: Path) -> None:
    blob = tmp_path / "blob"
    blob.write_bytes(b"x" * 1_000_001)
    english = tmp_path / "models--convaiinnovations--laya" / "snapshots" / "abc"
    english.mkdir(parents=True)
    (english / "model.safetensors").symlink_to(blob)
    typed = tmp_path / "models--convaiinnovations--laya-typed-decisions" / "snapshots" / "abc"
    typed.mkdir(parents=True)
    (typed / "model.safetensors").write_bytes(b"tiny")

    found = cached_checkpoints(tmp_path)

    assert found["english"] is True
    assert found["multilingual"] is False
    assert found["typed-decisions"] is False
