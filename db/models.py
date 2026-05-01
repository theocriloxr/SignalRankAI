from __future__ import annotations

from datetime import datetime
from typing import Optional, Dict, Any, List
from utils.timeutils import now_utc_naive
from uuid import uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, JSON
import logging
logger = logging.getLogger(__name__)

from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

def utcnow() -> datetime:
    return now_utc_naive()

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    tier: Mapped[str] = mapped_column(String(16), index=True, default="free")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    tier: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), index=True, nullable=False, default="active")
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    user: Mapped['User'] = relationship(back_populates="subscriptions")
User.subscriptions = relationship("Subscription", back_populates="user")

class Signal(Base):
    __tablename__ = "signals"
    signal_id: Mapped[PGUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    asset: Mapped[str] = mapped_column(String(32), index=True)
    timeframe: Mapped[str] = mapped_column(String(8), index=True)
    direction: Mapped[str] = mapped_column(String(16))
    score: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    outcomes = relationship("Outcome", back_populates="signal", cascade="all, delete-orphan")

logger.info("✅ Signal model defined successfully")

class Outcome(Base):
    __tablename__ = "outcomes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    signal_id: Mapped[PGUUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("signals.signal_id"), index=True)
    status: Mapped[str] = mapped_column(String(32))
    r_multiple: Mapped[float] = mapped_column(Float)
    pnl_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    signal: Mapped['Signal'] = relationship(back_populates="outcomes")

class DecisionLog(Base):
    __tablename__ = "decision_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    signal_id: Mapped[Optional[str]] = mapped_column(String(64))
    asset: Mapped[Optional[str]] = mapped_column(String(32))
    decision: Mapped[str] = mapped_column(String(32))
    reason: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

class MarketTick(Base):
    __tablename__ = "market_ticks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset: Mapped[str] = mapped_column(String(32), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    price: Mapped[float] = mapped_column(Float)

class MarketCandle(Base):
    __tablename__ = "market_candles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset: Mapped[str] = mapped_column(String(32), index=True)
    timeframe: Mapped[str] = mapped_column(String(8), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)

class ProcessedWebhookEvent(Base):
    __tablename__ = "processed_webhook_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    event_id: Mapped[str] = mapped_column(String(128), index=True)
    payload_hash: Mapped[str] = mapped_column(String(64), index=True)

class ApiToken(Base):
    __tablename__ = "api_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    scope: Mapped[str] = mapped_column(String(64), default="signals:read")
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    user: Mapped['User'] = relationship()

class ProxyNode(Base):
    __tablename__ = "proxy_nodes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proxy_url: Mapped[str] = mapped_column(String(512), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    last_checked: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

# Live Metrics
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

