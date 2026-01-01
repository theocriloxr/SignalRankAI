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
    Weighted consensus using strategy confidence.
    Groups signals by (symbol, direction) and sums confidence.
    Approves signals where total confidence >= min_score.
    """
    if not signals:
        return []

    # Allow disabling consensus entirely (for debugging / low-liquidity periods)
    if not _env_bool("CONSENSUS_ENABLED", True):
        return list(signals)

    if min_score is None:
        # Default is intentionally permissive so the bot produces signals.
        # Tune in production: e.g. 1.4 (needs ~2 strategies at 0.7 confidence),
        # or 2.1 (needs ~3 strategies at 0.7 confidence).
        min_score = _env_float("CONSENSUS_MIN_SCORE", 0.7)

    grouped = {}
    for s in signals:
        sym = s.get("symbol") or s.get("asset")
        direction = s.get("direction")
        key = (sym, direction)
        grouped.setdefault(key, 0)
        try:
            grouped[key] += float(s.get("confidence") or 0.0)
        except Exception:
            grouped[key] += 0.0

    approved = []
    for signal in signals:
        sym = signal.get("symbol") or signal.get("asset")
        direction = signal.get("direction")
        key = (sym, direction)
        if float(grouped.get(key) or 0.0) >= float(min_score):
            approved.append(signal)
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
