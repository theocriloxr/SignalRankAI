from __future__ import annotations

from datetime import datetime
from typing import Optional
from utils.timeutils import now_utc_naive
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Table, Column, MetaData
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
    referral_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    premium_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # Premium/VIP expiry
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    # ── Referral tracking ───────────────────────────────────────────────────────
    referred_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)  # referrer telegram_user_id

    # ── PREMIUM tier: fixed-lot MT5 execution settings ─────────────────────────
    # Max 3 executions/day. Fixed lot only. Editable via /setlot.
    fixed_lot_size: Mapped[float] = mapped_column(Float, nullable=False, default=0.01)
    daily_executions_today: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    daily_executions_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # ── VIP tier: risk-based auto-sizing ───────────────────────────────────────
    # Editable via /setrisk. Engine calculates lot from account balance + SL distance.
    max_risk_percentage: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    # ── Paystack recurring subscription tracking ────────────────────────────────
    # Set when Paystack creates a recurring subscription (charge.success event).
    paystack_subscription_code: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    paystack_customer_code: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    # False after /cancel or invoice.payment_failed — prevents re-renewal messaging
    auto_renew: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # ── Legal / onboarding gate ─────────────────────────────────────────────
    # True once the user has clicked [I Agree] on the financial disclaimer.
    # The bot withholds signal delivery until this is set.
    accepted_terms: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
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
    # ── Signal auto-expiry (12 hours after creation) ────────────────────────────
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    expired: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    # ── ML order-block enrichment ───────────────────────────────────────────────
    is_near_order_block: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

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
    is_successful: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reward_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    successful_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
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


