from copy import deepcopy

import pytest

from scripts.run_release_manifest import load_manifest, validate


def test_canonical_manifest_references_existing_inputs():
    validate(load_manifest())


@pytest.mark.parametrize("command", [
    "python scripts/nonexistent_gate.py",
    "python -m pytest tests/nonexistent_test.py",
    "pyright --project nonexistent_config.json",
    "cd nonexistent_frontend && npm run build",
    "python ../external.py",
])
def test_missing_gate_inputs_fail_before_execution(command):
    data = deepcopy(load_manifest())
    data["gates"][0]["command"] = command
    with pytest.raises(RuntimeError, match="missing|invalid"):
        validate(data)


def test_manual_gate_requires_evidence_and_cannot_be_inventoried_as_automatic():
    data = deepcopy(load_manifest())
    gate = next(gate for gate in data["gates"] if gate["command"].startswith("manual:"))
    gate.pop("evidence_requirements")
    with pytest.raises(RuntimeError, match="explicit evidence"):
        validate(data)
