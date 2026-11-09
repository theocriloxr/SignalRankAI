"""Fixes from the 9 Nov 2026 production log snapshot (signalrank-ops 07:45 UTC)."""
from __future__ import annotations

import asyncio
import os
from datetime import timedelta

import pytest

_PG_DSN = os.getenv("SIGNALRANK_TEST_PG_DSN", "")


@pytest.mark.skipif(not _PG_DSN, reason="set SIGNALRANK_TEST_PG_DSN to an owned scratch PostgreSQL at head")
def test_one_slow_section_no_longer_fails_the_weekly_review(monkeypatch):
    """analytics 07:02:46: '[continuous_improvement] scheduled review failed' on an asyncpg TimeoutError."""
    from db.session import _normalize_database_url

    monkeypatch.setenv("DATABASE_URL", _normalize_database_url(_PG_DSN, async_driver=True))
    from services import codex_governance as cg

    real = cg._guarded_execute

    async def slow_decision_log(session, unavailable, statement, params=None):
        if "FROM decision_log" in str(getattr(statement, "text", statement)):
            from sqlalchemy import text

            # Simulate the production timeout inside the section's savepoint.
            statement = text("SELECT pg_sleep(3)")
            await session.execute(text("SET LOCAL statement_timeout = '200ms'"))
        return await real(session, unavailable, statement, params)

    monkeypatch.setattr(cg, "_guarded_execute", slow_decision_log)

    async def run():
        from db.session import dispose_engine_for_event_loop

        try:
            return await cg.collect_codex_governance_context(days=7, limit=5)
        finally:
            await dispose_engine_for_event_loop()

    context = asyncio.run(run())
    assert context["ok"] is True
    # The two decision_log sections (latest decisions, AI provider performance) timed out.
    assert len(context["unavailable_sections"]) == 2
    assert all(s.endswith(":DBAPIError") for s in context["unavailable_sections"])
    assert "summary" in context  # the other sections still ran after the failed one


def test_scanner_server_action_requests_are_answered_by_the_proxy():
    """web 8 Nov: 'Failed to find Server Action' x24 in one second; the app has no Server Actions."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "frontend" / "src"
    proxy = (root / "proxy.ts").read_text("utf-8")
    assert 'request.headers.has("next-action")' in proxy and "status: 404" in proxy
    assert not any("use server" in p.read_text("utf-8", errors="ignore")
                   for p in root.rglob("*.ts*")), "a real Server Action now exists; revisit the proxy rule"


@pytest.mark.skipif(not _PG_DSN, reason="set SIGNALRANK_TEST_PG_DSN to an owned scratch PostgreSQL at head")
def test_signal_drought_alert_names_the_dominant_rejection(monkeypatch):
    """9 Nov: no signal all day, every FX candidate rejected by one gate, and no owner alert."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from db.session import _normalize_database_url
    from observability import owner_alerts

    url = _normalize_database_url(_PG_DSN, async_driver=True)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("OWNER_ALERT_SIGNAL_DROUGHT_HOURS", "1")

    async def scenario():
        from db.session import dispose_engine_for_event_loop

        engine = create_async_engine(url)
        try:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM decision_log WHERE asset='DROUGHTFX'"))
                for value in ("4.88", "4.76", "4.91"):
                    await conn.execute(text(
                        "INSERT INTO decision_log(asset, timeframe, decision, reason, meta, created_at) VALUES "
                        "('DROUGHTFX','5m','skipped',:r,'{}', NOW() AT TIME ZONE 'utc')"),
                        {"r": f"production_quality:quality_rr {value} > 4.50 (fx)"})
                newest = (await conn.execute(text("SELECT MAX(created_at) FROM signals"))).scalar()
            finding = await owner_alerts.signal_drought_finding()
            return newest, finding
        finally:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM decision_log WHERE asset='DROUGHTFX'"))
            await engine.dispose()
            await dispose_engine_for_event_loop()

    newest, finding = asyncio.run(scenario())
    if finding is None:
        pytest.skip(f"the scratch database has a signal newer than 1 h ({newest})")
    top = finding["top_reasons"][0]
    assert top["reason"] == "production_quality:quality_rr N > N (fx)" and top["count"] >= 3
    sent = []
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:test")
    monkeypatch.setattr(owner_alerts, "_owner_ids", lambda: [42])
    monkeypatch.setattr("core.health_notifications.claim_health_notification", lambda *a, **k: (True, None))
    owner_alerts.signal_drought_alert(finding, post=lambda token, chat, text: sent.append(text) or True)
    assert sent and "Signal drought" in sent[0] and "quality_rr N > N (fx)" in sent[0]


