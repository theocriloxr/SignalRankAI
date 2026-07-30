"""Classify command failures without masking SQL defects as DB pressure."""
from __future__ import annotations

from typing import Literal

CommandErrorClass = Literal["db_pressure", "db_query", "other"]


def classify_command_exception(exc: BaseException) -> CommandErrorClass:
    """Return a user-facing failure class for Telegram command handlers.

    Programming/data/integrity errors are deterministic code or schema defects;
    retrying them will not relieve connection pressure. Operational, interface,
    pool-timeout and connection-invalidated errors are transient DB pressure.
    """
    try:
        from sqlalchemy.exc import (
            DBAPIError,
            DataError,
            IntegrityError,
            InterfaceError,
            OperationalError,
            ProgrammingError,
            StatementError,
            TimeoutError as SQLAlchemyTimeoutError,
        )

        if isinstance(exc, (ProgrammingError, DataError, IntegrityError)):
            return "db_query"
        # StatementError can wrap a bind/serialization/programming defect. Check
        # the original exception text before treating a generic wrapper as other.
        if isinstance(exc, StatementError):
            original = getattr(exc, "orig", None)
            original_text = str(original or exc).lower()
            if any(
                marker in original_text
                for marker in (
                    "ambiguousparametererror",
                    "could not determine data type",
                    "inconsistent types deduced",
                    "undefinedcolumn",
                    "undefinedtable",
                    "syntax error",
                    "not json serializable",
                )
            ):
                return "db_query"
        if isinstance(exc, SQLAlchemyTimeoutError):
            return "db_pressure"
        if isinstance(exc, (OperationalError, InterfaceError)):
            return "db_pressure"
        if isinstance(exc, DBAPIError) and bool(getattr(exc, "connection_invalidated", False)):
            return "db_pressure"
    except Exception:
        pass

    message = str(exc).lower()
    query_markers = (
        "ambiguousparametererror",
        "could not determine data type of parameter",
        "inconsistent types deduced for parameter",
        "programmingerror",
        "undefinedcolumn",
        "undefinedtable",
        "syntax error at or near",
        "not json serializable",
    )
    if any(marker in message for marker in query_markers):
        return "db_query"

    pressure_markers = (
        "connection refused",
        "could not connect",
        "no route to host",
        "connection pool",
        "queuepool limit",
        "too many clients already",
        "toomanyconnectionserror",
        "remaining connection slots are reserved",
        "cannotconnectnowerror",
        "connectiondoesnotexisterror",
        "connection was closed",
        "connection is closed",
        "server closed the connection unexpectedly",
        "timeout acquiring database session",
        "pool timeout",
        "could not translate host",
        "password authentication failed",
    )
    if any(marker in message for marker in pressure_markers):
        return "db_pressure"
    return "other"


__all__ = ["CommandErrorClass", "classify_command_exception"]
