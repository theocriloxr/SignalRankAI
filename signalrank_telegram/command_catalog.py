"""Canonical launch command catalogue.

Only commands that provide a meaningful user action are exposed in Telegram's
command menu and /help. Compatibility handlers may remain registered but are
intentionally hidden until they have a launch-grade product surface.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from core.tier_policy import tier_rank


@dataclass(frozen=True)
class CommandSpec:
    name: str
    description: str
    tier: str = "FREE"
    section: str = "Core"
    botfather: bool = True


COMMANDS: tuple[CommandSpec, ...] = (
    # Free / public
    CommandSpec("start", "Start the bot and accept the risk terms", "FREE", "Getting started"),
    CommandSpec("help", "Show commands available for your account", "FREE", "Getting started"),
    CommandSpec("about", "Platform features and your verified signal totals", "FREE", "Getting started"),
    CommandSpec("status", "Subscription, tier, and account status", "FREE", "Account"),
    CommandSpec("account", "Open your account controls", "FREE", "Account"),
    CommandSpec("app", "Open or activate your unified web and mobile account", "FREE", "Account"),
    CommandSpec("login_code", "Generate a one-time app activation code", "FREE", "Account"),
    CommandSpec("link", "Link an app-created account to Telegram", "FREE", "Account"),
    CommandSpec("devices", "Review signed-in application sessions", "FREE", "Account"),
    CommandSpec("security", "Review account security guidance", "FREE", "Account"),
    CommandSpec("pricing", "View current plans and prices", "FREE", "Account"),
    CommandSpec("upgrade", "Subscribe or change plan", "FREE", "Account"),
    CommandSpec("tiers", "Compare Free, Premium, and VIP access", "FREE", "Account"),
    CommandSpec("signals", "Show signals confirmed for your tier", "FREE", "Signals"),
    CommandSpec("signal", "Open one signal by its reference", "FREE", "Signals"),
    CommandSpec("outcome", "Check a delivered signal outcome", "FREE", "Signals"),
    CommandSpec("proof", "View verified completed outcomes", "FREE", "Signals"),
    CommandSpec("liveprice", "Fetch the current price of an asset", "FREE", "Market"),
    CommandSpec("market", "View the current multi-asset market overview", "FREE", "Market"),
    CommandSpec("profile", "Choose scalp, day, swing, or position style", "FREE", "Preferences"),
    CommandSpec("paper_balance", "View or initialize your virtual balance", "FREE", "Paper trading"),
    CommandSpec("paper_positions", "View open automatic paper positions", "FREE", "Paper trading"),
    CommandSpec("paper_history", "View completed and skipped paper trades", "FREE", "Paper trading"),
    CommandSpec("paper_performance", "View paper-only performance statistics", "FREE", "Paper trading"),
    CommandSpec("paper_settings", "Control automatic paper entries and risk", "FREE", "Paper trading"),
    CommandSpec("paper_close_all", "Close all virtual positions with confirmation", "FREE", "Paper trading"),
    CommandSpec("paper_reset", "Reset paper history with explicit confirmation", "FREE", "Paper trading"),
    CommandSpec("invite", "Get your referral link", "FREE", "Referrals"),
    CommandSpec("referral_leaderboard", "View the referral leaderboard", "FREE", "Referrals"),
    CommandSpec("referral_rewards", "View your referral rewards", "FREE", "Referrals"),
    CommandSpec("support", "Contact support and report a problem", "FREE", "Support"),
    CommandSpec("faq", "Read common product questions", "FREE", "Support"),
    CommandSpec("disclaimer", "Read the financial-risk disclaimer", "FREE", "Support"),
    CommandSpec("myid", "Show your Telegram ID and tier", "FREE", "Support"),
    CommandSpec("language", "Change notification language", "FREE", "Preferences"),
    # Premium
    CommandSpec("performance", "Delivered-signal performance with provenance", "PREMIUM", "Analytics"),
    CommandSpec("stats", "Win rate, R multiples, and sample size", "PREMIUM", "Analytics"),
    CommandSpec("history", "View your delivered signal history", "PREMIUM", "Analytics"),
    CommandSpec("dashboard", "Open your analytics dashboard", "PREMIUM", "Analytics"),
    CommandSpec("portfolio", "View active signals and exposure", "PREMIUM", "Analytics"),
    CommandSpec("mission", "Open Signal Mission Control", "PREMIUM", "Analytics"),
    CommandSpec("risk", "View or update risk guidance", "PREMIUM", "Preferences"),
    CommandSpec("alerts", "Configure TP, SL, and quiet-hour alerts", "PREMIUM", "Preferences"),
    CommandSpec("filter", "Set score, R/R, asset, and regime filters", "PREMIUM", "Preferences"),
    CommandSpec("notify", "Choose notification assets and timeframes", "PREMIUM", "Preferences"),
    CommandSpec("analyze", "Request an on-demand asset analysis", "PREMIUM", "Market"),
    CommandSpec("feedback", "Rate a signal or report an incorrect outcome", "PREMIUM", "Support"),
    CommandSpec("execution", "Choose manual or eligible automatic execution", "PREMIUM", "Broker"),
    CommandSpec("connect_broker", "Start secure MT5/MetaApi connection setup", "PREMIUM", "Broker"),
    CommandSpec("mt5_link", "Link or replace your MT5/MetaApi account", "PREMIUM", "Broker"),
    CommandSpec("mt5_status", "Check broker readiness and execution preflight", "PREMIUM", "Broker"),
    CommandSpec("setlot", "Set the fixed lot used by eligible execution", "PREMIUM", "Broker"),
    CommandSpec("mystats", "View broker execution statistics", "PREMIUM", "Broker"),
    CommandSpec("referral", "View your referral code and statistics", "PREMIUM", "Referrals"),
    CommandSpec("cancel", "Turn off subscription auto-renewal", "PREMIUM", "Account"),
    # VIP
    CommandSpec("simulate", "Simulate using your confirmed delivered outcomes", "VIP", "VIP analytics"),
    CommandSpec("setrisk", "Set the execution preflight risk percentage", "VIP", "VIP controls"),
    CommandSpec("elite", "View VIP high-conviction signals", "VIP", "VIP signals"),
    CommandSpec("early", "View eligible early-access alerts", "VIP", "VIP signals"),
    CommandSpec("report", "Generate the detailed performance report", "VIP", "VIP analytics"),
    # Admin
    CommandSpec("admin", "Open the audited admin dashboard", "ADMIN", "Admin"),
    CommandSpec("admin_broadcast", "Send an audited platform announcement", "ADMIN", "Admin"),
    CommandSpec("force_market_scan", "Request one controlled market scan", "ADMIN", "Admin"),
    CommandSpec("force_signal", "Generate a controlled diagnostic signal", "ADMIN", "Admin"),
    CommandSpec("gemini", "Run the Gemini and ML review diagnostics", "ADMIN", "Admin"),
    CommandSpec("gemini_review", "Inspect the current AI review pipeline", "ADMIN", "Admin"),
    CommandSpec("qa_report", "Run the deployment QA report", "ADMIN", "Admin"),
    CommandSpec("selfcheck", "Run internal command and callback checks", "ADMIN", "Admin"),
    CommandSpec("ops_health", "View operational health and queues", "ADMIN", "Admin"),
    CommandSpec("system", "View system runtime health", "ADMIN", "Admin"),
    CommandSpec("db_health", "View database health and admission pressure", "ADMIN", "Admin"),
    CommandSpec("engine_debug", "Inspect the signal engine pipeline", "ADMIN", "Admin"),
    CommandSpec("assets", "Inspect enabled assets and capabilities", "ADMIN", "Admin"),
    CommandSpec("release_guard", "Check launch safety gates", "ADMIN", "Admin"),
    CommandSpec("adaptive_status", "Inspect adaptive profiles and lifecycle", "ADMIN", "Adaptive"),
    CommandSpec("adaptive_pause", "Pause adaptive learning and weighting", "ADMIN", "Adaptive"),
    CommandSpec("adaptive_resume", "Resume adaptive learning", "ADMIN", "Adaptive"),
    CommandSpec("adaptive_promote", "Promote an evidence-qualified profile", "ADMIN", "Adaptive"),
    CommandSpec("adaptive_suspend", "Suspend an adaptive profile", "ADMIN", "Adaptive"),
    CommandSpec("adaptive_rollback", "Restore an asset rollback profile", "ADMIN", "Adaptive"),
    # Owner
    CommandSpec("dev_pause", "Pause the signal engine", "OWNER", "Owner"),
    CommandSpec("dev_resume", "Resume the signal engine", "OWNER", "Owner"),
    CommandSpec("owner_users", "View registered users and tier counts", "OWNER", "Owner"),
    CommandSpec("owner_revenue", "View verified subscription revenue", "OWNER", "Owner"),
    CommandSpec("version", "Show the deployed build fingerprint", "OWNER", "Owner"),
    CommandSpec("provider_status", "View provider circuits and freshness", "OWNER", "Owner"),
    CommandSpec("broadcast", "Send an owner announcement", "OWNER", "Owner"),
    CommandSpec("performance_rebuild", "Run bounded performance projection rebuild", "OWNER", "Owner"),
    CommandSpec("performance_audit", "Audit performance projection integrity", "OWNER", "Owner"),
    CommandSpec("outcome_rebuild", "Run bounded outcome and outbox rebuild", "OWNER", "Owner"),
    CommandSpec("outcome_audit", "Audit outcome projection and notification state", "OWNER", "Owner"),
    CommandSpec("dedup_audit", "Audit deduplication and lock policy outputs", "OWNER", "Owner"),
    CommandSpec("notification_audit", "Audit notification delivery queues", "OWNER", "Owner"),
    CommandSpec("paper_audit", "Audit paper trading lifecycle aggregates", "OWNER", "Owner"),
    CommandSpec("queue_status", "Show owner job and queue checkpoint status", "OWNER", "Owner"),
    CommandSpec("queue_replay", "Replay bounded reconciliation queues", "OWNER", "Owner"),
    CommandSpec("dead_letter_status", "Inspect dead-letter queue depth", "OWNER", "Owner"),
    CommandSpec("dead_letter_replay", "Replay dead-letter items into retry queue", "OWNER", "Owner"),
    CommandSpec("ledger_audit", "Run canonical ledger consistency audit", "OWNER", "Owner"),
    CommandSpec("payment_reconcile", "Audit payment/webhook receipt reconciliation", "OWNER", "Owner"),
    CommandSpec("release_status", "Show release fingerprint and runtime version", "OWNER", "Owner"),
    CommandSpec("kill_switch", "Inspect or toggle the global kill switch", "OWNER", "Owner"),
    CommandSpec("system_health", "Summarize DB/Redis/runtime safety health", "ADMIN", "Admin"),
    CommandSpec("why_no_signal", "Explain the most recent signal rejections", "OWNER", "Owner diagnostics"),
    CommandSpec("delivery_eligibility", "Inspect a user's delivery eligibility", "OWNER", "Owner diagnostics"),
    CommandSpec("ohlc_health", "Inspect OHLC provider coverage", "OWNER", "Owner diagnostics"),
    CommandSpec("asset_capability", "Inspect one asset's runtime capability", "OWNER", "Owner diagnostics"),
    CommandSpec("asset_class_test", "Run asset-class routing checks", "OWNER", "Owner diagnostics"),
    CommandSpec("all_asset_test_status", "View the all-asset certification status", "OWNER", "Owner diagnostics"),
    CommandSpec("owner_test_delivery", "Send one audited owner test delivery", "OWNER", "Owner diagnostics"),
)


def normalized_tier(tier: str | None) -> str:
    value = str(tier or "FREE").strip().upper()
    return value if value in {"FREE", "PREMIUM", "VIP", "PROFESSIONAL", "INSTITUTIONAL", "ADMIN", "OWNER"} else "FREE"


def visible_commands(tier: str | None, *, botfather_only: bool = False) -> list[CommandSpec]:
    current = normalized_tier(tier)
    current_rank = tier_rank(current)
    specs = [
        spec for spec in COMMANDS
        if tier_rank(spec.tier) <= current_rank and (spec.botfather or not botfather_only)
    ]
    # Telegram Bot API supports at most 100 commands in a scope.
    return specs[:100]


def botfather_commands(tier: str | None) -> list[tuple[str, str]]:
    return [(spec.name, spec.description[:256]) for spec in visible_commands(tier, botfather_only=True)]


def grouped_help(tier: str | None) -> list[tuple[str, list[CommandSpec]]]:
    groups: list[tuple[str, list[CommandSpec]]] = []
    for spec in visible_commands(tier):
        for title, entries in groups:
            if title == spec.section:
                entries.append(spec)
                break
        else:
            groups.append((spec.section, [spec]))
    return groups


def command_description(name: str) -> str:
    normalized = str(name or "").strip().lstrip("/").lower()
    for spec in COMMANDS:
        if spec.name == normalized:
            return spec.description
    return ""


__all__ = [
    "COMMANDS", "CommandSpec", "botfather_commands", "command_description",
    "grouped_help", "normalized_tier", "visible_commands",
]
