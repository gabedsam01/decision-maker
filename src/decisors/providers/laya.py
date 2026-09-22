"""Local Laya provider, imported lazily so CLI/config stays lightweight."""

from __future__ import annotations

import gc
import importlib
import locale
import os
import time
import urllib.request
from contextlib import suppress
from pathlib import Path
from typing import Any

from ..config import Settings
from ..domain import DecisionRequest, DecisionResult, validate_result
from ..errors import ConfigurationError, ProviderError

_CACHE_REPOS = {
    "english": "models--convaiinnovations--laya",
    "multilingual": "models--convaiinnovations--laya-multilingual",
    "typed-decisions": "models--convaiinnovations--laya-typed-decisions",
}


def cached_checkpoints(root: Path | None = None) -> dict[str, bool]:
    """True only when the safetensors blob is actually on disk.

    Hugging Face cache entries are symlinks. Follow them. A 76-byte link is not a model.
    """
    base = root or Path.home() / ".cache" / "huggingface" / "hub"
    found: dict[str, bool] = {}
    for key, dirname in _CACHE_REPOS.items():
        repo = base / dirname
        ok = False
        if repo.is_dir():
            for path in repo.rglob("model.safetensors"):
                try:
                    if path.stat().st_size > 1_000_000:
                        ok = True
                        break
                except OSError:
                    continue
        found[key] = ok
    return found


def locale_warmup_model() -> str:
    language = (locale.getlocale()[0] or os.environ.get("LANG", "en")).lower()
    return "english" if language.startswith("en") else "multilingual"


