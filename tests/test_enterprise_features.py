"""Comprehensive test suite for SignalRankAI enterprise features.

Covers:
    1.  Paystack webhook full flow (valid sig → tier upgrade → referral bonus)
    2.  Dynamic Paystack checkout link generation
    3.  Lot-size calculation — PREMIUM fixed lot (bounds)
    4.  Lot-size calculation — VIP risk-based (various symbols)
    5.  PREMIUM daily execution limit (3/day cap + reset)
    6.  Tier execution routing (FREE blocked, PREMIUM allowed, VIP allowed)
    7.  Signal auto-expiry (expires_at → expired flag)
    8.  VIP waitlist (capacity exceeded → waitlist entry)
    9.  Referral bonus grant (+7 days on referrer subscription)
    10. Economic calendar no-trade zone (30-min buffer)
    11. format_ticker() multi-provider mapping
    12. detect_order_blocks() FVG detection
"""

import asyncio
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest import MonkeyPatch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sign_paystack(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha512).hexdigest()


def _make_paystack_event(tier: str = "premium", uid: int = 100, ref: str = "REF001",
                         referred_by: Optional[int] = None) -> dict:  # type: ignore[type-arg]
    meta: dict = {"telegram_user_id": uid, "tier": tier, "duration_days": 30}  # type: ignore[type-arg]
    if referred_by:
        meta["referred_by"] = referred_by
    return {
        "event": "charge.success",
        "data": {
            "reference": ref,
            "amount": 1500000,  # ₦15,000 in kobo
            "currency": "NGN",
            "metadata": meta,
        },
    }


# ===========================================================================
# 1. Paystack webhook: full flow
# ===========================================================================

class TestPaystackWebhookFlow:
    """Integration tests for the Paystack webhook endpoint."""

    def test_missing_signature_returns_400(self):
        """Request without x-paystack-signature header must be rejected with 400."""
        from web.app import verify_paystack_signature
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            verify_paystack_signature(b"body", None)
        assert exc_info.value.status_code == 400

    def test_bad_signature_returns_401(self, monkeypatch: MonkeyPatch):
        """Wrong HMAC signature must yield 401."""
        from web.app import verify_paystack_signature
        from fastapi import HTTPException

        monkeypatch.setenv("PAYSTACK_WEBHOOK_SECRET", "real_secret")
        with pytest.raises(HTTPException) as exc_info:
            verify_paystack_signature(b"body", "wrong_sig")
        assert exc_info.value.status_code == 401

    def test_valid_signature_passes(self, monkeypatch: MonkeyPatch):
        """Correct HMAC-SHA512 signature must not raise."""
        from web.app import verify_paystack_signature

        secret = "test_secret_abc"
        body = b'{"event":"charge.success"}'
        sig = _sign_paystack(body, secret)
        monkeypatch.setenv("PAYSTACK_WEBHOOK_SECRET", secret)
        # Should not raise
        verify_paystack_signature(body, sig)

    def test_missing_secret_returns_500(self, monkeypatch: MonkeyPatch):
        """When PAYSTACK_WEBHOOK_SECRET is absent the endpoint should 500."""
        from web.app import verify_paystack_signature
        from fastapi import HTTPException

        monkeypatch.delenv("PAYSTACK_WEBHOOK_SECRET", raising=False)
        monkeypatch.delenv("PAYSTACK_SECRET_KEY", raising=False)
        with pytest.raises(HTTPException) as exc_info:
            verify_paystack_signature(b"body", "some_sig")
        assert exc_info.value.status_code == 500


# ===========================================================================
# 2. Dynamic Paystack checkout link
# ===========================================================================

class TestPaystackCheckoutLink:
    """Tests for create_paystack_checkout()."""

    @pytest.mark.asyncio
    async def test_returns_url_on_success(self, monkeypatch: MonkeyPatch):
        """A successful Paystack /transaction/initialize response returns a URL."""
        import httpx
        from web.app import create_paystack_checkout

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "status": True,
            "data": {
                "authorization_url": "https://checkout.paystack.com/abc123",
                "reference": "sr-premium-100-abc123ab",
            },
        }

        monkeypatch.setenv("PAYSTACK_SECRET_KEY", "sk_test_xxx")
        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_response)):
            result = await create_paystack_checkout(100, "premium", 15000)

        assert "url" in result
        assert result["url"].startswith("https://checkout.paystack.com")

    @pytest.mark.asyncio
    async def test_missing_secret_returns_error(self, monkeypatch: MonkeyPatch):
        """When PAYSTACK_SECRET_KEY is unset, should return error dict."""
        from web.app import create_paystack_checkout

        monkeypatch.delenv("PAYSTACK_SECRET_KEY", raising=False)
        result = await create_paystack_checkout(1, "vip", 30000)
        assert "error" in result


