from utils.timeutils import now_utc_naive
from telegram import Update
from telegram.ext import ContextTypes
from db.session import get_session, get_engine_for_event_loop
from db.repository import get_or_create_user
# --- ADMIN COMMAND: /broadcast ---
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not await _is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Access Denied.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return
    msg = " ".join(context.args)
    import asyncio
    from telegram.error import RetryAfter
    from db.pg_compat import get_all_user_ids_compat
    user_ids = get_all_user_ids_compat()
    from signalrank_telegram.bot import application
    bot = application.bot
    sent = 0
    for uid in user_ids:
        try:
            while True:
                try:
                    await bot.send_message(chat_id=uid, text=msg)
                    break
                except RetryAfter as e:
                    await asyncio.sleep(float(getattr(e, "retry_after", 1.0) or 1.0))
            await asyncio.sleep(0.5)
            sent += 1
        except Exception:
            continue
    await update.message.reply_text(f"Broadcast sent to {sent} users.")

# --- ADMIN COMMAND: /add_vip ---
async def add_vip_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not await _is_owner(update.effective_user.id):
        return
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("Usage: /add_vip <telegram_user_id>")
        return
    try:
        user_id = int(context.args[0])
        async with get_session() as session:
            user = await get_or_create_user(session, telegram_user_id=user_id)
            user.tier = "vip"
            await session.commit()
        await update.message.reply_text(f"User {user_id} upgraded to VIP.")
    except Exception as e:
        await update.message.reply_text(f"Failed to add VIP: {e}")

# --- ADMIN COMMAND: /remove_user ---
async def remove_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not await _is_owner(update.effective_user.id):
        return
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("Usage: /remove_user <telegram_user_id>")
        return
    try:
        user_id = int(context.args[0])
        async with get_session() as session:
            user = await get_or_create_user(session, telegram_user_id=user_id)
            user.tier = "free"
            await session.commit()
        await update.message.reply_text(f"User {user_id} downgraded to FREE.")
    except Exception as e:
        await update.message.reply_text(f"Failed to remove user: {e}")

# --- ADMIN COMMAND: /pause_signals ---
async def pause_signals_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not await _is_owner(update.effective_user.id):
        return
    await state.set_killswitch(True, reason="Paused by admin via /pause_signals")
    await update.message.reply_text("All signals paused (kill-switch enabled).")
from config import config, ADMIN_IDS
import json
from uuid import uuid4
from datetime import datetime, timedelta
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from core.redis_state import state


def _owner_id() -> int:
    try:
        return int(getattr(config, "OWNER_TELEGRAM_ID", 0))
    except Exception:
        return 0


def _strict_owner_ids() -> set[int]:
    # Collect configured owner IDs from multiple possible config locations
    ids = set()
    try:
        ids |= set(getattr(config, "OWNER_TELEGRAM_IDS", set()) or set())
    except Exception:
        pass
    try:
        ids |= set(getattr(config, "OWNER_IDS", set()) or set())
    except Exception:
        pass
    try:
        ids |= set(getattr(config, "owner_ids", set()) or set())
    except Exception:
        pass
    # Normalize to ints
    out: set[int] = set()
    for v in ids:
        try:
            out.add(int(v))
        except Exception:
            continue
    return out


def _bypass_key() -> Optional[str]:
    key = getattr(config, "BYPASS_KEY", None)
    return key.strip() if key else None


import logging
_owner_logger = logging.getLogger("owner_debug")

async def _is_owner(user_id: int) -> bool:
    uid = int(user_id)
    # Check all configured owner IDs (OWNER_TELEGRAM_ID + OWNER_IDS + OWNER_TELEGRAM_IDS)
    if uid in _strict_owner_ids():
        return True
    oid = _owner_id()
    if oid and uid == oid:
        return True
    # Temporary bypass (granted by /unlock key)
    bypass = await state.has_temp_owner(uid)
    if bypass:
        return True
    return False


async def _is_admin_or_owner(user_id: int) -> bool:
    try:
        uid = int(user_id)
    except Exception:
        return False
    if await _is_owner(uid):
        return True
    try:
        if uid in ADMIN_IDS:
            return True
    except Exception:
        pass
    return False




async def _is_strict_owner(user_id: int) -> bool:
    uid = int(user_id)
    oid = _owner_id()
    return uid in _strict_owner_ids() or bool(oid and uid == oid)


    key = getattr(config, "BYPASS_KEY", None)
    return key.strip() if key else None


async def unlock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """One-time unlock: grants 7 days of Premium to anyone with the right key.

    Rules:
    - Silent if wrong key or no args
    - Each user can only redeem the key ONCE. After that they must pay.
    - Grants premium tier + 7-day expiry in DB
    - Records the use in Redis (long TTL) + BotEvent (permanent)
    """
    if update.effective_user is None or update.message is None:
        return
    if not context.args or len(context.args) != 1:
        return  # silent

    provided = context.args[0].strip()
    expected = _bypass_key()
    if not expected or provided != expected:
        return  # silent — wrong key

    user_id = int(update.effective_user.id)
    redis_key = f"unlock_key_used:{user_id}"

    # ── Check one-use gate (Redis fast path) ────────────────────────────────
    already_used_redis = False
    try:
        already_used_redis = bool(state.get_sync(redis_key))
    except Exception:
        pass

    if already_used_redis:
        await update.message.reply_text(
            "🔒 You've already used this unlock key.\n"
            "Use /upgrade to subscribe and keep your Premium access."
        )
        return

    # ── Check DB for belt-and-suspenders (in case Redis was flushed) ────────
    already_used_db = False
    try:
        from db.session import get_engine_for_event_loop, get_session
        from db.models import BotEvent
        from db.repository import get_or_create_user
        from sqlalchemy import select
        if get_engine_for_event_loop() is not None:
            async with get_session() as session:
                db_user = await get_or_create_user(
                    session,
                    telegram_user_id=user_id,
                    username=getattr(update.effective_user, "username", None),
                )
                res = await session.execute(
                    select(BotEvent)
                    .where(
                        BotEvent.user_id == db_user.id,
                        BotEvent.event_type == "unlock_key_used",
                    )
                    .limit(1)
                )
                already_used_db = res.scalar_one_or_none() is not None
    except Exception:
        pass

    if already_used_db:
        # Re-stamp Redis so future checks are fast
        try:
            state.set_sync(redis_key, "1", ex=60 * 60 * 24 * 365 * 10)  # 10 years
        except Exception:
            pass
        await update.message.reply_text(
            "🔒 You've already used this unlock key.\n"
            "Use /upgrade to subscribe and keep your Premium access."
        )
        return

    # ── Grant 7-day Premium ─────────────────────────────────────────────────
    from datetime import datetime, timedelta
    premium_until = now_utc_naive() + timedelta(days=7)

    try:
        from db.session import get_engine_for_event_loop, get_session
        from db.repository import get_or_create_user
        from db.models import BotEvent, Subscription, AdminEvent
        from db.pg_features import record_bot_event

        if get_engine_for_event_loop() is not None:
            async with get_session() as session:
                db_user = await get_or_create_user(
                    session,
                    telegram_user_id=user_id,
                    username=getattr(update.effective_user, "username", None),
                )
                # Upgrade tier + set expiry on User row
                db_user.tier = "premium"
                db_user.premium_until = premium_until

                # Create a real Subscription record so tier-resolution sees it
                import uuid as _uuid
                sub = Subscription(
                    user_id=db_user.id,
                    tier="premium",
                    status="active",
                    started_at=now_utc_naive(),
                    expires_at=premium_until,
                    meta={"source": "unlock_key"},
                    paystack_reference=f"unlock_{user_id}_{_uuid.uuid4().hex[:8]}",
                )
                session.add(sub)

                # Audit events
                try:
                    session.add(AdminEvent(
                        event_type="unlock_key_used",
                        actor_telegram_user_id=user_id,
                        details={"tier": "premium", "days": 7},
                    ))
                except Exception:
                    pass
                try:
                    await record_bot_event(
                        session,
                        telegram_user_id=user_id,
                        username=getattr(update.effective_user, "username", None),
                        event_type="unlock_key_used",
                        meta={"tier": "premium", "days": 7},
                    )
                except Exception:
                    pass

                await session.commit()
    except Exception as _e:
        _owner_logger.warning(f"[unlock] DB grant failed for user {user_id}: {_e}")
        await update.message.reply_text(
            "⚠️ Could not activate premium right now. Please contact support."
        )
        return

    # ── Stamp Redis so next call is instant ─────────────────────────────────
    try:
        state.set_sync(redis_key, "1", ex=60 * 60 * 24 * 365 * 10)  # 10 years
    except Exception:
        pass

    await update.message.reply_text(
        "🎉 *Premium Unlocked for 7 Days!*\n\n"
        "You now have access to:\n"
        "⭐ Real-time signals with full Entry / SL / TP\n"
        "📊 Confidence scores & risk/reward\n"
        "📈 Performance stats & signal history\n"
        "⚡ Trade directly on MT5\n\n"
        f"📅 Your premium expires on: {premium_until.strftime('%Y-%m-%d')}\n\n"
        "🔒 This key can only be used once. After expiry, use /upgrade to continue.",
        parse_mode="MarkdownV2",
    )


