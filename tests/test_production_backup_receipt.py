from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import shlex

import pytest

from scripts import production_backup_receipt as backup

SCHEMA = "0045_mt5_credential_retirement"
NOW = datetime(2026, 10, 7, 1, tzinfo=timezone.utc)
DIGEST = "a" * 64
DEPLOYMENT = "5d4a6b02-93d1-4a0a-903d-e0e88164fed1"


def deployment():
    return {"id": DEPLOYMENT, "status": "SUCCESS", "meta": {
        "image": backup.BACKUP_IMAGE, "imageDigest": backup.BACKUP_IMAGE.split("@", 1)[1],
        "volumeMounts": ["/backup"], "serviceManifest": {"deploy": {
            "startCommand": "sh -c " + shlex.quote(backup.expected_program())}},
    }}


def logs(created: datetime = NOW - timedelta(hours=2)):
    receipt = {"created_at": (created + timedelta(minutes=3)).isoformat(), "alembic_revision": SCHEMA,
               "dump_sha256": DIGEST, "scope": "DISPOSABLE_LOCAL_SOCKET_RESTORE",
               "restore_verified": True, "cleanup_verified": True, "production_target_used": False,
               "counts": {"users": 3, "signals": 8, "outcomes": 5, "signal_deliveries": 12}}
    return [
        {"timestamp": (created + timedelta(minutes=1)).isoformat(), "attributes": [],
         "message": f"[backup] BACKUP_ARTIFACT_PASS file=/backup/signalrank-production-{created.strftime('%Y%m%dT%H%M%SZ')}.dump revision={SCHEMA} restore_verified=false"},
        {"timestamp": (created + timedelta(minutes=2)).isoformat(), "attributes": [],
         "message": f"[restore] restoring digest={DIGEST} into disposable socket-only database"},
        {"timestamp": (created + timedelta(minutes=3, seconds=2)).isoformat(), "message": "",
         "attributes": [{"key": key, "value": json.dumps(value)} for key, value in receipt.items()]},
    ]


def change_receipt(rows, key, value):
    attributes = rows[-1]["attributes"]
    attributes[:] = [item for item in attributes if item["key"] != key]
    attributes.append({"key": key, "value": json.dumps(value)})


def test_receipt_measures_age_from_dump_start_and_keeps_private_rows_out():
    result = backup.select_restore_receipt(list(reversed(logs())), SCHEMA, NOW)
    assert result == {"PRODUCTION_DB_BACKUP_VERIFIED": "1", "PRODUCTION_DB_BACKUP_ID": "sha256:" + DIGEST,
                      "PRODUCTION_DB_BACKUP_CREATED_AT": (NOW - timedelta(hours=2)).isoformat(),
                      "PRODUCTION_DB_BACKUP_ALEMBIC_HEAD": SCHEMA}
    assert "counts" not in result


@pytest.mark.parametrize("key,value", [
    ("restore_verified", False), ("restore_verified", "true"), ("cleanup_verified", False),
    ("production_target_used", True), ("scope", "PRODUCTION_RESTORE"),
    ("alembic_revision", "0049_research_trial_ledger"), ("dump_sha256", "b" * 64),
    ("dump_sha256", "not-a-digest"), ("created_at", NOW.isoformat()),
    ("created_at", "2026-10-06T23:03:00"), ("counts", {"users": True}), ("counts", None),
])
def test_invalid_restore_evidence_is_rejected(key, value):
    rows = logs()
    change_receipt(rows, key, value)
    with pytest.raises(backup.BackupReceiptError):
        backup.select_restore_receipt(rows, SCHEMA, NOW)


@pytest.mark.parametrize("created", [NOW - timedelta(hours=24, seconds=1), NOW + timedelta(seconds=1)])
def test_stale_or_future_dump_is_rejected(created):
    with pytest.raises(backup.BackupReceiptError):
        backup.select_restore_receipt(logs(created), SCHEMA, NOW)


@pytest.mark.parametrize("change", ["artifact", "digest-marker", "duplicate-attribute", "malformed-attribute"])
def test_missing_or_ambiguous_restore_lineage_is_rejected(change):
    rows = logs()
    if change == "artifact":
        rows.pop(0)
    elif change == "digest-marker":
        rows.pop(1)
    elif change == "duplicate-attribute":
        rows[-1]["attributes"].append(deepcopy(rows[-1]["attributes"][0]))
    else:
        rows[-1]["attributes"][0]["value"] = "private-malformed-value"
    with pytest.raises(backup.BackupReceiptError) as error:
        backup.select_restore_receipt(rows, SCHEMA, NOW)
    assert "private" not in str(error.value)


@pytest.mark.parametrize("change", ["status", "image", "digest", "mount", "program", "wrapper", "missing", "malformed-command"])
def test_backup_runtime_provenance_is_verified(change):
    row = deployment()
    assert backup.verify_backup_deployment(row) == DEPLOYMENT
    if change == "status": row["status"] = "FAILED"
    elif change == "image": row["meta"]["image"] = "postgres:latest"
    elif change == "digest": row["meta"]["imageDigest"] = "sha256:" + "b" * 64
    elif change == "mount": row["meta"]["volumeMounts"] = ["/other"]
    elif change == "program": row["meta"]["serviceManifest"]["deploy"]["startCommand"] += " unsafe"
    elif change == "wrapper": row["meta"]["serviceManifest"]["deploy"]["startCommand"] = "bash -c " + shlex.quote(backup.expected_program())
    elif change == "malformed-command": row["meta"]["serviceManifest"]["deploy"]["startCommand"] = {"private": "value"}
    else: row["meta"] = None
    with pytest.raises(backup.BackupReceiptError): backup.verify_backup_deployment(row)


class FakeRailway:
    def __init__(self):
        self.active = [deployment()]
        self.rows = logs()
        self.calls = []

    def railway(self, query, variables):
        self.calls.append((query, variables))
        if "serviceInstance" in query: return {"serviceInstance": {"activeDeployments": self.active}}
        return {"deploymentLogs": self.rows}


def test_reader_uses_only_the_owned_deployment_and_never_mutates():
    api = FakeRailway()
    assert backup.read_backup_receipt(api, "owned-environment", SCHEMA, NOW)["PRODUCTION_DB_BACKUP_VERIFIED"] == "1"
    assert len(api.calls) == 2
    assert api.calls[0][1]["service"] == backup.BACKUP_SERVICE
    assert api.calls[1][1]["deployment"] == DEPLOYMENT
    assert all(query.startswith("query") for query, _ in api.calls)


@pytest.mark.parametrize("shape", ["multiple", "no-active", "no-logs", "truncated"])
def test_reader_refuses_missing_or_truncated_platform_evidence(shape):
    api = FakeRailway()
    if shape == "multiple": api.active *= 2
    elif shape == "no-active": api.active = []
    elif shape == "no-logs": api.rows = []
    else: api.rows = [logs()[0]] * 500
    with pytest.raises(backup.BackupReceiptError): backup.read_backup_receipt(api, "owned", SCHEMA, NOW)