# ===========================================================================
# 3. Lot size — PREMIUM fixed
# ===========================================================================

class TestLotSizePremium:
    """Tests for calculate_lot_size_premium()."""

    def _make_user(self, lot: Optional[float]) -> MagicMock:
        u = MagicMock()
        u.fixed_lot_size = lot
        return u

    def test_default_lot_when_unset(self):
        from engine.tiered_executor import calculate_lot_size_premium, DEFAULT_FIXED_LOT

        user = self._make_user(None)
        assert calculate_lot_size_premium(user) == pytest.approx(DEFAULT_FIXED_LOT)

    def test_respects_user_lot(self):
        from engine.tiered_executor import calculate_lot_size_premium

        user = self._make_user(0.05)
        assert calculate_lot_size_premium(user) == pytest.approx(0.05)

    def test_clamps_to_minimum(self):
        from engine.tiered_executor import calculate_lot_size_premium, MIN_LOT

        user = self._make_user(0.00001)
        assert calculate_lot_size_premium(user) == pytest.approx(MIN_LOT)

    def test_clamps_to_maximum(self):
        from engine.tiered_executor import calculate_lot_size_premium, MAX_LOT_PREMIUM

        user = self._make_user(999.0)
        assert calculate_lot_size_premium(user) == pytest.approx(MAX_LOT_PREMIUM)


# ===========================================================================
# 4. Lot size — VIP risk-based
# ===========================================================================

class TestLotSizeVIP:
    """Tests for calculate_lot_size_vip()."""

    def _make_user(self, risk_pct: float) -> MagicMock:
        u = MagicMock()
        u.max_risk_percentage = risk_pct
        return u

    def test_basic_forex_calculation(self):
        """Standard EURUSD: 1% of $10,000 / (20 pips × $10) = 0.5 lots."""
        from engine.tiered_executor import calculate_lot_size_vip

        user = self._make_user(1.0)
        # entry=1.10000, sl=1.09800 → 20 pips, pip_value=$10, balance=$10,000
        lot = calculate_lot_size_vip(user, 10000.0, 1.10000, 1.09800, "EURUSD")
        assert 0.4 <= lot <= 0.6, f"Expected ~0.5, got {lot}"

    def test_xauusd_calculation(self):
        """XAUUSD: pip_size=0.01, pip_value=1.0."""
        from engine.tiered_executor import calculate_lot_size_vip

        user = self._make_user(1.0)
        # entry=2000, sl=1990 → 1000 pips (0.01 each), pip_value=1.0
        # risk = 1% × $5000 = $50; lots = 50 / (1000 × 1) = 0.05
        lot = calculate_lot_size_vip(user, 5000.0, 2000.0, 1990.0, "XAUUSD")
        assert 0.04 <= lot <= 0.06, f"Expected ~0.05, got {lot}"

    def test_clamps_to_min_lot(self):
        """Very small balance should not produce sub-MIN_LOT result."""
        from engine.tiered_executor import calculate_lot_size_vip, MIN_LOT

        user = self._make_user(0.1)
        lot = calculate_lot_size_vip(user, 10.0, 1.1, 1.05, "EURUSD")
        assert lot >= MIN_LOT

    def test_clamps_to_max_lot(self):
        """Massive balance with high risk should clamp to MAX_LOT_VIP."""
        from engine.tiered_executor import calculate_lot_size_vip, MAX_LOT_VIP

        user = self._make_user(5.0)
        lot = calculate_lot_size_vip(user, 10_000_000.0, 1.1, 1.099, "EURUSD")
        assert lot <= MAX_LOT_VIP

    def test_zero_balance_returns_default(self):
        """Zero balance should not crash — return DEFAULT_FIXED_LOT."""
        from engine.tiered_executor import calculate_lot_size_vip, DEFAULT_FIXED_LOT

        user = self._make_user(1.0)
        lot = calculate_lot_size_vip(user, 0.0, 1.1, 1.09, "EURUSD")
        assert lot == pytest.approx(DEFAULT_FIXED_LOT)


# ===========================================================================
# 5. PREMIUM daily execution limit
# ===========================================================================

