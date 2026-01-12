def resend_unsent_signals_job():
    """Scheduled job: resend unsent signals to eligible users if outcome not reached, respecting tier logic."""
    try:
        from db.session import ENGINE, get_session
        from db.pg_features import list_active_signals, get_signal_outcome_status
        from signalrank_telegram.tier_delivery import TierDeliveryManager
        from db.pg_compat import get_all_user_ids_compat
        from core.redis_state import was_signal_delivered_sync
        from signalrank_telegram.access import resolve_user_tier
        from .formatter import format_signal
        bot = Bot(token=_require_telegram_token())
        delivery_mgr = TierDeliveryManager()
        user_ids = get_all_user_ids_compat()
        import asyncio
        async def _fetch_signals():
            async with get_session() as session:
                sigs = await list_active_signals(session, max_age_days=3, limit=100)
                await session.commit()
                return sigs
        try:
            signals = asyncio.run(_fetch_signals())
        except Exception:
            signals = []
        import concurrent.futures
        import threading
        from db.session import get_session
        from db.pg_features import record_signal_delivery
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
        def deliver_signal_to_user(sig, user_id):
            signal_id = str(getattr(sig, 'signal_id', '') or '')
            if not signal_id:
                logger.info(f"[resend] Skipping empty signal_id for user {user_id}")
                return
            # Check if outcome already reached
            try:
                outcome_status = get_signal_outcome_status(signal_id)
                if outcome_status and outcome_status.get('reached'):
                    logger.info(f"[resend] Signal {signal_id} already reached outcome, skipping user {user_id}")
                    return  # Already hit TP/SL
            except Exception as e:
                logger.warning(f"[resend] Outcome check failed for signal {signal_id}: {e}")
            # 1. Check if this user already received this signal (legacy Redis, for fast skip)
            already_delivered = was_signal_delivered_sync(user_id, signal_id)
            if already_delivered:
                logger.info(f"[resend] Signal {signal_id} already delivered to user {user_id} (Redis/memory), skipping.")
                return
            # 2. Check if this user is eligible for this signal (tier, score, daily limits)
            user_tier = resolve_user_tier(user_id).lower()
            score = float(getattr(sig, 'score', 0) or 0)
            eligible = delivery_mgr.should_send_signal(user_tier, score, user_id=user_id)
            if not eligible:
                logger.info(f"[resend] User {user_id} not eligible for signal {signal_id} (tier/score/limit), skipping.")
                return
            # 3. Deliver the signal to this user
            sig_dict = sig.__dict__ if hasattr(sig, '__dict__') else dict(sig)
            display_tier = 'vip' if user_tier in ('owner', 'admin') else user_tier
            try:
                _send_message_sync(bot, chat_id=user_id, text=format_signal(sig_dict, display_tier=display_tier))
                logger.info(f"[resend] Delivered signal {signal_id} to user {user_id} (tier={user_tier})")
            except Exception as e:
                logger.error(f"[resend] Failed to deliver signal {signal_id} to user {user_id}: {e}")
                return
            # 4. Record delivery in DB (persistent)
            try:
                # Use a new event loop for DB call if not in async context
                def db_record():
                    import asyncio
                    async def do_record():
                        async with get_session() as session:
                            try:
                                ok = await record_signal_delivery(
                                    session,
                                    telegram_user_id=int(user_id),
                                    signal_id=str(signal_id),
                                    tier_at_send=str(user_tier),
                                )
                                await session.commit()
                                if ok:
                                    logger.info(f"[resend] DB tracked delivery: signal {signal_id} to user {user_id} (tier={user_tier})")
                                else:
                                    logger.info(f"[resend] DB deduped: signal {signal_id} to user {user_id} (tier={user_tier})")
                            except Exception as e:
                                await session.rollback()
                                logger.error(f"[resend] DB error tracking delivery: signal {signal_id} to user {user_id}: {e}")
                    asyncio.run(do_record())
                if loop is None:
                    db_record()
                else:
                    # If already in event loop, schedule as thread
                    threading.Thread(target=db_record).start()
            except Exception as e:
                logger.error(f"[resend] Exception in DB delivery tracking for signal {signal_id} to user {user_id}: {e}")
        # Use ThreadPoolExecutor for parallel delivery
        # Increase pool size to handle more concurrent deliveries
        max_workers = int(os.getenv("TELEGRAM_POOL_SIZE", "24"))  # Default to 24, configurable
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for sig in signals:
                signal_id = str(getattr(sig, 'signal_id', '') or '')
                if not signal_id:
                    continue
                for user_id in user_ids:
                    futures.append(executor.submit(deliver_signal_to_user, sig, user_id))
            concurrent.futures.wait(futures)
    except Exception:
        pass

import os
from telegram.ext import Application, CommandHandler
from signalrank_telegram.httpx_config import httpx_client

def _audit_handler(command_name: str, handler):
    async def _inner(update, context):
        # IMPORTANT: Skip pre-audit for /start.
        # The audit writer creates the user row (via record_bot_event -> get_or_create_user).
        # That would make start_command see the user as "not new" and prevent referral attribution.
        # start_command already handles user creation + start auditing in a single transaction.
        if str(command_name) == "start":
            return await handler(update, context)

        try:
            from db.session import ENGINE, get_session
            if ENGINE is not None and getattr(update, "effective_user", None) is not None:
                user_id = int(update.effective_user.id)
                username = None
                try:
                    username = update.effective_user.username
                except Exception:
                    pass
                # ...existing code for auditing...
        except Exception:
            pass
        return await handler(update, context)
    return _inner

from telegram.ext import Defaults
# Increase Telegram bot request timeout for connection pool exhaustion
TELEGRAM_POOL_TIMEOUT = int(os.getenv("TELEGRAM_POOL_TIMEOUT", "30"))  # seconds, configurable
TELEGRAM_CONNECT_TIMEOUT = int(os.getenv("TELEGRAM_CONNECT_TIMEOUT", "30"))  # seconds, configurable
TELEGRAM_READ_TIMEOUT = int(os.getenv("TELEGRAM_READ_TIMEOUT", "30"))  # seconds, configurable
TELEGRAM_WRITE_TIMEOUT = int(os.getenv("TELEGRAM_WRITE_TIMEOUT", "30"))  # seconds, configurable
application = Application.builder()
application = application.token(os.getenv('TELEGRAM_TOKEN'))
application = application.pool_timeout(TELEGRAM_POOL_TIMEOUT)
application = application.connect_timeout(TELEGRAM_CONNECT_TIMEOUT)
application = application.read_timeout(TELEGRAM_READ_TIMEOUT)
application = application.write_timeout(TELEGRAM_WRITE_TIMEOUT)
application = application.build()
from .commands import reports_command
application.add_handler(CommandHandler("reports", _audit_handler("reports", reports_command)))
from .commands import filter_command
application.add_handler(CommandHandler("filter", _audit_handler("filter", filter_command)))
from .commands import apikey_command
application.add_handler(CommandHandler("apikey", _audit_handler("apikey", apikey_command)))
from .commands import language_command
application.add_handler(CommandHandler("language", _audit_handler("language", language_command)))
from .commands import referral_leaderboard_command, referral_rewards_command
# Register referral leaderboard and rewards commands
application.add_handler(CommandHandler("referral_leaderboard", _audit_handler("referral_leaderboard", referral_leaderboard_command)))
application.add_handler(CommandHandler("referral_rewards", _audit_handler("referral_rewards", referral_rewards_command)))
from .commands import admin_top_assets_command, admin_top_strategies_command, admin_user_engagement_command
# Register admin analytics commands
application.add_handler(CommandHandler("admin_top_assets", _audit_handler("admin_top_assets", admin_top_assets_command)))
application.add_handler(CommandHandler("admin_top_strategies", _audit_handler("admin_top_strategies", admin_top_strategies_command)))
application.add_handler(CommandHandler("admin_user_engagement", _audit_handler("admin_user_engagement", admin_user_engagement_command)))
import os
import asyncio
import socket
import logging
from telegram import Bot
from telegram.ext import Application, CommandHandler
from datetime import datetime

from core.performance import performance_tracker
from db.pg_compat import get_all_user_ids_compat
from signalrank_telegram.access import resolve_user_tier
from .formatter import format_signal

from .commands import (
    start_command,
    help_command,
    about_command,
    faq_command,
    disclaimer_command,
    performance_command,
    pricing_command,
    upgrade_command,
    policy_command,
    recap_command,
    signals_command,
    signal_command,
    outcome_command,
    invite_command,
    stats_command,
    history_command,
    risk_command,
    alerts_command,
    elite_command,
    early_command,
    report_command,
    feedback_command,
    notify_command,
    selfcheck_command,
    myid_command,
    dashboard_command,
)

# Register new commands
application.add_handler(CommandHandler("myid", _audit_handler("myid", myid_command)))
application.add_handler(CommandHandler("dashboard", _audit_handler("dashboard", dashboard_command)))
application.add_handler(CommandHandler("selfcheck", _audit_handler("selfcheck", selfcheck_command)))
application.add_handler(CommandHandler("notify", _audit_handler("notify", notify_command)))
application.add_handler(CommandHandler("feedback", _audit_handler("feedback", feedback_command)))

