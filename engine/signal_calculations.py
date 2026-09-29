"""
Enhanced signal calculations: profit/loss, risk-reward, position sizing, pips.
"""
from utils.timeutils import now_utc_naive
import json
import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def _normalize_direction(direction: Any) -> str | None:
    raw = str(direction or "").strip().lower()
    if raw in {"long", "buy"}:
        return "long"
    if raw in {"short", "sell"}:
        return "short"
    return None


def _parse_target_levels(raw: Any) -> list[float]:
    """Normalize numeric, JSON, mapping, and list target formats."""
    if raw is None:
        return []
    if isinstance(raw, str):
        text_value = raw.strip()
        if not text_value:
            return []
        try:
            raw = json.loads(text_value)
        except Exception:
            raw = [part.strip() for part in text_value.strip("[]").split(",") if part.strip()]
    if isinstance(raw, dict):
        # Preserve explicit TP ordering before falling back to mapping values.
        ordered: list[Any] = []
        for key in ("tp1", "target1", "1", "first", "tp2", "target2", "2", "second", "tp3", "target3", "3", "third"):
            if key in raw:
                ordered.append(raw[key])
        raw = ordered or list(raw.values())
    if not isinstance(raw, (list, tuple, set)):
        raw = [raw]
    levels: list[float] = []
    for item in raw:
        if isinstance(item, dict):
            item = item.get("price") or item.get("tp") or item.get("target") or item.get("value")
        try:
            value = float(item)
        except (TypeError, ValueError):
            continue
        if value > 0:
            levels.append(value)
    return levels


def _valid_target_for_direction(entry: float, target: float, direction: str) -> bool:
    return (direction == "long" and target > entry) or (direction == "short" and target < entry)


def calculate_profit_loss_pct(entry: float, exit_price: float, direction: str) -> float:
    """Calculate signed price return percentage for a valid trade direction."""
    try:
        entry_f = float(entry)
        exit_f = float(exit_price)
    except (TypeError, ValueError):
        return 0.0
    normalized = _normalize_direction(direction)
    if entry_f <= 0 or exit_f <= 0 or normalized is None:
        return 0.0
    if normalized == "long":
        return ((exit_f - entry_f) / entry_f) * 100.0
    return ((entry_f - exit_f) / entry_f) * 100.0


def calculate_expected_profit(signal: Dict) -> Optional[float]:
    """Calculate TP1 return only when target geometry matches the direction."""
    try:
        entry = float(signal.get("entry", 0) or 0)
    except (TypeError, ValueError):
        return None
    direction = _normalize_direction(signal.get("direction"))
    targets = _parse_target_levels(
        signal.get("take_profit") or signal.get("targets") or signal.get("tp_levels")
    )
    if entry <= 0 or direction is None or not targets:
        return None
    tp1 = float(targets[0])
    if not _valid_target_for_direction(entry, tp1, direction):
        return None
    value = calculate_profit_loss_pct(entry, tp1, direction)
    return value if value > 0 else None


def calculate_expected_loss(signal: Dict) -> Optional[float]:
    """Calculate signed stop-loss return when stop geometry is valid."""
    try:
        entry = float(signal.get("entry", 0) or 0)
        stop_loss = float(signal.get("stop_loss") or signal.get("stop") or 0)
    except (TypeError, ValueError):
        return None
    direction = _normalize_direction(signal.get("direction"))
    if entry <= 0 or stop_loss <= 0 or direction is None:
        return None
    if direction == "long" and stop_loss >= entry:
        return None
    if direction == "short" and stop_loss <= entry:
        return None
    value = calculate_profit_loss_pct(entry, stop_loss, direction)
    return value if value < 0 else None


