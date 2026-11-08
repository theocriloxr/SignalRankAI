"""Tier-specific signal formatting — HTML parse_mode.

Premium  : 🚨 PREMIUM SIGNAL DETECTED
VIP      : 🚨 VIP SIGNAL DETECTED
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict as DictType, List, Optional

from core.tier_constants import TIER_SCORE_THRESHOLDS
from core.production_integrity import probability_for_public_display
from core.geometry_calculation import calculate_trade_geometry
from engine.signal_metrics import (
    resolve_confidence_ratio,
    resolve_confluence_percent,
    resolve_ml_probability,
    resolve_score_percent,
)

try:
    from engine.signal_explainability import build_signal_explanation
except Exception:  # pragma: no cover - keep formatting available in lean runtimes.
    build_signal_explanation = None


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

def _h(text: str) -> str:
    """Escape text for Telegram HTML parse_mode."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ---------------------------------------------------------------------------
# Asset friendly-name lookup
# ---------------------------------------------------------------------------

_ASSET_NAMES: DictType[str, str] = {
    # Commodities
    "XAUUSD": "Gold", "XAGUSD": "Silver",
    "WTIUSD": "WTI Oil", "WTI": "WTI Oil",
    # Crypto
    "BTCUSDT": "Bitcoin", "ETHUSDT": "Ethereum", "SOLUSDT": "Solana",
    "BNBUSDT": "BNB", "ADAUSDT": "Cardano", "XRPUSDT": "XRP",
    "DOGEUSDT": "Dogecoin", "DOTUSDT": "Polkadot",
    "POLUSDT": "Polygon", "MATICUSDT": "Polygon", "LTCUSDT": "Litecoin",
    "LINKUSDT": "Chainlink", "AVAXUSDT": "Avalanche",
    "BTCUSD": "Bitcoin", "ETHUSD": "Ethereum",
    # FX
    "EURUSD": "Euro/USD", "GBPUSD": "GBP/USD", "USDJPY": "USD/JPY",
    "AUDUSD": "AUD/USD", "USDCAD": "USD/CAD", "USDCHF": "USD/CHF",
    "NZDUSD": "NZD/USD", "EURJPY": "EUR/JPY", "GBPJPY": "GBP/JPY",
    # Stocks / Indices
    "AAPL": "Apple", "TSLA": "Tesla", "MSFT": "Microsoft",
    "SPY": "S&P 500", "QQQ": "NASDAQ",
}


def _asset_display(asset: str) -> str:
    """Return 'XAUUSD (Gold)' or just asset symbol if no friendly name."""
    name = _ASSET_NAMES.get(str(asset).upper().strip(), "")
    return f"{asset} ({name})" if name else str(asset)


def _direction_display(direction: str) -> str:
    """Return 'BUY 🟢' or 'SELL 🔴'."""
    d = str(direction or "").strip().lower()
    return "BUY 🟢" if d in ("long", "buy") else "SELL 🔴"


def _volatility_label(signal: DictType[str, Any]) -> str:
    """Derive human-readable volatility label from signal data."""
    vol = signal.get("volatility")
    if vol is not None:
        try:
            v = float(vol)
            if v < 0.005:
                return "Clear"
            if v < 0.015:
                return "Moderate"
            return "High (Use caution)"
        except Exception:
            pass
    regime = str(signal.get("regime") or "").lower()
    if any(k in regime for k in ("high_vol", "volatile", "extreme")):
        return "High"
    if any(k in regime for k in ("ranging", "range", "choppy")):
        return "Moderate"
    return "Clear"


def _order_block_text(signal: DictType[str, Any]) -> Optional[str]:
    """Return order-block description if signal is near an order block."""
    if not signal.get("is_near_order_block"):
        return None
    tf = str(signal.get("timeframe") or "H1").upper()
    d = str(signal.get("direction") or "long").lower()
    if d in ("long", "buy"):
        return f"Price bouncing off {tf} Demand Zone"
    return f"Price rejecting {tf} Supply Zone"


def _candle_price_action_lines(
    signal: DictType[str, Any],
    *,
    detailed: bool = False,
) -> List[str]:
    """Render structured candle evidence without presenting it as certainty."""
    evidence = signal.get("candle_evidence")
    if not isinstance(evidence, dict) or not evidence:
        return []

    def _label(value: Any, fallback: str = "unknown") -> str:
        return str(value or fallback).replace("_", " ").strip()

    try:
        score = max(0.0, min(100.0, float(evidence.get("evidence_score_pct") or 0.0)))
    except Exception:
        score = 0.0
    try:
        body_pct = float(evidence.get("body_ratio") or 0.0) * 100.0
        upper_pct = float(evidence.get("upper_wick_ratio") or 0.0) * 100.0
        lower_pct = float(evidence.get("lower_wick_ratio") or 0.0) * 100.0
    except Exception:
        body_pct = upper_pct = lower_pct = 0.0

    body = _label(evidence.get("body_classification"))
    close_control = _label(evidence.get("close_control"))
    rejection = _label(evidence.get("rejection"), "no dominant wick rejection")
    context = _label(evidence.get("market_context"))
    confirmation = _label(evidence.get("confirmation"), "pending")
    volume = evidence.get("relative_volume")
    volume_text = "unavailable"
    try:
        if volume is not None:
            volume_text = f"{float(volume):.2f}x baseline"
    except Exception:
        pass

    lines = [
        f"🕯️ <b>Price Action Evidence: {score:.0f}/100</b> (evidence, not proof)",
        _h(
            f"Body: {body} ({body_pct:.0f}% of range) • "
            f"Wicks: upper {upper_pct:.0f}% / lower {lower_pct:.0f}% • Rejection: {rejection}"
        ),
    ]
    if detailed:
        lines.append(
            _h(
                f"Close: {close_control} • Context: {context} • "
                f"Volume: {volume_text} • Next candle: {confirmation}"
            )
        )
    else:
        lines.append(_h(f"Close: {close_control} • Context: {context} • Confirmation: {confirmation}"))
    return lines