from core.redis_state import state, mark_signal_delivered_sync
from .owner_commands import (
    unlock,
    dev_pause,
    dev_resume,
    dev_force_signal,
    dev_invalidate,
    owner_users,
    owner_revenue,
    correct_signal,
)

# Import tier-based notification manager
from engine.tier_notifications import TierNotificationManager

# Initialize tier notification manager
_tier_notifier = TierNotificationManager()

# Module-level logger for scheduled jobs and dispatch traces
logger = logging.getLogger(__name__)

TIER_LIMITS = {
    'free': 3,
    'premium': 10,
    'vip': 30,
    'admin': 9999,
    'owner': 9999,
}


_LOG_ONCE_KEYS: set[str] = set()


def _log_once(key: str, message: str) -> None:
    if key in _LOG_ONCE_KEYS:
        return
    _LOG_ONCE_KEYS.add(key)
    try:
        print(message, flush=True)
    except Exception:
        pass


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


async def _send_message_async(bot: Bot, chat_id: int, text: str) -> None:
    await bot.send_message(chat_id=chat_id, text=text)


def _send_message_sync(bot: Bot, chat_id: int, text: str) -> None:
    """Send a Telegram message from sync code.

    python-telegram-bot v20+ uses async methods. The engine and APScheduler jobs
    run in sync contexts, so we bridge with asyncio.
    """

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_send_message_async(bot, int(chat_id), str(text)))
        return
    # If we're already in an event loop, schedule it.
    try:
        loop.create_task(_send_message_async(bot, int(chat_id), str(text)))
    except Exception:
        pass


def _audit_handler(command_name: str, handler):
    async def _inner(update, context):
        # IMPORTANT: Skip pre-audit for /start.
        # The audit writer creates the user row (via record_bot_event -> get_or_create_user).
        # That would make start_command see the user as "not new" and prevent referral attribution.
        # start_command already handles user creation + start auditing in a single transaction.
        if str(command_name) == "start":
            return await handler(update, context)

        try:
            from db.session import ENGINE, get_session
            if ENGINE is not None and getattr(update, "effective_user", None) is not None:
                user_id = int(update.effective_user.id)
                username = None
                try:
                    username = update.effective_user.username
                except Exception:
                    username = None

                meta = {"command": str(command_name)}
                # Avoid logging secrets (e.g., /unlock bypass key)
                if str(command_name) not in {"unlock"}:
                    try:
                        meta["args"] = list(getattr(context, "args", None) or [])
                    except Exception:
                        meta["args"] = None

                async with get_session() as session:
                    try:
                        from db.pg_features import record_bot_event

                        await record_bot_event(
                            session,
                            telegram_user_id=user_id,
                            username=username,
                            event_type="command",
                            meta=meta,
                        )
                        await session.commit()
                    except Exception as e:
                        _log_once(
                            "bot_event_audit_failed",
                            f"[bot] bot_events audit write failed: {type(e).__name__}: {e}",
                        )
        except Exception as e:
            _log_once(
                "bot_event_audit_outer_failed",
                f"[bot] bot_events audit init failed: {type(e).__name__}: {e}",
            )
        return await handler(update, context)

    return _inner


def _require_telegram_token() -> str:
    token = os.getenv('TELEGRAM_TOKEN')
    if token:
        return token

    # Local dev convenience: optionally load from a `.env` file.
    # Railway/production should rely on injected environment variables.
    allow_dotenv = (os.getenv("ALLOW_DOTENV") or "").strip().lower() in {"1", "true", "yes", "y", "on"}
    if allow_dotenv:
        env_path = os.path.join(os.getcwd(), '.env')
        if os.path.exists(env_path):
            try:
                with open(env_path, 'r', encoding='utf-8') as f:
                    for raw_line in f:
                        line = raw_line.strip()
                        if not line or line.startswith('#') or '=' not in line:
                            continue
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if key and key not in os.environ:
                            os.environ[key] = value
            except Exception:
                pass

    token = os.getenv('TELEGRAM_TOKEN')
    if token:
        return token
    raise RuntimeError(
        "TELEGRAM_TOKEN is not set. "
        "Set it in your shell (PowerShell: $env:TELEGRAM_TOKEN='...') or as a Railway Variable."
    )

# Outcome tracking notifications with tier-based formatting
def notify_trade_outcome(user_id, strategy, result, ret):
    bot = Bot(token=_require_telegram_token())
    # result: 'tp', 'partial_tp', 'sl', 'invalid', 'summary', 'free_limited'
    
    # Get user tier for appropriate formatting
    tier_raw = resolve_user_tier(user_id)
    tier = (tier_raw or 'FREE').strip().lower()
    
    # Map tier for notifications
    if tier in ('owner', 'admin'):
        user_tier = 'vip'
    elif tier == 'vip':
        user_tier = 'vip'
    elif tier == 'premium':
        user_tier = 'premium'
    else:
        user_tier = 'free'
    
    # Use tier-based notifier for formatted messages
    try:
        if result == 'tp':
            # Calculate profit percentage
            entry = float(strategy.get('entry', 0))
            exit_price = float(strategy.get('exit', 0))
            direction = str(strategy.get('direction', '')).lower()
            
            if entry > 0 and exit_price > 0:
                if direction == 'long':
                    profit_pct = ((exit_price - entry) / entry) * 100
                else:
                    profit_pct = ((entry - exit_price) / entry) * 100
            else:
                profit_pct = float(strategy.get('percent', 0))
            
            # Determine which TP level (assume TP3 for full exit)
            tp_level = 3
            msg = _tier_notifier.format_tp_hit_notification(strategy, user_tier, tp_level, profit_pct)
            
        elif result == 'partial_tp':
            entry = float(strategy.get('entry', 0))
            tp1_price = float(strategy.get('tp1', 0))
            direction = str(strategy.get('direction', '')).lower()
            
            if entry > 0 and tp1_price > 0:
                if direction == 'long':
                    profit_pct = ((tp1_price - entry) / entry) * 100
                else:
                    profit_pct = ((entry - tp1_price) / entry) * 100
            else:
                profit_pct = float(strategy.get('r_multiple', 0)) * 100
            
            msg = _tier_notifier.format_tp_hit_notification(strategy, user_tier, 1, profit_pct)
            
        elif result == 'sl':
            loss_pct = float(strategy.get('percent', 0))
            if loss_pct > 0:
                loss_pct = -loss_pct  # Make it negative
            msg = _tier_notifier.format_sl_hit_notification(strategy, user_tier, loss_pct)
            
        elif result == 'invalid':
            # Signal invalidated
            msg = _tier_notifier.format_signal_update(
                strategy,
                user_tier,
                'invalidated',
                {'reason': strategy.get('reason', 'Market conditions changed')}
            )
            
        elif result == 'free_limited':
            # Free tier gets basic notification
            if user_tier == 'free':
                msg = (
                    "🔒 FREE USER (LIMITED OUTCOME MESSAGE)\n"
                    "📊 SIGNAL UPDATE\n\n"
                    "A recent trade reached its target.\n\n"
                    "Upgrade to Premium to see:\n"
                    "• Exact entries & exits\n"
                    "• Full performance stats\n"
                    "• Real-time alerts"
                )
            else:
                # Shouldn't happen, but fallback
                msg = "📊 Trade update."
        else:
            msg = "[Outcome] Trade update."
            
    except Exception as e:
        # Fallback to old format on error
        def fmt(val, d=2):
            return f"{val:.{d}f}" if isinstance(val, float) else str(val)
        
        if result == 'tp':
            msg = (
                "✅ TAKE PROFIT HIT — FULL CLOSE\n"
                f"\nAsset: {strategy.get('asset','')}\nTimeframe: {strategy.get('timeframe','')}\nDirection: {strategy.get('direction','').upper()}\n"
                f"\nEntry: {fmt(strategy.get('entry'))}\nExit: {fmt(strategy.get('exit'))}\n"
                f"\nResult: {fmt(strategy.get('r_multiple'))}R ({fmt(strategy.get('percent',0))}%)\nDuration: {strategy.get('duration','')}\nConfidence Score: {fmt(strategy.get('confidence',0))}%\n"
                "\nWell-managed trade ✔️"
            )
        elif result == 'partial_tp':
            msg = (
                "🟢 PARTIAL TAKE PROFIT (TP1)\n"
                f"\nAsset: {strategy.get('asset','')}\nTimeframe: {strategy.get('timeframe','')}\nDirection: {strategy.get('direction','').upper()}\n"
                f"\nEntry: {fmt(strategy.get('entry'))}\nTP1: {fmt(strategy.get('tp1'))}\n"
                f"\nPartial Result: {fmt(strategy.get('r_multiple',0))}R\nRemaining Position: Active"
            )
        elif result == 'sl':
            msg = (
                "❌ STOP LOSS HIT\n"
                f"\nAsset: {strategy.get('asset','')}\nTimeframe: {strategy.get('timeframe','')}\nDirection: {strategy.get('direction','').upper()}\n"
                f"\nEntry: {fmt(strategy.get('entry'))}\nStop Loss: {fmt(strategy.get('stop'))}\n"
                f"\nResult: {fmt(strategy.get('r_multiple',-1))}R ({fmt(strategy.get('percent',0))}%)\nDuration: {strategy.get('duration','')}\n"
                "\nRisk was predefined and controlled."
            )
        elif result == 'invalid':
            msg = (
                "⚠️ SIGNAL INVALIDATED (ADMIN / MARKET EVENT)\n"
                f"\nAsset: {strategy.get('asset','')}\nTimeframe: {strategy.get('timeframe','')}\n"
                f"\nReason: {strategy.get('reason','Unknown')}\nStatus: Closed at market\n\nResult: Flat (0R)"
            )
        elif result == 'free_limited':
            msg = (
                "🔒 FREE USER (LIMITED OUTCOME MESSAGE)\n📊 SIGNAL UPDATE\n\nA recent trade reached its target.\n\nUpgrade to Premium to see:\n• Exact entries & exits\n• Full performance stats\n• Real-time alerts"
            )
        else:
            msg = "[Outcome] Trade update."
    
    bot.send_message(chat_id=user_id, text=msg)

