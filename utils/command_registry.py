"""
Command Registry - Single Source of Truth for Telegram Commands

This module provides a centralized command registry that generates:
- /help text
- Menu layouts
- Permission checks
- Handler mappings

Usage:
    from utils.command_registry import (
        get_command_definition,
        generate_help_text,
        get_commands_for_tier,
        is_command_allowed,
    )

Command Structure:
    {
        "name": "start",
        "description": "Welcome message and account setup",
        "handler": "handle_start",
        "tier": "free",  # Minimum tier: free, premium, vip, owner, admin
        "aliases": ["/start", "/s"],
        "category": "core",  # core, signal, mt5, portfolio, admin
        "hidden": False,
    }
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# Command tier ranks (higher = more access)
TIER_RANKS = {
    "free": 0,
    "premium": 1,
    "vip": 2,
    "owner": 3,
    "admin": 4,
}

# Tier display names
TIER_NAMES = {
    "free": "Free",
    "premium": "Premium",
    "vip": "VIP",
    "owner": "Owner",
    "admin": "Admin",
}


@dataclass
class CommandDefinition:
    """Command definition with metadata."""
    name: str
    description: str
    handler: str
    tier: str = "free"
    aliases: List[str] = field(default_factory=list)
    category: str = "core"
    hidden: bool = False
    requires_mt5: bool = False
    requires_preferences: bool = False


# Core commands
CORE_COMMANDS = {
    "start": CommandDefinition(
        name="start",
        description="Welcome message and account setup",
        handler="handle_start",
        tier="free",
        aliases=["/start", "/s"],
        category="core",
    ),
    "help": CommandDefinition(
        name="help",
        description="Show available commands and usage guide",
        handler="handle_help",
        tier="free",
        aliases=["/help", "/h", "/?"],
        category="core",
    ),
    "settings": CommandDefinition(
        name="settings",
        description="Configure your signal preferences and alerts",
        handler="handle_settings",
        tier="free",
        aliases=["/settings", "/prefs"],
        category="core",
        requires_preferences=True,
    ),
    "status": CommandDefinition(
        name="status",
        description="Show bot status and active signals count",
        handler="handle_status",
        tier="free",
        aliases=["/status", "/health"],
        category="core",
    ),
}

# Signal commands
SIGNAL_COMMANDS = {
    "signal": CommandDefinition(
        name="signal",
        description="Get current active trading signals",
        handler="handle_signal",
        tier="free",
        aliases=["/signal", "/sig", "/sigs"],
        category="signal",
    ),
    "signal_history": CommandDefinition(
        name="signal_history",
        description="View past signals and their outcomes",
        handler="handle_signal_history",
        tier="free",
        aliases=["/history", "/sh"],
        category="signal",
    ),
    "subscribe": CommandDefinition(
        name="subscribe",
        description="Subscribe to signals for specific assets",
        handler="handle_subscribe",
        tier="free",
        aliases=["/subscribe", "/sub"],
        category="signal",
    ),
    "alert": CommandDefinition(
        name="alert",
        description="Set price alerts for any asset",
        handler="handle_alert",
        tier="free",
        aliases=["/alert", "/pricealert"],
        category="signal",
    ),
    "signal_premium": CommandDefinition(
        name="signal_premium",
        description="Get premium signals with higher win rates",
        handler="handle_signal_premium",
        tier="premium",
        aliases=["/premium", "/prem"],
        category="signal",
    ),
    "signal_vip": CommandDefinition(
        name="signal_vip",
        description="Get VIP signals with exclusive strategies",
        handler="handle_signal_vip",
        tier="vip",
        aliases=["/vip", "/elite"],
        category="signal",
    ),
}

# MT5 commands
MT5_COMMANDS = {
    "mt5": CommandDefinition(
        name="mt5",
        description="Link or manage your MT5 account",
        handler="handle_mt5",
        tier="free",
        aliases=["/mt5", "/metatrader"],
        category="mt5",
    ),
    "mt5_balance": CommandDefinition(
        name="mt5_balance",
        description="Check your MT5 account balance",
        handler="handle_mt5_balance",
        tier="premium",
        aliases=["/balance", "/bal"],
        category="mt5",
        requires_mt5=True,
    ),
    "mt5_positions": CommandDefinition(
        name="mt5_positions",
        description="View open positions",
        handler="handle_mt5_positions",
        tier="premium",
        aliases=["/positions", "/pos"],
        category="mt5",
        requires_mt5=True,
    ),
    "mt5_execute": CommandDefinition(
        name="mt5_execute",
        description="Execute signal directly on MT5",
        handler="handle_mt5_execute",
        tier="vip",
        aliases=["/execute", "/trade"],
        category="mt5",
        requires_mt5=True,
    ),
    "mt5_settings": CommandDefinition(
        name="mt5_settings",
        description="Configure MT5 auto-trading settings",
        handler="handle_mt5_settings",
        tier="vip",
        aliases=["/mt5settings"],
        category="mt5",
        requires_mt5=True,
    ),
}

# Portfolio commands
PORTFOLIO_COMMANDS = {
    "portfolio": CommandDefinition(
        name="portfolio",
        description="View your portfolio and P&L",
        handler="handle_portfolio",
        tier="free",
        aliases=["/portfolio", "/pf"],
        category="portfolio",
    ),
    "risk": CommandDefinition(
        name="risk",
        description="View risk metrics and exposure",
        handler="handle_risk",
        tier="free",
        aliases=["/risk", "/exposure"],
        category="portfolio",
    ),
    "performance": CommandDefinition(
        name="performance",
        description="View your trading performance stats",
        handler="handle_performance",
        tier="free",
        aliases=["/performance", "/perf", "/stats"],
        category="portfolio",
    ),
    "journal": CommandDefinition(
        name="journal",
        description="View your trade journal and lessons",
        handler="handle_journal",
        tier="premium",
        aliases=["/journal", "/journal"],
        category="portfolio",
    ),
    "coach": CommandDefinition(
        name="coach",
        description="Get AI coaching on your trades",
        handler="handle_coach",
        tier="premium",
        aliases=["/coach", "/ai"],
        category="portfolio",
    ),
    "leaderboard": CommandDefinition(
        name="leaderboard",
        description="View top traders",
        handler="handle_leaderboard",
        tier="free",
        aliases=["/leaderboard", "/leaders"],
        category="portfolio",
    ),
}

# Referral commands
REFERRAL_COMMANDS = {
    "referral": CommandDefinition(
        name="referral",
        description="Get your referral link and stats",
        handler="handle_referral",
        tier="free",
        aliases=["/referral", "/ref", "/invite"],
        category="core",
    ),
    "rewards": CommandDefinition(
        name="rewards",
        description="View your referral rewards",
        handler="handle_rewards",
        tier="free",
        aliases=["/rewards"],
        category="core",
    ),
}

# Upgrade commands
UPGRADE_COMMANDS = {
    "upgrade": CommandDefinition(
        name="upgrade",
        description="Upgrade to Premium for more signals",
        handler="handle_upgrade",
        tier="free",
        aliases=["/upgrade", "/premium", "/vip"],
        category="core",
    ),
    "check_sub": CommandDefinition(
        name="check_sub",
        description="Check subscription status",
        handler="handle_check_sub",
        tier="free",
        aliases=["/check_sub", "/substatus"],
        category="core",
    ),
    "cancel": CommandDefinition(
        name="cancel",
        description="Cancel subscription",
        handler="handle_cancel",
        tier="free",
        aliases=["/cancel"],
        category="core",
    ),
}

# Admin commands
ADMIN_COMMANDS = {
    "admin_broadcast": CommandDefinition(
        name="admin_broadcast",
        description="Broadcast message to all users",
        handler="handle_admin_broadcast",
        tier="admin",
        aliases=["/broadcast"],
        category="admin",
        hidden=True,
    ),
    "admin_stats": CommandDefinition(
        name="admin_stats",
        description="System statistics",
        handler="handle_admin_stats",
        tier="admin",
        aliases=["/admin_stats"],
        category="admin",
        hidden=True,
    ),
    "admin_users": CommandDefinition(
        name="admin_users",
        description="User management",
        handler="handle_admin_users",
        tier="admin",
        aliases=["/admin_users"],
        category="admin",
        hidden=True,
    ),
    "admin_kill": CommandDefinition(
        name="admin_kill",
        description="Emergency killswitch",
        handler="handle_admin_kill",
        tier="admin",
        aliases=["/kill"],
        category="admin",
        hidden=True,
    ),
    "owner_exec": CommandDefinition(
        name="owner_exec",
        description="Execute arbitrary code",
        handler="handle_owner_exec",
        tier="owner",
        aliases=["/exec"],
        category="admin",
        hidden=True,
    ),
}


# Combined registry
COMMAND_REGISTRY: Dict[str, CommandDefinition] = {
    **CORE_COMMANDS,
    **SIGNAL_COMMANDS,
    **MT5_COMMANDS,
    **PORTFOLIO_COMMANDS,
    **REFERRAL_COMMANDS,
    **UPGRADE_COMMANDS,
    **ADMIN_COMMANDS,
}


# Category groupings for menus
CATEGORY_GROUPS = {
    "core": CORE_COMMANDS,
    "signal": SIGNAL_COMMANDS,
    "mt5": MT5_COMMANDS,
    "portfolio": PORTFOLIO_COMMANDS,
    "referral": REFERRAL_COMMANDS,
    "upgrade": UPGRADE_COMMANDS,
    "admin": ADMIN_COMMANDS,
}


def get_command_definition(command: str) -> Optional[CommandDefinition]:
    """Get command definition by name or alias."""
    cmd_lower = command.lower().strip().lstrip("/")
    
    # Check direct name in registry
    if cmd_lower in COMMAND_REGISTRY:
        return COMMAND_REGISTRY[cmd_lower]
    
    # Check aliases
    for defn in COMMAND_REGISTRY.values():
        if cmd_lower in defn.aliases:
            return defn
    
    return None


def tier_rank(tier: str) -> int:
    """Get numeric rank for a tier."""
    return TIER_RANKS.get(tier.lower(), 0)


def is_command_allowed(command: str, user_tier: str) -> bool:
    """Check if user tier can access command."""
    defn = get_command_definition(command)
    if not defn:
        return False
    
    return tier_rank(user_tier) >= tier_rank(defn.tier)


def get_commands_for_tier(
    user_tier: str,
    include_hidden: bool = False,
    category: Optional[str] = None,
) -> List[CommandDefinition]:
    """
    Get all commands available to a user tier.
    
    Args:
        user_tier: User's tier (free, premium, vip, owner, admin)
        include_hidden: Include hidden admin commands
        category: Filter by category
        
    Returns:
        List of command definitions
    """
    user_rank = tier_rank(user_tier)
    results = []
    
    commands = CATEGORY_GROUPS.get(category, COMMAND_REGISTRY) if category else COMMAND_REGISTRY
    
    for name, defn in commands.items():
        # Skip hidden unless explicitly requested
        if defn.hidden and not include_hidden:
            continue
        
        # Check tier access
        if user_rank >= tier_rank(defn.tier):
            results.append(defn)
    
    return results


def generate_help_text(
    user_tier: str,
    include_hidden: bool = False,
    format: str = "text",  # "text", "markdown", "html"
) -> str:
    """
    Generate help text for user tier.
    
    Args:
        user_tier: User's tier
        include_hidden: Include hidden commands
        format: Output format (text, markdown, html)
        
    Returns:
        Formatted help string
    """
    lines = []
    user_rank = tier_rank(user_tier)
    tier_name = TIER_NAMES.get(user_tier, "Free")
    
    # Header
    lines.append(f"📡 <b>SignalRankAI Commands</b>")
    lines.append(f"━━━━━━━━━━━━━━━━")
    lines.append(f"📊 Your Tier: <b>{tier_name}</b>")
    lines.append("")
    
    # Group by category
    for category, commands in CATEGORY_GROUPS.items():
        category_lines = []
        
        for name, defn in commands.items():
            # Skip hidden unless requested
            if defn.hidden and not include_hidden:
                continue
            
            # Check tier access
            if user_rank < tier_rank(defn.tier):
                continue
            
            # Format aliases
            alias_text = ""
            if defn.aliases:
                aliases_str = ", ".join(a for a in defn.aliases if a != f"/{name}")
                if aliases_str:
                    alias_text = f" ({aliases_str})"
            
            # Build command line
            cmd_line = f"<code>/{name}</code>{alias_text} - {defn.description}"
            category_lines.append(cmd_line)
        
        if category_lines:
            # Category header
            cat_emoji = {
                "core": "⚙️",
                "signal": "📡",
                "mt5": "📈",
                "portfolio": "💼",
                "referral": "👥",
                "upgrade": "⬆️",
                "admin": "🔧",
            }.get(category, "📋")
            
            lines.append(f"{cat_emoji} <b>{category.upper()}</b>")
            lines.extend(category_lines)
            lines.append("")
    
    # Footer
    lines.append("━━━━━━━━━━━━━━━━")
    lines.append("<i>Use /help [command] for detailed help.</i>")
    lines.append("<i>Upgrade with /upgrade for more features.</i>")
    
    return "\n".join(lines)


def generate_menu_keyboard(
    user_tier: str,
    include_hidden: bool = False,
) -> List[List[Dict[str, str]]]:
    """
    Generate inline keyboard menu for user tier.
    
    Returns:
        List of button rows
    """
    from telegram import InlineKeyboardButton
    
    buttons = []
    user_rank = tier_rank(user_tier)
    
    # Main menu buttons
    main_buttons = [
        ("📡 Signals", "/signal"),
        ("📊 Portfolio", "/portfolio"),
        ("💼 MT5", "/mt5"),
        ("⚙️ Settings", "/settings"),
    ]
    
    for label, cmd in main_buttons:
        defn = get_command_definition(cmd)
        if defn and user_rank >= tier_rank(defn.tier):
            buttons.append([InlineKeyboardButton(label, callback_data=cmd)])
    
    # Premium menu (if eligible)
    if user_rank >= tier_rank("premium"):
        premium_buttons = [
            ("📈 Premium Signals", "/signal_premium"),
            ("🏆 Leaderboard", "/leaderboard"),
            ("💰 Upgrade", "/upgrade"),
        ]
        
        for label, cmd in premium_buttons:
            defn = get_command_definition(cmd)
            if defn and user_rank >= tier_rank(defn.tier):
                buttons.append([InlineKeyboardButton(label, callback_data=cmd)])
    
    # Back to main button
    buttons.append([InlineKeyboardButton("🔙 Back to Main", callback_data="menu_main")])
    
    return buttons


def get_handler_for_command(command: str) -> Optional[str]:
    """Get handler function name for a command."""
    defn = get_command_definition(command)
    return defn.handler if defn else None


__all__ = [
    "CommandDefinition",
    "COMMAND_REGISTRY",
    "TIER_RANKS",
    "TIER_NAMES",
    "get_command_definition",
    "tier_rank",
    "is_command_allowed",
    "get_commands_for_tier",
    "generate_help_text",
    "generate_menu_keyboard",
    "get_handler_for_command",
]
