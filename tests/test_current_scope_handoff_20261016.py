"""Stage 1 scope safeguards; deliberately no market/broker/network side effects."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from scripts.validate_current_scope import SCOPE_PATH, validate_scope


@pytest.fixture
def scope():
    return json.loads(SCOPE_PATH.read_text(encoding="utf-8"))


def test_five_classes_are_bounded_without_claiming_trading_readiness(scope):
    assert validate_scope(scope) == {
        "commodity": 15,
        "crypto": 15,
        "equity": 15,
        "forex": 15,
        "index": 15,
    }
    assert scope["status"] == "NOT_IMPLEMENTED"
    assert scope["acceptance"]["status"] == "FAILED"


@pytest.mark.parametrize("class_name", ["crypto", "forex", "index", "equity", "commodity"])
def test_sixteenth_instrument_is_rejected(scope, class_name):
    candidate = deepcopy(scope)
    candidate["asset_classes"][class_name]["optional"].append("EXTRA16")
    with pytest.raises(ValueError, match="invalid_candidate_counts"):
        validate_scope(candidate)


def test_duplicate_instrument_is_rejected(scope):
    candidate = deepcopy(scope)
    candidate["asset_classes"]["crypto"]["optional"][0] = "BTCUSDT"
    with pytest.raises(ValueError, match="duplicate_candidate"):
        validate_scope(candidate)


@pytest.mark.parametrize("key", [
    "qualification_required", "provider_mapping_required",
    "broker_account_certification_required", "execution_requires_independent_authorization",
    "manage_existing_positions_when_excluded", "retain_historical_data",
    "no_production_permission_change_authorized", "no_live_order_tests_authorized",
])
def test_safety_gate_cannot_be_removed(scope, key):
    candidate = deepcopy(scope)
    candidate["policy"][key] = False
    with pytest.raises(ValueError, match="unsafe_scope_policy"):
        validate_scope(candidate)


def test_no_claim_of_completed_runtime_implementation(scope):
    candidate = deepcopy(scope)
    candidate["status"] = "VERIFIED"
    with pytest.raises(ValueError, match="scope_claims_implementation"):
        validate_scope(candidate)


def test_static_fallback_cannot_be_allowed(scope):
    candidate = deepcopy(scope)
    candidate["policy"]["allow_unqualified_fallback"] = True
    with pytest.raises(ValueError, match="unsafe_scope_policy"):
        validate_scope(candidate)
