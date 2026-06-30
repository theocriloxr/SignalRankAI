"""Tier-specific signal formatting — HTML parse_mode.

Premium  : 🚨 PREMIUM SIGNAL DETECTED
VIP      : 🚨 VIP SIGNAL DETECTED
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict as DictType, List, Optional

from core.tier_constants import TIER_SCORE_THRESHOLDS
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


def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return None


def _compute_rr(entry: Any, stop_loss: Any, take_profit: Any) -> Optional[float]:
    entry_f = _safe_float(entry)
    stop_f = _safe_float(stop_loss)
    tp_f = _safe_float(take_profit)
    if entry_f is None or stop_f is None or tp_f is None:
        return None
    risk = abs(entry_f - stop_f)
    if risk <= 0:
        return None
    return abs(tp_f - entry_f) / risk


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
        # Return in format: "2024-05-03 14:30 UTC"
        return created.strftime("%Y-%m-%d %H:%M UTC")
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
    ml_prob = resolve_ml_probability(signal)
    confluence = resolve_confluence_percent(signal)
    parts: List[str] = []
    strong_threshold = max(
        float(TIER_SCORE_THRESHOLDS.get("vip", 75.0) or 75.0),
        float(TIER_SCORE_THRESHOLDS.get("premium", 70.0) or 70.0),
    )
    mid_threshold = float(TIER_SCORE_THRESHOLDS.get("premium", 70.0) or 70.0)
    if score >= strong_threshold:
        parts.append("high-conviction")
    elif score >= mid_threshold:
        parts.append("strong setup")
    else:
        parts.append("qualified setup")
    if ml_prob is not None:
        parts.append(f"ML {ml_prob * 100.0:.0f}%")
    if confluence is not None:
        parts.append(f"confluence {int(confluence)}")
    return " • ".join(parts)


def _ai_review_text(signal: DictType[str, Any]) -> Optional[str]:
    score = _safe_float(signal.get("gemini_review_score") or signal.get("ai_review_score"))
    reason = str(signal.get("gemini_review_reason") or signal.get("ai_review_reason") or "").strip()
    if score is None and not reason:
        return None
    if reason in {"gemini_disabled", "gemini_disabled_no_key"}:
        return None
    parts: List[str] = []
    if score is not None and score > 0:
        parts.append(f"Gemini {score:.1f}/10")
    if reason:
        readable = reason.replace("_", " ")
        if readable.lower() != "gemini ok":
            parts.append(readable[:80])
    return " • ".join(parts) if parts else None


def _suggested_size_text(signal: DictType[str, Any]) -> Optional[str]:
    suggested = _safe_float(signal.get("suggested_position_size") or signal.get("position_size") or signal.get("lot_size"))
    if suggested is not None and suggested > 0:
        return f"{suggested:.2f} units"
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
    return f"{size:.2f} units ({risk_pct:.2f}% risk)"


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
    tp_levels = _parse_tp_levels(signal.get("take_profit") or signal.get("tp_levels"))
    tp_levels = _build_tp_fallbacks(signal, tp_levels, min_levels=2)
    rr_calc = _compute_rr(entry, sl, tp_levels[-1] if tp_levels else None)
    expected_profit = _expected_move_pct(entry, tp_levels[-1] if tp_levels else None, signal.get("direction", "long"))
    expected_loss = _expected_move_pct(entry, sl, "short" if str(signal.get("direction", "long")).lower() in ("long", "buy") else "long")
    freshness = _freshness_text(signal)
    age_text = _signal_age_text(signal)
    expiry_text = _expiry_text(signal)
    suggested_size = _suggested_size_text(signal)
    generated_time = _signal_generated_time(signal)

    lines = [
        "🚨 <b>PREMIUM SIGNAL DETECTED</b> 🚨",
        f"Asset: <b>{asset_disp}</b>",
        f"Direction: <b>{direction_disp}</b>",
    ]

    if generated_time:
        lines.append(f"🕐 Generated: {_h(generated_time)}")

    lines += [
        "",
        "📊 <b>AI Analysis:</b>",
        f"🤖 Conviction Score: {score_val:.1f}%",
        f"⚠️ Volatility: {volatility}",
    ]

    # Optional: ML probability
    ml_prob = resolve_ml_probability(signal)
    if ml_prob is not None:
        lines.append(f"🧠 ML Probability: {ml_prob * 100.0:.1f}%")
    ai_review = _ai_review_text(signal)
    if ai_review:
        lines.append(f"🧠 AI Review: {_h(ai_review)}")

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

    # R/R ratio
    rr = signal.get("risk_reward") or signal.get("rr_ratio") or signal.get("rr_estimate")
    if not rr and entry and sl and tp_levels:
        try:
            _e, _s, _t = float(entry), float(sl), float(tp_levels[-1])
            rr = abs(_t - _e) / max(1e-9, abs(_e - _s))
        except Exception:
            pass
    if rr:
        try:
            rr_val = float(rr)
            if rr_val > 0:
                lines.append(f"⚖️ Risk/Reward: 1:{rr_val:.1f}")
        except Exception:
            pass
    elif rr_calc is not None:
        lines.append(f"⚖️ Risk/Reward: 1:{rr_calc:.1f}")

    if expected_profit is not None:
        lines.append(f"💰 Expected Profit: +{expected_profit:.2f}%")
    if expected_loss is not None:
        loss_display = -abs(expected_loss)
        lines.append(f"🛡️ Expected Loss: {loss_display:.2f}%")

    strategy = signal.get("strategy_name") or signal.get("strategy")
    regime = signal.get("regime") or signal.get("market_regime")
    if strategy:
        lines.append(f"🧭 Strategy: {_h(str(strategy))}")
    if regime:
        lines.append(f"🌍 Regime: {_h(str(regime))}")
    if suggested_size:
        lines.append(f"📦 Suggested Size: {_h(suggested_size)}")
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
        "<i>⚠️ Note: This trade will run naked. Upgrade to VIP to unlock "
        "Auto-Breakeven, Partial Profit Taking, and Smart Risk Sizing! /upgrade</i>",
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
    tp_levels = _parse_tp_levels(signal.get("tp_levels") or signal.get("take_profit"))
    tp_levels = _build_tp_fallbacks(signal, tp_levels, min_levels=3)
    rr_calc = _compute_rr(entry, sl, tp_levels[-1] if tp_levels else None)
    expected_profit = _expected_move_pct(entry, tp_levels[-1] if tp_levels else None, signal.get("direction", "long"))
    expected_loss = _expected_move_pct(entry, sl, "short" if str(signal.get("direction", "long")).lower() in ("long", "buy") else "long")
    freshness = _freshness_text(signal)
    age_text = _signal_age_text(signal)
    expiry_text = _expiry_text(signal)
    suggested_size = _suggested_size_text(signal)
    generated_time = _signal_generated_time(signal)

    # R/R — use last TP for best-case calculation
    rr = signal.get("risk_reward") or signal.get("rr_ratio") or signal.get("rr_estimate")
    if not rr and entry and sl and tp_levels:
        try:
            _e, _s, _t = float(entry), float(sl), float(tp_levels[-1])
            rr = abs(_t - _e) / max(1e-9, abs(_e - _s))
        except Exception:
            pass

    lines = [
        "🚨 <b>VIP SIGNAL DETECTED</b> 🚨",
        f"Asset: <b>{asset_disp}</b>",
        f"Direction: <b>{direction_disp}</b>",
    ]

    if generated_time:
        lines.append(f"🕐 Generated: {_h(generated_time)}")

    lines += [
        "",
        "📊 <b>AI Analysis:</b>",
        f"🤖 Conviction Score: {score_val:.1f}%",
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
            lines.append(f"🧱 Setup: {_h(str(tl)[:100])}")

    # Volatility with regime context
    regime = signal.get("regime") or signal.get("market_regime", "")
    vol_line = f"⚠️ Volatility: {_h(volatility)}"
    if regime and str(regime).strip():
        vol_line += f" — {_h(str(regime))}"
    lines.append(vol_line)

    # ML probability
    ml_prob = resolve_ml_probability(signal)
    if ml_prob is not None:
        lines.append(f"🧠 ML Probability: {ml_prob * 100.0:.1f}%")
    ai_review = _ai_review_text(signal)
    if ai_review:
        lines.append(f"🧠 AI Review: {_h(ai_review)}")

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
    if why:
        lines.append(f"Why: {_h(str(why)[:180])}")

    lines += [
        "",
        "🎯 <b>Targets &amp; Invalidation:</b>",
    ]

    if entry is not None:
        lines.append(f"Entry: {_h(_fmt_price_clean(entry, asset))}")
    if sl is not None:
        lines.append(f"🛑 Stop Loss: {_h(_fmt_price_clean(sl, asset))}")

    # TPs with auto-management annotations
    _tp_notes = [
        "(Bot will auto-close 50% &amp; move SL to BE)",
        "(Bot will auto-close 25%)",
        "(Moonbag running risk-free)",
    ]
    if tp_levels:
        for i, tp in enumerate(tp_levels[:3]):
            note = _tp_notes[i] if i < len(_tp_notes) else ""
            line = f"✅ TP{i + 1}: {_h(_fmt_price_clean(tp, asset))}"
            if note:
                line += f" {note}"
            lines.append(line)

    if rr:
        try:
            rr_val = float(rr)
            if rr_val > 0:
                lines.append(f"⚖️ Risk/Reward: 1:{rr_val:.1f}")
        except Exception:
            pass
    elif rr_calc is not None:
        lines.append(f"⚖️ Risk/Reward: 1:{rr_calc:.1f}")

    if expected_profit is not None:
        lines.append(f"💰 Expected Profit: +{expected_profit:.2f}%")
    if expected_loss is not None:
        loss_display = -abs(expected_loss)
        lines.append(f"🛡️ Expected Loss: {loss_display:.2f}%")

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
