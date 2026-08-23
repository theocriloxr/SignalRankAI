from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_v81_resumable_artifacts_exist_and_are_secret_safe() -> None:
    paths = (
        "docs/operations/CONNECTED_ACCESS_INVENTORY.md",
        "docs/operations/HUMAN_ACTIONS.md",
        "artifacts/staging/staging_checkpoint.json",
        "artifacts/staging/staging_certification_manifest.json",
        "artifacts/release/production_promotion_request.md",
        "artifacts/release/production_promotion_manifest.json",
    )
    for path in paths:
        text = (ROOT / path).read_text(encoding="utf-8")
        assert text.strip()
        assert "sk_live_" not in text
        assert "sk_test_" not in text
        assert "postgresql://" not in text
        assert "redis://" not in text


def test_v81_staging_checkpoint_is_fail_closed_and_resumable() -> None:
    checkpoint = _json("artifacts/staging/staging_checkpoint.json")
    assert checkpoint["environment"] == "staging"
    assert checkpoint["schema_head"] == "0038_account_security_product"
    assert checkpoint["production_mutation"] is False
    assert checkpoint["real_execution"] is False
    assert checkpoint["public_payments"] is False
    assert checkpoint["blockers"]
    assert checkpoint["resume"]["first_command"]


def test_v81_promotion_manifest_requires_literal_future_approval() -> None:
    promotion = _json("artifacts/release/production_promotion_manifest.json")
    assert promotion["status"] == "NOT_READY"
    assert promotion["production_write_authorized"] is False
    assert promotion["required_literal_instruction"] == "PROMOTE_TO_PRODUCTION"
    assert promotion["dangerous_features_remain_disabled"] is True


def test_v81_runtime_manifest_does_not_upgrade_structural_truth() -> None:
    certification = _json("artifacts/staging/staging_certification_manifest.json")
    assert certification["structural_certification"] == "PASS"
    assert certification["runtime_certification"] == "BLOCKED"
    assert certification["verdict"] == "STAGING_ONLY"
    assert certification["blocking_gates"]