class LayaProvider:
    name = "laya"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._router: Any | None = None
        self._loaded_for_init: str | None = None

    def _laya(self) -> Any:
        try:
            return importlib.import_module("laya")
        except ImportError as exc:
            raise ConfigurationError(
                "Laya is not installed. Reinstall Decisors with its default dependencies."
            ) from exc

    def _device(self) -> str | None:
        return None if self.settings.device == "auto" else self.settings.device

    def _ensure_router(self) -> Any:
        if self._router is not None:
            return self._router
        laya = self._laya()
        try:
            self._router = laya.Router(
                device=self._device(),
                max_loaded=self.settings.max_loaded,
                default="english",
                auto_task_detection=False,
                standalone_repos=True,
            )
        except Exception as exc:
            raise ProviderError(f"Could not initialize Laya runtime: {type(exc).__name__}.") from exc
        return self._router

    def _warmup_state(self) -> str:
        language = (locale.getlocale()[0] or os.environ.get("LANG", "en")).lower()
        if language.startswith("en"):
            return "The customer needs help with a duplicate charge."
        if language.startswith("pt"):
            return "O cliente precisa de ajuda com uma cobrança duplicada."
        return "Customer support request"

    def _target(self, router: Any) -> str:
        if self.settings.model == "auto":
            decision = router.route(self._warmup_state(), {})
        else:
            decision = router.route(self._warmup_state(), {}, model=self.settings.model)
        return str(decision["model"])

    def plan(self) -> dict[str, Any]:
        router = self._ensure_router()
        target = self._target(router)
        plan: dict[str, Any] = {
            "provider": self.name,
            "model": target,
            "device": self.settings.device,
            "download_bytes": None,
            "estimated_seconds": None,
            "estimate_source": None,
        }

        try:
            hub = importlib.import_module("huggingface_hub")
            spec = router.models[target]
            repo = spec[0] if isinstance(spec, (tuple, list)) else spec
            subfolder = spec[1] if isinstance(spec, (tuple, list)) and len(spec) > 1 else None
            if os.path.exists(str(repo)):
                plan["download_bytes"] = 0
                plan["estimated_seconds"] = 0.0
                plan["estimate_source"] = "local_model"
                return plan

            api = hub.HfApi(token=getattr(router, "token", None))
            info = api.model_info(str(repo), files_metadata=True)
            siblings = []
            for sibling in info.siblings:
                filename = sibling.rfilename
                if subfolder and not filename.startswith(str(subfolder).rstrip("/") + "/"):
                    continue
                size = getattr(sibling, "size", None)
                if not isinstance(size, int) or size < 0:
                    continue
                cached = hub.try_to_load_from_cache(str(repo), filename)
                if isinstance(cached, str):
                    continue
                siblings.append((filename, size))

            remaining = sum(size for _, size in siblings)
            plan["download_bytes"] = remaining
            if remaining == 0:
                plan["estimated_seconds"] = 0.0
                plan["estimate_source"] = "huggingface_cache"
                return plan

            probe_file = max(siblings, key=lambda item: item[1])[0]
            url = hub.hf_hub_url(str(repo), probe_file)
            request = urllib.request.Request(
                url,
                headers={"Range": "bytes=0-1048575", "User-Agent": "decisors/0.1"},
            )
            started = time.perf_counter()
            timeout = min(self.settings.timeout_seconds, 15.0)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                sample = response.read(1024 * 1024)
            elapsed = time.perf_counter() - started
            if len(sample) >= 64 * 1024 and elapsed > 0:
                bytes_per_second = len(sample) / elapsed
                plan["estimated_seconds"] = round(remaining / bytes_per_second, 1)
                plan["estimate_source"] = "measured_1mib_probe"
        except Exception as exc:
            plan["planning_warning"] = (
                f"Could not estimate the model download before initialization: {type(exc).__name__}."
            )
        return plan

    def prepare(self) -> dict[str, Any]:
        router = self._ensure_router()
        start = time.perf_counter()
        try:
            target = self._target(router)
            router.load(target)
            warmup_questions = {
                "team": {
                    "type": "choice",
                    "instructions": "Which support area best matches this request?",
                    "criteria": {
                        "billing": "Charges and payments",
                        "other": "Anything else",
                    },
                },
                "duplicate_charge": {
                    "type": "noul",
                    "instructions": "Does the state describe a duplicate charge?",
                },
            }
            router.predict(self._warmup_state(), warmup_questions, model=target)
            self._loaded_for_init = target
        except Exception as exc:
            raise ProviderError(f"Could not prepare Laya model: {type(exc).__name__}.") from exc
        elapsed_ms = round((time.perf_counter() - start) * 1000)
        return {
            "provider": self.name,
            "model": target,
            "device": self.settings.device,
            "elapsed_ms": elapsed_ms,
            "warmup_ok": True,
            "note": "Model is loaded, warmed up, and ready in the persistent bridge.",
        }

    def evaluate(self, request: DecisionRequest) -> DecisionResult:
        router = self._ensure_router()
        try:
            if self.settings.model == "auto":
                raw = router.predict(request.state, request.questions)
            else:
                raw = router.predict(request.state, request.questions, model=self.settings.model)
        except Exception as exc:
            raise ProviderError(f"Laya evaluation failed: {type(exc).__name__}.") from exc
        result = dict(raw)
        result["provider"] = self.name
        return validate_result(request, result)

    def stop(self) -> None:
        if self._router is not None:
            with suppress(Exception):
                self._router.unload()
        self._router = None
        self._loaded_for_init = None
        gc.collect()
        try:
            torch = importlib.import_module("torch")
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def status(self) -> dict[str, Any]:
        loaded: list[str] = []
        resolved: str | None = None
        reason: str | None = None
        if self._router is not None:
            try:
                loaded = [str(name) for name in self._router.loaded]
            except Exception:
                loaded = []
            try:
                if self.settings.model == "auto":
                    decision = self._router.route(self._warmup_state(), {})
                else:
                    decision = self._router.route(
                        self._warmup_state(),
                        {},
                        model=self.settings.model,
                    )
                resolved = str(decision.get("model") or "") or None
                raw_reason = decision.get("reason")
                reason = raw_reason if isinstance(raw_reason, str) else None
            except Exception:
                resolved = loaded[-1] if loaded else None
        elif self.settings.model != "auto":
            resolved = self.settings.model
        return {
            "provider": self.name,
            "ready": self._router is not None,
            "loaded": loaded,
            "configured_model": self.settings.model,
            "resolved_model": resolved,
            "route_reason": reason,
            "model": resolved or (loaded[-1] if loaded else self.settings.model),
            "device": self.settings.device,
        }
