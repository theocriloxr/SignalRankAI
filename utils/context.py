import contextvars
import uuid
from typing import Optional

# Context variable to hold the current correlation ID
_correlation_id_ctx_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("correlation_id", default=None)


def set_correlation_id(correlation_id: str) -> contextvars.Token:
    """Set the correlation ID for the current context."""
    return _correlation_id_ctx_var.set(correlation_id)


def get_correlation_id() -> Optional[str]:
    """Get the correlation ID for the current context."""
    return _correlation_id_ctx_var.get()


def generate_correlation_id() -> str:
    """Generate a new unique correlation ID."""
    return str(uuid.uuid4())


def reset_correlation_id(token: contextvars.Token) -> None:
    """Reset the correlation ID to its previous value."""
    _correlation_id_ctx_var.reset(token)
