from __future__ import annotations

from datetime import datetime
from typing import Optional, Dict, Any
from utils.timeutils import now_utc_naive
from uuid import uuid4, UUID as PythonUUID

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Table, Column, MetaData
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from typing import Final

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
    # Auto-trade safety guard: if today's realized drawdown hits this threshold,
    # auto-execution is paused for the rest of the day.
    max_daily_drawdown_pct: Mapped[float] = mapped_column(Float, nullable=False, default=8.0)
    # Broker execution routing mode: none | manual | auto
    execution_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="manual", index=True)
    # Daily auto-execution cap for AUTO mode (0 means disabled, -1 means unlimited)
    auto_signals_daily_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=-1)

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
    subscriptions: Mapped[list['Subscription']] = relationship(back_populates="user")  # type: ignore[name-defined]

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

    user: Mapped['User'] = relationship(back_populates="subscriptions")

# ... (all other existing models unchanged - PaymentEvent, ProcessedWebhookEvent, ApiToken, UserWebhook, MLShadowPrediction, BotEvent, Signal, MarketTick, MarketCandle, Outcome, OutcomeNotification, Trade, StrategyStat, AdminEvent, AlertPreference, ReferralCode, ReferralAttribution, ReferralReward, FreeSignalQueue, SignalDelivery, SignalCorrection, RuntimeState, MLRejectedSignal, MLPastTrainingData, DecisionLog, SignalEngagement, ActiveSignalMessage, EconomicEvent, MT5Execution, VIPWaitlist, ManagedAsset, MT5Credentials, ProxyNode, _unlogged tables ...)

# NEW: Phase 3 Live Metrics for Expectancy Gate
class AssetLiveMetric(Base):
    __tablename__ = "asset_live_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), index=True, nullable=False)
    
    # Rolling 7-day metrics
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    win_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_r: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_win_r: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_loss_r: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    
    expectancy: Mapped[float] = mapped_column(Float, index=True, nullable=False, default=0.0)
    
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True, nullable=False)

class StrategyLiveMetric(Base):
    __tablename__ = "strategy_live_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_name: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    strategy_group: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    
    # Rolling metrics
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    win_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expectancy: Mapped[float] = mapped_column(Float, index=True, nullable=False, default=0.0)
    
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True, nullable=False)