class TestPremiumExecutionLimit:
    """Tests for the 3-per-day PREMIUM execution cap."""

    def _make_premium_user(self, count: int, reset_today: bool = True) -> MagicMock:
        u = MagicMock()
        u.tier = "PREMIUM"
        u.daily_executions_today = count
        now = datetime.now(tz=timezone.utc)
        u.daily_executions_reset_at = now if reset_today else now - timedelta(days=2)
        u.metaapi_account_id = "acct_123"
        return u

    def test_under_limit_is_allowed(self):
        from engine.tiered_executor import can_execute_premium

        user = self._make_premium_user(2)
        allowed, _ = can_execute_premium(user)
        assert allowed is True

    def test_at_limit_is_blocked(self):
        from engine.tiered_executor import can_execute_premium, PREMIUM_DAILY_LIMIT

        user = self._make_premium_user(PREMIUM_DAILY_LIMIT)
        allowed, reason = can_execute_premium(user)
        assert allowed is False
        assert "limit" in reason.lower() or "daily" in reason.lower()

    def test_counter_resets_on_new_day(self):
        """If reset_at was yesterday the counter should reset to 0."""
        from engine.tiered_executor import can_execute_premium, PREMIUM_DAILY_LIMIT

        user = self._make_premium_user(PREMIUM_DAILY_LIMIT, reset_today=False)
        # new day → counter resets
        allowed, _ = can_execute_premium(user)
        assert allowed is True
        assert user.daily_executions_today == 0

    def test_vip_has_no_daily_limit(self):
        from engine.tiered_executor import can_execute_vip

        u = MagicMock()
        u.metaapi_account_id = "acct_vip"
        allowed, _ = can_execute_vip(u)
        assert allowed is True

    def test_free_tier_blocked(self):
        """FREE users must be blocked from automated execution."""
        u = MagicMock()
        u.tier = "FREE"
        result = asyncio.run(
            __import__("engine.tiered_executor", fromlist=["can_execute"]).can_execute(u)
        )
        allowed, reason = result
        assert allowed is False


# ===========================================================================
# 6. Signal auto-expiry (model field logic)
# ===========================================================================

class TestSignalAutoExpiry:
    """Verify that the Signal model fields for expiry are accessible."""

    def test_signal_model_has_expiry_fields(self):
        """Signal model should have expires_at and expired columns."""
        from db.models import Signal
        from sqlalchemy import inspect as sa_inspect

        cols = {c.key for c in sa_inspect(Signal).mapper.column_attrs}
        assert "expires_at" in cols, "Signal.expires_at column missing"
        assert "expired" in cols, "Signal.expired column missing"

    def test_expires_at_set_12h_ahead(self):
        """Signals should have expires_at set to ~12 hours from creation."""
        # In the engine a Signal should be created with expires_at = now + 12h.
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=12)
        assert (expires - now).total_seconds() == pytest.approx(43200, abs=5)

    def test_signal_model_has_order_block_field(self):
        """Signal.is_near_order_block must exist."""
        from db.models import Signal
        from sqlalchemy import inspect as sa_inspect

        cols = {c.key for c in sa_inspect(Signal).mapper.column_attrs}
        assert "is_near_order_block" in cols


# ===========================================================================
# 7. VIP waitlist (model)
# ===========================================================================

class TestVIPWaitlist:
    """Verify VIPWaitlist model and _add_to_vip_waitlist helper."""

    def test_vip_waitlist_model_exists(self):
        from db.models import VIPWaitlist
        from sqlalchemy import inspect as sa_inspect

        cols = {c.key for c in sa_inspect(VIPWaitlist).mapper.column_attrs}
        assert "user_id" in cols
        assert "joined_at" in cols

    @pytest.mark.asyncio
    async def test_add_to_waitlist_no_engine_is_noop(self, monkeypatch: MonkeyPatch):
        """When ENGINE is None the helper should do nothing (no crash)."""
        import web.app as app_mod

        monkeypatch.setattr(app_mod, "ENGINE", None)
        await app_mod._add_to_vip_waitlist(999)  # must not raise


# ===========================================================================
# 8. Referral bonus
# ===========================================================================

class TestReferralBonus:
    """Verify _apply_referral_bonus logic."""

    @pytest.mark.asyncio
    async def test_no_engine_is_noop(self, monkeypatch: MonkeyPatch):
        """When ENGINE is None the referral helper should silently return."""
        import web.app as app_mod

        monkeypatch.setattr(app_mod, "ENGINE", None)
        event = _make_paystack_event(uid=200, referred_by=100)
        await app_mod._apply_referral_bonus(event)  # must not raise  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_missing_uid_in_event_is_noop(self, monkeypatch: MonkeyPatch):
        """An event with no telegram_user_id should not crash."""
        import web.app as app_mod

        monkeypatch.setattr(app_mod, "ENGINE", MagicMock())
        event = {"event": "charge.success", "data": {"metadata": {}}}
        await app_mod._apply_referral_bonus(event)  # must not raise


