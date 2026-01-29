import os


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
        # Consensus threshold: higher values = fewer but higher-quality signals
        min_score = _env_float("CONSENSUS_MIN_SCORE", 0.70)

    try:
        min_groups = int((os.getenv("CONSENSUS_MIN_GROUPS") or "1").strip())
    except Exception:
        min_groups = 1
    min_groups = max(1, int(min_groups))

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
            conf = s.get("confidence")
            if conf is None:
                conf = s.get("strength")
            w = s.get("weight")
            if w is None:
                w = 1.0
            # ML adjustment: if ml_probability is present, use as a multiplier (advisory only)
            ml_prob = s.get("ml_probability")
            if ml_prob is not None and isinstance(ml_prob, (float, int)):
                conf = float(conf or 0.0) * (0.8 + 0.4 * float(ml_prob))  # 0.8-1.2x boost
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
    required_groups = ["momentum", "trend", "structure", "volatility", "volume"]
    for key, sigs in grouped_signals.items():
        # Only approve if total confidence and group count pass thresholds
        if float(grouped_score.get(key) or 0.0) < float(min_score):
            continue
        groups_present = set(grouped_groups.get(key) or set())
        # Require at least one from each major group: momentum, (trend or structure), (volatility or volume)
        has_momentum = "momentum" in groups_present
        has_trend_or_structure = bool({"trend", "structure"} & groups_present)
        has_vol_or_volume = bool({"volatility", "volume"} & groups_present)
        if not (has_momentum and has_trend_or_structure and has_vol_or_volume):
            continue
        if len(groups_present) < int(min_groups):
            continue
        # Guarantee one unique signal per asset/timeframe/direction/consensus
        # Pick the highest-confidence signal as representative
        best = max(sigs, key=lambda s: float(s.get("confidence", 0)), default=None)
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
    # Placeholder: return unique strategy groups in group
    return set()

def contains_required_groups(strategies_used):
    # Placeholder: check for required groups
    return True

def best_signal_in_group(group):
    # Placeholder: return best signal in group
    return group[0] if group else None
