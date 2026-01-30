from __future__ import annotations

from datetime import datetime
from typing import Optional
from utils.timeutils import now_utc_naive
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    # Use a consistent naive-UTC timestamp across the codebase as a
    # stop-gap. Prefer storing timestamptz and using aware datetimes.
    return now_utc_naive()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    tier: Mapped[str] = mapped_column(String(16), index=True, nullable=False, default="free")
    referral_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)  # Tracks referrals toward next reward
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="user")  # type: ignore[name-defined]


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    tier: Mapped[str] = mapped_column(String(16), index=True, nullable=False)  # free/premium/vip
    status: Mapped[str] = mapped_column(String(16), index=True, nullable=False, default="active")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    bonus_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # Referral bonus days to stack

    paystack_reference: Mapped[Optional[str]] = mapped_column(String(128), unique=True, nullable=True)
    meta: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    user: Mapped[User] = relationship(back_populates="subscriptions")


class PaymentEvent(Base):
    __tablename__ = "payment_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)

    # subscription | extra_signals | other
    kind: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="subscription")
    tier: Mapped[Optional[str]] = mapped_column(String(32), index=True, nullable=True)
    duration_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    plan_code: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    amount_ngn: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)

    paystack_reference: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    meta: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class BotEvent(Base):
    __tablename__ = "bot_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    meta: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class Signal(Base):
    __tablename__ = "signals"

    signal_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    asset: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), index=True, nullable=False)
    direction: Mapped[str] = mapped_column(String(8), index=True, nullable=False)  # long/short

    entry: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    take_profit: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-encoded list for now

    rr_estimate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    score: Mapped[float] = mapped_column(Float, index=True, nullable=False)
    regime: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    ml_probability: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=None)

    strategy_name: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_group: Mapped[str] = mapped_column(String(32), nullable=False)
    strength: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Optional deduplication key for “same signal” within a short window (e.g., 24h).
    fingerprint: Mapped[Optional[str]] = mapped_column(String(128), index=True, nullable=True)
    # Soft delete: signal with outcome is excluded from /signals queries but kept for history
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class MarketTick(Base):
    __tablename__ = "market_ticks"

    # One row per symbol; continuously upserted by WS/REST.
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    event_time_ms: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class MarketCandle(Base):
    __tablename__ = "market_candles"
    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "open_time_ms", name="uq_market_candles_symbol_tf_open"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), index=True, nullable=False)
    open_time_ms: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    close_time_ms: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Outcome(Base):
    __tablename__ = "outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_id: Mapped[str] = mapped_column(ForeignKey("signals.signal_id"), index=True, nullable=False)

    status: Mapped[str] = mapped_column(String(16), index=True, nullable=False)  # tp1/tp2/tp/sl/invalid
    r_multiple: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    meta: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class Trade(Base):
    """Track open and closed trades for position management."""
    __tablename__ = "trades"

    trade_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    signal_id: Mapped[Optional[str]] = mapped_column(ForeignKey("signals.signal_id"), index=True, nullable=True)
    
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)  # long/short
    
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    entry_time: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    
    position_size: Mapped[float] = mapped_column(Float, nullable=False)
    
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    take_profit: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-encoded list
    
    status: Mapped[str] = mapped_column(String(16), index=True, nullable=False, default="open")  # open/closed/cancelled
    
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exit_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    exit_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # tp/sl/invalidation/timeout
    
    pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pnl_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    max_drawdown: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_profit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Partial exits
    partial_exits: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    
    # Risk management
    max_risk_pct: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)  # Max % of account
    atr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    trade_metadata: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class StrategyStat(Base):
    __tablename__ = "strategy_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_name: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    strategy_group: Mapped[str] = mapped_column(String(32), index=True, nullable=False)

    trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    win_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_r: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ewma_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class AdminEvent(Base):
    __tablename__ = "admin_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    actor_telegram_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    details: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class AlertPreference(Base):
    __tablename__ = "alert_prefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True, nullable=False)
    tp_sl_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    quiet_start_hour: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    quiet_end_hour: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class ReferralCode(Base):
    __tablename__ = "referral_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    referrer_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class ReferralAttribution(Base):
    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    referred_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True, nullable=False)
    referrer_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    referrer_notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # When referrer was notified


class ReferralReward(Base):
    __tablename__ = "referral_rewards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    referrer_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    referred_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    reward_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    reward_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class FreeSignalQueue(Base):
    __tablename__ = "free_signal_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)

    signal_id: Mapped[str] = mapped_column(ForeignKey("signals.signal_id"), index=True, nullable=False)
    asset: Mapped[str] = mapped_column(String(32), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    queued_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    deliver_after: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), index=True, nullable=False, default="queued")


class SignalDelivery(Base):
    __tablename__ = "signal_deliveries"
    __table_args__ = (
        UniqueConstraint("user_id", "signal_id", name="uq_signal_delivery_user_signal"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    signal_id: Mapped[str] = mapped_column(ForeignKey("signals.signal_id"), index=True, nullable=False)
    tier_at_send: Mapped[str] = mapped_column(String(16), index=True, nullable=False, default="free")
    delivered_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class SignalCorrection(Base):
    """Track signal corrections sent to users when original signal had errors."""
    __tablename__ = "signal_corrections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    original_signal_id: Mapped[str] = mapped_column(ForeignKey("signals.signal_id"), index=True, nullable=False)
    corrected_signal_id: Mapped[Optional[str]] = mapped_column(ForeignKey("signals.signal_id"), index=True, nullable=True)
    
    error_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # invalid_entry/data_error/calc_error/etc
    error_description: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Track if users were notified
    users_notified: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correction_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    meta: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class RuntimeState(Base):
    __tablename__ = "runtime_state"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
