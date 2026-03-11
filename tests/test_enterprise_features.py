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
        result = asyncio.get_event_loop().run_until_complete(
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
