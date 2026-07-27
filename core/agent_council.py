"""Governed internal Agent Council registry.

Agents are role descriptors, not autonomous workers.  The registry documents
allowed inputs/outputs and forbidden actions so orchestration remains auditable
and deterministic by default.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable


class CouncilMode(StrEnum):
    READ_ONLY = "READ_ONLY"
    PROPOSAL = "PROPOSAL"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"


@dataclass(frozen=True, slots=True)
class AgentSpec:
    name: str
    role: str
    allowed_inputs: tuple[str, ...]
    allowed_outputs: tuple[str, ...]
    forbidden_actions: tuple[str, ...]
    required_approval: CouncilMode = CouncilMode.READ_ONLY
    timeout_seconds: float = 10.0
    cost_limit_usd: float = 0.0
    feature_flag: str = "AGENT_COUNCIL_ENABLED"


_FORBIDDEN = (
    "execute_real_trade",
    "enable_auto_trade",
    "enable_copy_trade",
    "withdraw_funds",
    "modify_production_code",
    "read_raw_secrets",
)


def _spec(name: str, role: str, inputs: Iterable[str], outputs: Iterable[str], approval: CouncilMode = CouncilMode.READ_ONLY) -> AgentSpec:
    return AgentSpec(name, role, tuple(inputs), tuple(outputs), _FORBIDDEN, approval)


AGENT_SPECS: tuple[AgentSpec, ...] = (
    _spec("market_data", "Market Data Agent", ("quotes", "provider_health"), ("trust_decision", "provider_recommendation")),
    _spec("strategy_research", "Strategy Research Agent", ("outcomes", "evidence"), ("quarantine_recommendation", "promotion_candidate"), CouncilMode.PROPOSAL),
    _spec("signal_quality", "Signal Quality Agent", ("candidate", "risk", "quote"), ("quality_explanation", "quality_flags")),
    _spec("risk_manager", "Risk Manager Agent", ("candidate", "portfolio", "drawdown"), ("risk_decision",)),
    _spec("delivery_guard", "Final Delivery Guard Agent", ("quote", "freshness", "market_state"), ("delivery_decision",)),
    _spec("outcome", "Outcome Agent", ("trusted_quotes", "lifecycle"), ("outcome_events",)),
    _spec("backtest", "Backtest Agent", ("historical_data", "manifest"), ("evidence_report",)),
    _spec("shadow", "Shadow Trading Agent", ("blocked_signals", "outcomes"), ("shadow_report",)),
    _spec("paper", "Paper Trading Agent", ("signal", "paper_account"), ("paper_fill", "paper_report")),
    _spec("automaton", "Automaton Supervisor Agent", ("system_metrics", "evidence"), ("state_recommendation",), CouncilMode.PROPOSAL),
    _spec("portfolio", "Portfolio Agent", ("positions", "risk"), ("exposure_report",)),
    _spec("business", "Business Agent", ("tier_events", "receipts"), ("product_recommendation",)),
    _spec("support", "Support Agent", ("tester_feedback",), ("support_summary",)),
    _spec("compliance", "Compliance and Trust Agent", ("public_copy", "metrics"), ("compliance_flags",)),
    _spec("codexops", "CodexOps Agent", ("source", "logs", "tests"), ("audit_report", "patch_proposal"), CouncilMode.PROPOSAL),
    _spec("release_guard", "Release Guard Agent", ("tests", "health", "flags"), ("release_verdict",)),
)


def get_agent(name: str) -> AgentSpec:
    key = str(name or "").strip().lower()
    for spec in AGENT_SPECS:
        if spec.name == key:
            return spec
    raise KeyError(f"unknown_agent:{key}")


def council_manifest() -> list[dict[str, object]]:
    return [
        {
            "name": spec.name,
            "role": spec.role,
            "required_approval": spec.required_approval.value,
            "forbidden_actions": list(spec.forbidden_actions),
            "feature_flag": spec.feature_flag,
        }
        for spec in AGENT_SPECS
    ]


__all__ = ["AgentSpec", "CouncilMode", "AGENT_SPECS", "get_agent", "council_manifest"]