async def provider_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner/admin command: show provider health and circuit-breaker snapshot.

    Returns a short report listing unhealthy providers (down > threshold),
    a small provider-health summary from the in-process cache, and the
    provider circuit breaker snapshot from `core.circuit_breaker`.
    """
    if update.effective_user is None or update.message is None:
        return
    if not await _is_admin_or_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Access Denied.")
        return

    try:
        from data import fetcher
        from core.circuit_breaker import get_provider_breaker_snapshot

        parts: list[str] = []

        unhealthy = []
        try:
            unhealthy = fetcher.get_unhealthy_providers()
        except Exception:
            unhealthy = []

        if unhealthy:
            parts.append("Unhealthy providers (down minutes):")
            for name, mins in unhealthy:
                parts.append(f"- {name}: {mins:.1f} min")
        else:
            parts.append("No unhealthy providers detected.")

        # Provider health summary (best-effort, internal structure)
        try:
            ph = getattr(fetcher, "_PROVIDER_HEALTH", {}) or {}
            if ph:
                parts.append("\nProvider health summary:")
                for name, entry in sorted(ph.items()):
                    failures = len(entry.get("failures", []))
                    last_success = int(entry.get("last_success", 0) or 0)
                    parts.append(f"- {name}: failures={failures}, last_success={last_success}")
        except Exception:
            pass

        # Circuit breaker snapshot
        try:
            snap = get_provider_breaker_snapshot()
            if snap:
                parts.append("\nCircuit breaker snapshot:")
                for name, info in sorted(snap.items()):
                    state = "OPEN" if info.get("open") else "closed"
                    rem = int(info.get("open_remaining_s", 0) or 0)
                    failures = int(info.get("failures", 0) or 0)
                    parts.append(f"- {name}: {state}, open_remaining={rem}s, failures={failures}")
        except Exception:
            pass

        await update.message.reply_text("\n".join(parts) or "No provider data available.")
    except Exception as e:
        await update.message.reply_text(f"Failed to get provider status: {e}")


async def dev_pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not await _is_admin_or_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Access Denied.")
        return
    await state.set_killswitch(True, reason="paused via /dev_pause")
    await update.message.reply_text("Kill-switch enabled.")


async def dev_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not await _is_admin_or_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Access Denied.")
        return
    await state.set_killswitch(False, reason="")
    await update.message.reply_text("Kill-switch disabled.")


async def dev_force_signal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not await _is_admin_or_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Access Denied.")
        return

    args = list(context.args or [])
    override_requested = any(str(a).strip().lower() in {"--override", "override", "--force"} for a in args)
    args = [a for a in args if str(a).strip().lower() not in {"--override", "override", "--force"}]
    requested_asset = str(args[0]).upper().replace("/", "").strip() if len(args) >= 1 else ""
    requested_tf = str(args[1]).strip().lower() if len(args) >= 2 else ""

    candidate_assets = [requested_asset] if requested_asset else [
        x.strip().upper().replace("/", "")
        for x in (config.__dict__.get("FORCE_SIGNAL_ASSETS") or "BTCUSDT,ETHUSDT,XAUUSD,EURUSD").split(",")
        if x.strip()
    ]
    candidate_timeframes = [requested_tf] if requested_tf else ["15m", "1h", "4h"]

    from db.session import get_engine_for_event_loop, get_session
    from db.models import Signal, AdminEvent
    from engine.market_state import get_market_state_async
    from engine.strategies.signal_generator import SignalGenerator

    engine = get_engine_for_event_loop()
    if engine is None:
        await update.message.reply_text("Database unavailable.")
        return

    generator = SignalGenerator()
    best_signal = None
    best_asset = None
    best_tf = None
    best_ml_prob = None
    best_regime = "NEUTRAL"

    for asset in candidate_assets:
        for timeframe in candidate_timeframes:
            try:
                import asyncio
                import os
                timeout_s = float(os.getenv("FORCE_SIGNAL_FETCH_TIMEOUT_SECONDS", "8") or 8)
                market_state = await asyncio.wait_for(
                    get_market_state_async(asset, [timeframe], include_ml=True),
                    timeout=max(2.0, timeout_s),
                )
                tf_data = (market_state.get("timeframes") or {}).get(timeframe) or {}
                candles = tf_data.get("candles") or []
                indicators = tf_data.get("indicators") or {}
                ml_prob = tf_data.get("ml_score")
                if len(candles) < 50:
                    continue
                generated = generator.generate_signals(
                    asset,
                    timeframe,
                    {
                        "candles": candles,
                        "indicators": indicators,
                        "ml_probability": ml_prob,
                    },
                )
                if not generated:
                    continue
                current_best = max(generated, key=lambda item: float(getattr(item, "score", 0) or 0))
                if best_signal is None or float(current_best.score or 0) > float(best_signal.score or 0):
                    best_signal = current_best
                    best_asset = asset
                    best_tf = timeframe
                    best_ml_prob = ml_prob
                    best_regime = str(indicators.get("regime") or "NEUTRAL")
            except Exception:
                continue

    if best_signal is None or best_asset is None or best_tf is None:
        attempted_assets = ", ".join(candidate_assets)
        attempted_tfs = ", ".join(candidate_timeframes)
        await update.message.reply_text(
            "No fresh signal could be generated right now.\n\n"
            f"Assets checked: {attempted_assets}\n"
            f"Timeframes checked: {attempted_tfs}\n\n"
            "Try again with /force_signal <ASSET> <TIMEFRAME>, for example: /force_signal BTCUSDT 1h"
        )
        return

    # Strict by default: bypass schedule timing only; keep core quality gates.
    # Admin/owner may explicitly override via /force_signal ... --override.
    try:
        strict_mode = str(getattr(config, "FORCE_SIGNAL_STRICT_MODE", "1") or "1").strip().lower() in {"1", "true", "yes", "on"}
    except Exception:
        strict_mode = True

    score_val = float(getattr(best_signal, "score", 0) or 0)
    try:
        ml_val = None if best_ml_prob is None else float(best_ml_prob)
    except Exception:
        ml_val = None
    min_score = float(getattr(config, "FORCE_SIGNAL_MIN_SCORE", 55.0) or 55.0)
    min_ml = float(getattr(config, "FORCE_SIGNAL_MIN_ML_PROB", 0.0) or 0.0)

    if strict_mode and not override_requested:
        quality_ok = score_val >= min_score and (ml_val is None or ml_val >= min_ml)
        if not quality_ok:
            await update.message.reply_text(
                "⚠️ Force-signal blocked by strict quality gates.\n"
                f"Score={score_val:.1f} (min {min_score:.1f})\n"
                f"ML={ml_val if ml_val is not None else 'N/A'} (min {min_ml:.2f})\n\n"
                "Use /force_signal <ASSET> <TF> --override to bypass for emergency use."
            )
            return

    tp_levels = []
    try:
        tp_levels = [float(tp.get("price")) for tp in (best_signal.take_profit or []) if isinstance(tp, dict) and tp.get("price") is not None]
    except Exception:
        tp_levels = []

    rr_ratio = None
    try:
        if tp_levels:
            risk = abs(float(best_signal.entry) - float(best_signal.stop_loss))
            reward = abs(float(tp_levels[0]) - float(best_signal.entry))
            if risk > 0:
                rr_ratio = reward / risk
    except Exception:
        rr_ratio = None

    signal_id = str(uuid4())
    expires_at = now_utc_naive() + timedelta(hours=12)
    
    score_for_storage = float(best_signal.score or 0)
    
    signal_payload = {
        "signal_id": signal_id,
        "asset": best_asset,
        "timeframe": best_tf,
        "direction": best_signal.direction,
        "entry": best_signal.entry,
        "stop_loss": best_signal.stop_loss,
        "take_profit": best_signal.take_profit,
        "tp_levels": tp_levels,
        "rr_ratio": rr_ratio,
        "score": score_for_storage,
        "regime": best_regime,
        "ml_probability": best_ml_prob,
        "strategy_name": best_signal.strategy_name,
        "strategy_group": best_signal.strategy_group,
        "strength": best_signal.confidence,
        "confidence": best_signal.confidence,
        "created_at": now_utc_naive(),
        "expires_at": expires_at,
    }

    async with get_session() as session:
        try:
            session.add(
                Signal(
                    signal_id=signal_id,
                    asset=best_asset,
                    timeframe=best_tf,
                    direction=best_signal.direction,
                    entry=float(best_signal.entry),
                    stop_loss=float(best_signal.stop_loss),
                    take_profit=json.dumps(best_signal.take_profit or []),
                    rr_estimate=rr_ratio,
                    score=score_for_storage,
                    regime=best_regime,
                    ml_probability=float(best_ml_prob) if best_ml_prob is not None else None,
                    strategy_name=str(best_signal.strategy_name),
                    strategy_group=str(best_signal.strategy_group),
                    strength=float(best_signal.confidence or 0.0),
                    fingerprint=f"{best_asset}_{best_tf}_{best_signal.direction}_{int(float(best_signal.entry) or 0)}",
                    archived=False,
                    expired=False,
                    expires_at=expires_at,
                )
            )
            session.add(
                AdminEvent(
                    event_type="dev_force_signal",
                    actor_telegram_user_id=int(update.effective_user.id),
                    details={
                        "signal_id": signal_id,
                        "asset": best_asset,
                        "timeframe": best_tf,
                        "generated": True,
                        "score": float(best_signal.score or 0),
                    },
                )
            )
            await session.commit()
        except Exception:
            await session.rollback()

    from signalrank_telegram.formatter import format_signal_vip_new
    
    # For forced signals, always use VIP template (bypasses quality gates for admin/owner)
    msg = format_signal_vip_new(signal_payload)
    
    if not msg:
        msg = (
            "Forced Signal (generated)\n"
            f"Asset: {best_asset}\n"
            f"TF: {best_tf}\n"
            f"Dir: {best_signal.direction}\n"
            f"Entry: {best_signal.entry}\n"
            f"SL: {best_signal.stop_loss}\n"
            f"TP1: {tp_levels[0] if tp_levels else 'N/A'}\n"
            f"Score: {best_signal.score}\n"
            f"Ref: {signal_id[:8]}"
        )

    # Send as a real signal card (same delivery path as live dispatch) so
    # /force_signal can be used to verify end-to-end Telegram delivery.
    delivered = False
    try:
        from telegram import Bot
        from signalrank_telegram.bot import _deliver_or_update_signal_sync, _require_telegram_token

        delivered = bool(
            _deliver_or_update_signal_sync(
                Bot(token=_require_telegram_token()),
                telegram_user_id=int(update.effective_user.id),
                signal=dict(signal_payload or {}),
                display_tier="vip",
            )
        )
    except Exception as _send_err:
        _owner_logger.warning("[/force_signal] direct signal send failed: %s", _send_err)

    if delivered:
        await update.message.reply_text(
            f"✅ Forced signal delivered to your Telegram inbox\n"
            f"Asset: {best_asset} | TF: {best_tf} | Score: {score_for_storage:.1f}"
        )
    else:
        await update.message.reply_text(msg)


async def dev_invalidate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not await _is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Access Denied.")
        return
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Usage: /dev_invalidate <signal_id>")
        return
    signal_id = context.args[0].strip()

    from db.session import get_engine_for_event_loop, get_session
    from db.models import Signal, AdminEvent
    from sqlalchemy import select, or_

    engine = get_engine_for_event_loop()
    if engine is None:
        await update.message.reply_text("Database unavailable.")
        return

    async with get_session() as session:
        stmt = select(Signal).where(or_(Signal.signal_id == signal_id, Signal.signal_id.ilike(f"{signal_id}%")))
        res = await session.execute(stmt)
        sig: Signal | None = res.scalar_one_or_none()
        if sig is None:
            await update.message.reply_text("Signal not found.")
            return

        sig.archived = True
        try:
            session.add(
                AdminEvent(
                    event_type="dev_invalidate",
                    actor_telegram_user_id=int(update.effective_user.id),
                    details={"signal_id": sig.signal_id},
                )
            )
        except Exception:
            pass

        await session.commit()

    await update.message.reply_text(f"Invalidated: {sig.signal_id[:8]}")


async def owner_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Strict owner-only: show total users and active subscribers."""
    if update.effective_user is None or update.message is None:
        return
    if not await _is_strict_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Access Denied.")
        return

    try:
        from db.session import get_engine_for_event_loop, get_session
        if get_engine_for_event_loop() is None:
            await update.message.reply_text("Postgres not configured.")
            return
        from db.models import User, Subscription
        from sqlalchemy import select, func
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        async with get_session() as session:
            res_users = await session.execute(select(func.count(User.id)))
            total_users = int(res_users.scalar() or 0)

            res_active = await session.execute(
                select(Subscription.tier, func.count(Subscription.id))
                .where(Subscription.status == "active", Subscription.expires_at.is_not(None), Subscription.expires_at > now)
                .group_by(Subscription.tier)
            )
            active_rows = res_active.all() or []
            await session.commit()

        active_map = {str(t).lower(): int(c) for (t, c) in active_rows}
        prem = int(active_map.get("premium", 0))
        vip = int(active_map.get("vip", 0))
        msg = (
            "👤 Users (Owner)\n\n"
            f"Total users started bot: {total_users}\n"
            f"Active Premium: {prem}\n"
            f"Active VIP: {vip}"
        )
        await update.message.reply_text(msg)
    except Exception:
        await update.message.reply_text("Unable to load user stats right now.")


