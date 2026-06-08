from utils.async_runner import run_sync
import threading
from core.redis_state import state, mark_signal_delivered_sync
from core.telemetry import observe_signal_dispatch
from apscheduler.schedulers.background import BackgroundScheduler

def resend_unsent_signals_job():
    """Scheduled job: resend top-scored unsent signals to eligible users.

    Signals are capped to the top-20 by score from the last 24 h to avoid flooding.
    Uses run_sync() so the global async engine is re-used correctly whether or not
    an event loop is already running in the calling thread.
    """
    # Pre-flight: make sure the global async engine is initialised.  This is a
    # no-op when run_bot() has already set it up, but guards against edge cases
    # where the job fires before the main startup path completes.
    try:
        from db.session import _get_global_engine
        if _get_global_engine() is None:
            logger.warning("[resend] DB engine not initialised — skipping job")
            return
    except Exception as _pre_err:
        logger.warning("[resend] DB engine pre-flight failed: %s", _pre_err)
        return
    _lock_conn = None
    try:
        # Cluster-safe lock (Postgres advisory lock): prevents duplicate resend
        # runs across multiple Railway instances when Redis is unavailable.
        import os
        import psycopg2
        try:
            from config import resolve_database_url
            _dsn = resolve_database_url(async_driver=False) or ""
        except Exception:
            _dsn = ""

        if _dsn:
            _lock_id = int(os.getenv("RESEND_JOB_LOCK_ID", "739206"))
            _lock_conn = psycopg2.connect(_dsn, connect_timeout=5)
            _lock_conn.autocommit = True
            with _lock_conn.cursor() as _cur:
                _cur.execute("SELECT pg_try_advisory_lock(%s)", (_lock_id,))
                _locked = bool((_cur.fetchone() or [False])[0])
            if not _locked:
                logger.info("[resend] skipped: another instance holds advisory lock")
                try:
                    _lock_conn.close()
                except Exception:
                    pass
                return
    except Exception as _lock_err:
        logger.debug(f"[resend] advisory lock unavailable, continuing without lock: {_lock_err}")

    try:
        run_sync(_resend_unsent_signals_async())
    except Exception:
        logger.exception("[resend] resend_unsent_signals_job failed")
    finally:
        if _lock_conn is not None:
            try:
                _lock_conn.close()
            except Exception:
                pass


async def _resend_unsent_signals_async():
    """Async core of the resend job — all deliveries share one event loop / Bot instance."""
    try:
        from db.session import get_session
        from db.pg_features import (
            list_active_signals,
            get_signal_outcome_status,
            record_signal_delivery,
            mark_signal_delivery_result,
        )
        from signalrank_telegram.tier_delivery import TierDeliveryManager
        from signalrank_telegram.access import resolve_user_tier
        from .formatter import format_signal
        import asyncio

        delivery_mgr = TierDeliveryManager()

        # Fetch user IDs with a direct async call — avoids calling
        # get_all_user_ids_compat() (which uses run_sync() internally and would
        # spawn a nested thread+event-loop inside the already-running loop).
        from db.pg_features import list_all_user_telegram_ids
        async with get_session() as _uid_session:
            user_ids = await list_all_user_telegram_ids(_uid_session)
        # Always include configured owner/admin IDs as a fallback audience,
        # even if user rows are missing in DB due onboarding races.
        try:
            from config import OWNER_IDS, ADMIN_IDS
            _fallback_ids = set(int(x) for x in (OWNER_IDS or set())) | set(int(x) for x in (ADMIN_IDS or set()))
            if _fallback_ids:
                user_ids = list(user_ids or []) + sorted(_fallback_ids)
        except Exception:
            pass
        # Defensive dedupe: malformed joins or legacy rows can surface duplicates.
        try:
            user_ids = sorted({int(uid) for uid in (user_ids or [])})
        except Exception:
            user_ids = list(user_ids or [])

        if not user_ids:
            logger.warning("[resend] audience empty: no user IDs found (DB + OWNER_IDS/ADMIN_IDS)")
            return

        # Cache user tiers once per run for consistent routing and diagnostics.
        user_tier_map: dict[int, str] = {}
        tier_counts: dict[str, int] = {}
        include_free_in_resend = str(
            os.getenv("RESEND_INCLUDE_FREE", "1") or "1"
        ).strip().lower() in {"1", "true", "yes", "on"}
        for _uid in user_ids:
            try:
                _tier = str(resolve_user_tier(int(_uid)) or "free").lower()
            except Exception:
                _tier = "free"
            user_tier_map[int(_uid)] = _tier
            tier_counts[_tier] = int(tier_counts.get(_tier, 0) or 0) + 1
        try:
            logger.info(f"[resend] audience users={len(user_ids)} tiers={tier_counts}")
        except Exception:
            pass

        # Fetch signals from the last 24 h, limit 100 rows, then rank by score
        async with get_session() as session:
            try:
                raw_signals = await list_active_signals(session, max_age_days=1, limit=100)
                await session.commit()
            except Exception:
                raw_signals = []

        if not raw_signals:
            logger.info("[resend] no active signals found in last 24h")
            return

        resend_min_score = float(os.getenv("RESEND_MIN_SCORE", "75") or 75)
        resend_max_signals = int(os.getenv("RESEND_MAX_SIGNALS", "8") or 8)

        # Keep highest-quality signals only to avoid flooding users.
        ranked = sorted(
            raw_signals,
            key=lambda s: float(getattr(s, 'score', 0) or 0),
            reverse=True,
        )

        # De-duplicate by asset+timeframe and enforce quality floor.
        best_by_bucket = {}
        for s in ranked:
            try:
                if float(getattr(s, 'score', 0) or 0) < resend_min_score:
                    continue
                bucket = f"{str(getattr(s, 'asset', '')).upper()}_{str(getattr(s, 'timeframe', '')).lower()}"
                if not bucket.strip("_"):
                    continue
                if bucket not in best_by_bucket:
                    best_by_bucket[bucket] = s
            except Exception:
                continue

        signals = list(best_by_bucket.values())[:max(1, resend_max_signals)]

        if not signals:
            logger.info(
                "[resend] no signals passed quality filters (min_score=%s, max_signals=%s)",
                resend_min_score,
                resend_max_signals,
            )
            return

        delivered_count = 0
        failed_count = 0
        skipped_eligibility_count = 0
        skipped_already_delivered_count = 0

        # Single Bot instance, properly initialised — avoids shared-httpx-client races
        bot = Bot(token=_require_telegram_token())
        async with bot:
            for sig in signals:
                signal_id = str(getattr(sig, 'signal_id', '') or '')
                if not signal_id:
                    continue

                # Do not resend signals for markets currently closed.
                # Keep the signal active so it can be reconsidered when market re-opens.
                try:
                    from data.fetcher import market_closed_reason
                    _asset = str(getattr(sig, 'asset', '') or '')
                    _closed_reason = market_closed_reason(_asset) if _asset else None
                    if _closed_reason:
                        logger.info(
                            f"[resend] Skipped signal {signal_id} for asset={_asset}: market closed ({_closed_reason})"
                        )
                        continue
                except Exception:
                    pass

                # DB-backed dedupe for this signal (survives process restarts).
                delivered_user_ids: set[int] = set()
                try:
                    from sqlalchemy import select
                    from db.models import SignalDelivery, User
                    async with get_session() as _deliv_s:
                        _q = (
                            select(User.telegram_user_id)
                            .join(SignalDelivery, SignalDelivery.user_id == User.id)
                            .where(
                                SignalDelivery.signal_id == signal_id,
                                SignalDelivery.sent_ok.is_(True),
                            )
                        )
                        _rows = await _deliv_s.execute(_q)
                        delivered_user_ids = {
                            int(v)
                            for v in (_rows.scalars().all() or [])
                            if v is not None
                        }
                except Exception as _deliv_err:
                    logger.debug(f"[resend] delivery prefetch failed for {signal_id}: {_deliv_err}")

                # Expire only signals older than 24 hours
                try:
                    from datetime import datetime, timezone, timedelta as _td
                    _created = getattr(sig, 'created_at', None)
                    if _created is not None:
                        if hasattr(_created, 'tzinfo') and _created.tzinfo is None:
                            _created = _created.replace(tzinfo=timezone.utc)
                        _age_min = (datetime.now(timezone.utc) - _created).total_seconds() / 60
                        if _age_min > (24 * 60):
                            # Mark as expired so this signal never re-enters the queue
                            try:
                                async with get_session() as _exp_s:
                                    from db.pg_features import expire_signal as _expire
                                    await _expire(_exp_s, signal_id)
                                    await _exp_s.commit()
                            except Exception:
                                pass
                            logger.info(f"[resend] Signal {signal_id} is {_age_min:.0f}m old — expired, skipped.")
                            continue
                except Exception as _age_err:
                    logger.debug(f"[resend] age-check failed for {signal_id}: {_age_err}")

                # Skip signals whose outcome (TP / SL) has already been reached
                try:
                    outcome_status = get_signal_outcome_status(signal_id)
                    if outcome_status and outcome_status.get('reached'):
                        continue
                except Exception:
                    pass

                # Build a plain dict from the ORM row for the formatter
                try:
                    if hasattr(sig, '__table__'):
                        sig_dict = {c.key: getattr(sig, c.key, None) for c in sig.__table__.columns}
                    else:
                        sig_dict = {k: v for k, v in sig.__dict__.items() if not k.startswith('_')}
                except Exception:
                    sig_dict = {}

                for user_id in user_ids:
                    user_tier = str(user_tier_map.get(int(user_id), "free") or "free").lower()
                    gate_tier = _normalized_delivery_tier(user_tier)
                    try:
                        # Free users are random-realtime routed by dispatch_signals();
                        # skip score-ranked resend flow unless explicitly enabled.
                        if gate_tier == "free" and not include_free_in_resend:
                            skipped_eligibility_count += 1
                            continue

                        if int(user_id) in delivered_user_ids:
                            skipped_already_delivered_count += 1
                            continue

                        # Tier, score, and daily-limit gate
                        score = float(getattr(sig, 'score', 0) or 0)
                        # No Redis dependency in resend flow; DB delivery table is the source of truth.
                        if not delivery_mgr.should_send_signal(gate_tier, score, user_id=int(user_id)):
                            skipped_eligibility_count += 1
                            logger.debug(
                                f"[resend] User {user_id} not eligible for signal {signal_id} "
                                f"(tier={gate_tier}/score/limit), skipping."
                            )
                            continue

                        _asset = str(getattr(sig, 'asset', '') or '').upper().strip()
                        if _asset and await _is_asset_delivery_locked(int(user_id), _asset):
                            logger.debug(f"[resend] asset lock user={user_id} asset={_asset} signal={signal_id}")
                            continue

                        # Format and send
                        display_tier = gate_tier
                        text = format_signal(sig_dict, user_tier=gate_tier, display_tier=display_tier)
                        if not text or not str(text).strip():
                            logger.info(
                                f"[resend] Skipped signal {signal_id} for user {user_id} "
                                f"(tier={user_tier}): formatter returned empty text"
                            )
                            continue
                        # Pre-send reservation in DB (attempt tracked even if network fails).
                        reserved = False
                        try:
                            async with get_session() as db_session:
                                reserved = await record_signal_delivery(
                                    db_session,
                                    telegram_user_id=int(user_id),
                                    signal_id=str(signal_id),
                                    tier_at_send=str(gate_tier),
                                )
                                await db_session.commit()
                            if not reserved:
                                logger.info(f"[resend] DB deduped before send: signal {signal_id} to user {user_id} (tier={gate_tier})")
                                continue
                        except Exception as db_err:
                            logger.error(f"[resend] DB reserve error: signal {signal_id} to user {user_id}: {db_err}")
                            continue

                        try:
                            await _deliver_or_update_signal_async(
                                bot=bot,
                                telegram_user_id=int(user_id),
                                signal=dict(sig_dict or {}),
                                display_tier=str(display_tier),
                            )
                            async with get_session() as db_session:
                                await mark_signal_delivery_result(
                                    db_session,
                                    telegram_user_id=int(user_id),
                                    signal_id=str(signal_id),
                                    sent_ok=True,
                                )
                                await db_session.commit()
                        except Exception as send_err:
                            try:
                                async with get_session() as db_session:
                                    await mark_signal_delivery_result(
                                        db_session,
                                        telegram_user_id=int(user_id),
                                        signal_id=str(signal_id),
                                        sent_ok=False,
                                        error=str(send_err),
                                    )
                                    await db_session.commit()
                            except Exception:
                                pass
                            raise send_err

                        await asyncio.sleep(0.5)
                        delivered_count += 1
                        logger.info(f"[resend] Delivered signal {signal_id} to user {user_id} (tier={user_tier})")
                        delivered_user_ids.add(int(user_id))

                    except Exception as send_err:
                        failed_count += 1
                        _err_text = str(send_err or "")
                        if "bot was blocked by the user" in _err_text.lower():
                            logger.info(f"[resend] User {user_id} blocked bot; suppressing retries for signal {signal_id}")
                            try:
                                async with get_session() as db_session:
                                    await record_signal_delivery(
                                        db_session,
                                        telegram_user_id=int(user_id),
                                        signal_id=str(signal_id),
                                        tier_at_send=f"{str(gate_tier)[:8]}_blk",
                                    )
                                    await db_session.commit()
                                delivered_user_ids.add(int(user_id))
                            except Exception:
                                pass
                        else:
                            logger.error(f"[resend] Failed to deliver signal {signal_id} to user {user_id}: {send_err}")

                # Do NOT expire signals based only on current recipient eligibility.
                # Eligibility can change (new users, upgrades, daily-limit reset), and
                # unresolved signals should remain active until real expiry/outcome rules do it.

        logger.info(
            "[resend] summary: users=%s candidate_signals=%s delivered=%s failed=%s skipped_eligibility=%s skipped_already_delivered=%s",
            len(user_ids),
            len(signals),
            delivered_count,
            failed_count,
            skipped_eligibility_count,
            skipped_already_delivered_count,
        )

    except Exception as e:
        logger.warning(f"[resend] Job inner error: {e}")


import os
from config import config, resolve_database_url
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from signalrank_telegram.httpx_config import httpx_client

def _audit_handler(command_name: str, handler):
    async def _inner(update, context):
        command_timeout_s = float(os.getenv("COMMAND_HANDLER_TIMEOUT_SECONDS", "60") or 60)
        # IMPORTANT: Skip pre-audit for /start.
        # The audit writer creates the user row (via record_bot_event -> get_or_create_user).
        # That would make start_command see the user as "not new" and prevent referral attribution.
        # start_command already handles user creation + start auditing in a single transaction.
        if str(command_name) == "start":
            try:
                return await asyncio.wait_for(handler(update, context), timeout=command_timeout_s)
            except Exception as exc:
                logger.exception("[cmd:%s] handler failed: %s", command_name, exc)
                try:
                    if getattr(update, "message", None) is not None:
                        await update.message.reply_text(
                            "The command could not complete right now. Please try again in a moment."
                        )
                except Exception:
                    pass
                return

        try:
            from db.session import get_session
            if getattr(update, "effective_user", None) is not None:
                user_id = int(update.effective_user.id)
                username = None
                try:
                    username = update.effective_user.username
                except Exception as e:
                    logger.debug(f"[audit] Failed to get username from update: {e}")
                    pass
                # ...existing code for auditing...
        except Exception as e:
            logger.debug(f"[audit] Failed to audit command wrapper: {e}")
            pass
        try:
            return await asyncio.wait_for(handler(update, context), timeout=command_timeout_s)
        except asyncio.TimeoutError:
            logger.warning("[cmd:%s] timed out after %ss", command_name, command_timeout_s)
            try:
                if getattr(update, "message", None) is not None:
                    await update.message.reply_text(
                        "That command is taking too long right now. Please try again shortly."
                    )
            except Exception:
                pass
            return
        except Exception as exc:
            logger.exception("[cmd:%s] handler failed: %s", command_name, exc)
            try:
                if getattr(update, "message", None) is not None:
                    await update.message.reply_text(
                        "The command could not complete right now. Please try again in a moment."
                    )
            except Exception:
                pass
            return
    return _inner

from telegram.ext import Defaults
import logging
# Increase Telegram bot request timeout for connection pool exhaustion
TELEGRAM_POOL_TIMEOUT = int(getattr(config, "TELEGRAM_POOL_TIMEOUT", 30))  # seconds, configurable
TELEGRAM_CONNECT_TIMEOUT = int(getattr(config, "TELEGRAM_CONNECT_TIMEOUT", 30))  # seconds, configurable
TELEGRAM_READ_TIMEOUT = int(getattr(config, "TELEGRAM_READ_TIMEOUT", 30))  # seconds, configurable
TELEGRAM_WRITE_TIMEOUT = int(getattr(config, "TELEGRAM_WRITE_TIMEOUT", 30))  # seconds, configurable

# Build the Telegram Application only when a token is provided and not in DRY_RUN.
# DRY_RUN defaults to "0" (disabled) — signals are sent for real unless you
# explicitly set DRY_RUN=1 in your Railway variables.
_token = getattr(config, 'TELEGRAM_BOT_TOKEN', None)
_dry_run_env = str(os.getenv('DRY_RUN', '0') or '0').strip().lower() in {'1', 'true', 'yes'}
if _token and not _dry_run_env:
    application = Application.builder()
    application = application.token(_token)
    application = application.pool_timeout(TELEGRAM_POOL_TIMEOUT)
    application = application.connect_timeout(TELEGRAM_CONNECT_TIMEOUT)
    application = application.read_timeout(TELEGRAM_READ_TIMEOUT)
    application = application.write_timeout(TELEGRAM_WRITE_TIMEOUT)
    application = application.build()
else:
    # Dummy application for environments without a token or when DRY_RUN is set.
    class _DummyApp:
        def add_handler(self, *a, **k):
            return None

        def run(self, *a, **k):
            return None

    application = _DummyApp()
    # Log a non-blocking warning so operators see why the real bot isn't running
    try:
        _logger = logging.getLogger(__name__)
        if _dry_run_env:
            _logger.warning("TELEGRAM_BOT_TOKEN not used because DRY_RUN is enabled; bot disabled for this process.")
        else:
            _logger.warning("TELEGRAM_BOT_TOKEN not provided; Telegram bot is disabled in this process.")
    except Exception as e:
        _logger.warning(f"[bot] Failed to initialize Telegram bot token: {e}")
        pass
import os
import asyncio
import socket
import logging
import time
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
    status_command,
    support_command,
    performance_command,
    quality_command,
    gemini_command,
    gemini_review_command,
    pricing_command,
    upgrade_command,
    policy_command,
    recap_command,
    signals_command,
    proof_command,
    signal_command,
    outcome_command,
    invite_command,
    stats_command,
    history_command,
    apikey_command,
    simulate_command,
    analyze_command,
    risk_command,
    alerts_command,
    elite_command,
    early_command,
    report_command,
    language_command,
    feedback_command,
    notify_command,
    filter_command,
    selfcheck_command,
    ops_health_command,
    myid_command,
    account_command,
    dashboard_command,
    liveprice_command,
    portfolio_command,
    market_command,
    gemini_analyze_command,
    gemini_audit_command,
    reports_command,
    gemini_predict_command,
    admin_command,
    admin_broadcast_command,
    agree_terms_callback,
    decline_terms_callback,
    vip_waitlist_join_callback,
    blast_terms_command,
    referral_leaderboard_command,
    referral_rewards_command,
    assets_command,
)

# Import admin commands directly from admin_commands module to avoid import conflicts
from .admin_commands import (
    admin_top_assets_command,
    admin_top_strategies_command,
    admin_user_engagement_command,
)

from .owner_commands import (
    unlock,
    dev_pause,
    dev_resume,
    dev_force_signal,
    dev_invalidate,
    owner_users,
    owner_revenue,
    correct_signal,
    provider_status_command,
    qa_report_command,
    broadcast_command,
)

# Import tier-based notification manager
from engine.tier_notifications import TierNotificationManager

# Initialize tier notification manager
_tier_notifier = TierNotificationManager()

# Module-level logger for scheduled jobs and dispatch traces
logger = logging.getLogger(__name__)
_vip_webhook_client = None

TIER_LIMITS = {
    'free': 3,
    'premium': 20,
    'vip': 50,
    'admin': 100,
    'owner': 100,
}


_LOG_ONCE_KEYS: set[str] = set()


def _log_once(key: str, message: str) -> None:
    if key in _LOG_ONCE_KEYS:
        return
    _LOG_ONCE_KEYS.add(key)
    try:
        print(message, flush=True)
    except Exception as e:
        logger.debug(f"[log_once] Failed to print log message: {e}")
        pass


def _mask_db_url_host(url: str) -> str:
    try:
        from sqlalchemy.engine.url import make_url
        parsed = make_url(url)
        host = str(parsed.host or "").strip()
        port = parsed.port
        db = str(parsed.database or "").strip()
        if not host:
            return "<masked>"
        out = host
        if port:
            out = f"{out}:{port}"
        if db:
            out = f"{out}/{db}"
        return out
    except Exception:
        return "<masked>"


def _normalized_delivery_tier(tier: str | None) -> str:
    t = str(tier or "free").strip().lower()
    if t in ("owner", "admin"):
        return "vip"
    return t




async def _send_message_async(
    bot: Bot,
    chat_id: int,
    text: str,
    parse_mode: str | None = None,
    telemetry_started_at: float | None = None,
    telemetry_tier: str | None = None,
    telemetry_regime: str | None = None,
) -> None:
    # Global fix: escape text for Markdown/MarkdownV2 parse modes
    try:
        if parse_mode and parse_mode.lower().startswith("markdown"):
            from telegram.helpers import escape_markdown
            version = 2 if "v2" in parse_mode.lower() else 1
            text = escape_markdown(str(text), version=version)
        await bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
        if telemetry_started_at is not None:
            observe_signal_dispatch(
                max(0.0, time.perf_counter() - float(telemetry_started_at)),
                tier=str(telemetry_tier or "unknown"),
                regime=telemetry_regime,
                status="ok",
            )
    except Exception:
        if telemetry_started_at is not None:
            observe_signal_dispatch(
                max(0.0, time.perf_counter() - float(telemetry_started_at)),
                tier=str(telemetry_tier or "unknown"),
                regime=telemetry_regime,
                status="error",
            )
        raise


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except Exception:
        return int(default)


def _first_take_profit(signal: dict | None) -> float | None:
    if not isinstance(signal, dict):
        return None
    raw_tp = signal.get("take_profit") or signal.get("tp_levels") or signal.get("targets")
    if isinstance(raw_tp, (list, tuple)):
        for item in raw_tp:
            try:
                candidate = item.get("price") if isinstance(item, dict) else item
                value = float(candidate)
                if value > 0:
                    return value
            except Exception:
                continue
        return None
    try:
        value = float(raw_tp)
        return value if value > 0 else None
    except Exception:
        return None


def _signal_roi_score(signal: dict) -> float:
    rr = _safe_float(
        signal.get("roi")
        or signal.get("expected_roi")
        or signal.get("rr_ratio")
        or signal.get("rr_estimate")
        or signal.get("risk_reward"),
        default=0.0,
    )
    if rr > 0:
        return rr
    entry = _safe_float(signal.get("entry") or signal.get("close_price"))
    stop = _safe_float(signal.get("stop_loss") or signal.get("stop"))
    target = _first_take_profit(signal)
    if entry <= 0 or stop <= 0 or target is None:
        return 0.0
    risk = abs(entry - stop)
    if risk <= 0:
        return 0.0
    return abs(target - entry) / risk


def _signal_variant_key(signal: dict) -> tuple[str, str]:
    asset = str(signal.get("asset") or signal.get("symbol") or "").upper().strip()
    direction = str(signal.get("direction") or signal.get("side") or "long").lower().strip()
    return asset, direction


def _collapse_signal_variants(signals_list: list[dict]) -> list[dict]:
    best_by_key: dict[tuple[str, str], dict] = {}
    for signal in signals_list or []:
        key = _signal_variant_key(signal)
        incumbent = best_by_key.get(key)
        if incumbent is None:
            best_by_key[key] = signal
            continue
        candidate_rank = (
            _signal_roi_score(signal),
            _safe_float(signal.get("score")),
            _safe_float(signal.get("ml_probability")),
        )
        incumbent_rank = (
            _signal_roi_score(incumbent),
            _safe_float(incumbent.get("score")),
            _safe_float(incumbent.get("ml_probability")),
        )
        if candidate_rank > incumbent_rank:
            best_by_key[key] = signal
    collapsed = list(best_by_key.values())
    collapsed.sort(
        key=lambda signal: (
            _signal_roi_score(signal),
            _safe_float(signal.get("score")),
            _safe_float(signal.get("ml_probability")),
        ),
        reverse=True,
    )
    return collapsed


def _signal_news_score(signal: dict | None) -> float:
    if not isinstance(signal, dict):
        return 0.0
    candidates = (
        signal.get("news_score"),
        signal.get("news_sentiment"),
        signal.get("sentiment_score"),
        signal.get("news_bias"),
    )
    for value in candidates:
        try:
            score = float(value)
            if abs(score) <= 1.0:
                score *= 100.0
            return score
        except Exception:
            continue
    return 0.0


def _build_update_reason(old_signal: dict | None, new_signal: dict | None) -> str | None:
    if not isinstance(old_signal, dict) or not isinstance(new_signal, dict):
        return None

    min_roi_delta = float(os.getenv("SIGNAL_UPDATE_MIN_ROI_DELTA", "0.10") or 0.10)
    min_rr_delta = float(os.getenv("SIGNAL_UPDATE_MIN_RR_DELTA", "0.10") or 0.10)
    min_ml_delta = float(os.getenv("SIGNAL_UPDATE_MIN_ML_DELTA", "0.02") or 0.02)
    min_news_delta = float(os.getenv("SIGNAL_UPDATE_MIN_NEWS_DELTA", "5") or 5.0)

    old_roi = _signal_roi_score(old_signal)
    new_roi = _signal_roi_score(new_signal)
    old_rr = _safe_float(old_signal.get("rr_ratio") or old_signal.get("rr_estimate") or old_signal.get("risk_reward"))
    new_rr = _safe_float(new_signal.get("rr_ratio") or new_signal.get("rr_estimate") or new_signal.get("risk_reward"))
    if old_rr <= 0:
        old_rr = old_roi
    if new_rr <= 0:
        new_rr = new_roi

    old_ml = _safe_float(old_signal.get("ml_probability"))
    new_ml = _safe_float(new_signal.get("ml_probability"))
    old_news = _signal_news_score(old_signal)
    new_news = _signal_news_score(new_signal)

    reasons: list[str] = []
    if (new_roi - old_roi) >= min_roi_delta:
        reasons.append(f"ROI improved {old_roi:.2f}→{new_roi:.2f}")
    if (new_rr - old_rr) >= min_rr_delta:
        reasons.append(f"R:R improved {old_rr:.2f}→{new_rr:.2f}")
    if (new_ml - old_ml) >= min_ml_delta:
        reasons.append(f"ML confidence improved {old_ml * 100:.0f}%→{new_ml * 100:.0f}%")
    if (new_news - old_news) >= min_news_delta and new_news >= old_news:
        reasons.append("news backdrop is more favorable")

    if not reasons:
        return None

    if (new_roi + 1e-9) < old_roi:
        return None
    if (new_rr + 1e-9) < old_rr:
        return None
    if new_news < old_news:
        return None

    return "; ".join(reasons[:3])


async def _is_asset_delivery_locked(
    telegram_user_id: int,
    asset: str,
    lock_hours: int | None = None,
) -> bool:
    try:
        from datetime import datetime, timedelta
        from sqlalchemy import and_, func, select
        from db.session import get_session
        from db.models import Outcome, Signal, SignalDelivery, User

        symbol = str(asset or "").upper().strip()
        if not symbol:
            return False

        hours = int(lock_hours if lock_hours is not None else int(os.getenv("ASSET_REPEAT_LOCK_HOURS", "12") or 12))
        if hours <= 0:
            return False
        cutoff = datetime.utcnow() - timedelta(hours=hours)

        async with get_session() as session:
            user = (
                await session.execute(
                    select(User).where(User.telegram_user_id == int(telegram_user_id)).limit(1)
                )
            ).scalar_one_or_none()
            if user is None:
                await session.commit()
                return False

            locked_count = (
                await session.execute(
                    select(func.count(SignalDelivery.id))
                    .select_from(SignalDelivery)
                    .join(Signal, Signal.signal_id == SignalDelivery.signal_id)
                    .outerjoin(Outcome, Outcome.signal_id == Signal.signal_id)
                    .where(
                        SignalDelivery.user_id == user.id,
                        SignalDelivery.delivered_at >= cutoff,
                        func.upper(Signal.asset) == symbol,
                        Signal.archived == False,
                        Signal.expired == False,
                        Outcome.id.is_(None),
                    )
                )
            ).scalar_one()
            await session.commit()
            return int(locked_count or 0) > 0
    except Exception as exc:
        logger.debug(f"[asset_lock] check failed for user={telegram_user_id} asset={asset}: {exc}")
        return False


