"""Jev through OpenRouter's Decisions API (not Chat Completions)."""

from .remote import RemoteJevProvider


class OpenRouterProvider(RemoteJevProvider):
    name = "openrouter"
    endpoint = "https://openrouter.ai/api/alpha/decisions"
    key_env = "OPENROUTER_API_KEY"
    default_model = "typesafe/jev-1.13"

    def _headers(self, key: str) -> dict[str, str]:
        headers = super()._headers(key)
        headers["X-OpenRouter-Title"] = "decisors"
        return headers
