"""Fail-closed execution policy and idempotent broker hand-off.

This is the Pass 6 compatibility boundary.  Existing signal and paper flows
continue to work, while every future broker call can use one small, testable
service.  Entitlements are presentation-only: live execution additionally
requires every safety input and an explicit environment flag.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Mapping

from core.env import SafetyFlags
from core.tier_policy import evaluate_feature_access

logger = logging.getLogger(__name__)


def _env_enabled(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    user_id: int
    signal_id: str
    signal: Mapping[str, Any]
    tier: str = "FREE"
    mode: str = "signals_only"
    consent: bool = False
    account_ready: bool = False
    quote_trusted: bool = False
    market_open: bool = False
    risk_allowed: bool = False
    evidence_allowed: bool = False
    kill_switch: bool = False
    idempotency_key: str | None = None
    # Broker P0 extensions follow the original field order so older positional
    # construction remains compatible.
    account_id: str = ""
    user_enabled: bool = False
    account_is_demo: bool | None = None
    credentials_encrypted: bool = False
    quote_age_seconds: float | None = None
    max_quote_age_seconds: float = 15.0
    broker_healthy: bool = False
    resources_available: bool = False
    reconciliation_ready: bool = False

    def key(self) -> str:
        if self.idempotency_key:
            return str(self.idempotency_key)
        payload = (
            f"{int(self.user_id)}|{self.account_id}|"
            f"{self.signal_id}|{str(self.mode).strip().lower()}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class GateDecision:
    allowed: bool
    code: str
    reasons: tuple[str, ...] = ()
    policy_version: str = "broker-p0-v2"


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    accepted: bool
    status: str
    decision: GateDecision
    idempotency_key: str
    order_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error: str | None = None


class ExecutionGate:
    """Single fail-closed gate for broker execution.

    ``broker_submit`` is injected by the caller and is never called unless
    :meth:`preflight` allows the request.  The reservation is protected by an
    async lock so concurrent coroutines cannot cross the broker boundary with
    the same key.  The active adapter additionally persists the same key with
    an atomic PostgreSQL upsert before the network call.
    """

    def __init__(self, *, safety_flags: SafetyFlags | None = None) -> None:
        self.safety_flags = safety_flags or SafetyFlags.from_env()
        self._reserved: dict[str, ExecutionResult] = {}
        self._reservation_lock = asyncio.Lock()

    def preflight(self, request: ExecutionRequest) -> GateDecision:
        reasons: list[str] = []
        mode = str(request.mode or "signals_only").strip().lower()
        if mode not in {"auto", "copy_trade", "live"}:
            reasons.append("execution_mode_not_live")
        # ``live`` is an explicit compatibility alias for auto execution; it
        # must never bypass the same global default-off switch.
        if mode in {"auto", "live"} and not self.safety_flags.auto_trade_enabled:
            reasons.append("AUTO_TRADE_DISABLED")
        if mode == "copy_trade" and not self.safety_flags.copy_trade_enabled:
            reasons.append("COPY_TRADE_DISABLED")
        if not request.user_enabled:
            reasons.append("user_execution_not_enabled")
        if not request.consent:
            reasons.append("user_consent_required")
        if not request.account_ready:
            reasons.append("broker_account_not_ready")
        if not request.credentials_encrypted:
            reasons.append("encrypted_credentials_required")
        if request.account_is_demo is None:
            reasons.append("account_demo_live_classification_required")
        elif request.account_is_demo:
            if not _env_enabled("DEMO_EXECUTION_ENABLED", True):
                reasons.append("DEMO_EXECUTION_DISABLED")
        elif not _env_enabled("REAL_EXECUTION_ENABLED", False):
            reasons.append("REAL_EXECUTION_DISABLED")
        if not request.quote_trusted:
            reasons.append("trusted_quote_required")
        try:
            quote_age = float(request.quote_age_seconds)  # type: ignore[arg-type]
            max_quote_age = float(request.max_quote_age_seconds)
            quote_fresh = (
                math.isfinite(quote_age)
                and quote_age >= 0
                and math.isfinite(max_quote_age)
                and max_quote_age > 0
                and quote_age <= max_quote_age
            )
        except (TypeError, ValueError):
            quote_fresh = False
        if not quote_fresh:
            reasons.append("fresh_quote_required")
        if not request.market_open:
            reasons.append("market_closed")
        if not request.risk_allowed:
            reasons.append("risk_policy_blocked")
        if not request.evidence_allowed:
            reasons.append("evidence_gate_blocked")
        if not request.broker_healthy:
            reasons.append("broker_unhealthy")
        if not request.resources_available:
            reasons.append("resource_pressure_blocked")
        if not request.reconciliation_ready:
            reasons.append("reconciliation_unavailable")
        if request.kill_switch:
            reasons.append("kill_switch_enabled")
        tier_decision = evaluate_feature_access(request.tier, "execution_preflight")
        if not tier_decision.allowed:
            reasons.append("tier_not_eligible")
        signal = request.signal or {}
        try:
            entry = float(signal.get("entry") or 0)
            stop = float(signal.get("stop_loss") or signal.get("stop") or 0)
        except (TypeError, ValueError):
            entry, stop = 0.0, 0.0
        direction = str(signal.get("direction") or signal.get("side") or "").lower()
        if entry <= 0 or stop <= 0:
            reasons.append("broker_native_stop_required")
        elif direction in {"long", "buy"} and stop >= entry:
            reasons.append("long_stop_must_be_below_entry")
        elif direction in {"short", "sell"} and stop <= entry:
            reasons.append("short_stop_must_be_above_entry")
        if not str(request.signal_id or "").strip():
            reasons.append("signal_id_required")
        if reasons:
            return GateDecision(False, "EXECUTION_BLOCKED", tuple(reasons))
        return GateDecision(True, "EXECUTION_ALLOWED")

    async def execute(
        self,
        request: ExecutionRequest,
        broker_submit: Callable[[ExecutionRequest], Awaitable[Any]],
    ) -> ExecutionResult:
        key = request.key()
        decision = self.preflight(request)
        if not decision.allowed:
            return ExecutionResult(False, "BLOCKED", decision, key)

        # Check and reserve in one critical section.  A timeout or network
        # error remains reserved and is never blindly retried.
        async with self._reservation_lock:
            existing = self._reserved.get(key)
            if existing is not None:
                return existing
            pending = ExecutionResult(True, "SUBMITTING", decision, key)
            self._reserved[key] = pending

        try:
            submitted = await broker_submit(request)
        except Exception as exc:  # broker ambiguity is fail-closed
            logger.warning("execution broker boundary failed: %s", type(exc).__name__)
            result = ExecutionResult(
                False,
                "AMBIGUOUS",
                decision,
                key,
                error=f"broker_boundary:{type(exc).__name__}",
            )
            async with self._reservation_lock:
                self._reserved[key] = result
            return result

        if isinstance(submitted, Mapping):
            success = bool(submitted.get("success"))
            order_id_raw = (
                submitted.get("order_id")
                or submitted.get("orderId")
                or submitted.get("position_id")
                or submitted.get("positionId")
            )
            order_id = str(order_id_raw).strip() if order_id_raw is not None else None
            error = str(submitted.get("error") or "").strip() or None
            if not success:
                status = str(submitted.get("status") or "REJECTED").strip().upper()
                result = ExecutionResult(False, status, decision, key, error=error)
                async with self._reservation_lock:
                    self._reserved[key] = result
                return result
        else:
            order_id = str(submitted).strip() if submitted is not None else None
            error = None

        # A provider response without a stable order/position identifier is an
        # uncertain submission, never a success that may be retried.
        if not order_id:
            result = ExecutionResult(
                False,
                "AMBIGUOUS",
                decision,
                key,
                error=error or "broker_ack_missing_order_id",
            )
            async with self._reservation_lock:
                self._reserved[key] = result
            return result

        result = ExecutionResult(
            True,
            "SUBMITTED",
            decision,
            key,
            order_id=order_id,
        )
        async with self._reservation_lock:
            self._reserved[key] = result
        return result


__all__ = ["ExecutionGate", "ExecutionRequest", "ExecutionResult", "GateDecision"]