async def _load_signal_payload(signal_id: str) -> dict | None:
    try:
        import json
        from db.session import get_session
        from db.models import Signal
        from sqlalchemy import select

        async with get_session() as session:
            signal_row = (
                await session.execute(
                    select(Signal).where(Signal.signal_id == str(signal_id)).limit(1)
                )
            ).scalar_one_or_none()
            await session.commit()

        if signal_row is None:
            return None

        take_profit = getattr(signal_row, "take_profit", None)
        if isinstance(take_profit, str):
            try:
                take_profit = json.loads(take_profit)
            except Exception:
                pass

        return {
            "signal_id": str(getattr(signal_row, "signal_id", signal_id)),
            "asset": getattr(signal_row, "asset", ""),
            "timeframe": getattr(signal_row, "timeframe", ""),
            "direction": getattr(signal_row, "direction", ""),
            "entry": getattr(signal_row, "entry", None),
            "stop_loss": getattr(signal_row, "stop_loss", None),
            "take_profit": take_profit,
            "score": getattr(signal_row, "score", None),
            "rr_ratio": getattr(signal_row, "rr_estimate", None),
            "regime": getattr(signal_row, "regime", None),
            "ml_probability": getattr(signal_row, "ml_probability", None),
            "strategy": getattr(signal_row, "strategy_name", None),
            "expires_at": getattr(signal_row, "expires_at", None),
            "created_at": getattr(signal_row, "created_at", None),
            "expired": getattr(signal_row, "expired", False),
        }
    except Exception as exc:
        logger.debug(f"[signal_payload] failed to load {signal_id}: {exc}")
        return None


async def _load_signal_engagement_counts(signal_id: str) -> dict[str, int]:
    counts = {"taking_it": 0, "watching": 0}
    try:
        from db.session import get_session
        from db.models import SignalEngagement
        from sqlalchemy import func, select

        async with get_session() as session:
            rows = await session.execute(
                select(SignalEngagement.reaction, func.count(SignalEngagement.id))
                .where(SignalEngagement.signal_id == str(signal_id))
                .group_by(SignalEngagement.reaction)
            )
            await session.commit()
        for reaction, count in rows.all():
            counts[str(reaction)] = int(count or 0)
    except Exception as exc:
        logger.debug(f"[engagement] count load failed for {signal_id}: {exc}")
    return counts


def _build_signal_keyboard(signal_id: str, signal: dict | None = None, counts: dict[str, int] | None = None):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    counts = counts or {}
    taking_it = int(counts.get("taking_it", 0) or 0)
    watching = int(counts.get("watching", 0) or 0)
    rows = [[
        InlineKeyboardButton(f"🔥 Taking It ({taking_it})", callback_data=f"signal_reaction_{signal_id}|taking_it"),
        InlineKeyboardButton(f"👀 Watching ({watching})", callback_data=f"signal_reaction_{signal_id}|watching"),
    ]]

    # Always include compact callback payload so button remains available
    # even when detailed numeric payload would exceed Telegram's 64-byte limit.
    if str(signal_id or "").strip():
        rows.append([
            InlineKeyboardButton("⚡ Take Trade", callback_data=f"mt5_trade_{str(signal_id)[:36]}")
        ])

    rows.append([
        InlineKeyboardButton("📈 Monitor", callback_data=f"monitor_signal_{signal_id}"),
        InlineKeyboardButton("🔍 Check Outcome", callback_data=f"check_outcome_{str(signal_id)[:36]}"),
    ])
    return InlineKeyboardMarkup(rows)


def _build_monitor_keyboard(signal_id: str):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup([[ 
        InlineKeyboardButton("🔄 Refresh", callback_data=f"monitor_signal_{signal_id}"),
        InlineKeyboardButton("🔍 Check Outcome", callback_data=f"check_outcome_{str(signal_id)[:36]}"),
    ]])


def _build_signal_message_link(chat_id: int, message_id: int) -> str:
    chat_str = str(int(chat_id))
    if chat_str.startswith("-100"):
        return f"https://t.me/c/{chat_str[4:]}/{int(message_id)}"
    return f"tg://openmessage?chat_id={int(chat_id)}&message_id={int(message_id)}"


async def _find_editable_signal_message(telegram_user_id: int, incoming_signal: dict) -> dict | None:
    """Find latest active same-asset/same-direction message eligible for in-place update.

    Do not update if previous signal is stale and has more than 5 newer signals after it.
    """
    try:
        from sqlalchemy import and_, desc, func, select
        from db.session import get_session
        from db.models import ActiveSignalMessage, Signal, SignalDelivery
        from db.pg_features import get_or_create_user
        from engine.price_validator import is_signal_stale

        asset = str(incoming_signal.get("asset") or "").upper().strip()
        direction = str(incoming_signal.get("direction") or "").lower().strip()
        if not asset or not direction:
            return None

        async with get_session() as session:
            user = await get_or_create_user(session, telegram_user_id=int(telegram_user_id))

            base = (
                await session.execute(
                    select(ActiveSignalMessage, Signal, SignalDelivery.delivered_at)
                    .join(Signal, Signal.signal_id == ActiveSignalMessage.signal_id)
                    .outerjoin(
                        SignalDelivery,
                        and_(
                            SignalDelivery.user_id == ActiveSignalMessage.user_id,
                            SignalDelivery.signal_id == ActiveSignalMessage.signal_id,
                        ),
                    )
                    .where(
                        ActiveSignalMessage.user_id == user.id,
                        ActiveSignalMessage.is_active.is_(True),
                        Signal.asset == asset,
                        Signal.direction == direction,
                    )
                    .order_by(desc(Signal.created_at))
                    .limit(1)
                )
            ).first()

            if not base:
                await session.commit()
                return None

            active_msg, signal_row, delivered_at = base
            signal_snapshot = {
                "asset": signal_row.asset,
                "direction": signal_row.direction,
                "entry": signal_row.entry,
                "stop_loss": signal_row.stop_loss,
                "take_profit": signal_row.take_profit,
                "created_at": signal_row.created_at,
                "expires_at": signal_row.expires_at,
                "expired": bool(signal_row.expired),
            }
            stale = bool(signal_row.expired) or bool(is_signal_stale(signal_snapshot))

            newer_count = (
                await session.execute(
                    select(func.count(SignalDelivery.id))
                    .join(Signal, Signal.signal_id == SignalDelivery.signal_id)
                    .where(
                        SignalDelivery.user_id == user.id,
                        Signal.created_at > signal_row.created_at,
                    )
                )
            ).scalar_one()

            await session.commit()

            if stale and int(newer_count or 0) > 5:
                return None

            return {
                "user_id": int(user.id),
                "old_signal_id": str(signal_row.signal_id),
                "chat_id": int(active_msg.chat_id),
                "message_id": int(active_msg.message_id),
                "stale": stale,
                "newer_count": int(newer_count or 0),
                "delivered_at": delivered_at,
            }
    except Exception as exc:
        logger.debug(f"[signal_update] find editable failed: {exc}")
        return None


async def _mark_signal_message_updated(user_id: int, old_signal_id: str, new_signal_id: str) -> None:
    """Repoint active message row to the latest signal id after an in-place edit."""
    try:
        from sqlalchemy import update
        from db.session import get_session
        from db.models import ActiveSignalMessage

        async with get_session() as session:
            await session.execute(
                update(ActiveSignalMessage)
                .where(
                    ActiveSignalMessage.user_id == int(user_id),
                    ActiveSignalMessage.signal_id == str(old_signal_id),
                )
                .values(signal_id=str(new_signal_id), is_active=True)
            )
            await session.commit()
    except Exception as exc:
        logger.debug(f"[signal_update] map update failed: {exc}")


async def _deliver_or_update_signal_async(
    bot: Bot,
    telegram_user_id: int,
    signal: dict,
    display_tier: str,
) -> bool:
    """Prefer editing existing active message over sending a near-duplicate new one."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    signal_id = str(signal.get("signal_id") or "").strip()
    text = format_signal(signal, display_tier=display_tier)
    if not text or not str(text).strip():
        return False

    if signal_id:
        editable = await _find_editable_signal_message(int(telegram_user_id), signal)
        if editable is not None:
            try:
                old_payload = await _load_signal_payload(str(editable.get("old_signal_id") or ""))
                update_reason = _build_update_reason(old_payload or {}, signal)
                if not update_reason:
                    logger.debug(
                        f"[signal_update] skipped non-material update user={telegram_user_id} "
                        f"old={editable.get('old_signal_id')} new={signal_id}"
                    )
                    return True

                counts = await _load_signal_engagement_counts(signal_id)
                keyboard = _build_signal_keyboard(signal_id, signal=signal, counts=counts)
                await bot.edit_message_text(
                    chat_id=int(editable["chat_id"]),
                    message_id=int(editable["message_id"]),
                    text=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )

                await _mark_signal_message_updated(
                    int(editable["user_id"]),
                    str(editable["old_signal_id"]),
                    signal_id,
                )

                jump_keyboard = InlineKeyboardMarkup(
                    [[InlineKeyboardButton("Go to signal", callback_data=f"open_signal_{signal_id[:36]}")]]
                )
                await bot.send_message(
                    chat_id=int(telegram_user_id),
                    text=f"♻️ <b>Signal updated</b> — {update_reason}.",
                    parse_mode="HTML",
                    reply_markup=jump_keyboard,
                )
                return True
            except Exception as exc:
                logger.debug(f"[signal_update] edit path failed; fallback to fresh send: {exc}")

    try:
        signal_asset = str(signal.get("asset") or signal.get("symbol") or "").upper().strip()
        if signal_asset and await _is_asset_delivery_locked(int(telegram_user_id), signal_asset):
            logger.info(
                f"[dispatch] skipped duplicate asset due to lock: user={telegram_user_id} "
                f"asset={signal_asset} signal={signal_id or signal.get('id')}"
            )
            return True
    except Exception as exc:
        logger.debug(f"[asset_lock] pre-send check failed for user={telegram_user_id}: {exc}")

    await _send_signal_with_engagement_async(
        bot,
        chat_id=int(telegram_user_id),
        text=str(text),
        signal_id=signal_id or str(signal.get("id") or ""),
        telegram_user_id=int(telegram_user_id),
        signal=signal,
    )
    return True


def _deliver_or_update_signal_sync(
    bot: Bot,
    telegram_user_id: int,
    signal: dict,
    display_tier: str,
) -> bool:
    try:
        ok = bool(
            run_sync(
                _deliver_or_update_signal_async(
                    bot=bot,
                    telegram_user_id=int(telegram_user_id),
                    signal=dict(signal or {}),
                    display_tier=str(display_tier),
                )
            )
        )
        if ok:
            try:
                sig_id = str(signal.get("signal_id") or signal.get("id") or "").strip()
                if sig_id:
                    mark_signal_delivered_sync(int(telegram_user_id), sig_id)
            except Exception as redis_err:
                logger.debug(f"[dispatch] Failed to track signal delivery in Redis: {redis_err}")
        return ok
    except Exception as exc:
        logger.debug(f"[dispatch] deliver_or_update failed: {exc}")
        return False


def _record_mt5_execution_sync(
    telegram_user_id: int,
    signal: dict,
    *,
    account_id: str,
    order_id: str | None,
    lot_size: float,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    tier_at_execution: str,
    status: str = "open",
    extra_meta: dict | None = None,
) -> None:
    """Best-effort persistence for broker executions used by risk controls/jobs."""
    try:
        from db.session import get_session
        from db.models import MT5Execution, User
        from sqlalchemy import select
        import json
        from datetime import datetime, timezone

        sig_id = str(signal.get("signal_id") or signal.get("id") or "").strip() or None
        symbol = str(signal.get("asset") or signal.get("symbol") or "").upper().strip()
        direction = str(signal.get("direction") or "long").lower().strip()
        if direction in {"buy"}:
            direction = "long"
        elif direction in {"sell"}:
            direction = "short"

        meta = {
            "hard_stop_attached": True,
            "source": "telegram_bot",
            "telegram_user_id": int(telegram_user_id),
        }
        if isinstance(extra_meta, dict):
            meta.update(extra_meta)

        async def _write() -> None:
            async with get_session() as session:
                user = (
                    await session.execute(
                        select(User).where(User.telegram_user_id == int(telegram_user_id)).limit(1)
                    )
                ).scalar_one_or_none()
                if user is None:
                    return

                row = MT5Execution(
                    user_id=int(user.id),
                    signal_id=sig_id,
                    metaapi_account_id=str(account_id),
                    order_id=(str(order_id) if order_id else None),
                    symbol=symbol,
                    direction=("long" if direction == "long" else "short"),
                    lot_size=float(lot_size),
                    entry_price=float(entry_price),
                    stop_loss=float(stop_loss),
                    take_profit=json.dumps([float(take_profit)]),
                    status=str(status or "open")[:16],
                    tier_at_execution=str(tier_at_execution or "premium").upper(),
                    executed_at=datetime.now(timezone.utc),
                    meta=meta,
                )
                session.add(row)
                await session.commit()

        run_sync(_write())
    except Exception as exc:
        logger.debug(f"[mt5_exec] persist failed user={telegram_user_id}: {exc}")


def _auto_execute_signal_if_enabled(telegram_user_id: int, signal: dict, routing_tier: str) -> None:
    """Best-effort AUTO execution path for users in execution_mode=auto.

    - no-op for mode!=auto
    - dedupes per user/signal
    - respects PREMIUM daily limit
    - sends success/failure DM
    """
    try:
        def _drawdown_guard_block_reason(user, realized_pnl_pct_today: float) -> str | None:
            try:
                cap = float(getattr(user, "max_daily_drawdown_pct", 8.0) or 8.0)
                if cap <= 0:
                    return None
                if float(realized_pnl_pct_today) <= -abs(cap):
                    return (
                        f"Daily drawdown guard hit ({realized_pnl_pct_today:.2f}% <= -{abs(cap):.2f}%). "
                        "Auto-trading paused for today."
                    )
            except Exception:
                return None
            return None

        sig_id = str(signal.get("signal_id") or signal.get("id") or "").strip()
        if not sig_id:
            return

        # AUTO mode is paid-only and intended for premium/vip routing.
        rt = str(routing_tier or "").lower()
        if rt not in {"premium", "vip"}:
            return

        auto_key = f"autoexec:{int(telegram_user_id)}:{sig_id}"
        try:
            if state.get_sync(auto_key):
                return
        except Exception:
            pass

        from db.session import get_session
        from db.models import User, MT5Execution
        from sqlalchemy import select, func, text
        from services.mt5_client import get_user_mt5_account_id, validate_slippage, execute_trade

        async def _run_auto():
            async with get_session() as session:
                user = (
                    await session.execute(
                        select(User).where(User.telegram_user_id == int(telegram_user_id)).limit(1)
                    )
                ).scalar_one_or_none()
                if user is None:
                    return (False, "User profile missing")

                mode = str(getattr(user, "execution_mode", "manual") or "manual").lower()
                if mode != "auto":
                    return (False, "Execution mode is not AUTO", "not_auto")

                # Explicit user opt-in guard: AUTO must be intentionally selected
                # via /execution auto on current deployments.
                optin_key = f"autoexec_user_optin:{int(telegram_user_id)}"
                optin = await session.execute(
                    text("SELECT value FROM runtime_state WHERE key = :k LIMIT 1"),
                    {"k": optin_key},
                )
                if optin.scalar_one_or_none() is None:
                    return (
                        False,
                        "AUTO not armed. Use /execution auto [count|all] to enable.",
                        "setup_missing",
                    )

                # Daily drawdown guard based on realized PnL%.
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc)
                day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                pnl_row = await session.execute(
                    select(func.coalesce(func.sum(MT5Execution.realized_pnl_pct), 0.0)).where(
                        MT5Execution.user_id.in_([int(getattr(user, "id", 0) or 0), int(telegram_user_id)]),
                        MT5Execution.executed_at >= day_start,
                    )
                )
                pnl_today = float(pnl_row.scalar_one_or_none() or 0.0)
                blocked_reason = _drawdown_guard_block_reason(user, pnl_today)
                if blocked_reason:
                    await session.commit()
                    return (False, blocked_reason, "risk_guard")

                entry = float(signal.get("entry") or 0)
                sl = float(signal.get("stop_loss") or 0)
                tp = float(_first_take_profit(signal) or 0)
                symbol = str(signal.get("asset") or "").upper().strip()
                direction = str(signal.get("direction") or "").lower().strip()

                if not symbol or direction not in {"long", "short", "buy", "sell"}:
                    return (False, "Invalid symbol/direction", "invalid_signal")
                if not entry or not sl or not tp:
                    return (False, "Signal missing entry/SL/TP", "invalid_signal")

                acct_id = await get_user_mt5_account_id(int(telegram_user_id))
                if not acct_id:
                    return (False, "No linked MT5 account", "setup_missing")

                # PREMIUM daily cap for AUTO mode.
                tier_up = str(getattr(user, "tier", "FREE") or "FREE").upper()
                if tier_up == "PREMIUM":
                    limit = int(os.getenv("PREMIUM_DAILY_EXECUTIONS", "3") or 3)
                    now = datetime.now(timezone.utc)
                    reset_at = getattr(user, "daily_executions_reset_at", None)
                    if reset_at is None or reset_at.date() < now.date():
                        user.daily_executions_today = 0
                        user.daily_executions_reset_at = now
                    if int(getattr(user, "daily_executions_today", 0) or 0) >= int(limit):
                        await session.commit()
                        return (False, f"PREMIUM daily limit reached ({limit})", "limit")

                # Optional per-user AUTO cap.
                auto_cap = int(getattr(user, "auto_signals_daily_limit", -1) or 0)
                if auto_cap == 0:
                    await session.commit()
                    return (False, "AUTO cap is 0", "setup_missing")

                ok, slip, live_px = await validate_slippage(acct_id, symbol, entry)
                if not ok:
                    await session.commit()
                    return (False, f"Slippage too high ({float(slip):.1f} pts)", "slippage")

                # Determine lot size by tier:
                # - VIP: risk-based sizing using account balance
                # - PREMIUM: fixed lot size from user profile
                if tier_up == "VIP":
                    try:
                        from engine.tiered_executor import calculate_lot_size_vip
                        from services.mt5_client import _http_get, _client_base, _deploy_account
                        # Fetch account balance from MetaApi
                        await _deploy_account(acct_id)
                        acct_info = await _http_get(f"{_client_base(acct_id)}/account-information")
                        balance = float((acct_info or {}).get("balance") or 0)
                        if balance <= 0:
                            # Fall back to equity; use 100.0 as last-resort minimum so
                            # calculate_lot_size_vip always returns MIN_LOT rather than
                            # erroring — the slippage guard will catch oversized orders.
                            balance = float((acct_info or {}).get("equity") or 100.0)
                        lot = calculate_lot_size_vip(
                            user,
                            account_balance=balance,
                            entry_price=entry,
                            stop_loss=sl,
                            symbol=symbol,
                        )
                    except Exception as _lot_err:
                        logger.warning("[autoexec] VIP lot calc failed: %s — using fixed lot", _lot_err)
                        lot = float(getattr(user, "fixed_lot_size", 0.01) or 0.01)
                else:
                    lot = float(getattr(user, "fixed_lot_size", 0.01) or 0.01)

                # Send the signal notice before attempting AUTO execution.
                try:
                    await _send_message_with_retry(
                        Bot(token=_require_telegram_token()),
                        chat_id=int(telegram_user_id),
                        text=(
                            "📩 <b>Signal Received</b>\n\n"
                            f"Asset: <b>{symbol}</b>\n"
                            f"Direction: <b>{('LONG' if direction in {'long', 'buy'} else 'SHORT')}</b>\n"
                            f"Lot size: <b>{lot:.3f}</b>\n"
                            "Attempting AUTO execution now..."
                        ),
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

                result = await execute_trade(
                    account_id=acct_id,
                    symbol=symbol,
                    direction=("long" if direction in {"long", "buy"} else "short"),
                    volume=lot,
                    stop_loss=sl,
                    take_profit=tp,
                    signal_entry=entry,
                )

                if bool(result.get("success")) and tier_up == "PREMIUM":
                    now = datetime.now(timezone.utc)
                    user.daily_executions_today = int(getattr(user, "daily_executions_today", 0) or 0) + 1
                    user.daily_executions_reset_at = now

                if bool(result.get("success")):
                    try:
                        _record_mt5_execution_sync(
                            int(telegram_user_id),
                            dict(signal or {}),
                            account_id=str(acct_id),
                            order_id=str(result.get("order_id") or ""),
                            lot_size=float(lot),
                            entry_price=float(live_px or entry),
                            stop_loss=float(sl),
                            take_profit=float(tp),
                            tier_at_execution=str(tier_up),
                            status="open",
                            extra_meta={
                                "auto_execution": True,
                                "hard_stop_attached": bool(result.get("hard_stop_attached", True)),
                                "lot_method": "risk_based" if tier_up == "VIP" else "fixed",
                            },
                        )
                    except Exception:
                        pass

                await session.commit()
                return (
                    bool(result.get("success")),
                    str(result.get("order_id") or result.get("error") or "unknown"),
                    ("success" if bool(result.get("success")) else "execute_failed"),
                )

            ok, detail, reason_code = run_sync(_run_auto())

        try:
            state.set_sync(auto_key, "1", ex=86400)
        except Exception:
            pass

        bot = Bot(token=_require_telegram_token())
        asset = str(signal.get("asset") or "")
        if ok:
            # Send a clean execution receipt after successful AUTO placement.
            _send_message_with_retry_sync(
                bot,
                chat_id=int(telegram_user_id),
                text=(
                    "🧾 <b>Execution Receipt (AUTO)</b>\n\n"
                    f"Asset: <b>{asset}</b>\n"
                    f"Order: <code>{detail}</code>\n"
                    f"Signal ID: <code>{sig_id}</code>"
                ),
                parse_mode="HTML",
            )
        elif reason_code == "setup_missing":
            # Only notify skips when user selected AUTO but setup is incomplete.
            setup_key = f"autoexec:setup_missing:{int(telegram_user_id)}"
            should_warn = True
            try:
                if state.get_sync(setup_key):
                    should_warn = False
                else:
                    state.set_sync(setup_key, "1", ex=21600)  # 6h cooldown
            except Exception:
                pass
            if should_warn:
                _send_message_with_retry_sync(
                    bot,
                    chat_id=int(telegram_user_id),
                    text=(
                        "⚠️ <b>AUTO execution needs setup</b>\n\n"
                        f"Asset: <b>{asset}</b>\n"
                        f"Reason: {detail}\n\n"
                        "Complete your setup and AUTO execution will resume."
                    ),
                    parse_mode="HTML",
                )
    except Exception as exc:
        logger.debug(f"[autoexec] failed user={telegram_user_id}: {exc}")


async def _build_monitor_snapshot(signal_id: str) -> tuple[str, bool, object | None]:
    import json
    from datetime import datetime, timezone

    payload = await _load_signal_payload(signal_id)
    if not payload:
        return "❌ <b>Monitor unavailable</b>\nSignal not found.", False, None

    outcome_row = None
    try:
        from db.session import get_session
        from db.models import Outcome
        from sqlalchemy import select

        async with get_session() as session:
            outcome_row = (
                await session.execute(
                    select(Outcome).where(Outcome.signal_id == str(signal_id)).limit(1)
                )
            ).scalar_one_or_none()
            await session.commit()
    except Exception as exc:
        logger.debug(f"[monitor] outcome load failed for {signal_id}: {exc}")

    asset = str(payload.get("asset") or "?")
    direction = str(payload.get("direction") or "long").lower()
    entry = _safe_float(payload.get("entry"))
    stop_loss = _safe_float(payload.get("stop_loss"))
    take_profit = payload.get("take_profit")
    if isinstance(take_profit, str):
        try:
            take_profit = json.loads(take_profit)
        except Exception:
            pass
    tp1 = _first_take_profit({"take_profit": take_profit})

    current_price = None
    try:
        from core.trade_tracker import _get_current_price
        current_price = await asyncio.to_thread(_get_current_price, asset)
    except Exception as exc:
        logger.debug(f"[monitor] live price fetch failed for {signal_id}: {exc}")

    pnl_pct = None
    if current_price and entry > 0:
        try:
            if direction == "short":
                pnl_pct = ((entry - float(current_price)) / entry) * 100.0
            else:
                pnl_pct = ((float(current_price) - entry) / entry) * 100.0
        except Exception:
            pnl_pct = None

    if outcome_row is not None:
        status = str(getattr(outcome_row, "status", "unknown")).upper()
        status_line = f"✅ <b>Outcome:</b> {status}" if status.startswith("TP") else f"🛑 <b>Outcome:</b> {status}"
        is_active = False
    elif payload.get("expired"):
        status_line = "⏰ <b>Status:</b> Expired"
        is_active = False
    else:
        status_line = "🟢 <b>Status:</b> Active"
        is_active = True

    created_at = payload.get("created_at")
    age_text = "N/A"
    if created_at:
        try:
            created = created_at.replace(tzinfo=timezone.utc) if getattr(created_at, "tzinfo", None) is None else created_at
            age_minutes = int((datetime.now(timezone.utc) - created).total_seconds() / 60)
            age_text = f"{age_minutes}m"
        except Exception:
            pass

    lines = [
        f"📈 <b>Trade Monitor — {asset}</b>",
        status_line,
        f"• Direction: <b>{direction.upper()}</b>",
        f"• Entry: <b>{entry:.5f}</b>" if entry > 0 else "• Entry: <b>N/A</b>",
        f"• Current: <b>{float(current_price):.5f}</b>" if current_price else "• Current: <b>Unavailable</b>",
        f"• Live P/L: <b>{pnl_pct:+.2f}%</b>" if pnl_pct is not None else "• Live P/L: <b>N/A</b>",
        f"• Stop Loss: <b>{stop_loss:.5f}</b>" if stop_loss > 0 else "• Stop Loss: <b>N/A</b>",
        f"• Next Target: <b>{float(tp1):.5f}</b>" if tp1 else "• Next Target: <b>N/A</b>",
        f"• Age: <b>{age_text}</b>",
        f"• Updated: <b>{datetime.utcnow().strftime('%H:%M UTC')}</b>",
    ]
    return "\n".join(lines), is_active, payload.get("expires_at")


def _parse_tp_levels_for_outcome(tp_raw) -> list[float]:
    import json
    if tp_raw is None:
        return []
    if isinstance(tp_raw, (int, float)):
        return [float(tp_raw)]
    if isinstance(tp_raw, (list, tuple)):
        out = []
        for item in tp_raw:
            try:
                if isinstance(item, dict):
                    candidate = item.get("price") or item.get("tp") or item.get("target")
                else:
                    candidate = item
                out.append(float(candidate))
            except Exception:
                continue
        return [x for x in out if x > 0]
    s = str(tp_raw).strip()
    if not s:
        return []
    try:
        data = json.loads(s)
        return _parse_tp_levels_for_outcome(data)
    except Exception:
        pass
    try:
        return [float(s)]
    except Exception:
        return []


def evaluate_signal_outcome_from_candles(
    *,
    entry: float,
    stop_loss: float,
    tp_levels: list[float],
    direction: str,
    candles: list[dict[str, object]],
) -> dict[str, object]:
    """Pure evaluator used by outcome tracker and integration tests.

    Returns dict with status in {tp1,tp2,tp3,sl,invalidated,missed,None}.
    """
    try:
        d = str(direction or "long").lower().strip()
        if d not in {"long", "short"}:
            return {"status": None, "entry_filled": False, "entry_filled_at": None, "max_tp_hit": 0}

        levels = [float(x) for x in (tp_levels or []) if x is not None]
        if not levels:
            return {"status": None, "entry_filled": False, "entry_filled_at": None, "max_tp_hit": 0}
        levels = sorted(levels) if d == "long" else sorted(levels, reverse=True)

        entry_filled = False
        entry_filled_at = None
        max_tp_hit = 0
        invalidated = False
        status = None

        for c in candles or []:
            try:
                hi = float(c.get("high"))
                lo = float(c.get("low"))
            except Exception:
                continue

            if not entry_filled:
                if (d == "long" and lo <= float(stop_loss)) or (d == "short" and hi >= float(stop_loss)):
                    invalidated = True
                    break
                if lo <= float(entry) <= hi:
                    entry_filled = True
                    entry_filled_at = c.get("timestamp")
                continue

            if d == "long":
                hit_sl = lo <= float(stop_loss)
                tp_hit_now = 0
                for idx, tp_price in enumerate(levels, start=1):
                    if hi >= float(tp_price):
                        tp_hit_now = idx
            else:
                hit_sl = hi >= float(stop_loss)
                tp_hit_now = 0
                for idx, tp_price in enumerate(levels, start=1):
                    if lo <= float(tp_price):
                        tp_hit_now = idx

            if hit_sl:
                status = "sl"
                break
            if tp_hit_now > max_tp_hit:
                max_tp_hit = tp_hit_now

        if status is None and max_tp_hit > 0:
            status = "tp3" if max_tp_hit >= 3 else ("tp2" if max_tp_hit == 2 else "tp1")

        if invalidated:
            status = "invalidated"
        elif (not entry_filled) and status is None:
            status = "missed"

        return {
            "status": status,
            "entry_filled": entry_filled,
            "entry_filled_at": entry_filled_at,
            "max_tp_hit": int(max_tp_hit),
            "tp_levels": levels,
        }
    except Exception:
        return {"status": None, "entry_filled": False, "entry_filled_at": None, "max_tp_hit": 0}


async def _refresh_signal_keyboards_for_all_recipients(signal_id: str, bot_obj) -> None:
    """Update vote counters across all active messages for the signal."""
    try:
        from sqlalchemy import select
        from db.session import get_session
        from db.models import ActiveSignalMessage

        payload = await _load_signal_payload(signal_id)
        counts = await _load_signal_engagement_counts(signal_id)
        keyboard = _build_signal_keyboard(signal_id, signal=payload, counts=counts)

        async with get_session() as session:
            rows = (
                await session.execute(
                    select(ActiveSignalMessage).where(
                        ActiveSignalMessage.signal_id == str(signal_id),
                        ActiveSignalMessage.is_active.is_(True),
                    )
                )
            ).scalars().all()

            for row in rows:
                try:
                    await bot_obj.edit_message_reply_markup(
                        chat_id=int(row.chat_id),
                        message_id=int(row.message_id),
                        reply_markup=keyboard,
                    )
                except Exception as exc:
                    if "message is not modified" not in str(exc).lower():
                        logger.debug(f"[engagement] global keyboard refresh failed: {exc}")

            await session.commit()
    except Exception as exc:
        logger.debug(f"[engagement] failed to refresh keyboards: {exc}")


async def _refresh_active_signal_messages_on_startup(bot_obj, limit: int = 500) -> None:
    """Best-effort migration: refresh active signal message templates + buttons.

    - Keeps only unresolved signals from last 24h active.
    - Re-renders active messages with current tier template and full keyboard.
    """
    try:
        from datetime import datetime, timezone, timedelta
        from sqlalchemy import select
        from db.session import get_session
        from db.models import ActiveSignalMessage, Signal, User, Outcome
        from signalrank_telegram.access import resolve_user_tier

        now_utc = datetime.now(timezone.utc)
        cutoff = now_utc - timedelta(days=1)
        refreshed = 0
        deactivated = 0

        async with get_session() as session:
            rows = (
                await session.execute(
                    select(ActiveSignalMessage, Signal, User.telegram_user_id)
                    .join(Signal, Signal.signal_id == ActiveSignalMessage.signal_id)
                    .join(User, User.id == ActiveSignalMessage.user_id)
                    .where(ActiveSignalMessage.is_active.is_(True))
                    .order_by(ActiveSignalMessage.created_at.desc())
                    .limit(max(1, int(limit)))
                )
            ).all()

            for msg_row, sig_row, telegram_uid in rows:
                try:
                    sid = str(getattr(sig_row, "signal_id", "") or "")
                    if not sid:
                        msg_row.is_active = False
                        deactivated += 1
                        continue

                    created_at = getattr(sig_row, "created_at", None)
                    if created_at is not None and getattr(created_at, "tzinfo", None) is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)

                    has_outcome = (
                        await session.execute(
                            select(Outcome.id).where(Outcome.signal_id == sid).limit(1)
                        )
                    ).scalar_one_or_none() is not None

                    if has_outcome or bool(getattr(sig_row, "expired", False)) or (created_at is not None and created_at < cutoff):
                        try:
                            await bot_obj.edit_message_reply_markup(
                                chat_id=int(msg_row.chat_id),
                                message_id=int(msg_row.message_id),
                                reply_markup=None,
                            )
                        except Exception:
                            pass
                        msg_row.is_active = False
                        deactivated += 1
                        continue

                    payload = await _load_signal_payload(sid)
                    if not payload:
                        payload = {
                            "signal_id": sid,
                            "asset": getattr(sig_row, "asset", ""),
                            "timeframe": getattr(sig_row, "timeframe", ""),
                            "direction": getattr(sig_row, "direction", ""),
                            "entry": getattr(sig_row, "entry", None),
                            "stop_loss": getattr(sig_row, "stop_loss", None),
                            "take_profit": getattr(sig_row, "take_profit", None),
                            "score": getattr(sig_row, "score", 0),
                            "rr_ratio": getattr(sig_row, "rr_estimate", None),
                            "regime": getattr(sig_row, "regime", None),
                            "strategy": getattr(sig_row, "strategy_name", None),
                            "created_at": created_at,
                        }

                    user_tier = str(resolve_user_tier(int(telegram_uid)) or "free").lower()
                    display_tier = "vip" if user_tier in ("owner", "admin") else user_tier
                    text = format_signal(payload, user_tier=user_tier, display_tier=display_tier)
                    if not text:
                        continue

                    counts = await _load_signal_engagement_counts(sid)
                    keyboard = _build_signal_keyboard(sid, signal=payload, counts=counts)

                    await bot_obj.edit_message_text(
                        chat_id=int(msg_row.chat_id),
                        message_id=int(msg_row.message_id),
                        text=str(text),
                        parse_mode="HTML",
                        reply_markup=keyboard,
                    )
                    refreshed += 1
                except Exception as exc:
                    if any(
                        token in str(exc).lower()
                        for token in ("message to edit not found", "chat not found", "bot was blocked")
                    ):
                        try:
                            msg_row.is_active = False
                            deactivated += 1
                        except Exception:
                            pass
                    else:
                        logger.debug(f"[refresh_messages] skipped row: {exc}")

            await session.commit()

        logger.info(f"[refresh_messages] startup refresh complete: refreshed={refreshed} deactivated={deactivated}")
    except Exception as exc:
        logger.warning(f"[refresh_messages] startup refresh failed: {exc}")


async def _send_signal_with_engagement_async(
    bot: Bot,
    chat_id: int,
    text: str,
    signal_id: str,
    telegram_user_id: int,
    signal: dict | None = None,
) -> None:
    """Send a signal message with engagement buttons (+ ⚡ MT5 button for PREMIUM+)
    and save message_id to ActiveSignalMessage for live-edit support."""
    counts = await _load_signal_engagement_counts(str(signal_id))
    keyboard = _build_signal_keyboard(str(signal_id), signal=signal, counts=counts)
    try:
        _dispatch_started = time.perf_counter()
        msg = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        try:
            from web.app import telegram_dispatch_latency_seconds
            telegram_dispatch_latency_seconds.labels(status="ok").observe(
                max(0.0, time.perf_counter() - _dispatch_started)
            )
        except Exception:
            pass
        # Persist message location so tiered_executor can live-edit it later
        try:
            from db.session import get_session
            from db.models import ActiveSignalMessage, UserWebhook
            from db.pg_features import get_or_create_user
            import httpx
            from sqlalchemy import select
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            global _vip_webhook_client
            async with get_session() as session:
                user = await get_or_create_user(session, telegram_user_id=int(telegram_user_id))
                stmt = pg_insert(ActiveSignalMessage).values(
                    user_id=user.id,
                    signal_id=str(signal_id),
                    chat_id=int(chat_id),
                    message_id=int(msg.message_id),
                    is_active=True,
                ).on_conflict_do_update(
                    constraint="uq_active_signal_msg_user_signal",
                    set_={"message_id": int(msg.message_id), "is_active": True},
                )
                await session.execute(stmt)
                # VIP webhook dispatch (best effort, async)
                try:
                    wh_row = (
                        await session.execute(
                            select(UserWebhook).where(
                                UserWebhook.user_id == int(user.id),
                                UserWebhook.is_active.is_(True),
                            )
                        )
                    ).scalars().first()
                    if wh_row and signal:
                        if _vip_webhook_client is None:
                            _vip_webhook_client = httpx.AsyncClient(timeout=8)
                        payload = {
                            "event": "signal",
                            "signal_id": str(signal_id),
                            "user_id": int(telegram_user_id),
                            "asset": signal.get("asset"),
                            "timeframe": signal.get("timeframe"),
                            "direction": signal.get("direction"),
                            "entry": signal.get("entry"),
                            "stop_loss": signal.get("stop_loss"),
                            "take_profit": signal.get("take_profit"),
                            "score": signal.get("score"),
                            "ml_probability": signal.get("ml_probability"),
                        }
                        headers = {}
                        if getattr(wh_row, "secret_token", None):
                            headers["X-SignalRank-Signature"] = str(wh_row.secret_token)
                        resp = await _vip_webhook_client.post(str(wh_row.webhook_url), json=payload, headers=headers)
                        if int(resp.status_code) >= 400:
                            logger.warning(
                                "[vip_webhook] non-2xx user=%s status=%s url=%s",
                                telegram_user_id,
                                resp.status_code,
                                wh_row.webhook_url,
                            )
                except Exception as _wh_exc:
                    logger.debug(f"[vip_webhook] dispatch failed for user={telegram_user_id}: {_wh_exc}")
                await session.commit()
        except Exception as _e:
            logger.debug(f"[engage] Failed to save ActiveSignalMessage: {_e}")
    except Exception:
        try:
            from web.app import telegram_dispatch_latency_seconds
            telegram_dispatch_latency_seconds.labels(status="fallback").observe(
                max(0.0, time.perf_counter() - _dispatch_started)
            )
        except Exception:
            pass
        # Fallback: send without buttons so the signal still reaches the user
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")


def _send_signal_with_engagement_sync(
    bot: Bot,
    chat_id: int,
    text: str,
    signal_id: str,
    telegram_user_id: int,
    signal: dict | None = None,
) -> None:
    """Sync wrapper for _send_signal_with_engagement_async."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        run_sync(_send_signal_with_engagement_async(
            bot, int(chat_id), str(text), str(signal_id), int(telegram_user_id), signal
        ))
        return
    try:
        loop.create_task(_send_signal_with_engagement_async(
            bot, int(chat_id), str(text), str(signal_id), int(telegram_user_id), signal
        ))
    except Exception as _e:
        logger.debug(f"[send_signal] Failed to schedule engagement send: {_e}")


