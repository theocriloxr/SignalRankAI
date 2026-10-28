"""CX-CHAN-01 / CX-TG-01: Telegram paths for the October web workspace features.

Each Telegram path must read or write the same store, with the same plan and
operator rules, as its web counterpart; owner mutations stay web-only.
Regressions covered: Telegram /feedback held ratings in process memory and only
flushed on every tenth rating of one signal; /apikey read only legacy v1 tokens,
so keys created in the web Developer view never appeared; /status showed daily
limits (Premium 20, VIP unlimited) that the delivery gate does not enforce.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


class _Message:
    def __init__(self) -> None:
        self.replies: list[str] = []

    async def reply_text(self, text: str, **_kwargs) -> None:
        self.replies.append(text)


def _update(user_id: int = 4242, username: str = "parity_user") -> SimpleNamespace:
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id, username=username),
        message=_Message(),
        callback_query=None,
    )


class _Session:
    def __init__(self, results: list | None = None) -> None:
        self.results = list(results or [])
        self.executed: list[str] = []
        self.committed = 0
        self.rolled_back = 0

    async def execute(self, statement, params=None):
        self.executed.append(str(statement))
        rows = self.results.pop(0) if self.results else []
        result = MagicMock()
        result.mappings.return_value.all.return_value = rows
        result.mappings.return_value.first.return_value = rows[0] if rows else None
        result.scalar_one_or_none.return_value = rows[0] if rows else None
        return result

    async def commit(self) -> None:
        self.committed += 1

    async def rollback(self) -> None:
        self.rolled_back += 1


def _session_factory(session: _Session):
    class _CM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc):
            return False

    return lambda *args, **kwargs: _CM()


@pytest.fixture
def open_gate():
    """Let require_tier/_public_guard through without Redis."""
    from signalrank_telegram import commands

    with patch.object(commands.state, "get_killswitch_sync", return_value=SimpleNamespace(enabled=False)), \
            patch.object(commands.state, "rate_limited_sync", return_value=False), \
            patch.object(commands, "_public_guard", new=AsyncMock(return_value=False)):
        yield commands


# ---------------------------------------------------------------- /quality

REPORT = {
    "window_hours": 6,
    "issued": 2,
    "rejected_or_skipped": 18,
    "acceptance_rate": 0.1,
    "reject_buckets": {"score": 9, "ml": 4, "news": 0, "stale": 3, "slippage": 0, "other": 2},
    "top_reasons": [{"reason": "score_below_threshold", "rows": 9}, {"reason": "", "rows": 1}],
    "breakdowns": {
        "strategy": [{"value": "breakout", "issued": 1, "rejected_or_skipped": 12, "other": 0, "acceptance_rate": 1 / 13},
                     {"value": "(unattributed)", "issued": 0, "rejected_or_skipped": 6, "other": 0, "acceptance_rate": 0.0}],
        "asset": [{"value": "BTCUSDT", "issued": 2, "rejected_or_skipped": 10, "other": 0, "acceptance_rate": 2 / 12}],
        "timeframe": [{"value": "15m", "issued": 0, "rejected_or_skipped": 18, "other": 0, "acceptance_rate": 0.0}],
        "layer": [{"value": "risk", "issued": 0, "rejected_or_skipped": 5, "other": 1, "acceptance_rate": 0.0}],
    },
}


def test_quality_reply_carries_every_web_breakdown_dimension():
    from signalrank_telegram.commands import _format_quality_report

    text = _format_quality_report(REPORT)
    assert "Quality (last 6h)" in text
    assert "Acceptance rate: 10.0%" in text
    for heading in ("by strategy", "by instrument", "by timeframe", "by pipeline layer"):
        assert f"Most rejected {heading}:" in text
    assert "- breakout: 12 rejected / 1 issued (8% accepted)" in text
    assert "(unattributed)" in text
    assert "- BTCUSDT: 10 rejected / 2 issued (17% accepted)" in text
    assert "- score_below_threshold: 9" in text
    assert len(text) < 4096


def test_quality_reply_explains_an_empty_window_like_the_web_view():
    from signalrank_telegram.commands import _format_quality_report

    text = _format_quality_report({"window_hours": 24, "issued": 0, "rejected_or_skipped": 0})
    assert "No quality decisions were recorded" in text
    assert "signal engine did not run" in text


@pytest.mark.asyncio
async def test_web_and_telegram_quality_read_the_same_shared_report(open_gate):
    import web.platform_api as platform_api

    session = _Session()
    shared = AsyncMock(return_value=REPORT)
    with patch("services.platform.decision_quality.decision_quality_report", new=shared), \
            patch.object(platform_api, "get_session", new=_session_factory(session)), \
            patch.object(open_gate, "get_session", new=_session_factory(session)), \
            patch.object(open_gate, "_effective_tier", return_value="PREMIUM"), \
            patch.object(platform_api, "_assert_command", lambda *_a, **_k: None):
        web = await platform_api.quality_report(hours=6, user={"id": 1, "tier": "premium"})
        update = _update()
        await open_gate.quality_command(update, SimpleNamespace(args=["6h"]))

    assert web is REPORT
    assert [call.kwargs["hours"] for call in shared.await_args_list] == [6, 6]
    assert "Most rejected by strategy:" in update.message.replies[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("arg", ["0", "169", "abc"])
async def test_quality_rejects_out_of_range_windows(open_gate, arg):
    shared = AsyncMock(return_value=REPORT)
    with patch("services.platform.decision_quality.decision_quality_report", new=shared), \
            patch.object(open_gate, "_effective_tier", return_value="PREMIUM"):
        update = _update()
        await open_gate.quality_command(update, SimpleNamespace(args=[arg]))
    assert update.message.replies == ["Usage: /quality [hours 1-168]"]
    shared.assert_not_awaited()


def test_shared_summary_matches_the_previous_web_buckets():
    from services.platform.decision_quality import summarize_decisions

    reasons = [
        {"decision": "issued", "reason": "", "rows": 3},
        {"decision": "rejected", "reason": "ml_probability_low", "rows": 4},
        {"decision": "skipped", "reason": "stale_market_data", "rows": 2},
        {"decision": "rejected", "reason": "news_blackout", "rows": 1},
        {"decision": "rejected", "reason": "slippage_too_high", "rows": 1},
        {"decision": "rejected", "reason": "score_below_threshold", "rows": 5},
        {"decision": "rejected", "reason": "", "rows": 1},
    ]
    report = summarize_decisions(reasons, [], hours=24)
    assert report["issued"] == 3 and report["rejected_or_skipped"] == 14
    assert report["reject_buckets"] == {"score": 5, "ml": 4, "news": 1, "stale": 2, "slippage": 1, "other": 1}
    assert report["top_reasons"][0] == {"reason": "score_below_threshold", "rows": 5}
    assert set(report["breakdowns"]) == {"asset", "timeframe", "strategy", "layer"}


# ---------------------------------------------------------------- /feedback

def test_feedback_validation_matches_the_web_contract():
    from services.platform.signal_feedback import FeedbackRejected, normalize_feedback

    assert normalize_feedback(4, None, "  good  ") == (4, None, "good")
    assert normalize_feedback(None, "Wrong_Outcome", None) == (None, "wrong_outcome", None)
    for rating, issue in ((None, None), (6, None), (0, None), (None, "spam")):
        with pytest.raises(FeedbackRejected) as caught:
            normalize_feedback(rating, issue, None)
        assert caught.value.status == 422


@pytest.mark.asyncio
async def test_telegram_feedback_records_through_the_shared_ledger_service(open_gate):
    session = _Session()
    recorder = AsyncMock(return_value={"recorded": True, "signal_id": "1a2b3c4d-0000-4000-8000-000000000000"})
    with patch.object(open_gate, "get_session", new=_session_factory(session)), \
            patch.object(open_gate, "_effective_tier", return_value="PREMIUM"), \
            patch("services.platform.identity.ensure_telegram_user", new=AsyncMock(return_value=77)), \
            patch("services.platform.signal_feedback.record_signal_feedback", new=recorder):
        update = _update()
        await open_gate.feedback_command(update, SimpleNamespace(args=["SIG-1a2b3c4d", "wrong_outcome", "TP1", "hit"]))

    kwargs = recorder.await_args.kwargs
    assert kwargs == {"user_id": 77, "signal_ref": "SIG-1a2b3c4d", "rating": None, "issue": "wrong_outcome",
                      "comment": "TP1 hit", "source": "telegram"}
    assert session.committed == 1
    assert update.message.replies == ["✅ Feedback recorded for SIG-1a2b3c4d. Thank you!"]


@pytest.mark.asyncio
async def test_telegram_feedback_refusal_records_nothing(open_gate):
    from services.platform.signal_feedback import FeedbackRejected

    session = _Session()
    refused = AsyncMock(side_effect=FeedbackRejected("Signal not found in your delivery history", status=404))
    with patch.object(open_gate, "get_session", new=_session_factory(session)), \
            patch.object(open_gate, "_effective_tier", return_value="VIP"), \
            patch("services.platform.identity.ensure_telegram_user", new=AsyncMock(return_value=77)), \
            patch("services.platform.signal_feedback.record_signal_feedback", new=refused):
        update = _update()
        await open_gate.feedback_command(update, SimpleNamespace(args=["SIG-deadbeef", "5"]))

    assert refused.await_args.kwargs["rating"] == 5
    assert session.committed == 0 and session.rolled_back == 1
    assert update.message.replies[0].startswith("⚠️ Signal not found in your delivery history. Nothing was recorded.")


def test_feedback_no_longer_uses_the_in_memory_store():
    source = (ROOT / "signalrank_telegram" / "commands.py").read_text(encoding="utf-8")
    block = source[source.index("async def feedback_command"):source.index("# /pricing command")]
    assert "feedback_store" not in source
    assert "get_signal_id_by_short_ref" not in block
    assert 'source="telegram"' in block


@pytest.mark.asyncio
async def test_web_feedback_uses_the_same_service_with_web_source():
    import web.platform_api as platform_api

    session = _Session()
    recorder = AsyncMock(return_value={"recorded": True, "signal_id": "abc"})
    with patch.object(platform_api, "get_session", new=_session_factory(session)), \
            patch.object(platform_api, "_assert_command", lambda *_a, **_k: None), \
            patch("services.platform.signal_feedback.record_signal_feedback", new=recorder):
        result = await platform_api.submit_signal_feedback(
            "abc", platform_api.SignalFeedbackRequest(rating=3), user={"id": 9, "tier": "premium"}
        )
    assert result == {"recorded": True, "signal_id": "abc"}
    assert recorder.await_args.kwargs["source"] == "web"
    assert recorder.await_args.kwargs["user_id"] == 9
    assert session.committed == 1


# ---------------------------------------------------------------- /apikey

@pytest.mark.asyncio
async def test_apikey_lists_web_created_keys_and_webhook_hosts_only(open_gate):
    session = _Session(results=[
        [{"name": "CI bot", "key_prefix": "srk_0123456789ab", "scopes": ["signals:read"],
          "expires_at": None, "last_used_at": "2026-10-27 10:00:00"}],
        [{"url": "https://hooks.example.com/T000/secret-path?token=abc", "subscribed_events": ["signal.created"]}],
    ])
    with patch.object(open_gate, "get_session", new=_session_factory(session)), \
            patch.object(open_gate, "_effective_tier", return_value="PROFESSIONAL"), \
            patch("services.platform.identity.ensure_telegram_user", new=AsyncMock(return_value=55)), \
            patch("db.repository.get_latest_active_api_token_meta", new=AsyncMock(return_value=None)):
        update = _update()
        await open_gate.apikey_command(update, SimpleNamespace(args=[]))

    text = update.message.replies[0]
    assert any("FROM api_keys" in sql for sql in session.executed)
    assert any("FROM webhook_endpoints" in sql for sql in session.executed)
    assert "CI bot — srk_0123456789ab — scopes: signals:read" in text
    assert "last used 2026-10-27" in text
    assert "https://hooks.example.com — events: signal.created" in text
    assert "secret-path" not in text and "token=abc" not in text
    assert "/app/settings" in text


@pytest.mark.asyncio
async def test_apikey_applies_the_web_plan_gate(open_gate):
    session = _Session()
    with patch.object(open_gate, "get_session", new=_session_factory(session)), \
            patch.object(open_gate, "_effective_tier", return_value="PREMIUM"), \
            patch("services.platform.identity.ensure_telegram_user", new=AsyncMock(return_value=55)), \
            patch("db.repository.get_latest_active_api_token_meta",
                  new=AsyncMock(return_value={"token_prefix": "abcd1234", "expires_at": None})):
        update = _update()
        await open_gate.apikey_command(update, SimpleNamespace(args=[]))

    text = update.message.replies[0]
    assert not any("FROM api_keys" in sql for sql in session.executed)
    assert "need the Professional plan" in text
    assert "Legacy v1 token: prefix abcd1234" in text


# ---------------------------------------------------------------- /status

@pytest.mark.asyncio
@pytest.mark.parametrize("tier", ["free", "premium", "vip"])
async def test_status_shows_the_daily_limit_the_delivery_gate_enforces(tier):
    from core.tier_policy import get_entitlements
    from signalrank_telegram import commands

    def _no_db(*_a, **_k):
        raise RuntimeError("no database in this test")

    with patch("signalrank_telegram.access.resolve_user_tier", return_value=tier), \
            patch("db.session.get_session", new=_no_db), \
            patch.object(commands.state, "get_sync", return_value=None), \
            patch.object(commands, "_build_dynamic_menu", return_value=None):
        message, _keyboard = await commands._compose_status_message(4242)
    assert f"Signals today: 0/{get_entitlements(tier).daily_signal_limit}" in message


# ---------------------------------------------------------------- /kill_switch

@pytest.mark.asyncio
async def test_kill_switch_status_shows_scoped_switches_read_only():
    from signalrank_telegram import owner_commands

    document = {"switches": {"strategy": {"ORDER-BLOCK-ABC-V1": {"actor": "owner:7", "reason": "shadow only"}},
                             "instrument": {}, "asset_class": {"FX": {"actor": "owner:7", "reason": ""}}}}
    setter = AsyncMock()
    with patch.object(owner_commands, "_is_strict_owner", new=AsyncMock(return_value=True)), \
            patch.object(owner_commands.state, "get_killswitch",
                         new=AsyncMock(return_value=SimpleNamespace(enabled=False, reason=""))), \
            patch.object(owner_commands.state, "get_scoped_killswitches", new=AsyncMock(return_value=document)), \
            patch.object(owner_commands.state, "set_scoped_killswitches", new=setter):
        update = _update()
        await owner_commands.kill_switch_command(update, SimpleNamespace(args=["status"]))

    text = update.message.replies[0]
    assert "enabled=False" in text
    assert "- strategy:ORDER-BLOCK-ABC-V1 by owner:7 (shadow only)" in text
    assert "- asset_class:FX by owner:7 (no reason given)" in text
    assert "recent sign-in required" in text
    setter.assert_not_called()


@pytest.mark.asyncio
async def test_kill_switch_reports_unreadable_scoped_store_as_fail_closed():
    from signalrank_telegram import owner_commands

    with patch.object(owner_commands, "_is_strict_owner", new=AsyncMock(return_value=True)), \
            patch.object(owner_commands.state, "get_killswitch",
                         new=AsyncMock(return_value=SimpleNamespace(enabled=True, reason="x"))), \
            patch.object(owner_commands.state, "get_scoped_killswitches",
                         new=AsyncMock(side_effect=RuntimeError("scoped_killswitch_store_unavailable"))):
        update = _update()
        await owner_commands.kill_switch_command(update, SimpleNamespace(args=[]))
    assert "every execution stays blocked" in update.message.replies[0]


def test_telegram_cannot_change_scoped_switches():
    source = (ROOT / "signalrank_telegram" / "owner_commands.py").read_text(encoding="utf-8")
    assert "set_scoped_killswitches" not in source
    assert "apply_change" not in source


# ---------------------------------------------------------------- /privacy

def test_privacy_status_text_never_offers_export_or_deletion_in_chat():
    from services.platform.privacy import ACCOUNT_RETAINED_RECORDS
    from signalrank_telegram.platform_parity_commands import format_privacy_status

    none = format_privacy_status(None, ACCOUNT_RETAINED_RECORDS)
    assert "No account deletion review has been requested." in none
    assert "/app/settings" in none and "Exports are never sent through Telegram" in none
    pending = format_privacy_status(
        {"ticket_id": "9f8e7d6c-aaaa", "status": "open", "created_at": "2026-10-28 09:15:00"},
        ACCOUNT_RETAINED_RECORDS,
    )
    assert "Deletion review 9f8e7d6c: open (opened 2026-10-28 09:15 UTC)." in pending
    assert "Nothing is deleted until support completes the review." in pending
    assert "payment receipts and subscription history" in pending


@pytest.mark.asyncio
async def test_privacy_command_reads_the_callers_canonical_account():
    from signalrank_telegram import platform_parity_commands as parity

    session = _Session()
    reader = AsyncMock(return_value=None)
    with patch.object(parity, "get_session", new=_session_factory(session)), \
            patch("services.platform.identity.ensure_telegram_user", new=AsyncMock(return_value=31)), \
            patch("services.platform.privacy.latest_deletion_request", new=reader):
        update = _update()
        await parity.privacy_command(update, SimpleNamespace(args=[]))
    assert reader.await_args.kwargs == {"user_id": 31}
    assert "No account deletion review has been requested." in update.message.replies[0]


def test_web_and_telegram_share_the_deletion_constants():
    import web.platform_api as platform_api
    from services.platform import privacy

    assert platform_api.ACCOUNT_DELETION_CATEGORY is privacy.ACCOUNT_DELETION_CATEGORY
    assert platform_api.ACCOUNT_RETAINED_RECORDS is privacy.ACCOUNT_RETAINED_RECORDS
    assert platform_api.ACCOUNT_DELETION_PHRASE == "DELETE MY ACCOUNT"


# ---------------------------------------------------------------- /account_merges

@pytest.mark.asyncio
async def test_account_merges_refuses_non_operators_before_reading_merges():
    from signalrank_telegram import platform_parity_commands as parity

    session = _Session(results=[["free"]])
    with patch.object(parity, "get_session", new=_session_factory(session)), \
            patch("services.platform.operator_authority.operator_authority", return_value=None):
        update = _update()
        await parity.account_merges_command(update, SimpleNamespace(args=[]))
    assert update.message.replies == ["⛔ Operator access required."]
    assert not any("account_merge_records" in sql for sql in session.executed)


@pytest.mark.asyncio
async def test_account_merges_lists_and_previews_but_never_applies():
    from signalrank_telegram import platform_parity_commands as parity

    pending = [{"merge_id": "m-1", "canonical_user_id": 10, "merged_user_id": 11, "created_at": "2026-10-27 08:00:00"}]
    plan = {"merge_id": "m-1", "canonical_user_id": 10, "merged_user_id": 11,
            "movable": {"signal_deliveries.user_id": 40, "watchlists.user_id": 2, "alerts.user_id": 0},
            "kept_on_archived_account": {"paper_accounts.user_id": 1},
            "never_moved": {"user_sessions": 3, "api_keys": 0}, "failed": {}, "account_changes": {"tier": "vip"}}
    apply = AsyncMock(side_effect=AssertionError("Telegram must never apply a merge"))
    with patch("services.platform.operator_authority.operator_authority", return_value="ADMIN"), \
            patch("services.platform.account_merge.plan_account_merge", new=AsyncMock(return_value=plan)), \
            patch("services.platform.account_merge.apply_account_merge", new=apply):
        listing_session = _Session(results=[["admin"], pending])
        with patch.object(parity, "get_session", new=_session_factory(listing_session)):
            listing = _update()
            await parity.account_merges_command(listing, SimpleNamespace(args=[]))
        preview_session = _Session(results=[["admin"]])
        with patch.object(parity, "get_session", new=_session_factory(preview_session)):
            preview = _update()
            await parity.account_merges_command(preview, SimpleNamespace(args=["m-1"]))

    assert "m-1 — keep #10, archive #11" in listing.message.replies[0]
    text = preview.message.replies[0]
    assert "(preview, nothing changed)" in text
    assert "Rows that would move: 42 across 2 references." in text
    assert "- signal_deliveries.user_id: 40" in text
    assert "Never moved (credentials, sessions, audit): user_sessions" in text
    assert "recent sign-in" in text
    apply.assert_not_awaited()
    assert listing_session.committed == preview_session.committed == 0


@pytest.mark.parametrize(
    "telegram_id, tier, expected",
    [(1001, "free", "OWNER"), (2002, "free", "ADMIN"), (0, "OWNER", "OWNER"),
     (0, "admin", "ADMIN"), (3003, "vip", None), (None, None, None)],
)
def test_operator_authority_is_one_rule_for_web_and_telegram(monkeypatch, telegram_id, tier, expected):
    import config
    import web.platform_api as platform_api
    from services.platform.operator_authority import operator_authority

    monkeypatch.setattr(config, "OWNER_IDS", {1001}, raising=False)
    monkeypatch.setattr(config, "OWNER_TELEGRAM_IDS", set(), raising=False)
    monkeypatch.setattr(config, "OWNER_TELEGRAM_ID", 0, raising=False)
    monkeypatch.setattr(config, "ADMIN_IDS", {2002}, raising=False)
    assert operator_authority(telegram_user_id=telegram_id, tier=tier) == expected
    assert platform_api._platform_operator_authority({"telegram_user_id": telegram_id, "tier": tier}) == expected


# ---------------------------------------------------------------- registry and matrix

def test_new_commands_are_registered_with_matching_policy_and_catalogue():
    from core.tier_policy import COMMAND_MINIMUM_TIER
    from signalrank_telegram.command_catalog import COMMANDS

    bot = (ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")
    registered = set(re.findall(r'CommandHandler\(\s*["\']([^"\']+)', bot))
    catalogue = {spec.name: spec.tier for spec in COMMANDS}
    for name, tier in (("privacy", "FREE"), ("quality", "PREMIUM"), ("apikey", "PREMIUM"), ("account_merges", "ADMIN")):
        assert name in registered
        assert COMMAND_MINIMUM_TIER[name].value == tier
        assert catalogue[name] == tier
    api = (ROOT / "web" / "platform_api.py").read_text(encoding="utf-8")
    assert '"quality": "markets"' in api


def test_parity_matrix_covers_every_command_route_and_workspace_section():
    from signalrank_telegram.command_catalog import COMMANDS

    matrix = (ROOT / "docs" / "release" / "TELEGRAM_WEB_PARITY_MATRIX.md").read_text(encoding="utf-8")
    missing_commands = [spec.name for spec in COMMANDS if f"`/{spec.name}`" not in matrix]
    assert not missing_commands, f"commands without a matrix row: {missing_commands}"

    page = (ROOT / "frontend" / "src" / "app" / "app" / "[...slug]" / "page.tsx").read_text(encoding="utf-8")
    sections = re.findall(r'"([a-z]+)"', page[page.index("new Set(["):page.index("]);")])
    missing_sections = [name for name in sections if f"`/app/{name}`" not in matrix]
    assert not missing_sections, f"web sections without a matrix row: {missing_sections}"

    api = (ROOT / "web" / "platform_api.py").read_text(encoding="utf-8")
    routes = sorted(set(re.findall(r'@router\.(?:get|post|put|patch|delete)\("([^"]+)"', api)))
    missing_routes = [route for route in routes if f"`{route}`" not in matrix]
    assert not missing_routes, f"platform routes without a matrix row: {missing_routes}"
