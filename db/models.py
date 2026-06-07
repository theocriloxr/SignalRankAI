from __future__ import annotations

from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import uuid4
import logging

from utils.timeutils import now_utc_naive

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    UniqueConstraint,
)
# Lazy-load PostgreSQL UUID dialect to avoid Railway startup crashes
try:
    from sqlalchemy.dialects.postgresql import UUID as PGUUID
except ImportError:
    PGUUID = None
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return now_utc_naive()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(64))
    tier: Mapped[str] = mapped_column(String(16), index=True, default="free")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    referred_by: Mapped[Optional[int]] = mapped_column(BigInteger, index=True)
    fixed_lot_size: Mapped[float] = mapped_column(Float, default=0.01, nullable=False)
    daily_executions_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    daily_executions_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    max_risk_percentage: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    paystack_subscription_code: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    paystack_customer_code: Mapped[Optional[str]] = mapped_column(String(128))
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    referral_count: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    premium_until: Mapped[Optional[datetime]] = mapped_column(DateTime)
    accepted_terms: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    execution_mode: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
    auto_signals_daily_limit: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    max_daily_drawdown_pct: Mapped[float] = mapped_column(Float, default=8.0, nullable=False)
    timezone: Mapped[Optional[str]] = mapped_column(String(64))
    dca_profile: Mapped[Optional[str]] = mapped_column(String(32))


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    tier: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), index=True, nullable=False, default="active")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    paystack_reference: Mapped[Optional[str]] = mapped_column(String(128), unique=True)
    meta: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    bonus_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped[User] = relationship(back_populates="subscriptions")


User.subscriptions = relationship("Subscription", back_populates="user")


class Signal(Base):
    __tablename__ = "signals"

    signal_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    asset: Mapped[str] = mapped_column(String(32), index=True)
    timeframe: Mapped[str] = mapped_column(String(8), index=True)
    direction: Mapped[str] = mapped_column(String(16))
    entry: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float] = mapped_column(Float)
    take_profit: Mapped[str] = mapped_column(Text)
    rr_estimate: Mapped[Optional[float]] = mapped_column(Float)
    score: Mapped[float] = mapped_column(Float)
    regime: Mapped[Optional[str]] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), index=True, default="issued")
    strategy_name: Mapped[str] = mapped_column(String(64))
    strategy_group: Mapped[str] = mapped_column(String(32))
    strength: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
fingerprint: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    ml_probability: Mapped[Optional[float]] = mapped_column(Float)
    expires_at: Mapped[Optional[datetime]]
    expired: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_near_order_block: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # MFE = Maximum Favorable Excursion (how far into profit before closing)
    mfe_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # MAE = Maximum Adverse Excursion (how far into loss before closing)
    mae_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    outcomes = relationship("Outcome", back_populates="signal", cascade="all, delete-orphan")


logger.info("✅ Signal model defined successfully")


class Outcome(Base):
    __tablename__ = "outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    signal_id: Mapped[str] = mapped_column(String(36), ForeignKey("signals.signal_id"), index=True)
    status: Mapped[str] = mapped_column(String(32))
    r_multiple: Mapped[Optional[float]] = mapped_column(Float)
    percent: Mapped[Optional[float]] = mapped_column(Float)
    opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    meta: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    pnl_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    canonical_outcome: Mapped[Optional[str]] = mapped_column(String(16))
    vip_fill_outcome: Mapped[Optional[str]] = mapped_column(String(16))
    sentiment_outcome: Mapped[Optional[str]] = mapped_column(String(16))

    signal: Mapped[Signal] = relationship(back_populates="outcomes")


SignalOutcome = Outcome


class StrategyStat(Base):
    __tablename__ = "strategy_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    strategy_name: Mapped[str] = mapped_column(String(64), index=True)
    strategy_group: Mapped[str] = mapped_column(String(32), index=True)
    trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_r: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    ewma_weight: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AdminEvent(Base):
    __tablename__ = "admin_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    actor_telegram_user_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    details: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AlertPreference(Base):
    __tablename__ = "alert_prefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    tp_sl_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    quiet_start_hour: Mapped[Optional[int]] = mapped_column(Integer)
    quiet_end_hour: Mapped[Optional[int]] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ReferralCode(Base):
    __tablename__ = "referral_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    referrer_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ReferralAttribution(Base):
    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    referred_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    referrer_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    is_successful: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reward_applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    successful_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    referrer_notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class ReferralReward(Base):
    __tablename__ = "referral_rewards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    referrer_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    referred_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    reward_type: Mapped[str] = mapped_column(String(64), index=True)
    reward_value: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class FreeSignalQueue(Base):
    __tablename__ = "free_signal_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime, index=True)
    signal_id: Mapped[str] = mapped_column(String(36), ForeignKey("signals.signal_id"), index=True)
    asset: Mapped[str] = mapped_column(String(32))
    timeframe: Mapped[str] = mapped_column(String(8))
    direction: Mapped[str] = mapped_column(String(8))
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    queued_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    deliver_after: Mapped[datetime] = mapped_column(DateTime, index=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)


