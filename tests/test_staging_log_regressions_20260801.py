from __future__ import annotations

import logging
from pathlib import Path

import httpx
import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_explicit_shadow_tracker_flag_is_not_gated_by_analytics_owner() -> None:
    source = (ROOT / "worker" / "worker.py").read_text(encoding="utf-8")
    block = source.split("# Start shadow outcome tracker", 1)[1].split(
        "# Start market monitor", 1
    )[0]
    assert "SHADOW_OUTCOME_TRACKER_ENABLED" in block
    assert "_analytics_work_allowed_in_worker()" not in block


def test_optional_managed_asset_lookup_cannot_starve_critical_db_lane() -> None:
    source = (ROOT / "engine" / "core.py").read_text(encoding="utf-8")
    block = source.split("async def _fetch_managed():", 1)[1].split(
        "_discovered_assets", 1
    )[0]
    assert 'priority="background"' in block
    assert 'label="engine.managed_assets"' in block
    assert "ENGINE_MANAGED_ASSETS_TIMEOUT_SECONDS" in block


@pytest.mark.asyncio
async def test_finnhub_http_error_log_never_contains_api_key(monkeypatch, caplog) -> None:
    from services import economic_calendar

    secret = "secret-finnhub-token"
    monkeypatch.setenv("FINNHUB_API_KEY", secret)

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, url, params=None):
            request = httpx.Request("GET", url, params=params)
            return httpx.Response(403, request=request)

    monkeypatch.setattr(economic_calendar.httpx, "AsyncClient", lambda **_kwargs: _Client())
    caplog.set_level(logging.WARNING)
    result = await economic_calendar._fetch_finnhub(
        economic_calendar.datetime.now(economic_calendar.timezone.utc),
        economic_calendar.datetime.now(economic_calendar.timezone.utc),
    )

    assert result == []
    assert secret not in caplog.text
    assert "status=403" in caplog.text


def test_staging_profile_uses_effective_pool_and_current_version() -> None:
    profile = (
        ROOT / "SignalRankAI_v1.3.3_Railway_Staging_Certification.env.example"
    ).read_text(encoding="utf-8")
    assert "APP_VERSION=1.3.3" in profile
    assert "DB_POOL_SIZE=2" in profile
    assert "DB_MAX_OVERFLOW=0" in profile
