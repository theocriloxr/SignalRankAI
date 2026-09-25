"""
MT5 Signal Router - Signal to MT5 Execution Routing

This module provides:
- Routes signals from signal generator to MT5 for automated execution
- Handles tier-based execution (manual, auto, none)
- Returns trade sync back to paper ledger
- Multi-account support per user (VIP)
- Position sizing based on account equity and risk parameters

Usage:
    from services.mt5_signal_router import MT5SignalRouter
    
    router = MT5SignalRouter()
    result = await router.route_signal(signal, user_id, execution_mode="auto")
"""

import logging
import os
import hashlib
import math
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
import asyncio
import json
import contextlib

logger = logging.getLogger("MT5SignalRouter")

# Execution modes
class ExecutionMode:
    MANUAL = "manual"   # User receives instructions and executes outside the bot
    MANUAL_CONFIRMED = "manual_confirmed"  # Authenticated one-click request
    AUTO = "auto"       # Auto-execute via MT5 after persisted opt-in
    COPY_TRADE = "copy_trade"
    NONE = "none"       # No execution, just signals


@dataclass
class ExecutionRequest:
    """Signal execution request."""
    signal_id: str
    user_id: int
    asset: str
    direction: str  # long/short
    entry: float
    stop_loss: float
    take_profit: List[float]
    volume: float
    execution_mode: str
    tier: str  # user's tier at time of execution
    created_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """Result of execution attempt."""
    success: bool
    message: str
    order_id: Optional[str] = None
    executed_at: Optional[datetime] = None
    error: Optional[str] = None