class MLRejectedSignal(Base):
    """Track signals rejected by ML for training improvement."""
    __tablename__ = "ml_rejected_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), index=True, nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    entry: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    take_profit: Mapped[str] = mapped_column(Text, nullable=False)
    ml_probability: Mapped[float] = mapped_column(Float, nullable=False)
    rejection_reason: Mapped[str] = mapped_column(String(128), nullable=False)
    features: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    actual_outcome: Mapped[Optional[str]] = mapped_column(String(32), index=True, nullable=True)
    outcome_tracked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class MLPastTrainingData(Base):
    """Persistent archive of historical labeled samples for ML retraining.

    This table is intentionally preserved during fresh-reset test boots so the
    model can train on both legacy and post-reset outcomes.
    """
    __tablename__ = "ml_past_training_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_id: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=False)
    asset: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), index=True, nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)

    entry: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    take_profit: Mapped[str] = mapped_column(Text, nullable=False)

    rr_estimate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    strength: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    regime: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    strategy_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    ml_probability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    outcome_status: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    outcome_r_multiple: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    outcome_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    outcome_meta: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    signal_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    outcome_closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    archived_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class DecisionLog(Base):
    __tablename__ = "decision_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)
    asset: Mapped[Optional[str]] = mapped_column(String(32), index=True, nullable=True)
    timeframe: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    decision: Mapped[str] = mapped_column(String(32), index=True, nullable=False)  # e.g., issued/filtered/rejected
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    meta: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Signal engagement polling (🔥 Taking It / 👀 Watching)
# ---------------------------------------------------------------------------
class SignalEngagement(Base):
    """Tracks user reactions to signals for gamification and fantasy scoring."""
    __tablename__ = "signal_engagements"
    __table_args__ = (
        UniqueConstraint("user_id", "signal_id", name="uq_signal_engagement_user_signal"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    signal_id: Mapped[str] = mapped_column(ForeignKey("signals.signal_id"), index=True, nullable=False)
    # 'taking_it' = 🔥  |  'watching' = 👀
    reaction: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Active signal message tracking (for inline keyboard editing)
# ---------------------------------------------------------------------------
class ActiveSignalMessage(Base):
    """Tracks the Telegram message_id of live signal DMs for real-time editing.

    When a user updates /setlot or /setrisk, we edit their pinned signal messages
    with the updated execution button.
    """
    __tablename__ = "active_signal_messages"
    __table_args__ = (
        UniqueConstraint("user_id", "signal_id", name="uq_active_signal_msg_user_signal"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    signal_id: Mapped[str] = mapped_column(ForeignKey("signals.signal_id"), index=True, nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Becomes False when signal expires, outcome reached, or bot catches edit error
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Economic calendar events (macro news protector)
# ---------------------------------------------------------------------------
class EconomicEvent(Base):
    """Cached economic calendar events (fetched from free APIs daily)."""
    __tablename__ = "economic_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_date: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), index=True, nullable=False)  # USD, EUR, GBP…
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    # 'high' (red folder) | 'medium' | 'low'
    impact: Mapped[str] = mapped_column(String(8), index=True, nullable=False, default="low")
    source: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # which API supplied it
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# MT5 execution log (tier-gated order tracking)
# ---------------------------------------------------------------------------
class MT5Execution(Base):
    """Tracks each automated MT5 trade execution for tier enforcement and P&L."""
    __tablename__ = "mt5_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    signal_id: Mapped[Optional[str]] = mapped_column(ForeignKey("signals.signal_id"), index=True, nullable=True)
    metaapi_account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    order_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)  # long/short
    lot_size: Mapped[float] = mapped_column(Float, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    take_profit: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-encoded list

    # 'pending' | 'open' | 'tp1' | 'tp2' | 'tp3' | 'sl' | 'closed' | 'error'
    status: Mapped[str] = mapped_column(String(16), index=True, nullable=False, default="pending")
    # Tier at execution time drives which TP logic applies
    tier_at_execution: Mapped[str] = mapped_column(String(16), nullable=False, default="premium")

    # Realised P&L (filled by outcome tracker)
    realized_pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    realized_pnl_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    executed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    meta: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


# ---------------------------------------------------------------------------
# VIP waitlist
# ---------------------------------------------------------------------------
class VIPWaitlist(Base):
    """Queue of users who tried to subscribe VIP when seats were full."""
    __tablename__ = "vip_waitlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # 24-hour invite TTL: set by check_waitlist_capacity_job when a seat opens
    invited_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    invite_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)


# ---------------------------------------------------------------------------
# Managed assets (admin-pinned asset list, merged with auto-discovered pairs)
# ---------------------------------------------------------------------------
class ManagedAsset(Base):
    """Admin-pinned assets that the engine ALWAYS includes in its universe.

    Assets can be added/removed via /assets add|remove <SYMBOL> and are merged
    with auto-discovered trending pairs on every engine cycle.

    ``is_active=True``  → include in engine universe
    ``is_active=False`` → soft-delete (pinned assets an admin has removed)
    """
    __tablename__ = "managed_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    asset_type: Mapped[str] = mapped_column(String(16), nullable=False, default="crypto")  # crypto/fx/stock/commodity
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    added_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)  # telegram_user_id of admin
    note: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    # Anti-stagnation queue: engine updates this after each analysis cycle so
    # assets with the oldest timestamp are processed first next cycle.
    last_analyzed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# MT5 / MetaApi credential storage (password encrypted with Fernet)
# ---------------------------------------------------------------------------
class MT5Credentials(Base):
    """Stores encrypted MT5 credentials per Telegram user.

    The ``password_encrypted`` column holds the Fernet-encrypted password.
    Never store plain-text passwords here.
    """
    __tablename__ = "mt5_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), unique=True, index=True, nullable=False
    )
    mt5_login: Mapped[str] = mapped_column(String(64), nullable=False)
    # Fernet token (URL-safe base64). Max ~512 bytes for a short password.
    password_encrypted: Mapped[str] = mapped_column(String(512), nullable=False)
    server: Mapped[str] = mapped_column(String(128), nullable=False)
    # Optional MetaApi account ID (returned by MetaApi after provisioning)
    metaapi_account_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# UNLOGGED tables for ephemeral/high-write state (rate limits, daily counters)
# These are NOT created via Alembic migrations but via raw DDL at startup.
# Defined here as SQLAlchemy Core Table objects for reference only.
# ---------------------------------------------------------------------------
from sqlalchemy import Table, Column, MetaData, event

_unlogged_meta = MetaData()

# Per-user per-day signal counter (replaces Redis daily counter)
_t_daily_counters = Table(
    "daily_signal_counters",
    _unlogged_meta,
    Column("user_id", BigInteger, nullable=False),
    Column("date", Date, nullable=False),
    Column("count", Integer, nullable=False, default=0),
)

# Per-user rate-limit window tokens
_t_rate_limits = Table(
    "rate_limit_tokens",
    _unlogged_meta,
    Column("user_id", BigInteger, nullable=False),
    Column("window_key", String(64), nullable=False),
    Column("hits", Integer, nullable=False, default=0),
    Column("window_start", DateTime, nullable=False),
)
