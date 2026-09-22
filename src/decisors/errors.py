"""Safe public errors for Decisors."""


class DecisorsError(Exception):
    """Base error whose message is safe to expose to a CLI or agent."""


class ConfigurationError(DecisorsError):
    """Configuration is missing or invalid."""


class ValidationError(DecisorsError):
    """A decision request or response failed validation."""


class ProviderError(DecisorsError):
    """A provider failed without leaking secrets or submitted state."""


class NotStartedError(DecisorsError):
    """The decision engine has not been started."""