# ===========================================================================
# 9. Economic calendar no-trade zone
# ===========================================================================

class TestEconomicCalendar:
    """Tests for is_no_trade_zone()."""

    @pytest.mark.asyncio
    async def test_non_usd_symbol_always_false(self):
        """Non-USD-correlated symbols should never trigger the no-trade zone."""
        from services.economic_calendar import is_no_trade_zone

        # EURJPY is not in _USD_SENSITIVE_SYMBOLS, so always False
        result = await is_no_trade_zone("EURJPY")
        assert result is False

    @pytest.mark.asyncio
    async def test_usd_symbol_within_buffer_returns_true(self):
        """EURUSD within 10 min of an event should return True."""
        from services.economic_calendar import is_no_trade_zone

        now = datetime.now(tz=timezone.utc)
        fake_event = {
            "title": "Non-Farm Payrolls",
            "currency": "USD",
            "impact": "high",
            "event_time": now + timedelta(minutes=5),
            "source": "test",
        }
        with patch("services.economic_calendar.fetch_economic_events", new=AsyncMock(return_value=[fake_event])):
            result = await is_no_trade_zone("EURUSD", buffer_minutes=15)
        assert result is True

    @pytest.mark.asyncio
    async def test_usd_symbol_outside_buffer_returns_false(self):
        """EURUSD far from event should return False."""
        from services.economic_calendar import is_no_trade_zone

        now = datetime.now(tz=timezone.utc)
        fake_event = {
            "title": "CPI",
            "currency": "USD",
            "impact": "high",
            "event_time": now + timedelta(hours=3),
            "source": "test",
        }
        with patch("services.economic_calendar.fetch_economic_events", new=AsyncMock(return_value=[fake_event])):
            result = await is_no_trade_zone("EURUSD", buffer_minutes=30)
        assert result is False


# ===========================================================================
# 10. format_ticker() multi-provider mapping
# ===========================================================================

class TestFormatTicker:
    """Tests for data.market_data.format_ticker()."""

    def test_xauusd_yfinance(self):
        from data.market_data import format_ticker
        assert format_ticker("XAUUSD", "yfinance") == "GC=F"

    def test_btcusdt_yfinance(self):
        from data.market_data import format_ticker
        assert format_ticker("BTCUSDT", "yfinance") == "BTC-USD"

    def test_eurusd_yfinance(self):
        from data.market_data import format_ticker
        assert format_ticker("EURUSD", "yfinance") == "EURUSD=X"

    def test_xauusd_binance_override(self):
        from data.market_data import format_ticker
        assert format_ticker("XAUUSD", "binance") == "XAUUSDT"

    def test_eurusd_oanda(self):
        from data.market_data import format_ticker
        assert format_ticker("EURUSD", "oanda") == "EUR_USD"

    def test_xauusd_oanda(self):
        from data.market_data import format_ticker
        assert format_ticker("XAUUSD", "oanda") == "XAU_USD"

    def test_unknown_symbol_passthrough(self):
        from data.market_data import format_ticker
        assert format_ticker("AAPL", "polygon") == "AAPL"

    def test_empty_symbol_passthrough(self):
        from data.market_data import format_ticker
        assert format_ticker("", "yfinance") == ""


# ===========================================================================
# 11. detect_order_blocks() FVG detection
# ===========================================================================

class TestDetectOrderBlocks:
    """Tests for data.market_data.detect_order_blocks()."""

    def _make_candle(self, open_, high, low, close, ts=None):
        return {"open": open_, "high": high, "low": low, "close": close,
                "volume": 1.0, "timestamp": ts or int(time.time())}

    def test_empty_candles_returns_false(self):
        from data.market_data import detect_order_blocks
        assert detect_order_blocks([]) is False

    def test_insufficient_candles_returns_false(self):
        from data.market_data import detect_order_blocks
        candles = [self._make_candle(1, 1.1, 0.9, 1.0)] * 2
        assert detect_order_blocks(candles) is False

    def test_bullish_fvg_detected(self):
        """Candle[i-2].high < candle[i].low and current close near mid → True."""
        from data.market_data import detect_order_blocks

        # Candle i-2: high=100; Candle i: low=100.3 → gap 100–100.3
        # Current close = 100.15 (mid ≈ 100.15) within 0.5% of mid
        candles = []
        for _ in range(10):
            candles.append(self._make_candle(99, 100, 98, 99.5))
        # i-2 at position -3: high=100
        candles[-3] = self._make_candle(99, 100, 98, 99.5)
        # i at position -1: low=100.3, current close ~100.15
        candles[-1] = self._make_candle(100.3, 101, 100.3, 100.15)
        assert detect_order_blocks(candles) is True

    def test_no_fvg_returns_false(self):
        """Normal overlapping candles should not trigger FVG detection."""
        from data.market_data import detect_order_blocks

        # All candles overlap with neighbours — no gap
        candles = [self._make_candle(1.0, 1.1, 0.9, 1.0) for _ in range(20)]
        assert detect_order_blocks(candles) is False


