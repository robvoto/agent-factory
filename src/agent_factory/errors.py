"""Domain errors for Agent Factory."""


class AgentFactoryError(Exception):
    """Base error for expected Agent Factory failures."""


class ManifestValidationError(AgentFactoryError):
    """Raised when an agent manifest is structurally invalid."""


class DuplicateAliasError(AgentFactoryError):
    """Raised when two configured agents claim the same alias."""


class UnknownToolError(AgentFactoryError):
    """Raised when a manifest asks for a tool that is not allowed."""


class AgentNotFoundError(AgentFactoryError):
    """Raised when routing cannot find a matching agent."""


class RouteError(AgentFactoryError):
    """Raised when a command cannot be parsed as an agent route."""
