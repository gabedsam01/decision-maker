"""Shared Jev transport for TypeSafe and OpenRouter."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from ..config import Settings
from ..domain import DecisionRequest, DecisionResult, validate_result
from ..errors import ConfigurationError, ProviderError

Transport = Callable[[str, dict[str, str], bytes, float], dict[str, Any]]


def urllib_transport(
    url: str,
    headers: dict[str, str],
    body: bytes,
    timeout_seconds: float,
) -> dict[str, Any]:
    if not url.startswith("https://"):
        raise ProviderError("Remote decision endpoint must be https.")
    request = urllib.request.Request(url=url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise ProviderError(f"Remote decision request failed with HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise ProviderError("Remote decision provider is unreachable.") from exc
    except TimeoutError as exc:
        raise ProviderError("Remote decision request timed out.") from exc

    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderError("Remote decision provider returned invalid JSON.") from exc
    if not isinstance(value, dict):
        raise ProviderError("Remote decision provider returned an unexpected response.")
    return value


class RemoteJevProvider:
    name = "remote"
    endpoint = ""
    key_env = ""
    default_model = ""

    def __init__(self, settings: Settings, *, transport: Transport | None = None) -> None:
        self.settings = settings
        self.transport = transport or urllib_transport
        self.requests_started = 0
        self.requests_succeeded = 0
        self.input_tokens = 0
        self.output_tokens = 0

    @property
    def model(self) -> str:
        return self.default_model if self.settings.model == "auto" else self.settings.model

    def _key(self) -> str:
        from ..config import get_credential

        key = get_credential(self.name)
        if not key:
            raise ConfigurationError(
                f"{self.key_env} is not set. Configure it in the environment "
                f"or ~/.pi/agent/auth.json before using {self.name}."
            )
        return key

    def _headers(self, key: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "decisors/0.1",
        }

    def plan(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "model": self.model,
            "remote": True,
            "download_bytes": 0,
            "estimated_seconds": 0.0,
            "key_source": self.key_env,
        }

    def prepare(self) -> dict[str, Any]:
        self._key()
        return {
            "provider": self.name,
            "model": self.model,
            "ready": True,
            "key_source": self.key_env,
            "note": "Credentials were detected locally; no billable request was sent.",
        }

    def evaluate(self, request: DecisionRequest) -> DecisionResult:
        if self.requests_started >= self.settings.max_requests_per_session:
            raise ProviderError(
                f"Remote request limit reached ({self.settings.max_requests_per_session} per session)."
            )
        key = self._key()
        body = json.dumps(
            {"model": self.model, **request.to_wire()},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

        self.requests_started += 1
        start = time.perf_counter()
        raw = self.transport(
            self.endpoint,
            self._headers(key),
            body,
            self.settings.timeout_seconds,
        )
        result = validate_result(request, raw)

        self.requests_succeeded += 1
        usage = result.get("usage", {})
        if isinstance(usage, dict):
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            if isinstance(input_tokens, int) and input_tokens >= 0:
                self.input_tokens += input_tokens
            if isinstance(output_tokens, int) and output_tokens >= 0:
                self.output_tokens += output_tokens
        result["provider"] = self.name
        result["elapsed_ms"] = round((time.perf_counter() - start) * 1000)
        return result

    def stop(self) -> None:
        return None

    def status(self) -> dict[str, Any]:
        from ..config import get_credential

        return {
            "provider": self.name,
            # Same source as _key(): env OR auth store. Env-only reads lie when the key lives in a file.
            "ready": bool(get_credential(self.name)),
            "configured_model": self.settings.model,
            "resolved_model": self.model,
            "model": self.model,
            "key_source": self.key_env,
            "usage": {
                "requests_started": self.requests_started,
                "requests_succeeded": self.requests_succeeded,
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
            },
        }