class SignalDelivery(Base):
    __tablename__ = "signal_deliveries"
    __table_args__ = (
        UniqueConstraint("user_id", "signal_id", name="uq_signal_delivery_user_signal"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    signal_id: Mapped[str] = mapped_column(String(36), ForeignKey("signals.signal_id"), index=True, nullable=False)
    tier_at_send: Mapped[str] = mapped_column(String(16), default="free", nullable=False)
    delivered_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    sent_ok: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_error: Mapped[Optional[str]] = mapped_column(Text)


class SignalCorrection(Base):
    __tablename__ = "signal_corrections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    original_signal_id: Mapped[str] = mapped_column(String(36), ForeignKey("signals.signal_id"), index=True)
    corrected_signal_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("signals.signal_id"), index=True)
    error_type: Mapped[str] = mapped_column(String(64), index=True)
    error_description: Mapped[str] = mapped_column(Text)
    users_notified: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    correction_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    meta: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)


class SignalEngagement(Base):
    __tablename__ = "signal_engagements"
    __table_args__ = (
        UniqueConstraint("user_id", "signal_id", name="uq_signal_engagement_user_signal"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    signal_id: Mapped[str] = mapped_column(String(36), ForeignKey("signals.signal_id"), index=True, nullable=False)
    reaction: Mapped[str] = mapped_column(String(16), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ActiveSignalMessage(Base):
    __tablename__ = "active_signal_messages"
    __table_args__ = (
        UniqueConstraint("user_id", "signal_id", name="uq_active_signal_msg_user_signal"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    signal_id: Mapped[str] = mapped_column(String(36), ForeignKey("signals.signal_id"), index=True, nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EconomicEvent(Base):
    __tablename__ = "economic_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_date: Mapped[datetime] = mapped_column(DateTime, index=True)
    currency: Mapped[str] = mapped_column(String(8), index=True)
    title: Mapped[str] = mapped_column(String(256))
    impact: Mapped[str] = mapped_column(String(8), default="low")
    source: Mapped[Optional[str]] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MT5Execution(Base):
    __tablename__ = "mt5_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    signal_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("signals.signal_id"))
    metaapi_account_id: Mapped[str] = mapped_column(String(128))
    order_id: Mapped[Optional[str]] = mapped_column(String(128))
    symbol: Mapped[str] = mapped_column(String(32))
    direction: Mapped[str] = mapped_column(String(8))
    lot_size: Mapped[float] = mapped_column(Float)
    entry_price: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float] = mapped_column(Float)
    take_profit: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    tier_at_execution: Mapped[str] = mapped_column(String(16), default="premium")
    realized_pnl: Mapped[Optional[float]] = mapped_column(Float)
    realized_pnl_pct: Mapped[Optional[float]] = mapped_column(Float)
    executed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    meta: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)


class VIPWaitlist(Base):
    __tablename__ = "vip_waitlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    invited_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    invite_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class MT5Credentials(Base):
    __tablename__ = "mt5_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    mt5_login: Mapped[str] = mapped_column(String(64))
    password_encrypted: Mapped[str] = mapped_column(String(512))
    server: Mapped[str] = mapped_column(String(128))
    metaapi_account_id: Mapped[Optional[str]] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    token_prefix: Mapped[str] = mapped_column(String(16))
    scope: Mapped[str] = mapped_column(String(32), default="signals:read")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class UserWebhook(Base):
    __tablename__ = "user_webhooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    webhook_url: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    secret_token: Mapped[Optional[str]] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ProcessedWebhookEvent(Base):
    __tablename__ = "processed_webhook_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(128), unique=True)
    provider: Mapped[str] = mapped_column(String(32), default="paystack")
    event_type: Mapped[str] = mapped_column(String(64))
    reference: Mapped[Optional[str]] = mapped_column(String(128))
    payload_hash: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    meta: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)


class PaymentEvent(Base):
    __tablename__ = "payment_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), default="subscription")
    tier: Mapped[Optional[str]] = mapped_column(String(32))
    duration_days: Mapped[Optional[int]] = mapped_column(Integer)
    plan_code: Mapped[Optional[str]] = mapped_column(String(128))
    amount_ngn: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[Optional[str]] = mapped_column(String(8))
    paystack_reference: Mapped[str] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    meta: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)


class BotEvent(Base):
    __tablename__ = "bot_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    meta: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)


class RuntimeState(Base):
    __tablename__ = "runtime_state"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MarketTick(Base):
    __tablename__ = "market_ticks"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    price: Mapped[float] = mapped_column(Float)
    event_time_ms: Mapped[Optional[int]] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MarketCandle(Base):
    __tablename__ = "market_candles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    timeframe: Mapped[str] = mapped_column(String(8), index=True)
    open_time_ms: Mapped[int] = mapped_column(BigInteger, index=True)
    close_time_ms: Mapped[Optional[int]] = mapped_column(BigInteger)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ProxyNode(Base):
    __tablename__ = "proxy_nodes"

    id: Mapped[PGUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    proxy_url: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fail_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_checked: Mapped[Optional[datetime]] = mapped_column(DateTime, default=utcnow)
    latency_ms: Mapped[Optional[float]] = mapped_column(Float)


class AssetLiveMetric(Base):
    __tablename__ = "asset_live_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset: Mapped[str] = mapped_column(String(32), index=True)
    expectancy: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class StrategyLiveMetric(Base):
    __tablename__ = "strategy_live_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    strategy_name: Mapped[str] = mapped_column(String(64), index=True)
    expectancy: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ManagedAsset(Base):
    __tablename__ = "managed_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True)
    asset_type: Mapped[str] = mapped_column(String(16), default="crypto")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    added_by: Mapped[Optional[int]] = mapped_column(BigInteger)
    note: Mapped[Optional[str]] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_analyzed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class MLShadowPrediction(Base):
    __tablename__ = "ml_shadow_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    signal_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    model_name: Mapped[str] = mapped_column(String(128), index=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(64))
    probability: Mapped[float] = mapped_column(Float)
    is_shadow: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    feature_schema_ok: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    meta: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MLRejectedSignal(Base):
    __tablename__ = "ml_rejected_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset: Mapped[str] = mapped_column(String(32), index=True)
    timeframe: Mapped[str] = mapped_column(String(8), index=True)
    direction: Mapped[str] = mapped_column(String(8))
    entry: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float] = mapped_column(Float)
    take_profit: Mapped[str] = mapped_column(Text)
    ml_probability: Mapped[float] = mapped_column(Float)
    rejection_reason: Mapped[str] = mapped_column(String(128))
    features: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    actual_outcome: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    outcome_tracked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MLPastTrainingData(Base):
    __tablename__ = "ml_past_training_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    signal_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    asset: Mapped[str] = mapped_column(String(32), index=True)
    timeframe: Mapped[str] = mapped_column(String(8), index=True)
    direction: Mapped[str] = mapped_column(String(8))
    entry: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float] = mapped_column(Float)
    take_profit: Mapped[str] = mapped_column(Text)
    rr_estimate: Mapped[Optional[float]] = mapped_column(Float)
    score: Mapped[Optional[float]] = mapped_column(Float)
    strength: Mapped[Optional[float]] = mapped_column(Float)
    regime: Mapped[Optional[str]] = mapped_column(String(32))
    strategy_name: Mapped[Optional[str]] = mapped_column(String(64))
    ml_probability: Mapped[Optional[float]] = mapped_column(Float)
    outcome_status: Mapped[str] = mapped_column(String(16))
    outcome_r_multiple: Mapped[Optional[float]] = mapped_column(Float)
    outcome_percent: Mapped[Optional[float]] = mapped_column(Float)
    outcome_meta: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    signal_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    outcome_closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    archived_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Trade(Base):
    __tablename__ = "trades"

    trade_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    signal_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("signals.signal_id"))
    symbol: Mapped[str] = mapped_column(String(32))
    direction: Mapped[str] = mapped_column(String(8))
    entry_price: Mapped[float] = mapped_column(Float)
    entry_time: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    position_size: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float] = mapped_column(Float)
    take_profit: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")
    exit_price: Mapped[Optional[float]] = mapped_column(Float)
    exit_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    exit_reason: Mapped[Optional[str]] = mapped_column(String(64))
    pnl: Mapped[Optional[float]] = mapped_column(Float)
    pnl_pct: Mapped[Optional[float]] = mapped_column(Float)
    max_drawdown: Mapped[Optional[float]] = mapped_column(Float)
    max_profit: Mapped[Optional[float]] = mapped_column(Float)
    # MFE = Maximum Favorable Excursion (how far into profit before closing)
    mfe_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # MAE = Maximum Adverse Excursion (how far into loss before closing)
    mae_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    partial_exits: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    max_risk_pct: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    atr: Mapped[Optional[float]] = mapped_column(Float)
    trade_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class OutcomeNotification(Base):
    __tablename__ = "outcome_notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    outcome_id: Mapped[int] = mapped_column(ForeignKey("outcomes.id"), index=True, nullable=False)
    signal_id: Mapped[str] = mapped_column(String(36), ForeignKey("signals.signal_id"), index=True, nullable=False)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    tier_at_send: Mapped[str] = mapped_column(String(16), default="free")
    outcome_status: Mapped[str] = mapped_column(String(16), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    delivery_state: Mapped[str] = mapped_column(String(16), default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DecisionLog(Base):
    __tablename__ = "decision_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    signal_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    asset: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    timeframe: Mapped[Optional[str]] = mapped_column(String(8), index=True)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    meta: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