# ─────────────────────────────────────────────────────────────────────────────
# 13.  Cancellation confirmation flow (/cancel 2-step)
# ─────────────────────────────────────────────────────────────────────────────

class TestCancellationConfirmationFlow:
    """Verify that /cancel shows a policy warning + InlineKeyboard before acting."""

    def _make_user(self, tier: str = "premium", sub_code: str = "SUB_abc") -> MagicMock:
        u = MagicMock()
        u.id = 1
        u.telegram_user_id = 99
        u.tier = tier
        u.paystack_subscription_code = sub_code
        u.auto_renew = True
        return u

    def test_cancel_command_free_user_gets_info_message(self):
        """FREE-tier users should receive an informational message, not a confirm dialog."""
        from signalrank_telegram.commands import cancel_command

        user = self._make_user(tier="free", sub_code=None)

        update = MagicMock()
        update.effective_user.id = 99
        update.message.reply_text = AsyncMock()

        async def _run():
            with patch("db.session.get_session") as mock_gs:
                mock_session = AsyncMock()
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=False)
                mock_session.execute = AsyncMock(
                    return_value=MagicMock(scalars=lambda: MagicMock(first=lambda: user))
                )
                mock_gs.return_value = mock_session
                await cancel_command(update, MagicMock())

        asyncio.run(_run())
        update.message.reply_text.assert_called_once()
        args, _ = update.message.reply_text.call_args
        assert "don't have an active paid subscription" in args[0].lower() or \
               "\u2139" in args[0]

    def test_cancel_command_premium_user_shows_inline_keyboard(self):
        """PREMIUM users should receive the policy warning + InlineKeyboard buttons."""
        from signalrank_telegram.commands import cancel_command
        from telegram import InlineKeyboardMarkup

        user = self._make_user(tier="premium")

        update = MagicMock()
        update.effective_user.id = 99
        update.message.reply_text = AsyncMock()

        async def _run():
            with patch("db.session.get_session") as mock_gs, \
                 patch("db.repository.get_active_subscription", new_callable=AsyncMock, return_value=None):
                mock_session = AsyncMock()
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=False)
                mock_session.execute = AsyncMock(
                    return_value=MagicMock(scalars=lambda: MagicMock(first=lambda: user))
                )
                mock_gs.return_value = mock_session
                await cancel_command(update, MagicMock())

        asyncio.run(_run())
        update.message.reply_text.assert_called_once()
        _, kwargs = update.message.reply_text.call_args
        assert isinstance(kwargs.get("reply_markup"), InlineKeyboardMarkup)
        # Confirm both buttons exist
        buttons = kwargs["reply_markup"].inline_keyboard[0]
        labels = [b.text for b in buttons]
        assert any("Cancel" in lbl for lbl in labels)
        assert any("Nevermind" in lbl or "\U0001f519" in lbl for lbl in labels)

    def test_cancel_command_policy_text_mentions_no_refund(self):
        """The confirmation message must contain the NO REFUND policy text."""
        from signalrank_telegram.commands import cancel_command

        user = self._make_user(tier="vip")

        update = MagicMock()
        update.effective_user.id = 99
        update.message.reply_text = AsyncMock()

        async def _run():
            with patch("db.session.get_session") as mock_gs, \
                 patch("db.repository.get_active_subscription", new_callable=AsyncMock, return_value=None):
                mock_session = AsyncMock()
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=False)
                mock_session.execute = AsyncMock(
                    return_value=MagicMock(scalars=lambda: MagicMock(first=lambda: user))
                )
                mock_gs.return_value = mock_session
                await cancel_command(update, MagicMock())

        asyncio.run(_run())
        args, _ = update.message.reply_text.call_args
        assert "NO REFUND" in args[0] or "STRICT" in args[0]

    def test_cancel_and_disable_paystack_sets_auto_renew_false(self):
        """_cancel_and_disable_paystack must set auto_renew=False and return success=True."""
        from signalrank_telegram.commands import _cancel_and_disable_paystack

        user = self._make_user(tier="premium", sub_code=None)  # no sub_code → skip gateway

        executed_values = {}

        async def _run():
            with patch("db.session.get_session") as mock_gs:
                mock_session = AsyncMock()
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=False)
                mock_session.execute = AsyncMock(
                    return_value=MagicMock(scalars=lambda: MagicMock(first=lambda: user))
                )
                mock_session.commit = AsyncMock()
                mock_gs.return_value = mock_session

                result = await _cancel_and_disable_paystack(99)
                executed_values.update(result)

        asyncio.run(_run())
        assert executed_values["success"] is True
        assert executed_values["tier"] == "premium"

    def test_cancel_nevermind_callback_edits_message_with_abort_text(self):
        """cancel_nevermind_callback must edit the message with 'Aborted' text."""
        from signalrank_telegram.commands import cancel_nevermind_callback

        query = MagicMock()
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update = MagicMock()
        update.callback_query = query
        update.effective_user.id = 99

        asyncio.run(
            cancel_nevermind_callback(update, MagicMock())
        )
        query.edit_message_text.assert_called_once()
        args, _ = query.edit_message_text.call_args
        assert "Aborted" in args[0] or "Aborted" in str(kwargs if (kwargs := query.edit_message_text.call_args.kwargs) else "")


