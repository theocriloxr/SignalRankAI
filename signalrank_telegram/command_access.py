"""Tier-based command access control and help menu system.

Maps commands to required tier and builds dynamic help based on user's current tier.
Handles tier changes (demotion) by checking live tier on each access.
"""

import os

# Map of command -> minimum tier required
COMMAND_TIERS = {
    # PUBLIC / FREE COMMANDS (accessible to everyone)
    "start": "FREE",
    "help": "FREE",
    "about": "FREE",
    "faq": "FREE",
    "disclaimer": "FREE",
    "pricing": "FREE",
    "upgrade": "FREE",
    "signals": "FREE",
    "signal": "FREE",
    "outcome": "FREE",
    "invite": "FREE",
    "policy": "FREE",
    "refunds": "FREE",
    "recap": "FREE",
    "buy_extra_signals": "FREE",
    "unlock": "FREE",  # Needed for admins to regain access via bypass key
    "language": "FREE",
    "referral_leaderboard": "FREE",
    "referral_rewards": "FREE",
    "support": "FREE",
    "status": "FREE",
    "liveprice": "FREE",  # NEW: Live price for any asset
    "market": "FREE",  # NEW: Market overview
    
    # PREMIUM COMMANDS
    "performance": "PREMIUM",
    "stats": "PREMIUM",
    "history": "PREMIUM",
    "risk": "PREMIUM",
    "alerts": "PREMIUM",
    "analyze": "PREMIUM",
    "dashboard": "PREMIUM",
    "feedback": "PREMIUM",
    "apikey": "PREMIUM",
    "filter": "PREMIUM",
    "reports": "PREMIUM",
    "notify": "PREMIUM",
    "portfolio": "PREMIUM",  # NEW: Show active signals with P&L
    
    # VIP COMMANDS
    "elite": "VIP",
    "early": "VIP",
    "report": "VIP",
    
    # OWNER/ADMIN COMMANDS (for internal use)
    "dev_pause": "OWNER",
    "dev_resume": "OWNER",
    "dev_force_signal": "OWNER",
    "dev_invalidate": "OWNER",
    "owner_users": "OWNER",
    "owner_revenue": "OWNER",
    "version": "OWNER",
    "correct_signal": "OWNER",
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
            ("start", "Start the bot"),
            ("help", "Show this help menu"),
            ("about", "About SignalRankAI"),
            ("faq", "Frequently asked questions"),
            ("disclaimer", "Risk disclaimer"),
            ("pricing", "View pricing plans"),
            ("upgrade", "Subscribe to Premium/VIP"),
            ("status", "Check subscription status"),
            ("signals", "View signals sent to you"),
            ("signal", "Lookup a specific signal (reference)"),
            ("outcome", "Check outcome of a signal"),
            ("invite", "Get your referral link (earn rewards)"),
            ("policy", "Subscription & refund policy"),
            ("recap", "Weekly performance recap"),
            ("support", "Contact support"),
            ("liveprice", "Get real-time price for any asset"),
            ("market", "Market overview & major assets"),
            # ("buy_extra_signals", "Buy 1-5 extra daily signals (₦300 each)"),
        ],
        "footer": (
            "📌 Free Features:\n"
            "• 1–3 signals/day (delayed)\n"
            "• Outcome notifications (basic)\n"
            "• Daily summary\n"
            "• Referral rewards\n"
            "• Live prices & market overview\n\n"
            "Markets: Crypto (spot) + major FX pairs\n"
            "Features: AI analysis, risk plans, TP/SL alerts\n\n"
            "💡 Tip: Upgrade to PREMIUM for real-time signals and full details."
        ),
    },
    "PREMIUM": {
        "title": "🟡 PREMIUM Tier Commands",
        "commands": [
            ("start", "Start the bot"),
            ("help", "Show this help menu"),
            ("about", "About SignalRankAI"),
            ("faq", "Frequently asked questions"),
            ("disclaimer", "Risk disclaimer"),
            ("pricing", "View pricing plans"),
            ("upgrade", "Upgrade to VIP"),
            ("signals", "View all your active signals"),
            ("signal", "Lookup a specific signal (full details)"),
            ("outcome", "Check full outcome of a signal"),
            ("invite", "Get your referral link (earn +7 days Premium)"),
            ("policy", "Subscription & refund policy"),
            ("recap", "Weekly performance recap"),
            ("performance", "Full performance stats (30 days)"),
            ("stats", "Quick stats summary"),
            ("history", "Recent signal history"),
            ("risk", "Risk management guidance"),
            ("alerts", "TP/SL alerts + quiet hours settings"),
            ("analyze", "AI analysis for a specific pair"),
            ("reports", "Daily/weekly report opt-in"),
            ("notify", "Notification preferences"),
            ("apikey", "API key for signals"),
            ("filter", "Custom signal filters"),
            ("support", "Contact support"),
            ("liveprice", "Get real-time price for any asset"),
            ("portfolio", "View all active signals with P&L"),
            ("market", "Market overview & major assets"),
            # ("buy_extra_signals", "Buy extra daily signals (if available)"),
        ],
        "footer": (
            "🟡 Premium Features:\n"
            "• Real-time signals (5m–24h)\n"
            "• Exact Entry, SL, TP levels\n"
            "• Confidence scores\n"
            "• TP/SL hit notifications\n"
            "• Daily & weekly stats\n"
            "• Risk management guidance\n"
            "• Portfolio tracking with live P&L\n\n"
            "Markets: Crypto (spot) + major FX pairs\n"
            "Features: AI analysis, risk plans, TP/SL alerts\n\n"
            "💡 Tip: Upgrade to VIP for elite signals."
        ),
    },
    "VIP": {
        "title": "🔴 VIP Tier Commands",
        "commands": [
            ("start", "Start the bot"),
            ("help", "Show this help menu"),
            ("about", "About SignalRankAI"),
            ("faq", "Frequently asked questions"),
            ("disclaimer", "Risk disclaimer"),
            ("pricing", "View pricing plans"),
            ("signals", "View your elite signals"),
            ("signal", "Lookup a specific signal (full analysis)"),
            ("outcome", "Check full outcome with R-multiples"),
            ("invite", "Get your referral link (earn rewards)"),
            ("policy", "Subscription & refund policy"),
            ("recap", "Weekly performance recap"),
            ("performance", "Full performance stats (unlimited)"),
            ("stats", "Detailed stats summary"),
            ("history", "Complete signal history"),
            ("risk", "Advanced risk management"),
            ("analyze", "AI analysis for a specific pair"),
            ("alerts", "TP/SL alerts + granular settings"),
            ("elite", "VIP-only high-conviction signals"),
            ("early", "Early access to market moves"),
            ("report", "Detailed monthly performance report"),
            ("analyze", "AI analysis for a specific pair"),
            ("support", "Contact support"),
        ],
        "footer": (
            "🔴 VIP Features:\n"
            "• Highest confidence signals only (≥85)\n"
            "• Reduced frequency (quality > quantity)\n"
            "• Early alerts\n"
            "• Priority notifications\n"
            "• Monthly performance reports\n"
            "• Advanced risk tools\n"
            "• NO-TRADE zone alerts\n\n"
            "✨ Elite trading intelligence."
        ),
    },
    "OWNER": {
        "title": "👑 OWNER/ADMIN Commands",
        "commands": [
            ("help", "Show this help menu"),
            # All public commands
            ("start", "Start the bot"),
            ("about", "About SignalRankAI"),
            ("faq", "Frequently asked questions"),
            ("disclaimer", "Risk disclaimer"),
            ("pricing", "View pricing"),
            ("signals", "View all signals"),
            ("signal", "Lookup signal (full debug info)"),
            ("outcome", "Check outcome"),
            ("invite", "Referral system"),
            ("policy", "Policy info"),
            ("recap", "Performance recap"),
            # Premium commands
            ("performance", "Full performance analytics"),
            ("stats", "Stats summary"),
            ("history", "Signal history"),
            ("risk", "Risk guidance"),
            ("alerts", "Alert management"),
            # VIP commands
            ("elite", "Elite signals"),
            ("early", "Early alerts"),
            ("report", "Performance reports"),
            # Admin commands
            ("unlock", "Temporary owner bypass (give user time-limited owner tier)"),
            ("dev_pause", "Pause engine"),
            ("dev_resume", "Resume engine"),
            ("dev_force_signal", "Force a test signal"),
            ("dev_invalidate", "Invalidate/delete a signal"),
            ("owner_users", "User statistics"),
            ("owner_revenue", "Revenue analytics"),
            ("version", "System version/deployment info"),
            ("correct_signal", "Correct/modify a signal outcome"),
            ("analyze", "AI analysis for a specific pair"),
            ("support", "Contact support"),
        ],
        "footer": (
            "👑 Full System Access:\n"
            "• All commands available\n"
            "• Debug & analytics\n"
            "• System control (pause/resume)\n"
            "• User & revenue management\n"
            "• Signal correction & validation\n\n"
            "⚙️ Administrative mode."
        ),
    },
}


