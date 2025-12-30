def calculate_dynamic_risk(signal, regime):
    base_risk = 1.0
    if regime == "TRENDING":
        base_risk += 0.5
    if signal.get('timeframe') in ['1h', '4h', '1d']:
        base_risk += 0.5
    if signal.get('rr_ratio', 2) < 2:
        base_risk -= 0.5
    risk = max(0.5, min(base_risk, 2.0))
    return {
        'risk_percent': risk,
        'position_size': calculate_position_size(signal, risk)
    }

def calculate_position_size(signal, risk):
    # Placeholder: implement position sizing logic
    return 1.0
