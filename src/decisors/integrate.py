"""Explicit integrations; package installation itself never mutates Pi config."""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from .errors import ConfigurationError


def install_pi_assets(root: Path | None = None) -> dict[str, Path]:
    base = root or Path.home() / ".pi" / "agent"
    resources = importlib.resources.files("decisors")
    targets = {
        "skill": (
            base / "skills" / "decisores-decisoes" / "SKILL.md",
            ("skills", "decisores-decisoes", "SKILL.md"),
        ),
        "prompt": (base / "prompts" / "juiz.md", ("prompts", "juiz.md")),
    }
    written: dict[str, Path] = {}
    for key, (target, parts) in targets.items():
        try:
            content = resources.joinpath("integrations", *parts).read_text(encoding="utf-8")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except OSError as exc:
            raise ConfigurationError(f"Could not install Pi asset at {target}.") from exc
        written[key] = target
    return written


def install_pi_extension(destination: Path | None = None) -> Path:
    target = destination or Path.home() / ".pi" / "agent" / "extensions" / "decisors" / "index.js"
    try:
        resource = importlib.resources.files("decisors").joinpath("integrations", "pi-extension.js")
        source = resource.read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, OSError) as exc:
        raise ConfigurationError("Bundled Pi extension could not be read.") from exc

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
    except OSError as exc:
        raise ConfigurationError(f"Could not install Pi extension at {target}.") from exc
    return target
