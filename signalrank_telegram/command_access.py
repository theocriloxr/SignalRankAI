"""Tier-based command access control and help menu system.

Maps commands to required tier and builds dynamic help based on user's current tier.
Handles tier changes (demotion) by checking live tier on each access.
"""

import os
from core.redis_state import state

# Map of command -> minimum tier required
# NOTE: "unlock" is intentionally NOT listed in any help menu but IS in COMMAND_TIERS
# for access-control purposes (owners can bypass kill-switch).
COMMAND_TIERS = {
    # ── FREE (public) ─────────────────────────────────────────────────────────
    "start":               "FREE",
    "help":                "FREE",
    "about":               "FREE",
    "faq":                "FREE",
    "disclaimer":          "FREE",
    "pricing":             "FREE",
    "upgrade":             "FREE",
    "signals":             "FREE",
    "signal":              "FREE",
    "proof":               "FREE",
    "outcome":             "FREE",
    "invite":              "FREE",
    "policy":              "FREE",
    "refunds":             "FREE",
    "recap":              "FREE",
    "language":            "FREE",
    "referral_leaderboard":"FREE",
    "referral_rewards":    "FREE",
    "support":             "FREE",
    "status":              "FREE",
    "liveprice":           "FREE",
    "market":              "FREE",
    "myid":                "FREE",
    "account":            "FREE",
    "leaderboard":         "FREE",
    "tiers":               "FREE",   # shows tier comparison — useful for all
    # unlock is intentionally omitted from help menus — keep access for owners
    "unlock":              "FREE",

    # ── PREMIUM ───────────────────────────────────────────────────────────────
    "performance":         "PREMIUM",
    "stats":               "PREMIUM",
    "history":             "PREMIUM",
    "risk":                "PREMIUM",
    "alerts":              "PREMIUM",
    "analyze":             "PREMIUM",
    "dashboard":           "PREMIUM",
    "feedback":            "PREMIUM",
    "apikey":              "PREMIUM",
    "filter":              "PREMIUM",
    "reports":             "PREMIUM",
    "notify":              "PREMIUM",
    "portfolio":           "PREMIUM",
    "quality":             "PREMIUM",
    "execution":           "PREMIUM",
    "drawdown":            "PREMIUM",
    "setlot":              "PREMIUM",
    "setwebhook":          "PREMIUM",
    "mystats":             "PREMIUM",
    "referral":            "PREMIUM",
    "mt5":                 "PREMIUM",
    "mt5link":             "PREMIUM",
    "mt5_link":            "PREMIUM",
    "mt5_status":          "PREMIUM",
    "connect_broker":      "PREMIUM",
    "cancel":              "PREMIUM",

    # ── VIP ───────────────────────────────────────────────────────────────────
    "simulate":            "VIP",
    "setrisk":             "VIP",
    "elite":               "VIP",
    "early":               "VIP",
    "report":              "VIP",
    "mode":               "VIP",           # Trading mode (manual/auto/none)

    # ── ADMIN ─────────────────────────────────────────────────────────────────
    "admin":               "ADMIN",
    "admin_dashboard":     "ADMIN",
    "admin_broadcast":     "ADMIN",
    "force_market_scan":   "ADMIN",
    "force_signal":        "ADMIN",
    "gemini":             "ADMIN",
    "gemini_review":      "ADMIN",
    "gemini_analyze":    "ADMIN",
    "gemini_audit":      "ADMIN",
    "gemini_predict":     "ADMIN",
    "admin_top_assets":   "ADMIN",
    "admin_top_strategies":"ADMIN",
    "admin_user_engagement":"ADMIN",
    "qa_report":          "ADMIN",
    "selfcheck":          "ADMIN",
    "ops_health":         "ADMIN",
    "blast_terms":        "ADMIN",
    "assets":            "ADMIN",

    # ── OWNER only (hidden from regular help) ─────────────────────────────────
    "dev_pause":          "OWNER",
    "dev_resume":         "OWNER",
    "dev_force_signal":  "OWNER",
    "dev_invalidate":    "OWNER",
    "owner_users":       "OWNER",
    "owner_revenue":     "OWNER",
    "version":           "OWNER",
    "correct_signal":   "OWNER",
    "provider_status":  "OWNER",
    "broadcast":        "OWNER",
}

