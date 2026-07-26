from scripts.run_complete_system_test import HERMETIC_TEST_FILES, build_steps


class Args:
    profile = "configs/env/railway-hobby-owner-beta.env.example"
    output_dir = "artifacts/test"
    live_providers = False
    full = True
    pytest_batches = 20


def test_orchestrator_covers_cross_subsystem_contracts():
    names = {name for name, _ in build_steps(Args())}
    assert {
        "compileall",
        "schema_audit",
        "architecture_smoke",
        "runtime_config",
        "provider_certification",
    }.issubset(names)
    assert any(name.startswith("full_pytest_batch_") for name in names)
    assert "hermetic_system_suite" not in names

    class HermeticArgs(Args):
        full = False

    hermetic_names = {name for name, _ in build_steps(HermeticArgs())}
    assert "hermetic_system_suite" in hermetic_names
    assert not any(name.startswith("full_pytest_batch_") for name in hermetic_names)

    files = set(HERMETIC_TEST_FILES)
    required = {
        "tests/test_callback_handler.py",
        "tests/test_trader_profiles_and_platform_reliability.py",
        "tests/test_indices_asset_support.py",
        "tests/test_outcome_delivery_contract.py",
        "tests/test_paystack_webhook.py",
        "tests/test_broker_execution_p0.py",
        "tests/test_resource_governor.py",
    }
    assert required.issubset(files)


def test_orchestrator_streams_step_output_to_log(tmp_path):
    import sys
    from scripts.run_complete_system_test import _run_step

    result = _run_step(
        "sample",
        [sys.executable, "-c", "print('captured-output')"],
        tmp_path,
        {},
    )
    assert result.ok is True
    assert "captured-output" in (tmp_path / "sample.log").read_text(encoding="utf-8")


def test_full_orchestrator_batches_cover_each_test_file_once():
    from scripts.run_complete_system_test import ROOT, _partition_pytest_files

    batches = _partition_pytest_files(20)
    flattened = [item for batch in batches for item in batch]
    expected = [
        str(path.relative_to(ROOT))
        for path in sorted((ROOT / "tests").rglob("test_*.py"))
    ]
    assert flattened == expected
    assert len(flattened) == len(set(flattened))
    assert len(batches) == 20
