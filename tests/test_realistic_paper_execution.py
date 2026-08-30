from services.ecosystem_policy import deterministic_paper_fill, portfolio_snapshot


SIGNAL = {"signal_id": "s-1", "asset": "BTCUSDT", "direction": "long", "entry": 100}


def test_paper_fill_records_costs_latency_and_partial_liquidity():
    fill = deterministic_paper_fill(
        user_id=1, signal=SIGNAL, quantity=10, available_quantity=4,
        spread_bps=10, slippage_bps=5, fee_bps=2, commission_bps=3,
        funding_bps=1, latency_ms=750,
    )
    assert fill.status == "partially_filled"
    assert fill.filled_quantity == 4
    assert fill.fill_price > fill.requested_price
    assert fill.fee > 0 and fill.commission > 0 and fill.funding > 0
    assert fill.latency_ms == 750
    snapshot = portfolio_snapshot(balance=1000, fills=[fill])
    assert snapshot["realized_fees"] == round(fill.fee + fill.commission + fill.funding, 8)


def test_paper_rejection_has_zero_fill_and_reason():
    fill = deterministic_paper_fill(
        user_id=1, signal=SIGNAL, quantity=10, reject_reason="market_closed"
    )
    assert fill.status == "rejected"
    assert fill.filled_quantity == 0
    assert fill.rejection_reason == "market_closed"