def notify_all_users_trade_outcome(strategy, result, ret, user_ids=None):
    bot = Bot(token=_require_telegram_token())
    if user_ids is None:
        user_ids = get_all_user_ids_compat()
    # Use the same message format as notify_trade_outcome, but for all users
    for uid in user_ids:
        notify_trade_outcome(uid, strategy, result, ret)

def send_performance_summary(user_id):
    bot = Bot(token=_require_telegram_token())
    # Example daily summary message
    stats = performance_tracker.get_stats()
    total = sum(s['trades'] for s in stats.values())
    wins = sum(int(s['win_rate']*s['trades']) for s in stats.values())
    losses = total - wins
    win_rate = (wins/total*100) if total else 0
    net_r = sum(s['avg_return']*s['trades'] for s in stats.values())
    msg = (
        "📊 DAILY PERFORMANCE SUMMARY (AUTO)\n\n"
        f"Total Signals: {total}\nWins: {wins}\nLosses: {losses}\nWin Rate: {win_rate:.1f}%\nNet Result: {net_r:.2f}R\n\nConsistency over frequency."
    )
    bot.send_message(chat_id=user_id, text=msg)

def _format_free_preview(signal):
    # Limited info to drive upgrades (no exact levels)
    return (
        "🔒 FREE USER (LIMITED SIGNAL)\n\n"
        f"Reference: {signal.get('signal_id') or signal.get('id')}\n"
        f"Asset: {signal.get('asset')}\n"
        f"Timeframe: {signal.get('timeframe')}\n"
        f"Direction: {signal.get('direction')}\n\n"
        "Upgrade to Premium to see:\n"
        "• Exact entry, stop, target\n"
        "• Real-time alerts\n"
        "• Full performance tracking"
    )

