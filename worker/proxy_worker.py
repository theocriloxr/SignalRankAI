from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import select

from config import config
from db.models import ProxyNode
from db.session import get_session
from utils import proxy_manager
from utils.timeutils import now_utc_naive
from utils.async_runner import run_sync


logger = logging.getLogger(__name__)

_BINANCE_PING_URL = "https://api.binance.com/api/v3/ping"
_DEFAULT_PROVIDER_URL = "https://example.com/proxies"
_VALIDATION_TIMEOUT_S = 2.0


def _provider_url() -> str:
    return (
        (getattr(config, "PROXY_API_PROVIDER_URL", "") or "").strip()
        or (os.getenv("PROXY_API_PROVIDER_URL") or "").strip()
        or _DEFAULT_PROVIDER_URL
    )


def _normalize_proxy_url(value: str) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if "://" not in raw:
        raw = f"http://{raw}"
    return raw


def _extract_proxy_candidates(payload: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, str):
                n = _normalize_proxy_url(item)
                if n:
                    urls.append(n)
            elif isinstance(item, dict):
                raw = item.get("proxy_url") or item.get("url") or item.get("proxy")
                n = _normalize_proxy_url(str(raw or ""))
                if n:
                    urls.append(n)
    elif isinstance(payload, dict):
        items = payload.get("proxies") or payload.get("data") or payload.get("results") or []
        urls.extend(_extract_proxy_candidates(items))
    return sorted({u for u in urls if u})


async def fetch_proxy_candidates() -> list[str]:
    url = _provider_url()
    if not url:
        return []
    try:
        async with httpx.AsyncClient(timeout=max(2.0, _VALIDATION_TIMEOUT_S)) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning("[proxy_worker] provider_fetch_failed status=%s url=%s", resp.status_code, url)
                return []
            payload = resp.json()
        proxies = _extract_proxy_candidates(payload)
        logger.info("[proxy_worker] provider_fetch_ok count=%s", len(proxies))
        return proxies
    except Exception as exc:
        logger.warning("[proxy_worker] provider_fetch_error url=%s err=%s", url, exc)
        return []


async def validate_proxy(proxy_url: str) -> tuple[bool, float | None]:
    started = time.perf_counter()
    timeout = _VALIDATION_TIMEOUT_S
    try:
        async with httpx.AsyncClient(proxy=proxy_url, timeout=timeout) as client:
            resp = await asyncio.wait_for(
                client.get(_BINANCE_PING_URL),
                timeout=timeout,
            )
        if resp.status_code == 200:
            latency_ms = max(0.0, (time.perf_counter() - started) * 1000.0)
            return True, latency_ms
        return False, None
    except Exception:
        return False, None


async def _apply_proxy_result(
    *,
    proxy_url: str,
    is_valid: bool,
    latency_ms: float | None,
    checked_at: datetime,
) -> None:
    async with get_session() as session:
        existing = await session.scalar(
            select(ProxyNode).where(ProxyNode.proxy_url == proxy_url)
        )
        if existing is None:
            existing = ProxyNode(proxy_url=proxy_url)
            session.add(existing)

        existing.last_checked = checked_at
        if is_valid:
            existing.is_active = True
            existing.fail_count = 0
            existing.latency_ms = latency_ms
        else:
            existing.fail_count = int(existing.fail_count or 0) + 1
            existing.latency_ms = None
            if existing.fail_count > 3:
                existing.is_active = False
        await session.commit()


async def run_proxy_validation_cycle() -> dict[str, int]:
    proxy_candidates = await fetch_proxy_candidates()
    if not proxy_candidates:
        return {"fetched": 0, "validated_ok": 0, "validated_failed": 0}

    semaphore = asyncio.Semaphore(50)

    async def _validate_one(url: str) -> tuple[str, bool, float | None]:
        async with semaphore:
            ok, latency = await validate_proxy(url)
            return url, ok, latency

    checked_at = now_utc_naive()
    results = await asyncio.gather(
        *[_validate_one(url) for url in proxy_candidates],
        return_exceptions=False,
    )

    ok_count = 0
    failed_count = 0
    for proxy_url, is_valid, latency_ms in results:
        await _apply_proxy_result(
            proxy_url=proxy_url,
            is_valid=bool(is_valid),
            latency_ms=latency_ms,
            checked_at=checked_at,
        )
        if is_valid:
            ok_count += 1
        else:
            failed_count += 1

    logger.info(
        "[proxy_worker] validation_cycle_complete fetched=%s ok=%s failed=%s",
        len(proxy_candidates),
        ok_count,
        failed_count,
    )
    try:
        active_pool = await proxy_manager.refresh_active_proxy_pool()
        logger.info("[proxy_worker] active_proxy_pool_refreshed count=%s", len(active_pool))
    except Exception as exc:
        logger.warning("[proxy_worker] active_proxy_pool_refresh_failed err=%s", exc)
    return {
        "fetched": len(proxy_candidates),
        "validated_ok": ok_count,
        "validated_failed": failed_count,
    }


def proxy_validation_job() -> None:
    try:
        run_sync(run_proxy_validation_cycle(), timeout=None)
    except Exception as exc:
        logger.warning("[proxy_worker] scheduled_job_failed err=%s", exc)