def _send_message_sync(bot: Bot, chat_id: int, text: str, parse_mode: str | None = None) -> None:
    """Send a Telegram message from sync code.

    python-telegram-bot v20+ uses async methods. The engine and APScheduler jobs
    run in sync contexts, so we bridge with asyncio.
    """

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        run_sync(_send_message_async(bot, int(chat_id), str(text), parse_mode=parse_mode))
        return
    # If we're already in an event loop, schedule it.
    try:
        loop.create_task(_send_message_async(bot, int(chat_id), str(text), parse_mode=parse_mode))
    except Exception as e:
        logger.debug(f"[send_message] Failed to create async task for message: {e}")
        pass


async def _send_message_with_retry(
    bot: Bot,
    chat_id: int,
    text: str,
    parse_mode: str | None = None,
    reply_markup=None,
) -> None:
    """Async send with Telegram flood-control retry and pacing."""
    import asyncio
    from telegram.error import RetryAfter

    import time
    last_heartbeat = time.time()
    while True:
        try:
            now = time.time()
            if now - last_heartbeat > 60:
                print(f"[bot] heartbeat: polling loop running", flush=True)
                last_heartbeat = now
            send_text = str(text)
            if parse_mode and parse_mode.lower().startswith("markdown"):
                from telegram.helpers import escape_markdown
                version = 2 if "v2" in parse_mode.lower() else 1
                send_text = escape_markdown(send_text, version=version)
            await bot.send_message(
                chat_id=int(chat_id),
                text=send_text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
            return
        except RetryAfter as e:
            await asyncio.sleep(float(getattr(e, "retry_after", 1.0) or 1.0))


def _send_message_with_retry_sync(
    bot: Bot,
    chat_id: int,
    text: str,
    parse_mode: str | None = None,
    reply_markup=None,
) -> None:
    """Sync wrapper for _send_message_with_retry, safe in background threads."""
    run_sync(_send_message_with_retry(
        bot,
        int(chat_id),
        str(text),
        parse_mode=parse_mode,
        reply_markup=reply_markup,
    ))


def _audit_handler(command_name: str, handler):
    async def _inner(update, context):
        # IMPORTANT: Skip pre-audit for /start.
        # The audit writer creates the user row (via record_bot_event -> get_or_create_user).
        # That would make start_command see the user as "not new" and prevent referral attribution.
        # start_command already handles user creation + start auditing in a single transaction.
        if str(command_name) == "start":
            return await handler(update, context)

        try:
            from db.session import get_engine_for_event_loop, get_session
            engine = get_engine_for_event_loop()
            if engine is not None and getattr(update, "effective_user", None) is not None:
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
        try:
            return await handler(update, context)
        except Exception as _cmd_err:
            # Detect DB/connection errors and give the user actionable feedback
            # instead of silent failure.
            _err_lower = str(_cmd_err).lower()
            _is_db_err = any(kw in _err_lower for kw in (
                "connection refused", "could not connect", "no route to host",
                "password authentication failed", "database error",
                "asyncpg", "operational error", "connection pool",
                "ssl", "timeout expired", "could not translate host",
            ))
            if _is_db_err:
                try:
                    if getattr(update, "message", None):
                        await update.message.reply_text(
                            "⚠️ Database connection error. Please try again later."
                        )
                except Exception:
                    pass
            else:
                raise  # Let the on_error handler log unexpected errors

    return _inner


def _require_telegram_token() -> str:
    # Always use centralized config for secrets
    token = getattr(config, 'TELEGRAM_BOT_TOKEN', None)
    if token:
        return token
    raise RuntimeError(
        "TELEGRAM_BOT_TOKEN is not set in config. "
        "Set it as an environment variable or in your .env file."
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
        # Multi-TP/Partial Exit Support
        tp_levels = strategy.get('tp_levels') or strategy.get('take_profit') or []
        if isinstance(tp_levels, str):
            import ast
            try:
                tp_levels = ast.literal_eval(tp_levels)
            except Exception:
                tp_levels = []
        if isinstance(tp_levels, (float, int)):
            tp_levels = [tp_levels]

        entry = float(strategy.get('entry', 0))
        direction = str(strategy.get('direction', '')).lower()
        # For each TP, check if it was hit and not yet notified
        trade_id = strategy.get('trade_id')
        notified_tps = set(strategy.get('notified_tps', []))

        # --- Outcome notification and feedback prompt ---
        # After sending outcome notification, prompt for feedback (premium/vip only)
        from db.session import get_session, get_engine_for_event_loop
        from db.pg_features import get_user_performance_30d
        import asyncio
        tier_for_feedback = user_tier
        if get_engine_for_event_loop() is not None and user_tier in ("premium", "vip"):
            async def _notify_and_feedback():
                async with get_session() as session:
                    perf = await get_user_performance_30d(session, int(user_id))
                    # Send tailored follow-up/advisory
                    summary = (
                        f"\n\n📈 30D Performance:\n"
                        f"Signals: {perf['total']} | Win Rate: {perf['win_rate']*100:.1f}% | NetR: {perf['net_r'] or 0:.2f}R\n"
                        f"Profit/Loss: {perf['profit_loss_pct']:.2f}%"
                    ) if perf['total'] else ""
                    # Send feedback prompt
                    feedback_msg = (
                        f"\n\nWe value your feedback!\nReply with /feedback {strategy.get('signal_id','')} <rating 1-5|issue> [comment]"
                    )
                    try:
                        await bot.send_message(chat_id=user_id, text=summary + feedback_msg)
                    except Exception as e:
                        logger.warning(f"[notify] Failed to send feedback message to user {user_id}: {e}")
                        pass
            try:
                run_sync(_notify_and_feedback())
            except Exception as e:
                logger.warning(f"[notify] Failed to run notify and feedback: {e}")
                pass

        # Determine which TP(s) to notify
        tp_hit = strategy.get('tp_hit')  # e.g., [1,2] if TP1 and TP2 hit
        if tp_hit is None:
            # Fallback: if result == 'tp', treat as full TP3; if 'partial_tp', as TP1
            if result == 'tp':
                tp_hit = [3]
            elif result == 'partial_tp':
                tp_hit = [1]
            else:
                tp_hit = []
        if isinstance(tp_hit, int):
            tp_hit = [tp_hit]

        for tp_level in tp_hit:
            if tp_level in notified_tps:
                continue  # Already notified
            # Calculate profit percentage for this TP
            tp_price = None
            if tp_levels and len(tp_levels) >= tp_level:
                tp_price = float(tp_levels[tp_level-1])
            else:
                tp_price = float(strategy.get(f'tp{tp_level}', 0))
            if entry > 0 and tp_price > 0:
                if direction == 'long':
                    profit_pct = ((tp_price - entry) / entry) * 100
                else:
                    profit_pct = ((entry - tp_price) / entry) * 100
            else:
                profit_pct = float(strategy.get('percent', 0))
            msg = _tier_notifier.format_tp_hit_notification(strategy, user_tier, tp_level, profit_pct)
            # Send notification
            _send_message_sync(bot, chat_id=user_id, text=msg)
            # Mark as notified (update DB or in-memory as needed)
            notified_tps.add(tp_level)
            # Optionally update Trade.partial_exits in DB here

        # SL notification
        if result == 'sl':
            loss_pct = float(strategy.get('percent', 0))
            if loss_pct > 0:
                loss_pct = -loss_pct  # Make it negative
            msg = _tier_notifier.format_sl_hit_notification(strategy, user_tier, loss_pct)
            _send_message_sync(bot, chat_id=user_id, text=msg)

        # Invalidation notification
        if result == 'invalid':
            msg = _tier_notifier.format_signal_update(
                strategy,
                user_tier,
                'invalidated',
                {'reason': strategy.get('reason', 'Market conditions changed')}
            )
            _send_message_sync(bot, chat_id=user_id, text=msg)

        # Free limited notification
        if result == 'free_limited' and user_tier == 'free':
            msg = (
                "🔒 FREE USER (LIMITED OUTCOME MESSAGE)\n"
                "📊 SIGNAL UPDATE\n\n"
                "A recent trade reached its target.\n\n"
                "Upgrade to Premium to see:\n"
                "• Exact entries & exits\n"
                "• Full performance stats\n"
                "• Real-time alerts"
            )
            _send_message_sync(bot, chat_id=user_id, text=msg)
        elif result == 'free_limited':
            msg = "📊 Trade update."
            _send_message_sync(bot, chat_id=user_id, text=msg)

        if not tp_hit and result not in ('sl', 'invalid', 'free_limited'):
            # Fallback generic notification
            msg = "[Outcome] Trade update."
            _send_message_sync(bot, chat_id=user_id, text=msg)

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
            _send_message_sync(bot, chat_id=user_id, text=msg)
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
    
    _send_message_sync(bot, chat_id=user_id, text=msg)

def notify_all_users_trade_outcome(strategy, result, ret, user_ids=None):
    bot = Bot(token=_require_telegram_token())
    if user_ids is None:
        user_ids = get_all_user_ids_compat()
    # Use the same message format as notify_trade_outcome, but for all users
    for uid in user_ids:
        notify_trade_outcome(uid, strategy, result, ret)
        try:
            import asyncio
            run_sync(asyncio.sleep(0.5))
        except Exception:
            pass

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
    _send_message_sync(bot, chat_id=user_id, text=msg)

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

def _format_free_delayed_digest(items: list) -> str:
    """Format a list of free-tier delayed signal queue items into a Telegram message.

    Each item is a dict with keys: id, signal_id, asset, timeframe, direction, score.
    """
    if not items:
        return "📊 No signals available right now."

    lines = [
        f"📊 *SignalRankAI — Daily Signal Digest*",
        f"_{len(items)} signal(s) selected for you today_\n",
    ]
    for i, item in enumerate(items, 1):
        asset     = str(item.get("asset") or "")
        tf        = str(item.get("timeframe") or "")
        direction = str(item.get("direction") or "").upper()
        score     = int(item.get("score") or 0)
        sig_ref   = str(item.get("signal_id") or "")[:8]
        arrow     = "📈" if direction == "LONG" else "📉"
        lines.append(
            f"{i}. {arrow} *{asset}* · `{tf}`\n"
            f"   Direction: {direction}\n"
            f"   Ref: `{sig_ref}` · Score: {score}/100"
        )

    lines.append(
        "\n🔒 _Upgrade to Premium for exact entry, stop-loss & take-profit levels._\n"
        "Use /upgrade to subscribe."
    )
    return "\n\n".join(lines)


def _is_free_fomo_dispatch_only_enabled() -> bool:
    """When enabled, FREE delivery is unlocked by VIP TP1 events (no random delay queue)."""
    try:
        # Default OFF: free users should receive realtime limited-detail signals.
        raw = str(os.getenv("FREE_FOMO_DISPATCH_ONLY", "0") or "0").strip().lower()
        return raw in {"1", "true", "yes", "on"}
    except Exception:
        return False


# ============================================================================
# APSCHEDULER JOBS REGISTRATION
# ============================================================================
# Register scheduled jobs with the BackgroundScheduler during bot initialization.
# These jobs are added in run_bot() after the application is built.

def _schedule_bot_jobs(scheduler: BackgroundScheduler) -> None:
    """Register all scheduled jobs with the BackgroundScheduler.
    
    This function is called during run_bot() initialization to set up
    recurring jobs for signal distribution and system maintenance.
    
    Note: Functions are referenced directly since they're defined in this same module.
    """
    # CRITICAL: FREE signal distribution job - runs every 30 minutes
    # This distributes random signals from the global pool to FREE tier users
    try:
        scheduler.add_job(
            distribute_random_signals_to_free_users_job,
            "interval",
            minutes=30,
            id="free_signal_distribution",
            replace_existing=True,
            max_instances=1,
        )
        logger.info("[sched] Registered: free_signal_distribution (every 30min)")
    except Exception as e:
        logger.warning(f"[sched] Could not add free_signal_distribution job: {e}")
    
    # Resend unsent signals job - runs every 15 minutes
    try:
        scheduler.add_job(
            resend_unsent_signals_job,
            "interval",
            minutes=15,
            id="resend_unsent_signals",
            replace_existing=True,
            max_instances=1,
        )
        logger.info("[sched] Registered: resend_unsent_signals (every 15min)")
    except Exception as e:
        logger.warning(f"[sched] Could not add resend_unsent_signals job: {e}")
    
    # Daily subscription downgrade check - runs at midnight UTC
    try:
        scheduler.add_job(
            downgrade_expired_subscriptions_job,
            "cron",
            hour=0,
            minute=0,
            id="downgrade_expired_subscriptions",
            replace_existing=True,
            max_instances=1,
        )
        logger.info("[sched] Registered: downgrade_expired_subscriptions (daily at midnight UTC)")
    except Exception as e:
        logger.warning(f"[sched] Could not add downgrade_expired_subscriptions job: {e}")
    
    # Weekly old signals cleanup - runs every Sunday at 3am UTC
    try:
        scheduler.add_job(
            auto_delete_old_signals_job,
            "cron",
            day_of_week="sun",
            hour=3,
            minute=0,
            id="auto_delete_old_signals",
            replace_existing=True,
            max_instances=1,
        )
        logger.info("[sched] Registered: auto_delete_old_signals (weekly Sunday 3am UTC)")
    except Exception as e:
        logger.warning(f"[sched] Could not add auto_delete_old_signals job: {e}")
    
    logger.info("[sched] All scheduled jobs registered successfully")


def _format_free_fomo_unlock_message(signal: dict) -> str:
    asset = str(signal.get("asset") or signal.get("symbol") or "MARKET").upper()
    timeframe = str(signal.get("timeframe") or "").lower() or "signal"
    direction = str(signal.get("direction") or "").upper() or "TRADE"
    return (
        "🔥 <b>VIP just hit TP1</b>\n\n"
        f"📣 Momentum alert on <b>{asset}</b> ({timeframe}, {direction}).\n"
        "🎁 We unlocked this setup for FREE users right now.\n\n"
        "Tap below to monitor it live."
    )


def _count_signals_sent_today_sync(telegram_user_id: int) -> int:
    """Count today's delivered signals for a user from Postgres."""
    try:
        from db.session import get_session
        from db.pg_features import count_signals_sent_today

        async def _count() -> int:
            async with get_session() as session:
                v = await count_signals_sent_today(session, int(telegram_user_id))
                await session.commit()
                return int(v or 0)

        return int(run_sync(_count()) or 0)
    except Exception:
        return 0


def _dispatch_free_fomo_unlock_for_signal(signal: dict) -> int:
    """Instant FREE dispatch trigger fired by VIP TP1 events."""
    if not _is_free_fomo_dispatch_only_enabled():
        return 0

    signal_id = str(signal.get("signal_id") or "").strip()
    if not signal_id:
        return 0

    try:
        if state.get_killswitch_sync().enabled:
            return 0
    except Exception:
        pass

    try:
        from db.pg_compat import get_all_user_ids_compat
        from signalrank_telegram.access import resolve_user_tier
        from core.tier_constants import TIER_DAILY_LIMITS

        all_users = list(get_all_user_ids_compat() or [])
        free_users: list[int] = []

        for uid in all_users:
            try:
                uid_i = int(uid)
                if str(resolve_user_tier(uid_i) or "free").lower() != "free":
                    continue
                daily_limit = int(TIER_DAILY_LIMITS.get("free", 3) or 3)
                already_sent = int(_count_signals_sent_today_sync(uid_i) or 0)
                if already_sent >= daily_limit:
                    continue
                free_users.append(uid_i)
            except Exception:
                continue

        if not free_users:
            return 0

        from db.session import get_session

        async def _reserve_recipients() -> list[int]:
            from db.pg_features import record_signal_delivery
            reserved: list[int] = []
            async with get_session() as session:
                for uid in free_users:
                    ok = await record_signal_delivery(
                        session,
                        telegram_user_id=int(uid),
                        signal_id=str(signal_id),
                        tier_at_send="free_fomo",
                    )
                    if ok:
                        reserved.append(int(uid))
                await session.commit()
            return reserved

        recipients = run_sync(_reserve_recipients())
        if not recipients:
            return 0

        bot = Bot(token=_require_telegram_token())
        unlock_msg = _format_free_fomo_unlock_message(signal)
        sent = 0

        for uid in recipients:
            try:
                _send_message_with_retry_sync(bot, chat_id=int(uid), text=unlock_msg, parse_mode="HTML")
                if _deliver_or_update_signal_sync(
                    bot,
                    telegram_user_id=int(uid),
                    signal=dict(signal or {}),
                    display_tier="free",):
                # Global fix: escape text for Markdown/MarkdownV2 parse modes
                    send_text = str(text)
                if parse_mode and parse_mode.lower().startswith("markdown"):
                    try:
                        from telegram.helpers import escape_markdown
                        version = 2 if "v2" in parse_mode.lower() else 1
                        send_text = escape_markdown(send_text, version=version)
                    except Exception:
                        pass
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    run_sync(_send_message_async(bot, int(chat_id), send_text, parse_mode=parse_mode, telemetry_started_at=time.perf_counter(), telemetry_tier=tier, telemetry_regime=regime))
                    return
                # If we're already in an event loop, schedule it.
                try:
                    loop.create_task(_send_message_async(bot, int(chat_id), send_text, parse_mode=parse_mode, telemetry_started_at=time.perf_counter(), telemetry_tier=tier, telemetry_regime=regime))
                except Exception as e:
                    logger.debug(f"[send_message] Failed to create async task for message: {e}")
                    pass
            except Exception as e:
                logger.debug(f"[fomo_free] Failed to send free fomo message to user {uid}: {e}")
                continue
        if sent:
            logger.info(f"[fomo_free] dispatched signal={signal_id[:8]} to free_users={sent}")
        return int(sent)
    except Exception as exc:
        logger.debug(f"[fomo_free] dispatch failed signal={signal_id[:8]} err={exc}")
        return 0


async def dispatch_signals_async(strategy_signals, user_id, regime=None):
    """Dispatch signals to user based on their tier.
    
    Tier-based Limits & Score Filtering:
    - OWNER: VIP-equivalent stream (30/day, same selection as VIP)
    - ADMIN: VIP-equivalent stream (30/day, same selection as VIP)
    - VIP: 30 signals/day (score >= 72 only, real-time)
    - PREMIUM: 10 signals/day (score 55-80, real-time)
    - FREE: 3 random signals/day (no default delay, bot picks any from global pool)
    - EXTRA: 1 signal per purchase (highest scoring available, real-time)
    
    FREE tier: Bot queues ALL generated signals to global pool, then randomly 
    distributes to FREE users (different users get different signals).
    
    EXTRA signals: When FREE users buy extra signals, they get the highest scoring
    ongoing signal that hasn't been sent to them yet.
    
    Outcomes are sent for ALL signals (crypto and FX) regardless of tier.
    """

    tier_raw = resolve_user_tier(user_id)
    tier = (tier_raw or 'FREE').strip().lower()
    routing_tier = _normalized_delivery_tier(tier)
    try:
        from signalrank_telegram.tier_delivery import TierDeliveryManager
        delivery_mgr = TierDeliveryManager()
    except Exception:
        delivery_mgr = None

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
    except Exception as e:
        logger.debug(f"[dispatch] Failed to check killswitch: {e}")
        pass

    # Support passing ranked buckets (vip/premium/free)
    signals_list = []
    if isinstance(strategy_signals, dict):
        vip_list = list(strategy_signals.get('vip', []) or [])
        prem_list = list(strategy_signals.get('premium', []) or [])
        # Keep upstream ranking intent, then apply canonical tier gates below.
        signals_list = (vip_list + prem_list)
    else:
        signals_list = list(strategy_signals or [])

    # Canonical tier quality gate: enforce per-tier score thresholds centrally,
    # independent of caller/source (engine, resend, callbacks, etc.).
    if delivery_mgr is not None:
        gated_signals: list[dict] = []
        for _sig in (signals_list or []):
            try:
                _score = float((_sig or {}).get('score', 0) or 0)
                if delivery_mgr.should_send_signal(routing_tier, _score, user_id=None):
                    gated_signals.append(_sig)
            except Exception:
                continue
        signals_list = gated_signals

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

    # --- FRESHNESS FILTERING ---
    # Keep this path non-blocking (avoid sync HTTP calls in async dispatch loop).
    try:
        from engine.stale_signal_validator import validate_signal_freshness

        fresh_signals = []
        for sig in signals_list:
            try:
                _cached_price = sig.get("current_price")
                _cached_price = float(_cached_price) if _cached_price is not None else None
            except Exception:
                _cached_price = None

            is_fresh, reason, live_price = await validate_signal_freshness(
                sig,
                cached_live_price=_cached_price,
            )
            if not is_fresh:
                sig_id = sig.get('signal_id') or sig.get('id', 'unknown')
                asset = sig.get('asset', 'unknown')
                logger.info(f"[dispatch] Filtered stale signal {sig_id} for user {user_id}: asset={asset} reason={reason}")
            else:
                if live_price is not None:
                    sig["current_price"] = float(live_price)
                fresh_signals.append(sig)
        
        signals_list = fresh_signals
        
        if not signals_list:
            logger.info(f"[dispatch] All signals filtered as stale for user {user_id}")
            return
    except Exception as e:
        logger.warning(f"[dispatch] Freshness filtering failed for user {user_id}: {e}")
        # Continue with unfiltered signals on error

    try:
        original_count = len(signals_list)
        signals_list = _collapse_signal_variants(signals_list)
        dropped_count = max(0, original_count - len(signals_list))
        if dropped_count:
            logger.info(f"[dispatch] user={user_id} dropped {dropped_count} lower-ROI duplicate signal variants")
    except Exception as e:
        logger.debug(f"[dispatch] signal collapse failed for user {user_id}: {e}")

    # Entry validation: check that current price is within entry zone (±3%)
    # Add entry_status flag to track if entry has been hit or is pending
    def _check_entry_status(signal: dict) -> tuple[bool, str]:
        """
        Check if entry is valid and return (allow: bool, status: str).
        Status: "AT_ENTRY" (within ±3%), "PENDING_ENTRY" (outside ±3%), "UNKNOWN"

        Uses signal["current_price"] when already enriched by a prior
        enrich_signal_with_live_price() / stale-validator step to avoid a
        blocking HTTP call from within the dispatch path.
        """
        try:
            asset = str(signal.get("asset") or "").upper()
            entry = float(signal.get("entry") or 0.0)
            if not asset or entry <= 0:
                return True, "UNKNOWN"

            # Prefer the cached price already attached to the signal dict.
            # This is set by:
            #   - engine/core.py deliver_all() after batch price fetch (P7)
            #   - engine/price_validator.enrich_signal_with_live_price()
            cached = signal.get("current_price") or signal.get("live_price")
            if cached:
                try:
                    price = float(cached)
                    if price > 0:
                        price_distance_pct = abs(price - entry) / entry * 100.0
                        return True, "AT_ENTRY" if price_distance_pct <= 3.0 else "PENDING_ENTRY"
                except Exception:
                    pass

            # Do not perform blocking network calls in this synchronous dispatch path.
            # If no cached price is available, keep status as UNKNOWN.
            try:
                is_crypto = asset.endswith(("USDT", "USDC", "BTC", "ETH", "BNB"))
                if not is_crypto:
                    return True, "UNKNOWN"
                return True, "UNKNOWN"
            except Exception:
                return True, "UNKNOWN"
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

    # Dispatch diagnostics (debug-level only)
    try:
        logger.debug(f"[dispatch] User {user_id} tier={tier} signals_list={len(signals_list)}")
        for sig in signals_list:
            logger.debug(f"[dispatch] Preparing to send signal: {sig.get('asset')} {sig.get('timeframe')} score={sig.get('score')} id={sig.get('signal_id', 'n/a')}")
    except Exception as e:
        logger.debug(f"[dispatch] Error in debug logging: {e}")

    # Postgres-backed delivery dedup + history (preferred)
    try:
        from db.session import get_engine_for_event_loop, get_session
        engine = get_engine_for_event_loop()

        if engine is not None:
            effective_tier = routing_tier
            display_tier = routing_tier
            
            # OWNER and ADMIN always get VIP format for ALL notifications
            if tier == 'free' and extra_left > 0:
                effective_tier = 'premium'
                display_tier = 'premium'


            if effective_tier in ('premium', 'vip'):
                bot = Bot(token=_require_telegram_token())
                limit = TIER_LIMITS.get(routing_tier, 0)
                if tier == 'free' and extra_left > 0:
                    limit = min(int(max(1, extra_left)), len(signals_list))

                async def _reserve() -> list[dict]:
                    from db.pg_features import get_or_create_signal, record_signal_delivery
                    from db.pg_features import count_signals_sent_today
                    from core.tier_constants import TIER_DAILY_LIMITS

                    to_send: list[dict] = []
                    async with get_session() as session:
                        daily_limit = TIER_DAILY_LIMITS.get(
                            str(effective_tier),
                            TIER_DAILY_LIMITS.get("free", 3),
                        )
                        already_sent_today = int(
                            await count_signals_sent_today(session, int(user_id))
                        )
                        for signal in signals_list[: max(0, int(limit))]:
                            if daily_limit != float('inf') and (already_sent_today + len(to_send)) >= int(daily_limit):
                                break
                            try:
                                _score = float((signal or {}).get('score', 0) or 0)
                                if delivery_mgr is not None and not delivery_mgr.should_send_signal(
                                    str(effective_tier),
                                    _score,
                                    user_id=None,
                                ):
                                    continue
                            except Exception:
                                continue
                            if await _is_asset_delivery_locked(
                                int(user_id),
                                str(signal.get('asset') or signal.get('symbol') or ''),
                            ):
                                logger.debug(
                                    f"[dispatch] asset lock skip user={user_id} "
                                    f"asset={signal.get('asset') or signal.get('symbol')}"
                                )
                                continue
                            s = await get_or_create_signal(session, signal)
                            logger.debug(f"[db] Attempting to record delivery: user={user_id} signal_id={s.signal_id} tier={effective_tier}")
                            ok = await record_signal_delivery(
                                session,
                                telegram_user_id=int(user_id),
                                signal_id=str(s.signal_id),
                                tier_at_send=str(effective_tier),
                            )
                            logger.debug(f"[db] record_signal_delivery result: {ok}")
                            if not ok:
                                continue
                            payload = dict(signal)
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
                    reserved = await _reserve()
                    reserve_failed = False
                except Exception as e:
                    reserved = []
                    reserve_failed = True
                    logger.debug(f"[db] dispatch reserve failed (falling back to direct send): {type(e).__name__}: {e}")

                if not reserved and not reserve_failed:
                    logger.warning(
                        "[dispatch] reservation returned no signals for user=%s tier=%s; falling back to direct send",
                        user_id,
                        routing_tier,
                    )
                    reserve_failed = True

                logger.debug(f"[dispatch] user={user_id} tier={tier} effective_tier={effective_tier} signals={len(signals_list)} limit={int(limit)} reserved={len(reserved)} reserve_failed={int(reserve_failed)}")

                if reserve_failed:
                    async def _reserve_one(_signal: dict) -> dict | None:
                        from db.pg_features import get_or_create_signal, record_signal_delivery

                        async with get_session() as session:
                            s = await get_or_create_signal(session, _signal)
                            ok = await record_signal_delivery(
                                session,
                                telegram_user_id=int(user_id),
                                signal_id=str(s.signal_id),
                                tier_at_send=str(effective_tier),
                            )
                            if not ok:
                                await session.rollback()
                                return None

                            payload = dict(_signal)
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
                            await session.commit()
                            return payload

                    sent = 0
                    for signal in signals_list:
                        if sent >= int(limit):
                            break
                        try:
                            reserved_signal = await _reserve_one(signal)
                            if not reserved_signal:
                                logger.debug(
                                    "[dispatch] Fallback dedupe skip: user=%s signal=%s",
                                    user_id,
                                    signal.get('signal_id', 'n/a'),
                                )
                                continue

                            logger.debug(f"[dispatch] Fallback direct send: user={user_id} signal={signal.get('asset')} id={signal.get('signal_id', 'n/a')}")
                            if await _deliver_or_update_signal_async(
                                bot,
                                telegram_user_id=int(user_id),
                                signal=reserved_signal,
                                display_tier=display_tier,
                            ):
                                sent += 1
                                try:
                                    _auto_execute_signal_if_enabled(
                                        telegram_user_id=int(user_id),
                                        signal=dict(reserved_signal or {}),
                                        routing_tier=str(effective_tier),
                                    )
                                except Exception:
                                    pass
                            if tier == 'free' and extra_left > 0:
                                try:
                                    state.consume_extra_signals_sync(int(user_id), 1)
                                except Exception as e:
                                    logger.debug(f"[dispatch] Failed to consume extra signal for user {user_id}: {e}")
                                    pass
                        except Exception as e:
                            logger.debug(f"[dispatch] Exception in fallback send: {e}")
                            continue
                    return

                for signal in reserved:
                    try:
                        logger.debug(f"[dispatch] Sending reserved signal: user={user_id} signal={signal.get('asset')} id={signal.get('signal_id', 'n/a')}")
                        _ok_send = await _deliver_or_update_signal_async(
                            bot,
                            telegram_user_id=int(user_id),
                            signal=signal,
                            display_tier=display_tier,
                        )
                        if _ok_send:
                            try:
                                _auto_execute_signal_if_enabled(
                                    telegram_user_id=int(user_id),
                                    signal=dict(signal or {}),
                                    routing_tier=str(effective_tier),
                                )
                            except Exception:
                                pass
                        if tier == 'free' and extra_left > 0:
                            try:
                                state.consume_extra_signals_sync(int(user_id), 1)
                            except Exception as e:
                                logger.debug(f"[dispatch] Failed to consume extra signal for user {user_id}: {e}")
                                pass
                    except Exception as e:
                        logger.debug(f"[dispatch] Exception in reserved send: {e}")
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
                            try:
                                _best_score = float(getattr(best_sig, 'score', 0) or 0)
                                if delivery_mgr is not None and not delivery_mgr.should_send_signal(
                                    'premium',
                                    _best_score,
                                    user_id=int(user_id),
                                ):
                                    continue
                            except Exception:
                                continue
                            
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
                                except Exception as e:
                                    logger.debug(f"[dispatch] Failed to parse TP levels: {e}")
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
                                    signal_display_tier = 'vip' if tier in ('owner', 'admin') else 'premium'
                                    if await _deliver_or_update_signal_async(
                                        bot,
                                        telegram_user_id=int(user_id),
                                        signal=sig_dict,
                                        display_tier=signal_display_tier,
                                    ):
                                        sent_count += 1
                                        state.consume_extra_signals_sync(int(user_id), 1)
                                except Exception as e:
                                    logger.warning(f"[dispatch] Failed to send extra signal to user {user_id}: {e}")
                                    pass
                        await session.commit()
                        return sent_count
                
                try:
                    await _get_best_signal()
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
                    
                    # Check how many signals user already received today from DB
                    from core.tier_constants import TIER_DAILY_LIMITS
                    from db.pg_features import count_signals_sent_today
                    
                    signals_sent_today = int(
                        await count_signals_sent_today(session, int(user_id))
                    )
                    
                    # Use resolved tier from function entry to avoid sync lookup in async path.
                    user_tier_actual = str(tier or "free").lower()
                    
                    # Get tier limit from constants
                    daily_limit = TIER_DAILY_LIMITS.get(
                        user_tier_actual,
                        TIER_DAILY_LIMITS.get("free", 3),
                    )
                    remaining = max(0, daily_limit - signals_sent_today) if daily_limit != float('inf') else 999
                    
                    if remaining <= 0:
                        logger.info(f"[bot] daily limit reached for user={user_id} tier={user_tier_actual} sent={signals_sent_today}")
                        return  # Already hit daily limit
                    
                    # Get one random available signal at a time to avoid burst delivery.
                    available_signals = await get_random_available_signals_for_free_user(
                        session, int(user_id), limit=1
                    )
                    
                    if not available_signals:
                        return  # No signals available
                    
                    # Send each signal
                    for sig in available_signals:
                        try:
                            _free_score = float(getattr(sig, 'score', 0) or 0)
                            if delivery_mgr is not None and not delivery_mgr.should_send_signal(
                                'free',
                                _free_score,
                                user_id=int(user_id),
                            ):
                                continue
                        except Exception:
                            continue
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
                            except Exception as e:
                                logger.debug(f"[dispatch] Failed to parse TP levels: {e}")
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
                                signal_display_tier = 'vip' if tier in ('owner', 'admin') else 'free'
                                if not await _deliver_or_update_signal_async(
                                    bot,
                                    telegram_user_id=int(user_id),
                                    signal=sig_dict,
                                    display_tier=signal_display_tier,
                                ):
                                    continue
                            except Exception as e:
                                logger.debug(f"[dispatch] Failed to track signal delivery in Redis: {e}")
                                pass
                    
                    await session.commit()

            # In production, FREE delivery should be driven by queued scheduler jobs
            # (distribute_random_signals_to_free_users_job + resend job) to keep timing
            # randomized and prevent burst/spam behavior from engine dispatch loops.
            if str(os.getenv("FREE_DIRECT_DISPATCH", "1")).strip().lower() in {"1", "true", "yes"}:
                try:
                    await _send_random_signals_immediately()
                    return
                except Exception as e:
                    _log_once(
                        "free_random_send_failed",
                        f"[bot] free random signal delivery failed: {type(e).__name__}: {e}",
                    )
            return
    except Exception as e:
        _log_once(
            "dispatch_pg_path_failed",
            f"[bot] dispatch postgres path failed: {type(e).__name__}: {e}",
        )

    if routing_tier in ('premium', 'vip'):
        from core.tier_constants import TIER_DAILY_LIMITS

        # Check daily limit from DB deliveries
        signals_sent_today = int(_count_signals_sent_today_sync(int(user_id)) or 0)
        
        daily_limit = TIER_DAILY_LIMITS.get(
            routing_tier,
            TIER_DAILY_LIMITS.get("free", 3),
        )
        
        if signals_sent_today >= daily_limit:
            logger.info(f"[bot] daily limit reached for user={user_id} tier={tier} sent={signals_sent_today}")
            return
        
        bot = Bot(token=_require_telegram_token())
        limit = TIER_LIMITS.get(routing_tier, 0)
        sent = 0
        display_tier = routing_tier
        for signal in signals_list:
            # Check if we've hit the daily limit
            if signals_sent_today + sent >= daily_limit:
                break
            if sent >= limit:
                break
            try:
                if not await _deliver_or_update_signal_async(
                    bot,
                    telegram_user_id=int(user_id),
                    signal=signal,
                    display_tier=display_tier,
                ):
                    continue
                try:
                    _auto_execute_signal_if_enabled(
                        telegram_user_id=int(user_id),
                        signal=dict(signal or {}),
                        routing_tier=str(routing_tier),
                    )
                except Exception:
                    pass
                sent += 1
            except Exception as e:
                logger.warning(f"[dispatch] Failed to dispatch signal to user {user_id}: {e}")
                continue
        return

    # FREE: queue delayed summary (legacy mode).
    # Default is FOMO unlock dispatch on VIP TP1 events.
    try:
        if _is_free_fomo_dispatch_only_enabled():
            logger.debug(f"[dispatch] free queue skipped (FREE_FOMO_DISPATCH_ONLY=1) user={user_id}")
            return

        from db.session import get_engine_for_event_loop, get_session
        engine = get_engine_for_event_loop()
        if engine is None:
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
            await _queue()
        except Exception as e:
            _log_once(
                "queue_free_legacy_failed",
                f"[bot] queue free (legacy path) failed: {type(e).__name__}: {e}",
            )
    except Exception:
        # As a last resort, send the limited preview
        try:
            bot = Bot(token=_require_telegram_token())
            await _send_message_async(bot, chat_id=user_id, text=_format_free_preview(signals_list[0]))
        except Exception as e:
            logger.warning(f"[dispatch] Failed to send free preview to user {user_id}: {e}")
            pass


def dispatch_signals(strategy_signals, user_id, regime=None):
    return run_sync(dispatch_signals_async(strategy_signals, user_id, regime=regime))


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

        run_sync(_do_downgrade())
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

        run_sync(_do_delete())
    except Exception as e:
        logger.error(f"❌ Error deleting old signals: {e}")


def distribute_random_signals_to_free_users_job():
    """Periodic job: distribute random signals to FREE users from global pool.
    
    CRITICAL: This job ALWAYS runs to distribute signals to FREE users.
    The FREE_FOMO_DISPATCH_ONLY mode is an alternative that unlocks signals
    on VIP TP1 events, but the regular queue distribution should still work.
    """
    # NOTE: We intentionally removed the _is_free_fomo_dispatch_only_enabled() check
    # because FREE users need regular signal distribution regardless of FOMO mode.
    # The FOMO mode is for unlocking signals on VIP TP1 events, not for disabling
    # the regular queue distribution.

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

        run_sync(_do_distribute())
    except Exception as e:
        logger.error(f"❌ Error distributing signals to FREE users: {e}")


def refresh_active_signal_keyboards_once() -> None:
    """One-shot migration: refresh keyboards for active unresolved signals.

    - Adds current callback schema to older messages
    - Deactivates rows for resolved/expired/old signals
    """
    try:
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import select
        from db.session import get_session
        from db.models import ActiveSignalMessage, Signal, Outcome

        async def _run() -> None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=1)
            bot = Bot(token=_require_telegram_token())
            async with bot:
                async with get_session() as session:
                    rows = (
                        await session.execute(
                            select(ActiveSignalMessage, Signal)
                            .join(Signal, Signal.signal_id == ActiveSignalMessage.signal_id)
                            .where(ActiveSignalMessage.is_active.is_(True))
                            .limit(500)
                        )
                    ).all()

                    for active_row, sig in rows:
                        try:
                            created = getattr(sig, "created_at", None)
                            if created is None:
                                active_row.is_active = False
                                continue
                            if getattr(created, "tzinfo", None) is None:
                                created = created.replace(tzinfo=timezone.utc)

                            outcome = (
                                await session.execute(
                                    select(Outcome).where(Outcome.signal_id == str(sig.signal_id)).limit(1)
                                )
                            ).scalar_one_or_none()

                            if bool(getattr(sig, "expired", False)) or created < cutoff or outcome is not None:
                                active_row.is_active = False
                                continue

                            signal_payload = await _load_signal_payload(str(sig.signal_id))
                            counts = await _load_signal_engagement_counts(str(sig.signal_id))
                            keyboard = _build_signal_keyboard(str(sig.signal_id), signal=signal_payload, counts=counts)
                            await bot.edit_message_reply_markup(
                                chat_id=int(active_row.chat_id),
                                message_id=int(active_row.message_id),
                                reply_markup=keyboard,
                            )
                        except Exception as exc:
                            if "message is not modified" not in str(exc).lower():
                                logger.debug(f"[backfill] keyboard refresh skipped: {exc}")

                    await session.commit()

        run_sync(_run())
    except Exception as exc:
        logger.debug(f"[backfill] active keyboard backfill failed: {exc}")


_bot_lock_conn = None
_bot_sched_lock_conn = None
_bot_init_lock = threading.Lock()
_bot_init_started = False
_bot_init_started_at = 0.0

# ── Webhook mode module-level state ──────────────────────────────────────────
# When TELEGRAM_USE_WEBHOOK=1, run_bot() stores the fully-configured Application
# here instead of blocking in run_polling().  railway_main.py reads this variable
# after run_bot() returns to obtain the application for process_update() calls.
_webhook_application = None
_webhook_handlers_ready = False
_bot_scheduler = None  # keeps the BackgroundScheduler alive after run_bot() returns
# Public module-level handle used by cross-module senders (e.g. engine outcome
# notifications). Must be assigned during run_bot() startup.
application = None

def run_bot() -> None:

    """Run the Telegram polling bot.

    This must be explicitly invoked (e.g. RUN_MODE=bot or RUN_MODE=all). It must
    not run on import.
    """

    # Default to webhook mode when running on Railway (RAILWAY_SERVICE_NAME is
    # always injected by Railway).  This prevents the bot from falling back to
    # long-polling on Railway where polling is unreliable and fights with the
    # FastAPI webhook route.  Local development is unaffected (no
    # RAILWAY_SERVICE_NAME → polling as before, unless TELEGRAM_USE_WEBHOOK=1
    # is set explicitly).
    if not os.getenv("TELEGRAM_USE_WEBHOOK") and os.getenv("RAILWAY_SERVICE_NAME"):
        os.environ["TELEGRAM_USE_WEBHOOK"] = "1"
        logger.info("[bot] TELEGRAM_USE_WEBHOOK defaulted to 1 (Railway deployment detected)")

    from apscheduler.schedulers.background import BackgroundScheduler

    # Idempotency guard for webhook deployments: if setup already completed in
    # this process, do not create a second scheduler/app instance.
    global _webhook_application, _webhook_handlers_ready, _bot_scheduler, _bot_init_started, _bot_init_started_at, application

    # Hard process-local guard (covers races during startup where run_bot() can
    # be invoked twice before _bot_scheduler is assigned).
    with _bot_init_lock:
        _now = time.monotonic()
        _stale_after = max(10, int(os.getenv("BOT_INIT_STALE_SECONDS", "120") or 120))
        if _bot_init_started:
            _age = float(_now - float(_bot_init_started_at or 0.0))
            # If init is stale and webhook app was never exposed, permit a retry.
            if os.getenv("TELEGRAM_USE_WEBHOOK") and _webhook_application is None and _age >= _stale_after:
                logger.warning(
                    "[bot] init guard stale (age=%.1fs, no webhook app); resetting for retry",
                    _age,
                )
                _bot_init_started = False
            else:
                logger.info("[bot] run_bot init already started; skipping duplicate init")
                return
        if _bot_init_started:
            logger.info("[bot] run_bot init already started; skipping duplicate init")
            return
        _bot_init_started = True
        _bot_init_started_at = _now

    try:
        if os.getenv("TELEGRAM_USE_WEBHOOK") and _webhook_application is not None:
            if _bot_scheduler is not None and bool(getattr(_bot_scheduler, "running", False)):
                _webhook_handlers_ready = True
                logger.info("[bot] run_bot already initialized in webhook mode; skipping duplicate init")
                return
    except Exception:
        pass

    # ── Bulletproof DATABASE_URL validation ─────────────────────────────────
    # Validate DATABASE_URL BEFORE any scheduler job or async session is
    # created.  If it is missing, raise immediately so Railway shows a clear
    # crash message rather than hundreds of "password authentication failed
    # for user 'postgres'" errors from asyncpg falling back to local auth.
    _db_raw = (resolve_database_url(async_driver=True) or "").strip()
    if not _db_raw:
        raise ValueError(
            "[FATAL] DATABASE_URL is not set. "
            "Add it as an environment variable on Railway before deploying."
        )
    # Safe log: print only the host portion, never the password.
    try:
        print(f"[boot] Connecting to DB at: {_mask_db_url_host(_db_raw)}", flush=True)
    except Exception:
        print("[boot] DATABASE_URL is set (host masked)", flush=True)
    # Force the global async engine to re-initialise using the fresh env value.
    # This is needed if session.py was imported before the env var was set
    # (e.g. in a hot-reload scenario) and the cached engine is None.
    try:
        from db.session import _get_global_engine, _global_engine
        if _global_engine is None:
            _get_global_engine()  # triggers engine creation with correct URL
    except Exception as _eng_err:
        print(f"[boot] DB engine init: {_eng_err}", flush=True)
    # ───────────────────────────────────────────────────────────────────────

    # Avoid leaking bot token in logs: httpx logs full request URLs at INFO.
    # We keep errors, but silence INFO/DEBUG.
    try:
        logging.getLogger("httpx").setLevel(logging.WARNING)
    except Exception as e:
        logger.debug(f"[bot] Failed to set httpx logging level: {e}")
        pass
    try:
        logging.getLogger("telegram").setLevel(logging.WARNING)
    except Exception as e:
        logger.debug(f"[bot] Failed to set telegram logging level: {e}")
        pass

    application = (
        Application.builder()
        .token(_require_telegram_token())
        .pool_timeout(TELEGRAM_POOL_TIMEOUT)
        .connect_timeout(TELEGRAM_CONNECT_TIMEOUT)
        .read_timeout(TELEGRAM_READ_TIMEOUT)
        .write_timeout(TELEGRAM_WRITE_TIMEOUT)
        .build()
    )

    # In webhook mode, expose the Application immediately so railway_main can
    # retrieve it even if later optional setup steps fail (scheduler/jobstore,
    # ancillary jobs, etc.). Handlers are registered on the same object below.
    if os.getenv("TELEGRAM_USE_WEBHOOK"):
        _webhook_handlers_ready = False
        _webhook_application = application

    _webhook_mode = bool(os.getenv("TELEGRAM_USE_WEBHOOK"))

    def _refresh_webhook_handlers_ready(stage: str) -> None:
        """Mark webhook handler readiness only when a sufficient handler set is present."""
        global _webhook_handlers_ready
        if not _webhook_mode:
            return
        try:
            handlers_map = getattr(application, "handlers", {}) or {}
            total_handlers = 0
            if isinstance(handlers_map, dict):
                for _group, _lst in handlers_map.items():
                    try:
                        total_handlers += int(len(_lst or []))
                    except Exception:
                        continue
            min_handlers = max(1, int(os.getenv("BOT_WEBHOOK_READY_MIN_HANDLERS", "60") or 60))
            _webhook_handlers_ready = total_handlers >= min_handlers
            logger.info(
                "[bot] webhook handler readiness check: stage=%s total=%s min=%s ready=%s",
                stage,
                total_handlers,
                min_handlers,
                bool(_webhook_handlers_ready),
            )
        except Exception as _ready_err:
            logger.warning("[bot] webhook readiness check failed at stage=%s: %s", stage, _ready_err)


    async def _on_error(update, context) -> None:
        err = getattr(context, "error", None)
        err_text = str(err or "")
        # Harmless Telegram callback race: user tapped an old button and the
        # callback query answer window already expired.
        if (
            "Query is too old" in err_text
            or "response timeout expired" in err_text
            or "query id is invalid" in err_text
        ):
            logger.info("[bot] stale callback ignored: %s", err_text)
            return
        print(f"[bot] error: {err}", flush=True)
        # Alert all owners about every unhandled exception so nothing is silent
        try:
            import traceback
            tb = "".join(traceback.format_exception(type(err), err, err.__traceback__)) if err else "(no traceback)"
            alert = f"🚨 *Bot Error*\n`{type(err).__name__}: {err}`\n\n```\n{tb[:800]}\n```"
            from config import OWNER_IDS
            for _oid in (OWNER_IDS or []):
                try:
                    await application.bot.send_message(
                        chat_id=int(_oid), text=alert, parse_mode="MarkdownV2"
                    )
                except Exception:
                    pass
        except Exception:
            pass  # Never let the error handler itself crash the bot

    application.add_error_handler(_on_error)

    async def _post_init(app):
        # BotFather-visible commands must remain concise.
        _global_cmds = [            ("start", "Start"),
            ("pricing", "Pricing"),
            ("upgrade", "Upgrade / subscribe"),
            ("help", "Commands"),
            ("status", "Subscription status"),
            ("signals", "Latest signals"),
            ("signal", "Signal by reference"),
            ("performance", "Performance"),
            ("invite", "Invite"),
            ("support", "Support"),
        ]
        _premium_cmds = _global_cmds + [
            ("dashboard", "Dashboard"),
            ("history", "Trade history"),
            ("risk", "Risk settings"),
            ("alerts", "Alerts"),
            ("tiers", "Tier comparison"),
            ("mystats", "My P&L stats"),
            ("referral", "Referral link"),
            ("setlot", "Set lot size"),
            ("execution", "Execution mode"),
            ("connect_broker", "Connect MT5 broker"),
            ("mt5_link", "Link MT5 account"),
            ("mt5_status", "MT5 account status"),
        ]
        _vip_cmds = _premium_cmds + [
            ("setrisk", "Set risk %"),
            ("elite", "Elite signals"),
            ("early", "Early access"),
            ("report", "Full report"),
        ]
        _owner_cmds = _vip_cmds + [
            ("unlock", "Owner: unlock tier"),
            ("dev_pause", "Owner: pause engine"),
            ("dev_resume", "Owner: resume engine"),
            ("gemini", "Admin: run Gemini+ML"),
            ("gemini_review", "Admin: Gemini rundown"),
            ("owner_users", "Owner: user list"),
            ("owner_revenue", "Owner: revenue"),
            ("provider_status", "Owner: provider health"),
            ("qa_report", "Owner: QA report"),
        ]
        try:
            from telegram import BotCommandScopeChat
            from signalrank_telegram.access import resolve_user_tier
            from db.pg_compat import get_all_user_ids_compat

            async def _set_per_user_commands() -> None:
                """Set per-user BotCommand scopes respecting the tier hierarchy.

                Runs in a background task so it never blocks _post_init /
                app.initialize() — on large user bases this loop can take
                tens of seconds and would time out the Railway startup
                healthcheck otherwise.
                """
                try:
                    user_ids = get_all_user_ids_compat()
                    for _uid in (user_ids or []):
                        try:
                            _t = (resolve_user_tier(int(_uid)) or "free").lower()
                            if _t in ("owner", "admin"):
                                _cmds = _owner_cmds
                            elif _t == "vip":
                                _cmds = _vip_cmds
                            elif _t == "premium":
                                _cmds = _premium_cmds
                            else:
                                _cmds = _global_cmds
                            await app.bot.set_my_commands(
                                _cmds, scope=BotCommandScopeChat(chat_id=int(_uid))
                            )
                        except Exception:
                            pass
                    logger.info("[bot] per-user command scopes updated for %d users", len(user_ids or []))
                except Exception as _e:
                    logger.warning("[bot] per-user command scope update failed: %s", _e)

            # Schedule as a fire-and-forget background task — does NOT block _post_init
            asyncio.create_task(_set_per_user_commands())
        except Exception as e:
            logger.warning(f"[bot] BotCommandScopeChat update skipped: {e}")
        try:
            await app.bot.set_my_commands(_global_cmds)
        except Exception as e:
            logger.warning(f"[bot] Failed to set bot commands: {e}")
            pass

        # Outcome tracker is worker-owned in monolith runtime.
        logger.info("[bot] RealtimeOutcomeTracker startup skipped (worker-owned)")

        # ── Post-deploy terms blast ───────────────────────────────────────────
        # Set env var TERMS_BLAST_ON_DEPLOY=1 on Railway to automatically send
        # the financial disclaimer to every existing user on this deployment.
        # After the blast runs once, remove the env var to prevent re-blasting.
        if str(os.getenv("TERMS_BLAST_ON_DEPLOY", "0")).strip() in {"1", "true", "yes"}:
            import asyncio as _aio
            async def _auto_blast():
                await _aio.sleep(30)  # Wait 30s for DB connections to settle
                try:
                    from db.session import get_session as _gs_ab
                    from db.models import User as _User_ab
                    from sqlalchemy import select as _sel_ab
                    from telegram import InlineKeyboardMarkup as _IKM_ab, InlineKeyboardButton as _IKB_ab

                    async with _gs_ab() as _session_ab:
                        _result_ab = await _session_ab.execute(
                            _sel_ab(_User_ab.telegram_user_id).where(_User_ab.accepted_terms == False)  # noqa: E712
                        )
                        _pending_ab = [row[0] for row in _result_ab.fetchall()]

                    logger.info(f"[blast_terms] Auto-blast: {len(_pending_ab)} users to notify")
                    _disclaimer_ab = (
                        "⚠️ <b>SignalRankAI - Financial Disclaimer</b>\n\n"
                        "We've updated our terms. Please confirm to continue using the bot:\n\n"
                        "• All signals are for <b>educational purposes only</b>\n"
                        "• Nothing here constitutes financial advice\n"
                        "• Trading involves significant risk; losses can exceed your deposit\n"
                        "• Past performance does not guarantee future results\n"
                        "• You are solely responsible for your trading decisions\n\n"
                        "Tap <b>✅ I Agree</b> to continue."
                    )
                    _kbd_ab = _IKM_ab([[
                        _IKB_ab("✅ I Agree", callback_data="agree_terms"),
                        _IKB_ab("❌ Decline", callback_data="decline_terms"),
                    ]])
                    _sent_ab = 0
                    for _uid_ab in _pending_ab:
                        try:
                            await app.bot.send_message(
                                chat_id=int(_uid_ab),
                                text=_disclaimer_ab,
                                parse_mode="HTML",
                                reply_markup=_kbd_ab,
                            )
                            _sent_ab += 1
                        except Exception:
                            pass
                    logger.info(f"[blast_terms] Auto-blast complete: sent={_sent_ab}/{len(_pending_ab)}")
                except Exception as _be:
                    logger.warning(f"[blast_terms] Auto-blast failed: {_be}")

            _aio.ensure_future(_auto_blast())
            logger.info("[blast_terms] Auto-blast scheduled (30s delay)")

        # ── Post-deploy active-message refresh ───────────────────────────────
        # Re-render old active signal messages with latest template + buttons.
        try:
            import asyncio as _aio_refresh

            async def _refresh_after_boot():
                await _aio_refresh.sleep(20)
                _limit = int(os.getenv("REFRESH_ACTIVE_SIGNAL_LIMIT", "800") or 800)
                await _refresh_active_signal_messages_on_startup(app.bot, limit=_limit)

            _aio_refresh.ensure_future(_refresh_after_boot())
            logger.info("[refresh_messages] startup refresh scheduled")
        except Exception as _r_err:
            logger.warning(f"[refresh_messages] failed to schedule startup refresh: {_r_err}")

    async def _post_stop(app):
        """Gracefully stop background tasks when the bot shuts down."""
        try:
            from engine.realtime_outcome_tracker import outcome_tracker
            await outcome_tracker.stop()
            logger.info("[bot] RealtimeOutcomeTracker stopped")
        except Exception as _e:
            logger.debug(f"[bot] RealtimeOutcomeTracker stop error: {_e}")

    application.post_init = _post_init
    application.post_stop = _post_stop

    application.add_handler(CommandHandler("start", _audit_handler("start", start_command)))
    application.add_handler(CommandHandler("status", _audit_handler("status", status_command)))
    application.add_handler(CommandHandler("help", _audit_handler("help", help_command)))
    application.add_handler(CommandHandler("about", _audit_handler("about", about_command)))
    application.add_handler(CommandHandler("faq", _audit_handler("faq", faq_command)))
    application.add_handler(CommandHandler("disclaimer", _audit_handler("disclaimer", disclaimer_command)))
    application.add_handler(CommandHandler("support", _audit_handler("support", support_command)))
    application.add_handler(CommandHandler("performance", _audit_handler("performance", performance_command)))
    application.add_handler(CommandHandler("quality", _audit_handler("quality", quality_command)))
    application.add_handler(CommandHandler("gemini", _audit_handler("gemini", gemini_command)))
    application.add_handler(CommandHandler("gemini_review", _audit_handler("gemini_review", gemini_review_command)))
    application.add_handler(CommandHandler("gemini_analyze", _audit_handler("gemini_analyze", gemini_analyze_command)))
    application.add_handler(CommandHandler("gemini_audit", _audit_handler("gemini_audit", gemini_audit_command)))
    application.add_handler(CommandHandler("gemini_predict", _audit_handler("gemini_predict", gemini_predict_command)))
    application.add_handler(CommandHandler("pricing", _audit_handler("pricing", pricing_command)))
    application.add_handler(CommandHandler("upgrade", _audit_handler("upgrade", upgrade_command)))
    application.add_handler(CommandHandler("signals", _audit_handler("signals", signals_command)))
    application.add_handler(CommandHandler("proof", _audit_handler("proof", proof_command)))
    application.add_handler(CommandHandler("signal", _audit_handler("signal", signal_command)))
    application.add_handler(CommandHandler("outcome", _audit_handler("outcome", outcome_command)))
    application.add_handler(CommandHandler("invite", _audit_handler("invite", invite_command)))

    # Premium (not advertised)
    application.add_handler(CommandHandler("stats", _audit_handler("stats", stats_command)))
    application.add_handler(CommandHandler("history", _audit_handler("history", history_command)))
    application.add_handler(CommandHandler("simulate", _audit_handler("simulate", simulate_command)))
    application.add_handler(CommandHandler("risk", _audit_handler("risk", risk_command)))
    application.add_handler(CommandHandler("alerts", _audit_handler("alerts", alerts_command)))
    
    # New commands for live prices and portfolio
    application.add_handler(CommandHandler("liveprice", _audit_handler("liveprice", liveprice_command)))
    application.add_handler(CommandHandler("portfolio", _audit_handler("portfolio", portfolio_command)))
    application.add_handler(CommandHandler("market", _audit_handler("market", market_command)))

    # VIP (not advertised)
    application.add_handler(CommandHandler("elite", _audit_handler("elite", elite_command)))
    application.add_handler(CommandHandler("early", _audit_handler("early", early_command)))
    application.add_handler(CommandHandler("report", _audit_handler("report", report_command)))

    application.add_handler(CommandHandler("policy", _audit_handler("policy", policy_command)))
    application.add_handler(CommandHandler("refunds", _audit_handler("refunds", policy_command)))
    application.add_handler(CommandHandler("recap", _audit_handler("recap", recap_command)))
    application.add_handler(CommandHandler("selfcheck", _audit_handler("selfcheck", selfcheck_command)))
    application.add_handler(CommandHandler("ops_health", _audit_handler("ops_health", ops_health_command)))
    application.add_handler(CommandHandler("myid", _audit_handler("myid", myid_command)))
    application.add_handler(CommandHandler("account", _audit_handler("account", account_command)))
    application.add_handler(CommandHandler("dashboard", _audit_handler("dashboard", dashboard_command)))
    application.add_handler(CommandHandler("notify", _audit_handler("notify", notify_command)))
    application.add_handler(CommandHandler("feedback", _audit_handler("feedback", feedback_command)))
    application.add_handler(CommandHandler("analyze", _audit_handler("analyze", analyze_command)))
    try:
        application.add_handler(CommandHandler("filter", _audit_handler("filter", filter_command)))
    except NameError:
        async def _filter_placeholder(update, context):
            try:
                if getattr(update, "message", None) is not None:
                    await update.message.reply_text("This command is currently unavailable.")
            except Exception:
                pass
        application.add_handler(CommandHandler("filter", _audit_handler("filter", _filter_placeholder)))

    # Unknown command handler: capture any /unknown_command and respond gracefully
    async def _handle_unknown_command(update, context):
        try:
            if getattr(update, "message", None) is not None:
                await update.message.reply_text("Unknown command. Send /help for available commands.")
        except Exception:
            pass
    application.add_handler(MessageHandler(filters.COMMAND, _audit_handler("unknown_command", _handle_unknown_command)))
    application.add_handler(CommandHandler("apikey", _audit_handler("apikey", apikey_command)))
    application.add_handler(CommandHandler("language", _audit_handler("language", language_command)))
    application.add_handler(CommandHandler("reports", _audit_handler("reports", reports_command)))
    application.add_handler(CommandHandler("referral_leaderboard", _audit_handler("referral_leaderboard", referral_leaderboard_command)))
    application.add_handler(CommandHandler("referral_rewards", _audit_handler("referral_rewards", referral_rewards_command)))
    application.add_handler(CommandHandler("admin_top_assets", _audit_handler("admin_top_assets", admin_top_assets_command)))
    application.add_handler(CommandHandler("admin_top_strategies", _audit_handler("admin_top_strategies", admin_top_strategies_command)))
    application.add_handler(CommandHandler("admin_user_engagement", _audit_handler("admin_user_engagement", admin_user_engagement_command)))
    application.add_handler(CommandHandler("assets", _audit_handler("assets", assets_command)))
    # Backward compatible alias

    # Hidden owner-only commands (silent for non-owners)
    application.add_handler(CommandHandler("unlock", _audit_handler("unlock", unlock)))
    application.add_handler(CommandHandler("dev_pause", _audit_handler("dev_pause", dev_pause)))
    application.add_handler(CommandHandler("dev_resume", _audit_handler("dev_resume", dev_resume)))
    application.add_handler(CommandHandler("dev_force_signal", _audit_handler("dev_force_signal", dev_force_signal)))
    application.add_handler(CommandHandler("force_signal", _audit_handler("force_signal", dev_force_signal)))
    application.add_handler(CommandHandler("dev_invalidate", _audit_handler("dev_invalidate", dev_invalidate)))
    application.add_handler(CommandHandler("owner_users", _audit_handler("owner_users", owner_users)))
    application.add_handler(CommandHandler("owner_revenue", _audit_handler("owner_revenue", owner_revenue)))
    application.add_handler(CommandHandler("correct_signal", _audit_handler("correct_signal", correct_signal)))
    application.add_handler(CommandHandler("provider_status", _audit_handler("provider_status", provider_status_command)))
    application.add_handler(CommandHandler("qa_report", _audit_handler("qa_report", qa_report_command)))
    application.add_handler(CommandHandler("broadcast", _audit_handler("broadcast", broadcast_command)))
    from .commands import version_command
    application.add_handler(CommandHandler("version", _audit_handler("version", version_command)))

    # MT5 commands (Premium+)
    from .commands import (
        mt5_link_command, mt5_status_command,
        setlot_command, setrisk_command, setwebhook_command, drawdown_command, tiers_command,
        mystats_command, referral_command, execution_command, build_connect_broker_conversation,
        cancel_command,
    )
    application.add_handler(CommandHandler("mt5_link", _audit_handler("mt5_link", mt5_link_command)))
    # Aliases for users who type "/mt5link" or "/mt5 ..." by habit
    application.add_handler(CommandHandler("mt5link", _audit_handler("mt5link", mt5_link_command)))
    application.add_handler(CommandHandler("mt5", _audit_handler("mt5", mt5_link_command)))
    application.add_handler(CommandHandler("mt5_status", _audit_handler("mt5_status", mt5_status_command)))
    application.add_handler(CommandHandler("setlot", _audit_handler("setlot", setlot_command)))
    application.add_handler(CommandHandler("setrisk", _audit_handler("setrisk", setrisk_command)))
    application.add_handler(CommandHandler("setwebhook", _audit_handler("setwebhook", setwebhook_command)))
    application.add_handler(CommandHandler("drawdown", _audit_handler("drawdown", drawdown_command)))
    application.add_handler(CommandHandler("execution", _audit_handler("execution", execution_command)))
    application.add_handler(CommandHandler("tiers", _audit_handler("tiers", tiers_command)))
    application.add_handler(CommandHandler("mystats", _audit_handler("mystats", mystats_command)))
    application.add_handler(CommandHandler("referral", _audit_handler("referral", referral_command)))
    application.add_handler(CommandHandler("cancel", _audit_handler("cancel", cancel_command)))

    # ── New commands ──────────────────────────────────────────────────────────
    from .commands import leaderboard_command
    application.add_handler(CommandHandler("leaderboard", _audit_handler("leaderboard", leaderboard_command)))

    application.add_handler(build_connect_broker_conversation())

    # Subscription cancellation confirmation callbacks
    from .commands import cancel_confirm_callback, cancel_nevermind_callback
    from telegram.ext import CallbackQueryHandler as _CQH_cancel
    application.add_handler(_CQH_cancel(cancel_confirm_callback, pattern="^cancel_confirm$"))
    application.add_handler(_CQH_cancel(cancel_nevermind_callback, pattern="^cancel_nevermind$"))

    # ── Terms gate callbacks (/start disclaimer) ─────────────────────────────
    from .commands import agree_terms_callback, decline_terms_callback
    from telegram.ext import CallbackQueryHandler as _CQH_terms
    application.add_handler(_CQH_terms(agree_terms_callback, pattern="^agree_terms$"))
    application.add_handler(_CQH_terms(decline_terms_callback, pattern="^decline_terms$"))

    # ── VIP waitlist join callback (/upgrade when full) ──────────────────────
    from .commands import vip_waitlist_join_callback
    from telegram.ext import CallbackQueryHandler as _CQH_vip
    application.add_handler(_CQH_vip(vip_waitlist_join_callback, pattern="^vip_waitlist_join$"))

    # ── Help pagination callbacks (/help) ────────────────────────────────────
    from .commands import help_page_callback
    from telegram.ext import CallbackQueryHandler as _CQH_help
    application.add_handler(_CQH_help(help_page_callback, pattern=r"^help_page_[1-4]$"))

    # ── Help/Navigation buttons ─────────────────────────────────────────────
    from .commands import button_click_handler
    from telegram.ext import CallbackQueryHandler as _CQH_nav
    application.add_handler(_CQH_nav(button_click_handler, pattern=r"^(nav_.*|trade_now.*|mt5_link_guide|mt5_settings|advanced_portfolio|locked_.*|admin_.*|vip_sold_out)$"))

    # ── Admin commands (OWNER/ADMIN only, silent for others) ─────────────────
    from .commands import admin_command, admin_broadcast_command, blast_terms_command, admin_dashboard, force_market_scan_command
    application.add_handler(CommandHandler("admin", _audit_handler("admin", admin_command)))
    application.add_handler(CommandHandler("admin_dashboard", _audit_handler("admin_dashboard", admin_dashboard)))
    application.add_handler(CommandHandler("admin_broadcast", _audit_handler("admin_broadcast", admin_broadcast_command)))
    application.add_handler(CommandHandler("force_market_scan", _audit_handler("force_market_scan", force_market_scan_command)))
    application.add_handler(CommandHandler("blast_terms", _audit_handler("blast_terms", blast_terms_command)))

    # NOTE: Commands are intentionally registered once above. Avoid duplicate
    # add_handler calls, which can execute the same command twice per update.

    # Lightweight command registry audit to catch missing handlers.
    try:
        from telegram.ext import CommandHandler as _CH, ConversationHandler as _Conv
        from signalrank_telegram.command_access import COMMAND_TIERS

        def _extract_commands(_handler) -> list[str]:
            if isinstance(_handler, _CH):
                return [str(c).lstrip("/") for c in (_handler.commands or [])]
            if isinstance(_handler, _Conv):
                cmds: list[str] = []
                for _ep in (_handler.entry_points or []):
                    if isinstance(_ep, _CH):
                        cmds.extend([str(c).lstrip("/") for c in (_ep.commands or [])])
                return cmds
            return []

        _registered: set[str] = set()
        _handlers_map = getattr(application, "handlers", {}) or {}
        if isinstance(_handlers_map, dict):
            for _lst in _handlers_map.values():
                for _h in (_lst or []):
                    _registered.update(_extract_commands(_h))

        _expected = set(COMMAND_TIERS.keys())
        _missing = sorted(_expected - _registered)
        _extras = sorted(_registered - _expected)
        if _missing:
            logger.warning("[bot] command registry mismatch: missing=%s", _missing)
        if _extras:
            logger.info("[bot] command registry extras=%s", _extras)
    except Exception as _cmd_audit_err:
        logger.debug("[bot] command registry audit skipped: %s", _cmd_audit_err)

    # 📊 Signal engagement reactions (🔥 Taking It / 👀 Watching)
    from telegram.ext import CallbackQueryHandler as _CQH
    async def _signal_reaction_callback(update, context):
        query = update.callback_query
        user_id = update.effective_user.id if update.effective_user else None
        if user_id is None:
            return
        try:
            # Callback data: signal_reaction_<signal_id>|<reaction>
            data = (query.data or "").replace("signal_reaction_", "", 1)
            signal_id_str, reaction = data.split("|", 1)
            signal_id = str(signal_id_str).strip()
            if reaction not in ("taking_it", "watching"):
                await query.answer("Invalid reaction.", show_alert=False)
                return
        except Exception:
            return
        try:
            from db.session import get_session as _gs
            from db.models import SignalEngagement
            from db.pg_features import get_or_create_user
            from sqlalchemy import select
            async with _gs() as session:
                user = await get_or_create_user(session, telegram_user_id=int(user_id))
                existing = (await session.execute(
                    select(SignalEngagement).where(
                        SignalEngagement.user_id == user.id,
                        SignalEngagement.signal_id == signal_id,
                    )
                )).scalar_one_or_none()
                if existing:
                    existing.reaction = reaction
                else:
                    session.add(SignalEngagement(
                        user_id=user.id,
                        signal_id=signal_id,
                        reaction=reaction,
                    ))
                await session.commit()
            signal_payload = await _load_signal_payload(signal_id)
            counts = await _load_signal_engagement_counts(signal_id)
            try:
                await query.edit_message_reply_markup(
                    reply_markup=_build_signal_keyboard(signal_id, signal=signal_payload, counts=counts)
                )
            except Exception as markup_exc:
                if "message is not modified" not in str(markup_exc).lower():
                    logger.debug(f"[engagement] reply markup refresh failed: {markup_exc}")
            try:
                await _refresh_signal_keyboards_for_all_recipients(signal_id, context.bot)
            except Exception as refresh_exc:
                logger.debug(f"[engagement] global keyboard refresh failed: {refresh_exc}")
            emoji = "🔥" if reaction == "taking_it" else "👀"
            await query.answer(f"{emoji} Noted!", show_alert=False)
        except Exception as exc:
            logger.debug(f"[engagement] reaction save failed: {exc}")

    application.add_handler(_CQH(_signal_reaction_callback, pattern=r"^signal_reaction_"))

    async def _signal_monitor_callback(update, context):
        query = update.callback_query
        user_id = update.effective_user.id if update.effective_user else None
        chat_id = update.effective_chat.id if update.effective_chat else None
        if user_id is None or chat_id is None:
            await query.answer()
            return
        signal_id = (query.data or "").replace("monitor_signal_", "", 1).strip()
        if not signal_id:
            await query.answer("No signal selected.", show_alert=True)
            return
        await query.answer("Refreshing monitor…", show_alert=False)
        try:
            text, is_active, expires_at = await _build_monitor_snapshot(signal_id)
            from db.session import get_session as _gs_mon
            from db.models import RuntimeState
            from sqlalchemy import select

            runtime_key = f"monitor:{int(user_id)}:{signal_id}"
            message_id = None
            async with _gs_mon() as session:
                state_row = (
                    await session.execute(
                        select(RuntimeState).where(RuntimeState.key == runtime_key).limit(1)
                    )
                ).scalar_one_or_none()
                if state_row is not None:
                    try:
                        message_id = int((state_row.value or {}).get("message_id") or 0)
                    except Exception:
                        message_id = None
                await session.commit()

            if message_id:
                try:
                    await context.bot.edit_message_text(
                        chat_id=int(chat_id),
                        message_id=int(message_id),
                        text=text,
                        parse_mode="HTML",
                        reply_markup=_build_monitor_keyboard(signal_id),
                    )
                except Exception as exc:
                    err = str(exc).lower()
                    if "message is not modified" in err:
                        # Keep the tracked message; no need to send a duplicate.
                        pass
                    elif any(
                        token in err
                        for token in (
                            "message to edit not found",
                            "chat not found",
                            "bot was blocked",
                            "message can't be edited",
                        )
                    ):
                        # Original monitor message is no longer editable; recreate once.
                        message_id = None
                    else:
                        # Transient edit failure: keep existing monitor message id to
                        # avoid spawning duplicate monitor threads/messages.
                        logger.debug(f"[monitor] edit_message_text transient failure: {exc}")

            if not message_id:
                monitor_msg = await context.bot.send_message(
                    chat_id=int(chat_id),
                    text=text,
                    parse_mode="HTML",
                    reply_markup=_build_monitor_keyboard(signal_id),
                )
                message_id = int(monitor_msg.message_id)

            async with _gs_mon() as session:
                state_row = (
                    await session.execute(
                        select(RuntimeState).where(RuntimeState.key == runtime_key).limit(1)
                    )
                ).scalar_one_or_none()
                if state_row is None:
                    state_row = RuntimeState(key=runtime_key, value={})
                    session.add(state_row)
                state_row.value = {
                    "telegram_user_id": int(user_id),
                    "chat_id": int(chat_id),
                    "message_id": int(message_id),
                    "signal_id": str(signal_id),
                }
                state_row.expires_at = expires_at
                state_row.updated_at = datetime.utcnow()
                await session.commit()

            if not is_active:
                await query.answer("Monitor captured final status.", show_alert=False)
        except Exception as exc:
            logger.debug(f"[monitor] callback failed: {exc}")
            await query.answer("⚠️ Could not open monitor right now.", show_alert=True)

    application.add_handler(_CQH(_signal_monitor_callback, pattern=r"^monitor_signal_"))

    # ⚡ Take Trade — one-click MT5 execution (PREMIUM/VIP) or upsell (FREE)
    # Callback data: mt5_trade_<signal_id>|<asset>|<direction>|<entry>|<sl>|<tp>
    async def _mt5_trade_callback(update, context):
        query = update.callback_query
        user_id = update.effective_user.id if update.effective_user else None
        if user_id is None:
            await query.answer()
            return

        # ── Tier gate: FREE users see an upsell paywall ───────────────────────
        _ut = "FREE"
        try:
            from signalrank_telegram.access import resolve_user_tier
            from signalrank_telegram.commands import tier_rank
            _ut = (resolve_user_tier(int(user_id)) or "FREE").upper()
            if tier_rank(_ut) < tier_rank("PREMIUM"):
                await query.answer("🔒 Premium feature", show_alert=False)
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=(
                        "🔒 *Premium Feature Locked!*\n\n"
                        "Auto-trading directly from Telegram is reserved for our paid members.\n\n"
                        "⭐️ *Premium Benefits:* 1-click execution, faster signals, and full asset coverage.\n\n"
                        "👑 *VIP Benefits:* Everything in Premium, plus custom risk management, "
                        "dedicated support, and exclusive market insights.\n\n"
                        "🚀 Type /upgrade right now to unlock these features and catch this trade!"
                    ),
                    parse_mode="MarkdownV2",
                )
                return
        except Exception as _te:
            logger.debug("[mt5] tier check error: %s", _te)

        await query.answer()
        try:
            raw = (query.data or "").replace("mt5_trade_", "", 1).strip()
            signal_id = ""
            asset = ""
            direction = ""
            entry = 0.0
            sl = 0.0
            tp = 0.0

            # Backward-compatible parser (legacy payload with all fields)
            if "|" in raw:
                parts = raw.split("|")
                signal_id, asset, direction = parts[0], parts[1], parts[2]
                entry, sl, tp = float(parts[3]), float(parts[4]), float(parts[5])
            else:
                # Compact payload: mt5_trade_<signal_id>
                signal_id = raw
                payload = await _load_signal_payload(signal_id)
                if not payload:
                    await query.edit_message_text("❌ Signal data unavailable for this trade.")
                    return
                asset = str(payload.get("asset") or "").upper().strip()
                direction = str(payload.get("direction") or "").lower().strip()
                entry = float(payload.get("entry") or 0)
                sl = float(payload.get("stop_loss") or 0)
                tp = float(_first_take_profit(payload) or 0)

        except Exception:
            await query.edit_message_text("❌ Invalid trade button data.")
            return

        # Validate that we actually have sl/tp (FREE signals have 0)
        if not sl or not tp:
            await query.edit_message_text(
                "⚠️ Trade data incomplete — stop-loss or take-profit is missing on this signal."
            )
            return

        try:
            from services.mt5_client import get_user_mt5_account_id, validate_slippage, execute_trade
            from db.session import get_session as _gs_mt5
            from db.models import User as _UserMT5
            from sqlalchemy import select as _sel_mt5
            from datetime import datetime, timezone

            # PREMIUM daily execution cap (default 3/day, configurable)
            _premium_daily_limit = int(os.getenv("PREMIUM_DAILY_EXECUTIONS", "3"))
            _user_row = None
            _premium_count_today = 0
            async with _gs_mt5() as _ucheck:
                _user_row = (await _ucheck.execute(
                    _sel_mt5(_UserMT5).where(_UserMT5.telegram_user_id == user_id)
                )).scalar_one_or_none()
            if _user_row is None:
                await query.edit_message_text("❌ User profile not found. Please send /start and try again.")
                return

            _exec_mode = str(getattr(_user_row, "execution_mode", "manual") or "manual").lower()
            if _exec_mode == "none":
                await query.edit_message_text(
                    "⛔ Broker execution is disabled for your account (mode: NONE).\n"
                    "Use /execution manual to re-enable one-click trading."
                )
                return

            if _ut == "PREMIUM":
                async with _gs_mt5() as _slim:
                    _user_row = (await _slim.execute(
                        _sel_mt5(_UserMT5).where(_UserMT5.telegram_user_id == user_id)
                    )).scalar_one_or_none()
                    if _user_row is None:
                        await query.edit_message_text("❌ User profile not found. Please send /start and try again.")
                        return

                    _now = datetime.now(timezone.utc)
                    _reset_at = getattr(_user_row, "daily_executions_reset_at", None)
                    if _reset_at is None or (_reset_at.date() < _now.date()):
                        _user_row.daily_executions_today = 0
                        _user_row.daily_executions_reset_at = _now
                        await _slim.commit()

                    _premium_count_today = int(getattr(_user_row, "daily_executions_today", 0) or 0)
                    if _premium_count_today >= _premium_daily_limit:
                        await query.edit_message_text(
                            f"⚠️ PREMIUM daily auto-trade limit reached ({_premium_daily_limit}/{_premium_daily_limit}).\n"
                            "It resets at 00:00 UTC, or upgrade to VIP for unlimited executions."
                        )
                        return

            # Daily drawdown guard for paid execution.
            try:
                from db.models import MT5Execution as _MT5Exec
                from sqlalchemy import func as _func
                from datetime import datetime, timezone
                async with _gs_mt5() as _sdd:
                    _u_dd = (await _sdd.execute(
                        _sel_mt5(_UserMT5).where(_UserMT5.telegram_user_id == user_id)
                    )).scalar_one_or_none()
                    if _u_dd is not None:
                        _now_dd = datetime.now(timezone.utc)
                        _day_start = _now_dd.replace(hour=0, minute=0, second=0, microsecond=0)
                        _sum_row = await _sdd.execute(
                            _sel_mt5(_func.coalesce(_func.sum(_MT5Exec.realized_pnl_pct), 0.0)).where(
                                _MT5Exec.user_id.in_([int(getattr(_u_dd, "id", 0) or 0), int(user_id)]),
                                _MT5Exec.executed_at >= _day_start,
                            )
                        )
                        _pnl_today = float(_sum_row.scalar_one_or_none() or 0.0)
                        _cap = float(getattr(_u_dd, "max_daily_drawdown_pct", 8.0) or 8.0)
                        if _cap > 0 and _pnl_today <= -abs(_cap):
                            await query.edit_message_text(
                                "⛔ Daily drawdown guard is active.\n"
                                f"Today: {_pnl_today:.2f}% (limit: -{abs(_cap):.2f}%).\n"
                                "Execution paused for today."
                            )
                            return
            except Exception:
                pass

            account_id = await get_user_mt5_account_id(user_id)
            if not account_id:
                await query.edit_message_text(
                    "⚠️ No MT5 account linked.\nUse /mt5_link <login> <password> <server> first."
                )
                return
            within_tol, slip, live_px = await validate_slippage(account_id, asset, entry)
            if not within_tol:
                await query.edit_message_text(
                    f"⚠️ *Slippage Warning*\n\nSignal entry: `{entry}`\nLive price: `{live_px:.5f}`\nSlippage: `{slip:.1f}` pts\n\nToo far from entry — trade not executed.",
                    parse_mode="MarkdownV2"
                )
                return
            # Use user's configured lot size (/setlot) or default 0.01
            _exec_vol = 0.01
            try:
                if _user_row is None:
                    async with _gs_mt5() as _sm5:
                        _user_row = (await _sm5.execute(
                            _sel_mt5(_UserMT5).where(_UserMT5.telegram_user_id == user_id)
                        )).scalar_one_or_none()
                if _user_row and getattr(_user_row, 'fixed_lot_size', None):
                    _exec_vol = float(_user_row.fixed_lot_size)
            except Exception:
                pass
            result = await execute_trade(
                account_id=account_id, symbol=asset, direction=direction,
                volume=_exec_vol, stop_loss=sl, take_profit=tp, signal_entry=entry
            )
            if result.get("success"):
                try:
                    _record_mt5_execution_sync(
                        int(user_id),
                        {
                            "signal_id": str(signal_id),
                            "asset": str(asset),
                            "direction": str(direction),
                        },
                        account_id=str(account_id),
                        order_id=str(result.get("order_id") or ""),
                        lot_size=float(_exec_vol),
                        entry_price=float(result.get("live_price") or entry),
                        stop_loss=float(sl),
                        take_profit=float(tp),
                        tier_at_execution=str(_ut),
                        status="open",
                        extra_meta={
                            "auto_execution": False,
                            "hard_stop_attached": bool(result.get("hard_stop_attached", True)),
                        },
                    )
                except Exception:
                    pass
                _remaining_text = ""
                if _ut == "PREMIUM":
                    try:
                        async with _gs_mt5() as _sinc:
                            _u2 = (await _sinc.execute(
                                _sel_mt5(_UserMT5).where(_UserMT5.telegram_user_id == user_id)
                            )).scalar_one_or_none()
                            if _u2 is not None:
                                _now = datetime.now(timezone.utc)
                                _u2.daily_executions_today = int(getattr(_u2, "daily_executions_today", 0) or 0) + 1
                                _u2.daily_executions_reset_at = _now
                                await _sinc.commit()
                                _remaining = max(0, _premium_daily_limit - int(_u2.daily_executions_today or 0))
                                _remaining_text = f"\n📊 Remaining today: {_remaining}/{_premium_daily_limit}"
                    except Exception:
                        pass
                oid = result.get("order_id", "")
                lp = result.get("live_price") or entry
                await query.edit_message_text(
                    f"✅ *Trade Executed*\n\n🏦 {asset} {direction.upper()}\n📍 Entry: `{lp:.5f}`\nSL: `{sl}` | TP: `{tp}`\n🆔 Order: `{oid}`{_remaining_text}",
                    parse_mode="MarkdownV2"
                )
                try:
                    await _send_message_with_retry(
                        context.bot,
                        chat_id=int(user_id),
                        text=(
                            "🧾 <b>Execution Receipt (MANUAL)</b>\n\n"
                            f"Asset: <b>{asset}</b>\n"
                            f"Order: <code>{oid}</code>\n"
                            f"Signal ID: <code>{signal_id}</code>"
                        ),
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
            else:
                await query.edit_message_text(f"❌ Trade failed: `{result.get('error', 'unknown')}`", parse_mode="MarkdownV2")
        except Exception as exc:
            await query.edit_message_text(f"❌ MT5 error: `{exc}`", parse_mode="MarkdownV2")

    application.add_handler(_CQH(_mt5_trade_callback, pattern=r"^mt5_trade_"))

    # 🔗 Open latest active signal message for this signal
    async def _open_signal_callback(update, context):
        query = update.callback_query
        raw = (query.data or "").replace("open_signal_", "", 1).strip()
        if not raw:
            await query.answer("Signal reference missing.", show_alert=True)
            return

        try:
            from sqlalchemy import select as _sel_os
            from db.session import get_session as _gs_os
            from db.models import ActiveSignalMessage as _ASM
            from db.pg_features import get_or_create_user as _gocu_os

            uid = int(getattr(update.effective_user, "id", 0) or 0)
            if uid <= 0:
                await query.answer("Unable to resolve your account.", show_alert=True)
                return

            await query.answer("Opening signal…")

            async with _gs_os() as _s:
                _u = await _gocu_os(_s, telegram_user_id=uid)
                _row = (
                    await _s.execute(
                        _sel_os(_ASM)
                        .where(
                            _ASM.user_id == int(_u.id),
                            _ASM.signal_id == str(raw),
                            _ASM.is_active.is_(True),
                        )
                        .order_by(_ASM.id.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                await _s.commit()

            if _row is None:
                await query.answer("Signal message not found. Use /signals for latest.", show_alert=True)
                return

            await context.bot.copy_message(
                chat_id=int(uid),
                from_chat_id=int(_row.chat_id),
                message_id=int(_row.message_id),
            )
        except Exception as _open_err:
            logger.debug("[open_signal] error: %s", _open_err)
            await query.answer("Could not open signal right now.", show_alert=True)

    application.add_handler(_CQH(_open_signal_callback, pattern=r"^open_signal_"))

    # 🔍 Check Outcome — query DB for signal status / outcome and show as popup
    async def _check_outcome_callback(update, context):
        query = update.callback_query
        raw = (query.data or "").replace("check_outcome_", "", 1).strip()
        if not raw:
            await query.answer("No signal ID found.", show_alert=True)
            return
        try:
            from db.session import get_session as _gs_oc
            from db.models import Signal as _Sig, Outcome as _Out
            from sqlalchemy import select as _sel_oc
            async with _gs_oc() as _s:
                sig_row = (await _s.execute(
                    _sel_oc(_Sig).where(_Sig.signal_id == raw).limit(1)
                )).scalar_one_or_none()
                out_row = (await _s.execute(
                    _sel_oc(_Out).where(_Out.signal_id == raw).limit(1)
                )).scalar_one_or_none() if sig_row else None
            if sig_row is None:
                await query.answer("❌ Signal not found in database.", show_alert=True)
                return
            asset     = getattr(sig_row, 'asset', '?')
            direction = str(getattr(sig_row, 'direction', '?')).upper()
            score     = getattr(sig_row, 'score', 0)
            expired   = getattr(sig_row, 'expired', False)
            created   = getattr(sig_row, 'created_at', None)
            age_str   = ""
            if created:
                try:
                    from datetime import datetime, timezone
                    _c = created.replace(tzinfo=timezone.utc) if created.tzinfo is None else created
                    _mins = int((datetime.now(timezone.utc) - _c).total_seconds() / 60)
                    age_str = f" | Age: {_mins}m"
                except Exception:
                    pass
            if out_row:
                outcome = str(getattr(out_row, 'status', 'unknown')).upper()
                emoji = "✅" if outcome.startswith("TP") else ("🛑" if outcome == "SL" else "ℹ️")
                msg = f"{emoji} {asset} {direction}\nOutcome: {outcome}\nScore: {score:.0f}{age_str}"
            elif expired:
                msg = f"⏰ {asset} {direction}\nStatus: Expired{age_str}"
            else:
                msg = f"🟢 {asset} {direction}\nStatus: Active (no outcome yet)\nScore: {score:.0f}{age_str}"
            await query.answer(msg, show_alert=True)
        except Exception as _oc_err:
            logger.debug("[check_outcome] error: %s", _oc_err)
            await query.answer("⚠️ Could not retrieve signal status right now.", show_alert=True)

    application.add_handler(_CQH(_check_outcome_callback, pattern=r"^check_outcome_"))

    # In webhook mode, handlers are now fully registered. Mark readiness here so
    # railway_main can begin processing updates while non-critical jobs continue
    # bootstrapping in this thread.
    _refresh_webhook_handlers_ready("post_handler_registration")

    def send_weekly_recap():
        user_ids = get_all_user_ids_compat()
        # Prefer Postgres-backed recap when configured
        from db.session import is_db_configured, get_session
        if is_db_configured():
            from db.pg_features import get_weekly_recap_stats

            async def _fetch(uid: int) -> dict:
                async with get_session() as session:
                    data = await get_weekly_recap_stats(session, int(uid))
                    await session.commit()
                    return data

            for user_id in user_ids:
                try:
                    stats = run_sync(_fetch(int(user_id)))
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
                    _send_message_with_retry_sync(application.bot, chat_id=int(user_id), text=recap_msg)
                    try:
                        import asyncio
                        run_sync(asyncio.sleep(0.5))
                    except Exception:
                        pass
                except Exception as e:
                    logger.warning(f"[recap] Failed to send weekly recap to user {user_id}: {e}")
                    pass
            return

    # Initialize and schedule jobs
    def send_outcome_notifications():
        # Send outcome notifications only once per outcome (notified_at tracks this).
        # Fetches unnotified outcomes and sends them to all users who received the signal.
        # Once sent and marked as notified, the outcome will never be resent.
        try:
            from db.session import is_db_configured, get_session
            if not is_db_configured():
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
                pending = run_sync(_fetch())
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

                # Keep MT5 execution rows in sync with signal outcomes.
                # This powers drawdown guard and reconciliation logic.
                try:
                    from db.models import MT5Execution as _MT5Exec
                    from sqlalchemy import select as _sel, and_ as _and
                    from datetime import datetime, timezone

                    async def _sync_exec_rows() -> None:
                        async with get_session() as _sx:
                            _rows = (
                                await _sx.execute(
                                    _sel(_MT5Exec).where(
                                        _and(
                                            _MT5Exec.signal_id == str(ref),
                                            _MT5Exec.closed_at.is_(None),
                                        )
                                    )
                                )
                            ).scalars().all()
                            if not _rows:
                                await _sx.commit()
                                return

                            for _ex in _rows:
                                _entry = float(getattr(_ex, "entry_price", 0) or 0)
                                _sl = float(getattr(_ex, "stop_loss", 0) or 0)

                                if status == "sl":
                                    _risk = 0.0
                                    try:
                                        _risk = abs(((_entry - _sl) / _entry) * 100.0) if _entry else 0.0
                                    except Exception:
                                        _risk = abs(float(getattr(oc, "percent", 0) or 0))
                                    _ex.status = "sl"
                                    _ex.realized_pnl_pct = -abs(float(_risk or 0.0))
                                    _ex.closed_at = datetime.now(timezone.utc)
                                elif status in {"tp3", "tp"}:
                                    _ex.status = "tp3"
                                    _ex.realized_pnl_pct = abs(float(getattr(oc, "percent", 0) or 0.0))
                                    _ex.closed_at = datetime.now(timezone.utc)
                                elif status == "tp2":
                                    _ex.status = "tp2"
                                elif status in {"tp1", "partial_tp"}:
                                    _ex.status = "tp1"

                            await _sx.commit()

                    run_sync(_sync_exec_rows())
                except Exception as _mx:
                    logger.debug(f"[outcome] mt5 execution reconcile failed ref={ref[:8]} err={_mx}")

                # FOMO trigger: VIP TP1 unlocks an immediate FREE dispatch.
                try:
                    if status in {"tp1", "partial_tp"} and _is_free_fomo_dispatch_only_enabled():
                        from signalrank_telegram.access import resolve_user_tier
                        is_vip_event = any(
                            str(resolve_user_tier(int(uid)) or "free").lower() in {"vip", "admin", "owner"}
                            for uid, _tier, _prefs in (recipients or [])
                        )
                        if is_vip_event:
                            try:
                                import json as _json
                                _tp = getattr(sig, "take_profit", None)
                                if isinstance(_tp, str):
                                    try:
                                        _tp = _json.loads(_tp)
                                    except Exception:
                                        pass
                                fomo_signal = {
                                    "signal_id": ref,
                                    "asset": asset,
                                    "timeframe": timeframe,
                                    "direction": direction,
                                    "entry": getattr(sig, "entry", None),
                                    "stop_loss": getattr(sig, "stop_loss", None),
                                    "take_profit": _tp,
                                    "score": getattr(sig, "score", 0),
                                    "rr_ratio": getattr(sig, "rr_estimate", None),
                                    "regime": getattr(sig, "regime", None),
                                    "strategy": getattr(sig, "strategy_name", None),
                                }
                                _dispatch_free_fomo_unlock_for_signal(fomo_signal)
                            except Exception as _fomo_exc:
                                logger.debug(f"[fomo_free] signal build failed ref={ref[:8]} err={_fomo_exc}")
                except Exception as _fomo_outer_exc:
                    logger.debug(f"[fomo_free] outcome hook failed ref={ref[:8]} err={_fomo_outer_exc}")

                now_hour = int(datetime.now().hour)
                sent_count = 0
                failed_count = 0
                quiet_deferred_count = 0
                eligible_count = 0

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
                                    quiet_deferred_count += 1
                                    continue
                            else:
                                # Wrap-around (e.g. 22 -> 6)
                                if now_hour >= qs or now_hour < qe:
                                    quiet_deferred_count += 1
                                    continue
                    except Exception as e:
                        logger.debug(f"[dispatch] Failed to check quiet hours for user: {e}")
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
                    elif status in {"tp3", "tp"}:
                        tp_level_num = 3

                    # Fetch the delivered signal for this user and signal_id
                    delivered_signal = None
                    try:
                        from db.session import get_session
                        from db.pg_features import get_delivered_signal_by_ref
                        async def _fetch_delivered():
                            async with get_session() as session:
                                return await get_delivered_signal_by_ref(session, int(telegram_user_id), str(ref))
                        delivered_signal = run_sync(_fetch_delivered())
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
                        async def _fetch_market_price():
                            tf = timeframe or "1h"
                            data = await fetch_market_data_cached(asset, [tf])
                            payload = data.get(tf) or {}
                            candles = payload.get("candles") or []
                            if candles:
                                return candles[-1].get("close")
                            return None
                        current_market_price = run_sync(_fetch_market_price())
                    except Exception as e:
                        logger.debug(f"[outcome] Failed to fetch current market price for {asset}: {e}")
                        pass

                    if user_tier in ("owner", "admin", "vip"):
                        if tp_level_num in (1, 2, 3):
                            notify = True
                            msg = _tier_notifier.format_tp_hit_notification(signal_data, user_tier, tp_level_num, float(getattr(oc, "percent", 0) or 0), current_market_price)
                        elif status == "sl":
                            notify = True
                            _entry_v = float(signal_data.get("entry") or 0)
                            _sl_v = float(signal_data.get("stop_loss") or 0)
                            _risk_pct = abs(float(getattr(oc, "percent", 0) or 0.0))
                            if _risk_pct <= 0 and _entry_v and _sl_v:
                                _risk_pct = abs(((_entry_v - _sl_v) / _entry_v) * 100.0)
                            msg = (
                                "❌ <b>Trade Closed</b>\n"
                                f"<b>{asset}</b> hit Stop Loss.\n"
                                f"Risk: <b>-{_risk_pct:.2f}%</b>\n"
                                "Status: Awaiting next high-probability setup."
                            )
                    elif user_tier == "premium":
                        if tp_level_num in (1, 2, 3):
                            notify = True
                            msg = _tier_notifier.format_tp_hit_notification(signal_data, user_tier, tp_level_num, float(getattr(oc, "percent", 0) or 0), current_market_price)
                        elif status == "sl":
                            notify = True
                            _entry_v = float(signal_data.get("entry") or 0)
                            _sl_v = float(signal_data.get("stop_loss") or 0)
                            _risk_pct = abs(float(getattr(oc, "percent", 0) or 0.0))
                            if _risk_pct <= 0 and _entry_v and _sl_v:
                                _risk_pct = abs(((_entry_v - _sl_v) / _entry_v) * 100.0)
                            msg = (
                                "❌ <b>Trade Closed</b>\n"
                                f"<b>{asset}</b> hit Stop Loss.\n"
                                f"Risk: <b>-{_risk_pct:.2f}%</b>\n"
                                "Status: Awaiting next high-probability setup."
                            )
                    elif str(tier_at_send).lower() == "free":
                        if tp_level_num > 0 or status == "tp":
                            notify = True
                            msg = _tier_notifier.format_tp_hit_notification(signal_data, "free", tp_level_num or 1, float(getattr(oc, "percent", 0) or 0), current_market_price)
                        elif status == "sl":
                            notify = True
                            _entry_v = float(signal_data.get("entry") or 0)
                            _sl_v = float(signal_data.get("stop_loss") or 0)
                            _risk_pct = abs(float(getattr(oc, "percent", 0) or 0.0))
                            if _risk_pct <= 0 and _entry_v and _sl_v:
                                _risk_pct = abs(((_entry_v - _sl_v) / _entry_v) * 100.0)
                            msg = (
                                "❌ <b>Trade Closed</b>\n"
                                f"<b>{asset}</b> hit Stop Loss.\n"
                                f"Risk: <b>-{_risk_pct:.2f}%</b>\n"
                                "Status: Awaiting next high-probability setup."
                            )

                    if notify and msg:
                        eligible_count += 1
                        try:
                            _send_message_with_retry_sync(
                                application.bot,
                                chat_id=int(telegram_user_id),
                                text=msg,
                                parse_mode="HTML",
                            )
                            try:
                                import asyncio
                                run_sync(asyncio.sleep(0.5))
                            except Exception:
                                pass
                            sent_count += 1
                        except Exception as e:
                            logger.warning(f"[outcome] Failed to send outcome notification to user {telegram_user_id}: {e}")
                            failed_count += 1
                            pass

                mark_notified = False
                if sent_count > 0:
                    mark_notified = True
                elif len(recipients or []) == 0:
                    # No recipients for this signal; avoid permanent retry loop.
                    mark_notified = True
                elif eligible_count == 0 and quiet_deferred_count == 0:
                    # No tier-qualified recipients and no quiet-hour deferrals.
                    mark_notified = True

                if mark_notified:
                    try:
                        async def _mark(oid: int) -> None:
                            async with get_session() as session:
                                await mark_outcome_notified(session, int(oid))
                                await session.commit()

                        run_sync(_mark(int(getattr(oc, 'id'))))
                    except Exception as e:
                        logger.debug(f"[outcome] Failed to mark outcome as handled: {e}")
                else:
                    logger.info(
                        "[outcome] deferring notify mark ref=%s status=%s recipients=%s sent=%s failed=%s quiet_deferred=%s",
                        ref_short,
                        status,
                        len(recipients or []),
                        sent_count,
                        failed_count,
                        quiet_deferred_count,
                    )
        except Exception as e:
            logger.warning(f"[outcome] Failed to process outcomes: {e}")
            return


    def smart_exit_guard_job():
        """Phase 2: close weak AUTO positions early on structural deterioration."""
        try:
            from db.session import is_db_configured, get_session
            if not is_db_configured():
                return

            from datetime import datetime, timedelta, timezone
            from sqlalchemy import select, and_
            from db.models import MT5Execution, User
            from services.mt5_client import get_live_price as _mt5_live_price, close_position as _mt5_close_position
            from data.fetcher import async_get_candles
            from engine.confluence_engine import run_confluence_engine

            min_loss_pct = float(os.getenv("SMART_EXIT_MIN_LOSS_PCT", "0.25") or 0.25)
            max_sl_share = float(os.getenv("SMART_EXIT_MAX_SL_SHARE", "0.90") or 0.90)
            weak_votes = int(os.getenv("SMART_EXIT_MIN_CONFLUENCE_VOTES", "4") or 4)
            btc_crash_pct = float(os.getenv("SMART_EXIT_BTC_CRASH_PCT", "-1.20") or -1.20)

            async def _run() -> None:
                now = datetime.now(timezone.utc)
                cutoff = now - timedelta(days=3)
                async with get_session() as session:
                    rows = (
                        await session.execute(
                            select(MT5Execution, User)
                            .join(User, User.id == MT5Execution.user_id)
                            .where(
                                and_(
                                    User.execution_mode == "auto",
                                    MT5Execution.closed_at.is_(None),
                                    MT5Execution.executed_at >= cutoff,
                                    MT5Execution.status.in_(["pending", "open", "tp1", "tp2"]),
                                )
                            )
                            .limit(100)
                        )
                    ).all()

                    if not rows:
                        await session.commit()
                        return

                    btc_1h_drop = 0.0
                    try:
                        _btc = await async_get_candles("BTCUSDT", "1h")
                        if _btc and len(_btc) >= 2:
                            _a = float((_btc[-2] or {}).get("close") or 0.0)
                            _b = float((_btc[-1] or {}).get("close") or 0.0)
                            if _a > 0:
                                btc_1h_drop = ((_b - _a) / _a) * 100.0
                    except Exception:
                        btc_1h_drop = 0.0

                    for exec_row, user in rows:
                        try:
                            account_id = str(getattr(exec_row, "metaapi_account_id", "") or "").strip()
                            if not account_id:
                                continue

                            symbol = str(getattr(exec_row, "symbol", "") or "").upper().strip()
                            direction = str(getattr(exec_row, "direction", "long") or "long").lower()
                            position_id = str(getattr(exec_row, "order_id", "") or "").strip()
                            entry = float(getattr(exec_row, "entry_price", 0.0) or 0.0)
                            sl = float(getattr(exec_row, "stop_loss", 0.0) or 0.0)

                            if not symbol or not position_id or entry <= 0 or sl <= 0:
                                continue

                            live = await _mt5_live_price(account_id, symbol)
                            if live is None:
                                continue

                            hard_sl_pct = abs(((entry - sl) / entry) * 100.0)
                            if hard_sl_pct <= 0:
                                continue

                            if direction == "short":
                                cur_loss_pct = max(0.0, ((float(live) - entry) / entry) * 100.0)
                                expected_dir = "SHORT"
                            else:
                                cur_loss_pct = max(0.0, ((entry - float(live)) / entry) * 100.0)
                                expected_dir = "LONG"

                            if cur_loss_pct < min_loss_pct:
                                continue
                            if cur_loss_pct >= hard_sl_pct * max_sl_share:
                                # Too close to hard SL — let broker stop handle it.
                                continue

                            candles = await async_get_candles(symbol, "1h")
                            if not candles:
                                continue
                            conf = run_confluence_engine(candles)
                            conf_score = int(conf.get("score", 0) or 0)
                            conf_total = int(conf.get("total", 15) or 15)
                            conf_dir = str(conf.get("direction", "NEUTRAL") or "NEUTRAL").upper()

                            structural_shift = (conf_score <= weak_votes) or (conf_dir != expected_dir)
                            market_shock = float(btc_1h_drop) <= float(btc_crash_pct)
                            if not structural_shift and not market_shock:
                                continue

                            closed = await _mt5_close_position(account_id, position_id, comment="SignalRankAI-SmartExit")
                            if not bool(closed.get("success")):
                                continue

                            exec_row.status = "smart_exit"
                            exec_row.realized_pnl_pct = -abs(float(cur_loss_pct))
                            exec_row.closed_at = now
                            _meta = dict(getattr(exec_row, "meta", {}) or {})
                            _meta.update({
                                "smart_exit": True,
                                "smart_exit_at": now.isoformat(),
                                "smart_exit_confluence": f"{conf_score}/{conf_total}",
                                "smart_exit_confluence_dir": conf_dir,
                                "smart_exit_expected_dir": expected_dir,
                                "smart_exit_btc_1h_pct": round(float(btc_1h_drop), 3),
                            })
                            exec_row.meta = _meta

                            try:
                                await application.bot.send_message(
                                    chat_id=int(user.telegram_user_id),
                                    text=(
                                        "⚠️ <b>Smart Exit</b>\n"
                                        f"Structural shift detected on <b>{symbol}</b>.\n"
                                        f"Closed early at <b>-{float(cur_loss_pct):.2f}%</b> "
                                        f"(vs hard SL ~-{float(hard_sl_pct):.2f}%)."
                                    ),
                                    parse_mode="HTML",
                                )
                            except Exception:
                                pass
                        except Exception as _one_err:
                            logger.debug(f"[smart_exit] row error: {_one_err}")

                    await session.commit()

            run_sync(_run())
        except Exception as _se:
            logger.warning(f"[smart_exit] job failed: {_se}")


    def drawdown_circuit_breaker_job():
        """Phase 3: pause AUTO mode when rolling 24h drawdown reaches user cap."""
        try:
            from db.session import is_db_configured, get_session
            if not is_db_configured():
                return

            from datetime import datetime, timedelta, timezone
            from sqlalchemy import select, func
            from db.models import User, MT5Execution

            async def _run() -> None:
                now = datetime.now(timezone.utc)
                window_start = now - timedelta(hours=24)
                async with get_session() as session:
                    users = (
                        await session.execute(
                            select(User).where(User.execution_mode == "auto", User.max_daily_drawdown_pct > 0)
                        )
                    ).scalars().all()
                    if not users:
                        await session.commit()
                        return

                    for user in users:
                        uid = int(getattr(user, "telegram_user_id", 0) or 0)
                        user_pk = int(getattr(user, "id", 0) or 0)
                        if uid <= 0 or user_pk <= 0:
                            continue

                        pnl_row = await session.execute(
                            select(func.coalesce(func.sum(MT5Execution.realized_pnl_pct), 0.0)).where(
                                MT5Execution.user_id.in_([user_pk, uid]),
                                MT5Execution.executed_at >= window_start,
                                MT5Execution.realized_pnl_pct.is_not(None),
                            )
                        )
                        pnl_24h = float(pnl_row.scalar_one_or_none() or 0.0)
                        cap = float(getattr(user, "max_daily_drawdown_pct", 0.0) or 0.0)
                        if cap <= 0 or pnl_24h > -abs(cap):
                            continue

                        user.execution_mode = "manual"

                        try:
                            await application.bot.send_message(
                                chat_id=uid,
                                text=(
                                    "🛑 <b>Capital Protection Activated</b>\n"
                                    f"Daily drawdown limit ({abs(cap):.2f}%) reached: <b>{pnl_24h:.2f}%</b>.\n"
                                    "Auto-trading is paused for now. You will still receive manual signals.\n"
                                    "Use /execution auto when you are ready to resume."
                                ),
                                parse_mode="HTML",
                            )
                        except Exception:
                            pass

                    await session.commit()

            run_sync(_run())
        except Exception as _dd:
            logger.warning(f"[drawdown_guard] job failed: {_dd}")


    def killswitch_close_all_watchdog_job():
        """When kill-switch turns ON, close all linked broker positions once."""
        try:
            ks = state.get_killswitch_sync()
            if not bool(getattr(ks, "enabled", False)):
                try:
                    # expire quickly so next kill-switch ON can re-run close-all
                    state.set_sync("killswitch:closeall:done", "0", ex=1)
                except Exception:
                    pass
                return

            marker = "killswitch:closeall:done"
            try:
                if state.get_sync(marker):
                    return
            except Exception:
                pass

            from db.session import is_db_configured, get_session
            if not is_db_configured():
                return

            from sqlalchemy import text
            from services.mt5_client import close_all_positions
            from datetime import datetime, timezone

            async def _run() -> tuple[int, int, int]:
                accounts_total = 0
                attempted = 0
                closed = 0
                async with get_session() as session:
                    rows = (
                        await session.execute(
                            text(
                                """
                                SELECT u.telegram_user_id, c.metaapi_account_id
                                FROM users u
                                JOIN mt5_credentials c ON c.user_id = u.id
                                WHERE c.metaapi_account_id IS NOT NULL
                                """
                            )
                        )
                    ).fetchall()

                    # best-effort close all positions per linked account
                    for telegram_user_id, account_id in rows:
                        try:
                            if not account_id:
                                continue
                            accounts_total += 1
                            res = await close_all_positions(str(account_id), comment="SignalRankAI-KillSwitch")
                            attempted += int(res.get("attempted", 0) or 0)
                            closed += int(res.get("closed", 0) or 0)
                            if int(res.get("attempted", 0) or 0) > 0:
                                try:
                                    await application.bot.send_message(
                                        chat_id=int(telegram_user_id),
                                        text=(
                                            "🛑 <b>Emergency Capital Protection</b>\n"
                                            "Kill-switch is ON. Open broker positions were force-closed."
                                        ),
                                        parse_mode="HTML",
                                    )
                                except Exception:
                                    pass
                        except Exception as _row_err:
                            logger.debug(f"[killswitch_closeall] account close error: {_row_err}")

                    # Mark DB executions as closed by kill-switch when still open.
                    await session.execute(
                        text(
                            """
                            UPDATE mt5_executions
                            SET status = 'closed_by_killsw',
                                closed_at = COALESCE(closed_at, NOW()),
                                meta = COALESCE(meta, '{}'::jsonb) || CAST(:meta AS JSONB)
                            WHERE closed_at IS NULL
                              AND status IN ('pending','open','tp1','tp2')
                            """
                        ),
                        {
                            "meta": '{"closed_by_killswitch": true}',
                        },
                    )
                    await session.commit()

                return accounts_total, attempted, closed

            accounts_total, attempted, closed = run_sync(_run())
            logger.warning(
                "[killswitch_closeall] executed accounts=%d attempted=%d closed=%d",
                int(accounts_total),
                int(attempted),
                int(closed),
            )
            try:
                state.set_sync(marker, str(datetime.now(timezone.utc).isoformat()), ex=60 * 60 * 24)
            except Exception:
                pass
        except Exception as _ke:
            logger.warning(f"[killswitch_closeall] watchdog failed: {_ke}")


    def broker_reconciliation_job():
        """Reconcile local MT5 execution rows against broker positions to catch ghost/orphan fills."""
        try:
            from db.session import is_db_configured, get_session
            if not is_db_configured():
                return

            from datetime import datetime, timedelta, timezone
            from sqlalchemy import select, and_
            from db.models import MT5Execution
            from services.mt5_client import list_open_positions

            grace_minutes = int(os.getenv("BROKER_RECONCILE_GRACE_MINUTES", "12") or 12)
            stale_days = int(os.getenv("BROKER_RECONCILE_STALE_DAYS", "5") or 5)

            async def _run() -> None:
                now = datetime.now(timezone.utc)
                cutoff = now - timedelta(days=stale_days)
                grace_before = now - timedelta(minutes=grace_minutes)

                async with get_session() as session:
                    rows = (
                        await session.execute(
                            select(MT5Execution).where(
                                and_(
                                    MT5Execution.closed_at.is_(None),
                                    MT5Execution.executed_at >= cutoff,
                                    MT5Execution.status.in_(["pending", "open", "tp1", "tp2"]),
                                )
                            )
                        )
                    ).scalars().all()

                    if not rows:
                        await session.commit()
                        return

                    account_cache: dict[str, set[str]] = {}

                    def _extract_pos_id(row: dict) -> str:
                        for k in ("id", "positionId", "position_id", "orderId", "order_id"):
                            v = row.get(k)
                            if v is not None and str(v).strip():
                                return str(v).strip()
                        return ""

                    for ex in rows:
                        try:
                            acct = str(getattr(ex, "metaapi_account_id", "") or "").strip()
                            oid = str(getattr(ex, "order_id", "") or "").strip()
                            if not acct or not oid:
                                continue

                            if acct not in account_cache:
                                pos_rows = await list_open_positions(acct)
                                account_cache[acct] = {
                                    _extract_pos_id(r) for r in (pos_rows or []) if _extract_pos_id(r)
                                }

                            open_ids = account_cache.get(acct) or set()
                            in_broker = oid in open_ids

                            if in_broker and str(getattr(ex, "status", "")).lower() == "pending":
                                ex.status = "open"

                            if (not in_broker) and (getattr(ex, "executed_at", now) <= grace_before):
                                # Position not visible at broker after grace period.
                                # Mark closed_unknown to avoid lingering ghost rows.
                                ex.status = "closed_unknown"
                                ex.closed_at = now
                                _meta = dict(getattr(ex, "meta", {}) or {})
                                _meta["broker_reconciled"] = True
                                _meta["broker_state"] = "not_found"
                                ex.meta = _meta
                        except Exception as _ex_err:
                            logger.debug(f"[broker_reconcile] row error: {_ex_err}")

                    await session.commit()

            run_sync(_run())
        except Exception as _br:
            logger.warning(f"[broker_reconcile] job failed: {_br}")


    def orphan_execution_cleanup_job():
        """Cleanup stale/orphaned execution rows to keep ops tables healthy."""
        try:
            from db.session import is_db_configured, get_session
            if not is_db_configured():
                return
            from sqlalchemy import text

            retention_days = int(os.getenv("MT5_EXECUTION_RETENTION_DAYS", "45") or 45)

            async def _run() -> None:
                async with get_session() as session:
                    # Step 1: close ancient still-open rows as orphaned.
                    await session.execute(
                        text(
                            """
                            UPDATE mt5_executions
                            SET status = 'orphaned',
                                closed_at = COALESCE(closed_at, NOW()),
                                meta = COALESCE(meta, '{}'::jsonb) || '{"cleanup_orphaned": true}'::jsonb
                            WHERE closed_at IS NULL
                              AND executed_at < NOW() - (:days || ' days')::interval
                              AND status IN ('pending','open','tp1','tp2','closed_unknown')
                            """
                        ),
                        {"days": str(retention_days)},
                    )

                    # Step 2: delete very old terminal rows that are no longer useful.
                    await session.execute(
                        text(
                            """
                            DELETE FROM mt5_executions
                            WHERE closed_at IS NOT NULL
                              AND closed_at < NOW() - (:days || ' days')::interval
                              AND status IN ('error','orphaned','closed_unknown','closed_by_killsw')
                            """
                        ),
                        {"days": str(retention_days)},
                    )
                    await session.commit()

            run_sync(_run())
        except Exception as _oc:
            logger.warning(f"[orphan_cleanup] job failed: {_oc}")


    def data_integrity_backfill_job():
        """Backfill critical operational tables so required data is not left empty.

        This is conservative/idempotent and only fills missing baseline rows.
        """
        try:
            from db.session import is_db_configured, get_session
            if not is_db_configured():
                return
            from sqlalchemy import text

            async def _run() -> None:
                async with get_session() as session:
                    # 1) Ensure each user has alert preferences row.
                    await session.execute(
                        text(
                            """
                            INSERT INTO alert_prefs (user_id, tp_sl_enabled, quiet_start_hour, quiet_end_hour, updated_at)
                            SELECT u.id, TRUE, NULL, NULL, NOW()
                            FROM users u
                            LEFT JOIN alert_prefs a ON a.user_id = u.id
                            WHERE a.user_id IS NULL
                            """
                        )
                    )

                    # 2) Ensure signals have expiry timestamp for lifecycle jobs.
                    await session.execute(
                        text(
                            """
                            UPDATE signals
                            SET expires_at = COALESCE(expires_at, created_at + INTERVAL '12 hours')
                            WHERE expires_at IS NULL
                            """
                        )
                    )

                    # 3) Repair historical MT5 rows created with telegram_user_id
                    # instead of users.id (legacy bug compatibility).
                    await session.execute(
                        text(
                            """
                            UPDATE mt5_executions m
                            SET user_id = u.id,
                                meta = COALESCE(m.meta, '{}'::jsonb) || '{"user_id_repaired": true}'::jsonb
                            FROM users u
                            WHERE m.user_id = u.telegram_user_id
                              AND m.user_id <> u.id
                            """
                        )
                    )

                    # 4) Ensure mt5 execution status has at least baseline value.
                    await session.execute(
                        text(
                            """
                            UPDATE mt5_executions
                            SET status = 'open'
                            WHERE (status IS NULL OR status = '')
                              AND closed_at IS NULL
                            """
                        )
                    )

                    # 5) Backfill missing closed_at on clearly terminal statuses.
                    await session.execute(
                        text(
                            """
                            UPDATE mt5_executions
                            SET closed_at = COALESCE(closed_at, NOW())
                            WHERE closed_at IS NULL
                              AND status IN ('sl','tp3','tp','smart_exit','orphaned','closed_unknown','closed_by_killsw','error')
                            """
                        )
                    )

                    await session.commit()

            run_sync(_run())
        except Exception as _ib:
            logger.warning(f"[integrity_backfill] job failed: {_ib}")


    def compute_outcomes_best_effort():
        """Best-effort outcome writer.

        Scans recently delivered signals that have no outcome yet, fetches candles,
        and records TP/SL if hit. This enables follow-up messages end-to-end.
        """
        try:
            from db.session import _get_global_engine, get_engine_for_event_loop, get_session
            engine = _get_global_engine()  # ensure engine is initialised in this thread
            if engine is None:
                logger.warning("[outcome] DB engine not initialised — skipping job")
                return
            from db.pg_features import list_signals_missing_outcomes, upsert_outcome
            from datetime import datetime
            from data.fetcher import get_candles

            async def _fetch_candidates():
                async with get_session() as session:
                    recent = await list_signals_missing_outcomes(
                        session,
                        max_age_days=int(os.getenv("OUTCOME_SCAN_MAX_AGE_DAYS", "3") or 3),
                        min_age_hours=0,
                        limit=int(os.getenv("OUTCOME_SCAN_LIMIT", "40") or 40),
                    )
                    catchup = await list_signals_missing_outcomes(
                        session,
                        max_age_days=int(os.getenv("OUTCOME_CATCHUP_MAX_AGE_DAYS", "30") or 30),
                        min_age_hours=int(os.getenv("OUTCOME_CATCHUP_MIN_AGE_HOURS", "24") or 24),
                        limit=int(os.getenv("OUTCOME_CATCHUP_LIMIT", "250") or 250),
                    )
                    await session.commit()
                    dedup: dict[str, object] = {}
                    for _s in list(recent or []) + list(catchup or []):
                        try:
                            _sid = str(getattr(_s, "signal_id", "") or "")
                            if _sid:
                                dedup[_sid] = _s
                        except Exception:
                            continue
                    return list(dedup.values())

            try:
                candidates = run_sync(_fetch_candidates())
            except Exception:
                candidates = []
            if not candidates:
                return

            now = datetime.utcnow()

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
                    tp_levels = _parse_tp_levels_for_outcome(getattr(sig, "take_profit", None))
                    created_at = getattr(sig, "created_at", None)
                    if not asset or not tf or direction not in {"long", "short"}:
                        continue
                    if not tp_levels or created_at is None:
                        continue

                    # Normalize TP ordering in favorable direction
                    if direction == "long":
                        tp_levels = sorted(tp_levels)
                    else:
                        tp_levels = sorted(tp_levels, reverse=True)

                    print(f"[DEBUG][outcome] Evaluating signal {sig.signal_id} {asset} {tf} {direction}", flush=True)

                    candles = get_candles(asset, tf)
                    if not candles:
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
                            print(f"[DEBUG][outcome] No candles found for {asset} {tf}", flush=True)
                            continue

                    created_ms = _ms(created_at)
                    filtered = []
                    for c in candles:
                        try:
                            ts = c.get("timestamp")
                            if isinstance(ts, (int, float)):
                                if int(ts) >= created_ms:
                                    filtered.append(c)
                            else:
                                filtered.append(c)
                        except Exception:
                            continue
                    if not filtered:
                        print(f"[DEBUG][outcome] No filtered candles for {asset} {tf}", flush=True)
                        continue

                    # Only progress outcome status (TP1->TP2->TP3->SL), never backwards or duplicate
                    from db.session import get_session
                    from db.pg_features import get_outcome_for_signal
                    prev_status = None
                    try:
                        async def _get_prev():
                            async with get_session() as session:
                                return await get_outcome_for_signal(session, str(sig.signal_id))
                        prev = run_sync(_get_prev())
                        if prev:
                            prev_status = str(getattr(prev, 'status', '') or '').lower()
                    except Exception:
                        prev_status = None


                    eval_result = evaluate_signal_outcome_from_candles(
                        entry=entry,
                        stop_loss=sl,
                        tp_levels=tp_levels,
                        direction=direction,
                        candles=filtered,
                    )
                    status = eval_result.get("status")
                    entry_filled = bool(eval_result.get("entry_filled"))
                    entry_filled_at = eval_result.get("entry_filled_at")
                    max_tp_hit = int(eval_result.get("max_tp_hit") or 0)

                    if entry_filled and entry_filled_at is not None:
                        print(f"[DEBUG][outcome] Entry filled for {sig.signal_id} at {entry_filled_at}", flush=True)

                    if status == "invalidated":
                        print(f"[DEBUG][outcome] Signal {sig.signal_id} invalidated: SL hit before entry", flush=True)
                    elif status == "missed":
                        print(f"[DEBUG][outcome] Signal {sig.signal_id} missed: entry never touched", flush=True)
                    elif status is None:
                        continue

                    # Only progress outcome status, never duplicate or regress
                    status_order = ["tp1", "tp2", "tp3", "tp", "sl"]
                    if prev_status:
                        try:
                            prev_idx = status_order.index(prev_status) if prev_status in status_order else -1
                            curr_idx = status_order.index(status) if status in status_order else -1
                            if curr_idx <= prev_idx:
                                print(f"[DEBUG][outcome] Skipping duplicate/regressive outcome for {sig.signal_id}: {status} (prev: {prev_status})", flush=True)
                                continue
                        except Exception as e:
                            logger.debug(f"[outcome] Failed to check outcome progression: {e}")
                            pass

                    risk = abs(entry - sl)
                    tp_exit = tp_levels[min(max(max_tp_hit, 1), len(tp_levels)) - 1] if tp_levels else entry
                    reward = abs(float(tp_exit) - entry)
                    r_mult = None
                    pct = None
                    try:
                        if risk > 0:
                            if status.startswith("tp"):
                                r_mult = reward / risk
                            else:
                                r_mult = -1.0
                        if status.startswith("tp"):
                            if direction == "long":
                                pct = ((float(tp_exit) - entry) / entry) * 100.0
                            else:
                                pct = ((entry - float(tp_exit)) / entry) * 100.0
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
                        "tp_levels": tp_levels,
                        "tp_hit_index": max_tp_hit if max_tp_hit > 0 else None,
                        "tp_exit": float(tp_exit) if status and status.startswith("tp") else None,
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

                    print(f"[DEBUG][outcome] Writing outcome for {sig.signal_id}: {status}", flush=True)
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
                        run_sync(_write())
                    except Exception as e:
                        print(f"[DEBUG][outcome] Exception writing outcome: {e}", flush=True)

                    # Fire outcome notifications immediately
                    try:
                        print(f"[DEBUG][outcome] Sending outcome notifications for {sig.signal_id}", flush=True)
                        send_outcome_notifications()
                    except Exception as e:
                        print(f"[DEBUG][outcome] Exception sending notifications: {e}", flush=True)
                except Exception as e:
                    print(f"[DEBUG][outcome] Exception in outcome computation: {e}", flush=True)
                    continue

        except Exception:
            logger.exception("[outcome] compute_outcomes_best_effort failed")

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
        if _is_free_fomo_dispatch_only_enabled():
            logger.debug("[free_summary] skipped (FREE_FOMO_DISPATCH_ONLY=1)")
            return

        # Respect kill-switch
        try:
            if state.get_killswitch_sync().enabled:
                return
        except Exception as e:
            logger.debug(f"[free_summary] Failed to check killswitch: {e}")
            pass

        logger.info("🔄 send_free_delayed_summaries job triggered")

        # Prefer Postgres-backed delayed queue
        try:
            from db.session import get_engine_for_event_loop, get_session
            engine = get_engine_for_event_loop()
            if engine is not None:
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
                        except Exception as e:
                            logger.debug(f"[free_summary] Failed to expire old free signal summaries: {e}")
                            pass
                        due = await get_due_free_signal_summaries_pg(session)
                        out: dict[int, dict] = {}
                        for uid, items in due.items():
                            prefs = await get_alert_prefs_pg(session, int(uid))
                            out[int(uid)] = {"items": items, "prefs": prefs}
                        await session.commit()
                        return out

                try:
                    due = run_sync(_fetch_due())
                    logger.info(f"📬 Free queue check: {len(due)} user(s) with due signals")
                except Exception as e:
                    logger.error(f"Error fetching due signals: {e}", exc_info=True)
                    due = {}

                if not due:
                    logger.info("✅ No free signals due for delivery")
                    return

                async def _deliver_due(_due: dict[int, dict]) -> int:
                    import asyncio

                    now_hour = datetime.now().hour
                    per_user_limit = int(getattr(config, 'FREE_DAILY_LIMIT', 3))
                    actions: list[tuple[int, list[int], list[str], str]] = []
                    bot = Bot(token=_require_telegram_token())

                    async with bot:
                        for uid, data in _due.items():
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
                                except Exception as e:
                                    logger.debug(f"[free_summary] Failed to check quiet hours for user {uid}: {e}")

                            items_to_send = items[:per_user_limit]
                            items_to_skip = items[per_user_limit:]

                            status = 'sent'
                            if items_to_send:
                                msg = _format_free_delayed_digest(items_to_send)
                                try:
                                    await _send_message_with_retry(bot, chat_id=int(uid), text=msg)
                                    await asyncio.sleep(0.5)
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
                        return 0

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
                    return len(actions)

                try:
                    action_count = int(run_sync(_deliver_due(due)) or 0)
                    logger.info(f"💾 Applied {action_count} queue action(s)")
                except Exception as e:
                    logger.error(f"Error delivering/applying free summary actions: {e}", exc_info=True)
                return
        except Exception as e:
            logger.debug(f"[free_summary] Failed to send free summaries: {e}")
            pass

        # Postgres-only: no SQLite fallback
        return

    def auto_retrain_ml_model_job():
        """Automatically retrain ML model when enough outcome data exists."""
        try:
            if state.get_killswitch_sync().enabled:
                return
        except Exception as e:
            logger.debug(f"[ml_retrain] Failed to check killswitch: {e}")
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

            run_sync(_retrain())
        except Exception as e:
            logger.error(f"Error in ML retrain job: {e}", exc_info=True)

    def vip_scarcity_broadcast_job():
        """Broadcast a VIP scarcity nudge to PREMIUM users when seats are available."""
        try:
            if state.get_killswitch_sync().enabled:
                return
        except Exception:
            pass
        try:
            from db.session import get_session
            from db.repository import count_active_vip_users
            from config import OWNER_IDS

            async def _check():
                async with get_session() as session:
                    exclude = set(OWNER_IDS or [])
                    used = await count_active_vip_users(session, exclude_telegram_user_ids=exclude)
                    return used

            used = run_sync(_check())
            vip_limit = int(os.getenv("VIP_SEAT_LIMIT", "15"))
            available = max(0, vip_limit - used)
            if available <= 0:
                return

            from db.pg_compat import get_all_user_ids_compat
            from signalrank_telegram.access import resolve_user_tier
            msg = (
                f"🔥 *VIP Seats Available — {available} of {vip_limit} open!*\n\n"
                "VIP members get:\n"
                "• Real-time signals (30/day)\n"
                "• TP1/TP2/TP3 notifications\n"
                "• One-click MT5 execution\n"
                "• Trailing SL to break-even on TP1\n\n"
                "Seats fill fast. Use /upgrade to claim yours."
            )
            for _uid in (get_all_user_ids_compat() or []):
                try:
                    _t = (resolve_user_tier(int(_uid)) or "free").lower()
                    if _t == "premium":
                        _send_message_with_retry_sync(application.bot, chat_id=int(_uid), text=msg)
                        try:
                            import asyncio
                            run_sync(asyncio.sleep(0.5))
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"[vip_scarcity] job failed: {e}")

    # ── FOMO engine ─────────────────────────────────────────────────────────
    def fomo_engine_job():
        """Broadcast today's VIP highlights to FREE users at 5PM UTC."""
        try:
            if state.get_killswitch_sync().enabled:
                return
        except Exception:
            pass
        try:
            from db.session import get_session as _gs
            from db.models import MT5Execution
            from sqlalchemy import select, func
            from datetime import datetime, timedelta

            async def _fetch_vip_pnl():
                today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                async with _gs() as session:
                    rows = await session.execute(
                        select(
                            func.count().label("trades"),
                            func.sum(MT5Execution.realized_pnl).label("total_pnl"),
                        ).where(
                            MT5Execution.executed_at >= today_start,
                            MT5Execution.tier_at_execution == "VIP",
                            MT5Execution.realized_pnl.isnot(None),
                        )
                    )
                    row = rows.one_or_none()
                    return row

            stats = run_sync(_fetch_vip_pnl())
            trades = int(getattr(stats, "trades", 0) or 0)
            total_pnl = float(getattr(stats, "total_pnl", 0.0) or 0.0)
            if trades == 0:
                return  # Nothing to FOMO about today

            sign = "+" if total_pnl >= 0 else ""
            msg = (
                f"⚡ <b>Today's VIP Execution Recap</b>\n\n"
                f"📊 VIP members executed <b>{trades}</b> trade(s) today\n"
                f"💰 Combined P&amp;L: <b>{sign}${total_pnl:.2f}</b>\n\n"
                f"🎯 Upgrade to VIP for unlimited automated executions.\n"
                f"👉 /tiers to compare plans • /upgrade to subscribe"
            )
            from db.pg_compat import get_all_user_ids_compat
            from signalrank_telegram.access import resolve_user_tier
            for _uid in (get_all_user_ids_compat() or []):
                try:
                    _t = (resolve_user_tier(int(_uid)) or "free").lower()
                    if _t == "free":
                        _send_message_with_retry_sync(application.bot, chat_id=int(_uid), text=msg)
                        try:
                            import asyncio
                            run_sync(asyncio.sleep(0.5))
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception as exc:
            logger.debug(f"[fomo] job failed: {exc}")

    # ── Friday leaderboard ──────────────────────────────────────────────────
    def friday_leaderboard_job():
        """Every Friday at 5PM UTC — 3-block leaderboard broadcast.

        Blocks:
        1) Top 3 Signals
        2) Top 3 VIP MT5 Traders (actual realised PnL)
        3) Top 3 Fantasy Scorers (🔥 votes mapped to outcome pips/points)
        """
        try:
            if state.get_killswitch_sync().enabled:
                return
        except Exception:
            pass
        try:
            from db.session import get_session as _gs
            from db.models import MT5Execution, Outcome, Signal, SignalEngagement, User
            from sqlalchemy import select, func
            from datetime import datetime, timedelta
            import json

            week_start = datetime.utcnow() - timedelta(days=7)

            def _parse_tp_list(raw_tp) -> list[float]:
                if raw_tp is None:
                    return []
                if isinstance(raw_tp, (list, tuple)):
                    out = []
                    for item in raw_tp:
                        try:
                            if isinstance(item, dict):
                                candidate = item.get("price") or item.get("tp") or item.get("target")
                            else:
                                candidate = item
                            out.append(float(candidate))
                        except Exception:
                            continue
                    return [x for x in out if x > 0]
                if isinstance(raw_tp, str):
                    s = raw_tp.strip()
                    if not s:
                        return []
                    try:
                        parsed = json.loads(s)
                        return _parse_tp_list(parsed)
                    except Exception:
                        try:
                            return [float(s)]
                        except Exception:
                            return []
                try:
                    return [float(raw_tp)]
                except Exception:
                    return []

            def _pip_size(asset: str) -> float:
                a = str(asset or "").upper()
                is_fx = len(a) == 6 and a.isalpha()
                if is_fx:
                    return 0.01 if "JPY" in a else 0.0001
                if a.startswith("XAU") or a.startswith("XAG"):
                    return 0.1
                return 1.0  # point-based fallback for non-FX assets

            def _signal_pips(sig: Signal, out: Outcome) -> float | None:
                try:
                    entry = float(getattr(sig, "entry", 0) or 0)
                    sl = float(getattr(sig, "stop_loss", 0) or 0)
                    if entry <= 0:
                        return None
                    direction = str(getattr(sig, "direction", "long") or "long").lower()
                    status = str(getattr(out, "status", "") or "").lower()
                    tps = _parse_tp_list(getattr(sig, "take_profit", None))

                    exit_price = None
                    if status in ("tp", "tp3"):
                        exit_price = tps[-1] if tps else None
                    elif status == "tp2":
                        exit_price = tps[1] if len(tps) > 1 else (tps[-1] if tps else None)
                    elif status == "tp1":
                        exit_price = tps[0] if tps else None
                    elif status == "sl":
                        exit_price = sl if sl > 0 else None
                    else:
                        return None

                    if exit_price is None or exit_price <= 0:
                        return None

                    raw_move = (exit_price - entry) if direction in ("long", "buy") else (entry - exit_price)
                    size = _pip_size(getattr(sig, "asset", ""))
                    if size <= 0:
                        return None
                    pips = raw_move / size

                    if status == "sl" and pips > 0:
                        pips = -abs(pips)
                    if status.startswith("tp") and pips < 0:
                        pips = abs(pips)
                    return float(pips)
                except Exception:
                    return None

            async def _fetch_leaderboard():
                async with _gs() as session:
                    # Block 1: Top 3 signals by realised % this week
                    sig_rows = await session.execute(
                        select(Signal, Outcome)
                        .join(Outcome, Outcome.signal_id == Signal.signal_id)
                        .where(
                            Outcome.closed_at >= week_start,
                            Outcome.status.in_(["tp", "tp1", "tp2", "tp3", "sl"]),
                        )
                    )
                    raw_signals = sig_rows.all()

                    ranked_signals: list[tuple[Signal, Outcome, float]] = []
                    for sig, out in raw_signals:
                        pct = getattr(out, "percent", None)
                        if pct is None:
                            r_mult = getattr(out, "r_multiple", None)
                            if r_mult is not None:
                                pct = float(r_mult) * 100.0
                        try:
                            pct_val = float(pct) if pct is not None else 0.0
                        except Exception:
                            pct_val = 0.0
                        ranked_signals.append((sig, out, pct_val))

                    ranked_signals.sort(key=lambda x: x[2], reverse=True)
                    top_signals = ranked_signals[:3]

                    # Block 2: Top 3 VIP MT5 traders
                    vip_rows = await session.execute(
                        select(
                            MT5Execution.user_id,
                            func.sum(MT5Execution.realized_pnl).label("pnl"),
                            func.count().label("trades"),
                            User.telegram_user_id,
                            User.username,
                        )
                        .join(User, User.id == MT5Execution.user_id)
                        .where(
                            MT5Execution.executed_at >= week_start,
                            MT5Execution.realized_pnl.isnot(None),
                            MT5Execution.tier_at_execution == "VIP",
                        )
                        .group_by(MT5Execution.user_id, User.telegram_user_id, User.username)
                        .order_by(
                            func.sum(MT5Execution.realized_pnl).desc()
                        )
                        .limit(3)
                    )
                    top_vip = vip_rows.all()

                    # Block 3: Top 3 fantasy scorers (🔥 votes weighted by realised pips)
                    fantasy_rows = await session.execute(
                        select(User.telegram_user_id, User.username, Signal, Outcome)
                        .join(SignalEngagement, SignalEngagement.user_id == User.id)
                        .join(Signal, Signal.signal_id == SignalEngagement.signal_id)
                        .join(Outcome, Outcome.signal_id == Signal.signal_id)
                        .where(
                            SignalEngagement.reaction == "taking_it",
                            SignalEngagement.created_at >= week_start,
                            Outcome.closed_at >= week_start,
                            Outcome.status.in_(["tp", "tp1", "tp2", "tp3", "sl"]),
                        )
                    )

                    fantasy_map: dict[int, dict] = {}
                    for tg_id, uname, sig, out in fantasy_rows.all():
                        try:
                            tg_uid = int(tg_id)
                        except Exception:
                            continue
                        pips = _signal_pips(sig, out)
                        if pips is None:
                            continue
                        slot = fantasy_map.setdefault(
                            tg_uid,
                            {"username": uname, "score": 0.0, "count": 0},
                        )
                        slot["score"] = float(slot["score"] or 0.0) + float(pips)
                        slot["count"] = int(slot["count"] or 0) + 1

                    top_fantasy = sorted(
                        fantasy_map.items(),
                        key=lambda kv: float(kv[1].get("score") or 0.0),
                        reverse=True,
                    )[:3]

                    return top_signals, top_vip, top_fantasy

            top_signals, top_traders, top_fantasy = run_sync(_fetch_leaderboard())
            if not top_signals and not top_traders and not top_fantasy:
                return

            lines = ["🏆 <b>Friday Leaderboard</b>", ""]
            medals = ["🥇", "🥈", "🥉"]

            # Block 1: Top 3 Signals
            lines.append("<b>Top 3 Signals</b>")
            if top_signals:
                for i, (sig, out, pct_val) in enumerate(top_signals):
                    asset = str(getattr(sig, "asset", "?") or "?")
                    tf = str(getattr(sig, "timeframe", "?") or "?")
                    direction = str(getattr(sig, "direction", "?") or "?").upper()
                    status = str(getattr(out, "status", "?") or "?").upper()
                    sign = "+" if pct_val >= 0 else ""
                    lines.append(
                        f"{medals[i]} <b>{asset}</b> {direction} ({tf})  {status}  {sign}{pct_val:.2f}%"
                    )
            else:
                lines.append("• No closed signal outcomes this week")

            lines.append("")
            lines.append("<b>Top 3 VIP MT5 Traders</b>")
            for i, row in enumerate(top_traders):
                uid = row.user_id
                pnl = float(row.pnl or 0)
                trades = int(row.trades or 0)
                sign = "+" if pnl >= 0 else ""
                tg_uid = getattr(row, "telegram_user_id", None)
                uname = (getattr(row, "username", None) or "").strip()
                trader_label = f"@{uname}" if uname else f"Trader #{tg_uid or uid}"
                lines.append(
                    f"{medals[i]} <b>{trader_label}</b>  "
                    f"{sign}${pnl:.2f}  ({trades} trades)"
                )
            if not top_traders:
                lines.append("• No VIP MT5 realised trades this week")

            lines.append("")
            lines.append("<b>Top 3 Fantasy Scorers</b>")
            if top_fantasy:
                for i, (tg_uid, data) in enumerate(top_fantasy):
                    uname = str(data.get("username") or "").strip()
                    label = f"@{uname}" if uname else f"User {tg_uid}"
                    score = float(data.get("score") or 0.0)
                    picks = int(data.get("count") or 0)
                    sign = "+" if score >= 0 else ""
                    lines.append(
                        f"{medals[i]} <b>{label}</b>  {sign}{score:.1f} pips  ({picks} voted signals)"
                    )
            else:
                lines.append("• No fantasy score data this week")

            lines.append(
                "\n💡 Join VIP for automated execution and leaderboard inclusion.\n"
                "👉 /upgrade"
            )
            msg = "\n".join(lines)
            from db.pg_compat import get_all_user_ids_compat
            for _uid in (get_all_user_ids_compat() or []):
                try:
                    _send_message_with_retry_sync(application.bot, chat_id=int(_uid), text=msg)
                    try:
                        import asyncio
                        run_sync(asyncio.sleep(0.5))
                    except Exception:
                        pass
                except Exception:
                    pass
        except Exception as exc:
            logger.debug(f"[leaderboard] job failed: {exc}")

    # ── Signal auto-expiry ──────────────────────────────────────────────────
    def expire_old_signals_job():
        """Mark signals where expires_at < now as expired=True, excluding unresolved tracked states."""
        try:
            from db.session import get_session as _gs
            from db.models import Signal, Outcome
            from sqlalchemy import select, update, and_
            from datetime import datetime

            async def _expire():
                now = datetime.utcnow()
                async with _gs() as session:
                    unresolved_tracked = (
                        select(Outcome.id)
                        .where(
                            and_(
                                Outcome.signal_id == Signal.signal_id,
                                Outcome.status.in_(["tp1", "tp2"]),
                            )
                        )
                        .exists()
                    )
                    await session.execute(
                        update(Signal)
                        .where(
                            Signal.expires_at <= now,
                            Signal.expired.is_(False),
                            ~unresolved_tracked,
                        )
                        .values(expired=True)
                    )
                    await session.commit()

            run_sync(_expire())
        except Exception as exc:
            logger.debug(f"[expiry] expire_old_signals_job failed: {exc}")

    def refresh_monitor_snapshots_job():
        """Refresh open monitor sub-pages every 5 minutes."""
        try:
            async def _refresh() -> None:
                from db.session import get_session as _gs_mon
                from db.models import RuntimeState
                from sqlalchemy import select

                bot = Bot(token=_require_telegram_token())
                async with _gs_mon() as session:
                    rows = (
                        await session.execute(
                            select(RuntimeState).where(RuntimeState.key.like("monitor:%"))
                        )
                    ).scalars().all()

                    async with bot:
                        for row in rows:
                            payload = dict(row.value or {})
                            signal_id = str(payload.get("signal_id") or "")
                            chat_id = payload.get("chat_id")
                            message_id = payload.get("message_id")
                            if not signal_id or not chat_id or not message_id:
                                await session.delete(row)
                                continue
                            text, is_active, expires_at = await _build_monitor_snapshot(signal_id)
                            try:
                                await bot.edit_message_text(
                                    chat_id=int(chat_id),
                                    message_id=int(message_id),
                                    text=text,
                                    parse_mode="HTML",
                                    reply_markup=_build_monitor_keyboard(signal_id),
                                )
                            except Exception as exc:
                                if "message is not modified" not in str(exc).lower():
                                    logger.debug(f"[monitor] refresh edit failed for {signal_id}: {exc}")
                            row.updated_at = datetime.utcnow()
                            row.expires_at = expires_at
                            if not is_active:
                                await session.delete(row)
                    await session.commit()

            run_sync(_refresh())
        except Exception as exc:
            logger.debug(f"[monitor] refresh job failed: {exc}")

    # ── ML market analysis scan ────────────────────────────────────────────
    def ml_market_analysis_job():
        """Every 15 min: run the ML filter over recent unscored signals.

        This makes ML activity visible in APScheduler logs.  Live market
        features are taken from the signal rows already stored by the engine
        loop (which populates indicators, ATR, regime, etc. before persisting).
        """
        try:
            if state.get_killswitch_sync().enabled:
                return
        except Exception:
            pass

        logger.info("🤖 [ML] Market analysis scan starting …")

        try:
            from ml.inference import MLFilter
            from ml.features import extract_features
        except ImportError:
            logger.warning("[ML] ml.inference not available — analysis scan skipped")
            return

        try:
            ml_filter = MLFilter()
            if not getattr(ml_filter, "active", False):
                logger.info("[ML] Model not loaded — scan skipped (train first)")
                return

            threshold_raw = str(os.getenv("ML_PROB_THRESHOLD") or "").strip()
            threshold = float(threshold_raw) if threshold_raw else None

            async def _scan():
                from db.session import get_session
                from db.models import Signal
                from sqlalchemy import select
                from datetime import datetime, timedelta

                cutoff = datetime.utcnow() - timedelta(hours=4)
                async with get_session() as session:
                    rows = await session.execute(
                        select(Signal).where(
                            Signal.created_at >= cutoff,
                            Signal.ml_probability.is_(None),
                            Signal.expired.is_(False),
                            Signal.status.not_like("shadow_%"),
                        ).limit(50)
                    )
                    signals = rows.scalars().all()

                approved = rejected = errors = 0
                for sig_row in signals:
                    try:
                        sig_dict = {
                            col.name: getattr(sig_row, col.name)
                            for col in sig_row.__table__.columns
                        }
                        features = extract_features(sig_dict, {})
                        ok, prob = ml_filter.ml_filter(features, threshold=threshold)
                        if ok:
                            approved += 1
                        else:
                            rejected += 1
                    except Exception as fe:
                        errors += 1
                        logger.debug("[ML] feature error: %s", fe)
                return len(signals), approved, rejected, errors

            total, approved, rejected, errors = run_sync(_scan())
            threshold_label = f"{threshold:.2f}" if threshold is not None else "auto"
            logger.info(
                "🤖 [ML] Scan done — signals=%d  approved=%d  rejected=%d  "
                "errors=%d  threshold=%s",
                total, approved, rejected, errors, threshold_label,
            )
        except Exception as exc:
            logger.error("[ML] ml_market_analysis_job failed: %s", exc, exc_info=True)

    def weekly_gemini_ml_review_job():
        """Weekly Gemini review plus model retrain from recent aggregate window."""
        try:
            _enabled = str(os.getenv("GEMINI_REVIEW_ENABLED", "1") or "1").strip().lower() in {
                "1", "true", "yes", "y", "on"
            }
            if not _enabled:
                logger.info("[gemini] weekly job disabled via GEMINI_REVIEW_ENABLED=0")
                return
            from services.gemini_ml import run_gemini_review_pipeline

            result = run_sync(
                run_gemini_review_pipeline(trigger="scheduler:weekly", scope="weekly"),
                timeout=1800.0,
            )
            if bool(result.get("ok", False)):
                logger.info("[gemini] weekly run complete: training=%s", bool((result.get("training") or {}).get("succeeded", False)))
                # Notify all owners via DM so the review is visible without needing to
                # run /gemini_review manually.
                try:
                    from config import OWNER_IDS as _owner_ids_gemini
                    _wh_app = _webhook_application or globals().get("application")
                    if _wh_app and _owner_ids_gemini:
                        _rx = result.get("received") or {}
                        _wins = int(_rx.get("wins") or 0)
                        _losses = int(_rx.get("losses") or 0)
                        _total = int(_rx.get("outcomes_total") or 0)
                        _wr = f"{_wins/max(1,_wins+_losses)*100:.1f}%" if (_wins + _losses) > 0 else "n/a"
                        _review_snippet = str(result.get("review") or "")
                        _snippet = (_review_snippet[:500] + "…") if len(_review_snippet) > 500 else _review_snippet
                        _training_ok = bool((result.get("training") or {}).get("succeeded", False))
                        _msg = (
                            "✅ <b>Weekly Gemini Review Complete</b>\n\n"
                            f"Win rate: <b>{_wr}</b> ({_wins}W / {_losses}L of {_total} outcomes)\n"
                            f"Model retrained: <b>{'yes' if _training_ok else 'no'}</b>\n\n"
                            + (_snippet or "<i>No review text returned.</i>")
                        )
                        async def _notify_owners_gemini():
                            for _oid in _owner_ids_gemini:
                                try:
                                    await _wh_app.bot.send_message(
                                        chat_id=int(_oid),
                                        text=_msg,
                                        parse_mode="HTML",
                                    )
                                except Exception as _dm_err:
                                    logger.debug("[gemini] owner DM failed for %s: %s", _oid, _dm_err)
                        run_sync(_notify_owners_gemini(), timeout=30.0)
                except Exception as _notify_err:
                    logger.debug("[gemini] weekly owner notification failed: %s", _notify_err)
            else:
                logger.warning("[gemini] weekly run skipped/failed: %s", result.get("error"))
        except Exception as exc:
            logger.warning(f"[gemini] weekly ML review failed: {exc}")

    def daily_gemini_ml_review_job():
        """Daily Gemini review using last 24-hour scope for faster feedback loops."""
        try:
            _enabled = str(os.getenv("GEMINI_REVIEW_ENABLED", "1") or "1").strip().lower() in {
                "1", "true", "yes", "y", "on"
            }
            _daily_enabled = str(os.getenv("GEMINI_DAILY_REVIEW_ENABLED", "1") or "1").strip().lower() in {
                "1", "true", "yes", "y", "on"
            }
            if not _enabled or not _daily_enabled:
                logger.info("[gemini] daily review disabled by env flag")
                return
            from services.gemini_ml import run_gemini_review_pipeline
            result = run_sync(
                run_gemini_review_pipeline(trigger="scheduler:daily", scope="weekly"),
                timeout=600.0,
            )
            if bool(result.get("ok", False)):
                logger.info("[gemini] daily review complete: training=%s", bool((result.get("training") or {}).get("succeeded", False)))
            else:
                logger.info("[gemini] daily review skipped/failed: %s", result.get("error"))
        except Exception as exc:
            logger.warning("[gemini] daily ML review failed: %s", exc)

    # ── APScheduler setup ───────────────────────────────────────────────────
    # APScheduler 3.x's SQLAlchemyJobStore uses *synchronous* SQLAlchemy.
    # Passing an asyncpg:// URL causes the driver to be rejected and the store
    # to silently fall back to  postgresql://postgres@localhost  — which Railway
    # always rejects with "password authentication failed for user postgres".
    # Strip the async driver prefix before creating the job store.
    _sched_raw = (resolve_database_url(async_driver=False) or "").strip()
    _sched_sync_url: str | None = None
    if _sched_raw:
        _sched_sync_url = _sched_raw
        for _pfx, _rep in (
            ("postgresql+asyncpg://", "postgresql://"),
            ("postgres://", "postgresql://"),
        ):
            if _sched_sync_url.startswith(_pfx):
                _sched_sync_url = _sched_sync_url.replace(_pfx, _rep, 1)
                break

    # Register a 'persistent' jobstore for module-level (picklable) callables.
    # Closure functions defined inside run_bot() cannot be pickled for
    # SQLAlchemy — they are added to the implicit default MemoryJobStore.
    _jobstores: dict = {}
    if _sched_sync_url:
        try:
            from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore as _SAJobStore
            _jobstore_engine_options = {
                "pool_size": max(1, _env_int("BOT_SCHEDULER_DB_POOL_SIZE", 1)),
                "max_overflow": max(0, _env_int("BOT_SCHEDULER_DB_MAX_OVERFLOW", 0)),
                "pool_timeout": max(1, _env_int("BOT_SCHEDULER_DB_POOL_TIMEOUT_SECONDS", 30)),
                "pool_recycle": max(30, _env_int("BOT_SCHEDULER_DB_POOL_RECYCLE_SECONDS", 1800)),
                "pool_pre_ping": True,
            }
            _jobstores["persistent"] = _SAJobStore(
                url=_sched_sync_url,
                engine_options=_jobstore_engine_options,
            )
            logger.info(
                "[sched] SQLAlchemyJobStore ready → %s (pool_size=%s max_overflow=%s)",
                _mask_db_url_host(_sched_sync_url),
                _jobstore_engine_options["pool_size"],
                _jobstore_engine_options["max_overflow"],
            )
        except Exception as _sa_err:
            logger.warning(
                "[sched] SQLAlchemyJobStore unavailable (%s) — using MemoryJobStore",
                _sa_err,
            )

    # _sa: alias for the store to use for picklable module-level jobs.
    _sa = "persistent" if "persistent" in _jobstores else "default"

    # Cross-process scheduler ownership lock (important when multiple workers/
    # replicas are alive). Only the lock holder starts APScheduler jobs.
    _scheduler_enabled = True
    # PATCH: Always enable scheduler in single-instance mode (Railway Free Tier)
    # so resend job and all critical jobs run, even if not lock-owner.
    # The lock logic is bypassed to ensure jobs are always scheduled.
    # If you ever run multiple instances, restore the lock logic for safety.

    scheduler = None
    if _scheduler_enabled:
        from apscheduler.executors.pool import ThreadPoolExecutor as _APThreadPoolExecutor
        _running_on_railway = bool((os.getenv("RAILWAY_SERVICE_NAME") or "").strip() or (os.getenv("RAILWAY_ENVIRONMENT") or "").strip())
        _sched_default_workers = 4 if _running_on_railway else 12
        _sched_workers = max(2, _env_int("BOT_SCHEDULER_MAX_WORKERS", _sched_default_workers))
        _executors = {
            "default": _APThreadPoolExecutor(max_workers=_sched_workers),
        }
        # job_defaults ensure that:
        #  - coalesce=True collapses multiple missed firings into one, preventing
        #    job storms after startup lag or container restarts.
        #  - misfire_grace_time=60 discards a job only if it misfired by more than
        #    60 s, which avoids cascaded submissions that race with executor shutdown.
        #  - max_instances=1 prevents concurrent overlapping runs of the same job.
        _job_defaults = {
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 60,
        }
        scheduler = BackgroundScheduler(
            jobstores=_jobstores or {},
            executors=_executors,
            job_defaults=_job_defaults,
            timezone="UTC",
        )
        logger.info(
            "[sched] BackgroundScheduler created workers=%s jobstore=%s job_defaults=%s",
            _sched_workers,
            _sa,
            _job_defaults,
        )

    # Clear stale jobs in the persistent store to prevent duplicates on restart.
    if scheduler is not None:
        try:
            if _sa != "default":
                scheduler.remove_all_jobs(jobstore=_sa)
                logger.info("[sched] cleared stale jobs from jobstore=%s", _sa)
        except Exception as _clr_err:
            logger.warning("[sched] failed to clear jobstore=%s: %s", _sa, _clr_err)

    # ── Closure jobs (defined inside run_bot — cannot be pickled for SQLAlchemy)
    # These always land in the default MemoryJobStore.
    if scheduler is not None:
        _minimal_scheduler_mode = str(
            os.getenv(
                "BOT_MINIMAL_SCHEDULER_MODE",
                "1" if _running_on_railway else "0",
            )
        ).strip().lower() in {"1", "true", "yes", "on"}

        if _minimal_scheduler_mode:
            logger.info("[sched] minimal mode enabled: scheduling only core closure jobs")
            scheduler.add_job(
                compute_outcomes_best_effort,
                'interval',
                minutes=5,
                id='compute_outcomes_best_effort',
                replace_existing=True,
                max_instances=1,
            )
            scheduler.add_job(
                send_outcome_notifications,
                'interval',
                minutes=3,
                id='send_outcome_notifications',
                replace_existing=True,
                max_instances=1,
            )
            scheduler.add_job(
                refresh_monitor_snapshots_job,
                'interval',
                minutes=10,
                id='refresh_monitor_snapshots_job',
                replace_existing=True,
                max_instances=1,
            )
            # Signal expiry must also run in minimal mode so signals transition
            # to an expired terminal state when their expires_at timestamp passes.
            scheduler.add_job(
                expire_old_signals_job,
                'interval',
                minutes=30,
                id='expire_old_signals_job',
                replace_existing=True,
                max_instances=1,
            )
        else:
            scheduler.add_job(
                ml_market_analysis_job,
                'interval',
                minutes=15,
                id='ml_market_analysis',
                replace_existing=True,
                max_instances=1,
            )
            scheduler.add_job(
                send_free_delayed_summaries,
                'interval',
                minutes=10,
                id='send_free_delayed_summaries',
                replace_existing=True,
                max_instances=1,
            )
            scheduler.add_job(
                compute_outcomes_best_effort,
                'interval',
                minutes=3,
                id='compute_outcomes_best_effort',
                replace_existing=True,
                max_instances=1,
            )
            scheduler.add_job(
                refresh_monitor_snapshots_job,
                'interval',
                minutes=5,
                id='refresh_monitor_snapshots_job',
                replace_existing=True,
                max_instances=1,
            )
            scheduler.add_job(
                send_outcome_notifications,
                'interval',
                minutes=2,
                id='send_outcome_notifications',
                replace_existing=True,
                max_instances=1,
            )
            scheduler.add_job(
                smart_exit_guard_job,
                'interval',
                minutes=5,
                id='smart_exit_guard_job',
                replace_existing=True,
                max_instances=1,
            )
            scheduler.add_job(
                drawdown_circuit_breaker_job,
                'interval',
                minutes=5,
                id='drawdown_circuit_breaker_job',
                replace_existing=True,
                max_instances=1,
            )
            scheduler.add_job(
                killswitch_close_all_watchdog_job,
                'interval',
                minutes=1,
                id='killswitch_close_all_watchdog_job',
                replace_existing=True,
                max_instances=1,
            )
            scheduler.add_job(
                broker_reconciliation_job,
                'interval',
                minutes=6,
                id='broker_reconciliation_job',
                replace_existing=True,
                max_instances=1,
            )
            scheduler.add_job(
                orphan_execution_cleanup_job,
                'cron',
                hour=3,
                minute=30,
                id='orphan_execution_cleanup_job',
                replace_existing=True,
                max_instances=1,
            )
            scheduler.add_job(
                data_integrity_backfill_job,
                'interval',
                minutes=10,
                id='data_integrity_backfill_job',
                replace_existing=True,
                max_instances=1,
                next_run_time=datetime.utcnow(),
            )
            scheduler.add_job(
                vip_scarcity_broadcast_job,
                'interval',
                hours=6,
                id='vip_scarcity_broadcast_job',
                replace_existing=True,
                max_instances=1,
            )
            scheduler.add_job(
                fomo_engine_job,
                'cron',
                hour=17,
                minute=0,
                id='fomo_engine_job',
                replace_existing=True,
                max_instances=1,
            )
            scheduler.add_job(
                friday_leaderboard_job,
                'cron',
                day_of_week='fri',
                hour=17,
                minute=0,
                id='friday_leaderboard_job',
                replace_existing=True,
                max_instances=1,
            )
            scheduler.add_job(
                expire_old_signals_job,
                'interval',
                minutes=30,
                id='expire_old_signals_job',
                replace_existing=True,
                max_instances=1,
            )
            scheduler.add_job(
                send_weekly_recap,
                'cron',
                day_of_week='sun',
                hour=18,
                minute=0,
                id='send_weekly_recap',
                replace_existing=True,
                max_instances=1,
            )
            scheduler.add_job(
                auto_retrain_ml_model_job,
                'cron',
                day_of_week='sun',
                hour=2,
                minute=0,
                id='auto_retrain_ml_model_job',
                replace_existing=True,
                max_instances=1,
            )
            scheduler.add_job(
                weekly_gemini_ml_review_job,
                'cron',
                day_of_week='sun',
                hour=3,
                minute=0,
                id='weekly_gemini_ml_review_job',
                replace_existing=True,
                max_instances=1,
            )
            # Daily Gemini review — runs every day at 04:00 UTC for fast feedback
            scheduler.add_job(
                daily_gemini_ml_review_job,
                'cron',
                hour=4,
                minute=0,
                id='daily_gemini_ml_review_job',
                replace_existing=True,
                max_instances=1,
            )

    # ── Module-level jobs (picklable) → SQLAlchemy persistent store when available
    if scheduler is not None:
        try:
            from worker.proxy_worker import proxy_validation_job as _proxy_validation_job
            scheduler.add_job(
                _proxy_validation_job,
                'interval',
                minutes=30,
                id='proxy_validation_job',
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=120,
                jobstore=_sa,
            )
        except Exception as _proxy_job_err:
            logger.warning("[sched] failed to schedule proxy_validation_job: %s", _proxy_job_err)
        scheduler.add_job(
            resend_unsent_signals_job,
            'interval',
            minutes=1,
            id='resend_unsent_signals_job',
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=20,
            jobstore=_sa,
            next_run_time=datetime.utcnow(),
        )
        scheduler.add_job(
            distribute_random_signals_to_free_users_job,
            'interval',
            minutes=15,
            id='distribute_random_signals_to_free_users_job',
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=120,
            jobstore=_sa,
        )
        scheduler.add_job(
            downgrade_expired_subscriptions_job,
            'cron',
            hour=0,
            minute=0,
            id='downgrade_expired_subscriptions_job',
            replace_existing=True,
            max_instances=1,
            jobstore=_sa,
        )
        scheduler.add_job(
            auto_delete_old_signals_job,
            'cron',
            day_of_week='sun',
            hour=1,
            minute=0,
            id='auto_delete_old_signals_job',
            replace_existing=True,
            max_instances=1,
            jobstore=_sa,
        )

logger.info("[sched] BackgroundScheduler starting (state=pre_start)")
        scheduler.start()
        logger.info("[sched] BackgroundScheduler started (state=running jobs=%d)", len(scheduler.get_jobs()))

    # Register scheduled jobs for signal distribution and system maintenance
    # This includes distribute_random_signals_to_free_users_job (every 30min)
    try:
        _schedule_bot_jobs(scheduler)
    except Exception as _sched_err:
        logger.warning(f"[sched] _schedule_bot_jobs failed: {_sched_err}")

    # One-shot startup migration: refresh keyboards on previously sent active messages.
    try:
        refresh_active_signal_keyboards_once()
    except Exception as _kbd_backfill_err:
        logger.debug(f"[backfill] startup keyboard refresh failed: {_kbd_backfill_err}")

    # ── Webhook mode ──────────────────────────────────────────────────────────
    # When TELEGRAM_USE_WEBHOOK is set, railway_main.py owns the event loop and
    # calls application.process_update() via the POST /telegram/webhook FastAPI
    # route.  Store the configured application and scheduler so they survive
    # this function's scope, then return without starting long-polling.
    if os.getenv("TELEGRAM_USE_WEBHOOK"):
        _webhook_application = application
        _bot_scheduler = scheduler  # prevent GC; daemon threads keep running
        _refresh_webhook_handlers_ready("webhook_return")
        if scheduler is None:
            print("[bot] webhook mode: application ready, scheduler disabled on this instance", flush=True)
        else:
            print("[bot] webhook mode: application ready, scheduler running, not polling", flush=True)
        return

    # ── Polling mode ──────────────────────────────────────────────────────────
    # Run polling with an explicit event loop (Python 3.12 safe)
    try:
        import asyncio as _asyncio
        loop = _asyncio.new_event_loop()
        _asyncio.set_event_loop(loop)
        print("[boot] telegram bot polling starting", flush=True)
        application.run_polling()
    except Exception:
        # Last resort: retry without custom loop
        print("[boot] telegram bot polling starting", flush=True)
        application.run_polling()


if __name__ == "__main__":
    run_bot()