async def owner_revenue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Strict owner-only: show revenue totals and breakdowns."""
    if update.effective_user is None or update.message is None:
        return
    if not await _is_strict_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Access Denied.")
        return

    try:
        from db.session import get_engine_for_event_loop, get_session
        if get_engine_for_event_loop() is None:
            await update.message.reply_text("Postgres not configured.")
            return
        from db.models import PaymentEvent
        from sqlalchemy import select, func

        def _plan_label(days: int | None, plan_code: str | None) -> str:
            if plan_code:
                return str(plan_code)
            if days == 7:
                return "weekly"
            if days == 30:
                return "monthly"
            if days == 90:
                return "quarterly"
            if days is None:
                return "unknown"
            return f"{int(days)}d"

        async with get_session() as session:
            res_total_sub = await session.execute(
                select(func.coalesce(func.sum(PaymentEvent.amount_ngn), 0)).where(PaymentEvent.kind == "subscription")
            )
            total_sub = int(res_total_sub.scalar() or 0)

            res_total_extra = await session.execute(
                select(func.coalesce(func.sum(PaymentEvent.amount_ngn), 0)).where(PaymentEvent.kind == "extra_signals")
            )
            total_extra = int(res_total_extra.scalar() or 0)

            total_all = int(total_sub) + int(total_extra)

            res_by_tier_sub = await session.execute(
                select(PaymentEvent.tier, func.coalesce(func.sum(PaymentEvent.amount_ngn), 0))
                .where(PaymentEvent.kind == "subscription")
                .group_by(PaymentEvent.tier)
                .order_by(func.coalesce(func.sum(PaymentEvent.amount_ngn), 0).desc())
            )
            by_tier_sub = [(str(t or "unknown"), int(a or 0)) for (t, a) in (res_by_tier_sub.all() or [])]

            res_by_tier_extra = await session.execute(
                select(PaymentEvent.tier, func.coalesce(func.sum(PaymentEvent.amount_ngn), 0))
                .where(PaymentEvent.kind == "extra_signals")
                .group_by(PaymentEvent.tier)
                .order_by(func.coalesce(func.sum(PaymentEvent.amount_ngn), 0).desc())
            )
            by_tier_extra = [(str(t or "unknown"), int(a or 0)) for (t, a) in (res_by_tier_extra.all() or [])]

            res_by_plan = await session.execute(
                select(PaymentEvent.tier, PaymentEvent.duration_days, PaymentEvent.plan_code, func.coalesce(func.sum(PaymentEvent.amount_ngn), 0))
                .where(PaymentEvent.kind == "subscription")
                .group_by(PaymentEvent.tier, PaymentEvent.duration_days, PaymentEvent.plan_code)
                .order_by(func.coalesce(func.sum(PaymentEvent.amount_ngn), 0).desc())
                .limit(10)
            )
            by_plan = res_by_plan.all() or []
            await session.commit()

        lines = [
            "💰 Revenue (Owner)",
            "",
            f"Total (all): ₦{total_all}",
            f"Subscriptions: ₦{total_sub}",
            f"Extra signals: ₦{total_extra}",
            "",
        ]

        if by_tier_sub:
            lines.append("Subscriptions by tier:")
            for t, a in by_tier_sub:
                lines.append(f"• {t.upper()}: ₦{a}")
            lines.append("")

        if by_tier_extra:
            lines.append("Extra signals by tier:")
            for t, a in by_tier_extra:
                lines.append(f"• {t.upper()}: ₦{a}")
            lines.append("")

        if by_plan:
            lines.append("Top plans:")
            for t, days, plan_code, a in by_plan:
                lines.append(f"• {str(t or 'unknown').upper()} / {_plan_label(days, plan_code)}: ₦{int(a or 0)}")
        await update.message.reply_text("\n".join(lines))
    except Exception:
        await update.message.reply_text("Unable to load revenue stats right now.")


async def correct_signal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Owner command to mark a signal as incorrect and notify all recipients.
    
    Usage: /correct_signal <signal_ref> <error_description>
    Example: /correct_signal abc123 Invalid entry level due to data error
    """
    if update.effective_user is None or update.message is None:
        return
    
    if not await _is_strict_owner(update.effective_user.id):
        return
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /correct_signal <signal_ref> <error_description>\n"
            "Example: /correct_signal abc123 Invalid entry level"
        )
        return
    
    signal_ref = context.args[0].strip()
    error_description = " ".join(context.args[1:]).strip()
    
    if not signal_ref or not error_description:
        await update.message.reply_text("❌ Both signal reference and error description are required.")
        return
    
    try:
        from db.session import get_engine_for_event_loop, get_session
        if get_engine_for_event_loop() is None:
            await update.message.reply_text("Postgres not configured.")
            return
        
        from db.models import Signal, SignalDelivery
        from sqlalchemy import select
        from engine.signal_validator import create_signal_correction, notify_signal_correction
        
        async with get_session() as session:
            # Find the signal
            query = select(Signal)
            if len(signal_ref) >= 32:
                query = query.where(Signal.signal_id == signal_ref)
            else:
                query = query.where(Signal.signal_id.like(f"{signal_ref}%"))
            
            query = query.order_by(Signal.created_at.desc()).limit(1)
            result = await session.execute(query)
            signal = result.scalar_one_or_none()
            
            if signal is None:
                await update.message.reply_text(f"❌ Signal not found: {signal_ref}")
                return
            
            # Count deliveries
            delivery_query = select(SignalDelivery).where(
                SignalDelivery.signal_id == signal.signal_id
            )
            delivery_result = await session.execute(delivery_query)
            deliveries = delivery_result.scalars().all()
            delivery_count = len(deliveries)
            
            if delivery_count == 0:
                await update.message.reply_text(
                    f"⚠️ Signal {signal.signal_id[:8]} was never delivered to any users.\n"
                    f"No corrections needed."
                )
                return
            
            # Create correction record
            await create_signal_correction(
                session=session,
                original_signal_id=signal.signal_id,
                error_type="manual_correction",
                error_description=error_description,
                corrected_signal_id=None  # Manual correction, no replacement signal
            )
            
            await session.commit()
        
        # Notify users
        await update.message.reply_text(
            f"⏳ Notifying {delivery_count} users about signal correction..."
        )
        
        from signalrank_telegram.bot import application
        bot = application.bot
        
        notified_count = await notify_signal_correction(
            bot=bot,
            original_signal_id=signal.signal_id,
            error_description=error_description,
            corrected_signal_id=None
        )
        
        await update.message.reply_text(
            f"✅ Signal correction complete:\n"
            f"• Signal: {signal.signal_id[:8]}\n"
            f"• Error: {error_description}\n"
            f"• Users notified: {notified_count}/{delivery_count}"
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        await update.message.reply_text(f"❌ Error correcting signal: {e}")


async def provider_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner command to check health status of data providers."""
    if update.effective_user is None or update.message is None:
        return
    if not await _is_owner(update.effective_user.id):
        await update.message.reply_text("⚠️ Owner access required.")
        return
    
    try:
        import os
        import time
        from data.fetcher import (
            get_unhealthy_providers,
            _PROVIDER_HEALTH,
            _PROVIDER_FAIL_THRESHOLD,
            _PROVIDER_FAIL_WINDOW,
            _PROVIDER_OUTAGE_MINUTES,
            _PROVIDER_OUTAGE_ALERT_INTERVAL_MINUTES,
        )
        from core.circuit_breaker import get_provider_breaker_snapshot
        from datetime import datetime
        
        # Get unhealthy providers
        unhealthy = get_unhealthy_providers(min_minutes=_PROVIDER_OUTAGE_MINUTES)
        
        message = "📊 **Data Provider Status**\n\n"
        
        # Show all tracked providers
        if _PROVIDER_HEALTH:
            message += "**All Providers:**\n"
            for provider, health_info in _PROVIDER_HEALTH.items():
                failures = len(health_info.get('failures', []))
                last_success = health_info.get('last_success', 0)
                
                if last_success > 0:
                    minutes_since_success = int((time.time() - last_success) / 60)
                    success_str = f"{minutes_since_success}m ago"
                else:
                    success_str = "Never"
                
                # Determine status
                if failures == 0:
                    status_emoji = "🟢"
                    status_text = "Healthy"
                elif failures < 3:
                    status_emoji = "🟡"
                    status_text = f"Warning ({failures} fails)"
                else:
                    status_emoji = "🔴"
                    status_text = f"Unhealthy ({failures} fails)"
                
                message += f"{status_emoji} **{provider}**: {status_text}\n"
                message += f"   Last Success: {success_str}\n\n"
        else:
            message += "No provider health data available yet.\n\n"
        
        # Show unhealthy providers summary
        if unhealthy:
            message += f"\n⚠️ **Unhealthy Providers ({len(unhealthy)}):**\n"
            for provider, minutes_down in unhealthy:
                message += f"🔴 {provider}: Down for {minutes_down:.0f} minutes\n"
        else:
            message += "\n✅ All providers healthy (or not yet tracked)\n"

        # Circuit breaker snapshot
        breaker_snapshot = get_provider_breaker_snapshot()
        if breaker_snapshot:
            message += "\n**Circuit Breakers:**\n"
            for name, info in sorted(breaker_snapshot.items(), key=lambda kv: kv[0]):
                open_flag = bool(info.get("open"))
                open_remaining = float(info.get("open_remaining_s") or 0.0)
                failures = int(info.get("failures") or 0)
                failure_threshold = int(info.get("failure_threshold") or 0)
                if open_flag:
                    remaining_s = max(0.0, open_remaining)
                    message += f"🔴 {name}: OPEN {remaining_s:.0f}s (fails {failures}/{failure_threshold})\n"
                else:
                    message += f"🟢 {name}: closed (fails {failures}/{failure_threshold})\n"

        # Backoff tuning snapshot
        def _env_value(key: str, default: str) -> str:
            raw = os.getenv(key)
            return (raw.strip() if raw is not None and str(raw).strip() else str(default))

        message += "\n**Backoff Settings:**\n"
        message += f"- health fail threshold: {_PROVIDER_FAIL_THRESHOLD} in {_PROVIDER_FAIL_WINDOW}s\n"
        message += f"- outage alert: min {_PROVIDER_OUTAGE_MINUTES}m, repeat {_PROVIDER_OUTAGE_ALERT_INTERVAL_MINUTES}m\n"
        message += "- min seconds between calls:\n"
        message += f"  polygon={_env_value('POLYGON_MIN_SECONDS_BETWEEN_CALLS', '12')}s, "
        message += f"twelvedata={_env_value('TWELVEDATA_MIN_SECONDS_BETWEEN_CALLS', '1')}s, "
        message += f"alphavantage={_env_value('ALPHAVANTAGE_MIN_SECONDS_BETWEEN_CALLS', '20')}s\n"
        message += "- rate limit cooldowns:\n"
        message += f"  polygon={_env_value('POLYGON_RATE_LIMIT_COOLDOWN_SECONDS', str(60 * 60))}s, "
        message += f"twelvedata={_env_value('TWELVEDATA_RATE_LIMIT_COOLDOWN_SECONDS', str(12 * 60 * 60))}s, "
        message += f"alphavantage={_env_value('ALPHAVANTAGE_RATE_LIMIT_COOLDOWN_SECONDS', '60')}s\n"
        
        # Add timestamp
        timestamp = now_utc_naive().strftime("%Y-%m-%d %H:%M:%S UTC")
        message += f"\n📅 Checked: {timestamp}"
        
        await update.message.reply_text(message)
    
    except Exception as e:
        await update.message.reply_text(f"Error checking provider status: {str(e)}")


async def qa_report_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin/Owner command: QA report with win rate by tier and asset class."""
    if update.effective_user is None or update.message is None:
        return
    if not await _is_admin_or_owner(update.effective_user.id):
        await update.message.reply_text("⚠️ Admin access required.")
        return

    days = 30
    min_tracked = 0
    for arg in (context.args or []):
        arg_s = str(arg).strip().lower()
        if arg_s.isdigit():
            days = int(arg_s)
        elif arg_s.startswith("min="):
            try:
                min_tracked = int(arg_s.split("=", 1)[-1])
            except Exception:
                pass

    if days <= 0:
        await update.message.reply_text("Usage: /qa_report [days] [min=N]")
        return

    from datetime import datetime, timedelta
    from sqlalchemy import select, func, or_
    from db.models import SignalDelivery, Signal, Outcome
    from data.fetcher import get_asset_type

    cutoff = now_utc_naive() - timedelta(days=int(days))

    win_statuses = {"tp", "tp1", "tp2", "tp3", "partial_tp"}
    loss_statuses = {"sl"}

    stats: dict[tuple[str, str], dict[str, int]] = {}
    total_delivered = 0
    reserved_not_sent = 0
    pending_reserved = 0
    failed_reserved = 0
    stale_reserved = 0

    async with get_session() as session:
        try:
            stale_cutoff = now_utc_naive() - timedelta(minutes=15)
            reserved_res = await session.execute(
                select(func.count(SignalDelivery.id))
                .where(SignalDelivery.delivered_at >= cutoff, SignalDelivery.sent_ok.is_(False))
            )
            reserved_not_sent = int(reserved_res.scalar_one_or_none() or 0)

            pending_res = await session.execute(
                select(func.count(SignalDelivery.id)).where(
                    SignalDelivery.delivered_at >= cutoff,
                    SignalDelivery.sent_ok.is_(False),
                    SignalDelivery.last_error.is_(None),
                    SignalDelivery.last_attempt_at >= stale_cutoff,
                )
            )
            pending_reserved = int(pending_res.scalar_one_or_none() or 0)

            failed_res = await session.execute(
                select(func.count(SignalDelivery.id)).where(
                    SignalDelivery.delivered_at >= cutoff,
                    SignalDelivery.sent_ok.is_(False),
                    SignalDelivery.last_error.is_not(None),
                )
            )
            failed_reserved = int(failed_res.scalar_one_or_none() or 0)

            stale_res = await session.execute(
                select(func.count(SignalDelivery.id)).where(
                    SignalDelivery.delivered_at >= cutoff,
                    SignalDelivery.sent_ok.is_(False),
                    SignalDelivery.last_error.is_(None),
                    or_(
                        SignalDelivery.last_attempt_at.is_(None),
                        SignalDelivery.last_attempt_at < stale_cutoff,
                    ),
                )
            )
            stale_reserved = int(stale_res.scalar_one_or_none() or 0)
        except Exception:
            reserved_not_sent = 0
            pending_reserved = failed_reserved = stale_reserved = 0

        totals_res = await session.execute(
            select(
                SignalDelivery.tier_at_send,
                Signal.asset,
                func.count(SignalDelivery.id),
            )
            .select_from(SignalDelivery)
            .join(Signal, Signal.signal_id == SignalDelivery.signal_id)
            .where(SignalDelivery.delivered_at >= cutoff, SignalDelivery.sent_ok.is_(True))
            .group_by(SignalDelivery.tier_at_send, Signal.asset)
        )
        totals_rows = totals_res.all() or []
        for tier_at_send, asset, count in totals_rows:
            tier = str(tier_at_send or "free").split("_", 1)[0].strip().upper()
            asset_class = str(get_asset_type(asset)).lower()
            key = (tier, asset_class)
            stats.setdefault(key, {"signals": 0, "wins": 0, "losses": 0})
            stats[key]["signals"] += int(count or 0)
            total_delivered += int(count or 0)

        outcomes_res = await session.execute(
            select(
                SignalDelivery.tier_at_send,
                Signal.asset,
                Outcome.status,
                func.count(Outcome.id),
            )
            .select_from(SignalDelivery)
            .join(Signal, Signal.signal_id == SignalDelivery.signal_id)
            .join(Outcome, Outcome.signal_id == Signal.signal_id)
            .where(SignalDelivery.delivered_at >= cutoff, SignalDelivery.sent_ok.is_(True))
            .group_by(SignalDelivery.tier_at_send, Signal.asset, Outcome.status)
        )
        outcomes_rows = outcomes_res.all() or []
        for tier_at_send, asset, status, count in outcomes_rows:
            tier = str(tier_at_send or "free").split("_", 1)[0].strip().upper()
            asset_class = str(get_asset_type(asset)).lower()
            key = (tier, asset_class)
            stats.setdefault(key, {"signals": 0, "wins": 0, "losses": 0})
            status_l = str(status or "").strip().lower()
            if status_l in win_statuses:
                stats[key]["wins"] += int(count or 0)
            elif status_l in loss_statuses:
                stats[key]["losses"] += int(count or 0)

    if not stats:
        await update.message.reply_text(f"QA report: no deliveries in last {days} days.")
        return

    total_tracked = sum((v.get("wins", 0) + v.get("losses", 0)) for v in stats.values())
    coverage_pct = (total_tracked / total_delivered * 100.0) if total_delivered > 0 else 0.0
    tier_order = {"FREE": 0, "PREMIUM": 1, "VIP": 2, "ADMIN": 3, "OWNER": 4}
    asset_order = {"crypto": 0, "fx": 1, "stock": 2, "commodity": 3}

    tiers_present = sorted({k[0] for k in stats.keys()}, key=lambda t: tier_order.get(t, 99))
    lines = [
        f"QA report (last {days}d)",
        f"Delivered: {total_delivered}, tracked: {total_tracked}, coverage: {coverage_pct:.1f}%",
    ]
    if reserved_not_sent:
        lines.append(
            "Reserved but not confirmed sent: "
            f"{reserved_not_sent} (pending={pending_reserved}, failed={failed_reserved}, stale={stale_reserved})"
        )

    for tier in tiers_present:
        tier_lines = []
        for (t, asset_class), data in sorted(
            stats.items(), key=lambda kv: (tier_order.get(kv[0][0], 99), asset_order.get(kv[0][1], 99))
        ):
            if t != tier:
                continue
            wins = int(data.get("wins") or 0)
            losses = int(data.get("losses") or 0)
            signals = int(data.get("signals") or 0)
            tracked = wins + losses
            if tracked < int(min_tracked or 0) and tracked > 0:
                continue
            if tracked == 0 and signals == 0:
                continue
            if tracked == 0:
                tier_lines.append(f"- {asset_class}: {signals} delivered, outcomes pending")
            else:
                win_rate = (wins / tracked) * 100.0 if tracked > 0 else 0.0
                tier_lines.append(
                    f"- {asset_class}: win {win_rate:.1f}% ({wins}W/{losses}L), tracked={tracked}, delivered={signals}"
                )

        if tier_lines:
            lines.append("")
            lines.append(f"{tier}:")
            lines.extend(tier_lines)

    lines.append("")
    lines.append("Notes: wins=tp/tp1/tp2/tp3/partial_tp; losses=sl")
    if total_delivered > 0 and coverage_pct < 80.0:
        lines.append(
            "Coverage warning: tracked outcomes are too sparse for a reliable expected win-rate estimate."
        )
    await update.message.reply_text("\n".join(lines))



async def outcome_rebuild_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner-only bounded outcome projection and notification-outbox recovery."""
    if update.effective_user is None or update.message is None:
        return
    if not await _is_strict_owner(int(update.effective_user.id)):
        await update.message.reply_text("⛔ Strict owner access required.")
        return
    action = str(context.args[0] if context.args else "status").strip().lower()
    if action not in {"dry_run", "apply", "status"}:
        await update.message.reply_text("Usage: /outcome_rebuild dry_run | apply | status")
        return

    from services.outcome_reconciliation import (
        ensure_outcome_projections,
        outcome_projection_health,
        repair_outcome_notification_outbox,
    )
    if action == "status":
        async with get_session() as session:
            health = await outcome_projection_health(session, days=30)
        await update.message.reply_text(
            "Outcome recovery status\n"
            f"{json.dumps(health, sort_keys=True, default=str)}"
        )
        return

    # Phase 1: canonical outcome recovery.
    async with get_session(
        label="owner.outcome_rebuild_projection"
    ) as session:
        result = await ensure_outcome_projections(
            session,
            queue_notifications=False,
        )

        if action == "apply":
            await session.commit()
        else:
            await session.rollback()

    # Phase 2: notification-outbox recovery.
    # Failure here cannot roll back canonical Outcome repairs.
    async with get_session(
        label="owner.outcome_rebuild_outbox"
    ) as session:
        outbox = await repair_outcome_notification_outbox(
            session,
            limit=500,
        )

        if action == "apply":
            await session.commit()
        else:
            await session.rollback()
    await update.message.reply_text(
        f"Outcome recovery {action} completed.\n"
        f"projection={json.dumps(result.as_dict(), sort_keys=True)}\n"
        f"outbox={json.dumps(outbox.as_dict(), sort_keys=True)}\n"
        + (
            "Changes committed; the front door will drain pending notifications."
            if action == "apply"
            else "Dry run rolled back; no database changes were retained."
        )
    )


async def outcome_audit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner-only outcome projection/outbox readiness audit."""
    if update.effective_user is None or update.message is None:
        return
    if not await _is_strict_owner(int(update.effective_user.id)):
        await update.message.reply_text("⛔ Strict owner access required.")
        return
    days = 30
    if context.args:
        try:
            days = max(1, min(3650, int(context.args[0])))
        except Exception:
            await update.message.reply_text("Usage: /outcome_audit [days]")
            return

    from sqlalchemy import func, select
    from db.models import OutcomeNotification
    from services.outcome_reconciliation import outcome_projection_health

    async with get_session() as session:
        health = await outcome_projection_health(session, days=days)
        rows = (await session.execute(
            select(OutcomeNotification.delivery_state, func.count(OutcomeNotification.id))
            .group_by(OutcomeNotification.delivery_state)
        )).all()
    outbox = {str(state_name or "unknown"): int(count or 0) for state_name, count in rows}
    blocked = int(outbox.get("failed", 0)) > 0 or int(outbox.get("sending", 0)) > 0
    verdict = "PASS" if health.get("ok") and not blocked else "BLOCKED"
    await update.message.reply_text(
        f"Outcome delivery audit: {verdict}\n"
        f"projection={json.dumps(health, sort_keys=True, default=str)}\n"
        f"outbox={json.dumps(outbox, sort_keys=True)}"
    )


async def performance_rebuild_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner-only bounded performance projection rebuild and dry-run."""
    if update.effective_user is None or update.message is None:
        return
    if not await _is_strict_owner(int(update.effective_user.id)):
        await update.message.reply_text("⛔ Strict owner access required.")
        return
    action = str(context.args[0] if context.args else "status").strip().lower()
    if action not in {"dry_run", "apply", "status"}:
        await update.message.reply_text(
            "Usage: /performance_rebuild dry_run | apply | status"
        )
        return
    from core.env import runtime_environment_name
    from services.performance_ledger import (
        performance_ledger_health,
        reconcile_all_performance_ledgers,
        persist_performance_reconciliation_result,
    )
    env = str(runtime_environment_name("development") or "development").lower()
    status_key = f"performance_reconciliation:status:{env}"
    if action == "status":
        raw = await __import__("asyncio").to_thread(state.get_sync, status_key)
        async with get_session() as session:
            health = await performance_ledger_health(session, environment=env)
        await update.message.reply_text(
            "Performance rebuild status\n"
            f"environment={env}\n"
            f"last_batch={raw or 'none'}\n"
            f"health={json.dumps(health, sort_keys=True, default=str)}"
        )
        return

    # Keep owner commands bounded. The worker continues cursor-based projection
    # on later cycles, so this does not load the full population into one request.
    limit = max(1, min(500, int(getattr(config, "PERFORMANCE_OWNER_REBUILD_LIMIT", 100) or 100)))
    async with get_session() as session:
        result = await reconcile_all_performance_ledgers(
            session,
            environment=env,
            limit_users=limit,
            dry_run=(action == "dry_run"),
            reset_cursor=True,
            persist_cursor=(action == "apply"),
            wrap_cursor=False,
        )
        if action == "apply":
            await session.commit()
            await persist_performance_reconciliation_result(
                result, environment=env, persist_cursor=True
            )
        else:
            await session.rollback()
            await persist_performance_reconciliation_result(
                result, environment=env, persist_cursor=False
            )
    await update.message.reply_text(
        f"Performance rebuild {action} completed for one bounded batch.\n"
        f"{json.dumps(result.as_dict(), sort_keys=True)}\n"
        "The worker will continue from the saved cursor after apply."
    )


async def performance_audit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner-only production-readiness audit for the proof-backed ledger."""
    if update.effective_user is None or update.message is None:
        return
    if not await _is_strict_owner(int(update.effective_user.id)):
        await update.message.reply_text("⛔ Strict owner access required.")
        return
    from core.env import runtime_environment_name
    from services.performance_ledger import performance_ledger_health
    days = 30
    if context.args:
        try:
            days = max(1, min(3650, int(context.args[0])))
        except Exception:
            await update.message.reply_text("Usage: /performance_audit [days]")
            return
    env = str(runtime_environment_name("development") or "development").lower()
    async with get_session() as session:
        health = await performance_ledger_health(session, days=days, environment=env)
    verdict = "PASS" if health.get("ok") else "BLOCKED"
    await update.message.reply_text(
        f"Performance ledger audit: {verdict}\n"
        f"{json.dumps(health, sort_keys=True, default=str)}"
    )


_OWNER_JOB_PREFIX = "owner_job:"
_OWNER_JOB_TASKS: dict[str, object] = {}


def _owner_job_key(job_id: str) -> str:
    return f"{_OWNER_JOB_PREFIX}{str(job_id).strip()}"


async def _owner_audit_event(event_type: str, actor_telegram_user_id: int, details: dict) -> None:
    try:
        from db.models import AdminEvent

        async with get_session() as session:
            session.add(
                AdminEvent(
                    event_type=str(event_type)[:64],
                    actor_telegram_user_id=int(actor_telegram_user_id),
                    details=dict(details or {}),
                )
            )
            await session.commit()
    except Exception:
        _owner_logger.exception("[owner_commands] failed to write admin event")


async def _owner_set_job_record(job_id: str, payload: dict) -> None:
    import asyncio

    payload = dict(payload or {})
    payload["job_id"] = str(job_id)
    payload.setdefault("updated_at", now_utc_naive().isoformat())
    _OWNER_JOB_TASKS[str(job_id)] = payload
    try:
        await asyncio.to_thread(state.set_sync, _owner_job_key(job_id), json.dumps(payload, sort_keys=True))
    except Exception:
        _owner_logger.exception("[owner_commands] failed to persist owner job record")


async def _owner_get_job_record(job_id: str) -> dict | None:
    import asyncio

    key = str(job_id).strip()
    cached = _OWNER_JOB_TASKS.get(key)
    if isinstance(cached, dict):
        return dict(cached)
    try:
        raw = await asyncio.to_thread(state.get_sync, _owner_job_key(key))
        if not raw:
            return None
        data = json.loads(raw)
        if isinstance(data, dict):
            _OWNER_JOB_TASKS[key] = dict(data)
            return dict(data)
    except Exception:
        _owner_logger.exception("[owner_commands] failed to load owner job record")
    return None


async def _start_owner_job(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    command_name: str,
    summary: str,
    runner,
) -> str:
    import asyncio

    if update.effective_user is None or update.message is None:
        return ""
    actor_id = int(update.effective_user.id)
    job_id = uuid4().hex
    created_at = now_utc_naive().isoformat()
    await _owner_set_job_record(
        job_id,
        {
            "command": str(command_name),
            "summary": str(summary),
            "status": "queued",
            "created_at": created_at,
            "updated_at": created_at,
            "actor_telegram_user_id": actor_id,
        },
    )
    await _owner_audit_event(
        "owner_command_job_queued",
        actor_id,
        {"command": str(command_name), "job_id": job_id, "summary": str(summary)},
    )

    async def _run() -> None:
        started = now_utc_naive().isoformat()
        await _owner_set_job_record(
            job_id,
            {
                "command": str(command_name),
                "summary": str(summary),
                "status": "running",
                "created_at": created_at,
                "started_at": started,
                "updated_at": started,
                "actor_telegram_user_id": actor_id,
            },
        )
        try:
            result = await runner()
            finished = now_utc_naive().isoformat()
            await _owner_set_job_record(
                job_id,
                {
                    "command": str(command_name),
                    "summary": str(summary),
                    "status": "completed",
                    "created_at": created_at,
                    "started_at": started,
                    "finished_at": finished,
                    "updated_at": finished,
                    "actor_telegram_user_id": actor_id,
                    "result": result,
                },
            )
            await _owner_audit_event(
                "owner_command_job_completed",
                actor_id,
                {"command": str(command_name), "job_id": job_id, "result": result},
            )
        except Exception as exc:
            finished = now_utc_naive().isoformat()
            message = str(exc).strip() or exc.__class__.__name__
            await _owner_set_job_record(
                job_id,
                {
                    "command": str(command_name),
                    "summary": str(summary),
                    "status": "failed",
                    "created_at": created_at,
                    "started_at": started,
                    "finished_at": finished,
                    "updated_at": finished,
                    "actor_telegram_user_id": actor_id,
                    "error": f"{exc.__class__.__name__}: {message}",
                },
            )
            await _owner_audit_event(
                "owner_command_job_failed",
                actor_id,
                {
                    "command": str(command_name),
                    "job_id": job_id,
                    "error_class": exc.__class__.__name__,
                    "error": message[:400],
                },
            )

    asyncio.create_task(_run())
    await update.message.reply_text(
        f"Accepted `{command_name}`. Job queued.\njob_id={job_id}\nUse /queue_status {job_id}",
        parse_mode="Markdown",
    )
    return job_id


async def dedup_audit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner-only dedup and same-asset lock audit."""
    if update.effective_user is None or update.message is None:
        return
    if not await _is_strict_owner(int(update.effective_user.id)):
        await update.message.reply_text("⛔ Strict owner access required.")
        return
    days = 30
    if context.args:
        try:
            days = max(1, min(3650, int(context.args[0])))
        except Exception:
            await update.message.reply_text("Usage: /dedup_audit [days]")
            return

    from sqlalchemy import func, select
    from db.models import PerformanceLedgerEntry, SignalDelivery
    from services.asset_repeat_policy import get_asset_repeat_lock_hours
    from services.performance_ledger import performance_ledger_health

    async with get_session() as session:
        health = await performance_ledger_health(session, days=days)
        duplicate_excluded = int(
            (
                await session.execute(
                    select(func.count(PerformanceLedgerEntry.ledger_id)).where(
                        PerformanceLedgerEntry.primary_bucket == "DUPLICATE_EXCLUDED"
                    )
                )
            ).scalar_one()
            or 0
        )
        unresolved_delivery_rows = int(
            (
                await session.execute(
                    select(func.count(SignalDelivery.id)).where(
                        SignalDelivery.sent_ok.is_(False),
                        func.lower(func.coalesce(SignalDelivery.delivery_state, ""))
                        .in_(("reserved", "sending")),
                    )
                )
            ).scalar_one()
            or 0
        )

    lock_hours = float(get_asset_repeat_lock_hours("owner"))
    verdict = "PASS" if lock_hours >= 4.0 and duplicate_excluded >= 0 else "BLOCKED"
    await update.message.reply_text(
        "Dedup audit\n"
        f"verdict={verdict}\n"
        f"same_asset_lock_hours={lock_hours:.2f}\n"
        f"duplicate_excluded={duplicate_excluded}\n"
        f"unresolved_delivery_rows={unresolved_delivery_rows}\n"
        f"projection_health={json.dumps(health, sort_keys=True, default=str)}"
    )


async def notification_audit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner-only outcome notification queue audit."""
    if update.effective_user is None or update.message is None:
        return
    if not await _is_strict_owner(int(update.effective_user.id)):
        await update.message.reply_text("⛔ Strict owner access required.")
        return

    from sqlalchemy import func, select
    from db.models import OutcomeNotification, SignalDelivery

    async with get_session() as session:
        state_rows = (
            await session.execute(
                select(OutcomeNotification.delivery_state, func.count(OutcomeNotification.id)).group_by(
                    OutcomeNotification.delivery_state
                )
            )
        ).all()
        duplicate_attempts = int(
            (
                await session.execute(
                    select(func.count(OutcomeNotification.id)).where(OutcomeNotification.attempt_count > 1)
                )
            ).scalar_one()
            or 0
        )
        missing_message_proof = int(
            (
                await session.execute(
                    select(func.count(SignalDelivery.id)).where(
                        SignalDelivery.sent_ok.is_(True),
                        SignalDelivery.telegram_message_id.is_(None),
                    )
                )
            ).scalar_one()
            or 0
        )

    states = {str(name or "unknown"): int(count or 0) for name, count in state_rows}
    await update.message.reply_text(
        "Notification audit\n"
        f"states={json.dumps(states, sort_keys=True)}\n"
        f"duplicate_attempt_rows={duplicate_attempts}\n"
        f"missing_delivery_proof_rows={missing_message_proof}"
    )


async def paper_audit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner-only paper-trading integrity audit."""
    if update.effective_user is None or update.message is None:
        return
    if not await _is_strict_owner(int(update.effective_user.id)):
        await update.message.reply_text("⛔ Strict owner access required.")
        return

    from sqlalchemy import func, select
    from db.models import PaperAccount, PaperLedgerEntry, PaperPosition, PaperTradeAttempt

    async with get_session() as session:
        accounts = int((await session.execute(select(func.count(PaperAccount.id)))).scalar_one() or 0)
        open_positions = int(
            (
                await session.execute(
                    select(func.count(PaperPosition.position_id)).where(
                        func.lower(PaperPosition.status) == "open"
                    )
                )
            ).scalar_one()
            or 0
        )
        closed_positions = int(
            (
                await session.execute(
                    select(func.count(PaperPosition.position_id)).where(
                        func.lower(PaperPosition.status) == "closed"
                    )
                )
            ).scalar_one()
            or 0
        )
        attempts = int((await session.execute(select(func.count(PaperTradeAttempt.id)))).scalar_one() or 0)
        skipped_attempts = int(
            (
                await session.execute(
                    select(func.count(PaperTradeAttempt.id)).where(
                        func.lower(PaperTradeAttempt.decision).in_(("skip", "rejected", "retry"))
                    )
                )
            ).scalar_one()
            or 0
        )
        ledger_rows = int((await session.execute(select(func.count(PaperLedgerEntry.id)))).scalar_one() or 0)

    await update.message.reply_text(
        "Paper audit\n"
        f"accounts={accounts}\n"
        f"open_positions={open_positions}\n"
        f"closed_positions={closed_positions}\n"
        f"trade_attempts={attempts}\n"
        f"skipped_or_retry_attempts={skipped_attempts}\n"
        f"ledger_rows={ledger_rows}"
    )


async def queue_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner-only owner-job and reconciliation queue status."""
    if update.effective_user is None or update.message is None:
        return
    if not await _is_strict_owner(int(update.effective_user.id)):
        await update.message.reply_text("⛔ Strict owner access required.")
        return

    if context.args:
        job = await _owner_get_job_record(str(context.args[0]))
        if not job:
            await update.message.reply_text("Job not found.")
            return
        await update.message.reply_text(json.dumps(job, sort_keys=True, default=str))
        return

    import asyncio
    from core.env import runtime_environment_name

    env = str(runtime_environment_name("development") or "development").lower()
    retry_key = f"performance_reconciliation:retry:{env}"
    dlq_key = f"performance_reconciliation:dlq:{env}"
    status_key = f"performance_reconciliation:status:{env}"
    retry_raw = await asyncio.to_thread(state.get_sync, retry_key)
    dlq_raw = await asyncio.to_thread(state.get_sync, dlq_key)
    status_raw = await asyncio.to_thread(state.get_sync, status_key)
    retry_items = json.loads(retry_raw) if retry_raw else []
    dlq_items = json.loads(dlq_raw) if dlq_raw else []
    status = json.loads(status_raw) if status_raw else {}
    owner_jobs = [v for v in _OWNER_JOB_TASKS.values() if isinstance(v, dict)]
    running = sum(1 for item in owner_jobs if str(item.get("status")) == "running")
    queued = sum(1 for item in owner_jobs if str(item.get("status")) == "queued")

    await update.message.reply_text(
        "Queue status\n"
        f"owner_jobs_total={len(owner_jobs)} queued={queued} running={running}\n"
        f"performance_retry_queue={len(retry_items)}\n"
        f"performance_dead_letter={len(dlq_items)}\n"
        f"last_performance_batch={json.dumps(status, sort_keys=True, default=str)}"
    )


async def queue_replay_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner-only replay request for bounded reconciliation queues."""
    if update.effective_user is None or update.message is None:
        return
    if not await _is_strict_owner(int(update.effective_user.id)):
        await update.message.reply_text("⛔ Strict owner access required.")
        return

    target = str(context.args[0] if context.args else "performance").strip().lower()
    if target not in {"performance", "all"}:
        await update.message.reply_text("Usage: /queue_replay [performance|all]")
        return

    async def _runner() -> dict:
        from core.env import runtime_environment_name
        from services.performance_ledger import (
            reconcile_all_performance_ledgers,
            persist_performance_reconciliation_result,
        )

        env = str(runtime_environment_name("development") or "development").lower()
        async with get_session() as session:
            result = await reconcile_all_performance_ledgers(
                session,
                environment=env,
                dry_run=False,
                reset_cursor=False,
                persist_cursor=True,
                wrap_cursor=False,
            )
            await session.commit()
        await persist_performance_reconciliation_result(result, environment=env, persist_cursor=True)
        return {"target": target, "result": result.as_dict()}

    await _start_owner_job(
        update,
        context,
        command_name="queue_replay",
        summary=f"Replay {target} queue",
        runner=_runner,
    )


async def dead_letter_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner-only dead-letter visibility for reconciliation queues."""
    if update.effective_user is None or update.message is None:
        return
    if not await _is_strict_owner(int(update.effective_user.id)):
        await update.message.reply_text("⛔ Strict owner access required.")
        return

    import asyncio
    from core.env import runtime_environment_name

    env = str(runtime_environment_name("development") or "development").lower()
    dlq_key = f"performance_reconciliation:dlq:{env}"
    raw = await asyncio.to_thread(state.get_sync, dlq_key)
    items = json.loads(raw) if raw else []
    sample = items[-5:]
    await update.message.reply_text(
        "Dead-letter status\n"
        f"environment={env}\n"
        f"count={len(items)}\n"
        f"sample={json.dumps(sample, sort_keys=True, default=str)}"
    )


async def dead_letter_replay_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner-only replay of dead-letter items back to retry queue."""
    if update.effective_user is None or update.message is None:
        return
    if not await _is_strict_owner(int(update.effective_user.id)):
        await update.message.reply_text("⛔ Strict owner access required.")
        return

    import asyncio
    from core.env import runtime_environment_name

    env = str(runtime_environment_name("development") or "development").lower()
    dlq_key = f"performance_reconciliation:dlq:{env}"
    retry_key = f"performance_reconciliation:retry:{env}"

    dlq_raw = await asyncio.to_thread(state.get_sync, dlq_key)
    retry_raw = await asyncio.to_thread(state.get_sync, retry_key)
    dlq_items = json.loads(dlq_raw) if dlq_raw else []
    retry_items = json.loads(retry_raw) if retry_raw else []
    moved = 0
    for item in dlq_items:
        if not isinstance(item, dict):
            continue
        retry_items.append(
            {
                "internal_user_id": int(item.get("internal_user_id") or 0),
                "telegram_user_id": int(item.get("telegram_user_id") or 0),
                "attempts": 1,
                "last_error_code": str(item.get("last_error_code") or "replay"),
                "last_failed_at": now_utc_naive().isoformat(),
            }
        )
        moved += 1

    await asyncio.to_thread(state.set_sync, retry_key, json.dumps(retry_items, sort_keys=True))
    await asyncio.to_thread(state.set_sync, dlq_key, json.dumps([], sort_keys=True))
    await update.message.reply_text(f"Dead-letter replay queued. moved={moved}")


async def ledger_audit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner-only performance ledger consistency audit."""
    if update.effective_user is None or update.message is None:
        return
    if not await _is_strict_owner(int(update.effective_user.id)):
        await update.message.reply_text("⛔ Strict owner access required.")
        return
    days = 30
    if context.args:
        try:
            days = max(1, min(3650, int(context.args[0])))
        except Exception:
            await update.message.reply_text("Usage: /ledger_audit [days]")
            return

    from services.performance_ledger import performance_ledger_health

    async with get_session() as session:
        health = await performance_ledger_health(session, days=days)
    verdict = "PASS" if bool(health.get("ok")) else "BLOCKED"
    await update.message.reply_text(
        f"Ledger audit: {verdict}\n{json.dumps(health, sort_keys=True, default=str)}"
    )


async def payment_reconcile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner-only payment receipt/webhook reconciliation summary."""
    if update.effective_user is None or update.message is None:
        return
    if not await _is_strict_owner(int(update.effective_user.id)):
        await update.message.reply_text("⛔ Strict owner access required.")
        return

    from sqlalchemy import func, select
    from db.models import PaymentEvent, PaymentReceipt, ProcessedWebhookEvent

    async with get_session() as session:
        event_count = int((await session.execute(select(func.count(PaymentEvent.id)))).scalar_one() or 0)
        receipt_count = int((await session.execute(select(func.count(PaymentReceipt.id)))).scalar_one() or 0)
        pending_hooks = int(
            (
                await session.execute(
                    select(func.count(ProcessedWebhookEvent.id)).where(
                        func.lower(ProcessedWebhookEvent.status).in_(("pending", "failed"))
                    )
                )
            ).scalar_one()
            or 0
        )

    await update.message.reply_text(
        "Payment reconcile\n"
        f"payment_events={event_count}\n"
        f"payment_receipts={receipt_count}\n"
        f"pending_or_failed_webhooks={pending_hooks}\n"
        f"receipt_gap={max(0, event_count - receipt_count)}"
    )


async def system_health_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner/admin system health summary command."""
    if update.effective_user is None or update.message is None:
        return
    if not await _is_admin_or_owner(int(update.effective_user.id)):
        await update.message.reply_text("⛔ Admin or owner access required.")
        return

    import asyncio
    from core.env import financial_feature_flags

    kill_switch = await state.get_killswitch()
    flags = financial_feature_flags()
    redis_ok = True
    try:
        await asyncio.to_thread(state.set_sync, "owner:health:probe", "ok")
        _ = await asyncio.to_thread(state.get_sync, "owner:health:probe")
    except Exception:
        redis_ok = False

    db_ok = True
    db_error = ""
    try:
        async with get_session() as session:
            from sqlalchemy import text

            await session.execute(text("SELECT 1"))
    except Exception as exc:
        db_ok = False
        db_error = f"{exc.__class__.__name__}: {str(exc)[:200]}"

    await update.message.reply_text(
        "System health\n"
        f"db_ok={db_ok}\n"
        f"redis_ok={redis_ok}\n"
        f"kill_switch={bool(getattr(kill_switch, 'enabled', True))}\n"
        f"financial_flags={json.dumps(flags, sort_keys=True)}\n"
        f"db_error={db_error or 'none'}"
    )


async def release_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner/admin release status summary."""
    if update.effective_user is None or update.message is None:
        return
    if not await _is_admin_or_owner(int(update.effective_user.id)):
        await update.message.reply_text("⛔ Admin or owner access required.")
        return

    import os

    fingerprint = "unknown"
    try:
        with open("RELEASE_FINGERPRINT.txt", "r", encoding="utf-8") as handle:
            fingerprint = handle.read().strip()
    except Exception:
        pass
    release_env = str(os.getenv("RELEASE_VERSION") or os.getenv("APP_VERSION") or "not_set")
    await update.message.reply_text(
        "Release status\n"
        f"fingerprint={fingerprint or 'unknown'}\n"
        f"release_env={release_env}\n"
        f"runtime={str(os.getenv('RAILWAY_ENVIRONMENT') or os.getenv('ENV') or 'development')}"
    )


async def kill_switch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner-only emergency kill-switch controller."""
    if update.effective_user is None or update.message is None:
        return
    if not await _is_strict_owner(int(update.effective_user.id)):
        await update.message.reply_text("⛔ Strict owner access required.")
        return

    action = str(context.args[0] if context.args else "status").strip().lower()
    if action not in {"status", "on", "off"}:
        await update.message.reply_text("Usage: /kill_switch [status|on|off]")
        return

    if action == "on":
        await state.set_killswitch(True, reason="owner_command_kill_switch")
        await _owner_audit_event(
            "kill_switch_on",
            int(update.effective_user.id),
            {"source": "owner_command"},
        )
    elif action == "off":
        await state.set_killswitch(False, reason="owner_command_release")
        await _owner_audit_event(
            "kill_switch_off",
            int(update.effective_user.id),
            {"source": "owner_command"},
        )

    status = await state.get_killswitch()
    await update.message.reply_text(
        "Kill switch\n"
        f"enabled={bool(getattr(status, 'enabled', True))}\n"
        f"reason={str(getattr(status, 'reason', '') or 'none')}"
    )
