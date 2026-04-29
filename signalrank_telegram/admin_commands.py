import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func, desc, text
from telegram import Update
from telegram.ext import ContextTypes
from db.session import get_engine_for_event_loop, get_session
from db.models import Signal, AdminEvent
from db.repository import count_active_vip_users
from core.redis_state import state
from ml.inference import MLFilter
from ml.features import extract_features
from engine.signal_analytics import signal_analytics
from config import OWNER_IDS, ADMIN_IDS

logger = logging.getLogger(__name__)

def _is_admin(user_id) -> bool:
    """Return True if user has admin or owner privileges."""
    try:
        uid = int(user_id)
    except Exception:
        return False
    try:
        if uid in OWNER_IDS:
            return True
    except Exception:
        pass
    try:
        if uid in ADMIN_IDS:
            return True
    except Exception:
        pass
    try:
        _aid = (os.getenv("ADMIN_ID") or "").strip()
        if _aid and uid == int(_aid):
            return True
    except Exception:
        pass
    try:
        tier = _effective_tier(uid).upper()
        return tier in ("ADMIN", "OWNER")
    except Exception:
        return False

async def admin_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin dashboard with secure button menu (ADMIN_IDS only)."""
    if update.effective_user is None:
        return
    if int(update.effective_user.id) not in ADMIN_IDS:
        return
    try:
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📢 Broadcast to All", callback_data="admin_broadcast"),
                InlineKeyboardButton("👥 User Stats", callback_data="admin_user_stats"),
            ],
            [
                InlineKeyboardButton("💸 Revenue Analytics", callback_data="admin_revenue"),
                InlineKeyboardButton("⚡ Force Signal", callback_data="admin_force_signal"),
            ],
            [
                InlineKeyboardButton("🛑 Pause/Resume Engine", callback_data="admin_toggle_engine"),
                InlineKeyboardButton("🧠 Force Market Scan", callback_data="admin_force_market_scan"),
            ],
        ])
    except Exception:
        keyboard = None
    if update.message is None and getattr(update, "callback_query", None) is not None:
        try:
            update.message = update.callback_query.message
        except Exception:
            pass
    if update.message is None:
        return
    await update.message.reply_text("🛡️ Admin Dashboard", reply_markup=keyboard)

@require_tier("ADMIN")
async def force_market_scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if int(update.effective_user.id) not in ADMIN_IDS:
        return
    try:
        from ml.inference import MLFilter
        from ml.features import extract_features
    except Exception:
        await update.message.reply_text("⚠️ ML module not available. Scan skipped.")
        return
    ml_filter = MLFilter()
    if not getattr(ml_filter, "active", False):
        await update.message.reply_text("⚠️ ML model not loaded — train first.")
        return
    threshold = float(os.getenv("ML_PROB_THRESHOLD", "0.65"))
    try:
        from db.session import get_session
        from db.models import Signal, AdminEvent
        from sqlalchemy import select
        from datetime import datetime, timedelta
        cutoff = datetime.utcnow() - timedelta(hours=4)
        async with get_session() as session:
            rows = await session.execute(
                select(Signal)
                .where(
                    Signal.created_at >= cutoff,
                    Signal.ml_probability.is_(None),
                    Signal.expired.is_(False),
                )
                .limit(50)
            )
            signals = rows.scalars().all()
        approved = rejected = errors = 0
        for sig_row in signals:
            try:
                sig_dict = {col.name: getattr(sig_row, col.name) for col in sig_row.__table__.columns}
                features = extract_features(sig_dict, {})
                ok, _prob = ml_filter.ml_filter(features, threshold=threshold)
                if ok:
                    approved += 1
                else:
                    rejected += 1
            except Exception:
                errors += 1
        try:
            session.add(
                AdminEvent(
                    event_type="force_market_scan",
                    actor_telegram_user_id=int(update.effective_user.id),
                    details={
                        "total": len(signals),
                        "approved": approved,
                        "rejected": rejected,
                        "errors": errors,
                        "threshold": threshold,
                    },
                )
            )
            await session.commit()
        except Exception:
            pass
    except Exception:
        await update.message.reply_text("⚠️ Scan failed. Check logs for details.")
        return
    await update.message.reply_text(
        f"🤖 Market scan complete. Signals={len(signals)} | "
        f"approved={approved} | rejected={rejected} | errors={errors} | "
        f"threshold={threshold:.2f}"
    )

async def admin_top_assets_command(update, context) -> None:
    if update.effective_user is None or update.message is None:
        return
    user_id = update.effective_user.id
    if not _is_admin(user_id):
        await update.message.reply_text("Admin only.")
        return
    stats = signal_analytics.get_stats()
    delivery = stats.get('delivery_stats', {})
    asset_counts = {}
    for k, v in delivery.items():
        if k.startswith('delivered_'):
            asset = k[len('delivered_'):]
            asset_counts[asset] = asset_counts.get(asset, 0) + v
    top = sorted(asset_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    msg: str = "\n".join([f"{a}: {c}" for a, c in top]) or "No data."
    await update.message.reply_text(f"Top Assets (delivered):\n{msg}")

async def admin_top_strategies_command(update, context) -> None:
    if update.effective_user is None or update.message is None:
        return
    user_id = update.effective_user.id
    if not _is_admin(user_id):
        await update.message.reply_text("Admin only.")
        return
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select, func, desc
    from db.session import get_session, get_engine_for_event_loop
    from db.models import Signal
    engine = get_engine_for_event_loop()
    if engine is None:
        await update.message.reply_text("Database unavailable.")
        return
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    async with get_session() as session:
        res = await session.execute(
            select(Signal.strategy_name, func.count(Signal.signal_id))
            .where(Signal.created_at >= cutoff)
            .group_by(Signal.strategy_name)
            .order_by(desc(func.count(Signal.signal_id)))
            .limit(10)
        )
        rows = res.fetchall()
    if not rows:
        await update.message.reply_text("No strategy data available (last 30d).")
        return
    lines = [f"{name}: {cnt}" for name, cnt in rows]
    await update.message.reply_text("Top Strategies (last 30d):\n" + "\n".join(lines))

async def admin_user_engagement_command(update, context) -> None:
    if update.effective_user is None or update.message is None:
        return
    user_id = update.effective_user.id
    if not _is_admin(user_id):
            await update.message.reply_text("Admin only.")
            return
    stats = signal_analytics.get_stats()
    engagement = stats.get('user_engagement', {})
    top = sorted(engagement.items(), key=lambda x: x[1], reverse=True)[:10]
    msg: str = "\n".join([f"{u}: {c}" for u, c in top]) or "No data."
    await update.message.reply_text(f"Top Users (engagement):\n{msg}")

@require_tier("ADMIN")
async def selfcheck_command(update, context) -> None:
    """Admin/Owner: Show quick health summary of the system."""
    checks = []
    running_on_railway = bool((os.getenv("RAILWAY_SERVICE_NAME") or "").strip() or (os.getenv("RAILWAY_ENVIRONMENT") or "").strip())
    
    # DB check
    try:
        from db.session import get_engine_for_event_loop
        engine = get_engine_for_event_loop()
        checks.append("✅ Database: connected" if engine else "❌ Database: not connected")
    except Exception:
        checks.append("❌ Database: error")
    
    # Redis check
    try:
        from core.redis_state import state
        state.get_sync("health_check")
        checks.append("✅ Redis: connected")
    except Exception:
        checks.append("❌ Redis: not connected")
+
    # Railway env readiness check
    if running_on_railway:
        checks.append("✅ Railway: detected")
        checks.append("✅ GEMINI_API_KEY: set" if (os.getenv("GEMINI_API_KEY") or "").strip() else "❌ GEMINI_API_KEY: missing")
        checks.append("✅ META_API_TOKEN: set" if (os.getenv("META_API_TOKEN") or "").strip() else "❌ META_API_TOKEN: missing")
        checks.append("✅ ENCRYPTION_KEY: set" if (os.getenv("ENCRYPTION_KEY") or "").strip() else "❌ ENCRYPTION_KEY: missing")
        _owner_ids_raw = (os.getenv("OWNER_IDS") or "").strip()
        checks.append("✅ OWNER_IDS: set" if _owner_ids_raw else "⚠️ OWNER_IDS: missing (owner-only commands disabled)")
    
    # yfinance check
    try:
        import yfinance as yf
        t = yf.Ticker("AAPL")
        p = t.fast_info.get('lastPrice')
        checks.append(f"✅ yfinance: working (AAPL=${p:.2f})" if p else "⚠️ yfinance: no price")
    except Exception:
        checks.append("❌ yfinance: not available")
    
    # Bot token check
    try:
        from signalrank_telegram.bot import application
        bot = application.bot
        me = await bot.get_me()
        checks.append(f"✅ Bot: @{me.username}")
    except Exception:
        checks.append("❌ Bot: token invalid")
    
    # Last signal check
    try:
        from db.session import get_session
        from sqlalchemy import select, desc
        from db.models import Signal
        async with get_session() as session:
            res = await session.execute(select(Signal).order_by(desc(Signal.created_at)).limit(1))
            last = res.scalar_one_or_none()
            if last:
                checks.append(f"✅ Last signal: {last.asset} {last.timeframe} at {last.created_at}")
            else:
                checks.append("⚠️ Last signal: none found")
    except Exception:
        checks.append("⚠️ Last signal: check failed")
    
    if update.message is not None:
        await update.message.reply_text("🔍 System Health\n\n" + "\n".join(checks))
    
    @require_tier("ADMIN")
    async def ops_health_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Admin runtime reliability report.
    
        Reports:
        - delivered signals without outcomes
        - time-stop/force-closed outcomes
        - redis connectivity
        - mt5 credential-link success rate
        """
        if update.message is None:
            return
    
        try:
            from datetime import datetime, timedelta
            from sqlalchemy import select, func
            from db.session import get_engine_for_event_loop, get_session
            from db.models import SignalDelivery, Outcome, MT5Credentials
    
            if get_engine_for_event_loop() is None:
                await update.message.reply_text("⚠️ Database not configured.")
                return
    
            # Redis connectivity check (real connectivity, not local fallback).
            redis_status = "❌ disconnected"
            redis_url = (os.getenv("REDIS_URL") or "").strip()
            if redis_url:
                try:
                    import redis as _redis
                    _rc = _redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=3, socket_timeout=3)
                    _rc.ping()
                    redis_status = "✅ connected"
                except Exception as _re:
                    redis_status = f"❌ error ({type(_re).__name__})"
            else:
                redis_status = "⚠️ REDIS_URL not set"
    
            window_days = 30
            now = datetime.utcnow()
            window_start = now - timedelta(days=window_days)
    
            async with get_session() as session:
                # 1) Delivered signals without any outcome row.
                untracked_q = (
                    select(func.count(func.distinct(SignalDelivery.signal_id)))
                    .outerjoin(Outcome, Outcome.signal_id == SignalDelivery.signal_id)
                    .where(Outcome.id.is_(None))
                )
                untracked_count = int((await session.execute(untracked_q)).scalar() or 0)
    
                # 2) Stale force-closed outcomes (TIME_STOP policy, with invalid fallback).
                invalid_q = (
                    select(func.count(Outcome.id))
                    .where(
                        Outcome.status.in_(["time_stop", "invalid"]),
                        Outcome.closed_at.is_not(None),
                        Outcome.closed_at >= window_start,
                    )
                )
                invalid_count_30d = int((await session.execute(invalid_q)).scalar() or 0)
    
                # 3) MT5 link success rate over recent credentials rows.
                total_mt5_q = select(func.count(MT5Credentials.id)).where(MT5Credentials.created_at >= window_start)
                success_mt5_q = select(func.count(MT5Credentials.id)).where(
                    MT5Credentials.created_at >= window_start,
                    MT5Credentials.metaapi_account_id.is_not(None),
                )
                total_mt5 = int((await session.execute(total_mt5_q)).scalar() or 0)
                success_mt5 = int((await session.execute(success_mt5_q)).scalar() or 0)
                await session.commit()
    
            mt5_rate = (float(success_mt5) / float(total_mt5) * 100.0) if total_mt5 > 0 else 0.0
    
            msg = (
                "🛠️ <b>Ops Health</b>\n\n"
                "<b>Runtime</b>\n"
                f"• Redis: <b>{redis_status}</b>\n"
                f"• Delivered signals without outcome: <b>{untracked_count}</b>\n"
                f"• Time-stop/force-closed outcomes (last {window_days}d): <b>{invalid_count_30d}</b>\n\n"
                "<b>Execution</b>\n"
                f"• MT5 link success (last {window_days}d): <b>{success_mt5}/{total_mt5}</b> (<b>{mt5_rate:.1f}%</b>)\n\n"
                "<i>Tip: if untracked is high, keep outcome tracker enabled and confirm live price providers are stable.</i>"
            )
            await update.message.reply_text(msg, parse_mode="HTML")
        except Exception as exc:
            await update.message.reply_text(f"❌ ops health failed: {exc}")
        
        __all__ = [
            'admin_dashboard',
            'admin_top_assets_command', 
            'admin_top_strategies_command',
            'admin_user_engagement_command',
            'selfcheck_command',
            'ops_health_command',
            'force_market_scan_command'
        ]
