"""Database package bootstrap guards.

The staging incident exposed a persistence-boundary bug where non-finite Python
floats (NaN/Infinity) could reach PostgreSQL JSON/JSONB values.  SQLAlchemy's
async engine accepts a JSON serializer, so install one centrally before
``db.session`` imports ``create_async_engine``.  This keeps every async JSON
write RFC-compatible without requiring each repository call site to remember to
sanitize its own payload.
"""
from __future__ import annotations

import json
from typing import Any

import sqlalchemy.ext.asyncio as _sa_asyncio

from utils.json_safety import strict_json_safe


_ORIGINAL_CREATE_ASYNC_ENGINE = _sa_asyncio.create_async_engine


def _strict_json_serializer(value: Any) -> str:
    return json.dumps(
        strict_json_safe(value),
        allow_nan=False,
        separators=(",", ":"),
        default=str,
    )


def _create_async_engine_with_json_guard(*args: Any, **kwargs: Any):
    kwargs.setdefault("json_serializer", _strict_json_serializer)
    return _ORIGINAL_CREATE_ASYNC_ENGINE(*args, **kwargs)


if not getattr(_sa_asyncio.create_async_engine, "__signalrank_json_guard__", False):
    _create_async_engine_with_json_guard.__signalrank_json_guard__ = True
    _sa_asyncio.create_async_engine = _create_async_engine_with_json_guard