def dispatch_signals(strategy_signals, user_id, regime=None):
    """Dispatch signals to user based on their tier.
    
    Tier-based Limits & Score Filtering:
    - OWNER: 9999 signals/day (all signals, real-time, no score filter)
    - ADMIN: 9999 signals/day (all signals, real-time, no score filter)
    - VIP: 30 signals/day (score >= 72 only, real-time)
    - PREMIUM: 10 signals/day (score 55-80, real-time)
    - FREE: 2 random signals/day (delayed queue, bot picks any from global pool)
    - EXTRA: 1 signal per purchase (highest scoring available, real-time)
    
    FREE tier: Bot queues ALL generated signals to global pool, then randomly 
    distributes to FREE users (different users get different signals).
    
    EXTRA signals: When FREE users buy extra signals, they get the highest scoring
    ongoing signal that hasn't been sent to them yet.
    
    Outcomes are sent for ALL signals (crypto and FX) regardless of tier.
    """

    tier_raw = resolve_user_tier(user_id)
    tier = (tier_raw or 'FREE').strip().lower()

    # Free users with paid extra-signal quota receive highest scoring signal
    extra_left = 0
    if tier == 'free':
        try:
            extra_left = int(state.get_extra_signals_left_sync(int(user_id)) or 0)
        except Exception:
            extra_left = 0

    # Global kill-switch (do not dispatch/queue)
    try:
        if state.get_killswitch_sync().enabled:
            return
    except Exception:
        pass

    # Support passing ranked buckets (vip/premium/free)
    signals_list = []
    if isinstance(strategy_signals, dict):
        vip_list = list(strategy_signals.get('vip', []) or [])
        prem_list = list(strategy_signals.get('premium', []) or [])
        # Tier-based signal selection with score thresholds
        if tier in ('owner', 'admin'):
            signals_list = vip_list + prem_list
        elif tier in ('vip',):
            signals_list = [s for s in (vip_list + prem_list) if s.get('score', 0) >= 55.0]
        elif tier in ('premium',):
            signals_list = [s for s in (vip_list + prem_list) if s.get('score', 0) >= 55.0]
        else:  # FREE
            signals_list = (vip_list + prem_list)
    else:
        signals_list = list(strategy_signals or [])

    # --- USER PREFERENCES FILTERING ---
    try:
        from .user_prefs import user_prefs_store
        prefs = user_prefs_store.get_prefs(user_id)
        assets = set([a.upper() for a in prefs.get('assets', set())]) if prefs.get('assets') else None
        timeframes = set([tf.lower() for tf in prefs.get('timeframes', set())]) if prefs.get('timeframes') else None
        strategies = set([s.lower() for s in prefs.get('strategies', set())]) if prefs.get('strategies') else None
        if assets or timeframes or strategies:
            filtered = []
            for sig in signals_list:
                asset_ok = True
                tf_ok = True
                strat_ok = True
                if assets:
                    asset = str(sig.get('asset') or sig.get('symbol') or '').upper()
                    asset_ok = asset in assets
                if timeframes:
                    tf = str(sig.get('timeframe') or '').lower()
                    tf_ok = tf in timeframes
                if strategies:
                    strat = str(sig.get('strategy_name') or sig.get('strategy') or '').lower()
                    strat_ok = strat in strategies
                if asset_ok and tf_ok and strat_ok:
                    filtered.append(sig)
            signals_list = filtered
    except Exception as e:
        _log_once('user_prefs_filter_error', f'[dispatch] User prefs filter error: {e}')

    if not signals_list:
        return

    # Entry validation: check that current price is within entry zone (±3%)
    # Add entry_status flag to track if entry has been hit or is pending
    def _check_entry_status(signal: dict) -> tuple[bool, str]:
        """
        Check if entry is valid and return (allow: bool, status: str).
        Status can be: "PENDING_ENTRY" (price >3% away), "AT_ENTRY" (price ±3%), "ENTRY_MISSED" (>3% away, hard reject)
        """
        try:
            asset = str(signal.get("asset") or "").upper()
            entry = float(signal.get("entry") or 0.0)
            if not asset or entry <= 0:
                return True, "UNKNOWN"  # Can't validate, allow through
            
            # Fetch current price
            try:
                import requests
                is_crypto = asset.endswith("USDT") or asset.endswith("USDC")
                if not is_crypto:
                    return True, "UNKNOWN"  # Skip FX validation for now
                
                # Try Binance first, then CryptoCompare fallback
                sym = asset.replace("USDT", "").replace("USDC", "")
                try:
                    resp = requests.get(
                        f"https://api.binance.com/api/v3/ticker/price",
                        params={"symbol": asset},
                        timeout=5,
                    )
                    if resp.ok:
                        price = float(resp.json().get("price", entry))
                    else:
                        raise Exception("Binance failed")
                except Exception:
                    # Fallback to CryptoCompare
                    api_key = (os.getenv("CRYPTOCOMPARE_API_KEY") or "").strip()
                    headers = {"authorization": f"Apikey {api_key}"} if api_key else {}
                    resp = requests.get(
                        "https://min-api.cryptocompare.com/data/price",
                        params={"fsym": sym, "tsyms": "USDT,USD"},
                        headers=headers,
                        timeout=5,
                    )
                    if resp.ok:
                        data = resp.json()
                        price = float(data.get("USDT") or data.get("USD") or entry)
                    else:
                        return True, "UNKNOWN"  # Can't validate, allow through
                
                # Check if price is within ±3% of entry
                price_distance_pct = abs(price - entry) / entry * 100.0
                
                # Determine entry status
                if price_distance_pct <= 3.0:
                    # Price is at entry (within tolerance)
                    return True, "AT_ENTRY"
                elif price < entry:
                    # Price is below entry (pending long entry)
                    return True, "PENDING_ENTRY"
                else:
                    # Price is above entry (potential miss)
                    return True, "PENDING_ENTRY"
            except Exception:
                return True, "UNKNOWN"  # On error, allow signal through
        except Exception:
            return True, "UNKNOWN"

    # Add entry_status flag to all signals
    try:
        for signal in signals_list:
            allow, status = _check_entry_status(signal)
            signal["entry_status"] = status
            signal["current_price_pct"] = None  # Will be populated on display
    except Exception as e:
        _log_once(
            "entry_status_error",
            f"[dispatch] Entry status error: {e}",
        )

    if not signals_list:
        return

    # Deduplicate: If multiple signals for same asset (any direction, any timeframe),
    # keep only the ONE with highest score. Use R/R as tie-breaker if scores are equal.
    try:
        original_count = len(signals_list)
        best_by_asset: dict[str, dict] = {}
        
        for sig in signals_list:
            asset = str(sig.get("asset") or sig.get("symbol") or "").upper().strip()
            
            if not asset:
                continue  # Skip invalid signals
            
            score = float(sig.get("score") or 0.0)
            rr = float(sig.get("rr_ratio") or sig.get("rr_estimate") or 0.0)
            
            cur = best_by_asset.get(asset)
            if cur is None:
                best_by_asset[asset] = sig
                continue
            
            cur_score = float(cur.get("score") or 0.0)
            cur_rr = float(cur.get("rr_ratio") or cur.get("rr_estimate") or 0.0)
            
            # Replace if better score, or same score but better R/R
            if (score > cur_score) or (score == cur_score and rr > cur_rr):
                best_by_asset[asset] = sig
        
        signals_list = list(best_by_asset.values())
        
        if len(signals_list) < original_count:
            _log_once(
                "asset_dedup",
                f"[dispatch] Deduplicated {original_count} signals → {len(signals_list)} (kept best per asset)",
            )
    except Exception as e:
        _log_once(
            "asset_dedup_error",
            f"[dispatch] Asset deduplication failed: {e}",
        )

    # Postgres-backed delivery dedup + history (preferred)
    try:
        from db.session import ENGINE, get_session

        if ENGINE is not None:
            effective_tier = tier
            display_tier = tier
            
            # OWNER and ADMIN always get VIP format for ALL notifications
            if tier in ('owner', 'admin'):
                display_tier = 'vip'
                effective_tier = tier  # Keep actual tier for delivery tracking
            elif tier == 'free' and extra_left > 0:
                effective_tier = 'premium'
                display_tier = 'premium'

            if effective_tier in ('premium', 'vip', 'owner', 'admin'):
                bot = Bot(token=_require_telegram_token())
                limit = TIER_LIMITS.get(tier, 0)
                if tier == 'free' and extra_left > 0:
                    limit = min(int(max(1, extra_left)), len(signals_list))

                async def _reserve() -> list[dict]:
                    from db.pg_features import get_or_create_signal, record_signal_delivery

                    to_send: list[dict] = []
                    async with get_session() as session:
                        for signal in signals_list[: max(0, int(limit))]:
                            s = await get_or_create_signal(session, signal)
                            ok = await record_signal_delivery(
                                session,
                                telegram_user_id=int(user_id),
                                signal_id=str(s.signal_id),
                                tier_at_send=str(effective_tier),
                            )
                            if not ok:
                                continue
                            payload = dict(signal)
                            # CRITICAL: Set signal_id from database (used for /outcome tracking)
                            payload["signal_id"] = str(s.signal_id)
                            payload.setdefault("asset", s.asset)
                            payload.setdefault("timeframe", s.timeframe)
                            payload.setdefault("direction", s.direction)
                            payload.setdefault("entry", s.entry)
                            payload.setdefault("stop_loss", s.stop_loss)
                            payload.setdefault("take_profit", s.take_profit)
                            payload.setdefault("rr_ratio", s.rr_estimate)
                            payload.setdefault("score", s.score)
                            payload.setdefault("regime", s.regime)
                            to_send.append(payload)
                        await session.commit()
                    return to_send

                try:
                    reserved = asyncio.run(_reserve())
                    reserve_failed = False
                except Exception as e:
                    reserved = []
                    reserve_failed = True
                    _log_once(
                        "dispatch_reserve_failed",
                        f"[bot] dispatch reserve failed (falling back to direct send): {type(e).__name__}: {e}",
                    )

                if _env_bool("BOT_DELIVERY_DEBUG", False):
                    try:
                        print(
                            "[bot] dispatch "
                            f"user={user_id} tier={tier} effective_tier={effective_tier} "
                            f"signals={len(signals_list)} limit={int(limit)} reserved={len(reserved)} reserve_failed={int(reserve_failed)}",
                            flush=True,
                        )
                    except Exception:
                        pass

                if reserve_failed:
                    # DB dedupe/history failed; still deliver to avoid "silent nothing".
                    sent = 0
                    for signal in signals_list:
                        if sent >= int(limit):
                            break
                        try:
                            _send_message_sync(bot, chat_id=user_id, text=format_signal(signal, display_tier=display_tier))
                            sent += 1
                            if tier == 'free' and extra_left > 0:
                                try:
                                    state.consume_extra_signals_sync(int(user_id), 1)
                                except Exception:
                                    pass
                        except Exception:
                            continue
                    return

                for signal in reserved:
                    try:
                        _send_message_sync(bot, chat_id=user_id, text=format_signal(signal, display_tier=display_tier))
                        if tier == 'free' and extra_left > 0:
                            try:
                                state.consume_extra_signals_sync(int(user_id), 1)
                            except Exception:
                                pass
                    except Exception:
                        continue
                return

            # FREE with extra signals: send highest scoring available signal immediately
            if tier == 'free' and extra_left > 0:
                bot = Bot(token=_require_telegram_token())
                
                async def _get_best_signal():
                    from db.pg_features import get_highest_scoring_available_signal_for_user, record_signal_delivery
                    async with get_session() as session:
                        sent_count = 0
                        for _ in range(min(extra_left, len(signals_list))):
                            best_sig = await get_highest_scoring_available_signal_for_user(
                                session, int(user_id)
                            )
                            if not best_sig:
                                break
                            
                            # Record delivery
                            ok = await record_signal_delivery(
                                session,
                                telegram_user_id=int(user_id),
                                signal_id=str(best_sig.signal_id),
                                tier_at_send='premium',  # Extra signals get premium formatting
                            )
                            if ok:
                                # Build signal dict for formatting with all VIP fields
                                import json
                                tp_parsed = best_sig.take_profit
                                try:
                                    # Parse JSON-encoded TP list
                                    if isinstance(best_sig.take_profit, str):
                                        tp_parsed = json.loads(best_sig.take_profit)
                                except Exception:
                                    pass
                                
                                sig_dict = {
                                    "signal_id": best_sig.signal_id,
                                    "asset": best_sig.asset,
                                    "timeframe": best_sig.timeframe,
                                    "direction": best_sig.direction,
                                    "entry": best_sig.entry,
                                    "stop_loss": best_sig.stop_loss,
                                    "take_profit": tp_parsed,
                                    "rr_ratio": best_sig.rr_estimate,
                                    "score": best_sig.score,
                                    "regime": getattr(best_sig, 'regime', 'NEUTRAL'),
                                    # VIP-specific fields
                                    "session": getattr(best_sig, 'session', ''),
                                    "market_regime": getattr(best_sig, 'regime', ''),
                                    "confluence": getattr(best_sig, 'confluence', None),
                                    "htf_bias": getattr(best_sig, 'htf_bias', None),
                                    "risk_reward": best_sig.rr_estimate,
                                    "invalidation": getattr(best_sig, 'invalidation', None),
                                    "trade_logic": getattr(best_sig, 'trade_logic', None),
                                    "strategy": best_sig.strategy_name,
                                }
                                try:
                                    # Determine display tier: VIP for owner/admin, PREMIUM otherwise
                                    from signalrank_telegram.access import resolve_user_tier
                                    user_tier = resolve_user_tier(user_id).lower()
                                    signal_display_tier = 'vip' if user_tier in ('owner', 'admin') else 'premium'
                                    _send_message_sync(bot, chat_id=user_id, text=format_signal(sig_dict, display_tier=signal_display_tier))
                                    sent_count += 1
                                    state.consume_extra_signals_sync(int(user_id), 1)
                                except Exception:
                                    pass
                        await session.commit()
                        return sent_count
                
                try:
                    asyncio.run(_get_best_signal())
                except Exception as e:
                    _log_once(
                        "extra_signal_failed",
                        f"[bot] extra signal delivery failed: {type(e).__name__}: {e}",
                    )

            # FREE users: send completely random signals at random times (bot decides when)
            # Bot picks ANY signals at random - different users get different random signals
            # Bot also decides WHEN to send: randomly picks times during day to check and send signals
            async def _send_random_signals_immediately() -> None:
                from db.pg_features import (
                    get_random_available_signals_for_free_user, 
                    record_signal_delivery,
                    get_user_next_signal_time,
                    set_user_next_signal_time
                )
                from db.models import User
                from sqlalchemy import select
                import random
                from datetime import datetime, timedelta
                from typing import Awaitable, Callable, cast
                from sqlalchemy.ext.asyncio import AsyncSession

                SetUserNextSignalTime = Callable[[AsyncSession, int, int, datetime], Awaitable[None]]
                set_user_next_signal_time_typed: SetUserNextSignalTime = cast(
                    SetUserNextSignalTime, set_user_next_signal_time
                )

                bot = Bot(token=_require_telegram_token())
                
                async with get_session() as session:
                    # Get user
                    res_user = await session.execute(
                        select(User).where(User.telegram_user_id == int(user_id))
                    )
                    user = res_user.scalar_one_or_none()
                    if not user:
                        return
                    
                    # Check how many signals user already received today
                    from db.pg_features import count_signals_delivered_today, get_last_signal_delivery_time
                    delivered_today = await count_signals_delivered_today(session, int(user_id))
                    
                    # FREE users get 2 signals per day
                    daily_limit = 3
                    remaining = max(0, daily_limit - delivered_today)
                    
                    if remaining <= 0:
                        return  # Already hit daily limit
                    
                    # Bot randomly decides WHEN to check for and send signals
                    # For 1st signal: bot picks random time during day (0-18 hours from day start)
                    # For 2nd signal: bot picks random time 2-8 hours after 1st signal
                    if delivered_today == 0:
                        # First signal: bot randomly decides what time to send a signal today
                        next_send_time = await get_user_next_signal_time(session, int(user_id), signal_number=1)
                        if not next_send_time:
                            # Bot decides: random time during the day (0-18 hours from start of day)
                            now = datetime.utcnow()
                            start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
                            random_hours = random.uniform(0, 18)
                            next_send_time = start_of_day + timedelta(hours=random_hours)
                            await set_user_next_signal_time_typed(
                                session, int(user_id), signal_number=1, send_time=next_send_time
                            )
                        
                        # Check if it's time to send yet (bot's random choice)
                        now = datetime.utcnow()
                        if now < next_send_time:
                            return  # Not time yet for 1st signal (bot's choice)
                    
                    elif delivered_today == 1:
                        # Second signal: bot decides random time after 1st signal
                        next_send_time = await get_user_next_signal_time(session, int(user_id), signal_number=2)
                        if not next_send_time:
                            last_delivery = await get_last_signal_delivery_time(session, int(user_id))
                            if last_delivery:
                                # Random delay between 2-8 hours for second signal
                                random_delay_hours = random.uniform(2, 8)
                                next_send_time = last_delivery + timedelta(hours=random_delay_hours)
                                await set_user_next_signal_time_typed(
                                    session, int(user_id), signal_number=2, send_time=next_send_time
                                )
                        
                        if next_send_time:
                            now = datetime.utcnow()
                            if now < next_send_time:
                                return  # Not time yet for 2nd signal (bot's choice)

                            min_hours = 2
                            max_hours = 8
                            random_delay_hours = random.uniform(min_hours, max_hours)
                            
                            now = datetime.utcnow()
                            time_since_last = (now - last_delivery).total_seconds() / 3600  # hours
                            
                            # Bot decides: has enough random time passed?
                            if time_since_last < random_delay_hours:
                                return  # Not time yet for 2nd signal (bot's choice)
                    
                    # Get completely random available signals (bot's choice - no quality filter)
                    # Different users get different random signals from the same pool
                    available_signals = await get_random_available_signals_for_free_user(
                        session, int(user_id), limit=remaining
                    )
                    
                    if not available_signals:
                        return  # No signals available
                    
                    # Send each signal
                    for sig in available_signals:
                        # Record delivery
                        ok = await record_signal_delivery(
                            session,
                            telegram_user_id=int(user_id),
                            signal_id=str(sig.signal_id),
                            tier_at_send='free',
                        )
                        
                        if ok:
                            # Build signal dict with all VIP fields
                            import json
                            tp_parsed = sig.take_profit
                            try:
                                # Parse JSON-encoded TP list
                                if isinstance(sig.take_profit, str):
                                    tp_parsed = json.loads(sig.take_profit)
                            except Exception:
                                pass
                            
                            sig_dict = {
                                "signal_id": sig.signal_id,
                                "asset": sig.asset,
                                "timeframe": sig.timeframe,
                                "direction": sig.direction,
                                "entry": sig.entry,
                                "stop_loss": sig.stop_loss,
                                "take_profit": tp_parsed,
                                "rr_ratio": sig.rr_estimate,
                                "score": sig.score,
                                "regime": getattr(sig, 'regime', 'NEUTRAL'),
                                # VIP-specific fields
                                "session": getattr(sig, 'session', ''),
                                "market_regime": getattr(sig, 'regime', ''),
                                "confluence": getattr(sig, 'confluence', None),
                                "htf_bias": getattr(sig, 'htf_bias', None),
                                "risk_reward": sig.rr_estimate,
                                "invalidation": getattr(sig, 'invalidation', None),
                                "trade_logic": getattr(sig, 'trade_logic', None),
                                "strategy": sig.strategy_name,
                            }
                            try:
                                # Determine display tier: VIP for owner/admin, FREE for others
                                from signalrank_telegram.access import resolve_user_tier
                                user_tier = resolve_user_tier(user_id).lower()
                                signal_display_tier = 'vip' if user_tier in ('owner', 'admin') else 'free'
                                _send_message_sync(bot, chat_id=user_id, text=format_signal(sig_dict, display_tier=signal_display_tier))
                                # Mark as delivered in Redis
                                try:
                                    mark_signal_delivered_sync(user_id, str(sig_dict.get('signal_id')))
                                except Exception:
                                    pass
                            except Exception:
                                pass
                    
                    await session.commit()

            try:
                asyncio.run(_send_random_signals_immediately())
                return
            except Exception as e:
                _log_once(
                    "free_random_send_failed",
                    f"[bot] free random signal delivery failed: {type(e).__name__}: {e}",
                )
    except Exception as e:
        _log_once(
            "dispatch_pg_path_failed",
            f"[bot] dispatch postgres path failed: {type(e).__name__}: {e}",
        )

    if tier in ('premium', 'vip', 'owner', 'admin'):
        bot = Bot(token=_require_telegram_token())
        limit = TIER_LIMITS.get(tier, 0)
        sent = 0
        # OWNER and ADMIN always get VIP format
        display_tier = 'vip' if tier in ('owner', 'admin') else tier
        for signal in signals_list:
            if sent >= limit:
                break
            try:
                _send_message_sync(bot, chat_id=user_id, text=format_signal(signal, display_tier=display_tier))
                # Mark as delivered in Redis
                try:
                    mark_signal_delivered_sync(user_id, str(signal.get('signal_id')))
                except Exception:
                    pass
                sent += 1
            except Exception:
                continue
        return

    # FREE: queue delayed summary (max 3/day)
    try:
        from db.session import ENGINE, get_session
        if ENGINE is None:
            raise RuntimeError("DATABASE_URL not configured. Postgres is required.")
        daily_limit = 3

        async def _queue() -> None:
            from db.pg_features import queue_free_signal_summary as queue_free_signal_summary_pg

            async with get_session() as session:
                # Queue any signals the bot generates (no score sorting - bot decides)
                for signal in signals_list:
                    ok = await queue_free_signal_summary_pg(
                        session,
                        telegram_user_id=int(user_id),
                        signal=signal,
                        daily_limit=int(daily_limit),
                    )
                    if not ok:
                        break
                await session.commit()

        try:
            asyncio.run(_queue())
        except Exception as e:
            _log_once(
                "queue_free_legacy_failed",
                f"[bot] queue free (legacy path) failed: {type(e).__name__}: {e}",
            )
    except Exception:
        # As a last resort, send the limited preview
        try:
            bot = Bot(token=_require_telegram_token())
            _send_message_sync(bot, chat_id=user_id, text=_format_free_preview(signals_list[0]))
        except Exception:
            pass


