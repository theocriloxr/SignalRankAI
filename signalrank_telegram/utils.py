import os
import logging
from typing import Optional, Dict, Any, Tuple
from functools import lru_cache
from datetime import datetime, timedelta
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from core.redis_state import state
from core.tier_constants import TIER_SCORE_THRESHOLDS
from core.command_limits import PUBLIC_COMMAND_RATE_LIMIT, REQUIRE_TIER_RATE_LIMIT
from config import ADMIN_IDS, OWNER_IDS, config

logger = logging.getLogger(__name__)

TIER_RANKS: Dict[str, int] = {
    "FREE": 0,
    "PREMIUM": 1,
    "VIP": 2,
    "ADMIN": 3,
    "OWNER": 3,
}

FREE_PROOF_FEED_LIMIT = 5

async def _public_guard(update) -> bool:
    """Rate limit + killswitch protection for public commands."""
    if not update.effective_user or not update.message:
        return True
    
    user_id: int = update.effective_user.id
    
    # Global kill-switch check
    try:
        if state.get_killswitch_sync().enabled:
            if update.message:
                await update.message.reply_text("🚨 Signals temporarily paused for maintenance.")
            return True
    except Exception:
        pass
    
    # Rate limit (30/min public, 20/min tiered)
    try:
        limit_key = f"public_cmd:{user_id}"
        if state.rate_limited_sync(
            user_id,
            limit=int(PUBLIC_COMMAND_RATE_LIMIT["limit"]),
            window_seconds=int(PUBLIC_COMMAND_RATE_LIMIT["window_seconds"]),
        ):
            if update.message:
                await update.message.reply_text("⏳ Rate limit hit. Wait 1 minute.")
            return True
    except Exception:
        pass
    
    return False

def _effective_tier(user_id: int) -> str:
    """Resolve user's effective tier (config → DB → FREE fallback)."""
    try:
        # Config override (OWNER/ADMIN)
        if user_id in OWNER_IDS:
            return "OWNER"
        if user_id in ADMIN_IDS:
            return "ADMIN"
        
        # DB tier (cached 1h)
        from signalrank_telegram.access import resolve_user_tier
        tier = resolve_user_tier(user_id)
        return str(tier or "FREE").upper()
    except Exception:
        return "FREE"

def tier_rank(tier: str) -> int:
    """Get numeric rank for tier comparison."""
    normalized = str(tier or "").upper().strip()
    return TIER_RANKS.get(normalized, 0)

def require_tier(min_tier: str):
    """Decorator: require minimum tier for command access."""
    rank_required = tier_rank(min_tier)
    
    def decorator(func):
        async def wrapper(update, context):
            if await _public_guard(update):
                return
            
            user_id = update.effective_user.id
            user_tier = _effective_tier(user_id)
            
            if tier_rank(user_tier) < rank_required:
                tier_display = user_tier.upper()
                await update.message.reply_text(
                    f"🔒 {tier_display} tier detected.\n"
                    f"Upgrade required for this command.\n\n"
                    f"Send /upgrade"
                )
                return
            
            return await func(update, context)
        return wrapper
    return decorator

def _build_dynamic_menu(user_id: int, tier: str) -> Optional[InlineKeyboardMarkup]:
    """Build tier-aware navigation menu."""
    try:
        rows = []
        
        # Core navigation (all tiers)
        rows.append([
            InlineKeyboardButton("📊 Signals", callback_data="nav_signals"),
            InlineKeyboardButton("📈 Performance", callback_data="nav_performance"),
        ])
        
        # Tier-specific rows
        if tier_rank(tier) < tier_rank("PREMIUM"):
            rows.append([
                InlineKeyboardButton("✅ Proof Feed", callback_data="nav_proof"),
                InlineKeyboardButton("💳 Upgrade", callback_data="nav_upgrade"),
            ])
        else:
            # PREMIUM+ gets execution controls
            rows.append([
                InlineKeyboardButton("⚙️ Execution", callback_data="nav_execution"),
                InlineKeyboardButton("🔗 MT5 Status", callback_data="mt5_status"),
            ])
        
        # Account/Support (all tiers)
        rows.append([
            InlineKeyboardButton("👤 Account", callback_data="nav_account"),
            InlineKeyboardButton("🆘 Support", callback_data="nav_support"),
        ])
        
        # Admin dashboard
        try:
            if user_id in ADMIN_IDS or user_id in OWNER_IDS:
                rows.append([
                    InlineKeyboardButton("🛡️ Admin", callback_data="admin_dashboard"),
                ])
        except Exception:
            pass
        
        return InlineKeyboardMarkup(rows)
    except Exception:
        return None

_TELEGRAM_CALLBACK_DATA_MAX_BYTES = 64


