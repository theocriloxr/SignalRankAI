"""A readiness label requires positive evidence for every preceding step."""
import pytest

from core.asset_certification import CERTIFICATION_STEPS, ReadinessState, evaluate_certification


@pytest.mark.parametrize("value", [False, "false", "true", "FAILED", 1, 0, None, [], {"ok": "false"}, {"ok": "true"}, {"ok": 1}, {"status": "PASS"}])
def test_truthy_or_untyped_status_does_not_establish_a_certification_step(value):
    report = evaluate_certification("crypto", {step: value for step in CERTIFICATION_STEPS}, live_guarded=True)
    assert report.ready_steps == ()
    assert report.coverage_pct == 0
    assert report.readiness is ReadinessState.CONFIGURED


@pytest.mark.parametrize("step", CERTIFICATION_STEPS)
def test_missing_step_prevents_testnet_or_live_guarded_label(step):
    evidence = {name: {"ok": True} for name in CERTIFICATION_STEPS}
    evidence[step] = {"ok": False}
    for flags in ({"testnet_ready": True}, {"live_guarded": True}):
        report = evaluate_certification("crypto", evidence, **flags)
        assert report.readiness not in {ReadinessState.TESTNET_READY, ReadinessState.LIVE_GUARDED}
        assert step in report.missing_steps


@pytest.mark.parametrize("step", ["symbol_discovery", "canonical_mapping", "historical_candles"])
def test_fresh_quotes_do_not_replace_incomplete_analysis_chain(step):
    evidence = {name: True for name in CERTIFICATION_STEPS}
    evidence[step] = False
    report = evaluate_certification("crypto", evidence, live_guarded=True)
    assert report.readiness is ReadinessState.MARKET_DATA_PARTIAL
    assert "analysis_chain_incomplete" in report.notes


def test_only_explicit_boolean_activation_arguments_select_higher_readiness():
    evidence = {name: True for name in CERTIFICATION_STEPS}
    assert evaluate_certification("crypto", evidence, live_guarded="false", testnet_ready="false").readiness is ReadinessState.PAPER_READY
    assert evaluate_certification("crypto", evidence, live_guarded=True).readiness is ReadinessState.LIVE_GUARDED
