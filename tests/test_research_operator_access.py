"""Research diagnostics share server evidence and enforce operator authority."""
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException


@pytest.mark.asyncio
@pytest.mark.parametrize("tier", ["free", "basic", "pro", "vip", "elite", "unknown"])
async def test_web_research_diagnostics_refuse_customer_tiers(monkeypatch, tier):
    from web import platform_api
    async def forbidden_database(**kwargs):
        pytest.fail("unauthorized request reached the research database")
    monkeypatch.setattr(platform_api, "get_session", forbidden_database)
    with pytest.raises(HTTPException) as error:
        await platform_api.operator_research(user={"tier": tier, "telegram_user_id": 0})
    assert error.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("tier", ["OWNER", "ADMIN"])
async def test_web_and_telegram_use_the_same_canonical_snapshot(monkeypatch, tier):
    from web import platform_api
    from engine.adaptive import research_ledger
    from signalrank_telegram import adaptive_commands
    session = object()
    snapshot = {"families": [{"trial_family": "trend", "raw_trial_count": 7, "terminal_trial_count": 6}],
                "experiments": [{"experiment_id": "trial-fixture", "status": "FAILED", "result": {}}]}
    read = AsyncMock(return_value=snapshot)
    @asynccontextmanager
    async def sessions(**kwargs):
        yield session
    monkeypatch.setattr(platform_api, "get_session", sessions)
    monkeypatch.setattr(adaptive_commands, "get_session", sessions)
    monkeypatch.setattr(research_ledger, "research_snapshot", read)
    monkeypatch.setattr(adaptive_commands, "research_snapshot", read)
    monkeypatch.setattr(adaptive_commands, "_privileged_ids", lambda: {42})
    assert await platform_api.operator_research(asset=" btcusdt ", user={"tier": tier}) == snapshot
    reply = AsyncMock()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=42), effective_message=SimpleNamespace(reply_text=reply))
    await adaptive_commands.research_command(update, SimpleNamespace(args=["btcusdt"]))
    assert read.await_count == 2
    assert all(call.kwargs["asset"] == "BTCUSDT" for call in read.await_args_list)
    assert "7 trials, 6 terminal results" in reply.await_args.args[0]
    assert "FAILED" in reply.await_args.args[0]


@pytest.mark.asyncio
async def test_telegram_research_is_hidden_from_unprivileged_users(monkeypatch):
    from signalrank_telegram import adaptive_commands
    monkeypatch.setattr(adaptive_commands, "_privileged_ids", lambda: {42})
    read, reply = AsyncMock(), AsyncMock()
    monkeypatch.setattr(adaptive_commands, "research_snapshot", read)
    update = SimpleNamespace(effective_user=SimpleNamespace(id=41), effective_message=SimpleNamespace(reply_text=reply))
    await adaptive_commands.research_command(update, SimpleNamespace(args=[]))
    read.assert_not_awaited()
    reply.assert_not_awaited()
