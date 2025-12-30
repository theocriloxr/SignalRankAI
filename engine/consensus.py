

def consensus_filter(signals, min_score=2.5):
    """
    Weighted consensus using strategy confidence.
    Groups signals by (symbol, direction) and sums confidence.
    Approves signals where total confidence >= min_score.
    """
    grouped = {}
    for s in signals:
        key = (s["symbol"], s["direction"])
        grouped.setdefault(key, 0)
        grouped[key] += s["confidence"]

    approved = []
    for signal in signals:
        key = (signal["symbol"], signal["direction"])
        if grouped[key] >= min_score:
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
