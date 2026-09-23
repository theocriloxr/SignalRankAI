"""Canonical server-side tier, quota, and access policy.

All adapters must delegate here. Tier decides product access and presentation;
it never bypasses freshness, provider, market, risk, consent, evidence, or
kill-switch checks.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping

POLICY_VERSION = "unified-platform-v1.5.1"
CATALOGUE_VERSION = POLICY_VERSION


class Tier(StrEnum):
    FREE = "FREE"
    PREMIUM = "PREMIUM"
    VIP = "VIP"
    PROFESSIONAL = "PROFESSIONAL"
    INSTITUTIONAL = "INSTITUTIONAL"
    ADMIN = "ADMIN"
    OWNER = "OWNER"


TIER_ORDER: tuple[Tier, ...] = (
    Tier.FREE,
    Tier.PREMIUM,
    Tier.VIP,
    Tier.PROFESSIONAL,
    Tier.INSTITUTIONAL,
    Tier.ADMIN,
    Tier.OWNER,
)

NON_BYPASSABLE_SAFETY_GATES = frozenset(
    {
        "fresh_quote",
        "provider_trust",
        "market_open",
        "risk_policy",
        "user_consent",
        "kill_switch",
        "evidence_gate",
        "global_feature_flag",
    }
)


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(float(os.getenv(name, str(default)) or default)))
    except Exception:
        return int(default)


def is_valid_tier(value: Tier | str | None) -> bool:
    raw = str(value or "").strip().upper()
    return raw in {tier.value for tier in Tier}


def normalize_tier(value: Tier | str | None) -> Tier:
    raw = str(value or Tier.FREE.value).strip().upper()
    try:
        return Tier(raw)
    except ValueError:
        return Tier.FREE


def tier_rank(value: Tier | str | None) -> int:
    return TIER_ORDER.index(normalize_tier(value))


@dataclass(frozen=True, slots=True)
class TierEntitlements:
    tier: Tier
    purchasable: bool
    daily_signal_limit: int
    minimum_signal_score: float
    delivery_delay_minutes: int
    delivery_priority: str
    max_tp_levels: int
    history_days: int
    analytics_level: str
    allowed_asset_classes: tuple[str, ...]
    allowed_profiles: tuple[str, ...]
    features: frozenset[str]
    support_level: str

    def has(self, feature: str) -> bool:
        feature_name = str(feature or "").strip().lower()
        return "*" in self.features or feature_name in self.features


_BASIC_FEATURES = frozenset(
    {
        "basic_signals",
        "proof_feed",
        "basic_outcomes",
        "basic_profile",
        "plan_comparison",
        "market_overview",
        "watchlist",
        "referrals",
        "support",
    }
)
_PREMIUM_FEATURES = _BASIC_FEATURES | frozenset(
    {
        "exact_levels",
        "lifecycle_updates",
        "paper_trading",
        "trade_management",
        "custom_alerts",
        "performance_analytics",
        "portfolio_analytics",
        "deep_history",
        "api_tokens",
        "broker_connection",
        "multi_asset",
        "detailed_provenance",
    }
)
_VIP_FEATURES = _PREMIUM_FEATURES | frozenset(
    {
        "tp3",
        "priority_delivery",
        "execution_preflight",
        "webhook_api",
        "advanced_profiles",
        "advanced_provenance",
        "ai_coaching",
        "risk_sizing",
        "priority_support",
    }
)
_PROFESSIONAL_FEATURES = _VIP_FEATURES | frozenset(
    {
        "rest_api",
        "websocket_api",
        "outbound_webhooks",
        "strategy_lab",
        "batch_backtesting",
        "advanced_exports",
        "team_workspace",
        "service_accounts",
        "higher_rate_limits",
    }
)
_INSTITUTIONAL_FEATURES = _PROFESSIONAL_FEATURES | frozenset(
    {
        "organization_tenancy",
        "institutional_sso",
        "white_label",
        "dedicated_quotas",
        "compliance_exports",
        "sla_reporting",
        "custom_integrations",
        "data_residency_controls",
    }
)


def _policies() -> Mapping[Tier, TierEntitlements]:
    all_assets = ("crypto", "fx", "commodity", "index", "stock")
    all_profiles = ("scalp", "day", "swing", "position")
    values = {
        Tier.FREE: TierEntitlements(
            tier=Tier.FREE,
            purchasable=False,
            daily_signal_limit=_env_int("FREE_SIGNAL_DAILY_LIMIT", 3),
            minimum_signal_score=80.0,
            delivery_delay_minutes=_env_int("FREE_SIGNAL_DELAY_MINUTES", 10),
            delivery_priority="normal",
            max_tp_levels=1,
            history_days=7,
            analytics_level="basic",
            allowed_asset_classes=("crypto", "fx"),
            allowed_profiles=("day", "swing"),
            features=_BASIC_FEATURES,
            support_level="community",
        ),
        Tier.PREMIUM: TierEntitlements(
            tier=Tier.PREMIUM,
            purchasable=True,
            daily_signal_limit=_env_int("PREMIUM_SIGNAL_DAILY_LIMIT", 15),
            minimum_signal_score=80.0,
            delivery_delay_minutes=_env_int("PREMIUM_SIGNAL_DELAY_MINUTES", 0),
            delivery_priority="high",
            max_tp_levels=2,
            history_days=30,
            analytics_level="detailed",
            allowed_asset_classes=all_assets,
            allowed_profiles=all_profiles,
            features=_PREMIUM_FEATURES,
            support_level="standard",
        ),
        Tier.VIP: TierEntitlements(
            tier=Tier.VIP,
            purchasable=True,
            daily_signal_limit=_env_int("VIP_SIGNAL_DAILY_LIMIT", 30),
            minimum_signal_score=80.0,
            delivery_delay_minutes=_env_int("VIP_SIGNAL_DELAY_MINUTES", 0),
            delivery_priority="priority",
            max_tp_levels=3,
            history_days=365,
            analytics_level="advanced",
            allowed_asset_classes=all_assets,
            allowed_profiles=all_profiles,
            features=_VIP_FEATURES,
            support_level="priority",
        ),
        Tier.PROFESSIONAL: TierEntitlements(
            tier=Tier.PROFESSIONAL,
            purchasable=True,
            daily_signal_limit=_env_int("PROFESSIONAL_SIGNAL_DAILY_LIMIT", 100),
            minimum_signal_score=75.0,
            delivery_delay_minutes=0,
            delivery_priority="professional",
            max_tp_levels=3,
            history_days=1825,
            analytics_level="professional",
            allowed_asset_classes=all_assets,
            allowed_profiles=all_profiles,
            features=_PROFESSIONAL_FEATURES,
            support_level="professional",
        ),
        Tier.INSTITUTIONAL: TierEntitlements(
            tier=Tier.INSTITUTIONAL,
            purchasable=True,
            daily_signal_limit=_env_int("INSTITUTIONAL_SIGNAL_DAILY_LIMIT", 1000),
            minimum_signal_score=0.0,
            delivery_delay_minutes=0,
            delivery_priority="institutional",
            max_tp_levels=3,
            history_days=3650,
            analytics_level="institutional",
            allowed_asset_classes=all_assets,
            allowed_profiles=all_profiles,
            features=_INSTITUTIONAL_FEATURES,
            support_level="dedicated",
        ),
        Tier.ADMIN: TierEntitlements(
            tier=Tier.ADMIN,
            purchasable=False,
            daily_signal_limit=_env_int("ADMIN_SIGNAL_DAILY_LIMIT", 100),
            minimum_signal_score=0.0,
            delivery_delay_minutes=0,
            delivery_priority="critical",
            max_tp_levels=3,
            history_days=3650,
            analytics_level="internal",
            allowed_asset_classes=all_assets,
            allowed_profiles=all_profiles,
            features=_INSTITUTIONAL_FEATURES | frozenset({"internal_operations", "audited_controls"}),
            support_level="internal",
        ),
        Tier.OWNER: TierEntitlements(
            tier=Tier.OWNER,
            purchasable=False,
            daily_signal_limit=_env_int("OWNER_SIGNAL_DAILY_LIMIT", 100),
            minimum_signal_score=0.0,
            delivery_delay_minutes=0,
            delivery_priority="critical",
            max_tp_levels=3,
            history_days=3650,
            analytics_level="internal",
            allowed_asset_classes=all_assets,
            allowed_profiles=all_profiles,
            features=frozenset({"*"}),
            support_level="internal",
        ),
    }
    return MappingProxyType(values)


def get_entitlements(value: Tier | str | None) -> TierEntitlements:
    return _policies()[normalize_tier(value)]


FEATURE_MINIMUM_TIER: Mapping[str, Tier] = MappingProxyType(
    {
        "basic_signals": Tier.FREE,
        "proof_feed": Tier.FREE,
        "basic_outcomes": Tier.FREE,
        "basic_profile": Tier.FREE,
        "plan_comparison": Tier.FREE,
        "market_overview": Tier.FREE,
        "watchlist": Tier.FREE,
        "referrals": Tier.FREE,
        "support": Tier.FREE,
        "exact_levels": Tier.PREMIUM,
        "lifecycle_updates": Tier.PREMIUM,
        "paper_trading": Tier.PREMIUM,
        "trade_management": Tier.PREMIUM,
        "custom_alerts": Tier.PREMIUM,
        "performance_analytics": Tier.PREMIUM,
        "portfolio_analytics": Tier.PREMIUM,
        "deep_history": Tier.PREMIUM,
        "api_tokens": Tier.PREMIUM,
        "broker_connection": Tier.PREMIUM,
        "multi_asset": Tier.PREMIUM,
        "detailed_provenance": Tier.PREMIUM,
        "tp3": Tier.VIP,
        "priority_delivery": Tier.VIP,
        "execution_preflight": Tier.VIP,
        "webhook_api": Tier.VIP,
        "advanced_profiles": Tier.VIP,
        "advanced_provenance": Tier.VIP,
        "ai_coaching": Tier.VIP,
        "risk_sizing": Tier.VIP,
        "priority_support": Tier.VIP,
        "rest_api": Tier.PROFESSIONAL,
        "websocket_api": Tier.PROFESSIONAL,
        "outbound_webhooks": Tier.PROFESSIONAL,
        "strategy_lab": Tier.PROFESSIONAL,
        "batch_backtesting": Tier.PROFESSIONAL,
        "advanced_exports": Tier.PROFESSIONAL,
        "team_workspace": Tier.PROFESSIONAL,
        "service_accounts": Tier.PROFESSIONAL,
        "higher_rate_limits": Tier.PROFESSIONAL,
        "organization_tenancy": Tier.INSTITUTIONAL,
        "institutional_sso": Tier.INSTITUTIONAL,
        "white_label": Tier.INSTITUTIONAL,
        "dedicated_quotas": Tier.INSTITUTIONAL,
        "compliance_exports": Tier.INSTITUTIONAL,
        "sla_reporting": Tier.INSTITUTIONAL,
        "custom_integrations": Tier.INSTITUTIONAL,
        "data_residency_controls": Tier.INSTITUTIONAL,
        "internal_operations": Tier.ADMIN,
        "audited_controls": Tier.ADMIN,
    }
)

FEATURE_VALUE = MappingProxyType(
    {
        "exact_levels": "complete entry, stop-loss, and target context",
        "lifecycle_updates": "timely tracked lifecycle updates",
        "paper_trading": "rehearsal with a paper ledger before live execution",
        "performance_analytics": "deeper history and transparent performance analysis",
        "portfolio_analytics": "portfolio exposure and active-position context",
        "api_tokens": "scoped programmatic access with revocable credentials",
        "broker_connection": "broker readiness and account connection tools",
        "tp3": "the complete three-target management ladder",
        "priority_delivery": "higher-priority workflow when a qualified setup is available",
        "execution_preflight": "execution-grade preflight; activation still requires every safety gate",
        "webhook_api": "controlled webhook and API workflow",
        "advanced_profiles": "more precise horizon and profile personalization",
        "rest_api": "scoped REST API access",
        "websocket_api": "real-time WebSocket streams",
        "outbound_webhooks": "signed outbound webhooks",
        "strategy_lab": "the governed strategy research laboratory",
        "organization_tenancy": "secure multi-user organization workspaces",
        "institutional_sso": "institutional single sign-on",
        "white_label": "contract-governed white-label delivery",
        "internal_operations": "audited internal operations",
    }
)


@dataclass(frozen=True, slots=True)
class AccessDecision:
    allowed: bool
    code: str
    current_tier: Tier
    required_tier: Tier
    feature: str
    reason: str
    policy_version: str = POLICY_VERSION
    safety_failures: tuple[str, ...] = ()

    def intent_payload(self, *, action: str, source: str) -> dict[str, Any]:
        return {
            "event": "upgrade_intent",
            "action": str(action),
            "source": str(source),
            "feature": self.feature,
            "current_tier": self.current_tier.value,
            "required_tier": self.required_tier.value,
            "decision_code": self.code,
            "policy_version": self.policy_version,
        }


def _locked_reason(current: Tier, required: Tier, feature: str) -> str:
    value = FEATURE_VALUE.get(feature, feature.replace("_", " "))
    return (
        f"🔒 This action is available on {required.value} because it includes {value}.\n"
        f"Your current tier is {current.value}. Safety, freshness, risk, consent, and kill-switch checks "
        "remain identical on every tier, and no outcome is guaranteed. Use /upgrade to compare plans."
    )


def evaluate_feature_access(
    tier: Tier | str | None,
    feature: str,
    *,
    safety_checks: Mapping[str, bool] | None = None,
) -> AccessDecision:
    current = normalize_tier(tier)
    feature_name = str(feature or "").strip().lower()
    required = FEATURE_MINIMUM_TIER.get(feature_name, Tier.FREE)
    if not get_entitlements(current).has(feature_name):
        return AccessDecision(
            False,
            "TIER_LOCKED",
            current,
            required,
            feature_name,
            _locked_reason(current, required, feature_name),
        )

    failures = tuple(
        sorted(
            name
            for name, passed in dict(safety_checks or {}).items()
            if name in NON_BYPASSABLE_SAFETY_GATES and passed is not True
        )
    )
    if failures:
        return AccessDecision(
            False,
            "SAFETY_BLOCKED",
            current,
            required,
            feature_name,
            "Safety check blocked this action: " + ", ".join(failures) + ". Upgrading cannot bypass it.",
            safety_failures=failures,
        )
    return AccessDecision(True, "ALLOWED", current, required, feature_name, "")


COMMAND_MINIMUM_TIER: Mapping[str, Tier] = MappingProxyType(
    {
        # Public/proof surface.
        "start": Tier.FREE, "help": Tier.FREE, "about": Tier.FREE,
        "faq": Tier.FREE, "disclaimer": Tier.FREE, "pricing": Tier.FREE,
        "upgrade": Tier.FREE, "signals": Tier.FREE, "signal": Tier.FREE,
        "proof": Tier.FREE, "outcome": Tier.FREE, "profile": Tier.FREE,
        "invite": Tier.FREE, "policy": Tier.FREE, "refunds": Tier.FREE,
        "recap": Tier.FREE, "language": Tier.FREE,
        "referral_leaderboard": Tier.FREE, "referral_rewards": Tier.FREE,
        "support": Tier.FREE, "status": Tier.FREE, "liveprice": Tier.FREE,
        "market": Tier.FREE, "myid": Tier.FREE, "account": Tier.FREE,
        "app": Tier.FREE, "open_app": Tier.FREE, "login_code": Tier.FREE,
    "link": Tier.FREE,
        "devices": Tier.FREE, "security": Tier.FREE,
        "timezone": Tier.FREE, "travelmode": Tier.FREE,
        "settings": Tier.FREE,
        "leaderboard": Tier.FREE, "tiers": Tier.FREE, "unlock": Tier.FREE,
        # Safe public-testing and paper/education surfaces.
        "public_test_status": Tier.FREE, "paper_balance": Tier.FREE,
        "paper_positions": Tier.FREE, "paper_performance": Tier.FREE,
        "paper_history": Tier.FREE, "paper_close_all": Tier.FREE, "paper_reset": Tier.FREE, "paper_settings": Tier.FREE,
        "paper_status": Tier.FREE, "paper_activity": Tier.FREE,
        "paper_skips": Tier.FREE, "paper_retry": Tier.FREE,
        "receipt": Tier.FREE, "receipts": Tier.FREE,
        "report_issue": Tier.FREE, "performance_truth": Tier.FREE,
        "payment_help": Tier.FREE, "refund_request": Tier.FREE,
        "contact_admin": Tier.FREE, "tester_feedback": Tier.FREE,
        "provider_health": Tier.FREE, "automaton_status": Tier.FREE,
        "automaton_pause": Tier.FREE, "automaton_resume": Tier.FREE,
        "automaton_reset_paper": Tier.FREE,
        # Premium workflow.
        "performance": Tier.PREMIUM, "stats": Tier.PREMIUM,
        "history": Tier.PREMIUM, "risk": Tier.PREMIUM,
        "alerts": Tier.PREMIUM, "analyze": Tier.PREMIUM,
        "dashboard": Tier.PREMIUM, "feedback": Tier.PREMIUM,
        "apikey": Tier.PREMIUM, "filter": Tier.PREMIUM,
        "reports": Tier.PREMIUM, "notify": Tier.PREMIUM,
        "portfolio": Tier.PREMIUM, "mission": Tier.PREMIUM,
        "quality": Tier.PREMIUM, "execution": Tier.PREMIUM,
        "mode": Tier.PREMIUM,
        "signal_quality": Tier.PREMIUM, "winrate": Tier.PREMIUM,
        "shadow_report": Tier.PREMIUM, "strategy_leaderboard": Tier.PREMIUM,
        "drawdown": Tier.PREMIUM, "setlot": Tier.PREMIUM,
        "mystats": Tier.PREMIUM, "referral": Tier.PREMIUM,
        "mt5": Tier.PREMIUM, "mt5link": Tier.PREMIUM,
        "mt5_link": Tier.PREMIUM, "mt5_status": Tier.PREMIUM,
        "connect_broker": Tier.PREMIUM, "cancel": Tier.PREMIUM,
        # VIP execution-grade/product surface.
        "simulate": Tier.VIP, "setrisk": Tier.VIP, "setwebhook": Tier.VIP,
        "elite": Tier.VIP, "early": Tier.VIP, "report": Tier.VIP,
        # Audited operations.
        "admin": Tier.ADMIN, "admin_dashboard": Tier.ADMIN,
        "admin_broadcast": Tier.ADMIN, "force_market_scan": Tier.ADMIN,
        "force_signal": Tier.ADMIN, "gemini": Tier.ADMIN,
        "gemini_review": Tier.ADMIN, "gemini_analyze": Tier.ADMIN,
        "gemini_audit": Tier.ADMIN, "gemini_predict": Tier.ADMIN,
        "codex_audit": Tier.ADMIN, "admin_top_assets": Tier.ADMIN,
        "codex_log_review": Tier.ADMIN, "codex_fix_plan": Tier.ADMIN,
        "codex_security_scan": Tier.ADMIN, "codex_release_check": Tier.ADMIN,
        "codex_test_plan": Tier.ADMIN, "codex_refactor_plan": Tier.ADMIN,
        "codex_pr_summary": Tier.ADMIN, "codex_generate_issue": Tier.ADMIN,
        "admin_top_strategies": Tier.ADMIN, "admin_user_engagement": Tier.ADMIN,
        "qa_report": Tier.ADMIN, "selfcheck": Tier.ADMIN,
        "ops_health": Tier.ADMIN, "system": Tier.ADMIN,
        "db_health": Tier.ADMIN, "engine_debug": Tier.ADMIN,
        "delivery_debug": Tier.ADMIN, "signal_debug": Tier.ADMIN,
        "format_debug": Tier.ADMIN, "profile_debug": Tier.ADMIN,
        "why_no_signal": Tier.ADMIN, "ohlc_health": Tier.ADMIN,
        "asset_capability": Tier.ADMIN, "asset_class_test": Tier.ADMIN,
        "all_asset_test_status": Tier.ADMIN,
        "delivery_eligibility": Tier.ADMIN,
        "blast_terms": Tier.ADMIN, "assets": Tier.ADMIN,
        "release_guard": Tier.ADMIN, "automaton_report": Tier.ADMIN,
        "admin_receipt_lookup": Tier.ADMIN, "admin_payment_lookup": Tier.ADMIN,
        "admin_user": Tier.ADMIN, "admin_subscription_fix": Tier.ADMIN,
        "admin_signal_lookup": Tier.ADMIN, "admin_feedback": Tier.ADMIN,
        "adaptive_status": Tier.ADMIN, "adaptive_pause": Tier.ADMIN,
        "adaptive_resume": Tier.ADMIN, "adaptive_promote": Tier.ADMIN,
        "adaptive_suspend": Tier.ADMIN, "adaptive_rollback": Tier.ADMIN,
        # Owner-only controls.
        "dev_pause": Tier.OWNER, "dev_resume": Tier.OWNER,
        "dev_force_signal": Tier.OWNER, "dev_invalidate": Tier.OWNER,
        "owner_users": Tier.OWNER, "owner_revenue": Tier.OWNER,
        "version": Tier.OWNER, "correct_signal": Tier.OWNER,
        "provider_status": Tier.OWNER, "broadcast": Tier.OWNER,
        "owner_test_delivery": Tier.OWNER,
        "performance_rebuild": Tier.OWNER,
        "performance_audit": Tier.OWNER,
        "outcome_rebuild": Tier.OWNER,
        "outcome_audit": Tier.OWNER,
        "dedup_audit": Tier.OWNER,
        "notification_audit": Tier.OWNER,
        "paper_audit": Tier.OWNER,
        "queue_status": Tier.OWNER,
        "queue_replay": Tier.OWNER,
        "dead_letter_status": Tier.OWNER,
        "dead_letter_replay": Tier.OWNER,
        "ledger_audit": Tier.OWNER,
        "payment_reconcile": Tier.OWNER,
        "release_status": Tier.OWNER,
        "kill_switch": Tier.OWNER,
        "system_health": Tier.ADMIN,
    }
)

COMMAND_FEATURE: Mapping[str, str] = MappingProxyType(
    {
        "performance": "performance_analytics", "stats": "performance_analytics",
        "history": "deep_history", "alerts": "custom_alerts",
        "dashboard": "performance_analytics", "apikey": "api_tokens",
        "portfolio": "portfolio_analytics", "mission": "portfolio_analytics",
        "simulate": "paper_trading", "setwebhook": "webhook_api",
        "mt5": "broker_connection", "mt5link": "broker_connection",
        "mt5_link": "broker_connection", "mt5_status": "broker_connection",
        "connect_broker": "broker_connection", "setrisk": "risk_sizing",
        "admin": "internal_operations", "admin_dashboard": "internal_operations",
    }
)


def evaluate_command_access(command: str, tier: Tier | str | None) -> AccessDecision:
    name = str(command or "").strip().lstrip("/").lower()
    current = normalize_tier(tier)
    required = COMMAND_MINIMUM_TIER.get(name, Tier.FREE)
    feature = COMMAND_FEATURE.get(name, f"command:{name or 'unknown'}")
    if tier_rank(current) < tier_rank(required):
        return AccessDecision(
            False,
            "TIER_LOCKED",
            current,
            required,
            feature,
            _locked_reason(current, required, feature),
        )
    return AccessDecision(True, "ALLOWED", current, required, feature, "")


BUTTON_FEATURE: Mapping[str, str] = MappingProxyType(
    {
        "nav_signals": "basic_signals",
        "nav_performance": "performance_analytics",
        "nav_proof": "proof_feed",
        "nav_upgrade": "plan_comparison",
        "nav_account": "basic_profile",
        "nav_support": "support",
        "check_outcome": "basic_outcomes",
        "monitor_signal": "lifecycle_updates",
        "signal_reaction": "basic_signals",
        "advanced_portfolio": "portfolio_analytics",
        "mt5_link_guide": "broker_connection",
        "mt5_settings": "broker_connection",
        "mt5_trade": "execution_preflight",
        "exec_mt5": "execution_preflight",
        "webhook": "webhook_api",
        "paper_trade": "paper_trading",
        "admin": "internal_operations",
    }
)


def button_action_name(callback_data: str) -> str:
    raw = str(callback_data or "").strip().lower()
    for name in sorted(BUTTON_FEATURE, key=len, reverse=True):
        if raw == name or raw.startswith(f"{name}_"):
            return name
    return raw


def evaluate_button_access(
    callback_data: str,
    tier: Tier | str | None,
    *,
    safety_checks: Mapping[str, bool] | None = None,
) -> AccessDecision:
    action = button_action_name(callback_data)
    feature = BUTTON_FEATURE.get(action, "basic_signals")
    return evaluate_feature_access(tier, feature, safety_checks=safety_checks)


def policy_snapshot() -> dict[str, Any]:
    return {
        "version": POLICY_VERSION,
        "tiers": {
            tier.value: {
                "rank": tier_rank(tier),
                "purchasable": get_entitlements(tier).purchasable,
                "daily_signal_limit": get_entitlements(tier).daily_signal_limit,
                "max_tp_levels": get_entitlements(tier).max_tp_levels,
                "delivery_priority": get_entitlements(tier).delivery_priority,
                "features": sorted(get_entitlements(tier).features),
            }
            for tier in TIER_ORDER
        },
    }


__all__ = [
    "AccessDecision",
    "BUTTON_FEATURE",
    "COMMAND_FEATURE",
    "COMMAND_MINIMUM_TIER",
    "FEATURE_MINIMUM_TIER",
    "CATALOGUE_VERSION",
    "NON_BYPASSABLE_SAFETY_GATES",
    "POLICY_VERSION",
    "TIER_ORDER",
    "Tier",
    "TierEntitlements",
    "button_action_name",
    "evaluate_button_access",
    "evaluate_command_access",
    "evaluate_feature_access",
    "get_entitlements",
    "is_valid_tier",
    "normalize_tier",
    "policy_snapshot",
    "tier_rank",
]