def _fmt_price_clean(price: Any, asset: str = "") -> str:
    """Format a price value cleanly without currency prefix."""
    try:
        p = float(price)
    except Exception:
        return str(price)
    asset_up = str(asset).upper()
    # BTC / ETH — 2 dp
    if any(c in asset_up for c in ("BTC", "ETH")):
        return f"{p:,.2f}"
    # JPY crosses — 3 dp
    if "JPY" in asset_up:
        return f"{p:.3f}"
    # Large prices (Gold >= 1000, stocks) — 2 dp
    if p >= 1_000:
        return f"{p:,.2f}"
    # FX / alts — 5 dp if < 10, else 4 dp
    if p < 10:
        return f"{p:.5f}"
    return f"{p:.4f}"


def _parse_tp_levels(tp_raw: Any) -> List[float]:
    """Parse take_profit field into list of TP prices."""
    if tp_raw is None:
        return []
    if isinstance(tp_raw, (int, float)):
        return [float(tp_raw)]
    if isinstance(tp_raw, list):
        out: List[float] = []
        for x in tp_raw:
            try:
                if isinstance(x, dict):
                    v = x.get("price") or x.get("tp") or x.get("target")
                    if v is not None:
                        out.append(float(v))
                elif x is not None:
                    out.append(float(x))
            except Exception:
                pass
        return [v for v in out if v > 0]
    try:
        s = str(tp_raw).strip()
        if s.startswith("["):
            data = json.loads(s)
            if isinstance(data, list):
                return [float(x) for x in data if x is not None]
        return [float(s)]
    except Exception:
        pass
    return []


def _build_tp_fallbacks(
    signal: DictType[str, Any],
    tp_levels: List[float],
    min_levels: int,
) -> List[float]:
    """Guarantee a minimum number of TP levels for tier presentation.

    Fallback policy:
    - If TP1 exists, extrapolate additional levels from entry using TP1 distance.
    - If TP1 missing but entry/SL exist, synthesize TP ladder from risk distance.
    - Keep direction-consistent ordering (BUY ascending, SELL descending).
    """
    if min_levels <= 0:
        return tp_levels

    # Start from valid positive values only.
    out: List[float] = []
    for v in tp_levels:
        try:
            fv = float(v)
            if fv > 0:
                out.append(fv)
        except Exception:
            continue

    if len(out) >= min_levels:
        return out

    entry = _safe_float(signal.get("entry"))
    stop_loss = _safe_float(signal.get("stop_loss"))
    direction = str(signal.get("direction") or "long").strip().lower()
    is_long = direction in ("long", "buy")
    sign = 1.0 if is_long else -1.0

    if entry is None:
        return out

    base_step: Optional[float] = None

    # If we already have TP1, use its distance from entry as the base step.
    if out:
        try:
            base_step = abs(float(out[0]) - float(entry))
        except Exception:
            base_step = None

    # Otherwise use risk distance as a proxy and start from 2R (common TP1 convention).
    if (base_step is None or base_step <= 0) and stop_loss is not None:
        risk = abs(float(entry) - float(stop_loss))
        if risk > 0:
            base_step = risk * 2.0

    if base_step is None or base_step <= 0:
        return out

    while len(out) < min_levels:
        n = len(out) + 1
        if n == 1:
            candidate = entry + (sign * base_step)
        else:
            # TP2, TP3... extend further from entry in equal base steps.
            candidate = entry + (sign * base_step * n)
        try:
            out.append(float(candidate))
        except Exception:
            break

    # Direction-consistent ordering for clean display.
    out = sorted(out, reverse=not is_long)
    return out


def _real_tp_levels(signal: DictType[str, Any], raw: Any) -> List[float]:
    """Targets the signal really carries, on the profit side of entry, in order.

    Until 6 Nov 2026 the Premium and VIP cards filled missing levels with
    ``_build_tp_fallbacks`` (2x and 3x the TP1 distance). ADX Trend signals
    carry one stored target, so cards showed a TP2 "close 25%" and a TP3
    R:R 1:10.8 that no tracker followed; the booked result (+1.79R: half at
    TP1, the rest at the protected stop) then contradicted the card.
    """
    entry = _safe_float(signal.get("entry"))
    is_long = str(signal.get("direction") or "long").strip().lower() in ("long", "buy", "bullish")
    out: List[float] = []
    for value in _parse_tp_levels(raw):
        level = _safe_float(value)
        if level is None or level <= 0:
            continue
        if entry is not None and ((is_long and level <= entry) or (not is_long and level >= entry)):
            continue
        out.append(level)
    return sorted(set(out), reverse=not is_long)


def _money_plan_lines(signal: DictType[str, Any], tp_levels: List[float]) -> List[str]:
    """Money figures for the size shown on the card (engine.signal_calculations)."""
    size = _safe_float(signal.get("suggested_position_size") or signal.get("position_size") or signal.get("lot_size"))
    if size is None or size <= 0:
        return []
    try:
        from engine.signal_calculations import calculate_money_plan

        plan = calculate_money_plan(dict(signal, take_profit=tp_levels), position_size=size)
    except Exception:
        plan = None
    if not plan:
        return []
    labels = {"stop_first": "stop", "tp1_then_entry": "TP1 then entry", "tp2_then_entry": "TP2 then entry",
              "tp3_planned_closes": "TP3 with planned closes"}
    paths = " • ".join(f"{labels.get(p['path'], p['path'])} {'+' if p['money'] >= 0 else '−'}${abs(p['money']):,.2f}"
                       for p in plan["paths"])
    full = plan["targets"][0]["profit_if_all_closed"] if plan["targets"] else None
    full_text = f" • all closed at TP1 +${full:,.2f}" if full is not None else ""
    return [
        f"💵 At the suggested size: ${plan['risk_amount']:,.2f} at risk, position value ${plan['position_value']:,.2f}",
        f"💵 Result: {paths}{full_text} (before fees and slippage)",
    ]


def _fmt_r(value: float) -> str:
    return f"{value:+.2f}R"


