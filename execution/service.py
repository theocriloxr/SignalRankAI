"""Fail-closed execution policy and idempotent broker hand-off.

This is the Pass 6 compatibility boundary.  Existing signal and paper flows
continue to work, while every future broker call can use one small, testable
service.  Entitlements are presentation-only: live execution additionally
requires every safety input and an explicit environment flag.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Mapping

from core.env import SafetyFlags
from core.tier_policy import evaluate_feature_access

logger = logging.getLogger(__name__)


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

    def key(self) -> str:
        if self.idempotency_key:
            return str(self.idempotency_key)
        payload = f"{int(self.user_id)}|{self.signal_id}|{self.mode}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class GateDecision:
    allowed: bool
    code: str
    reasons: tuple[str, ...] = ()
    policy_version: str = "phase4-pass6-v1"


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    accepted: bool
    status: str
    decision: GateDecision
    idempotency_key: str
    order_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ExecutionGate:
    """Single fail-closed gate for broker execution.

    ``broker_submit`` is injected by the caller and is never called unless
    :meth:`preflight` allows the request.  The in-memory reservation is a
    compatibility guard; durable callers should persist the same key in their
    execution ledger before invoking this service.
    """

    def __init__(self, *, safety_flags: SafetyFlags | None = None) -> None:
        self.safety_flags = safety_flags or SafetyFlags.from_env()
        self._reserved: dict[str, ExecutionResult] = {}

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
        if not request.consent:
            reasons.append("user_consent_required")
        if not request.account_ready:
            reasons.append("broker_account_not_ready")
        if not request.quote_trusted:
            reasons.append("trusted_quote_required")
        if not request.market_open:
            reasons.append("market_closed")
        if not request.risk_allowed:
            reasons.append("risk_policy_blocked")
        if not request.evidence_allowed:
            reasons.append("evidence_gate_blocked")
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
        broker_submit: Callable[[ExecutionRequest], Awaitable[str | None]],
    ) -> ExecutionResult:
        key = request.key()
        existing = self._reserved.get(key)
        if existing is not None:
            return existing
        decision = self.preflight(request)
        if not decision.allowed:
            result = ExecutionResult(False, "BLOCKED", decision, key)
            self._reserved[key] = result
            return result
        # Reserve before the ambiguous broker boundary.  A timeout or network
        # error remains pending and is never blindly retried.
        pending = ExecutionResult(True, "SUBMITTING", decision, key)
        self._reserved[key] = pending
        try:
            order_id = await broker_submit(request)
        except Exception as exc:  # broker ambiguity is fail-closed
            logger.warning("execution broker boundary failed: %s", type(exc).__name__)
            result = ExecutionResult(False, "AMBIGUOUS", decision, key)
            self._reserved[key] = result
            return result
        result = ExecutionResult(True, "SUBMITTED", decision, key, order_id=order_id)
        self._reserved[key] = result
        return result


__all__ = ["ExecutionGate", "ExecutionRequest", "ExecutionResult", "GateDecision"]
