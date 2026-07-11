import os

from engine.signal_metrics import (
    resolve_confidence_ratio,
    resolve_confluence_percent,
    resolve_ml_probability,
    resolve_score_percent,
)


def _env_float(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or str(default)).strip())
    except Exception:
        return float(default)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def consensus_filter(signals, min_score=None):
    """
    Robust, weighted, and configurable ensemble consensus logic.
    - Groups signals by (symbol, timeframe, direction)
    - Sums weighted confidence across all strategies
    - Requires minimum total confidence and minimum unique strategy groups
    - Integrates ML adjustments (if present in signal)
    - Guarantees one unique signal per asset/timeframe/candle/consensus
    """
    if not signals:
        return []

    # Allow disabling consensus entirely (for debugging / low-liquidity periods)
    if not _env_bool("CONSENSUS_ENABLED", True):
        return list(signals)

    if min_score is None:
        # Relaxed threshold: lower values = more signals pass through
        # TEMPORARILY LOWERED for debugging - signals were 0 with 0.20
        min_score = _env_float("CONSENSUS_MIN_SCORE", 0.10)

    try:
        min_groups = int((os.getenv("CONSENSUS_MIN_GROUPS") or "1").strip())
    except Exception:
        min_groups = 1
        # TEMPORARILY lowered from 3 to 2 for debugging
        min_groups = max(2, int(min_groups))

    grouped_score: dict[tuple[str, str, str], float] = {}
    grouped_groups: dict[tuple[str, str, str], set[str]] = {}
    grouped_signals: dict[tuple[str, str, str], list[dict]] = {}

    for s in signals:
        sym = str(s.get("symbol") or s.get("asset") or "").strip()
        tf = str(s.get("timeframe") or "").strip().lower()
        direction = str(s.get("direction") or "").strip().lower()
        if not sym or not tf or direction not in {"long", "short", "buy", "sell"}:
            continue
        if direction == "buy":
            direction = "long"
        if direction == "sell":
            direction = "short"
        key = (sym, tf, direction)
        grouped_score.setdefault(key, 0.0)
        grouped_groups.setdefault(key, set())
        grouped_signals.setdefault(key, [])
        try:
            conf = resolve_confidence_ratio(s)
            if conf is None:
                score_pct = resolve_score_percent(s)
                if score_pct is not None:
                    conf = max(0.0, min(score_pct / 100.0, 1.0))
            if conf is None:
                conf = resolve_ml_probability(s)
            if conf is None:
                conf = resolve_confluence_percent(s)
                if conf is not None:
                    conf = max(0.0, min(conf / 100.0, 1.0))
            if conf is None:
                continue
            w = s.get("weight")
            if w is None:
                w = 1.0
            # ML adjustment: if ml_probability is present, use as a multiplier (advisory only)
            ml_prob = resolve_ml_probability(s)
            if ml_prob is not None:
                boost_min = _env_float("CONSENSUS_ML_BOOST_MIN", 0.8)
                boost_range = _env_float("CONSENSUS_ML_BOOST_RANGE", 0.4)
                conf = float(conf or 0.0) * (boost_min + (boost_range * float(ml_prob)))
            grouped_score[key] += float(conf or 0.0) * float(w or 1.0)
        except Exception:
            pass
        try:
            g = str(s.get("strategy_group") or "").strip().lower()
            if g:
                grouped_groups[key].add(g)
        except Exception:
            pass
        grouped_signals[key].append(s)

    approved: list[dict] = []
    # TEMPORARILY disabled strict_groups for debugging - was blocking all signals
    strict_groups = _env_bool("CONSENSUS_STRICT_GROUPS", False) if _env_bool("PROD_MODE", True) else _env_bool("CONSENSUS_STRICT_GROUPS", False)
    required_groups = ["momentum", "trend", "structure", "volatility", "volume"]
    for key, sigs in grouped_signals.items():
        # Only approve if total confidence and group count pass thresholds
        if float(grouped_score.get(key) or 0.0) < float(min_score):
            continue
        groups_present = set(grouped_groups.get(key) or set())
        if groups_present:
            # TEMPORARILY relaxed - was requiring all 3 groups
            has_momentum = "momentum" in groups_present
            has_trend_or_structure = bool({"trend", "structure"} & groups_present)
            has_vol_or_volume = bool({"volatility", "volume"} & groups_present)
            # TEMPORARILY disabled strict check - only require 1 group now
            if strict_groups and len(groups_present) < 1:
                continue
            if len(groups_present) < int(min_groups):
                continue
        else:
            # If strategy groups are missing, allow consensus to pass on score alone (unless strict)
            if strict_groups:
                continue
        # Guarantee one unique signal per asset/timeframe/direction/consensus
        # Pick the highest-confidence signal as representative
        best = max(sigs, key=lambda s: float(s.get("confidence", s.get("strength", s.get("score", 0)) or 0)), default=None)
        if best:
            approved.append(best)
    return approved


apply_consensus_filter = consensus_filter


def group_by_asset_and_direction(signals):
    # Group signals by (asset, direction)
    grouped = {}
    for s in signals:
        key = (s.get('asset'), s.get('direction'))
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(s)
    return grouped


def unique_strategy_groups(group):
    # Return unique strategy groups in group
    groups = set()
    for sig in group or []:
        try:
            g = str(sig.get("strategy_group") or sig.get("strategy") or "").strip().lower()
            if g:
                groups.add(g)
        except Exception:
            continue
    return groups


def contains_required_groups(strategies_used):
    # Check for required groups
    required_raw = str(os.getenv("CONSENSUS_REQUIRED_GROUPS") or "").strip()
    if required_raw:
        required = {g.strip().lower() for g in required_raw.split(",") if g.strip()}
    else:
        required = {"momentum", "trend", "structure", "volatility", "volume"}
    used = {str(s).strip().lower() for s in (strategies_used or []) if str(s).strip()}
    if not required:
        return True
    return bool(required & used)


def best_signal_in_group(group):
    # Return best signal in group
    if not group:
        return None

    def _rank(sig):
        score = resolve_score_percent(sig) or 0.0
        ml = resolve_ml_probability(sig) or 0.0
        conf = resolve_confidence_ratio(sig) or 0.0
        return (score, ml, conf)

    try:
        return max(group, key=_rank)
    except Exception:
        return group[0]