def _plan_math_lines(signal: DictType[str, Any], entry: Any, stop_loss: Any, tp_levels: List[float],
                     asset: Any) -> List[str]:
    """The result each path books, from the same accounting the ledger uses.

    ``core.partial_exit_accounting`` closes ``planned_exit_fractions()`` at TP1
    and TP2 and moves the stop to entry after TP1; the final target closes the
    remainder. Showing these figures keeps the card and the booked outcome
    in agreement.
    """
    try:
        from core.partial_exit_accounting import calculate_partial_exit_result, planned_exit_fractions
    except Exception:
        return []
    entry_f, stop_f = _safe_float(entry), _safe_float(stop_loss)
    if entry_f is None or stop_f is None or not tp_levels or entry_f == stop_f:
        return []
    direction = str(signal.get("direction") or "long")
    risk = abs(entry_f - stop_f)
    is_short = direction.strip().lower() in ("short", "sell", "bearish")
    rrs = [((entry_f - t) if is_short else (t - entry_f)) / risk for t in tp_levels[:3]]
    f1, f2, runner = planned_exit_fractions()
    paths = ["stop first -1.00R"]
    for stage in (1, 2):
        if len(tp_levels) < stage:
            break
        result = calculate_partial_exit_result(entry=entry_f, stop_loss=stop_f, take_profit=tp_levels,
                                               direction=direction, highest_tp=stage)
        if result is not None:
            paths.append(f"TP{stage} then stop at entry {_fmt_r(result.realized_r)}")
    if len(tp_levels) >= 3:
        # Following the plan (f1 at TP1, f2 at TP2, the runner at TP3). The
        # outcome ledger records a TP3 at the full move to TP3; both are shown
        # so the card never disagrees with /performance.
        full = f1 * rrs[0] + f2 * rrs[1] + runner * rrs[2]
        paths.append(f"TP3 {_fmt_r(full)} with the planned closes (recorded as TP3 {_fmt_r(rrs[2])})")
    lines = ["📐 Plan result: " + " • ".join(paths)]
    if len(tp_levels) < 3:
        open_share = 1.0 - f1 - (f2 if len(tp_levels) >= 2 else 0.0)
        if open_share > 0:
            lines.append(
                f"ℹ️ After TP{len(tp_levels)} the remaining {open_share:.0%} has no further target: "
                "it closes at the protected stop (entry) or the time limit."
            )
    lines.extend(_money_plan_lines(signal, tp_levels))
    current = _safe_float(signal.get("current_price") or signal.get("live_price"))
    if current is not None and current > 0 and abs(current - entry_f) / entry_f > 0.0005:
        first = tp_levels[0]
        past_target = (current <= first) if is_short else (current >= first)
        past_stop = (current >= stop_f) if is_short else (current <= stop_f)
        price_text = _fmt_price_clean(current, asset)
        if past_target or past_stop:
            lines.append(f"📍 Now {price_text}: already past the {'first target' if past_target else 'stop'}; "
                         "do not enter on this plan.")
        else:
            reward = (current - first) if is_short else (first - current)
            stop_gap = (stop_f - current) if is_short else (current - stop_f)
            if stop_gap > 0:
                lines.append(f"📍 Now {price_text}: R/R to TP1 from this price 1:{reward / stop_gap:.2f}")
                moved_r = ((entry_f - current) if is_short else (current - entry_f)) / risk
                if moved_r >= 0.25:
                    # Owner finding, 8 Nov 2026: entries "arrive late". When
                    # price has already run toward TP1, chasing it shrinks the
                    # R/R; the tracker keeps waiting for an entry touch until
                    # the signal expires, so a limit order keeps the plan.
                    lines.append(
                        f"⏳ Price is {moved_r:.2f}R past entry. To keep the planned R/R, use a limit order at "
                        f"{_fmt_price_clean(entry_f, asset)}; the signal is tracked until it expires."
                    )
    return lines


def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return None


def _compute_rr(entry: Any, stop_loss: Any, take_profit: Any, direction: Any = "long") -> Optional[float]:
    """R:R through the canonical post-geometry calculation (single source of truth)."""
    result = calculate_trade_geometry(entry, stop_loss, [take_profit], direction)
    if not result.ok or result.rr_tp1 is None:
        return None
    try:
        return float(result.rr_tp1)
    except Exception:
        return None


def _strip_embedded_rr(text: str) -> str:
    """Remove bare R:R expressions so only canonical TP-identified values remain."""
    import re

    cleaned = re.sub(r"\bR\s*:\s*R\s*[:=]?\s*[\d.]+\b", "", str(text or ""))
    return cleaned.strip(" ;,•|")


def _why_with_canonical_rr(why: str, rr_tp1: Optional[float], rr_tp_last: Optional[float], tp_count: int) -> str:
    """Append canonical, target-identified R:R to a Why explanation.

    Never a bare generic 'R:R=3.74' — the value is always tied to its target.
    """
    text = _strip_embedded_rr(why)
    if rr_tp1 is None or rr_tp_last is None or int(tp_count or 0) < 2:
        return text
    return (
        f"{text} • TP1 R:R 1:{float(rr_tp1):.2f} • TP{min(3, int(tp_count))} R:R 1:{float(rr_tp_last):.2f}"
    )


def _expected_move_pct(entry: Any, target: Any, direction: str) -> Optional[float]:
    entry_f = _safe_float(entry)
    target_f = _safe_float(target)
    if entry_f is None or target_f is None or entry_f == 0:
        return None
    if str(direction).lower() in ("short", "sell"):
        return ((entry_f - target_f) / entry_f) * 100.0
    return ((target_f - entry_f) / entry_f) * 100.0


def _signal_age_text(signal: DictType[str, Any]) -> Optional[str]:
    created_at = signal.get("created_at")
    if not created_at:
        return None
    try:
        if isinstance(created_at, str):
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        else:
            created = created_at
        if getattr(created, "tzinfo", None) is None:
            created = created.replace(tzinfo=timezone.utc)
        age_minutes = int((datetime.now(timezone.utc) - created).total_seconds() / 60)
        return f"{age_minutes}m"
    except Exception:
        return None