# Tier ranking (higher = more access)
TIER_RANKS = {
    "FREE": 0,
    "PREMIUM": 1,
    "VIP": 2,
    "ADMIN": 3,
    "OWNER": 3,
}

# Command descriptions and help text per tier
COMMAND_HELP = {
"FREE": {
        "title": "🆓 FREE Tier Commands",
        "commands": [
            ("start",                "Start / re-register the bot"),
            ("help",                 "Show this help menu"),
            ("status",               "Check your subscription status & tier"),
            ("upgrade",              "Subscribe to Premium or VIP"),
            ("pricing",              "View all plan prices"),
            ("tiers",                "Compare Free / Premium / VIP features"),
            ("signals",              "View latest signals (limited on Free)"),
            ("signal",               "Lookup a specific signal by reference"),
            ("proof",                "Proof feed: recent verified wins/outcomes"),
            ("outcome",              "View your 24h outcomes or check one signal outcome"),
            ("liveprice",            "Get real-time price for any asset"),
            ("market",               "Market overview — major assets at a glance"),
            ("invite",               "Get your referral link and earn rewards"),
            ("referral_leaderboard",  "Top referrers leaderboard"),
            ("referral_rewards",     "View your referral rewards & history"),
            ("recap",                "Weekly performance recap"),
            ("about",                "About SignalRankAI"),
            ("faq",                  "Frequently asked questions"),
            ("disclaimer",           "Financial risk disclaimer"),
            ("policy",               "Subscription & refund policy"),
            ("refunds",              "Refund policy"),
            ("support",              "Contact support: @theocrilox"),
            ("myid",                 "Your Telegram user ID and current tier"),
            ("account",              "Alias for /status"),
            ("language",             "Change notification language"),
        ],
        "footer": (
            "📌 Free Tier Limits:\n"
            "• 1–3 signals/day (delayed delivery)\n"
            "• Basic outcome notifications\n"
            "• Referral rewards (earn free Premium days)\n"
            "• Live prices & market overview\n\n"
            "💡 /upgrade to PREMIUM for real-time signals with full Entry, SL & TP."
        ),
    },
    "PREMIUM": {
        "title": "⭐ PREMIUM Tier Commands",
        "commands": [
            # ─ All Free commands ────────────────────────────────────────────
            ("start",                "Start / re-register the bot"),
            ("help",                 "Show this help menu"),
            ("status",               "Subscription status & tier details"),
            ("upgrade",              "Upgrade to VIP"),
            ("pricing",              "View all plan prices"),
            ("tiers",                "Compare tier features"),
            ("signals",              "All active signals with full Entry/SL/TP"),
            ("signal",               "Lookup a specific signal (full details)"),
            ("outcome",              "Check full outcome with R-multiple"),
            ("liveprice",            "Real-time price for any asset"),
            ("market",               "Market overview — major assets"),
            ("invite",               "Referral link (earn +7 days Premium per referral)"),
            ("referral_leaderboard", "Top referrers leaderboard"),
            ("referral_rewards",     "Your referral rewards history"),
            ("recap",                "Weekly performance recap"),
            ("about",                "About SignalRankAI"),
            ("faq",                  "FAQ"),
            ("disclaimer",           "Risk disclaimer"),
            ("policy",               "Subscription & refund policy"),
            ("support",              "Contact support"),
            ("myid",                 "Your Telegram ID and tier"),
            ("language",             "Change notification language"),
            # ─ Premium-only ────────────────────────────────────────────
            ("performance",          "Full 30-day performance analytics"),
            ("stats",                "Win rate, net R, avg R/trade"),
            ("history",              "Recent signal history (last 10)"),
            ("risk",                 "Risk management guidance"),
            ("alerts",               "TP/SL alert settings & quiet hours"),
            ("analyze",              "AI analysis for any asset/timeframe"),
            ("dashboard",            "Analytics dashboard"),
            ("portfolio",            "Active signals with live P&L"),
            ("reports",              "Daily/weekly report opt-in"),
            ("notify",               "Notification preferences (assets/TFs)"),
            ("filter",               "Custom signal filters (score/RR/regime)"),
            ("feedback",             "Rate a signal or report an issue"),
            ("apikey",               "API key for programmatic signal access"),
            ("mystats",              "MT5 execution stats"),
            ("setlot",               "Set fixed lot size for MT5 execution"),
            ("setrisk",              "Set max risk % per trade (VIP auto-sizing)"),
            ("mt5_link",             "Link your MT5/MetaApi account"),
            ("mt5_status",           "Check MT5 connection status"),
            ("connect_broker",       "Connect your broker account step-by-step"),
            ("referral",             "Your referral code & stats"),
            ("cancel",               "Cancel your subscription auto-renewal"),
        ],
        "footer": (
            "⭐ Premium Features:\n"
            "• Real-time signals (5m–24h timeframes)\n"
            "• Full Entry, SL, and TP levels\n"
            "• AI Confluence scores (15-strategy engine)\n"
            "• TP/SL hit notifications\n"
            "• 30-day win rate & R-multiple tracking\n"
            "• MT5 auto-execution (3 trades/day, fixed lot)\n"
            "• Portfolio tracking with live P&L\n\n"
            "💡 /upgrade to VIP for elite high-conviction signals."
        ),
    },
    "VIP": {
        "title": "� VIP Tier Commands",
        "commands": [
            # ─ All Free commands ────────────────────────────────────────────
            ("start",                "Start / re-register"),
            ("help",                 "This help menu"),
            ("status",               "Subscription & tier details"),
            ("upgrade",              "Plan details"),
            ("pricing",              "View pricing"),
            ("tiers",                "Tier comparison"),
            ("signals",              "Your VIP-grade signals"),
            ("signal",               "Lookup a signal (full analysis + ML score)"),
            ("outcome",              "Full outcome with R-multiples"),
            ("liveprice",            "Real-time price for any asset"),
            ("market",               "Market overview"),
            ("invite",               "Referral link & rewards"),
            ("referral_leaderboard", "Leaderboard"),
            ("referral_rewards",     "Referral rewards"),
            ("recap",                "Weekly recap"),
            ("about",                "About SignalRankAI"),
            ("faq",                  "FAQ"),
            ("disclaimer",           "Risk disclaimer"),
            ("policy",               "Policy"),
            ("support",              "Support"),
            ("myid",                 "Your ID and tier"),
            ("language",             "Language settings"),
            # ─ Premium commands ────────────────────────────────────────
            ("performance",          "Full performance analytics (unlimited history)"),
            ("stats",                "Win rate, net R, avg R/trade"),
            ("history",              "Complete signal history"),
            ("risk",                 "Advanced risk management"),
            ("alerts",               "Granular TP/SL alert settings"),
            ("analyze",              "AI analysis for any asset/timeframe"),
            ("dashboard",            "Analytics dashboard"),
            ("portfolio",            "Active signals with live P&L"),
            ("reports",              "Monthly performance reports"),
            ("notify",               "Notification preferences"),
            ("filter",               "Custom signal filters"),
            ("feedback",             "Signal feedback"),
            ("apikey",               "API key"),
            ("mystats",              "MT5 execution stats"),
            ("setlot",               "Fixed lot size for MT5"),
            ("setrisk",              "Max risk % per trade"),
            ("mt5_link",             "Link MT5 account"),
            ("mt5_status",           "MT5 connection status"),
            ("connect_broker",       "Connect broker account"),
            ("referral",             "Referral code & stats"),
            ("cancel",               "Cancel auto-renewal"),
            # ─ VIP-exclusive ──────────────────────────────────────────
            ("elite",                "VIP-only high-conviction signals"),
            ("early",                "Early-access market move alerts"),
            ("report",               "Detailed monthly performance report"),
        ],
        "footer": (
            "💎 VIP Features:\n"
            "• Highest-confidence signals only (≥85 score)\n"
            "• ML probability scores on every signal\n"
            "• Early-access alerts before premium delivery\n"
            "• MT5 auto-execution (unlimited, risk-based sizing)\n"
            "• Monthly performance reports\n"
            "• Priority notification delivery\n"
            "• NO-TRADE zone alerts (high-impact news)\n\n"
            "✨ Elite trading intelligence."
        ),
    },
    "OWNER": {
        "title": "👑 OWNER / ADMIN Commands",
        "commands": [
            # ─ Free ───────────────────────────────────────────────────────────────
            ("start",                  "Start / re-register"),
            ("help",                   "This help menu"),
            ("status",                 "Subscription status"),
            ("upgrade",                "Plan details"),
            ("pricing",                "Pricing"),
            ("tiers",                  "Tier comparison"),
            ("signals",                "All signals"),
            ("signal",                 "Lookup signal (full debug)"),
            ("outcome",                "Check outcome"),
            ("liveprice",              "Live price"),
            ("market",                 "Market overview"),
            ("invite",                 "Referral system"),
            ("referral_leaderboard",   "Leaderboard"),
            ("referral_rewards",       "Rewards"),
            ("recap",                  "Weekly recap"),
            ("about",                  "About"),
            ("faq",                    "FAQ"),
            ("disclaimer",             "Disclaimer"),
            ("policy",                 "Policy"),
            ("support",                "Support"),
            ("myid",                   "Your ID and tier"),
            ("language",               "Language"),
            # ─ Premium ───────────────────────────────────────────────────────────
            ("performance",            "Performance analytics"),
            ("stats",                  "Win rate, net R"),
            ("history",                "Signal history"),
            ("risk",                   "Risk guidance"),
            ("alerts",                 "Alert settings"),
            ("analyze",                "AI analysis"),
            ("dashboard",              "Analytics dashboard"),
            ("portfolio",              "Active signals with P&L"),
            ("reports",                "Report opt-in"),
            ("notify",                 "Notification preferences"),
            ("filter",                 "Signal filters"),
            ("feedback",               "Signal feedback"),
            ("apikey",                 "API key"),
            ("mystats",                "MT5 execution stats"),
            ("setlot",                 "Fixed lot size"),
            ("setrisk",                "Max risk %"),
            ("mt5_link",               "Link MT5 account"),
            ("mt5_status",             "MT5 status"),
            ("connect_broker",         "Connect broker"),
            ("referral",               "Referral code"),
            ("cancel",                 "Cancel auto-renewal"),
            # ─ VIP ─────────────────────────────────────────────────────────────────
            ("elite",                  "Elite signals"),
            ("early",                  "Early alerts"),
            ("report",                 "Monthly report"),
            # ─ ADMIN ─────────────────────────────────────────────────────────────
            ("admin",                  "Platform dashboard (users, VIP, signals)"),
            ("admin_broadcast",        "DM blast to all users"),
            ("force_signal",           "Generate and send a fresh signal now"),
            ("force_market_scan",      "Run ML market scan now"),
            # ─ OWNER-only ───────────────────────────────────────────────────────
            ("blast_terms",            "Send terms gate to all unconfirmed users"),
            ("dev_pause",              "Pause engine (kill-switch ON)"),
            ("dev_resume",             "Resume engine (kill-switch OFF)"),
            ("dev_force_signal",       "Generate and send a fresh signal now"),
            ("dev_invalidate",         "Archive/invalidate a signal"),
            ("owner_users",            "User statistics"),
            ("owner_revenue",          "Revenue analytics"),
            ("version",                "System version / deployment info"),
            ("correct_signal",         "Correct/modify a signal outcome"),
            ("admin_top_assets",       "Top performing assets"),
            ("admin_top_strategies",   "Top performing strategies"),
            ("admin_user_engagement",  "User engagement analytics"),
            ("qa_report",              "QA report by tier and asset class"),
            ("broadcast",              "Owner broadcast (via owner_commands)"),
            ("assets",                 "Manage pinned asset universe"),
            ("selfcheck",              "System self-check"),
            ("provider_status",        "Data provider status"),
        ],
        "footer": (
            "👑 Full System Access:\n"
            "• All user commands\n"
            "• Real-time admin dashboard\n"
            "• Broadcast & terms gate management\n"
            "• Engine control (pause/resume/force)\n"
            "• User & revenue analytics\n"
            "• Signal correction & validation\n\n"
            "⚙️ /unlock is intentionally hidden — only you know it exists."
        ),
    },
}