def downgrade_expired_subscriptions_job():
    """Daily job: downgrade expired subscriptions to FREE tier."""
    logger.info("🔄 Checking for expired subscriptions...")
    try:
        from db.session import get_session
        from db.pg_features import downgrade_expired_subscriptions

        async def _do_downgrade():
            async with get_session() as session:
                count = await downgrade_expired_subscriptions(session)
                if count > 0:
                    logger.info(f"📉 Downgraded {count} user(s) to FREE tier")
                    await session.commit()
                else:
                    logger.info("✅ No expired subscriptions to downgrade")

        asyncio.run(_do_downgrade())
    except Exception as e:
        logger.error(f"❌ Error downgrading subscriptions: {e}")


def auto_delete_old_signals_job():
    """Weekly job: hard delete signals older than 7 days."""
    logger.info("🗑️ Deleting old signals (>7 days)...")
    try:
        from db.session import get_session
        from db.pg_features import delete_old_signals

        async def _do_delete():
            async with get_session() as session:
                count = await delete_old_signals(session, older_than_days=7)
                if count > 0:
                    logger.info(f"🗑️ Deleted {count} old signal(s)")
                    await session.commit()
                else:
                    logger.info("✅ No old signals to delete")

        asyncio.run(_do_delete())
    except Exception as e:
        logger.error(f"❌ Error deleting old signals: {e}")