def _signal_generated_time(signal: DictType[str, Any]) -> Optional[str]:
    """Return signal generation time in readable format."""
    created_at = signal.get("created_at")
    if not created_at:
        return None
    try:
        if isinstance(created_at, str):
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        else:
            created = created_at
        if getattr(created, "tzinfo", None) is None:
            created = created.replace(tzinfo=timezone.utc)
        from signalrank_telegram.timezones import format_user_datetime
        return format_user_datetime(
            created,
            signal.get("display_timezone"),
            signal.get("display_telegram_user_id"),
        )
    except Exception:
        return None


def _signal_delivery_time(signal: DictType[str, Any]) -> Optional[str]:
    delivered_at = signal.get("delivered_at")
    if not delivered_at:
        return None
    try:
        if isinstance(delivered_at, str):
            delivered_at = datetime.fromisoformat(delivered_at.replace("Z", "+00:00"))
        from signalrank_telegram.timezones import format_user_datetime
        return format_user_datetime(
            delivered_at,
            signal.get("display_timezone"),
            signal.get("display_telegram_user_id"),
            include_date=False,
        )
    except Exception:
        return None


def _expiry_text(signal: DictType[str, Any]) -> Optional[str]:
    expires_at = signal.get("expires_at")
    if not expires_at:
        return None
    try:
        if isinstance(expires_at, str):
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        else:
            expiry = expires_at
        if getattr(expiry, "tzinfo", None) is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        remaining = int((expiry - datetime.now(timezone.utc)).total_seconds() / 60)
        if remaining <= 0:
            return "expired"
        if remaining >= 60:
            return f"{remaining // 60}h {remaining % 60}m"
        return f"{remaining}m"
    except Exception:
        return None


def _freshness_text(signal: DictType[str, Any]) -> str:
    age_seconds = _safe_float(signal.get("data_age_seconds"))
    if age_seconds is None:
        age_text = _signal_age_text(signal)
        return age_text or "Live"
    if age_seconds <= 60:
        return "Live"
    if age_seconds <= 300:
        return "Fresh"
    if age_seconds <= 900:
        return "Warm"
    return "Aging"


def _score_blurb(signal: DictType[str, Any]) -> str:
    score = resolve_score_percent(signal) or 0.0
    probability = probability_for_public_display(signal)
    confluence = resolve_confluence_percent(signal)
    # Plain figures only: on production the score did not predict reaching TP1
    # (AUC 0.489, 3 Nov 2026), so it is not described as conviction or strength.
    parts: List[str] = [f"engine score {score:.0f}"]
    if probability.probability is not None:
        parts.append(f"calibrated {probability.probability * 100.0:.0f}%")
    if confluence is not None:
        parts.append(f"confluence {int(confluence)}")
    return " • ".join(parts)


def _ai_review_text(signal: DictType[str, Any]) -> Optional[str]:
    """User-facing AI review summary.

    Keep internal degradation strings out of paid signal messages. The raw
    reason is still logged in engine/core.py, but users should see a clean
    explanation such as "Local AI fallback 8.7/10" instead of
    "ai_review_status=rate_limited_degraded;local_ai:...".
    """
    score = _safe_float(signal.get("ai_review_score") or signal.get("gemini_review_score"))
    raw_reason = str(signal.get("ai_review_reason") or signal.get("gemini_review_reason") or "").strip()
    provider = str(signal.get("ai_review_provider") or "").strip().lower()
    if score is None and not raw_reason:
        return None
    if raw_reason in {"gemini_disabled", "gemini_disabled_no_key"}:
        return None

    reason = raw_reason
    degraded = False
    # Strip machine-only status prefixes. Preserve the useful explanation after
    # the semicolon.
    if "ai_review_status=" in reason:
        degraded = True
        if ";" in reason:
            reason = reason.split(";", 1)[1]
        else:
            reason = ""
    local = reason.startswith("local_ai:") or degraded
    reason = reason.replace("local_ai:", "").replace("_", " ").strip(" ;,")
    if reason.lower() in {"gemini ok", "ok"}:
        reason = "quality checks passed"
    if not reason:
        reason = "quality checks passed"

    if local:
        # Not an AI opinion: the external reviewer was unavailable (production,
        # Nov 2026: OpenAI key rejected) and a local rule check scored the setup.
        label = "Rule check (AI reviewer unavailable)"
    elif provider == "openai" or raw_reason.startswith("openai_"):
        label = "OpenAI"
    elif provider == "gemini" or raw_reason.startswith("gemini_"):
        label = "Gemini"
    else:
        label = "AI review"
    parts: List[str] = []
    if score is not None and score > 0:
        parts.append(f"{label} {score:.1f}/10")
    else:
        parts.append(label)
    parts.append(reason[:90])
    return " • ".join(parts) if parts else None


def _execution_mode(signal: DictType[str, Any]) -> str:
    """Return recipient-specific execution state; intent alone never proves management."""
    mode = str(
        signal.get("delivery_execution_mode")
        or signal.get("execution_mode")
        or signal.get("trade_execution_mode")
        or "manual"
    ).strip().lower()
    state = str(signal.get("execution_state") or "").strip().lower()
    evidence = signal.get("execution_evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    reference = str(
        evidence.get("reference")
        or signal.get("broker_order_id")
        or signal.get("paper_position_id")
        or ""
    ).strip()
    destination = str(evidence.get("destination") or "").strip().lower()
    if reference and state in {"confirmed", "open", "partially_filled", "filled"}:
        return "paper_managed" if destination == "paper" else "broker_managed"
    if mode in {"auto", "automatic", "autotrade", "auto_trade", "copy", "copy_trade"}:
        return "auto_pending"
    return "manual"


def _exit_fractions() -> tuple:
    try:
        from core.partial_exit_accounting import planned_exit_fractions

        return planned_exit_fractions()
    except Exception:
        return 0.5, 0.25, 0.25