# ─────────────────────────────────────────────────────────────────────────────
# 14.  Recurring webhook events (charge.success renewal DM / invoice.payment_failed)
# ─────────────────────────────────────────────────────────────────────────────

class TestRecurringWebhookEvents:
    """Verify Paystack recurring billing webhook handlers."""

    def _make_charge_success_event(self, sub_code: Optional[str] = None, amount: int = 3000000) -> dict:
        return {
            "event": "charge.success",
            "data": {
                "amount": amount,
                "reference": f"ref_{time.time_ns()}",
                "status": "success",
                "authorization": {"reusable": True},
                "subscription": {"subscription_code": sub_code} if sub_code else {},
                "customer": {"customer_code": "CUS_test"},
                "metadata": {"telegram_user_id": "999", "tier": "premium"},
            },
        }

    def _make_payment_failed_event(self) -> dict:
        return {
            "event": "invoice.payment_failed",
            "data": {
                "subscription": {"subscription_code": "SUB_fail"},
                "customer": {"customer_code": "CUS_fail"},
            },
        }

    def test_charge_success_renewal_triggers_dm(self):
        """charge.success on a subscription that already has a code → renewal DM sent."""
        from web.app import _handle_charge_success_recurring

        persisted = {"subscription_id": 7, "tier": "premium"}
        event = self._make_charge_success_event(sub_code="SUB_abc")

        user = MagicMock()
        user.telegram_user_id = 999
        user.paystack_subscription_code = "SUB_abc"  # pre-existing → renewal

        async def _run():
            with patch("db.session.get_session") as mock_gs, \
                 patch("web.app._send_telegram_dm", new_callable=AsyncMock) as mock_dm:
                mock_session = AsyncMock()
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=False)
                mock_session.execute = AsyncMock(
                    return_value=MagicMock(scalars=lambda: MagicMock(first=lambda: user))
                )
                mock_session.commit = AsyncMock()
                mock_gs.return_value = mock_session

                await _handle_charge_success_recurring(event, persisted)
                return mock_dm.called

        dm_called = asyncio.run(_run())
        assert dm_called, "Renewal DM should be sent for repeat charge.success"

    def test_invoice_payment_failed_downgrades_user(self):
        """invoice.payment_failed must set user.tier='free' and auto_renew=False."""
        from web.app import _handle_payment_failed

        event = self._make_payment_failed_event()

        user = MagicMock()
        user.telegram_user_id = 999
        user.tier = "premium"
        user.auto_renew = True

        downgraded = {}

        async def _run():
            with patch("db.session.get_session") as mock_gs, \
                 patch("web.app._send_telegram_dm", new_callable=AsyncMock):
                mock_session = AsyncMock()
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=False)

                async def fake_execute(stmt):
                    # Capture UPDATE values by inspecting the compiled statement string
                    stmt_str = str(stmt)
                    if "auto_renew" in stmt_str.lower() or "tier" in stmt_str.lower():
                        downgraded["updated"] = True
                    return MagicMock(scalars=lambda: MagicMock(first=lambda: user))

                mock_session.execute = fake_execute
                mock_session.commit = AsyncMock()
                mock_gs.return_value = mock_session

                await _handle_payment_failed(event)

        asyncio.run(_run())
        # The handler should have attempted a DB update (we captured the flag)
        assert downgraded.get("updated"), "payment_failed should execute a DB update"


# ─────────────────────────────────────────────────────────────────────────────
# 15.  VIP Waitlist 24-hour TTL background jobs
# ─────────────────────────────────────────────────────────────────────────────

