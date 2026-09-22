"""Explicit integrations; package installation itself never mutates Pi config."""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from .errors import ConfigurationError


def install_pi_assets(root: Path | None = None) -> dict[str, Path]:
    base = root or Path.home() / ".pi" / "agent"
    bundled = Path(__file__).parent / "integrations"
    targets = {
        "skill": base / "skills" / "decisores-decisoes" / "SKILL.md",
        "prompt": base / "prompts" / "juiz.md",
    }
    sources = {
        "skill": bundled / "skills" / "decisores-decisoes" / "SKILL.md",
        "prompt": bundled / "prompts" / "juiz.md",
    }
    written: dict[str, Path] = {}
    for key, target in targets.items():
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(sources[key].read_text(encoding="utf-8"), encoding="utf-8")
        except OSError as exc:
            raise ConfigurationError(f"Could not install Pi asset at {target}.") from exc
        written[key] = target
    return written


def install_pi_extension(destination: Path | None = None) -> Path:
    target = destination or Path.home() / ".pi" / "agent" / "extensions" / "decisors" / "index.js"
    try:
        resource = importlib.resources.files("decisors").joinpath("integrations/pi-extension.js")
        source = resource.read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, OSError) as exc:
        raise ConfigurationError("Bundled Pi extension could not be read.") from exc

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
    except OSError as exc:
        raise ConfigurationError(f"Could not install Pi extension at {target}.") from exc
    return target