class MT5SignalRouter:
    """
    Routes signals to MT5 for automated execution.
    
    Features:
    - Tier-based execution control (manual/auto/none)
    - Position sizing based on account equity
    - Risk-based lot calculation
    - Paper ledger sync for non-executed trades
    - Multi-account support (VIP)
    """
    
    def __init__(self, *, execution_gate: Any | None = None):
        from execution.service import ExecutionGate

        try:
            queue_size = max(1, int(os.getenv("MT5_EXECUTION_QUEUE_SIZE", "100") or 100))
        except (TypeError, ValueError):
            queue_size = 100
        self._execution_queue: asyncio.Queue[tuple[ExecutionRequest, asyncio.Future[ExecutionResult]] | None] = (
            asyncio.Queue(maxsize=queue_size)
        )
        self._processing = False
        self._worker_task: asyncio.Task[None] | None = None
        self._execution_gate = execution_gate or ExecutionGate()

    @staticmethod
    def _utc_now_naive() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _parse_take_profit(value: Any) -> list[float]:
        if value is None:
            return []
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []
            try:
                return MT5SignalRouter._parse_take_profit(json.loads(raw))
            except Exception:
                parts = [p.strip() for p in raw.split(",") if p.strip()]
                out = []
                for part in parts:
                    try:
                        out.append(float(part))
                    except Exception:
                        continue
                return out
        if isinstance(value, dict):
            candidate = value.get("price") or value.get("tp") or value.get("target") or value.get("value")
            try:
                return [float(candidate)] if candidate is not None else []
            except Exception:
                return []
        if isinstance(value, (list, tuple)):
            out: list[float] = []
            for item in value:
                out.extend(MT5SignalRouter._parse_take_profit(item))
            return out
        try:
            return [float(value)]
        except Exception:
            return []

    @staticmethod
    def _validate_signal(signal: Dict[str, Any]) -> tuple[bool, str]:
        asset = str(signal.get("asset") or signal.get("symbol") or "").upper().strip()
        direction = str(signal.get("direction") or signal.get("side") or "").lower().strip()
        try:
            entry = float(signal.get("entry") or 0)
            stop_loss = float(signal.get("stop_loss") or signal.get("stop") or 0)
        except Exception:
            return False, "entry and stop_loss must be numeric"
        tps = MT5SignalRouter._parse_take_profit(signal.get("take_profit") or signal.get("targets"))
        if not asset:
            return False, "asset is required"
        if direction not in {"long", "short", "buy", "sell"}:
            return False, "direction must be long/short"
        if entry <= 0:
            return False, "entry must be positive"
        if stop_loss <= 0:
            return False, "broker execution requires a hard stop_loss"
        if not tps or tps[0] <= 0:
            return False, "at least one take_profit is required"
        if direction in {"long", "buy"} and stop_loss >= entry:
            return False, "long stop_loss must be below entry"
        if direction in {"short", "sell"} and stop_loss <= entry:
            return False, "short stop_loss must be above entry"
        return True, ""

    @staticmethod
    def _reservation_key(idempotency_key: str) -> str:
        digest = hashlib.sha256(str(idempotency_key).encode("utf-8")).hexdigest()
        return f"broker_exec:{digest}"

    async def _reserve_execution_once(
        self,
        idempotency_key: str,
        *,
        user_id: int,
        signal_id: str,
    ) -> bool:
        """Atomically reserve a broker request in PostgreSQL.

        A cache get followed by cache set races under concurrent callbacks.
        ``runtime_state.key`` is a primary key, so this one-statement upsert is
        atomic across coroutines, workers, and restarts. Database uncertainty
        blocks execution.
        """
        if not str(idempotency_key or "").strip() or not str(signal_id or "").strip():
            return False
        try:
            ttl = max(
                300,
                int(os.getenv("BROKER_EXEC_IDEMPOTENCY_SECONDS", "86400") or 86400),
            )
        except (TypeError, ValueError):
            ttl = 86400
        expires_at = self._utc_now_naive() + timedelta(seconds=ttl)
        payload = json.dumps(
            {
                "status": "reserved",
                "user_id": int(user_id),
                "signal_id": str(signal_id),
                "idempotency_key": str(idempotency_key),
                "reserved_at": self._utc_now_naive().isoformat(),
            },
            separators=(",", ":"),
        )
        try:
            from db.session import get_session
            from sqlalchemy import text

            async with get_session() as session:
                result = await session.execute(
                    text(
                        """
                        INSERT INTO runtime_state(key, value, expires_at, updated_at)
                        VALUES (:key, CAST(:value AS JSONB), :expires_at, NOW())
                        ON CONFLICT (key) DO UPDATE
                        SET value = EXCLUDED.value,
                            expires_at = EXCLUDED.expires_at,
                            updated_at = NOW()
                        WHERE runtime_state.expires_at IS NOT NULL
                          AND runtime_state.expires_at <= NOW()
                        RETURNING key
                        """
                    ),
                    {
                        "key": self._reservation_key(idempotency_key),
                        "value": payload,
                        "expires_at": expires_at,
                    },
                )
                row = result.fetchone()
                await session.commit()
            return bool(row)
        except Exception:
            logger.warning(
                "[SignalRouter] durable execution reservation unavailable; blocking",
                exc_info=True,
            )
            return False

    async def _record_execution_reservation(
        self,
        idempotency_key: str,
        *,
        status: str,
        order_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update reservation evidence without affecting the broker outcome."""
        try:
            from db.session import get_session
            from sqlalchemy import text

            payload = json.dumps(
                {
                    "status": str(status),
                    "order_id": str(order_id) if order_id else None,
                    "error": str(error)[:240] if error else None,
                    "updated_at": self._utc_now_naive().isoformat(),
                },
                separators=(",", ":"),
            )
            async with get_session() as session:
                await session.execute(
                    text(
                        """
                        UPDATE runtime_state
                        SET value = runtime_state.value || CAST(:value AS JSONB),
                            updated_at = NOW()
                        WHERE key = :key
                        """
                    ),
                    {
                        "key": self._reservation_key(idempotency_key),
                        "value": payload,
                    },
                )
                await session.commit()
        except Exception:
            logger.warning(
                "[SignalRouter] failed to update execution reservation evidence",
                exc_info=True,
            )

    @staticmethod
    def _resource_pressure_clear() -> bool:
        """Block new broker orders when the runtime reports critical pressure."""
        values = (
            os.getenv("RESOURCE_PRESSURE_LEVEL"),
            os.getenv("RESOURCE_GOVERNOR_STATE"),
            os.getenv("SIGNALRANK_RESOURCE_PRESSURE"),
        )
        blocked = {"critical", "blocked", "stop", "oom", "overloaded"}
        if any(str(value or "").strip().lower() in blocked for value in values):
            return False
        try:
            from core.resource_governor import get_resource_governor

            return bool(
                get_resource_governor().policy.real_execution_allowed
            )
        except Exception:
            logger.warning(
                "[SignalRouter] resource governor unavailable; blocking execution",
                exc_info=True,
            )
            return False

    async def _get_user_profile_policy(
        self,
        user_id: int,
        signal: Dict[str, Any],
        requested_execution_mode: str,
        user_identity: str = "telegram",
    ) -> Dict[str, Any]:
        """Evaluate the canonical user profile before any broker-side work."""
        result: Dict[str, Any] = {
            "allowed": False,
            "reason": "profile_unavailable",
            "max_concurrent_positions": 0,
        }
        try:
            from db.models import BrokerExecution, MT5Execution, User
            from db.session import get_session
            from services.user_intelligence import (
                get_platform_user_trading_preferences,
                signal_matches_preferences,
            )
            from sqlalchemy import func, select

            async with get_session(label="mt5.profile_policy", timeout_seconds=8.0) as session:
                identity = str(user_identity or "telegram").strip().lower()
                user_filter = (
                    User.id == int(user_id)
                    if identity == "platform"
                    else User.telegram_user_id == int(user_id)
                )
                user = (await session.execute(
                    select(User).where(user_filter).limit(1)
                )).scalar_one_or_none()
                if user is None:
                    return {**result, "reason": "user_profile_missing"}
                prefs = await get_platform_user_trading_preferences(session, int(user.id))
                profile_ok, profile_reason = signal_matches_preferences(signal, prefs)
                if not profile_ok:
                    return {**result, "reason": f"signal_profile_mismatch:{profile_reason}"}
                if str(prefs.trading_mode or "paper").lower() not in {"live", "both"}:
                    return {**result, "reason": "profile_live_disabled"}
                requested = str(requested_execution_mode or "").strip().lower()
                configured = str(prefs.execution_mode or "manual").strip().lower()
                if requested in {ExecutionMode.COPY_TRADE, "copy"} and configured != "copy_trade":
                    return {**result, "reason": "profile_copy_disabled"}
                if requested in {ExecutionMode.AUTO, "live"} and configured not in {"auto", "live"}:
                    return {**result, "reason": "profile_auto_disabled"}
                if requested == ExecutionMode.MANUAL_CONFIRMED and configured not in {
                    "manual", "manual_confirmed", "semi_auto"
                }:
                    return {**result, "reason": "profile_manual_confirmation_disabled"}
                provider = str(prefs.execution_provider or "auto").strip().lower()
                if provider not in {"auto", "mt4", "mt5", "metaapi"}:
                    return {**result, "reason": "profile_provider_mismatch"}

                open_statuses = ("pending", "submitted", "confirmed", "open", "submitting", "ambiguous", "reconciliation_pending")
                mt5_open = int((await session.execute(
                    select(func.count(MT5Execution.id)).where(
                        MT5Execution.user_id == int(user.id),
                        func.lower(MT5Execution.status).in_(open_statuses),
                    )
                )).scalar_one() or 0)
                bybit_open = int((await session.execute(
                    select(func.count(BrokerExecution.id)).where(
                        BrokerExecution.user_id == int(user.id),
                        func.lower(BrokerExecution.status).in_(open_statuses),
                    )
                )).scalar_one() or 0)
                asset = str(signal.get("asset") or signal.get("symbol") or "").upper().strip()
                duplicate_mt5 = int((await session.execute(
                    select(func.count(MT5Execution.id)).where(
                        MT5Execution.user_id == int(user.id),
                        MT5Execution.symbol == asset,
                        func.lower(MT5Execution.status).in_(open_statuses),
                    )
                )).scalar_one() or 0) > 0
                duplicate_bybit = int((await session.execute(
                    select(func.count(BrokerExecution.id)).where(
                        BrokerExecution.user_id == int(user.id),
                        BrokerExecution.symbol == asset,
                        func.lower(BrokerExecution.status).in_(open_statuses),
                    )
                )).scalar_one() or 0) > 0
                if duplicate_mt5 or duplicate_bybit:
                    return {**result, "reason": "duplicate_open_asset"}
                maximum = max(1, int(prefs.max_concurrent_positions or 1))
                if mt5_open + bybit_open >= maximum:
                    return {
                        **result,
                        "reason": "profile_max_concurrent_positions",
                        "max_concurrent_positions": maximum,
                    }
                return {
                    "allowed": True,
                    "reason": "ok",
                    "max_concurrent_positions": maximum,
                    "risk_per_trade_pct": float(prefs.risk_per_trade_pct),
                    "trade_profile": prefs.trade_profile,
                    "risk_profile": prefs.risk_profile,
                    "execution_provider": provider,
                }
        except Exception:
            logger.warning("[SignalRouter] canonical user profile unavailable; blocking", exc_info=True)
            return result

    async def _get_user_execution_policy(
        self,
        user_id: int,
        account_id: str,
        requested_execution_mode: str,
        user_identity: str = "telegram",
        broker_platform: str = "mt5",
        connection_id: str | None = None,
    ) -> Dict[str, Any]:
        """Load terms, mode, explicit opt-in and secured broker credentials."""
        policy: Dict[str, Any] = {
            "found": False,
            "accepted_terms": False,
            "consent": False,
            "user_enabled": False,
            "credentials_encrypted": False,
            "connection_execution_enabled": False,
            "mode": "",
            "platform": str(broker_platform or "mt5").lower(),
        }
        requested = str(requested_execution_mode or "").strip().lower()
        platform = str(broker_platform or "mt5").strip().lower()
        try:
            from db.models import (
                BrokerConnection,
                BrokerReconciliationState,
                MT5Credentials,
                RuntimeState,
                TradingAccountPolicyRecord,
                User,
            )
            from db.session import get_session
            from services.security import decrypt_secret, is_encryption_available
            from sqlalchemy import select

            async with get_session(label="metatrader.execution_policy", timeout_seconds=8.0) as session:
                identity = str(user_identity or "telegram").strip().lower()
                user_filter = (
                    User.id == int(user_id)
                    if identity == "platform"
                    else User.telegram_user_id == int(user_id)
                )
                user = (
                    await session.execute(
                        select(User).where(user_filter).limit(1)
                    )
                ).scalar_one_or_none()
                if user is None:
                    return policy
                canonical_id = int(user.id)
                telegram_id = (
                    int(user.telegram_user_id)
                    if user.telegram_user_id is not None
                    else None
                )
                accepted_terms = bool(user.accepted_terms)
                stored_mode = str(user.execution_mode or "").strip().lower()

                query = select(BrokerConnection).where(
                            BrokerConnection.user_id == canonical_id,
                            BrokerConnection.connector == "metaapi",
                            BrokerConnection.platform == platform,
                            BrokerConnection.external_account_id == str(account_id),
                        )
                if connection_id is not None:
                    query = query.where(BrokerConnection.connection_id == connection_id)
                connections = (await session.execute(query.limit(2))).scalars().all()
                connection = connections[0] if len(connections) == 1 else None

                credentials_valid = False
                connection_execution_enabled = False
                if connection is not None:
                    from services.broker_connections import account_classification, execution_connection_error
                    from services.account_policies import public_account_policy

                    policy["canonical_user_id"] = canonical_id
                    policy["connection_id"] = str(connection.connection_id)
                    policy["account_classification"] = account_classification(connection)

                    account_policy_row = (
                        await session.execute(
                            select(TradingAccountPolicyRecord).where(
                                TradingAccountPolicyRecord.user_id == canonical_id,
                                TradingAccountPolicyRecord.connection_id == str(connection.connection_id),
                            ).limit(1)
                        )
                    ).scalar_one_or_none()
                    reconciliation_row = await session.get(
                        BrokerReconciliationState,
                        str(connection.connection_id),
                    )
                    policy["account_policy"] = (
                        public_account_policy(account_policy_row)
                        if account_policy_row is not None
                        else None
                    )
                    policy["reconciliation_status"] = (
                        str(reconciliation_row.status).upper()
                        if reconciliation_row is not None
                        else "UNKNOWN"
                    )

                    auth_mode = str(connection.auth_mode or "").strip().lower()
                    provider_managed = auth_mode == "provider_secure_link"
                    locally_encrypted = bool(
                        connection.secret_encrypted
                        and is_encryption_available()
                        and decrypt_secret(str(connection.secret_encrypted))
                    )
                    credentials_valid = bool(
                        str(connection.external_account_id or "").strip()
                        == str(account_id).strip()
                        and (provider_managed or locally_encrypted)
                    )
                    connection_execution_enabled = execution_connection_error(connection, canonical_id) is None

                # Backward-compatible MT5 credential proof while legacy rows are
                # being migrated into broker_connections.
                if connection is None and platform == "mt5":
                    legacy = (
                        await session.execute(
                            select(MT5Credentials).where(
                                MT5Credentials.user_id == canonical_id
                            ).limit(1)
                        )
                    ).scalar_one_or_none()
                    if legacy is not None:
                        credentials_valid = bool(
                            legacy.password_encrypted
                            and legacy.metaapi_account_id
                            and str(legacy.metaapi_account_id).strip()
                            == str(account_id).strip()
                            and is_encryption_available()
                            and decrypt_secret(str(legacy.password_encrypted))
                        )
                        # Legacy connection rows are deliberately not auto-enabled.
                        connection_execution_enabled = False

                if identity == "platform":
                    optin_keys = (
                        f"autoexec_platform_optin:{canonical_id}",
                        f"copyexec_platform_optin:{canonical_id}",
                    )
                else:
                    optin_keys = (
                        f"autoexec_user_optin:{int(user_id)}",
                        f"copyexec_user_optin:{int(user_id)}",
                    )
                optins = {}
                if optin_keys:
                    rows = (
                        await session.execute(
                            select(RuntimeState.key, RuntimeState.value).where(
                                RuntimeState.key.in_(optin_keys)
                            )
                        )
                    ).all()
                    optins = {
                        str(item[0]): item[1]
                        for item in rows
                        if item and len(item) >= 2
                    }

            if requested == ExecutionMode.COPY_TRADE:
                optin = optins.get(
                    f"copyexec_platform_optin:{canonical_id}"
                    if identity == "platform"
                    else f"copyexec_user_optin:{int(user_id)}"
                )
                explicit_mode_optin = bool(
                    isinstance(optin, dict) and optin.get("enabled") is True
                )
                mode_enabled = stored_mode == ExecutionMode.COPY_TRADE
                user_enabled = bool(mode_enabled and connection_execution_enabled)
                consent = bool(
                    accepted_terms
                    and user_enabled
                    and explicit_mode_optin
                )
            elif requested in {ExecutionMode.AUTO, "live"}:
                optin = optins.get(
                    f"autoexec_platform_optin:{canonical_id}"
                    if identity == "platform"
                    else f"autoexec_user_optin:{int(user_id)}"
                )
                explicit_mode_optin = bool(
                    isinstance(optin, dict) and optin.get("enabled") is True
                )
                mode_enabled = stored_mode in {ExecutionMode.AUTO, "live"}
                user_enabled = bool(mode_enabled and connection_execution_enabled)
                consent = bool(
                    accepted_terms
                    and user_enabled
                    and explicit_mode_optin
                )
            elif requested == ExecutionMode.MANUAL_CONFIRMED:
                mode_enabled = stored_mode in {
                    ExecutionMode.MANUAL,
                    ExecutionMode.MANUAL_CONFIRMED,
                    "semi_auto",
                }
                user_enabled = bool(mode_enabled and connection_execution_enabled)
                consent = bool(accepted_terms and user_enabled)
            else:
                user_enabled = False
                consent = False

            policy.update(
                {
                    "found": True,
                    "accepted_terms": accepted_terms,
                    "consent": consent,
                    "user_enabled": user_enabled,
                    "credentials_encrypted": credentials_valid,
                    "connection_execution_enabled": connection_execution_enabled,
                    "mode": stored_mode,
                    "platform": platform,
                }
            )
        except Exception:
            logger.warning(
                "[SignalRouter] user execution policy unavailable; blocking",
                exc_info=True,
            )
        return policy

    async def _reserve_user_execution_quota(
        self,
        user_id: int,
        *,
        tier: str,
        execution_mode: str,
        user_identity: str = "telegram",
    ) -> tuple[bool, str, int | None]:
        """Delegate every channel to one canonical quota/drawdown ledger."""
        from services.execution_quota import (
            reserve_platform_user_execution_quota,
            reserve_user_execution_quota,
        )

        if str(user_identity or "telegram").strip().lower() == "platform":
            return await reserve_platform_user_execution_quota(
                int(user_id),
                tier=tier,
                execution_mode=execution_mode,
            )
        return await reserve_user_execution_quota(
            int(user_id),
            tier=tier,
            execution_mode=execution_mode,
        )

    async def _release_user_execution_quota(self, user_db_id: int | None) -> None:
        """Release only a definite pre-order rejection through the shared ledger."""
        from services.execution_quota import release_user_execution_quota

        await release_user_execution_quota(user_db_id)

    async def _record_execution_ledger(
        self,
        *,
        user_id: int,
        signal: Dict[str, Any],
        account_id: str,
        order_id: str,
        volume: float,
        tier: str,
        execution_mode: str,
        idempotency_key: str,
        broker_result: Dict[str, Any],
        user_identity: str = "telegram",
        broker_platform: str = "mt5",
    ) -> bool:
        """Persist one canonical MT5Execution row after broker acknowledgement."""
        try:
            from db.models import MT5Execution, User
            from db.session import get_session
            from sqlalchemy import select

            order = str(order_id or "").strip()
            if not order:
                return False
            signal_id = str(
                signal.get("signal_id") or signal.get("id") or ""
            ).strip() or None
            symbol = str(
                signal.get("asset") or signal.get("symbol") or ""
            ).upper().strip()
            raw_direction = str(
                signal.get("direction") or signal.get("side") or ""
            ).lower().strip()
            direction = "long" if raw_direction in {"long", "buy"} else "short"
            take_profit = self._parse_take_profit(
                signal.get("take_profit") or signal.get("targets")
            )
            entry = float(
                broker_result.get("live_price")
                or broker_result.get("price")
                or signal.get("entry")
                or 0
            )
            stop = float(signal.get("stop_loss") or signal.get("stop") or 0)
            identity = str(user_identity or "telegram").strip().lower()
            meta = {
                "source": "canonical_metatrader_signal_router",
                "broker_platform": str(broker_platform or "mt5").lower(),
                "execution_mode": str(execution_mode),
                "user_identity": identity,
                "request_user_id": int(user_id),
                "idempotency_key": str(idempotency_key),
                "hard_stop_attached": bool(
                    broker_result.get("hard_stop_attached", True)
                ),
                "broker_response_status": str(
                    broker_result.get("status") or "submitted"
                ),
            }
            async with get_session() as session:
                user_filter = (
                    User.id == int(user_id)
                    if identity == "platform"
                    else User.telegram_user_id == int(user_id)
                )
                user = (
                    await session.execute(
                        select(User).where(user_filter).limit(1)
                    )
                ).scalar_one_or_none()
                if user is None:
                    return False
                existing = (
                    await session.execute(
                        select(MT5Execution)
                        .where(
                            MT5Execution.metaapi_account_id == str(account_id),
                            MT5Execution.order_id == order,
                        )
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    return True
                session.add(
                    MT5Execution(
                        user_id=int(user.id),
                        signal_id=signal_id,
                        metaapi_account_id=str(account_id),
                        order_id=order,
                        symbol=symbol,
                        direction=direction,
                        lot_size=float(volume),
                        entry_price=entry,
                        stop_loss=stop,
                        take_profit=json.dumps(take_profit),
                        status="open",
                        tier_at_execution=str(tier or "FREE").upper(),
                        executed_at=self._utc_now_naive(),
                        meta=meta,
                    )
                )
                await session.commit()
                return True
        except Exception:
            logger.exception(
                "[SignalRouter] broker acknowledged but execution ledger persistence failed"
            )
            return False

    async def _has_execution_evidence(
        self,
        user_id: int,
        signal_id: str,
        user_identity: str = "telegram",
    ) -> bool:
        """Require channel-authentic access evidence before broker execution."""
        if not str(signal_id or "").strip():
            return False
        try:
            from db.session import get_session
            from services.execution_evidence import (
                get_execution_evidence,
                get_platform_execution_evidence,
            )

            async with get_session() as session:
                if str(user_identity or "telegram").strip().lower() == "platform":
                    evidence = await get_platform_execution_evidence(
                        session,
                        user_id=int(user_id),
                        signal_id=str(signal_id),
                    )
                    return bool(evidence.get("access_proven"))
                evidence = await get_execution_evidence(
                    session,
                    telegram_user_id=int(user_id),
                    signal_id=str(signal_id),
                )
                return bool(evidence.get("delivery_proven"))
        except Exception:
            logger.warning(
                "[SignalRouter] execution evidence unavailable; blocking",
                exc_info=True,
            )
            return False
        
    async def initialize(self) -> bool:
        """Initialize one bounded execution worker."""
        if self._processing and self._worker_task and not self._worker_task.done():
            return True
        self._processing = True
        self._worker_task = asyncio.create_task(
            self._process_execution_loop(),
            name="mt5-execution-router",
        )
        logger.info("[SignalRouter] Initialized queue_size=%s", self._execution_queue.maxsize)
        return True

    async def enqueue_execution(
        self,
        request: ExecutionRequest,
        *,
        enqueue_timeout: float = 1.0,
        result_timeout: float = 60.0,
    ) -> ExecutionResult:
        """Queue one request and await its bounded result.

        The queue is deliberately small and single-owned.  This prevents the
        old implementation from spawning an unbounded task for every request.
        """
        if not self._processing:
            await self.initialize()
        loop = asyncio.get_running_loop()
        future: asyncio.Future[ExecutionResult] = loop.create_future()
        try:
            await asyncio.wait_for(
                self._execution_queue.put((request, future)),
                timeout=max(0.05, float(enqueue_timeout)),
            )
        except asyncio.TimeoutError:
            return ExecutionResult(
                success=False,
                message="Broker execution queue is full",
                error="execution_queue_full",
            )
        try:
            return await asyncio.wait_for(
                asyncio.shield(future),
                timeout=max(0.1, float(result_timeout)),
            )
        except asyncio.TimeoutError:
            return ExecutionResult(
                success=False,
                message="Broker execution did not complete before timeout",
                error="execution_result_timeout",
            )
    
    async def route_signal(
        self,
        signal: Dict[str, Any],
        user_id: int,
        execution_mode: str = "manual",
        *,
        user_identity: str = "telegram",
        broker_platform: str = "mt5",
        connection_id: str | None = None,
    ) -> ExecutionResult:
        """
        Route signal to appropriate execution handler.
        
        Args:
            signal: Signal dict with asset, direction, entry, stop_loss, take_profit
            user_id: Telegram user ID by default, or canonical users.id for platform identity
            execution_mode: manual, auto, or none
            
        Returns:
            ExecutionResult with success status and details
        """
        try:
            valid, reason = self._validate_signal(signal or {})
            if not valid:
                return ExecutionResult(success=False, message=reason, error=reason)

            execution_mode = str(execution_mode or ExecutionMode.NONE).strip().lower()
            if execution_mode == "copy":
                execution_mode = ExecutionMode.COPY_TRADE
            if execution_mode == ExecutionMode.NONE:
                return ExecutionResult(
                    success=False,
                    message="Execution disabled - signals only",
                )
            if execution_mode == ExecutionMode.MANUAL:
                return ExecutionResult(
                    success=True,
                    message=(
                        f"Execute manually: {signal.get('asset')} "
                        f"{str(signal.get('direction') or '').upper()} "
                        f"@ {signal.get('entry')} SL {signal.get('stop_loss')}"
                    ),
                )
            if execution_mode not in {
                ExecutionMode.MANUAL_CONFIRMED,
                ExecutionMode.AUTO,
                ExecutionMode.COPY_TRADE,
            }:
                return ExecutionResult(
                    success=False,
                    message="Unsupported or non-live execution mode",
                    error="execution_mode_not_live",
                )

            # Return the master-switch reason before loading broker credentials or
            # user profile state. This is both cheaper and operationally clearer.
            flags = self._execution_gate.safety_flags
            master_reasons: list[str] = []
            if execution_mode in {ExecutionMode.AUTO, ExecutionMode.COPY_TRADE}:
                if not flags.auto_execution_enabled:
                    master_reasons.append("AUTO_EXECUTION_DISABLED")
            if execution_mode == ExecutionMode.AUTO and not flags.auto_trade_enabled:
                master_reasons.append("AUTO_TRADE_DISABLED")
            if execution_mode == ExecutionMode.COPY_TRADE and not flags.copy_trade_enabled:
                master_reasons.append("COPY_TRADE_DISABLED")
            if master_reasons:
                reason = ", ".join(master_reasons)
                return ExecutionResult(
                    success=False,
                    message=f"Execution blocked: {reason}",
                    error=reason,
                )

            signal_id = str(
                signal.get("signal_id") or signal.get("id") or ""
            ).strip()
            identity = str(user_identity or "telegram").strip().lower()
            platform = str(broker_platform or "mt5").strip().lower()
            if platform not in {"mt4", "mt5"}:
                return ExecutionResult(
                    success=False,
                    message="Unsupported MetaTrader platform",
                    error="unsupported_metatrader_platform",
                )
            if identity not in {"telegram", "platform"}:
                return ExecutionResult(
                    success=False,
                    message="Unsupported execution identity",
                    error="unsupported_execution_identity",
                )
            tier = (
                await self._get_platform_user_tier(user_id)
                if identity == "platform"
                else self._get_user_tier(user_id)
            )
            mt5_account_id = await self._get_user_mt5_account(
                user_id,
                user_identity=identity,
                broker_platform=platform,
                connection_id=connection_id,
            )
            if not mt5_account_id:
                return ExecutionResult(
                    success=False,
                    message=f"No {platform.upper()} account is ready for execution",
                    error="broker_account_not_ready",
                )

            from core.redis_state import state
            from execution.service import ExecutionRequest as GateRequest
            from services.market_intelligence import evaluate_market
            from services.mt5_client import (
                get_account_info,
                get_live_quote,
                get_reconciliation_snapshot,
                get_symbol_specification,
            )

            asset = str(signal.get("asset") or signal.get("symbol") or "").upper()
            account_info, symbol_spec, quote, policy, profile_policy, evidence = await asyncio.gather(
                get_account_info(mt5_account_id),
                get_symbol_specification(mt5_account_id, asset),
                get_live_quote(mt5_account_id, asset),
                self._get_user_execution_policy(
                    user_id,
                    mt5_account_id,
                    execution_mode,
                    user_identity=identity,
                    broker_platform=platform,
                    connection_id=connection_id,
                ),
                self._get_user_profile_policy(
                    user_id,
                    signal,
                    execution_mode,
                    user_identity=identity,
                ),
                self._has_execution_evidence(
                    user_id,
                    str(signal.get("evidence_signal_id") or signal_id),
                    user_identity=identity,
                ),
            )
            if not bool(profile_policy.get("allowed")):
                return ExecutionResult(
                    success=False,
                    message=f"Execution blocked by user profile: {profile_policy.get('reason')}",
                    error=str(profile_policy.get("reason") or "profile_policy_blocked"),
                )
            reconciliation = await get_reconciliation_snapshot(
                mt5_account_id,
                account_info=account_info,
            )
            try:
                kill_state = await state.get_killswitch()
                kill_switch = bool(getattr(kill_state, "enabled", True))
            except Exception:
                # Inability to establish kill-switch clearance is itself a
                # block; never infer "clear" from an unavailable backend.
                kill_switch = True

            volume = await self._calculate_position_size(
                user_id=user_id,
                entry=signal.get("entry", 0),
                stop_loss=signal.get("stop_loss", 0),
                account_id=mt5_account_id,
                tier=tier,
                account_info=account_info,
                symbol_spec=symbol_spec,
                symbol=asset,
                user_identity=identity,
                execution_mode=execution_mode,
            )
            volume = self._apply_position_weight(
                volume,
                signal.get("position_weight", 1.0),
                symbol_spec,
            )

            market = evaluate_market(asset, signal=signal)
            requested_mode = str(policy.get("mode") or "").strip().lower()
            if execution_mode == ExecutionMode.COPY_TRADE:
                user_enabled = requested_mode == ExecutionMode.COPY_TRADE
            elif execution_mode == ExecutionMode.MANUAL_CONFIRMED:
                user_enabled = requested_mode in {
                    ExecutionMode.MANUAL,
                    ExecutionMode.MANUAL_CONFIRMED,
                    "semi_auto",
                }
            else:
                user_enabled = requested_mode in {ExecutionMode.AUTO, "live"}
            account_ready = bool(
                isinstance(account_info, dict)
                and account_info.get("connected") is True
                and isinstance(account_info.get("equity"), (int, float))
                and float(account_info["equity"]) > 0
                and isinstance(account_info.get("free_margin"), (int, float))
                and float(account_info["free_margin"]) > 0
            )
            account_is_demo = (
                account_info.get("is_demo")
                if isinstance(account_info, dict)
                and isinstance(account_info.get("is_demo"), bool)
                else None
            )
            quote_trusted = bool(
                isinstance(quote, dict)
                and quote.get("provider") == "metaapi"
                and quote.get("trusted") is True
            )
            quote_age = quote.get("age_seconds") if isinstance(quote, dict) else None
            max_quote_age = (
                quote.get("max_age_seconds", 15.0)
                if isinstance(quote, dict)
                else 15.0
            )
            symbol_ready = bool(
                isinstance(symbol_spec, dict)
                and symbol_spec.get("trade_allowed") is True
            )
            risk_allowed = bool(volume > 0 and symbol_ready and account_ready)

            # Evaluate the immutable per-account policy separately from the
            # global execution gate. Market intelligence is shared, but every
            # user's account owns its own risk/prop policy and reconciliation.
            account_policy_payload = policy.get("account_policy")
            account_policy_allowed = False
            account_policy_version = 0
            execution_permission = ""
            prop_policy_certified = False
            prop_policy_version = ""
            account_frozen = False
            account_policy_reasons: tuple[str, ...] = ("account_policy_missing",)
            canonical_user_id = policy.get("canonical_user_id")
            connection_id_value = str(policy.get("connection_id") or "")
            reconciliation_ready = bool(reconciliation.get("ready"))

            if canonical_user_id and connection_id_value:
                try:
                    from services.account_policies import record_reconciliation

                    await record_reconciliation(
                        int(canonical_user_id),
                        connection_id_value,
                        status="HEALTHY" if reconciliation_ready else "RECONCILING",
                        discrepancy_code=None if reconciliation_ready else "provider_reconciliation_pending",
                        details={
                            "provider": str(reconciliation.get("provider") or platform),
                            "positions_count": len(reconciliation.get("positions") or []),
                            "checked_at": str(reconciliation.get("checked_at") or ""),
                            "equity": (
                                float(account_info.get("equity"))
                                if isinstance(account_info, dict)
                                and isinstance(account_info.get("equity"), (int, float))
                                else None
                            ),
                        },
                    )
                except Exception:
                    logger.warning(
                        "[SignalRouter] account reconciliation evidence unavailable; blocking",
                        exc_info=True,
                    )
                    reconciliation_ready = False

            if isinstance(account_policy_payload, dict):
                try:
                    from core.account_policy import (
                        AccountRiskSnapshot,
                        evaluate_account_policy,
                        policy_from_mapping,
                    )

                    account_policy = policy_from_mapping(account_policy_payload)
                    account_policy_version = int(account_policy.policy_version)
                    execution_permission = account_policy.execution_permission
                    prop_policy_certified = bool(account_policy.certified)
                    prop_policy_version = str(account_policy.prop_rules_version or "")
                    account_frozen = bool(account_policy.frozen)

                    current_equity = Decimal(str(account_info.get("equity") or 0))
                    raw_day_start = account_info.get("day_start_equity")
                    raw_peak = account_info.get("peak_equity")
                    baseline_verified = bool(
                        isinstance(raw_day_start, (int, float))
                        and float(raw_day_start) > 0
                        and isinstance(raw_peak, (int, float))
                        and float(raw_peak) > 0
                    )
                    day_start_equity = Decimal(
                        str(raw_day_start if baseline_verified else current_equity)
                    )
                    peak_equity = Decimal(
                        str(raw_peak if baseline_verified else current_equity)
                    )
                    daily_realized_pnl = Decimal(
                        str(account_info.get("daily_realized_pnl") or 0)
                    )
                    profile_risk_fraction = Decimal(
                        str(profile_policy.get("risk_per_trade_pct") or 0)
                    ) / Decimal("100")
                    contract_size = Decimal(
                        str(symbol_spec.get("contract_size") or 0)
                    )
                    entry_decimal = Decimal(str(signal.get("entry") or 0))
                    proposed_leverage = Decimal("0")
                    if current_equity > 0 and contract_size > 0 and entry_decimal > 0:
                        proposed_leverage = (
                            Decimal(str(volume)) * contract_size * entry_decimal
                        ) / current_equity

                    policy_snapshot = AccountRiskSnapshot(
                        current_equity=current_equity,
                        day_start_equity=day_start_equity,
                        peak_equity=peak_equity,
                        daily_realized_pnl=daily_realized_pnl,
                        open_positions=len(reconciliation.get("positions") or []),
                        proposed_risk_pct=profile_risk_fraction,
                        proposed_leverage=proposed_leverage,
                        symbol=asset,
                        asset_class=str(signal.get("asset_class") or ""),
                        high_impact_news_window=bool(signal.get("high_impact_news_window")),
                        weekend_hold_expected=bool(signal.get("weekend_hold_expected")),
                        account_is_demo=account_is_demo,
                        reconciliation_ready=reconciliation_ready,
                        loss_baselines_verified=baseline_verified,
                    )
                    account_policy_decision = evaluate_account_policy(
                        account_policy,
                        policy_snapshot,
                        execution_mode=execution_mode,
                    )
                    account_policy_allowed = account_policy_decision.allowed
                    account_policy_reasons = account_policy_decision.reasons
                except Exception:
                    logger.warning(
                        "[SignalRouter] account policy evaluation unavailable; blocking",
                        exc_info=True,
                    )
                    account_policy_allowed = False
                    account_policy_reasons = ("account_policy_unavailable",)

            gate_request = GateRequest(
                user_id=int(user_id),
                signal_id=signal_id,
                signal=signal,
                account_id=str(policy.get("connection_id") or ""),
                tier=tier,
                mode=execution_mode,
                user_enabled=bool(policy.get("found") and policy.get("user_enabled") and user_enabled and profile_policy.get("allowed")),
                consent=bool(policy.get("consent")),
                account_ready=account_ready,
                account_is_demo=account_is_demo,
                credentials_encrypted=bool(policy.get("credentials_encrypted")),
                quote_trusted=quote_trusted,
                quote_age_seconds=quote_age,
                max_quote_age_seconds=max_quote_age,
                market_open=bool(market.market_open and market.trading_allowed),
                risk_allowed=risk_allowed,
                evidence_allowed=bool(evidence),
                broker_healthy=bool(account_ready and quote_trusted and symbol_ready),
                resources_available=self._resource_pressure_clear(),
                reconciliation_ready=reconciliation_ready,
                kill_switch=kill_switch,
                broker_provider=platform,
                user_identity=identity,
                canonical_user_id=policy.get("canonical_user_id"),
                account_classification=str(policy.get("account_classification") or "UNKNOWN"),
                account_policy_allowed=account_policy_allowed,
                account_policy_version=account_policy_version,
                execution_permission=execution_permission,
                prop_policy_certified=prop_policy_certified,
                prop_policy_version=prop_policy_version,
                account_frozen=account_frozen,
            )
            idempotency_key = gate_request.key()

            # Master execution flags, user consent, account state, quote freshness,
            # reconciliation and kill switches must fail before the richer signal
            # integrity contract. This preserves precise operator diagnostics and
            # keeps demo certification usable without weakening real accounts.
            preflight = self._execution_gate.preflight(gate_request)

            # Append-only decision evidence is best-effort for demo/advisory
            # diagnostics, but inability to persist it blocks any real-money
            # account because auditability is part of the live safety contract.
            decision_evidence_ok = False
            if canonical_user_id and connection_id_value:
                try:
                    from services.account_policies import record_execution_decision

                    await record_execution_decision(
                        user_id=int(canonical_user_id),
                        connection_id=connection_id_value,
                        signal_id=signal_id,
                        execution_mode=execution_mode,
                        account_mode=str(policy.get("account_classification") or "UNKNOWN"),
                        policy_version=account_policy_version,
                        allowed=preflight.allowed,
                        reasons=tuple(preflight.reasons) + tuple(account_policy_reasons),
                        market_snapshot={
                            "asset": asset,
                            "asset_class": str(signal.get("asset_class") or ""),
                            "quote_age_seconds": quote_age,
                            "market_open": bool(market.market_open and market.trading_allowed),
                        },
                        risk_snapshot={
                            "account_policy_allowed": account_policy_allowed,
                            "reconciliation_ready": reconciliation_ready,
                            "volume": str(volume),
                        },
                        request_snapshot={
                            "signal_id": signal_id,
                            "execution_mode": execution_mode,
                            "connection_id": connection_id_value,
                        },
                    )
                    decision_evidence_ok = True
                except Exception:
                    logger.warning(
                        "[SignalRouter] execution decision evidence unavailable",
                        exc_info=True,
                    )
            if account_is_demo is False and not decision_evidence_ok:
                return ExecutionResult(
                    success=False,
                    message="Execution blocked: decision_provenance_unavailable",
                    error="decision_provenance_unavailable",
                )
            if not preflight.allowed:
                reasons = ", ".join(preflight.reasons)
                return ExecutionResult(
                    success=False,
                    message=f"Execution blocked: {reasons}",
                    error=reasons,
                )

            demo_requires_integrity = str(
                os.getenv("DEMO_EXECUTION_REQUIRES_LIVE_INTEGRITY", "0") or "0"
            ).strip().lower() in {"1", "true", "yes", "on"}
            if account_is_demo is not True or demo_requires_integrity:
                from core.live_execution_integrity import evaluate_live_signal_admission

                integrity = evaluate_live_signal_admission(signal or {})
                if not integrity.allowed:
                    reason = "live_integrity_blocked:" + ",".join(integrity.reasons)
                    return ExecutionResult(success=False, message=reason, error=reason)

            broker_result_holder: Dict[str, ExecutionResult] = {}

            async def _broker_submit(_request: GateRequest) -> Dict[str, Any]:
                reserved = await self._reserve_execution_once(
                    idempotency_key,
                    user_id=int(user_id),
                    signal_id=signal_id,
                )
                if not reserved:
                    return {
                        "success": False,
                        "status": "DUPLICATE",
                        "error": "duplicate_or_unavailable_execution_reservation",
                    }

                quota_reserved, quota_error, user_db_id = (
                    await self._reserve_user_execution_quota(
                        int(user_id),
                        tier=tier,
                        execution_mode=execution_mode,
                        user_identity=identity,
                    )
                )
                if not quota_reserved:
                    await self._record_execution_reservation(
                        idempotency_key,
                        status="rejected",
                        error=quota_error,
                    )
                    return {
                        "success": False,
                        "status": "REJECTED",
                        "error": quota_error,
                    }

                routed = await self._execute_via_mt5(
                    signal=signal,
                    user_id=user_id,
                    volume=volume,
                    account_id=mt5_account_id,
                    tier=tier,
                    execution_mode=execution_mode,
                    execution_authorized=True,
                    idempotency_key=idempotency_key,
                    user_identity=identity,
                    broker_platform=platform,
                )
                broker_result_holder["result"] = routed
                if not routed.success:
                    await self._release_user_execution_quota(user_db_id)

                await self._record_execution_reservation(
                    idempotency_key,
                    status="submitted" if routed.success else "rejected",
                    order_id=routed.order_id,
                    error=routed.error,
                )
                return {
                    "success": routed.success,
                    "order_id": routed.order_id,
                    "error": routed.error,
                    "status": "SUBMITTED" if routed.success else "REJECTED",
                }

            gated = await self._execution_gate.execute(gate_request, _broker_submit)
            if gated.accepted and gated.status == "SUBMITTED":
                routed_result = broker_result_holder.get("result")
                if routed_result is not None:
                    return routed_result
                return ExecutionResult(
                    success=True,
                    message=f"Executed: {asset} {signal.get('direction')}",
                    order_id=gated.order_id,
                    executed_at=self._utc_now_naive(),
                )
            if gated.status == "SUBMITTING":
                return ExecutionResult(
                    success=False,
                    message="Broker execution is already in progress",
                    error="execution_in_progress",
                )
            reasons = ", ".join(gated.decision.reasons)
            error = gated.error or (
                reasons if gated.status == "BLOCKED" else gated.status.lower()
            )
            return ExecutionResult(
                success=False,
                message=f"Execution {gated.status.lower()}: {error}",
                error=error,
            )

        except Exception as e:
            logger.error(f"[SignalRouter] Route error: {e}")
            return ExecutionResult(
                success=False,
                message=f"Error: {str(e)}",
                error=str(e),
            )
    
    async def _execute_via_mt5(
        self,
        signal: Dict[str, Any],
        user_id: int,
        volume: float,
        account_id: str,
        tier: str,
        execution_mode: str,
        *,
        execution_authorized: bool = False,
        idempotency_key: Optional[str] = None,
        user_identity: str = "telegram",
        broker_platform: str = "mt5",
    ) -> ExecutionResult:
        """Execute signal via MetaApi for MT4 or MT5."""
        if not execution_authorized or not str(idempotency_key or "").strip():
            return ExecutionResult(
                success=False,
                message="ExecutionGate authorization is required",
                error="execution_gate_required",
            )
        try:
            from services.mt5_client import execute_trade
            
            asset = signal.get("asset", "")
            direction = signal.get("direction", "long")
            entry = signal.get("entry", 0)
            stop_loss = signal.get("stop_loss", 0)
            take_profit = signal.get("take_profit")
            
            tp_list = self._parse_take_profit(take_profit)
            
            # Use first TP for now
            tp_price = float(tp_list[0]) if tp_list else 0
            
            result = await execute_trade(
                account_id=account_id,
                symbol=asset,
                direction=direction,
                volume=volume,
                stop_loss=stop_loss,
                take_profit=tp_price,
                signal_entry=entry,
                comment=f"SignalRank:{signal.get('signal_id', '')}",
                execution_authorized=True,
                idempotency_key=idempotency_key,
            )
            
            if result.get("success"):
                order_id = str(result.get("order_id") or "").strip()
                ledger_ok = await self._record_execution_ledger(
                    user_id=int(user_id),
                    signal=signal,
                    account_id=str(account_id),
                    order_id=order_id,
                    volume=float(volume),
                    tier=str(tier),
                    execution_mode=str(execution_mode),
                    idempotency_key=str(idempotency_key),
                    broker_result=dict(result),
                    user_identity=user_identity,
                    broker_platform=broker_platform,
                )
                await self._sync_to_paper_ledger(
                    signal=signal,
                    user_id=user_id,
                    order_id=order_id,
                    volume=volume,
                    user_identity=user_identity,
                )
                message = f"Executed: {asset} {direction}"
                error = None
                if not ledger_ok:
                    message = (
                        f"Executed: {asset} {direction}; durable execution "
                        "ledger reconciliation is pending"
                    )
                    error = "execution_ledger_pending"
                return ExecutionResult(
                    success=True,
                    message=message,
                    order_id=order_id,
                    executed_at=self._utc_now_naive(),
                    error=error,
                )
            else:
                return ExecutionResult(
                    success=False,
                    message=f"Failed: {result.get('error', 'Unknown error')}",
                    error=result.get("error"),
                )
                
        except Exception as e:
            logger.error(f"[SignalRouter] MetaTrader execution error: {e}")
            return ExecutionResult(
                success=False,
                message=f"Execution error: {str(e)}",
                error=str(e),
            )
    
    @staticmethod
    def _apply_position_weight(
        volume: float,
        weight: Any,
        symbol_spec: Optional[Dict[str, Any]],
    ) -> float:
        """Scale an already risk-bounded lot size without rounding upward."""
        try:
            base = float(volume)
            fraction = float(weight)
            spec = symbol_spec if isinstance(symbol_spec, dict) else {}
            step = float(spec.get("volume_step"))
            minimum = float(spec.get("min_volume"))
            maximum = float(spec.get("max_volume"))
            values = (base, fraction, step, minimum, maximum)
            if not all(math.isfinite(value) for value in values):
                return 0.0
            if base <= 0 or not 0 < fraction <= 1 or step <= 0 or minimum <= 0 or maximum < minimum:
                return 0.0
            step_d = Decimal(str(step))
            scaled = (
                (Decimal(str(min(base * fraction, maximum))) / step_d)
                .to_integral_value(rounding=ROUND_DOWN)
                * step_d
            )
            result = float(scaled)
            return result if minimum <= result <= maximum else 0.0
        except (TypeError, ValueError, ArithmeticError):
            return 0.0

    async def _calculate_position_size(
        self,
        user_id: int,
        entry: float,
        stop_loss: float,
        account_id: str,
        tier: str,
        account_info: Optional[Dict[str, Any]] = None,
        symbol_spec: Optional[Dict[str, Any]] = None,
        symbol: str = "",
        user_identity: str = "telegram",
        execution_mode: str = "manual",
    ) -> float:
        """Calculate broker-compliant size or return zero on missing data.

        Tick value is assumed to be reported by MetaApi in account currency.
        The result is always rounded *down* to the broker's volume step. It is
        never raised to the minimum lot and never replaced by a fallback lot.
        """
        try:
            from services.mt5_client import (
                get_account_info,
                get_symbol_specification,
            )

            info = (
                account_info
                if isinstance(account_info, dict)
                else await get_account_info(account_id)
            )
            spec = (
                symbol_spec
                if isinstance(symbol_spec, dict)
                else await get_symbol_specification(
                    account_id,
                    str(symbol or "").strip().upper(),
                )
            )
            # Callers that do not already have a specification must provide a
            # symbol through the specification object; guessing is unsafe.
            if not isinstance(info, dict) or not isinstance(spec, dict):
                return 0.0
            if spec.get("trade_allowed") is not True:
                return 0.0

            equity = float(info.get("equity"))
            free_margin = float(info.get("free_margin"))
            entry_f = float(entry)
            stop_f = float(stop_loss)
            tick_size = float(spec.get("tick_size"))
            tick_value = float(spec.get("tick_value"))
            contract_size = float(spec.get("contract_size"))
            min_volume = float(spec.get("min_volume"))
            max_volume = float(spec.get("max_volume"))
            volume_step = float(spec.get("volume_step"))
            values = (
                equity,
                free_margin,
                entry_f,
                stop_f,
                tick_size,
                tick_value,
                contract_size,
                min_volume,
                max_volume,
                volume_step,
            )
            if not all(math.isfinite(value) for value in values):
                return 0.0
            if (
                equity <= 0
                or free_margin <= 0
                or entry_f <= 0
                or stop_f <= 0
                or tick_size <= 0
                or tick_value <= 0
                or contract_size <= 0
                or min_volume <= 0
                or max_volume < min_volume
                or volume_step <= 0
            ):
                return 0.0

            risk_pct = await self._get_user_risk_pct(
                user_id,
                user_identity=user_identity,
            )
            if risk_pct is None or not math.isfinite(risk_pct) or risk_pct <= 0:
                return 0.0
            try:
                max_risk_pct = float(os.getenv("MAX_LIVE_RISK_PCT", "5"))
            except (TypeError, ValueError):
                max_risk_pct = 5.0
            mode = str(execution_mode or "manual").strip().lower()
            if mode in {"auto", "copy", "copy_trade"}:
                try:
                    auto_cap = float(
                        os.getenv("AUTO_MAX_RISK_CAP_PCT", "3.0") or 3.0
                    )
                except (TypeError, ValueError):
                    auto_cap = 3.0
                max_risk_pct = min(max_risk_pct, max(0.0, auto_cap))
            if risk_pct > max(0.0, max_risk_pct):
                return 0.0

            risk_amount = equity * (risk_pct / 100.0)
            if risk_amount <= 0 or risk_amount > free_margin:
                return 0.0
            sl_distance = abs(entry_f - stop_f)
            if sl_distance <= 0:
                return 0.0
            risk_per_lot = (sl_distance / tick_size) * tick_value
            if not math.isfinite(risk_per_lot) or risk_per_lot <= 0:
                return 0.0
            raw_volume = min(risk_amount / risk_per_lot, max_volume)
            step = Decimal(str(volume_step))
            rounded = (
                (Decimal(str(raw_volume)) / step)
                .to_integral_value(rounding=ROUND_DOWN)
                * step
            )
            volume = float(rounded)
            if not math.isfinite(volume) or volume < min_volume:
                return 0.0
            return min(volume, max_volume)
        except Exception as e:
            logger.error(f"[SignalRouter] Volume calculation error: {e}")
            return 0.0
    
    async def _sync_to_paper_ledger(
        self,
        signal: Dict[str, Any],
        user_id: int,
        order_id: Optional[str],
        volume: float,
        user_identity: str = "telegram",
    ) -> None:
        """Sync executed trade to paper ledger for tracking."""
        try:
            from core.paper_ledger import sync_execution

            canonical_id = await self._resolve_canonical_user_id(
                user_id,
                user_identity=user_identity,
            )
            if canonical_id is None:
                logger.error("[SignalRouter] paper mirror blocked: canonical user unavailable")
                return
            await sync_execution(
                signal_id=signal.get("signal_id", ""),
                user_id=canonical_id,
                order_id=order_id or "",
                asset=signal.get("asset", ""),
                direction=signal.get("direction", "long"),
                entry=signal.get("entry", 0),
                stop_loss=signal.get("stop_loss", 0),
                take_profit=signal.get("take_profit", ""),
                volume=volume,
                status="executed",
            )
        except Exception as e:
            logger.error(f"[SignalRouter] Paper ledger sync error: {e}")
    
    async def _get_user_mt5_account(
        self,
        user_id: int,
        user_identity: str = "telegram",
        broker_platform: str = "mt5",
        connection_id: str | None = None,
    ) -> Optional[str]:
        """Resolve an owned account without choosing a default among multiple accounts."""
        try:
            from services.broker_connections import resolve_execution_connection
            from services.mt5_client import ensure_platform_metatrader_account_id

            identity = str(user_identity or "telegram").strip().lower()
            platform = str(broker_platform or "mt5").strip().lower()
            if identity not in {"platform", "telegram"}:
                return None
            canonical_id = await self._resolve_canonical_user_id(
                int(user_id),
                user_identity=identity,
            )
            if canonical_id is None:
                return None
            connection = await resolve_execution_connection(
                canonical_id, platform=platform, connection_id=connection_id,
            )
            return await ensure_platform_metatrader_account_id(
                canonical_id,
                platform=platform,
                connection_id=connection.connection_id,
                require_execution_enabled=True,
            )
        except Exception:
            return None

    async def _resolve_canonical_user_id(
        self,
        user_id: int,
        user_identity: str = "telegram",
    ) -> Optional[int]:
        try:
            from db.models import User
            from db.session import get_session
            from sqlalchemy import select

            identity = str(user_identity or "telegram").strip().lower()
            async with get_session(label="mt5.identity.resolve", timeout_seconds=5.0) as session:
                query = select(User.id).where(
                    User.id == int(user_id)
                    if identity == "platform"
                    else User.telegram_user_id == int(user_id)
                ).limit(1)
                value = (await session.execute(query)).scalar_one_or_none()
                await session.rollback()
            return int(value) if value is not None else None
        except Exception:
            return None

    async def _get_platform_user_tier(self, user_id: int) -> str:
        """Resolve effective tier for a canonical platform account."""
        try:
            from db.access import resolve_product_tier
            from db.models import User
            from db.session import get_session
            from sqlalchemy import select

            async with get_session(label="mt5.platform.tier", timeout_seconds=5.0) as session:
                user = (
                    await session.execute(
                        select(User).where(User.id == int(user_id)).limit(1)
                    )
                ).scalar_one_or_none()
                if user is None:
                    return "FREE"
                tier = await resolve_product_tier(session, user)
                await session.rollback()
            return str(tier or "free").upper()
        except Exception:
            return "FREE"
    
    def _get_user_tier(self, user_id: int) -> str:
        """Get user's current tier."""
        try:
            from signalrank_telegram.access import resolve_user_tier
            tier = resolve_user_tier(user_id)
            return str(tier).upper()
        except Exception:
            return "FREE"
    
    async def _get_user_risk_pct(
        self,
        user_id: int,
        user_identity: str = "telegram",
    ) -> Optional[float]:
        """Load canonical risk percentage from PostgreSQL."""
        try:
            from db.session import get_session
            from db.models import User
            from sqlalchemy import select

            async with get_session() as session:
                identity = str(user_identity or "telegram").strip().lower()
                user_filter = (
                    User.id == int(user_id)
                    if identity == "platform"
                    else User.telegram_user_id == int(user_id)
                )
                result = await session.execute(
                    select(User.id, User.max_risk_percentage)
                    .where(user_filter)
                    .limit(1)
                )
                row = result.fetchone()
                if not row or row[1] is None:
                    return None
                canonical_id = int(row[0])
                value = float(row[1])
                try:
                    from services.user_intelligence import get_platform_user_trading_preferences
                    prefs = await get_platform_user_trading_preferences(
                        session,
                        canonical_id,
                    )
                    profile_risk = float(getattr(prefs, "risk_per_trade_pct", value) or value)
                    if profile_risk > 0:
                        value = min(value, profile_risk)
                except Exception:
                    pass
            return value if math.isfinite(value) and value > 0 else None
        except Exception:
            logger.warning(
                "[SignalRouter] risk configuration unavailable; blocking",
                exc_info=True,
            )
            return None
    
    async def _process_execution_loop(self) -> None:
        """Process queued broker requests without unbounded task creation."""
        while True:
            item = await self._execution_queue.get()
            try:
                if item is None:
                    return
                request, future = item
                result = await self._process_request(request)
                if not future.done():
                    future.set_result(result)
            except asyncio.CancelledError:
                if item is not None:
                    _request, future = item
                    if not future.done():
                        future.cancel()
                raise
            except Exception as exc:
                logger.exception("[SignalRouter] queued execution failed")
                if item is not None:
                    _request, future = item
                    if not future.done():
                        future.set_result(
                            ExecutionResult(
                                success=False,
                                message="Queued execution failed",
                                error=str(exc),
                            )
                        )
            finally:
                self._execution_queue.task_done()

    async def _process_request(self, request: ExecutionRequest) -> ExecutionResult:
        """Route one queued request through the canonical execution gate."""
        signal = {
            **dict(request.metadata or {}),
            "signal_id": request.signal_id,
            "asset": request.asset,
            "direction": request.direction,
            "entry": request.entry,
            "stop_loss": request.stop_loss,
            "take_profit": list(request.take_profit),
            # The canonical router calculates broker-compliant volume from
            # account equity and stored risk; queued caller volume is audit
            # context only and cannot bypass sizing.
            "requested_volume": request.volume,
            "queued_at": request.created_at.isoformat(),
        }
        return await self.route_signal(
            signal,
            int(request.user_id),
            str(request.execution_mode),
        )

    async def shutdown(self) -> None:
        """Stop the bounded worker and settle queued waiters."""
        self._processing = False
        task = self._worker_task
        if task and not task.done():
            try:
                self._execution_queue.put_nowait(None)
            except asyncio.QueueFull:
                task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=5.0)
        self._worker_task = None
        while not self._execution_queue.empty():
            item = self._execution_queue.get_nowait()
            try:
                if item is not None:
                    _request, future = item
                    if not future.done():
                        future.set_result(
                            ExecutionResult(
                                success=False,
                                message="Execution router shut down",
                                error="execution_router_shutdown",
                            )
                        )
            finally:
                self._execution_queue.task_done()
        logger.info("[SignalRouter] Shutdown complete")