def _tp_notes_for_execution(signal: DictType[str, Any]) -> List[str]:
    mode = _execution_mode(signal)
    if mode in {"broker_managed", "paper_managed"}:
        return [
            "(Bot will auto-close 50% &amp; move SL to BE)",
            "(Bot will auto-close 25%)",
            "(Moonbag running risk-free)",
        ]
    if mode == "auto_pending":
        return [
            "(Auto-close starts only after a separate execution receipt confirms one open position)",
            "(No automated close is active until that receipt arrives)",
            "(Manual management applies if execution is not confirmed)",
        ]
    f1, f2, _runner = _exit_fractions()
    return [
        f"(Suggested close {f1:.0%} &amp; move SL to BE)",
        f"(Suggested close {f2:.0%})",
        "(Optional runner; manual execution)",
    ]


def _execution_status_line(signal: DictType[str, Any]) -> str:
    if signal.get("score_floor_advisory") and not bool(signal.get("ml_recovery_mode")):
        return (
            "Execution: PAPER ONLY — passed the setup-evidence filter below the quality-score "
            "floor, so live broker execution is disabled"
        )
    if bool(signal.get("ml_recovery_mode")):
        if str(signal.get("ml_recovery_reason") or "") == "ml_advisory_mode":
            return (
                "Execution: PAPER ONLY — passed the setup-evidence filter; the ML model "
                "is advisory, so live broker execution is disabled"
            )
        return (
            "Execution: PAPER ONLY — serving-model recovery signal; "
            "live broker execution is disabled"
        )
    mode = _execution_mode(signal)
    if mode == "broker_managed":
        return "Execution: Broker position confirmed — automated management is active for that order"
    if mode == "paper_managed":
        return "Execution: Paper position confirmed — automated virtual management is active"
    if mode == "auto_pending":
        return "Execution: Automatic entry requested — not active until a separate execution receipt"
    return "Execution: Manual — confirm trade and size yourself"

def _setup_record_line(signal: DictType[str, Any]) -> str:
    """The setup's real 60-day record, as measured: the truth, whatever the number."""
    record = signal.get("segment_evidence")
    if not isinstance(record, dict):
        return ""
    try:
        trades, wins = int(record.get("trades") or 0), int(record.get("wins") or 0)
    except (TypeError, ValueError):
        return ""
    if trades <= 0:
        return ""
    line = f"📈 Setup record (60 days): {wins:,} of {trades:,} similar setups reached TP1 ({wins / trades:.0%})."
    breakeven = record.get("breakeven")
    if isinstance(breakeven, (int, float)) and breakeven > 0:
        line += f" This plan breaks even at {breakeven:.0%}."
    return line


def _best_rr(signal: DictType[str, Any], entry: Any, stop_loss: Any, tp_levels: List[float]) -> Optional[float]:
    """Prefer actual target-derived R/R over profile minimum placeholders."""
    rr_calc = _compute_rr(entry, stop_loss, tp_levels[-1] if tp_levels else None)
    rr_signal = _safe_float(signal.get("risk_reward") or signal.get("rr_ratio") or signal.get("rr_estimate"))
    # Profile min values such as 1.2 should not override real TP3-derived RR.
    vals = [v for v in (rr_calc, rr_signal) if v is not None and v > 0]
    if not vals:
        return None
    return max(vals)


def _suggested_size_text(signal: DictType[str, Any]) -> Optional[str]:
    suggested = _safe_float(signal.get("suggested_position_size") or signal.get("position_size") or signal.get("lot_size"))
    if suggested is not None and suggested > 0:
        return f"{suggested:.2f} units (manual estimate; confirm account risk)"
    entry = _safe_float(signal.get("entry"))
    stop_loss = _safe_float(signal.get("stop_loss"))
    if entry is None or stop_loss is None:
        return None
    risk_distance = abs(entry - stop_loss)
    if risk_distance <= 0:
        return None
    equity = _safe_float(signal.get("account_balance") or signal.get("equity") or signal.get("balance"))
    risk_pct = _safe_float(
        (signal.get("risk_profile") or {}).get("risk_pct") if isinstance(signal.get("risk_profile"), dict) else signal.get("risk_pct")
    )
    if equity is None or risk_pct is None:
        return None
    risk_amount = equity * (risk_pct / 100.0)
    size = risk_amount / risk_distance
    if size <= 0:
        return None
    return f"{size:.2f} units ({risk_pct:.2f}% risk basis; manual estimate)"


# ---------------------------------------------------------------------------
# PREMIUM signal formatter
# ---------------------------------------------------------------------------

