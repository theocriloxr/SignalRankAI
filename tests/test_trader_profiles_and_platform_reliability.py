from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_trade_profile_shapes_intraday_targets_and_expiry(monkeypatch):
    from services.trade_profiles import apply_trade_profile_to_signal, infer_trade_profile

    monkeypatch.setenv("TRADE_PROFILE_ENGINE_ENABLED", "1")
    signal = {
        "asset": "XAUUSD",
        "timeframe": "15m",
        "direction": "long",
        "entry": 3984.50,
        "stop_loss": 3970.0,
        "take_profit": [4100.0, 4200.0, 4300.0],
        "atr": 10.0,
        "score": 94.0,
    }
    shaped = apply_trade_profile_to_signal(signal)

    assert infer_trade_profile(shaped) == "day"
    assert shaped["trade_profile"] == "day"
    assert shaped["take_profit"] == [3992.5, 3996.5, 4002.5]
    assert shaped["stop_loss"] == 3978.0
    assert shaped["time_to_target_score"] > 0
    assert shaped["expires_at"] is not None


def test_signal_profile_filter_matches_user_intent():
    from services.trade_profiles import signal_matches_user_profile

    assert signal_matches_user_profile({"timeframe": "15m"}, "day") is True
    assert signal_matches_user_profile({"timeframe": "4h"}, "day") is False
    assert signal_matches_user_profile({"timeframe": "4h"}, "all") is True


def test_trading_ledger_transition_contract():
    from services.trading_ledger import assert_valid_transition

    assert_valid_transition("ACTIVE", "TP1")
    assert_valid_transition("TP1", "TP2")
    with pytest.raises(ValueError):
        assert_valid_transition("STOPPED", "ACTIVE")
    with pytest.raises(ValueError):
        assert_valid_transition("TP3", "TP1")


def test_command_wrapper_has_timeout_reference_and_db_pressure_handling():
    source = (ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")

    assert "COMMAND_HANDLER_TIMEOUT_SECONDS" in source
    assert "ERR-" in source
    assert "asyncio.wait_for(handler(update, context)" in source
    assert "too many clients already" in source
    assert "Database connection pressure detected" in source


def test_db_health_and_profile_commands_are_registered_and_helped():
    bot = (ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")
    access = (ROOT / "signalrank_telegram" / "command_access.py").read_text(encoding="utf-8")
    commands = (ROOT / "signalrank_telegram" / "commands.py").read_text(encoding="utf-8")

    assert 'CommandHandler("profile"' in bot
    assert 'CommandHandler("db_health"' in bot
    assert '"profile":             "FREE"' in access
    assert '"db_health":           "ADMIN"' in access
    assert "async def profile_command" in commands
    assert "async def db_health_command" in commands


def test_signal_all_is_fast_usage_reply():
    source = (ROOT / "signalrank_telegram" / "commands.py").read_text(encoding="utf-8")

    assert 'if arg.lower() in {"all", "active", "list"}' in source
    assert "Use /signals to list your active signals" in source


def test_broadcast_and_terms_do_not_report_zero_sent_as_success():
    source = (ROOT / "signalrank_telegram" / "commands.py").read_text(encoding="utf-8")

    assert "Broadcast failed: no users received the message" in source
    assert "Terms blast failed: no users received the message" in source
    assert "return\n\n\texcept Exception as e:" in source


@pytest.mark.asyncio
async def test_tier_delivery_does_not_create_unmanaged_async_session():
    from signalrank_telegram.tier_delivery import TierDeliveryManager

    manager = TierDeliveryManager()
    with pytest.raises(RuntimeError, match="requires a synchronous SQLAlchemy session"):
        manager.get_users_for_signal({"score": 99}, "sig-1")

    fake_session = MagicMock()
    with patch("db.session.get_sync_session", return_value=fake_session), patch.object(
        manager,
        "get_users_for_signal",
        return_value={"free": [], "premium": [], "vip": [], "admin": [], "owner": []},
    ) as sample_mock:
        result = await manager.get_users_for_signal_managed({"score": 99}, "sig-1")

    assert result["free"] == []
    sample_mock.assert_called_once_with({"score": 99}, "sig-1", session=fake_session)
    fake_session.close.assert_called_once()


@pytest.mark.asyncio
async def test_db_health_command_formats_pool_snapshot():
    from signalrank_telegram.commands import db_health_command

    class _Message:
        def __init__(self):
            self.replies = []

        async def reply_text(self, text, **kwargs):
            self.replies.append(text)

    update = MagicMock()
    update.effective_user = MagicMock(id=123)
    update.message = _Message()
    context = MagicMock()

    with patch("signalrank_telegram.commands._is_admin", return_value=True), patch(
        "db.session.collect_database_health",
        new=AsyncMock(
            return_value={
                "pool": {
                    "configured": True,
                    "engine_ready": True,
                    "railway_runtime": True,
                    "engine_count": 1,
                    "size": 2,
                    "checkedout": 1,
                    "overflow": 0,
                    "effective_pool_size": 2,
                    "effective_max_overflow": 0,
                },
                "postgres": {"max_connections": "100", "activity_by_state": {"active": 1}},
            }
        ),
    ):
        await db_health_command(update, context)

    assert any("Database Health" in reply for reply in update.message.replies)
    assert any("checked_out=1" in reply for reply in update.message.replies)