def calculate_rr_ladder(signal: Dict) -> Dict[str, Any]:
    """Return canonical TP1/final/per-target R:R from executable geometry."""
    try:
        entry = float(signal.get("entry", 0) or 0)
        stop = float(signal.get("stop_loss") or signal.get("stop") or 0)
    except (TypeError, ValueError):
        return {"target_rrs": [], "tp1_rr": None, "final_rr": None}
    direction = _normalize_direction(signal.get("direction"))
    targets = _parse_target_levels(
        signal.get("take_profit") or signal.get("targets") or signal.get("tp_levels")
    )
    risk = abs(entry - stop)
    if entry <= 0 or stop <= 0 or risk <= 0 or direction is None:
        return {"target_rrs": [], "tp1_rr": None, "final_rr": None}
    if direction == "long" and stop >= entry:
        return {"target_rrs": [], "tp1_rr": None, "final_rr": None}
    if direction == "short" and stop <= entry:
        return {"target_rrs": [], "tp1_rr": None, "final_rr": None}
    valid = [tp for tp in targets if _valid_target_for_direction(entry, tp, direction)]
    target_rrs = [abs(float(tp) - entry) / risk for tp in valid]
    return {
        "target_rrs": [round(value, 6) for value in target_rrs],
        "tp1_rr": round(target_rrs[0], 6) if target_rrs else None,
        "final_rr": round(target_rrs[-1], 6) if target_rrs else None,
    }


def calculate_risk_reward(signal: Dict) -> Optional[float]:
    """Compatibility R:R value, preferring executable geometry over cached metadata."""
    ladder = calculate_rr_ladder(signal)
    tp1 = ladder.get("tp1_rr")
    if tp1 is not None:
        return float(tp1)

    # When executable geometry is present but invalid, never resurrect a stale
    # precomputed rr_ratio/rr_estimate. That would make web/Telegram disagree
    # with the actual entry/stop/target shown to the user.
    geometry_present = bool(
        signal.get("entry") is not None
        and (signal.get("stop_loss") is not None or signal.get("stop") is not None)
        and (
            signal.get("take_profit") is not None
            or signal.get("targets") is not None
            or signal.get("tp_levels") is not None
        )
    )
    if geometry_present:
        return None

    for key in ("rr_ratio", "rr_estimate"):
        try:
            value = float(signal.get(key))
            if value > 0:
                return value
        except (TypeError, ValueError):
            continue
    return None


def calculate_position_size(signal: Dict, account_balance: float = 10000, risk_pct: float = 1.0) -> Optional[float]:
    """
    Calculate suggested position size using 1% risk rule.
    
    Args:
        signal: Signal dict with entry and stop_loss
        account_balance: Account balance (default 10000)
        risk_pct: Risk percentage per trade (default 1%)
    
    Returns:
        Position size in asset units
    """
    try:
        entry = float(signal.get("entry", 0) or 0)
        stop_loss = float(signal.get("stop_loss") or signal.get("stop") or 0)
        balance = float(account_balance)
        risk_percent = float(risk_pct)
        direction = _normalize_direction(signal.get("direction"))

        if entry <= 0 or stop_loss <= 0 or balance <= 0 or risk_percent <= 0 or direction is None:
            return None
        if direction == "long" and stop_loss >= entry:
            return None
        if direction == "short" and stop_loss <= entry:
            return None

        risk_per_unit = abs(entry - stop_loss)
        if risk_per_unit <= 0:
            return None

        # This is deliberately asset-units, not lots/contracts. Broker-specific
        # sizing must convert this through its own contract-size/tick-value rules.
        risk_amount = balance * (risk_percent / 100.0)
        position_size = risk_amount / risk_per_unit
        return position_size if position_size > 0 else None
    
    except Exception as e:
        logger.debug(f"Failed to calculate position size: {e}")
        return None


def calculate_pips(asset: str, entry: float, exit_price: float) -> Optional[float]:
    """Calculate pips for canonical FX symbols with or without separators."""
    try:
        symbol = str(asset or "").upper().replace("/", "").replace("-", "").replace("_", "")
        fiat = {
            "USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD",
            "SGD", "HKD", "NOK", "SEK", "DKK", "ZAR", "MXN", "TRY", "PLN",
        }
        if len(symbol) != 6 or symbol[:3] not in fiat or symbol[3:] not in fiat:
            return None
        entry_f = float(entry)
        exit_f = float(exit_price)
        if entry_f <= 0 or exit_f <= 0:
            return None
        pip_size = 0.01 if symbol[3:] == "JPY" else 0.0001
        return abs(exit_f - entry_f) / pip_size
    except (TypeError, ValueError):
        return None


