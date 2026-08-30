"""Pass 9 paper/copy-trading policy primitives.

These records make the future ecosystem explicit without turning on broker or
copy execution.  They are intentionally storage-agnostic and can be used by
Telegram, API, or an internal paper runner.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from core.env import env_bool


@dataclass(frozen=True, slots=True)
class ConsentRecord:
    user_id: int
    mode: str
    accepted: bool
    version: str = "phase4-pass9-v1"
    accepted_at: str | None = None
    revoked_at: str | None = None

    @property
    def active(self) -> bool:
        return bool(self.accepted and not self.revoked_at)


@dataclass(frozen=True, slots=True)
class PaperFill:
    order_id: str
    user_id: int
    signal_id: str
    asset: str
    direction: str
    quantity: float
    requested_price: float
    fill_price: float
    fee: float
    slippage: float
    status: str = "filled"
    filled_quantity: float = 0.0
    commission: float = 0.0
    funding: float = 0.0
    latency_ms: int = 0
    rejection_reason: str | None = None
    provenance: str = "paper"
    filled_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True, slots=True)
class CopyTradeDecision:
    allowed: bool
    code: str
    reasons: tuple[str, ...] = ()


def copy_trade_decision(
    *,
    enabled: bool | None = None,
    consent: ConsentRecord | None = None,
    leader_event_id: str | None = None,
    risk_allowed: bool = False,
    kill_switch: bool = False,
    duplicate: bool = False,
) -> CopyTradeDecision:
    reasons: list[str] = []
    if not env_bool("COPY_TRADE_ENABLED", False) if enabled is None else not enabled:
        reasons.append("COPY_TRADE_DISABLED")
    if not consent or not consent.active or consent.mode != "copy_trade":
        reasons.append("explicit_copy_consent_required")
    if not leader_event_id:
        reasons.append("leader_provenance_required")
    if not risk_allowed:
        reasons.append("risk_cap_blocked")
    if kill_switch:
        reasons.append("kill_switch_enabled")
    if duplicate:
        reasons.append("duplicate_event")
    return CopyTradeDecision(not reasons, "COPY_ALLOWED" if not reasons else "COPY_BLOCKED", tuple(reasons))


def deterministic_paper_fill(
    *,
    user_id: int,
    signal: Mapping[str, Any],
    quantity: float,
    spread_bps: float = 0.0,
    slippage_bps: float = 0.0,
    fee_bps: float = 0.0,
    commission_bps: float = 0.0,
    funding_bps: float = 0.0,
    latency_ms: int = 0,
    available_quantity: float | None = None,
    reject_reason: str | None = None,
) -> PaperFill:
    requested = float(signal.get("entry") or signal.get("price") or 0.0)
    direction = str(signal.get("direction") or "long").lower()
    sign = 1.0 if direction in {"long", "buy"} else -1.0
    fill_price = requested * (1 + sign * (spread_bps + slippage_bps) / 10000.0)
    requested_quantity = max(0.0, float(quantity))
    available = requested_quantity if available_quantity is None else max(0.0, float(available_quantity))
    filled_quantity = min(requested_quantity, available)
    status = "rejected" if reject_reason or requested <= 0 or requested_quantity <= 0 else (
        "partially_filled" if filled_quantity < requested_quantity else "filled"
    )
    if status == "rejected":
        filled_quantity = 0.0
    notional = abs(fill_price * filled_quantity)
    fee = notional * max(0.0, fee_bps) / 10000.0
    commission = notional * max(0.0, commission_bps) / 10000.0
    funding = notional * float(funding_bps) / 10000.0
    signal_id = str(signal.get("signal_id") or signal.get("id") or "")
    order_id = "paper_" + hashlib.sha256(f"{user_id}|{signal_id}|{requested}|{quantity}".encode()).hexdigest()[:20]
    return PaperFill(
        order_id, int(user_id), signal_id, str(signal.get("asset") or "").upper(),
        direction, requested_quantity, requested, fill_price, fee,
        abs(fill_price - requested), status, filled_quantity, commission, funding,
        max(0, int(latency_ms)), str(reject_reason)[:160] if reject_reason else (
            "invalid_order" if status == "rejected" else None
        ),
    )


def portfolio_snapshot(*, balance: float, fills: list[PaperFill], open_positions: int = 0) -> dict[str, Any]:
    realized_fees = sum(fill.fee + fill.commission + fill.funding for fill in fills)
    return {
        "balance": round(float(balance), 8),
        "realized_fees": round(realized_fees, 8),
        "fill_count": len(fills),
        "open_positions": max(0, int(open_positions)),
        "provenance": "paper",
        "assumptions": {
            "spread_bps": "explicit", "slippage_bps": "explicit", "fees": "explicit",
            "commissions": "explicit", "funding": "explicit", "latency": "explicit",
            "partial_fills": "liquidity_bounded", "rejections": "recorded",
        },
    }


__all__ = ["ConsentRecord", "PaperFill", "CopyTradeDecision", "copy_trade_decision", "deterministic_paper_fill", "portfolio_snapshot"]