def test_scorecard_needs_99_percent_evidence_before_moving_a_score():
    """~1,180 cells tested at 95% leave ~59 'decisive' by chance; decisions now use 99%."""
    from services.strategy_scorecard import _Cell, adjustment_for_cell, summarise_cell

    def cell(wins, losses, win_r=2.0):
        c = _Cell()
        c.wins, c.losses, c.sum_win_r, c.sum_r = wins, losses, wins * win_r, wins * win_r - losses
        return summarise_cell(c)

    borderline = cell(30, 30)  # 50% vs 33% break-even: significant at 95%, not at 99%
    assert borderline["win_lower_95"] > borderline["breakeven_win_rate"] + 0.02
    assert adjustment_for_cell(borderline) == (1.0, "undecided")
    assert adjustment_for_cell(cell(70, 70))[1] == "supported_edge"


def test_live_price_skips_unentitled_providers_and_reuses_a_recent_quote(monkeypatch):
    """worker 9 Nov: 'All providers failed for JPM reasons=fmp:provider_timeout,...,polygon:...:403,yahoo:...:429'."""
    import time as _time

    from data import get_live_price as glp

    calls = []
    good = {"on": True}

    async def fake(provider, symbol, timeout):
        calls.append(provider)
        if provider == "fmp" and good["on"]:
            now = _time.time()
            return glp._typed_quote(symbol=symbol, provider="fmp", price=342.5, source_timestamp=now,
                                    started=_time.perf_counter(), received_at=now)
        if provider == "polygon":
            return glp._typed_failure(symbol, provider, "invalid_response:403")
        return glp._typed_failure(symbol, provider, "provider_timeout")

    monkeypatch.setattr(glp, "_fetch_structured_quote", fake)
    monkeypatch.setattr(glp, "_get_providers_for_asset", lambda s: ["polygon", "fmp", "yahoo"])
    monkeypatch.setattr(glp, "_FORBIDDEN_PROVIDERS", {})
    monkeypatch.setattr(glp, "_LAST_GOOD", {})
    first = asyncio.run(glp.get_live_price_result("JPM"))
    assert first.price == 342.5 and calls == ["polygon", "fmp"]
    good["on"] = False
    calls.clear()
    second = asyncio.run(glp.get_live_price_result("JPM"))
    assert "polygon" not in calls  # 403 -> skipped for the cooldown
    assert getattr(second, "price", None) == 342.5  # recent quote reused for analysis paths
    fresh_required = asyncio.run(glp.get_live_price_result("JPM", require_delivery_freshness=True))
    assert not hasattr(fresh_required, "price") or fresh_required.__class__.__name__ == "LivePriceFailure"


def test_deferred_review_is_retried_quietly():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "services" / "continuous_improvement" / "scheduler.py").read_text()
    assert '"AnalyticsWorkDeferred"' in source and "CONTINUOUS_IMPROVEMENT_DEFER_RETRY_SECONDS" in source


def test_freshness_label_scales_with_the_chart():
    """9 Nov JPM 1h card: 'Freshness: Aging' with 'Age: 0m'."""
    from signalrank_telegram.tier_signal_formatter import _freshness_text

    assert _freshness_text({"timeframe": "1h", "data_age_seconds": 960}).startswith("Fresh")
    assert _freshness_text({"timeframe": "5m", "data_age_seconds": 960}).startswith("Aging")