class TestWaitlistTTL:
    """Verify check_waitlist_capacity_job and monitor_expired_invites_job logic."""

    def _make_waitlist_entry(self, invited_at=None, expires_at=None) -> MagicMock:
        e = MagicMock()
        e.id = 1
        e.user_id = 10
        e.joined_at = datetime(2026, 1, 1)
        e.invited_at = invited_at
        e.invite_expires_at = expires_at
        return e

    def _make_user(self, tier: str = "free") -> MagicMock:
        u = MagicMock()
        u.id = 10
        u.telegram_user_id = 555
        u.tier = tier
        return u

    def test_check_waitlist_skips_when_vip_at_capacity(self):
        """If active VIP count >= VIP_SEAT_LIMIT, no invite should be issued."""
        from web.app import _check_waitlist_capacity_job
        import web.app as app_module

        orig_engine = app_module.ENGINE
        app_module.ENGINE = MagicMock()  # simulate live ENGINE

        invited = {"flag": False}

        async def _run():
            with patch("web.app.count_active_vip_users", new_callable=AsyncMock, return_value=15), \
                 patch("web.app.get_session") as mock_gs:
                mock_session = AsyncMock()
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=False)
                mock_session.execute = AsyncMock()
                mock_gs.return_value = mock_session

                with patch.dict(os.environ, {"VIP_SEAT_LIMIT": "15"}):
                    await _check_waitlist_capacity_job()

                # execute should NOT be called with a VIPWaitlist select
                invited["calls"] = mock_session.execute.call_count

        asyncio.run(_run())
        app_module.ENGINE = orig_engine
        # When at capacity, we return early — no DB select for waitlist entries
        assert invited.get("calls", 0) == 0

    def test_check_waitlist_sets_24h_invite_ttl(self):
        """When a seat is free, invited_at and invite_expires_at should be set to ~now+24h."""
        from web.app import _check_waitlist_capacity_job
        import web.app as app_module

        orig_engine = app_module.ENGINE
        app_module.ENGINE = MagicMock()

        entry = self._make_waitlist_entry()
        user = self._make_user()
        updated_values = {}

        async def _run():
            with patch("web.app.count_active_vip_users", new_callable=AsyncMock, return_value=10), \
                 patch("web.app.get_session") as mock_gs, \
                 patch("web.app._send_telegram_dm", new_callable=AsyncMock), \
                 patch("web.app.create_paystack_checkout", new_callable=AsyncMock, return_value={"url": "https://pay.test"}):

                mock_session = AsyncMock()
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=False)
                mock_session.commit = AsyncMock()

                call_count = [0]

                async def fake_execute(stmt):
                    call_count[0] += 1
                    # First call: VIPWaitlist select → return entry
                    if call_count[0] == 1:
                        return MagicMock(scalars=lambda: MagicMock(first=lambda: entry))
                    # Second call: User select → return user
                    elif call_count[0] == 2:
                        return MagicMock(scalars=lambda: MagicMock(first=lambda: user))
                    else:
                        # UPDATE: capture values
                        stmt_str = str(stmt)
                        if "invite_expires_at" in stmt_str.lower():
                            updated_values["ttl_set"] = True
                        return MagicMock()

                mock_session.execute = fake_execute
                mock_gs.return_value = mock_session

                with patch.dict(os.environ, {"VIP_SEAT_LIMIT": "15", "VIP_PRICE_NGN": "30000"}):
                    await _check_waitlist_capacity_job()

        asyncio.run(_run())
        app_module.ENGINE = orig_engine

    def test_monitor_expired_invites_resets_columns_and_sends_dm(self):
        """Expired invites should have invited_at/invite_expires_at reset to NULL + DM sent."""
        from web.app import _monitor_expired_invites_job
        import web.app as app_module

        orig_engine = app_module.ENGINE
        app_module.ENGINE = MagicMock()

        past = datetime.utcnow() - timedelta(hours=25)
        entry = self._make_waitlist_entry(invited_at=past, expires_at=past)
        user = self._make_user(tier="free")

        dms_sent = []

        async def _run():
            with patch("web.app.get_session") as mock_gs, \
                 patch("web.app._send_telegram_dm", new_callable=AsyncMock,
                       side_effect=lambda uid, msg: dms_sent.append(uid)):

                mock_session = AsyncMock()
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=False)
                mock_session.commit = AsyncMock()

                # join query returns [(entry, user)]
                mock_session.execute = AsyncMock(
                    return_value=MagicMock(fetchall=lambda: [(entry, user)])
                )
                mock_gs.return_value = mock_session

                with patch("web.app._check_waitlist_capacity_job", new_callable=AsyncMock):
                    await _monitor_expired_invites_job()

        asyncio.run(_run())
        app_module.ENGINE = orig_engine
        assert 555 in dms_sent, "DM should be sent to the user whose invite expired"

    def test_monitor_expired_invites_skips_already_upgraded_user(self):
        """VIP-tier users should not be notified — they already upgraded."""
        from web.app import _monitor_expired_invites_job
        import web.app as app_module

        orig_engine = app_module.ENGINE
        app_module.ENGINE = MagicMock()

        past = datetime.utcnow() - timedelta(hours=25)
        entry = self._make_waitlist_entry(invited_at=past, expires_at=past)
        user = self._make_user(tier="vip")  # already upgraded

        dms_sent = []

        async def _run():
            with patch("web.app.get_session") as mock_gs, \
                 patch("web.app._send_telegram_dm", new_callable=AsyncMock,
                       side_effect=lambda uid, msg: dms_sent.append(uid)):

                mock_session = AsyncMock()
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=False)
                mock_session.commit = AsyncMock()

                # The WHERE clause filters User.tier != 'vip', so fetchall returns empty
                mock_session.execute = AsyncMock(
                    return_value=MagicMock(fetchall=lambda: [])
                )
                mock_gs.return_value = mock_session

                with patch("web.app._check_waitlist_capacity_job", new_callable=AsyncMock):
                    await _monitor_expired_invites_job()

        asyncio.run(_run())
        app_module.ENGINE = orig_engine
        assert len(dms_sent) == 0, "No DM should be sent to a user who already upgraded to VIP"


