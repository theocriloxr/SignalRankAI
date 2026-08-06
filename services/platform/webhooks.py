"""Signed, retryable and SSRF-hardened outbound webhook delivery."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import socket
import time
from datetime import datetime, timedelta
from typing import Any, Mapping
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from sqlalchemy import text

from db.session import get_session
from services.security import decrypt_secret

logger = logging.getLogger(__name__)


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(float(os.getenv(name, str(default)) or default)))
    except Exception:
        return max(minimum, default)


async def queue_user_webhook_event(
    session: Any,
    *,
    user_id: int,
    event_type: str,
    event_id: str,
    payload: Mapping[str, Any],
) -> int:
    """Queue one logical event for each subscribed user endpoint."""
    event_name = str(event_type).strip().lower()[:96]
    if not event_name:
        return 0
    payload_json = _json(dict(payload))
    result = await session.execute(
        text(
            "INSERT INTO webhook_deliveries("
            "webhook_delivery_id,webhook_endpoint_id,event_id,event_type,payload,idempotency_key"
            ") SELECT gen_random_uuid()::text,we.webhook_endpoint_id,:event_id,:event_type,CAST(:payload AS JSONB),"
            "(:event_id || ':' || we.webhook_endpoint_id) "
            "FROM webhook_endpoints we WHERE we.user_id=:uid AND we.active=TRUE "
            "AND (we.subscribed_events @> CAST(:event_match AS JSONB) OR we.subscribed_events @> '[\"*\"]'::jsonb) "
            "ON CONFLICT(webhook_endpoint_id,idempotency_key) DO NOTHING"
        ),
        {
            "uid": int(user_id),
            "event_id": str(event_id)[:64],
            "event_type": event_name,
            "payload": payload_json,
            "event_match": _json([event_name]),
        },
    )
    return int(result.rowcount or 0)


async def _resolve_public_host(hostname: str) -> set[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.run_in_executor(None, lambda: socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM))
    addresses = {str(info[4][0]) for info in infos if info and info[4]}
    if not addresses:
        raise ValueError("webhook_host_unresolved")
    for raw in addresses:
        ip = ipaddress.ip_address(raw)
        if any((ip.is_private, ip.is_loopback, ip.is_link_local, ip.is_multicast, ip.is_reserved, ip.is_unspecified)):
            raise ValueError("webhook_private_address_blocked")
    return addresses


async def validate_webhook_destination(url: str) -> str:
    parsed = urlparse(str(url).strip())
    environment = str(os.getenv("ENVIRONMENT") or os.getenv("RAILWAY_ENVIRONMENT_NAME") or "local").lower()
    local_ok = (
        environment not in {"staging", "production"}
        and parsed.scheme == "http"
        and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    )
    if not ((parsed.scheme == "https" and parsed.hostname) or local_ok):
        raise ValueError("webhook_https_required")
    if parsed.username or parsed.password:
        raise ValueError("webhook_userinfo_forbidden")
    if parsed.port and parsed.port not in {80, 443, 8443}:
        raise ValueError("webhook_port_forbidden")
    allowed_hosts = {value.strip().lower() for value in (os.getenv("WEBHOOK_ALLOWED_HOSTS") or "").split(",") if value.strip()}
    if allowed_hosts and str(parsed.hostname).lower() not in allowed_hosts:
        raise ValueError("webhook_host_not_allowlisted")
    if not local_ok:
        await _resolve_public_host(str(parsed.hostname))
    return parsed.geturl()


def webhook_signature(secret: str, timestamp: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), timestamp.encode("ascii") + b"." + body, hashlib.sha256).hexdigest()
    return "v1=" + digest


async def _claim_batch(limit: int) -> list[dict[str, Any]]:
    async with get_session(priority="background", label="webhook.claim") as session:
        rows = (
            await session.execute(
                text(
                    "SELECT wd.webhook_delivery_id,wd.webhook_endpoint_id,wd.event_id,wd.event_type,wd.payload,"
                    "wd.idempotency_key,wd.attempt_count,we.url,we.encrypted_secret "
                    "FROM webhook_deliveries wd JOIN webhook_endpoints we ON we.webhook_endpoint_id=wd.webhook_endpoint_id "
                    "WHERE we.active=TRUE AND wd.next_attempt_at<=NOW() "
                    "AND (wd.status IN ('pending','retry') OR (wd.status='delivering' AND wd.updated_at<NOW()-INTERVAL '5 minutes')) "
                    "ORDER BY wd.created_at FOR UPDATE OF wd SKIP LOCKED LIMIT :limit"
                ),
                {"limit": max(1, min(int(limit), 100))},
            )
        ).mappings().all()
        claimed: list[dict[str, Any]] = []
        for row in rows:
            await session.execute(
                text(
                    "UPDATE webhook_deliveries SET status='delivering',attempt_count=attempt_count+1,updated_at=NOW() "
                    "WHERE webhook_delivery_id=:delivery_id"
                ),
                {"delivery_id": row["webhook_delivery_id"]},
            )
            item = dict(row)
            item["attempt_count"] = int(item.get("attempt_count") or 0) + 1
            claimed.append(item)
        await session.commit()
    return claimed


async def _store_result(
    delivery_id: str,
    *,
    delivered: bool,
    status_code: int | None = None,
    response_excerpt: str | None = None,
    error: str | None = None,
    attempts: int = 1,
) -> None:
    max_attempts = _env_int("WEBHOOK_MAX_ATTEMPTS", 8)
    terminal = delivered or attempts >= max_attempts
    if delivered:
        status = "delivered"
        next_attempt = datetime.utcnow()
    elif terminal:
        status = "failed"
        next_attempt = datetime.utcnow()
    else:
        status = "retry"
        delay = min(3600, 2 ** min(attempts, 10) * 5)
        next_attempt = datetime.utcnow() + timedelta(seconds=delay)
    async with get_session(priority="background", label="webhook.result") as session:
        await session.execute(
            text(
                "UPDATE webhook_deliveries SET status=:status,next_attempt_at=:next_attempt,response_status=:status_code,"
                "response_excerpt=:excerpt,last_error=:error,delivered_at=CASE WHEN :delivered THEN NOW() ELSE delivered_at END,"
                "updated_at=NOW() WHERE webhook_delivery_id=:delivery_id"
            ),
            {
                "status": status,
                "next_attempt": next_attempt,
                "status_code": status_code,
                "excerpt": (response_excerpt or "")[:500] or None,
                "error": (error or "")[:500] or None,
                "delivered": bool(delivered),
                "delivery_id": delivery_id,
            },
        )
        await session.commit()


async def _deliver_one(client: httpx.AsyncClient, item: Mapping[str, Any]) -> bool:
    delivery_id = str(item["webhook_delivery_id"])
    attempts = int(item.get("attempt_count") or 1)
    try:
        url = await validate_webhook_destination(str(item["url"]))
        secret = decrypt_secret(str(item.get("encrypted_secret") or ""))
        if not secret:
            raise ValueError("webhook_secret_unavailable")
        envelope = {
            "id": str(item["event_id"]),
            "type": str(item["event_type"]),
            "created_at": datetime.utcnow().isoformat() + "Z",
            "data": item.get("payload") or {},
        }
        body = _json(envelope).encode("utf-8")
        timestamp = str(int(time.time()))
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "SignalRankAI-Webhooks/1.0",
            "X-SignalRank-Event": str(item["event_type"]),
            "X-SignalRank-Delivery": delivery_id,
            "X-SignalRank-Timestamp": timestamp,
            "X-SignalRank-Signature": webhook_signature(secret, timestamp, body),
            "Idempotency-Key": str(item["idempotency_key"]),
        }
        response = await client.post(url, content=body, headers=headers)
        excerpt = response.text[:500] if response.text else None
        if 200 <= response.status_code < 300:
            await _store_result(delivery_id, delivered=True, status_code=response.status_code, response_excerpt=excerpt, attempts=attempts)
            return True
        await _store_result(
            delivery_id,
            delivered=False,
            status_code=response.status_code,
            response_excerpt=excerpt,
            error=f"http_{response.status_code}",
            attempts=attempts,
        )
    except Exception as exc:  # noqa: BLE001
        await _store_result(delivery_id, delivered=False, error=f"{type(exc).__name__}:{exc}", attempts=attempts)
    return False


async def deliver_webhook_batch(limit: int | None = None) -> dict[str, int]:
    items = await _claim_batch(limit or _env_int("WEBHOOK_BATCH_SIZE", 25))
    if not items:
        return {"claimed": 0, "delivered": 0, "failed_or_retried": 0}
    timeout = httpx.Timeout(float(os.getenv("WEBHOOK_TIMEOUT_SECONDS", "10")), connect=5.0)
    concurrency = _env_int("WEBHOOK_CONCURRENCY", 5)
    semaphore = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        async def run(item: Mapping[str, Any]) -> bool:
            async with semaphore:
                return await _deliver_one(client, item)
        results = await asyncio.gather(*(run(item) for item in items), return_exceptions=False)
    delivered = sum(bool(value) for value in results)
    return {"claimed": len(items), "delivered": delivered, "failed_or_retried": len(items) - delivered}


__all__ = [
    "deliver_webhook_batch",
    "queue_user_webhook_event",
    "validate_webhook_destination",
    "webhook_signature",
]
