"""Read and verify an owned Railway backup/isolated-restore receipt; no mutations."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import shlex
from typing import Any, Protocol

BACKUP_SERVICE = "5658004b-4056-4704-ac3d-79dce7d87bfc"
BACKUP_IMAGE = "postgres:18@sha256:5a5a84b19854a9ffaa54082c166ff4ec27473a361e496e5ea167f298f2da9722"
MAX_AGE = timedelta(hours=24)
ARTIFACT = re.compile(r"^\[backup\] BACKUP_ARTIFACT_PASS file=/backup/signalrank-production-(\d{8}T\d{6}Z)\.dump revision=([a-zA-Z0-9_]+) restore_verified=false$")
RESTORING = re.compile(r"^\[restore\] restoring digest=([0-9a-f]{64}) into disposable socket-only database$")


class BackupReceiptError(RuntimeError):
    """Messages intentionally exclude raw API responses and credentials."""


class RailwayReader(Protocol):
    def railway(self, query: str, variables: dict[str, Any]) -> dict[str, Any]: ...


def expected_program() -> str:
    root = Path(__file__).resolve().parent
    return "\n\n".join((root / name).read_text(encoding="utf-8").strip()
                        for name in ("production_backup.sh", "production_backup_restore.sh"))


def verify_backup_deployment(deployment: dict[str, Any]) -> str:
    if deployment.get("status") != "SUCCESS" or not re.fullmatch(r"[0-9a-f-]{36}", str(deployment.get("id", ""))):
        raise BackupReceiptError("Backup service has no unambiguous successful active deployment")
    meta = deployment.get("meta")
    try:
        meta = json.loads(meta) if isinstance(meta, str) else meta
        if not isinstance(meta, dict):
            raise ValueError
        if (meta.get("image") != BACKUP_IMAGE or meta.get("imageDigest") != BACKUP_IMAGE.split("@", 1)[1]
                or meta.get("volumeMounts") != ["/backup"]):
            raise ValueError
        command = meta["serviceManifest"]["deploy"]["startCommand"]
        if not isinstance(command, str):
            raise ValueError
        args = shlex.split(command)
        if len(args) != 3 or args[:2] != ["sh", "-c"] or args[2].strip() != expected_program():
            raise ValueError
    except (ValueError, TypeError, KeyError):
        raise BackupReceiptError("Backup image, mount or restore program differs from the audited repository") from None
    return str(deployment["id"])


def _timestamp(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError):
        raise BackupReceiptError("Backup receipt contains an invalid UTC timestamp") from None


def select_restore_receipt(logs: list[dict[str, Any]], schema: str, now: datetime) -> dict[str, str]:
    if now.tzinfo is None or not re.fullmatch(r"[a-zA-Z0-9_]+", schema):
        raise BackupReceiptError("Backup verification context is invalid")
    ordered = sorted(logs, key=lambda row: _timestamp(row.get("timestamp")))
    artifact: tuple[str, str] | None = None
    restoring: str | None = None
    latest: dict[str, Any] | None = None
    for row in ordered:
        message = row.get("message", "")
        match = ARTIFACT.fullmatch(message) if isinstance(message, str) else None
        if match:
            artifact = (match[1], match[2])
            restoring = None
        match = RESTORING.fullmatch(message) if isinstance(message, str) else None
        if match:
            restoring = match[1]
        attributes = row.get("attributes", [])
        if not isinstance(attributes, list):
            raise BackupReceiptError("Backup log attributes are unavailable")
        if not any(isinstance(item, dict) and item.get("key") == "restore_verified" for item in attributes):
            continue
        try:
            keys = [item["key"] for item in attributes]
            if len(keys) != len(set(keys)):
                raise ValueError
            receipt = {item["key"]: json.loads(item["value"]) for item in attributes}
        except (ValueError, TypeError, KeyError):
            raise BackupReceiptError("Backup restore receipt attributes are malformed") from None
        latest = {"receipt": receipt, "artifact": artifact, "restoring": restoring,
                  "log_time": _timestamp(row.get("timestamp"))}
    if latest is None or latest["artifact"] is None:
        raise BackupReceiptError("Backup service has no complete artifact and restore receipt")
    receipt = latest["receipt"]
    stamp, revision = latest["artifact"]
    digest = receipt.get("dump_sha256")
    if (receipt.get("restore_verified") is not True or receipt.get("cleanup_verified") is not True
            or receipt.get("production_target_used") is not False
            or receipt.get("scope") != "DISPOSABLE_LOCAL_SOCKET_RESTORE"
            or receipt.get("alembic_revision") != schema or revision != schema
            or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or latest["restoring"] != digest):
        raise BackupReceiptError("Backup restore proof, digest or schema validation failed")
    counts = receipt.get("counts")
    if not isinstance(counts, dict) or any(type(counts.get(key)) is not int or counts[key] < 0
                                          for key in ("users", "signals", "outcomes", "signal_deliveries")):
        raise BackupReceiptError("Backup restored-table verification is missing")
    try:
        created = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        raise BackupReceiptError("Backup artifact timestamp is invalid") from None
    completed = _timestamp(receipt.get("created_at"))
    logged = latest["log_time"]
    if not (created <= completed <= logged <= now + timedelta(seconds=5)) or completed > now:
        raise BackupReceiptError("Backup restore chronology is invalid")
    if now - created > MAX_AGE:
        raise BackupReceiptError("Restored production backup is older than 24 hours")
    return {"PRODUCTION_DB_BACKUP_VERIFIED": "1", "PRODUCTION_DB_BACKUP_ID": f"sha256:{digest}",
            "PRODUCTION_DB_BACKUP_CREATED_AT": created.isoformat(),
            "PRODUCTION_DB_BACKUP_ALEMBIC_HEAD": schema}


def read_backup_receipt(api: RailwayReader, environment: str, schema: str,
                        now: datetime | None = None) -> dict[str, str]:
    observed = now or datetime.now(timezone.utc)
    result = api.railway("""query($environment:String!, $service:String!) {
      serviceInstance(environmentId:$environment, serviceId:$service) {
        activeDeployments { id status meta }
      }
    }""", {"environment": environment, "service": BACKUP_SERVICE})
    active = (result.get("serviceInstance") or {}).get("activeDeployments")
    if not isinstance(active, list) or len(active) != 1 or not isinstance(active[0], dict):
        raise BackupReceiptError("Backup deployment identity is unavailable or ambiguous")
    deployment = verify_backup_deployment(active[0])
    result = api.railway("""query($deployment:String!, $since:DateTime!) {
      deploymentLogs(deploymentId:$deployment, startDate:$since, limit:500) {
        timestamp message attributes { key value }
      }
    }""", {"deployment": deployment, "since": (observed - MAX_AGE).isoformat()})
    logs = result.get("deploymentLogs")
    if not isinstance(logs, list) or not logs or len(logs) >= 500 or any(not isinstance(row, dict) for row in logs):
        raise BackupReceiptError("Backup logs are missing, ambiguous or truncated")
    return select_restore_receipt(logs, schema, observed)