def calculate_signal_age_minutes(signal: Dict) -> Optional[int]:
    """Calculate signal age in minutes from created_at timestamp."""
    try:
        from datetime import datetime, timezone

        created_at = signal.get("created_at")
        if not created_at:
            return None
        
        # Handle both datetime objects and string timestamps
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if created_at.tzinfo is not None:
            created_at = created_at.astimezone(timezone.utc).replace(tzinfo=None)

        age = now_utc_naive() - created_at
        return max(0, int(age.total_seconds() / 60))
    
    except Exception as e:
        logger.debug(f"Failed to calculate signal age: {e}")
        return None


def get_price_status_indicator(signal: Dict) -> str:
    """
    Get colored indicator for price status.
    
    Returns:
        Emoji indicator showing if conditions are favorable, cautious, or unfavorable
    """
    try:
        current_price = signal.get('current_price')
        entry = float(signal.get('entry', 0))
        direction = signal.get('direction', 'long').lower()
        
        if current_price is None or entry <= 0:
            return "ℹ️"
        
        current_price = float(current_price)
        normalized = _normalize_direction(direction)
        if normalized is None:
            return "ℹ️"

        # Entry-drift indicator only; this is not a prediction of market quality.
        if normalized == "long":
            if current_price < entry * 0.995:  # More than 0.5% below entry
                return "✅"  # Good entry opportunity
            elif current_price > entry * 1.005:  # More than 0.5% above entry
                return "❌"  # Unfavorable entry
            else:
                return "⚠️"  # Near entry
        else:  # short
            if current_price > entry * 1.005:  # More than 0.5% above entry
                return "✅"  # Good entry opportunity
            elif current_price < entry * 0.995:  # More than 0.5% below entry
                return "❌"  # Unfavorable entry
            else:
                return "⚠️"  # Near entry
    
    except Exception as e:
        logger.debug(f"Failed to get price status indicator: {e}")
        return "ℹ️"


def format_enhanced_signal_data(signal: Dict) -> Dict:
    """Calculate one canonical display/calculation projection for a signal."""
    rr_ladder = calculate_rr_ladder(signal)
    enhanced: Dict[str, Any] = {
        "expected_profit_pct": calculate_expected_profit(signal),
        "expected_loss_pct": calculate_expected_loss(signal),
        "risk_reward_ratio": calculate_risk_reward(signal),
        "rr_tp1": rr_ladder.get("tp1_rr"),
        "rr_final": rr_ladder.get("final_rr"),
        "rr_targets": rr_ladder.get("target_rrs") or [],
        "suggested_position_size": calculate_position_size(
            signal,
            account_balance=float(signal.get("account_balance") or 10000),
            risk_pct=float(signal.get("risk_pct") or 1.0),
        ),
        "position_size_unit": "asset_units",
        "signal_age_minutes": calculate_signal_age_minutes(signal),
        "price_status_indicator": get_price_status_indicator(signal),
    }

    asset = str(signal.get("asset") or signal.get("symbol") or "")
    try:
        entry = float(signal.get("entry") or 0)
    except (TypeError, ValueError):
        entry = 0.0
    targets = _parse_target_levels(
        signal.get("take_profit") or signal.get("targets") or signal.get("tp_levels")
    )
    if entry > 0 and targets:
        enhanced["pips_to_tp"] = calculate_pips(asset, entry, targets[0])
    try:
        stop_loss = float(signal.get("stop_loss") or signal.get("stop") or 0)
    except (TypeError, ValueError):
        stop_loss = 0.0
    if entry > 0 and stop_loss > 0:
        enhanced["pips_to_sl"] = calculate_pips(asset, entry, stop_loss)
    return enhanced

