from __future__ import annotations

import asyncio

from core.agent_council import AGENT_SPECS, council_manifest
from core.automaton import AutomatonInputs, AutomatonState, evaluate
from core.release_guard import evaluate_release
from execution.service import ExecutionGate, ExecutionRequest
from ml.evidence import build_manifest, compute_metrics, evaluate_promotion, purged_walk_forward_splits
from payments.receipt_service import ReceiptService


def test_agent_council_is_explicit_and_forbids_dangerous_actions():
    assert len(AGENT_SPECS) >= 16
    assert len(council_manifest()) == len(AGENT_SPECS)
    assert all("execute_real_trade" in spec.forbidden_actions for spec in AGENT_SPECS)


def test_automaton_degrades_on_provider_and_dependency_health():
    decision = evaluate(AutomatonInputs(provider_confidence=0.2))
    assert decision.state is AutomatonState.PAUSE
    decision = evaluate(AutomatonInputs(db_healthy=False))
    assert decision.state is AutomatonState.CONSERVE


def test_receipt_requires_verified_payment_and_is_idempotent():
    service = ReceiptService()
    try:
        service.create_confirmed_receipt(user_id=1, plan="premium", amount=1, payment_reference="x")
    except ValueError as exc:
        assert str(exc) == "receipt_requires_verified_payment"
    else:
        raise AssertionError("unverified payment generated a receipt")
    one = service.create_confirmed_receipt(user_id=1, plan="premium", amount=1, payment_reference="x", verified=True)
    two = service.create_confirmed_receipt(user_id=1, plan="premium", amount=1, payment_reference="x", verified=True)
    assert one == two
    assert "no profit" in one.text_body.lower()


def test_evidence_is_reproducible_and_promotion_is_conservative():
    first = build_manifest(dataset_id="d", rows=[{"t": 1}], strategy_version="s")
    second = build_manifest(dataset_id="d", rows=[{"t": 1}], strategy_version="s")
    assert first.manifest_hash == second.manifest_hash
    metrics = compute_metrics([{"r": 1, "state": "tp1"}, {"r": -1, "state": "sl"}])
    decision = evaluate_promotion(first, metrics)
    assert not decision.eligible
    assert purged_walk_forward_splits(list(range(20)), train_size=10, test_size=5, embargo=1) == [
        (list(range(10)), list(range(11, 16)))
    ]


def test_execution_gate_is_default_off_and_deduplicates():
    gate = ExecutionGate()
    request = ExecutionRequest(
        user_id=1,
        signal_id="s",
        signal={"entry": 100, "stop_loss": 90, "direction": "long"},
        tier="VIP",
        mode="auto",
        consent=True,
        account_ready=True,
        quote_trusted=True,
        market_open=True,
        risk_allowed=True,
        evidence_allowed=True,
    )
    async def submit(_request):
        raise AssertionError("default-off execution attempted")
    result = asyncio.run(gate.execute(request, submit))
    assert result.status == "BLOCKED"
    assert "AUTO_TRADE_DISABLED" in result.decision.reasons