# Singleton instance
router = MT5SignalRouter()


# Convenience functions
async def route_signal_to_mt5(
    signal: Dict[str, Any],
    user_id: int,
    execution_mode: str = "manual",
    *,
    connection_id: str | None = None,
) -> ExecutionResult:
    """Route a Telegram-originated signal to MT5 for execution."""
    return await router.route_signal(signal, user_id, execution_mode, connection_id=connection_id)


async def route_platform_signal_to_metatrader(
    signal: Dict[str, Any],
    user_id: int,
    *,
    platform: str = "mt5",
    execution_mode: str = "manual_confirmed",
    connection_id: str | None = None,
) -> ExecutionResult:
    """Route an authenticated MT4/MT5 signal through the same safety gate."""
    return await router.route_signal(
        signal,
        int(user_id),
        execution_mode,
        user_identity="platform",
        broker_platform=str(platform or "mt5").lower(),
        connection_id=connection_id,
    )


async def route_platform_signal_to_mt5(
    signal: Dict[str, Any],
    user_id: int,
    execution_mode: str = "manual_confirmed",
) -> ExecutionResult:
    """Backward-compatible MT5 platform route."""
    return await route_platform_signal_to_metatrader(
        signal,
        int(user_id),
        platform="mt5",
        execution_mode=execution_mode,
    )


async def get_user_execution_mode(user_id: int) -> str:
    """Get user's current execution mode."""
    try:
        from db.session import get_session
        from db.models import User
        from sqlalchemy import select
        
        async with get_session() as session:
            result = await session.execute(
                select(User.execution_mode)
                .where(User.telegram_user_id == user_id)
            )
            row = result.fetchone()
            return row[0] if row else "manual"
    except Exception:
        return "manual"


async def set_user_execution_mode(user_id: int, mode: str) -> bool:
    """Set user's execution mode."""
    try:
        from db.session import get_session
        from db.models import User
        from sqlalchemy import update
        
        async with get_session() as session:
            await session.execute(
                update(User)
                .where(User.telegram_user_id == user_id)
                .values(execution_mode=mode)
            )
            await session.commit()
        return True
    except Exception as e:
        logger.error(f"[SignalRouter] Set mode error: {e}")
        return False


if __name__ == "__main__":
    # Test
    import asyncio
    
    async def test():
        r = MT5SignalRouter()
        await r.initialize()
        print("Router initialized")
        await r.shutdown()
    
    asyncio.run(test())
