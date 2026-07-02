from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class MissionSnapshot:
    signal_id: str
    asset: str
    status: str
    health_score: float
    progress_to_tp1_pct: float
    live_pl_pct: float
    probability_tp_today: float
    probability_recovery: float
    recommendation: str
    recommendation_reason: str
    risk_state: str


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def parse_tp_levels(raw: Any) -> list[float]:
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        try:
            raw = json.loads(text)
        except Exception:
            raw = [x.strip() for x in text.strip("[]").replace("'", "").replace('"', "").split(",") if x.strip()]
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        raw = [raw]
    out: list[float] = []
    for item in raw:
        if isinstance(item, dict):
            item = item.get("price") or item.get("tp") or item.get("target") or item.get("value")
        value = _f(item, 0.0)
        if value > 0:
            out.append(value)
    return out


def build_mission_snapshot(signal: dict[str, Any], current_price: float | None = None, now: datetime | None = None) -> MissionSnapshot:
    sig = dict(signal or {})
    entry = _f(sig.get("entry"))
    stop = _f(sig.get("stop_loss") or sig.get("stop"))
    price = _f(current_price if current_price is not None else sig.get("current_price") or sig.get("live_price") or entry)
    direction = str(sig.get("direction") or "long").lower()
    is_short = direction in {"short", "sell"}
    tp_levels = parse_tp_levels(sig.get("take_profit") or sig.get("targets") or sig.get("tp_levels"))
    tp1 = tp_levels[0] if tp_levels else 0.0
    if entry > 0 and price > 0:
        live_pl = ((entry - price) / entry * 100.0) if is_short else ((price - entry) / entry * 100.0)
    else:
        live_pl = 0.0
    if entry > 0 and tp1:
        numerator = (entry - price) if is_short else (price - entry)
        denominator = abs(entry - tp1)
        progress = max(0.0, min(100.0, numerator / max(denominator, 1e-9) * 100.0))
    else:
        progress = 0.0
    planned_risk = abs(entry - stop) / max(entry, 1e-9) * 100.0 if entry and stop else 1.0
    drawdown_ratio = abs(min(live_pl, 0.0)) / max(planned_risk, 0.1)
    base_score = _f(sig.get("opportunity_score") or sig.get("score") or 60.0)
    mtf = _f(sig.get("mtf_alignment_score"), 55.0)
    market_health = _f(sig.get("asset_health_score"), 60.0)
    time_score = _f(sig.get("time_to_target_score"), 60.0)
    health = max(0.0, min(100.0, base_score * 0.35 + mtf * 0.20 + market_health * 0.20 + time_score * 0.15 + max(0.0, 100.0 - drawdown_ratio * 40.0) * 0.10))
    tp_today = _probability_tp_today(sig, progress, health)
    recovery = max(0.0, min(100.0, health - drawdown_ratio * 28.0 + (15.0 if progress > 25 else 0.0)))
    if health < 40 or recovery < 25:
        rec = "Close or reduce"
        reason = "Trade health and recovery probability are weak."
    elif health < 58:
        rec = "Tighten stop"
        reason = "Trade quality has deteriorated; protect capital."
    elif progress >= 50:
        rec = "Hold, consider moving SL to breakeven"
        reason = "Trade is progressing toward TP1."
    else:
        rec = "Hold"
        reason = "Setup remains valid."
    risk_state = "high" if drawdown_ratio >= 0.75 else "normal" if drawdown_ratio < 0.35 else "watch"
    return MissionSnapshot(
        signal_id=str(sig.get("signal_id") or sig.get("id") or ""),
        asset=str(sig.get("asset") or sig.get("symbol") or ""),
        status=str(sig.get("status") or "active").upper(),
        health_score=round(health, 1),
        progress_to_tp1_pct=round(progress, 1),
        live_pl_pct=round(live_pl, 2),
        probability_tp_today=round(tp_today, 1),
        probability_recovery=round(recovery, 1),
        recommendation=rec,
        recommendation_reason=reason,
        risk_state=risk_state,
    )


def _probability_tp_today(signal: dict[str, Any], progress: float, health: float) -> float:
    ttt = signal.get("time_to_target")
    if isinstance(ttt, dict):
        probs = ttt.get("probabilities") or {}
        for key in ("tp1_24h", "tp1_12h", "tp1_4h"):
            if key in probs:
                return max(0.0, min(99.0, float(probs[key]) * 100.0))
    return max(0.0, min(99.0, health * 0.65 + progress * 0.35))


def format_mission(snapshot: MissionSnapshot) -> str:
    return "\n".join(
        [
            f"Signal Mission Control - {snapshot.asset}",
            "",
            f"Status: {snapshot.status}",
            f"Health: {snapshot.health_score:.1f}%",
            f"Progress to TP1: {snapshot.progress_to_tp1_pct:.1f}%",
            f"Live P/L: {snapshot.live_pl_pct:+.2f}%",
            f"Probability TP today: {snapshot.probability_tp_today:.1f}%",
            f"Probability of recovery: {snapshot.probability_recovery:.1f}%",
            f"Risk state: {snapshot.risk_state}",
            "",
            f"AI recommendation: {snapshot.recommendation}",
            snapshot.recommendation_reason,
            "",
            f"Signal ID: {snapshot.signal_id}",
        ]
    )
