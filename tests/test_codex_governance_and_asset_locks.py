from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_local_codex_recommendations_flag_duplicate_and_weak_win_rate():
    from services.codex_governance import build_local_codex_recommendations

    review = build_local_codex_recommendations(
        {
            "summary": {"outcomes": 20, "wins": 3, "losses": 17},
            "deliveries": {"reserved": 100, "sent_ok": 80, "reserved_not_confirmed": 20},
            "same_asset_deliveries_12h": 12,
            "score_saturation": {"signals": 50, "score_100": 7},
            "outcome_integrity": {"outcome_rows": 30, "distinct_signals": 20, "partial_progress_rows": 0},
            "segments": [
                {"asset_class": "fx", "timeframe": "1h", "strategy_name": "EMA Trend", "wins": 1, "losses": 9, "avg_r": -0.8}
            ],
        }
    )

    findings = "\n".join(review["highest_risk_findings"])
    env_tweaks = "\n".join(review["recommended_env_tweaks"])
    code_changes = "\n".join(review["recommended_code_changes"])

    assert "same-user/same-asset" in findings
    assert "Tracked win rate" in findings
    assert "delivery reservations" in findings
    assert "scored exactly 100" in findings
    assert "Outcome table has" in findings
    assert "No partial TP progress rows" in findings
    assert "ASSET_REPEAT_LOCK_HOURS=12" in env_tweaks
    assert "SCORE_DISPLAY_MAX=99.5" in env_tweaks
    assert "segment-level quarantine" in code_changes


@pytest.mark.asyncio
async def test_codex_audit_command_uses_local_governance_review():
    from signalrank_telegram.commands import codex_audit_command

    class _Message:
        def __init__(self) -> None:
            self.replies: list[str] = []

        async def reply_text(self, text: str) -> None:
            self.replies.append(text)

    update = MagicMock()
    update.effective_user = MagicMock(id=999)
    update.message = _Message()
    context = MagicMock()
    context.args = ["weekly"]

    result = {
        "ok": True,
        "external_codex_review": {"ok": True, "review": {"highest_risk_findings": ["aggregate finding"]}},
        "context": {
            "summary": {"signals": 10, "outcomes": 4, "wins": 1, "losses": 3},
            "deliveries": {"reserved_not_confirmed": 2},
            "same_asset_deliveries_12h": 5,
        },
        "review": {
            "assessment": "Local assessment.",
            "highest_risk_findings": ["duplicate issue"],
            "recommended_env_tweaks": ["ASSET_REPEAT_LOCK_HOURS=12"],
            "recommended_code_changes": ["keep central delivery guard"],
        },
    }

    with patch("signalrank_telegram.commands._is_admin", return_value=True), patch(
        "services.codex_governance.run_codex_governance_review", new=AsyncMock(return_value=result)
    ) as review_mock:
        await codex_audit_command(update, context)

    assert review_mock.await_count == 1
    assert any("Local Codex governance review complete" in reply for reply in update.message.replies)
    assert any("Same-asset repeats <12h: 5" in reply for reply in update.message.replies)
    assert any("OpenAI aggregate review findings" in reply for reply in update.message.replies)