def get_accessible_commands(tier: str) -> list[tuple[str, str]]:
    """Return list of (command, description) for a given tier."""
    tier = str(tier or "FREE").strip().upper()
    
    # Admin and Owner get all commands
    if tier in ("ADMIN", "OWNER"):
        tier = "OWNER"
    
    # Unknown tiers default to FREE
    if tier not in ("FREE", "PREMIUM", "VIP", "OWNER"):
        tier = "FREE"
    
    return COMMAND_HELP.get(tier, {}).get("commands", [])


def get_help_message(tier: str) -> str:
    """Build dynamic help message based on user's current tier."""
    tier = str(tier or "FREE").strip().upper()
    
    # Admin and Owner get OWNER help
    if tier in ("ADMIN", "OWNER"):
        tier = "OWNER"
    
    # Unknown tiers default to FREE
    if tier not in ("FREE", "PREMIUM", "VIP", "OWNER"):
        tier = "FREE"
    
    help_data = COMMAND_HELP.get(tier, COMMAND_HELP["FREE"])
    title = help_data.get("title", "🤖 SignalRankAI Commands")
    commands = help_data.get("commands", [])
    footer = help_data.get("footer", "")
    
    def escape_md(text):
        # Telegram Markdown V2 escaping
        chars = r'_[]()~`>#+-=|{}.!'
        for c in chars:
            text = text.replace(c, f'\\{c}')
        return text

    # Build message
    lines = [escape_md(title), ""]
    for cmd, desc in commands:
        lines.append(f"/{escape_md(cmd)} – {escape_md(desc)}")

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
        ("feedback", "- /feedback <signal_ref> <rating|issue> [comment] – Submit feedback"),
        ("analyze", "- /analyze BTCUSDT 1h – Run AI analysis"),
    ]

    dashboard_url = os.getenv("DASHBOARD_URL")
    visible_adv = [line for cmd, line in adv_cmds if check_command_access(cmd, tier)[0] and (cmd != "dashboard" or dashboard_url)]
    visible_usage = [line for cmd, line in adv_usage if check_command_access(cmd, tier)[0]]

    if visible_adv:
        lines.append("")
        lines.append(escape_md("*Advanced Features & Usage*"))
        lines.append("")
        lines.extend([escape_md(line) for line in visible_adv])
        if visible_usage:
            lines.append("")
            lines.append(escape_md("*How to use advanced features:*"))
            lines.extend([escape_md(line) for line in visible_usage])

    if footer:
        lines.extend(["", escape_md(footer)])

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
    lines.extend([escape_md(line) if line else "" for line in disclaimers])

    return "\n".join(lines)


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
    "get_accessible_commands",
    "get_help_message",
    "check_command_access",
    "tier_rank",
]
