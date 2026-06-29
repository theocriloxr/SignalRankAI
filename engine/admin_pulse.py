"""
engine/admin_pulse.py

Hourly admin pulse that computes engine health summary, including shadow regret
metrics, and posts to owner/admin Telegram IDs.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


async def compute_engine_health(window_hours: int = 1) -> dict[str, Any]:
    """Collect engine health stats for the last `window_hours` hours.
    
    Now uses GlobalStats for real-time engine metrics instead of only DB queries.
    Falls back to DB-only if GlobalStats not available.
    """
    # Try to get stats from GlobalStats first (real-time from engine).
    # A fresh deploy can legitimately have cold Redis/process counters while DB
    # rows already prove recent activity, so DB evidence is merged below.
    global_scanned = 0
    global_delivered = 0
    global_vetoed = {}
    use_global_stats = False
    
    try:
        from engine.stats_manager import stats
        global_stats = stats.get_stats()
        global_scanned = global_stats.get("scanned", 0)
        global_delivered = global_stats.get("delivered", 0)
        global_vetoed = {
            "regime": global_stats.get("vetoed_regime", 0),
            "squeeze": global_stats.get("vetoed_squeeze", 0),
            "microstructure": global_stats.get("vetoed_microstructure", 0),
            "score": global_stats.get("vetoed_score", 0),
            "ml": global_stats.get("vetoed_ml", 0),
            "other": global_stats.get("vetoed_other", 0),
        }
        use_global_stats = True
        logger.info("[admin_pulse] Using GlobalStats for real-time metrics")
    except ImportError:
        logger.debug("[admin_pulse] GlobalStats not available, using DB fallback")
    
    # Always get DB-based counts for delivered signals and shadow metrics
    try:
        from db.session import get_session
        from sqlalchemy import text
        from core.redis_state import state

        since = datetime.now(timezone.utc) - timedelta(hours=max(1, int(window_hours or 1)))
        params = {"since": since}
        
        async with get_session() as session:
            # Check if created_at column exists in decision_log
            try:
                scanned_row = (
                    await session.execute(
                        text("SELECT COUNT(*) FROM decision_log WHERE created_at >= :since"),
                        params,
                    )
                ).first()
                db_scanned = int(scanned_row[0] or 0) if scanned_row else 0

                # Rejected by risk / score
                rej_rows = (
                    await session.execute(
                        text("SELECT decision, COUNT(*) FROM decision_log WHERE created_at >= :since GROUP BY decision"),
                        params,
                    )
                ).fetchall()
                db_rejected_by = {str(r[0] or ""): int(r[1] or 0) for r in (rej_rows or [])}
            except Exception as e:
                # Fallback if created_at column doesn't exist yet
                if "created_at" in str(e):
                    logger.warning("[admin_pulse] created_at column missing in decision_log - using fallback")
                    db_scanned = 0
                    db_rejected_by = {}
                else:
                    db_scanned = 0
                    db_rejected_by = {}

                # SignalDelivery uses delivered_at in the ORM; some old tables
                # may have created_at, so try delivered_at first then fallback.
            try:
                delivered_row = (
                    await session.execute(
                        text(
                            "SELECT COUNT(DISTINCT signal_id) FROM signal_deliveries WHERE delivered_at >= :since AND sent_ok IS TRUE"
                        ),
                        params,
                    )
                ).first()
                db_delivered = int(delivered_row[0] or 0) if delivered_row else 0
            except Exception as e:
                try:
                    delivered_row = (
                        await session.execute(
                        text(
                            "SELECT COUNT(DISTINCT signal_id) FROM signal_deliveries WHERE created_at >= :since AND sent_ok IS TRUE"
                        ),
                            params,
                        )
                    ).first()
                    db_delivered = int(delivered_row[0] or 0) if delivered_row else 0
                except Exception:
                    db_delivered = 0

            try:
                issued_row = (
                    await session.execute(
                        text("SELECT COUNT(*) FROM signals WHERE created_at >= :since"),
                        params,
                    )
                ).first()
                db_issued = int(issued_row[0] or 0) if issued_row else 0
            except Exception:
                db_issued = 0
    except Exception as db_err:
        logger.debug("[admin_pulse] DB query failed: %s", db_err)
        db_scanned = 0
        db_delivered = 0
        db_issued = 0
        db_rejected_by = {}

    # Get shadow counters from Redis
    try:
        from core.redis_state import state
        total_tracked = int(state.get_sync("shadow:counts:total_tracked") or 0)
        false_neg = int(state.get_sync("shadow:counts:false_negative") or 0)
        correct_block = int(state.get_sync("shadow:counts:correct_block") or 0)
        partial_win = int(state.get_sync("shadow:counts:partial_win") or 0)
    except Exception:
        total_tracked = false_neg = correct_block = partial_win = 0

    shadow_winner_rate = (false_neg / max(1, total_tracked)) * 100.0 if total_tracked > 0 else 0.0

    global_total = int(global_scanned or 0) + int(global_delivered or 0) + sum(int(v or 0) for v in (global_vetoed or {}).values())
    db_rejected_total = sum(int(v or 0) for v in (db_rejected_by or {}).values())
    db_scanned_evidence = max(int(db_scanned or 0), int(db_issued or 0), int(db_delivered or 0), int(db_rejected_total or 0))
    scanned = max(int(global_scanned or 0), db_scanned_evidence)
    delivered = max(int(global_delivered or 0), int(db_delivered or 0))
    rejected_by = global_vetoed if (use_global_stats and global_total > 0) else db_rejected_by

    return {
        "scanned": scanned,
        "delivered": delivered,
        "rejected_by": rejected_by,
        "sources": {
            "global_stats": bool(use_global_stats),
            "global_total": int(global_total),
            "db_decisions": int(db_scanned or 0),
            "db_signals": int(db_issued or 0),
            "db_deliveries": int(db_delivered or 0),
        },
        "shadow": {
            "total_tracked": total_tracked,
            "false_negative": false_neg,
            "correct_block": correct_block,
            "partial_win": partial_win,
            "shadow_winner_rate_pct": shadow_winner_rate,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


async def send_admin_pulse_via_telegram(window_hours: int = 1) -> bool:
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        logger.debug("[admin_pulse] no telegram token configured")
        return False
    try:
        from config import OWNER_IDS, ADMIN_IDS
        recipients = sorted({int(x) for x in ((OWNER_IDS or set()) | (ADMIN_IDS or set()))})
        if not recipients:
            logger.debug("[admin_pulse] no recipients configured")
            return False

        stats = await compute_engine_health(window_hours=window_hours)
        txt = (
            f"Engine Pulse ({window_hours}h)\n\n"
            f"Total Scanned: {stats.get('scanned', 0)}\n"
            f"Delivered: {stats.get('delivered', 0)}\n"
            "Rejected breakdown:\n"
        )
        for k, v in (stats.get("rejected_by") or {}).items():
            txt += f"- {k}: {v}\n"
        sh = stats.get("shadow") or {}
        txt += (
            f"\nShadow (tracked rejects): {sh.get('total_tracked', 0)}\n"
            f"False Negatives (would have hit TP3): {sh.get('false_negative', 0)}\n"
            f"Correct Blocks (would have hit SL): {sh.get('correct_block', 0)}\n"
            f"Partial Wins: {sh.get('partial_win', 0)}\n"
            f"Shadow Winner Rate: {sh.get('shadow_winner_rate_pct', 0.0):.1f}%\n"
        )
        src = stats.get("sources") or {}
        if int(src.get("global_total") or 0) == 0 and int(src.get("db_decisions") or 0) == 0 and int(src.get("db_signals") or 0) == 0:
            txt += "\nNote: no engine/DB activity was observed in this window yet; this may be a cold-start pulse.\n"

        import requests

        for rid in recipients:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": int(rid), "text": txt},
                    timeout=6,
                )
            except Exception:
                continue
        return True
    except Exception as exc:
        logger.error("[admin_pulse] send error: %s", exc)
        return False


async def send_weekly_filter_efficacy_via_telegram(window_days: int = 7) -> bool:
    """Run Gemini weekly filter-efficacy review and post summary to admins.

    This delegates to services.gemini_ml.run_gemini_review_pipeline which already
    collects DB aggregates and stores the review in runtime_state.
    """
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        logger.debug("[admin_pulse] no telegram token configured for weekly report")
        return False
    try:
        from config import OWNER_IDS, ADMIN_IDS
        recipients = sorted({int(x) for x in ((OWNER_IDS or set()) | (ADMIN_IDS or set()))})
        if not recipients:
            logger.debug("[admin_pulse] no recipients configured for weekly report")
            return False

        api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
        if not api_key:
            logger.debug("[admin_pulse] GEMINI_API_KEY not configured; skipping weekly filter efficacy")
            return False

        # run the gemini weekly pipeline (it persists results and returns review)
        try:
            from services import gemini_ml
            review = await gemini_ml.run_gemini_review_pipeline(trigger="weekly_filter_efficacy", scope="weekly")
        except Exception as exc:
            logger.exception("[admin_pulse] gemini weekly review failed: %s", exc)
            return False

        # Build message: concise top-level summary + short delivered vs shadow outcome table
        summary = review.get("review") if isinstance(review, dict) else str(review or "")
        stats = review.get("aggregate") if isinstance(review, dict) else {}

        # Delivered outcomes (DB): last window_days days
        delivered_total = delivered_wins = delivered_losses = 0
        try:
            from db.session import get_session
            from sqlalchemy import text
            since = datetime.now(timezone.utc) - timedelta(days=max(1, int(window_days or 7)))
            async with get_session() as session:
                row = (await session.execute(
                    text(
                        "SELECT COUNT(*) AS total, SUM(CASE WHEN o.status IN ('tp','tp1','tp2','tp3','partial_tp') THEN 1 ELSE 0 END) AS wins, SUM(CASE WHEN o.status = 'sl' THEN 1 ELSE 0 END) AS losses FROM outcomes o WHERE o.closed_at >= :since"
                    ), {"since": since}
                )).first()
                if row:
                    delivered_total = int(row[0] or 0)
                    delivered_wins = int(row[1] or 0)
                    delivered_losses = int(row[2] or 0)
        except Exception:
            delivered_total = delivered_wins = delivered_losses = 0

        # Shadow outcomes: prefer Redis counters, but also try DB ml_rejected_signals if available
        try:
            from core.redis_state import state
            total_tracked = int(state.get_sync("shadow:counts:total_tracked") or 0)
            false_neg = int(state.get_sync("shadow:counts:false_negative") or 0)
            correct_block = int(state.get_sync("shadow:counts:correct_block") or 0)
            partial_win = int(state.get_sync("shadow:counts:partial_win") or 0)
        except Exception:
            total_tracked = false_neg = correct_block = partial_win = 0

        txt = (
            f"Weekly Filter Efficacy Report ({window_days}d)\n\n"
            f"Signals Issued (recent): {stats.get('issued', 0)}  Rejected: {stats.get('rejected_or_skipped', 0)}\n"
            f"Outcomes (recent): total={stats.get('outcomes_total',0)} wins={stats.get('wins',0)} losses={stats.get('losses',0)}\n\n"
            "Delivered vs Shadow outcomes (last period):\n"
            f"- Delivered: total={delivered_total} | wins={delivered_wins} | losses={delivered_losses}\n"
            f"- Shadow (tracked rejects): total={total_tracked} | false_negatives={false_neg} | correct_blocks={correct_block} | partial_wins={partial_win}\n\n"
        )
        # Truncate review text to keep Telegram messages reasonable; include top recommendations snippet.
        if summary:
            snippet = summary[:2000]
            txt += f"Top Recommendations:\n{snippet}\n"

        import requests

        for rid in recipients:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": int(rid), "text": txt},
                    timeout=10,
                )
            except Exception:
                logger.debug("[admin_pulse] failed to send weekly report to %s", rid, exc_info=True)

        return True
    except Exception as exc:
        logger.error("[admin_pulse] weekly send error: %s", exc, exc_info=True)
        return False


async def start_pulse_loop(interval_seconds: int = None) -> None:
    interval = int(os.getenv("ENGINE_PULSE_INTERVAL_SECONDS", "3600") or 3600) if interval_seconds is None else int(interval_seconds)
    initial_delay = int(os.getenv("ENGINE_PULSE_INITIAL_DELAY_SECONDS", "300") or 300)
    if initial_delay > 0:
        await asyncio.sleep(min(initial_delay, max(60, int(interval))))
    while True:
        try:
            await send_admin_pulse_via_telegram(window_hours=1)
        except Exception:
            logger.exception("[admin_pulse] loop send failed")
        # Weekly filter-efficacy report: run once per configured weekday/hour
        try:
            weekday = int(os.getenv("ADMIN_WEEKLY_REPORT_WEEKDAY", str(datetime.now(timezone.utc).weekday())))
            # Default weekday env not set -> use current weekday (no-op); recommend ADMIN_WEEKLY_REPORT_WEEKDAY=6 for Sunday
            report_weekday = int(os.getenv("ADMIN_WEEKLY_REPORT_WEEKDAY", "6"))
            report_hour = int(os.getenv("ADMIN_WEEKLY_REPORT_HOUR_UTC", "9"))
            now = datetime.now(timezone.utc)
            if now.weekday() == report_weekday and now.hour == report_hour:
                # Avoid duplicate runs by checking runtime_state key
                try:
                    from db.session import get_session
                    from sqlalchemy import text
                    async with get_session() as session:
                        row = (await session.execute(text("SELECT value FROM runtime_state WHERE key = :k"), {"k": "admin_pulse_last_weekly_run"})).first()
                        last = None
                        if row and row[0]:
                            last = str(row[0])
                        # If last run is today, skip
                        if last and str(now.date()) in last:
                            pass
                        else:
                            # run weekly report
                            try:
                                await send_weekly_filter_efficacy_via_telegram(window_days=7)
                            except Exception:
                                logger.exception("[admin_pulse] weekly report failed")
                            # persist last run
                            val = json.dumps(now.isoformat())
                            await session.execute(text("INSERT INTO runtime_state(key,value,expires_at,updated_at) VALUES (:k, CAST(:v AS JSONB), NULL, NOW()) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()"), {"k": "admin_pulse_last_weekly_run", "v": val})
                            await session.commit()
                except Exception:
                    logger.debug("[admin_pulse] weekly run check failed", exc_info=True)
        except Exception:
            logger.debug("[admin_pulse] weekly scheduling check error", exc_info=True)

        await asyncio.sleep(max(60, int(interval)))
