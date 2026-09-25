from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

from tools import staging_certification as certification
from scripts import assert_database_schema as schema_gate
from scripts import staging_runtime_proof as runtime_proof


def valid_report():
    head = schema_gate._expected_head()
    return {
        "environment": "staging",
        "release": {"commit_matches_expected": True},
        "schema": {"single_head": True, "expected_head": head},
        "runtime_schema": {"ok": True, "alembic_current": head, "alembic_expected_head": head},
        "database_url_set": True,
        "safety_flags": dict.fromkeys(certification.LIVE_FLAGS, "0"),
        **{name: {"available": True} for name in certification.REGISTRIES},
    }


def test_complete_admission_report_passes():
    assert certification.blockers(valid_report()) == []


@pytest.mark.parametrize("section", ["release", "schema", "runtime_schema", *certification.REGISTRIES])
def test_missing_or_failed_diagnostic_cannot_certify(section):
    report = valid_report()
    report.pop(section)
    assert certification.blockers(report)
    report[section] = {"error": "unavailable"}
    assert certification.blockers(report)


def test_offline_preflight_is_not_runtime_proof():
    report = valid_report()
    report.pop("runtime_schema")
    report["release"]["commit_matches_expected"] = False
    assert certification.blockers(report, require_runtime=False) == []
    assert "runtime_schema_unproven" in certification.blockers(report)
    assert any(item.startswith("release_identity:") for item in certification.blockers(report))


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "perhaps", None])
def test_unknown_or_enabled_financial_flags_block(value):
    report = valid_report()
    report["safety_flags"]["MT5_ALLOW_LIVE_ACCOUNTS"] = value
    assert "unsafe_live_risk_flag:MT5_ALLOW_LIVE_ACCOUNTS" in certification.blockers(report)


@pytest.mark.parametrize("value", ["0", "FALSE", " False ", "OFF", "no"])
def test_disabled_financial_flags_are_normalized(value):
    report = valid_report()
    report["safety_flags"] = dict.fromkeys(certification.LIVE_FLAGS, value)
    assert certification.blockers(report) == []


def test_matching_revision_cannot_hide_failed_runtime_admission():
    report = valid_report()
    report["runtime_schema"]["ok"] = False
    assert "runtime_schema_unproven" in certification.blockers(report)


def test_json_mode_emits_one_document_without_certification_claim(monkeypatch, capsys):
    monkeypatch.setattr(certification, "collect_report", lambda **kwargs: valid_report())
    monkeypatch.setattr(sys, "argv", ["staging_certification", "--offline", "--json"])
    assert certification.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "PREFLIGHT_PASS"


class FakeCursor:
    def __init__(self, revisions, missing):
        record = {
            "deployed_revisions": revisions,
            **dict.fromkeys((
                "subscription_products", "instruments", "webhook_deliveries",
                "auth_identities", "user_sessions", "user_acquisition",
                "broker_connections", "trading_account_policies",
                "broker_reconciliation_state", "broker_execution_decisions",
                "broker_executions_connection_id", "mt5_executions_connection_id",
                "signals_ml_recovery_mode", "users_public_user_id",
            ), True),
        }
        record.update({name: False for name in missing})
        self.description = [(key,) for key in record]
        self.row = tuple(record.values())
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, query):
        self.queries.append(query)

    def fetchone(self):
        return self.row


@pytest.mark.parametrize("extra_revision,missing,allowed", [
    (False, (), True),
    (True, (), False),
    (False, ("signals_ml_recovery_mode",), False),
    (False, ("broker_connections",), False),
])
def test_schema_gate_checks_all_revisions_and_execution_columns(monkeypatch, extra_revision, missing, allowed):
    head = schema_gate._expected_head()
    cursor = FakeCursor([head, "other_branch"] if extra_revision else [head], missing)
    settings = {}
    connection = SimpleNamespace(
        cursor=lambda: cursor,
        set_session=lambda **kwargs: settings.update(kwargs),
        close=lambda: None,
    )
    monkeypatch.setattr(schema_gate, "_runtime_database_url", lambda: "postgresql://unused")
    monkeypatch.setitem(sys.modules, "psycopg2", SimpleNamespace(connect=lambda *args, **kwargs: connection))
    report = schema_gate.check_schema()
    assert report["ok"] is allowed
    assert settings == {"readonly": True, "autocommit": True}
    assert "statement_timeout" in cursor.queries[0]
    required = report["required_schema"]
    for key in (
        "trading_account_policies",
        "broker_reconciliation_state",
        "broker_execution_decisions",
        "broker_executions_connection_id",
        "mt5_executions_connection_id",
    ):
        assert key in required


def test_schema_driver_failure_does_not_disclose_credentials(monkeypatch, capsys):
    def fail():
        raise RuntimeError("postgresql://user:secret@host/db")
    monkeypatch.setattr(schema_gate, "check_schema", fail)
    monkeypatch.setattr(sys, "argv", ["assert_database_schema", "--json"])
    assert schema_gate.main() != 0
    output = capsys.readouterr().out
    assert "secret" not in output
    assert json.loads(output)["ok"] is False


def test_runtime_proof_uses_current_repository_head_and_rejects_incomplete_evidence():
    head = schema_gate._expected_head()
    report = {
        "alembic_current": head, "alembic_revisions": [head], "expected_head": head,
        "users_public_user_id": True,
        "broker_executions_connection_id": True,
        "mt5_executions_connection_id": True,
        "required_tables": dict.fromkeys(runtime_proof.REQUIRED_TABLES, True),
        "catalogue_counts": {"active_products": 6}, "catalogue_minimums": {"active_products": 6},
        "runtime": {"duplicate_delivery_groups": 0, "duplicate_paper_position_groups": 0},
    }
    assert runtime_proof.evaluate(report) == []
    report["alembic_current"] = "0038_account_security_product"
    assert any(item.startswith("alembic:") for item in runtime_proof.evaluate(report))
    report["alembic_current"] = head
    report.pop("required_tables")
    assert "missing_table:auth_identities" in runtime_proof.evaluate(report)


def test_failed_post_migration_certification_returns_nonzero(monkeypatch, tmp_path):
    from scripts import staging_migrate_and_bootstrap as migration

    monkeypatch.setattr(migration, "migrate_and_bootstrap", lambda **kwargs: {
        "status": "BLOCKED", "certification_passed": False,
    })
    monkeypatch.setattr(sys, "argv", ["migration", "--output", str(tmp_path / "report.json")])
    assert migration.main() == 1
