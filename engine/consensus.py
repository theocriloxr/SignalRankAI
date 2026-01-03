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
        # Consensus threshold: higher values = fewer but higher-quality signals
        # Recommendations:
        # - 0.6: Permissive (single strategy @ 0.6+ confidence)
        # - 0.8: Moderate (single strategy @ 0.8+ or 2 @ 0.4+ confidence)
        # - 1.0: Selective (2 strategies @ 0.5+)
        # - 1.4: Strict (2 strategies @ 0.7+)
        # - 2.0: Very Strict (3 strategies @ 0.67+)
        # 
        # Default to 0.8 for balanced signal generation with quality control
        min_score = _env_float("CONSENSUS_MIN_SCORE", 0.8)

    try:
        min_groups = int((os.getenv("CONSENSUS_MIN_GROUPS") or "1").strip())
    except Exception:
        min_groups = 1
    min_groups = max(1, int(min_groups))

    grouped_score: dict[tuple[str, str, str], float] = {}
    grouped_groups: dict[tuple[str, str, str], set[str]] = {}

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
        try:
            conf = s.get("confidence")
            if conf is None:
                conf = s.get("strength")
            w = s.get("weight")
            if w is None:
                w = 1.0
            grouped_score[key] += float(conf or 0.0) * float(w or 1.0)
        except Exception:
            pass
        try:
            g = str(s.get("strategy_group") or "").strip().lower()
            if g:
                grouped_groups[key].add(g)
        except Exception:
            pass

    approved: list[dict] = []
    for signal in signals:
        sym = str(signal.get("symbol") or signal.get("asset") or "").strip()
        tf = str(signal.get("timeframe") or "").strip().lower()
        direction = str(signal.get("direction") or "").strip().lower()
        if direction == "buy":
            direction = "long"
        if direction == "sell":
            direction = "short"
        key = (sym, tf, direction)
        if float(grouped_score.get(key) or 0.0) < float(min_score):
            continue
        if len(grouped_groups.get(key) or set()) < int(min_groups):
            continue
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
