import json

import pytest

from decisors.config import Settings
from decisors.domain import DecisionRequest
from decisors.errors import ConfigurationError, ProviderError
from decisors.providers.openrouter import OpenRouterProvider
from decisors.providers.typesafe import TypeSafeProvider

REQUEST = DecisionRequest.from_value(
    {"message": "refund"},
    {
        "route": {
            "type": "choice",
            "instructions": "Route it",
            "criteria": {"billing": "payments", "other": None},
        }
    },
)


def result(model: str) -> dict:
    return {
        "model": model,
        "usage": {"input_tokens": 20, "output_tokens": 0},
        "answers": {
            "route": {
                "type": "choice",
                "choice": "billing",
                "probabilities": {"billing": 0.9, "other": 0.1},
                "confidence": 0.8,
            }
        },
    }


def test_openrouter_uses_decisions_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret")
    seen = {}

    def transport(url: str, headers: dict[str, str], body: bytes, timeout: float) -> dict:
        seen.update(url=url, headers=headers, body=json.loads(body), timeout=timeout)
        return result("typesafe/jev-1.13")

    provider = OpenRouterProvider(Settings(provider="openrouter"), transport=transport)
    response = provider.evaluate(REQUEST)

    assert seen["url"] == "https://openrouter.ai/api/alpha/decisions"
    assert seen["body"]["model"] == "typesafe/jev-1.13"
    assert seen["headers"]["Authorization"] == "Bearer secret"
    assert response["provider"] == "openrouter"


def test_typesafe_uses_system_one_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "secret")
    seen = {}

    def transport(url: str, headers: dict[str, str], body: bytes, timeout: float) -> dict:
        seen["url"] = url
        return result("jev-latest")

    provider = TypeSafeProvider(Settings(provider="typesafe"), transport=transport)
    provider.evaluate(REQUEST)
    assert seen["url"] == "https://api.typesafe.ai/v1/systemone"


def test_remote_requires_explicit_key(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    provider = OpenRouterProvider(Settings(provider="openrouter"), transport=lambda *_: result("x"))
    with pytest.raises(ConfigurationError, match="OPENROUTER_API_KEY"):
        provider.prepare()


def test_remote_request_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret")
    provider = OpenRouterProvider(
        Settings(provider="openrouter", max_requests_per_session=1),
        transport=lambda *_: result("typesafe/jev-1.13"),
    )
    provider.evaluate(REQUEST)
    with pytest.raises(ProviderError, match="request limit"):
        provider.evaluate(REQUEST)


def test_status_ready_follows_credential_store_not_just_env(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    provider = OpenRouterProvider(Settings(provider="openrouter"))
    assert provider.status()["ready"] is False

    auth = tmp_path / ".pi" / "agent" / "auth.json"
    auth.parent.mkdir(parents=True)
    auth.write_text(json.dumps({"openrouter": {"key": "from-file"}}), encoding="utf-8")

    status = provider.status()
    assert status["ready"] is True
    assert provider._key() == "from-file"
