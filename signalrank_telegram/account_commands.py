from datetime import datetime, timedelta
from sqlalchemy import select, func
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from db.session import get_session, get_engine_for_event_loop
from db.models import User, SignalDelivery, Outcome, MT5Execution
from engine.tiered_executor import PREMIUM_DAILY_LIMIT, reset_daily_counter_if_needed
from engine.risk_analytics import sharpe_ratio, sortino_ratio
from signalrank_telegram.utils import tier_rank, _effective_tier, _build_dynamic_menu

async def performance_command(update, context):
    """30-day performance summary."""
    if await _public_guard(update):
        return
    user_id = update.effective_user.id
    tier: str = _effective_tier(user_id)
    
    try:
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        _perf_kbd = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📈 Signals", callback_data="nav_signals"),
                InlineKeyboardButton("👤 Account", callback_data="nav_account"),
            ],
            [
                InlineKeyboardButton("🚀 Upgrade", callback_data="nav_upgrade"),
                InlineKeyboardButton("🆘 Support", callback_data="nav_support"),
            ],
        ])
    except Exception:
        _perf_kbd = None
    
    try:
        from db.pg_features import get_user_performance_30d
        async with get_session() as session:
            stats = await get_user_performance_30d(session, int(user_id))
            await session.commit()
        
        total = int((stats or {}).get("total") or 0)
        wins = int((stats or {}).get("wins") or 0)
        losses = int((stats or {}).get("losses") or 0)
        win_rate = float((stats or {}).get("win_rate") or 0.0)
        avg_r = (stats or {}).get("avg_r")
        net_r = (stats or {}).get("net_r")
        tracked = int((stats or {}).get("tracked_outcomes") or 0)
        profit_loss = float((stats or {}).get("profit_loss_pct") or 0.0)
        
        if total <= 0:
            msg = "No signals in the last 30 days."
        else:
            if tier_rank(tier) < tier_rank("PREMIUM"):
                bucket: str = "strong" if win_rate >= 0.6 else ("cautious" if win_rate <= 0.4 else "mixed")
                msg: str = f"📊 Performance (limited)\n\nRecent trend: {bucket}.\nUpgrade to Premium for full stats."
            else:
                avg_r_str: str = f"{float(avg_r):.2f}R" if avg_r is not None else "N/A"
                net_r_str: str = f"{float(net_r):.2f}R" if net_r is not None else "N/A"
                profit_str: str = f"+{profit_loss:.2f}%" if profit_loss >= 0 else f"{profit_loss:.2f}%"
                profit_emoji: str = "✅" if profit_loss >= 0 else "⚠️"
                
                msg: str = (
                    f"📊 Performance (last 30 days)\n\n"
                    f"Signals delivered: {total}\n"
                    f"Outcomes tracked: {tracked}/{total}\n"
                    f"Wins: {wins} | Losses: {losses}\n"
                    f"Win rate: {round(win_rate*100,1)}%\n"
                    f"Avg R per trade: {avg_r_str}\n"
                    f"Net R (total): {net_r_str}\n"
                    f"{profit_emoji} Est. profit/loss: {profit_str}\n\n"
                    "💡 Based on 1% risk per signal."
                )
        
        if update.message is not None:
            await update.message.reply_text(msg, reply_markup=_perf_kbd)
        return
    except Exception as e:
        _audit_logger.error(f"/performance failed for user={user_id}: {e}")
        if update.message is not None:
            await update.message.reply_text(
                "No performance data available. Use /signals for recent activity.",
                reply_markup=_perf_kbd,
            )

