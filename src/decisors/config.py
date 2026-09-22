"""XDG configuration with no persisted API secrets."""

from __future__ import annotations

import json
import os
import tempfile
import tomllib
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from .errors import ConfigurationError

PROVIDERS = {"laya", "typesafe", "openrouter"}


def get_credential(name: str) -> str:
    env_name = f"{name.upper()}_API_KEY"
    if val := os.environ.get(env_name, "").strip():
        return val
    auth_file = Path.home() / ".pi" / "agent" / "auth.json"
    if auth_file.is_file():
        try:
            data = json.loads(auth_file.read_text(encoding="utf-8"))
            entry = data.get(name) or data.get(name.lower())
            if isinstance(entry, dict):
                key = str(entry.get("key") or entry.get("apiKey") or entry.get("token") or "").strip()
                if key:
                    return key
            elif isinstance(entry, str) and entry.strip():
                return entry.strip()
        except Exception:
            pass
    return ""


@dataclass(frozen=True, slots=True)
class Settings:
    provider: str = "laya"
    model: str = "auto"
    device: str = "auto"
    confidence_threshold: float = 0.60
    max_loaded: int = 1
    timeout_seconds: float = 15.0
    max_requests_per_session: int = 20
    initialized: bool = False

    def validated(self) -> Settings:
        if self.provider not in PROVIDERS:
            raise ConfigurationError(
                f"Unknown provider {self.provider!r}; choose one of {sorted(PROVIDERS)}."
            )
        if not self.model.strip():
            raise ConfigurationError("model cannot be empty.")
        if self.device not in {"auto", "cpu", "cuda", "mps"}:
            raise ConfigurationError("device must be auto, cpu, cuda, or mps.")
        if not 0.0 <= self.confidence_threshold <= 1.0:
            raise ConfigurationError("confidence_threshold must be between 0 and 1.")
        if self.max_loaded < 1:
            raise ConfigurationError("max_loaded must be at least 1.")
        if self.timeout_seconds <= 0:
            raise ConfigurationError("timeout_seconds must be positive.")
        if self.max_requests_per_session < 1:
            raise ConfigurationError("max_requests_per_session must be at least 1.")
        return self


class ConfigStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_config_path()

    def load(self) -> Settings:
        if not self.path.exists():
            return apply_environment(Settings()).validated()
        try:
            data = tomllib.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ConfigurationError(f"Could not read config at {self.path}.") from exc
        raw = data.get("decisors", data)
        if not isinstance(raw, dict):
            raise ConfigurationError("Config root must be a TOML table.")
        known = {key: value for key, value in raw.items() if key in asdict(Settings())}
        try:
            settings = Settings(**known)
        except TypeError as exc:
            raise ConfigurationError("Config contains invalid fields.") from exc
        return apply_environment(settings).validated()

    def save(self, settings: Settings) -> None:
        settings = settings.validated()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = _to_toml(settings)
        try:
            fd, temp_name = tempfile.mkstemp(prefix=".decisors-", dir=self.path.parent, text=True)
            temp_path = Path(temp_name)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_path, 0o600)
            os.replace(temp_path, self.path)
        except OSError as exc:
            raise ConfigurationError(f"Could not write config at {self.path}.") from exc

    def update(self, **changes: Any) -> Settings:
        current = self.load()
        allowed = set(asdict(current))
        unknown = sorted(set(changes) - allowed)
        if unknown:
            raise ConfigurationError(f"Unknown config field(s): {', '.join(unknown)}.")
        updated = replace(current, **changes).validated()
        self.save(updated)
        return updated


def default_config_path() -> Path:
    explicit = os.environ.get("DECISORS_CONFIG")
    if explicit:
        return Path(explicit).expanduser()
    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home).expanduser() if config_home else Path.home() / ".config"
    return base / "decisors" / "config.toml"


def apply_environment(settings: Settings) -> Settings:
    changes: dict[str, Any] = {}
    if value := os.environ.get("DECISORS_PROVIDER"):
        changes["provider"] = value.strip().lower()
    if value := os.environ.get("DECISORS_MODEL"):
        changes["model"] = value.strip()
    if value := os.environ.get("DECISORS_DEVICE"):
        changes["device"] = value.strip().lower()
    return replace(settings, **changes)


def _to_toml(settings: Settings) -> str:
    values = asdict(settings)
    lines = ["[decisors]"]
    for key, value in values.items():
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        elif isinstance(value, str):
            rendered = '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
        else:
            rendered = str(value)
        lines.append(f"{key} = {rendered}")
    return "\n".join(lines) + "\n"
