"""
engine/admin_pulse.py

Hourly admin pulse that computes engine health summary, including shadow regret
metrics, and posts to owner/admin Telegram IDs.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


async def compute_engine_health(window_hours: int = 1) -> dict[str, Any]:
    """Collect engine health stats for the last `window_hours` hours."""
    try:
        from db.session import get_session
        from sqlalchemy import text
        from core.redis_state import state

        since = datetime.utcnow() - timedelta(hours=max(1, int(window_hours or 1)))
        params = {"since": since}
        async with get_session() as session:
            # Total scanned ~ signals considered (using decision_log entries)
            scanned_row = (
                await session.execute(
                    text("SELECT COUNT(*) FROM decision_log WHERE created_at >= :since"),
                    params,
                )
            ).first()
            scanned = int(scanned_row[0] or 0) if scanned_row else 0

            # Rejected by risk / score
            rej_rows = (
                await session.execute(
                    text("SELECT decision, COUNT(*) FROM decision_log WHERE created_at >= :since GROUP BY decision"),
                    params,
                )
            ).fetchall()
            rejected_by = {str(r[0] or ""): int(r[1] or 0) for r in (rej_rows or [])}

            # Delivered
            delivered_row = (
                await session.execute(
                    text(
                        "SELECT COUNT(DISTINCT signal_id) FROM signal_deliveries WHERE created_at >= :since"
                    ),
                    params,
                )
            ).first()
            delivered = int(delivered_row[0] or 0) if delivered_row else 0

        # Shadow counters from Redis
        try:
            total_tracked = int(state.get_sync("shadow:counts:total_tracked") or 0)
            false_neg = int(state.get_sync("shadow:counts:false_negative") or 0)
            correct_block = int(state.get_sync("shadow:counts:correct_block") or 0)
            partial_win = int(state.get_sync("shadow:counts:partial_win") or 0)
        except Exception:
            total_tracked = false_neg = correct_block = partial_win = 0

        shadow_winner_rate = (false_neg / max(1, total_tracked)) * 100.0 if total_tracked > 0 else 0.0

        return {
            "scanned": scanned,
            "rejected_by": rejected_by,
            "delivered": delivered,
            "shadow": {
                "total_tracked": total_tracked,
                "false_negative": false_neg,
                "correct_block": correct_block,
                "partial_win": partial_win,
                "shadow_winner_rate_pct": shadow_winner_rate,
            },
            "generated_at": datetime.utcnow().isoformat(),
        }
    except Exception as exc:
        logger.error("[admin_pulse] compute error: %s", exc)
        return {"ok": False, "error": str(exc)}


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
            since = datetime.utcnow() - timedelta(days=max(1, int(window_days or 7)))
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
    while True:
        try:
            await send_admin_pulse_via_telegram(window_hours=1)
        except Exception:
            logger.exception("[admin_pulse] loop send failed")
        # Weekly filter-efficacy report: run once per configured weekday/hour
        try:
            weekday = int(os.getenv("ADMIN_WEEKLY_REPORT_WEEKDAY", str(datetime.utcnow().weekday())))
            # Default weekday env not set -> use current weekday (no-op); recommend ADMIN_WEEKLY_REPORT_WEEKDAY=6 for Sunday
            report_weekday = int(os.getenv("ADMIN_WEEKLY_REPORT_WEEKDAY", "6"))
            report_hour = int(os.getenv("ADMIN_WEEKLY_REPORT_HOUR_UTC", "9"))
            now = datetime.utcnow()
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
                            val = f"{now.isoformat()}"
                            await session.execute(text("INSERT INTO runtime_state(key,value,expires_at,updated_at) VALUES (:k, CAST(:v AS JSONB), NULL, NOW()) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()"), {"k": "admin_pulse_last_weekly_run", "v": val})
                            await session.commit()
                except Exception:
                    logger.debug("[admin_pulse] weekly run check failed", exc_info=True)
        except Exception:
            logger.debug("[admin_pulse] weekly scheduling check error", exc_info=True)

        await asyncio.sleep(max(60, int(interval)))
