from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
import traceback
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CachedCommandResponse:
    value: Any
    age_seconds: float


@dataclass(frozen=True)
class _CacheEntry:
    value: Any
    created_at: float
    expires_at: float


class CommandResponseCache:
    """Thread-safe, bounded TTL cache for fail-open command responses."""

    def __init__(
        self,
        *,
        max_entries: int = 256,
        ttl_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_entries = max(1, int(max_entries))
        self.ttl_seconds = max(0.01, float(ttl_seconds))
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: OrderedDict[str, _CacheEntry] = OrderedDict()

    def _purge_expired(self, now: float) -> None:
        expired = [key for key, entry in self._entries.items() if entry.expires_at <= now]
        for key in expired:
            self._entries.pop(key, None)

    def set(self, key: str, value: Any, *, ttl_seconds: float | None = None) -> None:
        now = self._clock()
        ttl = self.ttl_seconds if ttl_seconds is None else max(0.01, float(ttl_seconds))
        normalized = str(key)
        with self._lock:
            self._purge_expired(now)
            self._entries.pop(normalized, None)
            self._entries[normalized] = _CacheEntry(value, now, now + ttl)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def get(self, key: str) -> CachedCommandResponse | None:
        now = self._clock()
        normalized = str(key)
        with self._lock:
            self._purge_expired(now)
            entry = self._entries.get(normalized)
            if entry is None:
                return None
            self._entries.move_to_end(normalized)
            return CachedCommandResponse(
                value=entry.value,
                age_seconds=max(0.0, now - entry.created_at),
            )

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        now = self._clock()
        with self._lock:
            self._purge_expired(now)
            return len(self._entries)


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(float(os.getenv(name, str(default)) or default)))
    except Exception:
        return default


def _env_float(name: str, default: float, minimum: float = 0.01) -> float:
    try:
        return max(minimum, float(os.getenv(name, str(default)) or default))
    except Exception:
        return default


command_response_cache = CommandResponseCache(
    max_entries=_env_int("COMMAND_RESPONSE_CACHE_MAX_ENTRIES", 256),
    ttl_seconds=_env_float("COMMAND_RESPONSE_CACHE_TTL_SECONDS", 60.0),
)


async def acknowledge_command(update: Any, context: Any, *, timeout_s: float = 0.20) -> bool:
    """Best-effort acknowledgement performed before audit or database work."""
    try:
        query = getattr(update, "callback_query", None)
        if query is not None and callable(getattr(query, "answer", None)):
            await asyncio.wait_for(query.answer(), timeout=max(0.01, float(timeout_s)))
            return True

        chat = getattr(update, "effective_chat", None)
        chat_id = getattr(chat, "id", None)
        bot = getattr(context, "bot", None)
        send_chat_action = getattr(bot, "send_chat_action", None)
        if chat_id is not None and callable(send_chat_action):
            await asyncio.wait_for(
                send_chat_action(chat_id=int(chat_id), action="typing"),
                timeout=max(0.01, float(timeout_s)),
            )
            return True
    except Exception:
        logger.debug("command acknowledgement skipped", exc_info=True)
    return False


def schedule_background_task(awaitable: Awaitable[Any], *, name: str) -> asyncio.Task[Any]:
    """Schedule best-effort work and always consume/log its exception."""
    task = asyncio.create_task(awaitable, name=name)

    def _completed(done: asyncio.Task[Any]) -> None:
        try:
            done.result()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.debug("background command task failed name=%s", name, exc_info=True)

    task.add_done_callback(_completed)
    return task


def safe_command_error(action: str, exc: BaseException) -> str:
    """Log full command failure details and return a safe, actionable reply.

    Raw provider, database, and credential-bearing exception messages must not
    be copied into Telegram. The short reference lets operators correlate the
    user report with the full server-side traceback.
    """
    reference = f"CMD-{uuid.uuid4().hex[:8].upper()}"
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        guidance = "The request timed out. Please retry in a moment."
    elif isinstance(exc, PermissionError):
        guidance = "The operation was denied. Check your account access or contact support."
    elif isinstance(exc, (ConnectionError, OSError)):
        guidance = "A required service is temporarily unavailable. Please retry shortly."
    elif isinstance(exc, ValueError):
        guidance = "The supplied value could not be processed. Check the command format and retry."
    else:
        guidance = "The request could not be completed. Please retry or send this reference to /support."
    logger.error(
        "command failure reference=%s action=%s error_type=%s traceback=%s",
        reference,
        str(action),
        type(exc).__name__,
        " | ".join(line.strip() for line in traceback.format_tb(exc.__traceback__))[:2000] or "unavailable",
    )
    return f"❌ {str(action).strip()}\n{guidance}\nReference: {reference}"