COMMAND_DESCRIPTIONS = {
    "qa_report": "QA report by tier and asset class",
}


def _normalize_command_name(command: str) -> str:
    return str(command or "").strip().lstrip("/").lower()


def _help_tier_bucket(required_tier: str) -> str:
    tier = str(required_tier or "FREE").strip().upper()
    if tier in {"ADMIN", "OWNER"}:
        return "OWNER"
    if tier in {"VIP", "PREMIUM", "FREE"}:
        return tier
    return "FREE"


def sync_command_help() -> None:
    """Ensure COMMAND_HELP includes all commands from COMMAND_TIERS."""
    desc_lookup: dict[str, str] = {}
    for _tier, _info in (COMMAND_HELP or {}).items():
        for _cmd, _desc in (_info.get("commands") or []):
            cmd_key = _normalize_command_name(_cmd)
            if cmd_key and cmd_key not in desc_lookup:
                desc_lookup[cmd_key] = str(_desc or "").strip()
    for k, v in (COMMAND_DESCRIPTIONS or {}).items():
        if k:
            desc_lookup[_normalize_command_name(k)] = str(v or "").strip()

    existing: dict[str, set[str]] = {}
    for tier_name, info in (COMMAND_HELP or {}).items():
        existing[tier_name] = {
            _normalize_command_name(cmd)
            for cmd, _desc in (info.get("commands") or [])
            if _normalize_command_name(cmd)
        }

    for cmd, required_tier in (COMMAND_TIERS or {}).items():
        cmd_key = _normalize_command_name(cmd)
        if not cmd_key:
            continue
        bucket = _help_tier_bucket(required_tier)
        if cmd_key in existing.get(bucket, set()):
            continue
        desc = desc_lookup.get(cmd_key) or "Command"
        COMMAND_HELP.setdefault(bucket, {}).setdefault("commands", []).append((cmd_key, desc))
        existing.setdefault(bucket, set()).add(cmd_key)


