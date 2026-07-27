"""Safe SignalRank Automaton: simulation, survival scoring, and recommendations.

The automaton owns no broker, payment, or deployment capability.  It consumes
metrics and returns a state plus auditable recommendations; all state changes
are deterministic and virtual-treasury-only.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Mapping


class AutomatonState(StrEnum):
    OBSERVE = "OBSERVE"
    SIMULATE = "SIMULATE"
    PAPER_TRADE = "PAPER_TRADE"
    CONSERVE = "CONSERVE"
    RECOVER = "RECOVER"
    OPTIMIZE = "OPTIMIZE"
    SCALE = "SCALE"
    PAUSE = "PAUSE"
    KILL_SWITCH = "KILL_SWITCH"


@dataclass(frozen=True, slots=True)
class AutomatonInputs:
    equity: float = 5000.0
    starting_balance: float = 5000.0
    drawdown_pct: float = 0.0
    win_rate: float = 0.0
    expectancy_r: float = 0.0
    sample_size: int = 0
    provider_confidence: float = 1.0
    delivery_latency_ms: float = 0.0
    db_healthy: bool = True
    redis_healthy: bool = True
    outcome_healthy: bool = True
    missed_entry_rate: float = 0.0
    expired_rate: float = 0.0
    kill_switch: bool = False


@dataclass(frozen=True, slots=True)
class AutomatonDecision:
    state: AutomatonState
    risk_multiplier: float
    signal_volume_multiplier: float
    recommendations: tuple[str, ...]
    reasons: tuple[str, ...]
    virtual_only: bool = True

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        return payload


def starting_balance() -> float:
    try:
        return max(0.0, float(os.getenv("AUTOMATON_STARTING_BALANCE_USD", "5000")))
    except (TypeError, ValueError):
        return 5000.0


def evaluate(inputs: AutomatonInputs) -> AutomatonDecision:
    reasons: list[str] = []
    recommendations: list[str] = []
    balance = max(float(inputs.starting_balance), 1e-9)
    equity_ratio = float(inputs.equity) / balance
    if inputs.kill_switch:
        return AutomatonDecision(AutomatonState.KILL_SWITCH, 0.0, 0.0, ("keep all risky actions paused",), ("kill_switch_enabled",))
    if not inputs.db_healthy or not inputs.redis_healthy or not inputs.outcome_healthy:
        reasons.append("critical_dependency_degraded")
        recommendations.append("defer background work and preserve durable truth")
        return AutomatonDecision(AutomatonState.CONSERVE, 0.25, 0.5, tuple(recommendations), tuple(reasons))
    if inputs.provider_confidence < 0.65:
        reasons.append("provider_confidence_low")
        recommendations.append("reduce risky signal delivery until provider health recovers")
        return AutomatonDecision(AutomatonState.PAUSE, 0.0, 0.0, tuple(recommendations), tuple(reasons))
    if inputs.drawdown_pct >= 20.0 or equity_ratio <= 0.5:
        reasons.append("survival_drawdown_limit")
        recommendations.append("quarantine weak strategies and preserve virtual treasury")
        return AutomatonDecision(AutomatonState.CONSERVE, 0.2, 0.4, tuple(recommendations), tuple(reasons))
    if inputs.drawdown_pct >= 10.0 or inputs.win_rate < 0.5 or inputs.expectancy_r <= 0:
        reasons.append("performance_requires_recovery")
        recommendations.append("tighten validation and lower risk while collecting evidence")
        return AutomatonDecision(AutomatonState.RECOVER, 0.5, 0.7, tuple(recommendations), tuple(reasons))
    if inputs.sample_size < 100:
        reasons.append("insufficient_evidence")
        recommendations.append("remain in observation until out-of-sample sample size is sufficient")
        return AutomatonDecision(AutomatonState.OBSERVE, 0.5, 0.8, tuple(recommendations), tuple(reasons))
    if inputs.win_rate >= 0.6 and inputs.expectancy_r > 0 and inputs.drawdown_pct < 10:
        recommendations.append("consider controlled paper scaling; human approval remains required")
        return AutomatonDecision(AutomatonState.SCALE, 1.0, 1.0, tuple(recommendations), ("positive_evidence",))
    return AutomatonDecision(AutomatonState.OPTIMIZE, 0.75, 0.9, ("compare strategy and provider segments",), ("continue_evidence_review",))


def status(inputs: AutomatonInputs | None = None) -> dict[str, Any]:
    values = inputs or AutomatonInputs(starting_balance=starting_balance(), equity=starting_balance())
    decision = evaluate(values)
    return {"state": decision.state.value, "starting_balance": values.starting_balance, "inputs": asdict(values), "decision": decision.as_dict(), "real_money_enabled": False}


__all__ = ["AutomatonInputs", "AutomatonDecision", "AutomatonState", "evaluate", "starting_balance", "status"]