def distribute_random_signals_to_free_users_job():
    """Periodic job: distribute random signals to FREE users from global pool."""
    logger.info("🎲 Distributing random signals to FREE users...")
    try:
        from db.session import get_session
        from db.pg_features import queue_random_free_signals_for_all_users

        async def _do_distribute():
            async with get_session() as session:
                count = await queue_random_free_signals_for_all_users(session)
                if count > 0:
                    logger.info(f"📬 Queued signals for {count} FREE user(s)")
                    await session.commit()
                else:
                    logger.info("✅ All FREE users have reached daily limit or no new signals")

        asyncio.run(_do_distribute())
    except Exception as e:
        logger.error(f"❌ Error distributing signals to FREE users: {e}")


def run_bot() -> None:
    """Run the Telegram polling bot.

    This must be explicitly invoked (e.g. RUN_MODE=bot or RUN_MODE=all). It must
    not run on import.
    """

    from apscheduler.schedulers.background import BackgroundScheduler

    # Avoid leaking bot token in logs: httpx logs full request URLs at INFO.
    # We keep errors, but silence INFO/DEBUG.
    try:
        logging.getLogger("httpx").setLevel(logging.WARNING)
    except Exception:
        pass
    try:
        logging.getLogger("telegram").setLevel(logging.WARNING)
    except Exception:
        pass

    application = Application.builder().token(_require_telegram_token()).build()

    async def _on_error(update, context) -> None:
        err = getattr(context, "error", None)
        print(f"[bot] error: {err}", flush=True)
        # Avoid crashing the bot on handler errors; PTB will continue polling.

    application.add_error_handler(_on_error)

    async def _post_init(app):
        # BotFather-visible commands must remain concise.
        try:
            await app.bot.set_my_commands(
                [
                    ("start", "Start"),
                    ("pricing", "Pricing"),
                    ("upgrade", "Upgrade / subscribe"),
                    ("help", "Commands"),
                    ("signals", "Latest signals"),
                    ("signal", "Signal by reference"),
                    ("performance", "Performance"),
                    ("invite", "Invite"),
                ]
            )
        except Exception:
            pass

    application.post_init = _post_init

    application.add_handler(CommandHandler("start", _audit_handler("start", start_command)))
    application.add_handler(CommandHandler("help", _audit_handler("help", help_command)))
    application.add_handler(CommandHandler("about", _audit_handler("about", about_command)))
    application.add_handler(CommandHandler("faq", _audit_handler("faq", faq_command)))
    application.add_handler(CommandHandler("disclaimer", _audit_handler("disclaimer", disclaimer_command)))
    application.add_handler(CommandHandler("performance", _audit_handler("performance", performance_command)))
    application.add_handler(CommandHandler("pricing", _audit_handler("pricing", pricing_command)))
    application.add_handler(CommandHandler("upgrade", _audit_handler("upgrade", upgrade_command)))
    application.add_handler(CommandHandler("signals", _audit_handler("signals", signals_command)))
    application.add_handler(CommandHandler("signal", _audit_handler("signal", signal_command)))
    application.add_handler(CommandHandler("outcome", _audit_handler("outcome", outcome_command)))
    application.add_handler(CommandHandler("invite", _audit_handler("invite", invite_command)))

    # Premium (not advertised)
    application.add_handler(CommandHandler("stats", _audit_handler("stats", stats_command)))
    application.add_handler(CommandHandler("history", _audit_handler("history", history_command)))
    application.add_handler(CommandHandler("risk", _audit_handler("risk", risk_command)))
    application.add_handler(CommandHandler("alerts", _audit_handler("alerts", alerts_command)))

    # VIP (not advertised)
    application.add_handler(CommandHandler("elite", _audit_handler("elite", elite_command)))
    application.add_handler(CommandHandler("early", _audit_handler("early", early_command)))
    application.add_handler(CommandHandler("report", _audit_handler("report", report_command)))

    application.add_handler(CommandHandler("policy", _audit_handler("policy", policy_command)))
    application.add_handler(CommandHandler("refunds", _audit_handler("refunds", policy_command)))
    application.add_handler(CommandHandler("recap", _audit_handler("recap", recap_command)))
    # Backward compatible alias

    # Hidden owner-only commands (silent for non-owners)
    application.add_handler(CommandHandler("unlock", _audit_handler("unlock", unlock)))
    application.add_handler(CommandHandler("dev_pause", _audit_handler("dev_pause", dev_pause)))
    application.add_handler(CommandHandler("dev_resume", _audit_handler("dev_resume", dev_resume)))
    application.add_handler(CommandHandler("dev_force_signal", _audit_handler("dev_force_signal", dev_force_signal)))
    application.add_handler(CommandHandler("dev_invalidate", _audit_handler("dev_invalidate", dev_invalidate)))
    application.add_handler(CommandHandler("owner_users", _audit_handler("owner_users", owner_users)))
    application.add_handler(CommandHandler("owner_revenue", _audit_handler("owner_revenue", owner_revenue)))
    application.add_handler(CommandHandler("correct_signal", _audit_handler("correct_signal", correct_signal)))

    def send_weekly_recap():
        user_ids = get_all_user_ids_compat()
        # Prefer Postgres-backed recap when configured
        from db.session import ENGINE, get_session
        if ENGINE is not None:
            from db.pg_features import get_weekly_recap_stats

            async def _fetch(uid: int) -> dict:
                async with get_session() as session:
                    data = await get_weekly_recap_stats(session, int(uid))
                    await session.commit()
                    return data

            for user_id in user_ids:
                try:
                    stats = asyncio.run(_fetch(int(user_id)))
                except Exception:
                    stats = {"total": 0, "top_assets": [], "top_strategies": []}
                total = int(stats.get("total") or 0)
                if total <= 0:
                    recap_msg = (
                        "\U0001F4CA SignalRankAI Weekly Recap\n\n"
                        "No signals were sent to you this week.\n\n"
                        "Remember: No signals is sometimes better than bad signals.\n\n"
                        "Thank you for trading responsibly."
                    )
                else:
                    most_active = ", ".join(list(stats.get("top_assets") or [])[:2]) or "N/A"
                    best_strategy = ", ".join(list(stats.get("top_strategies") or [])[:1]) or "N/A"
                    recap_msg = (
                        "\U0001F4CA SignalRankAI Weekly Recap\n\n"
                        "Here’s a quick overview of your past week:\n\n"
                        f"• Total signals delivered: {total}\n"
                        f"• Markets most active: {most_active}\n"
                        f"• Best-performing strategy: {best_strategy}\n\n"
                        "Market conditions can be mixed, so signal frequency is intentionally limited.\n\n"
                        "Thank you for trading responsibly."
                    )
                try:
                    _send_message_sync(application.bot, chat_id=int(user_id), text=recap_msg)
                except Exception:
                    pass
            return

    # Initialize and schedule jobs
    scheduler = BackgroundScheduler()
    scheduler.add_job(send_weekly_recap, 'cron', day_of_week='mon', hour=8, minute=0)
    scheduler.add_job(resend_unsent_signals_job, 'interval', minutes=1)
    scheduler.start()


    def send_outcome_notifications():
        # Send outcome notifications only once per outcome (notified_at tracks this).
        # Fetches unnotified outcomes and sends them to all users who received the signal.
        # Once sent and marked as notified, the outcome will never be resent.
        try:
            from db.session import ENGINE, get_session
            if ENGINE is None:
                return
            from db.pg_features import (
                list_unnotified_outcomes,
                list_delivery_recipients_for_signal,
                mark_outcome_notified,
                get_alert_prefs,
            )
            from datetime import datetime

            async def _fetch() -> list[tuple[object, object, list[tuple[int, str, dict]]]]:
                async with get_session() as session:
                    rows = await list_unnotified_outcomes(session, limit=50)
                    out = []
                    for oc, sig in rows:
                        recipients = await list_delivery_recipients_for_signal(session, str(sig.signal_id))
                        enriched: list[tuple[int, str, dict]] = []
                        for telegram_user_id, tier_at_send in recipients:
                            try:
                                prefs = await get_alert_prefs(session, int(telegram_user_id))
                            except Exception:
                                prefs = {"tp_sl_enabled": True, "quiet_start_hour": None, "quiet_end_hour": None}
                            enriched.append((int(telegram_user_id), str(tier_at_send), dict(prefs or {})))
                        out.append((oc, sig, enriched))
                    await session.commit()
                    return out

            try:
                pending = asyncio.run(_fetch())
            except Exception:
                pending = []
            if not pending:
                return

            for oc, sig, recipients in pending:
                status = str(getattr(oc, 'status', '') or '').lower()
                ref = str(getattr(sig, 'signal_id', '') or '')
                # Shorten ref to 8 chars for display
                ref_short = ref[:8] if ref else 'unknown'
                r_multiple = getattr(oc, 'r_multiple', None)
                asset = str(getattr(sig, 'asset', '') or '')
                timeframe = str(getattr(sig, 'timeframe', '') or '')
                direction = str(getattr(sig, 'direction', '') or '')

                now_hour = int(datetime.now().hour)

                for telegram_user_id, tier_at_send, prefs in recipients:
                    try:
                        if isinstance(prefs, dict) and not prefs.get('tp_sl_enabled', True):
                            continue
                        qs = prefs.get('quiet_start_hour')
                        qe = prefs.get('quiet_end_hour')
                        if qs is not None and qe is not None:
                            qs = int(qs)
                            qe = int(qe)
                            if qs == qe:
                                # Quiet all day
                                continue
                            if qs < qe:
                                if qs <= now_hour < qe:
                                    continue
                            else:
                                # Wrap-around (e.g. 22 -> 6)
                                if now_hour >= qs or now_hour < qe:
                                    continue
                    except Exception:
                        pass

                    # Check if user is owner/admin for VIP formatting
                    from signalrank_telegram.access import resolve_user_tier
                    user_tier = resolve_user_tier(telegram_user_id).lower()
                    
                    # Parse which TP was hit (TP1, TP2, TP3)
                    tp_level_num = 0
                    if status in ("tp1", "partial_tp"):
                        tp_level_num = 1
                    elif status == "tp2":
                        tp_level_num = 2
                    elif status == "tp3":
                        tp_level_num = 3

                    # Fetch the delivered signal for this user and signal_id
                    delivered_signal = None
                    try:
                        from db.session import get_session
                        from db.pg_features import get_delivered_signal_by_ref
                        async def _fetch_delivered():
                            async with get_session() as session:
                                return await get_delivered_signal_by_ref(session, int(telegram_user_id), str(ref))
                        delivered_signal = asyncio.run(_fetch_delivered())
                    except Exception:
                        delivered_signal = None

                    signal_data = delivered_signal.__dict__ if delivered_signal else sig.__dict__

                    # Outcome notification logic by tier
                    notify = False
                    msg = None
                    # Try to get current market price for the asset
                    current_market_price = None
                    try:
                        from data.market_data import fetch_market_data_cached
                        mkt = fetch_market_data_cached(asset, timeframe)
                        if mkt and 'candles' in mkt and mkt['candles']:
                            current_market_price = mkt['candles'][-1].get('close')
                    except Exception:
                        pass

                    if user_tier in ("owner", "admin", "vip"):
                        if tp_level_num in (1, 2, 3):
                            notify = True
                            msg = _tier_notifier.format_tp_hit_notification(signal_data, user_tier, tp_level_num, float(getattr(oc, "percent", 0) or 0), current_market_price)
                        elif status == "sl":
                            notify = True
                            msg = _tier_notifier.format_sl_hit_notification(signal_data, user_tier, float(getattr(oc, "percent", 0) or 0))
                    elif user_tier == "premium":
                        if tp_level_num in (1, 2):
                            notify = True
                            msg = _tier_notifier.format_tp_hit_notification(signal_data, user_tier, tp_level_num, float(getattr(oc, "percent", 0) or 0), current_market_price)
                        elif status == "sl":
                            notify = True
                            msg = _tier_notifier.format_sl_hit_notification(signal_data, user_tier, float(getattr(oc, "percent", 0) or 0))
                    elif str(tier_at_send).lower() == "free":
                        if tp_level_num > 0 or status == "tp":
                            notify = True
                            msg = _tier_notifier.format_tp_hit_notification(signal_data, "free", tp_level_num or 1, float(getattr(oc, "percent", 0) or 0), current_market_price)
                        elif status == "sl":
                            notify = True
                            msg = _tier_notifier.format_sl_hit_notification(signal_data, "free", float(getattr(oc, "percent", 0) or 0))

                    if notify and msg:
                        try:
                            _send_message_sync(application.bot, chat_id=int(telegram_user_id), text=msg)
                        except Exception:
                            pass
                    try:
                        _send_message_sync(application.bot, chat_id=int(telegram_user_id), text=msg)
                    except Exception:
                        pass

                # Mark as notified so this outcome is never sent again.
                # Once marked, list_unnotified_outcomes() won't return it.
                try:
                    async def _mark(oid: int) -> None:
                        async with get_session() as session:
                            await mark_outcome_notified(session, int(oid))
                            await session.commit()

                    asyncio.run(_mark(int(getattr(oc, 'id'))))
                except Exception:
                    pass
        except Exception:
            return


    def compute_outcomes_best_effort():
        """Best-effort outcome writer.

        Scans recently delivered signals that have no outcome yet, fetches candles,
        and records TP/SL if hit. This enables follow-up messages end-to-end.
        """
        try:
            from db.session import ENGINE, get_session
            if ENGINE is None:
                return
            from db.pg_features import list_signals_missing_outcomes, upsert_outcome
            from datetime import datetime
            import json
            from data.fetcher import get_candles

            async def _fetch_candidates():
                async with get_session() as session:
                    sigs = await list_signals_missing_outcomes(session, max_age_days=3, limit=30)
                    await session.commit()
                    return sigs

            try:
                candidates = asyncio.run(_fetch_candidates())
            except Exception:
                candidates = []
            if not candidates:
                return

            now = datetime.utcnow()

            def _parse_tp(tp_raw):
                if tp_raw is None:
                    return None
                if isinstance(tp_raw, (int, float)):
                    return float(tp_raw)
                s = str(tp_raw).strip()
                if not s:
                    return None
                try:
                    data = json.loads(s)
                    if isinstance(data, list) and data:
                        return float(data[0])
                    if isinstance(data, (int, float)):
                        return float(data)
                except Exception:
                    pass
                try:
                    return float(s)
                except Exception:
                    return None

            def _ms(dt):
                try:
                    return int(dt.timestamp() * 1000)
                except Exception:
                    return 0

            for sig in candidates:
                try:
                    asset = str(getattr(sig, "asset", "") or "").upper().strip()
                    tf = str(getattr(sig, "timeframe", "") or "").lower().strip()
                    direction = str(getattr(sig, "direction", "") or "").lower().strip()
                    entry = float(getattr(sig, "entry"))
                    sl = float(getattr(sig, "stop_loss"))
                    tp = _parse_tp(getattr(sig, "take_profit", None))
                    created_at = getattr(sig, "created_at", None)
                    if not asset or not tf or direction not in {"long", "short"}:
                        continue
                    if tp is None or created_at is None:
                        continue

                    candles = get_candles(asset, tf)
                    if not candles:
                        # Fallback: try alternate granularities to improve availability
                        # Prefer higher resolution first for better entry/TP/SL detection
                        tf_order = ["1m", "5m", "15m", "1h", "4h", "1d"]
                        alt_tfs = [t for t in tf_order if t != tf]
                        for alt in alt_tfs:
                            try:
                                candles = get_candles(asset, alt)
                                if candles:
                                    break
                            except Exception:
                                candles = []
                                continue
                        if not candles:
                            continue

                    created_ms = _ms(created_at)
                    
                    # Note: Don't skip based on entry distance from current price.
                    # If TP/SL was hit, price will be far from entry - that's expected.
                    # The entry fill detection below will determine if entry was actually touched.
                    
                    # Filter candles to those after signal creation when possible.
                    filtered = []
                    for c in candles:
                        try:
                            ts = c.get("timestamp")
                            if isinstance(ts, (int, float)):
                                if int(ts) >= created_ms:
                                    filtered.append(c)
                            else:
                                # FX timestamps are ISO-ish strings; keep best-effort.
                                filtered.append(c)
                        except Exception:
                            continue
                    if not filtered:
                        continue

                    status = None
                    entry_filled = False
                    entry_filled_at = None
                    # Walk candles in chronological order and detect first hit after entry is touched.
                    for c in filtered:
                        try:
                            hi = float(c.get("high"))
                            lo = float(c.get("low"))
                        except Exception:
                            continue

                        ts_val = c.get("timestamp")

                        # Require entry fill before considering TP/SL.
                        if not entry_filled:
                            # Entry is filled if price trades through entry level OR
                            # if price has already reached TP/SL (gap up/down case)
                            if lo <= entry <= hi:
                                # Normal case: price traded through entry
                                entry_filled = True
                                entry_filled_at = ts_val
                            elif (direction == "long" and hi >= tp) or (direction == "short" and lo <= tp):
                                # Gap case: price gapped past TP without hitting entry
                                # Mark entry as filled since trade was profitable
                                entry_filled = True
                                entry_filled_at = ts_val
                            else:
                                continue

                        if direction == "long":
                            hit_sl = lo <= sl
                            hit_tp = hi >= tp
                        else:
                            hit_sl = hi >= sl
                            hit_tp = lo <= tp

                        if hit_sl and hit_tp:
                            # Ambiguous within-candle; be conservative.
                            status = "sl"
                            break
                        if hit_sl:
                            status = "sl"
                            break
                        if hit_tp:
                            status = "tp"
                            break

                    if status is None:
                        continue

                    # Compute R and % (best-effort)
                    risk = abs(entry - sl)
                    reward = abs(tp - entry)
                    r_mult = None
                    pct = None
                    try:
                        if risk > 0:
                            if status == "tp":
                                r_mult = reward / risk
                            else:
                                r_mult = -1.0
                        if status == "tp":
                            if direction == "long":
                                pct = ((tp - entry) / entry) * 100.0
                            else:
                                pct = ((entry - tp) / entry) * 100.0
                        else:
                            if direction == "long":
                                pct = -((entry - sl) / entry) * 100.0
                            else:
                                pct = -((sl - entry) / entry) * 100.0
                    except Exception:
                        r_mult = None
                        pct = None

                    meta = {
                        "source": "candle_scan",
                        "evaluated_at": now.isoformat(),
                        "tp": tp,
                        "sl": sl,
                    }

                    entry_filled_dt = None
                    try:
                        if isinstance(entry_filled_at, (int, float)):
                            entry_filled_dt = datetime.utcfromtimestamp(float(entry_filled_at) / 1000.0)
                        elif entry_filled_at:
                            entry_filled_dt = datetime.fromisoformat(str(entry_filled_at).replace("Z", ""))
                    except Exception:
                        entry_filled_dt = None

                    if entry_filled_at is not None:
                        meta["entry_filled_at"] = entry_filled_at

                    async def _write():
                        async with get_session() as session:
                            await upsert_outcome(
                                session,
                                str(sig.signal_id),
                                status,
                                meta=meta,
                                r_multiple=r_mult,
                                percent=pct,
                                opened_at=entry_filled_dt or created_at,
                                closed_at=now,
                            )
                            await session.commit()

                    try:
                        asyncio.run(_write())
                    except Exception:
                        pass

                    # Fire outcome notifications immediately instead of waiting for the scheduler loop.
                    try:
                        send_outcome_notifications()
                    except Exception:
                        pass
                except Exception:
                    continue

        except Exception:
            return

    def _in_quiet_hours(current_hour, start_hour, end_hour):
        """Check if current_hour is within quiet hours (respecting wrap-around)."""
        if start_hour == end_hour:
            return True  # Quiet all day
        if start_hour < end_hour:
            return start_hour <= current_hour < end_hour
        else:
            # Wrap-around (e.g., 22 to 6 means quiet 22-23 and 0-5)
            return current_hour >= start_hour or current_hour < end_hour

    def send_free_delayed_summaries():
        # Respect kill-switch
        try:
            if state.get_killswitch_sync().enabled:
                return
        except Exception:
            pass

        logger.info("🔄 send_free_delayed_summaries job triggered")

        # Prefer Postgres-backed delayed queue
        try:
            from db.session import ENGINE, get_session
            if ENGINE is not None:
                from db.pg_features import (
                    expire_old_free_signal_summaries as expire_old_free_signal_summaries_pg,
                    get_alert_prefs as get_alert_prefs_pg,
                    get_due_free_signal_summaries as get_due_free_signal_summaries_pg,
                    mark_free_signal_summaries_sent as mark_free_signal_summaries_sent_pg,
                    record_signal_delivery,
                )
                from datetime import datetime

                async def _fetch_due() -> dict[int, dict]:
                    async with get_session() as session:
                        try:
                            await expire_old_free_signal_summaries_pg(session, max_age_hours=24)
                        except Exception:
                            pass
                        due = await get_due_free_signal_summaries_pg(session)
                        out: dict[int, dict] = {}
                        for uid, items in due.items():
                            prefs = await get_alert_prefs_pg(session, int(uid))
                            out[int(uid)] = {"items": items, "prefs": prefs}
                        await session.commit()
                        return out

                try:
                    due = asyncio.run(_fetch_due())
                    logger.info(f"📬 Free queue check: {len(due)} user(s) with due signals")
                except Exception as e:
                    logger.error(f"Error fetching due signals: {e}", exc_info=True)
                    due = {}

                if not due:
                    logger.info("✅ No free signals due for delivery")
                    return

                now_hour = datetime.now().hour
                per_user_limit = int(os.getenv('FREE_DAILY_LIMIT', '3'))

                actions: list[tuple[int, list[int], list[str], str]] = []

                for uid, data in due.items():
                    items = list(data.get("items") or [])
                    prefs = dict(data.get("prefs") or {})

                    logger.info(f"📨 User {uid}: {len(items)} queued signal(s)")

                    if not prefs.get("tp_sl_enabled", True):
                        logger.info(f"⏸️ User {uid} has alerts disabled, marking as suppressed")
                        actions.append(
                            (int(uid), [it["id"] for it in items], [it["signal_id"] for it in items], 'suppressed')
                        )
                        continue

                    qs = prefs.get("quiet_start_hour")
                    qe = prefs.get("quiet_end_hour")
                    if qs is not None and qe is not None:
                        try:
                            if _in_quiet_hours(now_hour, int(qs), int(qe)):
                                logger.info(f"🔇 User {uid} in quiet hours ({qs}-{qe}), skipping")
                                continue
                        except Exception:
                            pass

                    items_to_send = items[:per_user_limit]
                    items_to_skip = items[per_user_limit:]

                    status = 'sent'
                    if items_to_send:
                        msg = _format_free_delayed_digest(items_to_send)
                        try:
                            _send_message_sync(application.bot, chat_id=int(uid), text=msg)
                            logger.info(f"✅ Delivered {len(items_to_send)} signal(s) to user {uid}")
                        except Exception as e:
                            logger.error(f"❌ Failed to send to user {uid}: {e}")
                            status = 'failed'

                        actions.append(
                            (
                                int(uid),
                                [it["id"] for it in items_to_send],
                                [it["signal_id"] for it in items_to_send],
                                status,
                            )
                        )

                    # Clear out any extra due items so they don't remain queued forever.
                    if items_to_skip:
                        logger.info(f"⏱️ User {uid}: {len(items_to_skip)} signal(s) overflow, marking as expired")
                        actions.append(
                            (
                                int(uid),
                                [it["id"] for it in items_to_skip],
                                [it["signal_id"] for it in items_to_skip],
                                'expired',
                            )
                        )

                if not actions:
                    logger.info("✅ No actions to apply")
                    return

                async def _apply_actions() -> None:
                    async with get_session() as session:
                        for uid, ids, signal_ids, status in actions:
                            await mark_free_signal_summaries_sent_pg(session, ids, status=status)
                            if status == 'sent':
                                for sid in signal_ids:
                                    await record_signal_delivery(
                                        session,
                                        telegram_user_id=int(uid),
                                        signal_id=str(sid),
                                        tier_at_send='free',
                                    )
                        await session.commit()

                try:
                    asyncio.run(_apply_actions())
                    logger.info(f"💾 Applied {len(actions)} queue action(s)")
                except Exception as e:
                    logger.error(f"Error applying actions: {e}", exc_info=True)
                return
        except Exception:
            pass

        # Postgres-only: no SQLite fallback
        return

    def auto_retrain_ml_model_job():
        """Automatically retrain ML model when enough outcome data exists."""
        try:
            if state.get_killswitch_sync().enabled:
                return
        except Exception:
            pass

        logger.info("🤖 ML auto-retrain job triggered")

        try:
            from ml.train_model import main as train_main

            async def _retrain():
                try:
                    success = await train_main()
                    if success:
                        logger.info("✅ ML model retrained successfully")
                    else:
                        logger.warning("⚠️ ML retrain skipped (insufficient data)")
                except Exception as e:
                    logger.error(f"❌ ML retrain failed: {e}", exc_info=True)

            asyncio.run(_retrain())
        except Exception as e:
            logger.error(f"Error in ML retrain job: {e}", exc_info=True)

    scheduler = BackgroundScheduler()
    scheduler.add_job(send_free_delayed_summaries, 'interval', minutes=10)
    scheduler.add_job(compute_outcomes_best_effort, 'interval', minutes=3)
    scheduler.add_job(send_outcome_notifications, 'interval', minutes=2)  # Only sends unnotified outcomes (sends once per outcome)
    # Distribute random signals to FREE users every 15 minutes
    scheduler.add_job(distribute_random_signals_to_free_users_job, 'interval', minutes=15)
    scheduler.add_job(
        send_weekly_recap,
        'cron',
        day_of_week='sun',
        hour=18,
        minute=0
    )
    # Auto-downgrade expired subscriptions (daily at 00:00 UTC)
    scheduler.add_job(
        downgrade_expired_subscriptions_job,
        'cron',
        hour=0,
        minute=0,
    )
    # Auto-delete old signals (weekly, Sunday at 01:00 UTC)
    scheduler.add_job(
        auto_delete_old_signals_job,
        'cron',
        day_of_week='sun',
        hour=1,
        minute=0,
    )
    # Auto-retrain ML model (weekly, Sunday at 02:00 UTC)
    scheduler.add_job(
        auto_retrain_ml_model_job,
        'cron',
        day_of_week='sun',
        hour=2,
        minute=0,
    )
    scheduler.start()

    print("[boot] telegram bot polling starting", flush=True)
    application.run_polling()


if __name__ == "__main__":
    run_bot()