def get_accessible_commands(tier: str) -> list[tuple[str, str]]:
    """Return list of (command, description) for a given tier."""
    sync_command_help()
    tier = str(tier or "FREE").strip().upper()
    
    # Admin and Owner get all commands
    if tier in ("ADMIN", "OWNER"):
        tier = "OWNER"
    
    # Unknown tiers default to FREE
    if tier not in ("FREE", "PREMIUM", "VIP", "OWNER"):
        tier = "FREE"
    
    return COMMAND_HELP.get(tier, {}).get("commands", [])


def get_help_message(tier: str) -> str:
    """Build dynamic help message based on user's current tier. Returns HTML-formatted text."""
    sync_command_help()
    tier = str(tier or "FREE").strip().upper()
    
    # Admin and Owner get OWNER help
    if tier in ("ADMIN", "OWNER"):
        tier = "OWNER"
    
    # Unknown tiers default to FREE
    if tier not in ("FREE", "PREMIUM", "VIP", "OWNER"):
        tier = "FREE"

    dashboard_url = os.getenv("DASHBOARD_URL")
    cache_key = f"help_menu:{tier}:{'1' if dashboard_url else '0'}"
    try:
        cached = state.cache_get_sync(cache_key)
        if cached:
            return str(cached)
    except Exception:
        pass
    
    help_data = COMMAND_HELP.get(tier, COMMAND_HELP["FREE"])
    title = help_data.get("title", "🤖 SignalRankAI Commands")
    commands = help_data.get("commands", [])
    footer = help_data.get("footer", "")

    def _he(text: str) -> str:
        """HTML-safe escape: only & < > need replacing in Telegram HTML mode."""
        return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    # Build message
    lines = [f"<b>{_he(title)}</b>", ""]
    for cmd, desc in commands:
        lines.append(f"/{_he(cmd)} – {_he(desc)}")

    # --- Advanced Features Section ---
    adv_cmds = [
        ("dashboard", "• /dashboard – Open your analytics dashboard"),
        ("apikey", "• /apikey – Get your API key for programmatic access"),
        ("filter", "• /filter – Set custom signal filters (min_score, rr, regime)"),
        ("reports", "• /reports – Opt-in/out of daily/weekly performance reports"),
        ("notify", "• /notify – Customize which assets, timeframes, or strategies you receive"),
        ("language", "• /language – Change your notification language"),
        ("referral_leaderboard", "• /referral_leaderboard – See top referrers"),
        ("referral_rewards", "• /referral_rewards – View your referral rewards"),
        ("feedback", "• /feedback – Rate a signal or report an issue"),
        ("analyze", "• /analyze – AI analysis for a specific pair"),
    ]
    adv_usage = [
        ("apikey", "- /apikey regenerate – Reset your API key"),
        ("filter", "- /filter min_score 60 – Set minimum score"),
        ("filter", "- /filter rr 2.0 – Set minimum risk/reward"),
        ("filter", "- /filter regime TRENDING – Set regime filter"),
        ("reports", "- /reports on|off – Subscribe/unsubscribe to scheduled reports"),
        ("notify", "- /notify assets BTCUSDT,ETHUSDT – Set asset notifications"),
        ("notify", "- /notify timeframes 1h,4h – Set timeframes"),
        ("notify", "- /notify strategies momentum,trend – Set strategies"),
        ("notify", "- /notify clear – Reset notification preferences"),
        ("language", "- /language en|es|fr – Set your language"),
        ("feedback", "- /feedback &lt;signal_ref&gt; &lt;rating|issue&gt; [comment] – Submit feedback"),
        ("analyze", "- /analyze BTCUSDT 1h – Run AI analysis"),
    ]

    visible_adv = [line for cmd, line in adv_cmds if check_command_access(cmd, tier)[0] and (cmd != "dashboard" or dashboard_url)]
    visible_usage = [line for cmd, line in adv_usage if check_command_access(cmd, tier)[0]]

    if visible_adv:
        lines.append("")
        lines.append("<b>Advanced Features &amp; Usage</b>")
        lines.append("")
        lines.extend([_he(line) for line in visible_adv])
        if visible_usage:
            lines.append("")
            lines.append("<b>How to use advanced features:</b>")
            # usage lines already have HTML entities hand-coded above; append as-is
            lines.extend(visible_usage)

    if footer:
        lines.extend(["", _he(footer)])

    # Add disclaimers
    disclaimers = [
        "",
        "📌 Notes",
        "• Signals are real-time from live market data",
        "• Supports crypto and FX",
        "• Signal corrections: automatic + manual fixes",
        "• No duplicate signals per user",
        "• Tier features reflect your current subscription",
        "",
        "⚠️ Educational only. Not financial advice. Trading involves risk.",
    ]
    lines.extend([_he(line) if line else "" for line in disclaimers])

    rendered = "\n".join(lines)
    try:
        ttl = max(30, int((os.getenv("HELP_MENU_CACHE_TTL_SECONDS") or "300").strip()))
        state.cache_set_sync(cache_key, rendered, ex=ttl)
    except Exception:
        pass
    return rendered