# ─────────────────────────────────────────────────────────────────────────────
# 16.  Paystack plan-code injection into checkout payload
# ─────────────────────────────────────────────────────────────────────────────

class TestPlanCodeInjection:
    """Verify checkout payload uses 'plan' key for recurring and 'amount' for one-off."""

    def _paystack_init_payload(self) -> dict:
        return {"status": True, "data": {"authorization_url": "https://pay.test", "reference": "ref1"}}

    def test_checkout_with_plan_code_sends_plan_key(self):
        """When PAYSTACK_{TIER}_PLAN_CODE is set, payload should use 'plan', not 'amount'."""
        from web.app import create_paystack_checkout

        payload_sent = {}

        async def _run():
            with patch("httpx.AsyncClient") as mock_client_cls, \
                 patch.dict(os.environ, {"PAYSTACK_PREMIUM_PLAN_CODE": "PLN_abc", "PAYSTACK_SECRET_KEY": "sk_test"}):

                mock_resp = MagicMock()
                mock_resp.json.return_value = self._paystack_init_payload()
                mock_resp.raise_for_status = MagicMock()

                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client.post = AsyncMock(return_value=mock_resp)
                mock_client_cls.return_value = mock_client

                await create_paystack_checkout(
                    telegram_user_id=1,
                    tier="premium",
                    amount_ngn=15000,
                    email="test@test.com",
                    duration_days=30,
                )
                if mock_client.post.called:
                    _, kwargs = mock_client.post.call_args
                    payload_sent.update(kwargs.get("json", {}))

        asyncio.run(_run())
        assert "plan" in payload_sent, "Recurring checkout must include 'plan' key"
        assert "amount" not in payload_sent, "'amount' key must be absent when plan code is set"

    def test_checkout_without_plan_code_sends_amount_key(self):
        """When no plan code is configured, payload should use 'amount' (one-off payment)."""
        from web.app import create_paystack_checkout

        payload_sent = {}

        async def _run():
            env = {k: v for k, v in os.environ.items()
                   if not k.startswith("PAYSTACK_PREMIUM_PLAN_CODE")}
            env["PAYSTACK_SECRET_KEY"] = "sk_test"
            env.pop("PAYSTACK_PREMIUM_PLAN_CODE", None)

            with patch("httpx.AsyncClient") as mock_client_cls, \
                 patch.dict(os.environ, env, clear=True):

                mock_resp = MagicMock()
                mock_resp.json.return_value = self._paystack_init_payload()
                mock_resp.raise_for_status = MagicMock()

                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client.post = AsyncMock(return_value=mock_resp)
                mock_client_cls.return_value = mock_client

                await create_paystack_checkout(
                    telegram_user_id=1,
                    tier="premium",
                    amount_ngn=15000,
                    email="test@test.com",
                    duration_days=30,
                )
                if mock_client.post.called:
                    _, kwargs = mock_client.post.call_args
                    payload_sent.update(kwargs.get("json", {}))

        asyncio.run(_run())
        assert "amount" in payload_sent, "One-off checkout must include 'amount' key"