def format_premium_signal(signal: DictType[str, Any]) -> str:
    """Format signal for PREMIUM tier.

    Returns HTML string — send with parse_mode='HTML'.

    Layout:
        🚨 PREMIUM SIGNAL DETECTED 🚨
        Asset: XAUUSD (Gold)
        Direction: BUY 🟢

        📊 AI Analysis:
        🤖 Conviction Score: 89.2%
        ⚠️ Volatility: Clear

        🎯 Targets & Invalidation:
        Entry: 2024.50
        🛑 Stop Loss: 2019.00
        ✅ TP1: 2026.00
        ✅ TP2: 2028.50
        ⚖️ Risk/Reward: 1:2.5

        ⚠️ Note: Upgrade to VIP for Auto-Breakeven...
    """
    asset = signal.get("asset", "N/A")
    direction_text = _direction_display(signal.get("direction", ""))
    asset_disp = _h(_asset_display(asset))
    direction_disp = _h(direction_text)

    score_val = resolve_score_percent(signal)
    if score_val is None:
        conf_ratio = resolve_confidence_ratio(signal)
        score_val = conf_ratio * 100.0 if conf_ratio is not None else 0.0

    volatility = _h(_volatility_label(signal))
    entry = signal.get("entry")
    sl = signal.get("stop_loss")
    # Only the targets the signal really carries: these are the levels the
    # lifecycle tracker follows and the ledger books (see _plan_math_lines).
    tp_levels = _real_tp_levels(signal, signal.get("take_profit") or signal.get("tp_levels"))
    rr_calc = _compute_rr(entry, sl, tp_levels[-1] if tp_levels else None)
    expected_profit = _expected_move_pct(entry, tp_levels[-1] if tp_levels else None, signal.get("direction", "long"))
    expected_loss = _expected_move_pct(entry, sl, "short" if str(signal.get("direction", "long")).lower() in ("long", "buy") else "long")
    freshness = _freshness_text(signal)
    age_text = _signal_age_text(signal)
    expiry_text = _expiry_text(signal)
    suggested_size = _suggested_size_text(signal)
    generated_time = _signal_generated_time(signal)
    delivered_time = _signal_delivery_time(signal)

    lines = [
        "🚨 <b>PREMIUM SIGNAL DETECTED</b> 🚨",
        f"Asset: <b>{asset_disp}</b>",
        f"Direction: <b>{direction_disp}</b>",
    ]

    if generated_time:
        lines.append(f"🕐 Generated: {_h(generated_time)}")
    if delivered_time:
        lines.append(f"📡 Delivered: {_h(delivered_time)}")

    lines += [
        "",
        "📊 <b>AI Analysis:</b>",
        f"🤖 Engine score: {score_val:.1f}/100 (ranks setups; not a chance of winning)",
        f"⚠️ Volatility: {volatility}",
    ]

    # Public probability language is allowed only for a persisted calibration curve.
    probability = probability_for_public_display(signal)
    if probability.probability is not None:
        lines.append(f"🧠 {probability.label}: {probability.probability * 100.0:.1f}%")
    else:
        raw_model_score = resolve_ml_probability(signal)
        if raw_model_score is not None:
            lines.append(f"🧠 Model Score (uncalibrated): {raw_model_score * 100.0:.1f}/100")
    ai_review = _ai_review_text(signal)
    if ai_review:
        lines.append(f"🧠 AI Review: {_h(ai_review)}")
    lines.extend(_candle_price_action_lines(signal))

    lines += [
        "",
        "🎯 <b>Targets &amp; Invalidation:</b>",
    ]

    if entry is not None:
        lines.append(f"Entry: {_h(_fmt_price_clean(entry, asset))}")
    if sl is not None:
        lines.append(f"🛑 Stop Loss: {_h(_fmt_price_clean(sl, asset))}")

    if len(tp_levels) >= 2:
        lines.append(f"✅ TP1: {_h(_fmt_price_clean(tp_levels[0], asset))}")
        lines.append(f"✅ TP2: {_h(_fmt_price_clean(tp_levels[1], asset))}")
    elif len(tp_levels) == 1:
        lines.append(f"✅ TP: {_h(_fmt_price_clean(tp_levels[0], asset))}")

    # R/R ratio — canonical TP-identified values from the rendered ladder,
    # never a bare generic ratio.
    rr_tp1 = _compute_rr(entry, sl, tp_levels[0] if tp_levels else None, signal.get("direction", "long"))
    rr_tp_last = _compute_rr(entry, sl, tp_levels[-1] if tp_levels else None, signal.get("direction", "long"))
    if rr_tp1 is not None and rr_tp_last is not None and len(tp_levels) > 1:
        lines.append(
            f"⚖️ R/R: TP1 1:{float(rr_tp1):.1f} • TP{min(3, len(tp_levels))} 1:{float(rr_tp_last):.1f}"
        )
    elif rr_tp1 is not None:
        lines.append(f"⚖️ Risk/Reward: 1:{float(rr_tp1):.1f}")

    if expected_profit is not None:
        lines.append(f"💰 Move to final target: +{expected_profit:.2f}%")
    if expected_loss is not None:
        loss_display = -abs(expected_loss)
        lines.append(f"🛡️ Move to stop: {loss_display:.2f}%")
    lines.extend(_h(line) for line in _plan_math_lines(signal, entry, sl, tp_levels, asset))

    strategy = signal.get("strategy_name") or signal.get("strategy")
    regime = signal.get("regime") or signal.get("market_regime")
    if strategy:
        lines.append(f"🧭 Strategy: {_h(str(strategy))}")
    if regime:
        lines.append(f"🌍 Regime: {_h(str(regime))}")
    if suggested_size:
        lines.append(f"📦 Suggested Size: {_h(suggested_size)}")
    if _setup_record_line(signal):
        lines.append(_h(_setup_record_line(signal)))
    lines.append(_execution_status_line(signal))
    lines.append(f"🧾 Score Read: {_h(_score_blurb(signal))}")
    lines.append(f"🕒 Freshness: {_h(freshness)}")
    if age_text:
        lines.append(f"⏳ Age: {_h(age_text)}")
    if expiry_text:
        lines.append(f"⌛ Expires: {_h(expiry_text)}")

    # Session / timeframe / signal ref
    session = signal.get("session") or signal.get("market_session", "")
    if session:
        lines.append(f"⏱️ Session: {_h(str(session))}")
    tf = signal.get("timeframe")
    if tf:
        lines.append(f"📐 Timeframe: {_h(str(tf))}")
    sig_id = signal.get("signal_id") or signal.get("id")
    if sig_id:
        lines.append(f"📌 Ref: {str(sig_id)[:8]}")

    lines += [
        "",
        "<i>VIP adds the TP3 management ladder and execution preflight. "
        "Every tier still requires the same freshness, risk, consent, and kill-switch checks. "
        "No outcome is guaranteed. /upgrade</i>",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# VIP signal formatter
# ---------------------------------------------------------------------------

def format_vip_signal(signal: DictType[str, Any]) -> str:
    """Format signal for VIP / Admin / Owner tier.

    Returns HTML string — send with parse_mode='HTML'.

    Layout:
        🚨 VIP SIGNAL DETECTED 🚨
        Asset: XAUUSD (Gold)
        Direction: BUY 🟢

        📊 AI Analysis:
        🤖 Conviction Score: 89.2%
        🧱 Order Block: Price bouncing off H1 Demand Zone
        ⚠️ Volatility: Clear — trending_bullish
        🧠 ML Probability: 78.4%
        📈 HTF Bias: bullish

        🎯 Targets & Invalidation:
        Entry: 2024.50
        🛑 Stop Loss: 2019.00
        ✅ TP1: 2026.00 (Bot will auto-close 50% & move SL to BE)
        ✅ TP2: 2028.50 (Bot will auto-close 25%)
        ✅ TP3: 2032.00 (Moonbag running risk-free)
        ⚖️ Risk/Reward: 1:3.0
    """
    asset = signal.get("asset", "N/A")
    direction_text = _direction_display(signal.get("direction", ""))
    asset_disp = _h(_asset_display(asset))
    direction_disp = _h(direction_text)

    score_val = resolve_score_percent(signal)
    if score_val is None:
        conf_ratio = resolve_confidence_ratio(signal)
        score_val = conf_ratio * 100.0 if conf_ratio is not None else 0.0

    volatility = _volatility_label(signal)
    order_block = _order_block_text(signal)

    entry = signal.get("entry")
    sl = signal.get("stop_loss")
    tp_levels = _real_tp_levels(signal, signal.get("tp_levels") or signal.get("take_profit"))
    rr_calc = _compute_rr(entry, sl, tp_levels[-1] if tp_levels else None)
    expected_profit = _expected_move_pct(entry, tp_levels[-1] if tp_levels else None, signal.get("direction", "long"))
    expected_loss = _expected_move_pct(entry, sl, "short" if str(signal.get("direction", "long")).lower() in ("long", "buy") else "long")
    freshness = _freshness_text(signal)
    age_text = _signal_age_text(signal)
    expiry_text = _expiry_text(signal)
    suggested_size = _suggested_size_text(signal)
    generated_time = _signal_generated_time(signal)
    delivered_time = _signal_delivery_time(signal)

    # R/R — use actual target-derived RR, not merely profile minimum.
    # Compute from the exact TP ladder rendered in this message so the display
    # is always internally consistent (canonical post-geometry calculation).
    rr = _best_rr(signal, entry, sl, tp_levels)
    rr_tp1 = _compute_rr(entry, sl, tp_levels[0] if tp_levels else None, signal.get("direction", "long"))
    rr_tp_last = _compute_rr(entry, sl, tp_levels[-1] if tp_levels else None, signal.get("direction", "long"))

    lines = [
        "🚨 <b>VIP SIGNAL DETECTED</b> 🚨",
        f"Asset: <b>{asset_disp}</b>",
        f"Direction: <b>{direction_disp}</b>",
    ]

    if generated_time:
        lines.append(f"🕐 Generated: {_h(generated_time)}")
    if delivered_time:
        lines.append(f"📡 Delivered: {_h(delivered_time)}")

    lines += [
        "",
        "📊 <b>AI Analysis:</b>",
        f"🤖 Engine score: {score_val:.1f}/100 (ranks setups; not a chance of winning)",
    ]

    # Order Block — VIP exclusive
    if order_block:
        lines.append(f"🧱 Order Block: {_h(order_block)}")
    else:
        tl = (
            signal.get("trade_logic")
            or signal.get("technical_reason")
            or signal.get("setup_rationale")
        )
        if tl:
            # Never leak a bare generic R:R into the Setup line either.
            lines.append(f"🧱 Setup: {_h(_strip_embedded_rr(str(tl)[:100]))}")

    # Volatility with regime context
    regime = signal.get("regime") or signal.get("market_regime", "")
    vol_line = f"⚠️ Volatility: {_h(volatility)}"
    if regime and str(regime).strip():
        vol_line += f" — {_h(str(regime))}"
    lines.append(vol_line)

    # Public probability language is allowed only for a persisted calibration curve.
    probability = probability_for_public_display(signal)
    if probability.probability is not None:
        lines.append(f"🧠 {probability.label}: {probability.probability * 100.0:.1f}%")
    else:
        raw_model_score = resolve_ml_probability(signal)
        if raw_model_score is not None:
            lines.append(f"🧠 Model Score (uncalibrated): {raw_model_score * 100.0:.1f}/100")
    ai_review = _ai_review_text(signal)
    if ai_review:
        lines.append(f"🧠 AI Review: {_h(ai_review)}")
    lines.extend(_candle_price_action_lines(signal, detailed=True))

    # HTF Bias
    htf_bias = signal.get("htf_bias") or signal.get("higher_timeframe_bias")
    if htf_bias:
        if isinstance(htf_bias, dict):
            htf_val = htf_bias.get("bias") or htf_bias.get("direction") or ""
        else:
            htf_val = str(htf_bias)
        if htf_val:
            lines.append(f"📈 HTF Bias: {_h(htf_val)}")

    # Confluence
    confluence = resolve_confluence_percent(signal)
    if confluence is not None:
        lines.append(f"📊 Confluence: {int(confluence)}%")

    explanation = {}
    if build_signal_explanation is not None:
        try:
            explanation = build_signal_explanation(signal)
        except Exception:
            explanation = {}
    why = (
        explanation.get("summary")
        or signal.get("technical_reason")
        or signal.get("trade_logic")
        or signal.get("setup_rationale")
    )
    if not why:
        strategy = str(signal.get("strategy") or signal.get("strategy_name") or "multi-factor setup")
        direction_text = str(signal.get("direction") or "trade").upper()
        timeframe_text = str(signal.get("timeframe") or "current timeframe")
        regime_text = str(signal.get("market_regime") or signal.get("regime") or "current market regime")
        why = (
            f"{strategy} supports this {direction_text} setup on {timeframe_text}; "
            f"risk and confluence checks passed for the {regime_text} regime."
        )
    lines.append(f"Why: {_h(_why_with_canonical_rr(str(why)[:180], rr_tp1, rr_tp_last, len(tp_levels)))}")

    lines += [
        "",
        "🎯 <b>Targets &amp; Invalidation:</b>",
    ]

    if entry is not None:
        lines.append(f"Entry: {_h(_fmt_price_clean(entry, asset))}")
    if sl is not None:
        lines.append(f"🛑 Stop Loss: {_h(_fmt_price_clean(sl, asset))}")

    # TPs with profile-aware execution annotations
    _tp_notes = _tp_notes_for_execution(signal)
    if tp_levels:
        for i, tp in enumerate(tp_levels[:3]):
            note = _tp_notes[i] if i < len(_tp_notes) else ""
            line = f"✅ TP{i + 1}: {_h(_fmt_price_clean(tp, asset))}"
            if note:
                line += f" {note}"
            lines.append(line)

    if rr_tp1 is not None and rr_tp_last is not None and len(tp_levels) > 1:
        lines.append(
            f"⚖️ R/R: TP1 1:{float(rr_tp1):.1f} • TP{min(3, len(tp_levels))} 1:{float(rr_tp_last):.1f}"
        )
    elif rr_tp1 is not None:
        lines.append(f"⚖️ Risk/Reward: 1:{float(rr_tp1):.1f}")
    elif rr:
        try:
            rr_val = float(rr)
            if rr_val > 0:
                lines.append(f"⚖️ Risk/Reward: 1:{rr_val:.1f}")
        except Exception:
            pass
    elif rr_calc is not None:
        lines.append(f"⚖️ Risk/Reward: 1:{rr_calc:.1f}")

    if expected_profit is not None:
        lines.append(f"💰 Move to final target: +{expected_profit:.2f}%")
    if expected_loss is not None:
        loss_display = -abs(expected_loss)
        lines.append(f"🛡️ Move to stop: {loss_display:.2f}%")
    lines.extend(_h(line) for line in _plan_math_lines(signal, entry, sl, tp_levels, asset))

    # Invalidation level
    invalidation = signal.get("invalidation") or signal.get("invalidation_level")
    if invalidation:
        if isinstance(invalidation, list):
            inv_str = " | ".join(str(x) for x in invalidation[:2])
        else:
            inv_str = str(invalidation)
        lines.append(f"❌ Invalidation: {_h(inv_str[:80])}")

    # Session / timeframe / signal ref
    session = signal.get("session") or signal.get("market_session", "")
    if session:
        lines.append(f"⏱️ Session: {_h(str(session))}")
    strategy = signal.get("strategy_name") or signal.get("strategy")
    if strategy:
        lines.append(f"🧭 Strategy: {_h(str(strategy))}")
    if suggested_size:
        lines.append(f"📦 Suggested Size: {_h(suggested_size)}")
    if _setup_record_line(signal):
        lines.append(_h(_setup_record_line(signal)))
    lines.append(_execution_status_line(signal))
    lines.append(f"🧾 Score Read: {_h(_score_blurb(signal))}")
    lines.append(f"🕒 Freshness: {_h(freshness)}")
    if age_text:
        lines.append(f"⏳ Age: {_h(age_text)}")
    if expiry_text:
        lines.append(f"⌛ Expires: {_h(expiry_text)}")
    tf = signal.get("timeframe")
    if tf:
        lines.append(f"📐 Timeframe: {_h(str(tf))}")
    sig_id = signal.get("signal_id") or signal.get("id")
    if sig_id:
        lines.append(f"📌 Signal ID: {str(sig_id)[:12]}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# TP-hit update formatters
# ---------------------------------------------------------------------------

def format_premium_tp_update(tp_level: int, asset: str, confidence: str = "HIGH") -> str:
    """Format PREMIUM tier TP hit update."""
    emoji_map = {1: "✅", 2: "✅", 3: "✅"}
    emoji = emoji_map.get(tp_level, "✅")
    lines = [
        f"📢 UPDATE — {asset}",
        "",
        f"{emoji} TP{tp_level} HIT",
        "🔒 Consider moving SL to breakeven",
    ]
    return "\n".join(lines)


def format_vip_tp_update(
    tp_level: int,
    asset: str,
    direction: str = "long",
    entry: Optional[float] = None,
    tp_price: Optional[float] = None,
    remaining_tps: Optional[List[float]] = None,
) -> str:
    """Format VIP tier TP hit update."""
    emoji_map = {1: "🟢", 2: "🟡", 3: "🔴"}
    emoji = emoji_map.get(tp_level, "✅")
    lines = [
        f"📣 Outcome Update — {emoji} TP{tp_level} HIT",
        "",
        f"{asset}",
    ]
    if entry and tp_price:
        if direction.lower() == "long":
            profit_pct = ((tp_price - entry) / entry) * 100.0
        else:
            profit_pct = ((entry - tp_price) / entry) * 100.0
        lines.append(f"✅ Profit: +{profit_pct:.2f}%")
    lines.append("")
    if tp_level == 1:
        lines.extend([
            "💡 Partial TP1 hit — Consider:",
            "  • Move SL to breakeven",
            "  • Trail remaining position",
            "  • Target TP2 for more gains",
        ])
    elif tp_level == 2:
        lines.extend([
            "💡 Partial TP2 hit — Consider:",
            "  • Lock in more profits",
            "  • Exit 50% of position",
            "  • Trail the rest to TP3",
        ])
    elif tp_level == 3:
        lines.extend([
            "💡 TP3 hit — Consider:",
            "  • Exit remaining position",
            "  • Manage trailing stop",
            "  • Lock in full profit",
        ])
    if remaining_tps:
        lines.append("")
        lines.append(
            "📊 Remaining TPs: "
            + " | ".join(
                f"TP{i} {tp:,.2f}" for i, tp in enumerate(remaining_tps, tp_level + 1)
            )
        )
    lines.append("")
    lines.append("This signal has been marked with an outcome in the tracker.")
    return "\n".join(lines)


def format_vip_no_trade_alert(conditions: DictType[str, Any]) -> str:
    """Format VIP NO-TRADE zone alert."""
    lines = [
        "🔵 VIP — NO-TRADE ALERT",
        "⛔ NO TRADE ZONE — VIP",
        "",
        "Market Conditions:",
    ]
    if conditions.get("low_volume"):
        lines.append("• Low volume")
    if conditions.get("choppy"):
        lines.append("• Choppy structure")
    if conditions.get("poor_rr"):
        lines.append("• Poor risk-to-reward")
    if conditions.get("high_volatility"):
        lines.append("• Extreme volatility")
    lines.extend(["", "📉 Capital preservation mode active"])
    return "\n".join(lines)