def check_command_access(command: str, user_tier: str) -> tuple[bool, str]:
    """Check if user tier can access a command.
    
    Returns (can_access: bool, reason: str).
    If False, reason explains why they can't access it.
    """
    command = str(command or "").strip().lower()
    user_tier = str(user_tier or "FREE").strip().upper()
    
    # Admin and Owner can access everything
    if user_tier in ("ADMIN", "OWNER"):
        return True, ""
    
    # Default unknown tiers to FREE
    if user_tier not in ("FREE", "PREMIUM", "VIP"):
        user_tier = "FREE"
    
    # Get required tier for command
    required_tier = COMMAND_TIERS.get(command, "FREE")
    
    # Check tier rank
    user_rank = TIER_RANKS.get(user_tier, 0)
    required_rank = TIER_RANKS.get(required_tier, 0)
    
    if user_rank >= required_rank:
        return True, ""
    
    # Access denied
    reason = (
        f"🔒 Command not available on {user_tier} tier.\n"
        f"This command requires {required_tier} tier or higher.\n"
        "Use /upgrade to subscribe."
    )
    return False, reason


def tier_rank(tier: str) -> int:
    """Get numeric tier rank (0 = FREE, 3 = OWNER)."""
    tier = str(tier or "FREE").strip().upper()
    return TIER_RANKS.get(tier, 0)


__all__ = [
    "COMMAND_TIERS",
    "TIER_RANKS",
    "COMMAND_HELP",
    "COMMAND_DESCRIPTIONS",
    "sync_command_help",
    "get_accessible_commands",
    "get_help_message",
    "check_command_access",
    "tier_rank",
]

sync_command_help()
