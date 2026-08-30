from ml.evidence import evaluate_public_win_rate_claim


def _outcomes(wins: int, losses: int):
    rows = []
    for index in range(wins + losses):
        won = index < wins
        rows.append({
            "delivered": True,
            "out_of_sample": True,
            "thesis_fingerprint": f"thesis-{index}",
            "state": "tp3" if won else "stop_loss",
            "r_multiple": 1.0 if won else -1.0,
            "cost_r": 0.02,
        })
    return rows


def test_raw_accuracy_cannot_certify_public_win_rate():
    decision = evaluate_public_win_rate_claim(_outcomes(80, 20), approved_drawdown_limit_r=30)
    assert not decision.certified
    assert "minimum_200_terminal_delivered_oos_signals" in decision.reasons


def test_claim_requires_conservative_wilson_bound_and_expectancy():
    decision = evaluate_public_win_rate_claim(_outcomes(160, 40), approved_drawdown_limit_r=50)
    assert decision.certified
    assert decision.strict_confidence_low >= 0.70


def test_partial_profit_cannot_inflate_strict_tp3_win_rate():
    rows = _outcomes(140, 40)
    rows.extend({
        "delivered": True,
        "out_of_sample": True,
        "thesis_fingerprint": f"partial-{index}",
        "state": "partial_profit",
        "r_multiple": 0.5,
        "cost_r": 0.02,
    } for index in range(20))
    decision = evaluate_public_win_rate_claim(rows, approved_drawdown_limit_r=50)
    assert not decision.certified
    assert "wilson_lower_bound_below_70_percent" in decision.reasons


def test_duplicate_theses_are_not_counted_as_independent():
    rows = _outcomes(160, 40)
    for row in rows[100:]:
        row["thesis_fingerprint"] = "thesis-duplicate"
    decision = evaluate_public_win_rate_claim(rows, approved_drawdown_limit_r=50)
    assert not decision.certified
    assert decision.terminal_signals == 101