async def history_command(update, context):
    """Recent signal history with outcomes."""
    if update.effective_user is None:
        return
    user_id = update.effective_user.id
    asset: str | None = None
    tf: str | None = None
    if context.args:
        asset = str(context.args[0]).upper()
        if len(context.args) > 1:
            tf = str(context.args[1])
    
    try:
        from db.pg_features import list_recent_signals_delivered
        async with get_session() as session:
            rows = await list_recent_signals_delivered(
                session,
                telegram_user_id=int(user_id),
                limit=15,
                asset=asset,
                timeframe=tf,
            )
            if rows:
                sids = [s.signal_id for s in rows]
                from sqlalchemy import select
                from db.models import Outcome
                oc_rows = (await session.execute(
                    select(Outcome).where(Outcome.signal_id.in_(sids))
                )).scalars().all()
                oc_map: dict[str, Outcome] = {oc.signal_id: oc for oc in oc_rows}
            else:
                oc_map = {}
            await session.commit()
        
        if not rows:
            if update.message is not None:
                await update.message.reply_text(
                    "📭 No signal history found yet.\n\n"
                    "You'll see your past signals here as they arrive."
                )
            return
        
        lines: list[str] = [f"🧾 <b>Signal History</b> (last {len(rows)})\n"]
        _r_values: list[float] = []
        for s in rows:
            oc = oc_map.get(s.signal_id)
            if oc is not None and oc.status:
                status_u = str(oc.status).upper()
                oc_emoji = "✅" if oc.status.startswith("tp") else ("❌" if oc.status == "sl" else "⏳")
                r_txt = ""
                if oc.r_multiple is not None:
                    r_sign = "+" if float(oc.r_multiple) >= 0 else ""
                    r_txt = f" | {r_sign}{float(oc.r_multiple):.1f}R"
                    _r_values.append(float(oc.r_multiple))
                outcome_txt = f"{oc_emoji} <b>{status_u}</b>{r_txt}"
            else:
                outcome_txt = "⏳ Open"
            
            tf_txt = f" [{s.timeframe}]" if s.timeframe else ""
            entry_txt = f"{float(s.entry):.5f}" if s.entry is not None else "—"
            ref = s.signal_id[:8]
            lines.append(
                f"• <b>{s.asset}</b>{tf_txt} {str(s.direction or '').upper()}\n"
                f"  Entry: <code>{entry_txt}</code>  {outcome_txt}  Ref: <code>{ref}</code>"
            )
        
        if len(_r_values) >= 5:
            try:
                _sr = sharpe_ratio(_r_values)
                _so = sortino_ratio(_r_values)
                lines.append("")
                lines.append("📐 <b>Advanced Ratios</b>")
                lines.append(f"• Sharpe: <b>{_sr:.2f}</b>")
                lines.append(f"• Sortino: <b>{_so:.2f}</b>")
            except Exception:
                pass
        
        lines.append("\n💡 /signal <ref> for full signal details")
        lines.append("💡 /simulate <capital> <risk%> for Monte Carlo forecast")
        if update.message is not None:
            await update.message.reply_text("\n".join(lines), parse_mode="HTML")
        return
    except Exception as exc:
        if update.message is not None:
            await update.message.reply_text(f"❌ Could not load history: {exc}")

async def apikey_command(update, context) -> None:
    """Generate or rotate API key for /signals web endpoint."""
    if update.effective_user is None or update.message is None:
        return
    user_id = update.effective_user.id
    args = context.args or []
    try:
        from web.api import generate_api_key
    except Exception:
        generate_api_key = lambda: "demo-key"
    
    async def _rotate_api_token_for_user(user_id: int, ttl_days: int = 30) -> str:
        from datetime import datetime, timedelta
        from db.session import get_session
        from db.repository import create_api_token
        token = generate_api_key()
        expires = datetime.utcnow() + timedelta(days=max(1, min(int(ttl_days), 365)))
        async with get_session() as session:
            await create_api_token(
                session,
                telegram_user_id=int(user_id),
                raw_token=str(token),
                scope="signals:read",
                expires_at=expires,
            )
            await session.commit()
        return str(token)
    
    async def _get_existing_api_token_meta(user_id: int):
        from db.session import get_session
        from db.repository import get_latest_active_api_token_meta
        async with get_session() as session:
            meta = await get_latest_active_api_token_meta(session, telegram_user_id=int(user_id))
            await session.commit()
        return meta
    
    if args and args[0].lower() == "regenerate":
        key = await _rotate_api_token_for_user(int(user_id), ttl_days=30)
        await update.message.reply_text(f"🔑 Your new API key: {key}\nKeep it secret. Use it with the /signals API endpoint.")
        return
    
    meta = await _get_existing_api_token_meta(int(user_id))
    if meta is None:
        key = await _rotate_api_token_for_user(int(user_id), ttl_days=30)
        await update.message.reply_text(f"🔑 Your API key: {key}\nUse it with the /signals API endpoint. Send /apikey regenerate to rotate.")
        return
    
    prefix = str(meta.get("token_prefix") or "")
    exp = str(meta.get("expires_at") or "unknown")
    await update.message.reply_text(
        f"🔑 Active API key exists.\n"
        f"Prefix: <code>{prefix}</code>\n"
        f"Expires: <code>{exp}</code>\n\n"
        f"Use /apikey regenerate to rotate and receive a new full key.",
        parse_mode="HTML",
    )

__all__ = ['performance_command', 'history_command', 'apikey_command']