def test_asset_lock_and_quarantine_wiring_present():
    root = Path(__file__).resolve().parents[1]
    pg_features = (root / "db" / "pg_features.py").read_text(encoding="utf-8")
    bot = (root / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")
    engine = (root / "engine" / "core.py").read_text(encoding="utf-8")

    assert "get_user_asset_position_state" in pg_features
    assert "get_user_asset_position_state" in bot
    assert "SignalDelivery.sent_ok.is_(False)" in pg_features
    assert "SignalDelivery.last_error.is_(None)" in pg_features
    assert "safety query failed; blocking delivery" in pg_features
    assert "SignalDelivery.sent_ok.is_(False)" in bot
    assert "_cycle_asset_cooldown" in engine
    assert "skipped_db_asset_cooldown" in engine
    assert "SEGMENT_QUARANTINE_ENABLED" in engine


def test_uncalibrated_perfect_score_is_display_capped(monkeypatch):
    from engine.core import _signal_display_score

    monkeypatch.delenv("SCORE_ALLOW_HARD_100", raising=False)
    monkeypatch.setenv("SCORE_DISPLAY_MAX", "99.5")

    assert _signal_display_score({"score": 100.0}) == 99.5
    assert _signal_display_score({"score": 100.0, "score_calibrated": 97.25}) == 97.25


def test_asset_position_manager_state_contract():
    from services.asset_position_manager import AssetPositionState, POSITION_STATES, _state_from_status

    for state in {"NONE", "CANDIDATE", "ACTIVE", "TP1", "TP2", "TP3", "STOPPED", "EXPIRED", "SUPERSEDED"}:
        assert state in POSITION_STATES

    assert _state_from_status("tp1") == "TP1"
    assert _state_from_status("tp2") == "TP2"
    assert _state_from_status("sl") == "STOPPED"
    assert _state_from_status("") == "ACTIVE"
    assert AssetPositionState(1, 2, "BTCUSDT", "STOPPED", locked=True).is_locked is True
    assert AssetPositionState(1, 2, "BTCUSDT", "ACTIVE", locked=False).is_locked is False


def test_railway_dump_analyzer_reports_same_asset_duplicates(tmp_path):
    from scripts.analyze_railway_sql_dump import analyze_dump

    dump = tmp_path / "dump.sql"
    dump.write_text(
        "\n".join(
            [
                "COPY public.signals (signal_id, asset, timeframe, direction, entry, stop_loss, take_profit, rr_estimate, score, regime, strategy_name, strategy_group, strength, created_at, fingerprint, archived, ml_probability, expires_at, expired, is_near_order_block, status, mfe_pct, mae_pct, asset_class) FROM stdin;",
                "sig1\tBTCUSDT\t1h\tlong\t100\t98\t102\t2\t100\tREG\tEMA\ttrend\t1\t2026-06-30 00:00:00\tfp1\tf\t0.8\t\\N\tf\tf\tactive\t\\N\t\\N\tcrypto",
                "sig2\tBTCUSDT\t15m\tshort\t101\t103\t99\t2\t99\tREG\tEMA\ttrend\t1\t2026-06-30 01:00:00\tfp2\tf\t0.8\t\\N\tf\tf\tactive\t\\N\t\\N\tcrypto",
                "\\.",
                "COPY public.signal_deliveries (id, user_id, signal_id, tier_at_send, delivered_at, sent_ok, attempt_count, last_attempt_at, last_error, created_at) FROM stdin;",
                "1\t1\tsig1\tvip\t2026-06-30 00:00:00\tt\t1\t2026-06-30 00:00:00\t\\N\t2026-06-30 00:00:00",
                "2\t1\tsig2\tvip\t2026-06-30 01:00:00\tt\t1\t2026-06-30 01:00:00\t\\N\t2026-06-30 01:00:00",
                "\\.",
                "COPY public.outcomes (id, signal_id, status, r_multiple, percent, opened_at, closed_at, duration_seconds, meta, canonical_outcome, vip_fill_outcome, sentiment_outcome, pnl_pct) FROM stdin;",
                "1\tsig1\tsl\t-1\t-1\t2026-06-30 00:00:00\t2026-06-30 02:00:00\t7200\t{}\tsl\t\\N\t\\N\t-1",
                "\\.",
                "COPY public.mt5_credentials (id, user_id, mt5_login, password_encrypted, server, metaapi_account_id, created_at, updated_at) FROM stdin;",
                "\\.",
                "COPY public.active_signal_messages (id, user_id, signal_id, chat_id, message_id, is_active, created_at) FROM stdin;",
                "\\.",
                "COPY public.users (id, telegram_user_id, username, created_at, tier, referred_by, fixed_lot_size, daily_executions_today, daily_executions_reset_at, max_risk_percentage, paystack_subscription_code, paystack_customer_code, auto_renew, referral_count, premium_until, max_daily_drawdown_pct, execution_mode, auto_signals_daily_limit, accepted_terms, timezone, dca_profile) FROM stdin;",
                "\\.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    report = analyze_dump(dump)

    assert report["same_asset_duplicate_12h_count"] == 1
    assert report["score_summary"]["score_100_count"] == 1
    assert report["outcome_counts"]["loss"] == 1
