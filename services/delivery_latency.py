"""Where signal delivery time goes (owner finding, 8 Nov 2026: "entries arrive late").

For each confirmed Telegram delivery in a window, three stages:

- **engine**: the bar's close -> the signal stored (``signals.created_at``). The
  bar close is the start of the signal's timeframe bar containing
  ``created_at``; the time since then is how long the engine took to act on
  the bar.
- **queue**: stored -> Telegram send started (``telegram_send_started_at``).
- **send**: send started -> delivery confirmed (``delivery_confirmed_at``).

Reported as median and 90th percentile per asset class and timeframe, with the
share of deliveries that arrived after a quarter of the signal's bar had gone
(``late_share``). Read only.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

TIMEFRAME_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400,
                     "24h": 86400}

LATENCY_SQL = """
WITH d AS (
    SELECT lower(COALESCE(s.asset_class, 'unknown')) AS asset_class,
           lower(COALESCE(s.timeframe, '?')) AS timeframe,
           EXTRACT(EPOCH FROM s.created_at)
             - floor(EXTRACT(EPOCH FROM s.created_at) / :tfsec_expr) * :tfsec_expr AS engine_s,
           EXTRACT(EPOCH FROM (COALESCE(d.telegram_send_started_at, d.delivery_confirmed_at) - s.created_at)) AS queue_s,
           EXTRACT(EPOCH FROM (d.delivery_confirmed_at - COALESCE(d.telegram_send_started_at, d.delivery_confirmed_at))) AS send_s,
           EXTRACT(EPOCH FROM (d.delivery_confirmed_at - s.created_at)) AS total_s,
           CASE lower(COALESCE(s.timeframe, ''))
               WHEN '1m' THEN 60 WHEN '5m' THEN 300 WHEN '15m' THEN 900 WHEN '30m' THEN 1800
               WHEN '1h' THEN 3600 WHEN '4h' THEN 14400 WHEN '1d' THEN 86400 WHEN '24h' THEN 86400
               ELSE 3600 END AS bar_s
    FROM signal_deliveries d JOIN signals s ON s.signal_id = d.signal_id
    WHERE d.sent_ok IS TRUE AND d.delivery_confirmed_at IS NOT NULL AND d.delivery_confirmed_at >= :since
)
SELECT asset_class, timeframe, COUNT(*),
       percentile_cont(0.5) WITHIN GROUP (ORDER BY engine_s), percentile_cont(0.9) WITHIN GROUP (ORDER BY engine_s),
       percentile_cont(0.5) WITHIN GROUP (ORDER BY queue_s), percentile_cont(0.9) WITHIN GROUP (ORDER BY queue_s),
       percentile_cont(0.5) WITHIN GROUP (ORDER BY send_s), percentile_cont(0.9) WITHIN GROUP (ORDER BY send_s),
       percentile_cont(0.5) WITHIN GROUP (ORDER BY total_s), percentile_cont(0.9) WITHIN GROUP (ORDER BY total_s),
       AVG(CASE WHEN engine_s + total_s > 0.25 * bar_s THEN 1.0 ELSE 0.0 END)
FROM d GROUP BY asset_class, timeframe ORDER BY COUNT(*) DESC
"""

_TF_CASE = ("(CASE lower(COALESCE(s.timeframe, '')) WHEN '1m' THEN 60 WHEN '5m' THEN 300 WHEN '15m' THEN 900 "
            "WHEN '30m' THEN 1800 WHEN '1h' THEN 3600 WHEN '4h' THEN 14400 WHEN '1d' THEN 86400 "
            "WHEN '24h' THEN 86400 ELSE 3600 END)")


def _r(value: Any) -> float | None:
    return None if value is None else round(float(value), 1)


async def delivery_latency_report(session, *, hours: int = 24) -> dict[str, Any]:
    from sqlalchemy import text

    since = (datetime.now(timezone.utc) - timedelta(hours=max(1, int(hours)))).replace(tzinfo=None)
    rows = (await session.execute(text(LATENCY_SQL.replace(":tfsec_expr", _TF_CASE)), {"since": since})).all()
    groups = []
    for r in rows:
        groups.append({
            "asset_class": r[0], "timeframe": r[1], "deliveries": int(r[2]),
            "engine_p50_s": _r(r[3]), "engine_p90_s": _r(r[4]),
            "queue_p50_s": _r(r[5]), "queue_p90_s": _r(r[6]),
            "send_p50_s": _r(r[7]), "send_p90_s": _r(r[8]),
            "total_p50_s": _r(r[9]), "total_p90_s": _r(r[10]),
            "late_share": None if r[11] is None else round(float(r[11]), 3),
        })
    return {"window_hours": int(hours), "groups": groups,
            "deliveries": sum(g["deliveries"] for g in groups)}


def _fmt_s(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value / 60:.1f}m" if value >= 120 else f"{value:.0f}s"


def format_latency_lines(report: dict[str, Any], *, limit: int = 8) -> list[str]:
    groups = report.get("groups") or []
    if not groups:
        return [f"No confirmed deliveries in the last {report.get('window_hours')}h."]
    lines = [f"Delivery latency, last {report.get('window_hours')}h ({report.get('deliveries')} deliveries)",
             "class tf: bar close→stored | stored→send | send→confirmed (p50/p90) | late"]
    for g in groups[:limit]:
        late = "—" if g["late_share"] is None else f"{g['late_share']:.0%}"
        lines.append(
            f"{g['asset_class']} {g['timeframe']} ×{g['deliveries']}: "
            f"{_fmt_s(g['engine_p50_s'])}/{_fmt_s(g['engine_p90_s'])} | "
            f"{_fmt_s(g['queue_p50_s'])}/{_fmt_s(g['queue_p90_s'])} | "
            f"{_fmt_s(g['send_p50_s'])}/{_fmt_s(g['send_p90_s'])} | {late}"
        )
    return lines
