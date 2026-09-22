"""Provider protocol shared by local and remote decision engines."""

from __future__ import annotations

from typing import Any, Protocol

from ..domain import DecisionRequest, DecisionResult


class DecisionProvider(Protocol):
    name: str

    def plan(self) -> dict[str, Any]:
        """Describe preparation/download work without loading the model."""
        ...

    def prepare(self) -> dict[str, Any]:
        """Prepare the provider without enabling agent calls."""
        ...

    def evaluate(self, request: DecisionRequest) -> DecisionResult:
        """Evaluate one normalized request."""
        ...

    def stop(self) -> None:
        """Release provider resources."""
        ...

    def status(self) -> dict[str, Any]:
        """Return safe provider status."""
        ...