def _compact_signal_callback_id(signal_id: object) -> str:
    raw = str(signal_id or "").strip()
    return raw[:36] if raw else ""


def _signal_callback_data(prefix: str, signal_id: object, suffix: str = "") -> str:
    payload = _compact_signal_callback_id(signal_id)
    data = f"{prefix}{payload}{suffix}"
    while payload and len(data.encode("utf-8")) > _TELEGRAM_CALLBACK_DATA_MAX_BYTES:
        payload = payload[:-1]
        data = f"{prefix}{payload}{suffix}"
    return data


def _build_signal_action_keyboard(signal: Optional[Dict[str, Any]] = None) -> Optional[InlineKeyboardMarkup]:
    """Inline buttons for signals: Chart + Trade."""
    try:
        broker_prefix, asset = _chart_symbol_for_broker(signal)
        chart_symbol = asset.replace("/", "").replace(" ", "")
        chart_url = f"https://www.tradingview.com/chart/?symbol={broker_prefix}:{chart_symbol}"
        
        signal_id = _compact_signal_callback_id((signal or {}).get("signal_id"))
        
        rows = [[
            InlineKeyboardButton("📈 TradingView Chart", url=chart_url),
        ]]
        if signal_id:
            rows[0].append(InlineKeyboardButton("⚡ Execute", callback_data=_signal_callback_data("mt5_trade_", signal_id)))
        
        if signal_id:
            rows.append([
                InlineKeyboardButton("🔥 Taking Position", callback_data=_signal_callback_data("signal_reaction_", signal_id, "|taking_it")),
                InlineKeyboardButton("👀 Watching", callback_data=_signal_callback_data("signal_reaction_", signal_id, "|watching")),
            ])
            rows.append([
                InlineKeyboardButton("📈 Monitor", callback_data=_signal_callback_data("monitor_signal_", signal_id)),
                InlineKeyboardButton("🔍 Check Outcome", callback_data=_signal_callback_data("check_outcome_", signal_id)),
            ])
        
        return InlineKeyboardMarkup(rows)
    except Exception:
        return None

def _chart_symbol_for_broker(signal: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
    """Map asset → TradingView symbol + broker prefix."""
    import os
    asset = str((signal or {}).get("asset") or "").upper().strip()
    broker_hint = str((signal or {}).get("broker") or "").upper().strip()
    
    default_broker = str(os.getenv("TRADINGVIEW_BROKER", "BINANCE")).upper()
    fx_prefix = str(os.getenv("TRADINGVIEW_FX_PREFIX", "OANDA")).upper() or "OANDA"
    
    # Crypto
    if asset.endswith(("USDT", "USDC", "BUSD")):
        return broker_hint or default_broker, asset
    
    # FX pairs (6 chars)
    if len(asset) == 6 and asset.isalpha():
        return fx_prefix, asset
    
    # Commodities
    if asset in ("XAUUSD", "XAGUSD"):
        return "OANDA", asset
    
    return default_broker, asset

def sanitize_input(text: str, max_len: int = 1000) -> str:
    """Sanitize user input for HTML safety + length limits."""
    import html
    import re
    
    # Length limit
    text = text[:max_len]
    
    # HTML escape
    text = html.escape(str(text))
    
    # Block suspicious patterns
    blocked_patterns = [
        r'javascript:',
        r'on\w+\s*=',
        r'<script',
        r'<!--',
    ]
    for pattern in blocked_patterns:
        text = re.sub(pattern, '[REDACTED]', text, flags=re.IGNORECASE)
    
    return text

def _railway_env_hint(feature: str, missing_vars: list[str]) -> str:
    """Helpful Railway env var setup message."""
    vars_str = ", ".join(missing_vars)
    return (
        f"⚠️ {feature} requires environment variables:\n\n"
        f"Missing: <code>{vars_str}</code>\n\n"
        f"<b>Railway Setup:</b>\n"
        f"1. Railway dashboard → your service\n"
        f"2. Variables tab → Add Variables\n"
        f"3. Redeploy service\n\n"
        f"Need help? Reply with service name."
    )

def validate_lot_size(lot: float) -> bool:
    """Validate MT5 lot size (0.001-100)."""
    return 0.001 <= lot <= 100.0

def validate_risk_pct(pct: float) -> bool:
    """Validate risk percentage (0.1-5.0%)."""
    return 0.1 <= pct <= 5.0

__all__ = [
    '_public_guard',
    '_effective_tier', 
    'tier_rank',
    'require_tier',
    '_build_dynamic_menu',
    '_build_signal_action_keyboard',
    'sanitize_input',
    '_railway_env_hint',
    'validate_lot_size',
    'validate_risk_pct',
]
