import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from decisors.config import ConfigStore, get_credential
from decisors.engine import DecisionEngine
from decisors.errors import NotStartedError
from decisors.referee import (
    command_report,
    pick_scored,
    shape_text,
    skill_shortlist,
    subagent_report,
    where_plan,
)


def test_rg_exit_1_is_empty() -> None:
    report = command_report("rg foo src", 1, "", "")
    assert report["verdict"] == "vazio"
    assert report["needs_model"] is False


def test_destructive_is_not_authorization() -> None:
    report = command_report("rm -rf /tmp/x", 0, "gone", "")
    assert report["verdict"] == "risco"
    assert report["authorized"] is False


def test_subagent_infra_does_not_retry() -> None:
    report = subagent_report("failed", "", "Agent uses removed frontmatter field fallbackModels")
    assert report["verdict"] == "infra"
    assert report["retry"] is False


def test_skill_shortlist_caps_at_19_and_honors_a_named_skill() -> None:
    catalog = [{"name": f"skill-{index}", "description": "alpha"} for index in range(40)]
    catalog.append({"name": "ponytail", "description": "be lazy"})
    capped = skill_shortlist("alpha work", catalog)
    assert len(capped["shortlist"]) <= 19
    named = skill_shortlist("use ponytail please", catalog)
    assert named["recommended"] == "ponytail"
    assert len(named["shortlist"]) == 1


def test_local_only_never_mentions_cloud() -> None:
    plan = where_plan(30, {"typesafe": False, "openrouter": False})
    assert plan["mode"] == "local_loop"
    blob = json.dumps(plan).lower()
    assert "nuvem" not in blob
    assert "api" not in blob
    assert "typesafe" not in blob


def test_key_present_asks_and_does_not_call_cloud() -> None:
    plan = where_plan(21, {"typesafe": True, "openrouter": False}, None)
    assert plan["mode"] == "ask"
    assert plan["provider"] == "typesafe"
    assert plan["authorized"] is False


def test_no_keeps_the_local_loop() -> None:
    plan = where_plan(21, {"typesafe": True}, False)
    assert plan["mode"] == "local_loop"


def test_yes_is_one_cloud_call() -> None:
    plan = where_plan(21, {"openrouter": True}, True)
    assert plan["mode"] == "cloud"
    assert plan["provider"] == "openrouter"


def test_engine_where_does_not_leak_key_or_start(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "secret-value")
    engine = DecisionEngine(ConfigStore(tmp_path / "config.toml"))
    result = engine.referee("where", {"options": [str(index) for index in range(21)]})
    assert result["mode"] == "ask"
    assert "secret-value" not in json.dumps(result)
    assert engine._active is False


def test_find_exit_1_is_not_a_clean_miss() -> None:
    report = command_report("find . -name x", 1, "", "find: permission denied")
    assert report["verdict"] != "vazio"


def test_named_skill_prefers_the_longest_whole_name() -> None:
    catalog = [
        {"name": "pi", "description": "agent"},
        {"name": "pi-extension", "description": "adapter"},
    ]
    named = skill_shortlist("use pi-extension", catalog)
    assert named["recommended"] == "pi-extension"


def test_close_scores_do_not_pick_the_first_label() -> None:
    result = pick_scored({"placa": 0.51, "processador": 0.49})
    assert result["choice"] is None
    assert result["authorized"] is False


def test_clear_gap_picks_the_higher_score_not_the_first_label() -> None:
    result = pick_scored({"placa": 0.04, "processador": 0.61})
    assert result["choice"] == "processador"


def test_empty_state_keeps_the_instruction_text() -> None:
    shaped, _question, portuguese = shape_text("", "Só o processador foi medido. Não use a placa.")
    assert "processador" in shaped["texto"]
    assert portuguese is True


def test_conclude_on_cloud_provider_stays_local_without_writing(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "config.toml"
    engine = DecisionEngine(ConfigStore(path))
    engine.settings = replace(engine.settings, provider="openrouter", model="jev-latest")
    seen: list[str] = []

    class FakeLaya:
        def __init__(self, settings: Any) -> None:
            seen.append(settings.provider)
            seen.append(settings.model)

        def evaluate(self, request: Any) -> dict[str, Any]:
            instructions = request.questions["q"]["instructions"]
            score = 0.9 if instructions.endswith(" a.") else 0.1
            return {"answers": {"q": {"noul": score}}}

        def stop(self) -> None:
            seen.append("stopped")

    monkeypatch.setattr("decisors.engine.LayaProvider", FakeLaya)
    result = engine.referee("conclude", {"options": ["a", "b"]})
    assert result["choice"] == "a"
    assert engine.settings.provider == "openrouter"
    assert engine.settings.model == "jev-latest"
    assert not path.exists()
    assert seen == ["laya", "auto"]
    engine.stop()
    assert seen == ["laya", "auto", "stopped"]


def test_cloud_once_does_not_write_config_or_send_laya_model(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "secret-value")
    path = tmp_path / "config.toml"
    engine = DecisionEngine(ConfigStore(path))
    engine.settings = replace(engine.settings, model="convaiinnovations/laya-multilingual")
    seen: dict[str, str] = {}

    class FakeRemote:
        def __init__(self, settings: Any) -> None:
            seen["provider"] = settings.provider
            seen["model"] = settings.model

        def evaluate(self, request: Any) -> dict[str, Any]:
            return {"answers": {"pick": {"choice": "b"}}}

    monkeypatch.setattr("decisors.engine.TypeSafeProvider", FakeRemote)
    result = engine.referee(
        "cloud_once",
        {"provider": "typesafe", "options": ["a", "b"]},
    )
    assert result["choice"] == "b"
    assert result["authorized"] is False
    assert seen == {"provider": "typesafe", "model": "auto"}
    assert engine.settings.provider == "laya"
    assert engine.settings.model == "convaiinnovations/laya-multilingual"
    assert not path.exists()
    assert "secret-value" not in json.dumps(result)


def test_conclude_requires_start(tmp_path) -> None:
    engine = DecisionEngine(ConfigStore(tmp_path / "config.toml"))
    with pytest.raises(NotStartedError):
        engine.referee("conclude", {"options": ["a", "b"]})


def test_expand_label_numbers() -> None:
    from decisors.referee import expand_label

    assert expand_label("7", True) == "7 ou sete"
    assert expand_label("sete", True) == "sete ou 7"
    assert expand_label("7", False) == "7 or seven"
    assert expand_label("seven", False) == "seven or 7"
    assert expand_label("placa", True) == "placa"


def test_conclude_scored_21_options_picks_target() -> None:
    from decisors.referee import conclude_scored

    options = [str(i) for i in range(1, 22)]

    def score(label: str) -> float:
        return 0.95 if label == "7" else 0.01

    result = conclude_scored(options, score)
    assert result["choice"] == "7"
    assert result["rounds"] == 2
    assert result["mode"] == "local_loop"


def test_get_credential_from_auth_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    fake_auth = tmp_path / "auth.json"
    fake_auth.write_text(json.dumps({"openrouter": {"key": "test-key-or", "type": "api_key"}}))

    monkeypatch.setattr(Path, "home", lambda: tmp_path.parent)
    pi_dir = tmp_path.parent / ".pi" / "agent"
    pi_dir.mkdir(parents=True, exist_ok=True)
    (pi_dir / "auth.json").write_text(fake_auth.read_text())

    key = get_credential("openrouter")
    assert key == "test-key-or"

