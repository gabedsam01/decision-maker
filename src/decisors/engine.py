"""Lifecycle and explicit provider selection for Decisors."""

from __future__ import annotations

import importlib.util
import platform
import sys
import threading
from dataclasses import asdict, replace
from typing import Any

from .config import ConfigStore, get_credential
from .domain import DecisionRequest, DecisionResult
from .errors import ConfigurationError, DecisorsError, NotStartedError, ValidationError
from .providers import LayaProvider, OpenRouterProvider, TypeSafeProvider
from .providers.base import DecisionProvider
from .providers.laya import cached_checkpoints, locale_warmup_model

SAMPLE_STATE = {"message": "I was charged twice and need this fixed today."}
SAMPLE_QUESTIONS = {
    "urgent": {
        "type": "noul",
        "instructions": "Does the sender explicitly request prompt help?",
    },
    "team": {
        "type": "choice",
        "instructions": "Which team best matches the message?",
        "criteria": {
            "billing": "Charges, payments, and refunds",
            "technical": "Software failures",
            "other": "None of these",
        },
    },
}


class DecisionEngine:
    def __init__(self, store: ConfigStore | None = None) -> None:
        self.store = store or ConfigStore()
        self.settings = self.store.load()
        self._provider: DecisionProvider | None = None
        self._judge: DecisionProvider | None = None
        self._ready = False
        self._active = False
        self._warming = False
        self._warmup_error: str | None = None

    def _new_provider(self) -> DecisionProvider:
        if self.settings.provider == "laya":
            return LayaProvider(self.settings)
        if self.settings.provider == "typesafe":
            return TypeSafeProvider(self.settings)
        if self.settings.provider == "openrouter":
            return OpenRouterProvider(self.settings)
        raise ConfigurationError(f"Unsupported provider {self.settings.provider!r}.")

    def _get_provider(self) -> DecisionProvider:
        if self._provider is None:
            self._provider = self._new_provider()
        return self._provider

    def plan(self) -> dict[str, Any]:
        return self._get_provider().plan()

    def probe(self) -> dict[str, Any]:
        from .devices import probe_devices

        return probe_devices()

    def referee(self, tool: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        from .referee import command_report, skill_shortlist, subagent_report, where_plan

        params = params or {}
        if tool == "command":
            return command_report(
                str(params.get("command") or ""),
                int(params.get("exit_code") or 0),
                str(params.get("stdout") or ""),
                str(params.get("stderr") or ""),
            )
        if tool == "subagent":
            return subagent_report(
                str(params.get("status") or ""),
                str(params.get("output") or ""),
                str(params.get("error") or ""),
            )
        if tool == "skill":
            catalog = params.get("catalog")
            if not isinstance(catalog, list):
                raise ValidationError("catalog precisa ser uma lista.")
            return skill_shortlist(str(params.get("task") or ""), catalog)
        if tool == "where":
            options = params.get("options")
            if not isinstance(options, list):
                raise ValidationError("options precisa ser uma lista.")
            allowed = params.get("cloud_allowed")
            if allowed is not None and not isinstance(allowed, bool):
                raise ValidationError("cloud_allowed precisa ser verdadeiro, falso ou ausente.")
            return where_plan(len(options), self._catalog()["credentials"], allowed)
        if tool == "conclude":
            return self._conclude_local(params)
        if tool == "cloud_once":
            return self._cloud_once(params)
        raise DecisorsError(f"Unknown referee tool {tool!r}.")

    def _choice_request(self, params: dict[str, Any], chunk: list[str]) -> DecisionRequest:
        return DecisionRequest.from_value(
            params.get("state") or "",
            {
                "pick": {
                    "type": "choice",
                    "instructions": params.get("instructions") or "Qual opção segue?",
                    "criteria": {item: None for item in chunk},
                }
            },
        )

    def _judge_provider(self) -> DecisionProvider:
        # ponytail: one cached Laya judge for local referee scoring; a load costs ~67s each.
        if self._judge is None:
            self._judge = LayaProvider(replace(self.settings, provider="laya", model="auto"))
        return self._judge

    def _conclude_local(self, params: dict[str, Any]) -> dict[str, Any]:
        from .referee import conclude_scored, expand_label, shape_text

        options = params.get("options")
        if not isinstance(options, list):
            raise ValidationError("options precisa ser uma lista.")
        str_options = [str(item) for item in options]
        if self.settings.provider == "laya":
            if not self._active:
                raise NotStartedError("Decisors is stopped. Run /decision start before agent evaluations.")
            provider = self._get_provider()
        else:
            provider = self._judge_provider()
        shaped, _question, portuguese = shape_text(
            params.get("state") or "",
            str(params.get("instructions") or ""),
        )

        def score(label: str) -> float:
            target = expand_label(label, portuguese)
            instructions = (
                f"O `texto` escolhe {target}." if portuguese else f"The `texto` selects {target}."
            )
            result = provider.evaluate(
                DecisionRequest.from_value(shaped, {"q": {"type": "noul", "instructions": instructions}})
            )
            return float(result["answers"]["q"]["noul"])

        return conclude_scored(str_options, score)

    def _cloud_once(self, params: dict[str, Any]) -> dict[str, Any]:
        provider_name = str(params.get("provider") or "")
        if provider_name not in {"typesafe", "openrouter"}:
            raise ConfigurationError("A nuvem desta chamada precisa ser typesafe ou openrouter.")
        if not self._catalog()["credentials"].get(provider_name):
            raise ConfigurationError(f"Sem chave para {provider_name}.")
        options = params.get("options")
        if not isinstance(options, list):
            raise ValidationError("options precisa ser uma lista.")
        saved = self.settings
        config_existed = self.store.path.exists()
        config_before = self.store.path.read_text(encoding="utf-8") if config_existed else None
        remote_settings = replace(saved, provider=provider_name, model="auto")
        remote = (
            TypeSafeProvider(remote_settings)
            if provider_name == "typesafe"
            else OpenRouterProvider(remote_settings)
        )
        result = remote.evaluate(self._choice_request(params, [str(item) for item in options]))
        choice = str(result["answers"]["pick"]["choice"])
        config_after = self.store.path.read_text(encoding="utf-8") if self.store.path.exists() else None
        if self.settings != saved or config_after != config_before:
            raise ConfigurationError("A chamada de nuvem alterou o provider salvo.")
        return {
            "mode": "cloud",
            "provider": provider_name,
            "choice": choice,
            "say": f"Ficou em {choice}. Uma chamada em {provider_name}.",
            "authorized": False,
        }

    def initialize(self) -> dict[str, Any]:
        provider = self._get_provider()
        prepared = provider.prepare()
        self._ready = True
        if not self.settings.initialized:
            self.settings = self.store.update(initialized=True)
        return {"initialized": True, "active": self._active, **prepared}

    def start(self) -> dict[str, Any]:
        if not self._ready:
            self.initialize()
        self._active = True
        self.settings = self.store.update(active=True)
        return self.status()

    def start_async(self) -> dict[str, Any]:
        """Kick warm-up in a background thread and return immediately (warming state)."""
        if self._warming or self._active:
            return self.status()
        self._warming = True
        self._warmup_error = None

        def run() -> None:
            try:
                self.initialize()
                self._active = True
                self.settings = self.store.update(active=True)
            except Exception as exc:
                self._warmup_error = f"{type(exc).__name__}: warm-up failed."
            finally:
                self._warming = False

        threading.Thread(target=run, name="decisors-warmup", daemon=True).start()
        return self.status()

    def stop(self) -> dict[str, Any]:
        self._active = False
        self.settings = self.store.update(active=False)
        if self._provider is not None:
            self._provider.stop()
        self._provider = None
        if self._judge is not None:
            self._judge.stop()
            self._judge = None
        self._ready = False
        return self.status()

    def evaluate(self, state: Any, questions: Any) -> DecisionResult:
        if not self._active:
            if self._warming:
                raise NotStartedError("Decisors warm-up em andamento; tente de novo em instantes.")
            raise NotStartedError("Decisors is stopped. Run /decision start before agent evaluations.")
        request = DecisionRequest.from_value(state, questions)
        return self._get_provider().evaluate(request)

    def test(self) -> DecisionResult:
        if not self._ready:
            self.initialize()
        request = DecisionRequest.from_value(SAMPLE_STATE, SAMPLE_QUESTIONS)
        return self._get_provider().evaluate(request)

    def configure(self, **changes: Any) -> dict[str, Any]:
        before = self.settings
        updated = self.store.update(**changes)
        restart_fields = {"provider", "model", "device", "max_loaded"}
        changed_restart = any(
            getattr(before, field) != getattr(updated, field) for field in restart_fields
        )
        self.settings = updated
        if changed_restart:
            self._active = False
            self._ready = False
            if self._provider is not None:
                self._provider.stop()
            self._provider = None
            if self._judge is not None:
                self._judge.stop()
                self._judge = None
        return self.status()

    def status(self) -> dict[str, Any]:
        if self._provider is not None:
            provider_status = self._provider.status()
        else:
            # Light remote-aware status: same credential source as the providers, no model load.
            name = self.settings.provider
            ready = bool(get_credential(name)) if name != "laya" else False
            provider_status = {"provider": name, "ready": ready, "model": self.settings.model}
        return {
            "active": self._active,
            "ready": self._ready,
            "warming": self._warming,
            "warmup_error": self._warmup_error,
            "initialized": self.settings.initialized,
            "config_path": str(self.store.path),
            "config": asdict(self.settings),
            "provider_status": provider_status,
            "catalog": self._catalog(),
        }

    def _catalog(self) -> dict[str, Any]:
        try:
            cached = cached_checkpoints()
        except OSError:
            cached = {}
        return {
            "cached": cached,
            "warmup_model": locale_warmup_model(),
            "credentials": {
                "openrouter": bool(get_credential("openrouter")),
                "typesafe": bool(get_credential("typesafe")),
            },
        }

    def doctor(self) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        checks.append(
            {
                "name": "python",
                "ok": sys.version_info >= (3, 11),
                "detail": platform.python_version(),
            }
        )
        checks.append(
            {
                "name": "config",
                "ok": True,
                "detail": str(self.store.path),
            }
        )
        if self.settings.provider == "laya":
            checks.append(
                {
                    "name": "laya",
                    "ok": importlib.util.find_spec("laya") is not None,
                    "detail": "Python package import",
                }
            )
        else:
            key_env = "TYPESAFE_API_KEY" if self.settings.provider == "typesafe" else "OPENROUTER_API_KEY"
            checks.append(
                {
                    "name": key_env,
                    "ok": bool(get_credential(self.settings.provider)),
                    "detail": "environment or auth.json credential",
                }
            )
        return {
            "ok": all(bool(check["ok"]) for check in checks),
            "checks": checks,
            "status": self.status(),
        }
