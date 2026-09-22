"""Jev through TypeSafe's official System One API."""

from .remote import RemoteJevProvider


class TypeSafeProvider(RemoteJevProvider):
    name = "typesafe"
    endpoint = "https://api.typesafe.ai/v1/systemone"
    key_env = "TYPESAFE_API_KEY"
    default_model = "jev-latest"
