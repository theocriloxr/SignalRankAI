import asyncio
import logging
import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import ContextTypes
from sqlalchemy import select, func, text
from db.session import get_engine_for_event_loop, get_session
from db.models import Signal, Outcome, SignalDelivery, User
from engine.price_validator import enrich_signal_with_live_price, is_signal_fresh, get_asset_type
from core.tier_constants import MAX_SIGNAL_AGE_SECONDS, TIER_SCORE_THRESHOLDS, FREE_MIN_SCORE, FREE_SIGNAL_DAILY_LIMIT, FREE_PROOF_FEED_LIMIT
from .utils import _public_guard, tier_rank, _effective_tier, _build_signal_action_keyboard
from .formatter import format_signal, format_signal_free_new, format_signal_free_limited
from engine.signal_calculations import calculate_profit_loss_pct
from core.redis_state import state
from data.fetcher import async_get_candles, get_asset_type as _get_asset_type

_audit_logger = logging.getLogger("audit")
logger = logging.getLogger(__name__)

async def signals_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user's signals with tier-specific formatting.
    
    FIX: Now fetches ALL signals including resolved/invalidated ones to show users what happened.
    Shows status info: Active, Invalidated (SL hit before entry), Missed, Expired.
    """
    if await _public_guard(update):
        return
    if update.message is None and getattr(update, "callback_query", None) is not None:
        try:
            update.message = update.callback_query.message
        except Exception:
            pass
    if update.message is None:
        return
    
    user_id: int = update.effective_user.id
    tier: str = _effective_tier(user_id)
    show_unvoted_only: bool = False
    
    try:
        arg0 = str((context.args or [""])[0] or "").strip().lower()
        show_unvoted_only = arg0 in {"unvoted", "pending", "notvoted"}
    except Exception:
        show_unvoted_only = False
    
    try:
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        _nav_kbd = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📊 Performance", callback_data="nav_performance"),
                InlineKeyboardButton("🚀 Upgrade", callback_data="nav_upgrade"),
            ],
            [
                InlineKeyboardButton("👤 Account", callback_data="nav_account"),
                InlineKeyboardButton("🆘 Support", callback_data="nav_support"),
            ],
        ])
    except Exception:
        _nav_kbd = None
    
    signals_list: list[dict] = []
    
    async def _filter_unvoted(signals_in: list[dict]) -> list[dict]:
        if not show_unvoted_only or not signals_in:
            return signals_in
        try:
            from sqlalchemy import select
            from db.models import SignalEngagement, User
            from db.session import get_session
            signal_ids = [str(s.get("signal_id") or "") for s in signals_in if s.get("signal_id")]
            if not signal_ids:
                return []
            async with get_session() as session:
                user_row = (await session.execute(
                    select(User).where(User.telegram_user_id == int(user_id)).limit(1)
                )).scalar_one_or_none()
                if user_row is None:
                    return signals_in
                engaged_rows = await session.execute(
                    select(SignalEngagement.signal_id)
                    .where(
                        SignalEngagement.user_id == int(user_row.id),
                        SignalEngagement.signal_id.in_(signal_ids),
                    )
                )
                engaged_set = {str(x) for x in (engaged_rows.scalars().all() or [])}
                await session.commit()
            return [s for s in signals_in if str(s.get("signal_id") or "") not in engaged_set]
        except Exception:
            return signals_in
    
    # FREE tier: show last 5 delivered signals from today
    if tier_rank(tier) < tier_rank("PREMIUM"):
        try:
            from db.pg_features import list_signals_sent_today
            async with get_session() as session:
                rows = await list_signals_sent_today(session, telegram_user_id=int(user_id))
                signals_list = []
                for r in rows:
                    sig_dict = {
                        "signal_id": r.signal_id,
                        "asset": r.asset,
                        "timeframe": r.timeframe,
                        "direction": r.direction,
                        "entry": r.entry,
                        "stop_loss": r.stop_loss,
                        "take_profit": r.take_profit,
                        "rr_ratio": r.rr_estimate,
                        "score": r.score,
                        "created_at": getattr(r, "created_at", None),
                    }
                    try:
                        sig_dict = enrich_signal_with_live_price(sig_dict)
                    except Exception:
                        pass
                    signals_list.append(sig_dict)
            signals_list = await _filter_unvoted(signals_list)
            eligible = list(signals_list)
            if not eligible:
                free_min = int(float(TIER_SCORE_THRESHOLDS.get("free", FREE_MIN_SCORE)))
                if show_unvoted_only:
                    await update.message.reply_text("✅ No unvoted FREE proof cards right now.")
                else:
                    await update.message.reply_text(
                        f"⚠️ No FREE-eligible proof cards ({free_min}+) right now. Upgrade for full active feed access."
                    )
                return
            picked = eligible[:FREE_PROOF_FEED_LIMIT]
            from .formatter import format_signal_free_new
            for s in picked:
                try:
                    formatted = format_signal_free_new(
                        s,
                        signals_sent_today=len(signals_list),
                        daily_limit=int(FREE_SIGNAL_DAILY_LIMIT),
                    )
                    if formatted:
                        await update.message.reply_text(
                            formatted,
                            parse_mode="HTML",
                            reply_markup=_build_signal_action_keyboard(s),
                        )
                except Exception as e:
                    _audit_logger.error(f"Error formatting free signal for {user_id}: {e}")
                await update.message.reply_text("👆 Upgrade to PREMIUM for full signal intelligence.")
                return
        except Exception as e:
            _audit_logger.error(f"signals_command FREE tier error for {user_id}: {e}")
    
    # PREMIUM/VIP: ALL signals from last 48 hours including resolved/invalidated ones
    # FIX: Broaden query to show signals regardless of sent_ok status or outcome
    # This fixes the issue where resend job didn't mark sent_ok=True
    # Also fetch outcome status to display properly
    all_signals = []
    try:
        from sqlalchemy import select
        from db.models import Signal, SignalDelivery, User, Outcome
        from datetime import datetime, timedelta, timezone
        
        async with get_session() as session:
            # Get user
            user_row = (await session.execute(
                select(User).where(User.telegram_user_id == int(user_id)).limit(1)
            )).scalar_one_or_none()
            
            if user_row is None:
                await update.message.reply_text("⚠️ User not found. Start with /start")
                return
            
            # FIX: Get signals from last 48 hours WITHOUT filtering by sent_ok or outcome
            cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
            
            # Get ALL signals delivered to user in last 48 hours (regardless of sent_ok or outcome)
            rows = (
                await session.execute(
                    select(Signal, SignalDelivery.delivered_at)
                    .join(SignalDelivery, SignalDelivery.signal_id == Signal.signal_id)
                    .where(
                        SignalDelivery.user_id == user_row.id,
                        SignalDelivery.delivered_at >= cutoff,
                    )
                    .order_by(SignalDelivery.delivered_at.desc())
                    .limit(50)
                )
            ).all()
            
            # Get outcomes for these signals
            signal_ids = [r[0].signal_id for r in rows]
            outcomes_map = {}
            if signal_ids:
                outcome_rows = (
                    await session.execute(
                        select(Outcome.signal_id, Outcome.status)
                        .where(Outcome.signal_id.in_(signal_ids))
                    )
                ).all()
                outcomes_map = {row[0]: row[1] for row in outcome_rows}
            
            # Build signal dicts with status info
            for sig_row, delivered_at in rows:
                outcome_status = outcomes_map.get(sig_row.signal_id)
                status_str = str(outcome_status).upper() if outcome_status else None
                
                # Determine signal status display
                if status_str:
                    if status_str.startswith('TP'):
                        signal_status = f"✅ WIN ({status_str})"
                    elif status_str == 'SL':
                        signal_status = "❌ STOP LOSS"
                    elif status_str in {'INVALID', 'INVALIDATED'}:
                        signal_status = "⚠️ INVALIDATED (SL hit before entry)"
                    elif status_str in {'MISSED', 'TIME_STOP'}:
                        signal_status = "⏰ MISSED (price never reached entry)"
                    else:
                        signal_status = f"📊 {status_str}"
                elif getattr(sig_row, 'expired', False):
                    signal_status = "⏰ EXPIRED"
                else:
                    signal_status = "🟢 ACTIVE"
                
                all_signals.append({
                    "signal_id": sig_row.signal_id,
                    "asset": sig_row.asset,
                    "timeframe": sig_row.timeframe,
                    "direction": sig_row.direction,
                    "entry": sig_row.entry,
                    "stop_loss": sig_row.stop_loss,
                    "take_profit": sig_row.take_profit,
                    "rr_ratio": sig_row.rr_estimate,
                    "score": sig_row.score,
                    "regime": getattr(sig_row, 'regime', 'NEUTRAL'),
                    "strategy_name": sig_row.strategy_name,
                    "created_at": sig_row.created_at,
                    "signal_status": signal_status,
                })
    except Exception as e:
        _audit_logger.error(f"Error fetching signals for {user_id}: {e}")
    
    # Try fallback to unresolved if the new function fails
    if not all_signals:
        try:
            from db.pg_features import list_unresolved_signals_for_user
            async with get_session() as session:
                rows = await list_unresolved_signals_for_user(
                    session,
                    telegram_user_id=int(user_id),
                    lookback_days=30,
                )
                all_signals = [
                    {
                        "signal_id": r.signal_id,
                        "asset": r.asset,
                        "timeframe": r.timeframe,
                        "direction": r.direction,
                        "entry": r.entry,
                        "stop_loss": r.stop_loss,
                        "take_profit": r.take_profit,
                        "rr_ratio": r.rr_estimate,
                        "score": r.score,
                        "confidence": getattr(r, 'confidence', 0.5),
                        "regime": getattr(r, 'regime', 'NEUTRAL'),
                        "strength": getattr(r, 'strength', 0.5),
                        "ml_probability": getattr(r, 'ml_probability', 0.5),
                        "strategy_name": r.strategy_name,
                        "strategy_group": r.strategy_group,
                        "created_at": r.created_at,
                        "outcome_status": None,
                    }
                    for r in rows
                ]
        except Exception as e:
            _audit_logger.error(f"Error fetching unresolved signals for {user_id}: {e}")
    
    all_signals = await _filter_unvoted(all_signals)
    filtered_signals = all_signals  # PREMIUM/VIP get all signals
    
    if not filtered_signals:
        await update.message.reply_text(
            "✅ No active unresolved signals in your range right now."
            if not show_unvoted_only 
            else "✅ No unvoted active unresolved signals right now."
        )
        return
    
    total_active = len(filtered_signals)
    if update.message is not None and total_active > 0:
        await update.message.reply_text(f"📊 Your Active Signals ({total_active} in last 30 days):")
    
    from .formatter import format_signal
    for s in filtered_signals:
        try:
            formatted = format_signal(s, user_tier=tier)
            if formatted:
                await update.message.reply_text(
                    formatted,
                    parse_mode="HTML",
                    reply_markup=_build_signal_action_keyboard(s),
                )
        except Exception as e:
            _audit_logger.error(f"Error formatting signal for {user_id}: {e}")

async def proof_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Free-friendly proof feed with recent verified outcomes."""
    if await _public_guard(update):
        return
    if update.message is None:
        return
    try:
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import select, func
        from db.models import Signal, Outcome
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        tp_statuses = {"tp", "tp1", "tp2", "tp3"}
        loss_statuses = {"sl"}
        
        recent_rows = []
        wins = 0
        losses = 0
        engine = get_engine_for_event_loop()
        if engine is not None:
            async with get_session() as session:
                recent_rows = (
                    await session.execute(
                        select(Signal.asset, Signal.timeframe, Outcome.status)
                        .join(Outcome, Outcome.signal_id == Signal.signal_id)
                        .where(Signal.created_at >= cutoff)
                        .where(func.lower(Outcome.status).in_(tp_statuses.union(loss_statuses)))
                        .order_by(Signal.created_at.desc())
                        .limit(5)
                    )
                ).all()
                summary_rows = (
                    await session.execute(
                        select(Outcome.status, func.count(Outcome.id))
                        .join(Signal, Signal.signal_id == Outcome.signal_id)
                        .where(Signal.created_at >= cutoff)
                        .where(func.lower(Outcome.status).in_(tp_statuses.union(loss_statuses)))
                        .group_by(Outcome.status)
                    )
                ).all()
                for status, count in summary_rows:
                    st = str(status or "").lower()
                    if st in tp_statuses:
                        wins += int(count or 0)
                    elif st in loss_statuses:
                        losses += int(count or 0)
        
        total = wins + losses
        win_rate = (wins / total * 100.0) if total > 0 else 0.0
        lines = [
            "✅ <b>Proof Feed</b>",
            "Recent verified outcomes to show real performance quality.",
            "",
            f"📊 Last 30d tracked outcomes: <b>{total}</b>",
            f"✅ Wins: <b>{wins}</b>   ❌ Losses: <b>{losses}</b>   🎯 Win rate: <b>{win_rate:.1f}%</b>",
            "",
            "🔎 Latest verified outcomes:",
        ]
        if recent_rows:
            for asset, timeframe, status in recent_rows:
                st = str(status or "").upper()
                tag = "✅" if str(status or "").lower().startswith("tp") else "❌"
                lines.append(f"{tag} {asset} • {timeframe} • {st}")
        else:
            lines.append("No verified outcomes yet in this window.")
        lines.extend([
            "",
            "⚠️ Trading risk is real. No guaranteed returns.",
        ])
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 View Signals", callback_data="nav_signals")],
            [InlineKeyboardButton("🚀 Upgrade", callback_data="nav_upgrade")],
        ])
        await update.message.reply_text("\n".join(lines), parse_mode="HTML", reply_markup=keyboard)
    except Exception as e:
        _audit_logger.error(f"Error in proof command: {e}")
        await update.message.reply_text("⚠️ Proof feed temporarily unavailable.")

__all__ = ['signals_command', 'proof_command']
