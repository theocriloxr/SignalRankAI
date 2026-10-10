"""Replay the exact persisted outcome dataset, without rereading mutable sources.

This freezes canonical labels and captured sequence metadata. It does not invent
missing OHLC, feature vintages, historical universe membership or broker fills.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .dataset import AdaptiveDatasetRow, DatasetManifest, MAX_DATASET_ROWS, build_dataset

FORMAT_VERSION = 1
MAX_SNAPSHOT_BYTES = 32 * 1024 * 1024


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _aware(value: Any) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("snapshot_timestamp_invalid") from None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("snapshot_timestamp_must_be_aware")
    return value.astimezone(timezone.utc)


def encode_dataset_snapshot(rows: Sequence[AdaptiveDatasetRow], manifest: DatasetManifest) -> str:
    """Bound materialization and bind every stored row to the manifest hash."""
    if len(rows) > MAX_DATASET_ROWS or manifest.row_count != len(rows):
        raise ValueError("snapshot_row_count_invalid")
    header = '{"manifest":' + _json(manifest.to_dict()) + ',"rows":['
    size = len(header.encode("utf-8")) + 2
    encoded_rows: list[str] = []
    digest = hashlib.sha256(b"[")
    for ordinal, row in enumerate(rows):
        encoded = _json(row.canonical())
        size += len(encoded.encode("utf-8")) + bool(ordinal)
        if size > MAX_SNAPSHOT_BYTES:
            raise ValueError("research_dataset_snapshot_byte_budget_exceeded")
        if ordinal:
            digest.update(b",")
        digest.update(encoded.encode("utf-8"))
        encoded_rows.append(encoded)
    digest.update(b"]")
    if digest.hexdigest() != manifest.content_hash:
        raise ValueError("snapshot_content_hash_mismatch")
    if size > MAX_SNAPSHOT_BYTES:
        raise ValueError("research_dataset_snapshot_byte_budget_exceeded")
    return header + ",".join(encoded_rows) + "]}"


def restore_dataset_snapshot(
    payload: Mapping[str, Any], *, observation_cutoff: datetime,
) -> tuple[tuple[AdaptiveDatasetRow, ...], DatasetManifest]:
    """Validate structure, chronology, normalization and identity before replay."""
    if not isinstance(payload, Mapping) or set(payload) != {"manifest", "rows"}:
        raise ValueError("snapshot_payload_invalid")
    stored_manifest, stored_rows = payload["manifest"], payload["rows"]
    if not isinstance(stored_manifest, Mapping) or not isinstance(stored_rows, list):
        raise ValueError("snapshot_payload_invalid")
    if len(stored_rows) > MAX_DATASET_ROWS:
        raise ValueError("snapshot_row_count_invalid")
    version = stored_manifest.get("dataset_version")
    if not isinstance(version, str) or len(version) > 128 or ":" not in version:
        raise ValueError("snapshot_dataset_version_invalid")
    namespace = version.rsplit(":", 1)[0]
    cutoff = _aware(observation_cutoff)
    raw_rows: list[dict[str, Any]] = []
    expected_keys = set(AdaptiveDatasetRow.__dataclass_fields__)
    size = len(_json(stored_manifest).encode("utf-8"))
    for stored in stored_rows:
        if not isinstance(stored, Mapping) or set(stored) != expected_keys:
            raise ValueError("snapshot_row_invalid")
        size += len(_json(stored).encode("utf-8")) + 1
        if size > MAX_SNAPSHOT_BYTES:
            raise ValueError("research_dataset_snapshot_byte_budget_exceeded")
        row = dict(stored)
        row["decision_time"] = _aware(stored["decision_time"])
        row["outcome_known_at"] = _aware(stored["outcome_known_at"])
        refs = row["sequence_provenance"]
        hashes = row["sequence_hashes"]
        if not isinstance(refs, list) or len(refs) > 8 or not isinstance(hashes, list):
            raise ValueError("snapshot_sequence_metadata_invalid")
        provenance = []
        for encoded in refs:
            if not isinstance(encoded, str) or len(encoded.encode("utf-8")) > 4096:
                raise ValueError("snapshot_sequence_metadata_invalid")
            ref = json.loads(encoded)
            if not isinstance(ref, dict):
                raise ValueError("snapshot_sequence_metadata_invalid")
            summary_keys = ("captured_at", "timestamp_convention", "publication_vintage")
            summary = {key: ref.pop(key, None) for key in summary_keys}
            provenance.append({**ref, "summary": summary})
        row["sequence_provenance"] = provenance
        raw_rows.append(row)
    rows, manifest = build_dataset(raw_rows, dataset_namespace=namespace, as_of=cutoff)
    reconstructed = encode_dataset_snapshot(rows, manifest)
    # Compare canonical JSON rather than Python equality: True must not pass as
    # a numeric one, and a changed normalization may not silently rewrite history.
    if reconstructed != _json(dict(payload)):
        raise ValueError("snapshot_noncanonical_or_manifest_mismatch")
    return rows, manifest


async def persist_dataset_snapshot(
    session: AsyncSession, rows: Sequence[AdaptiveDatasetRow], manifest: DatasetManifest,
    *, observation_cutoff: datetime,
) -> None:
    cutoff = _aware(observation_cutoff)
    encoded = encode_dataset_snapshot(rows, manifest)
    # Validate all supplied labels and the declared manifest before insertion.
    restore_dataset_snapshot(json.loads(encoded), observation_cutoff=cutoff)
    await session.execute(text("""
        INSERT INTO research_dataset_snapshots(dataset_version,content_hash,
            format_version,row_count,observation_cutoff,payload)
        VALUES(:version,:hash,:format,:count,:cutoff,CAST(:payload AS JSONB))
        ON CONFLICT(dataset_version) DO NOTHING
    """), {"version": manifest.dataset_version, "hash": manifest.content_hash,
             "format": FORMAT_VERSION, "count": manifest.row_count,
             "cutoff": cutoff, "payload": encoded})
    # Concurrent identical retries preserve the first actual capture cutoff.
    # A conflicting existing row is never treated as a successful retry.
    loaded_rows, loaded_manifest = await load_dataset_snapshot(session, manifest.dataset_version)
    if encode_dataset_snapshot(loaded_rows, loaded_manifest) != encoded:
        raise ValueError("conflicting_immutable_dataset_snapshot")


async def load_dataset_snapshot(
    session: AsyncSession, dataset_version: str,
) -> tuple[tuple[AdaptiveDatasetRow, ...], DatasetManifest]:
    stored = (await session.execute(text("""
        SELECT s.content_hash,s.format_version,s.row_count,s.observation_cutoff,s.payload,
               d.content_hash AS dataset_content_hash,d.manifest AS dataset_manifest
        FROM research_dataset_snapshots s
        JOIN adaptive_dataset_versions d USING(dataset_version)
        WHERE s.dataset_version=:version
    """), {"version": dataset_version})).mappings().first()
    if stored is None:
        raise ValueError("research_dataset_snapshot_unavailable")
    if stored["format_version"] != FORMAT_VERSION:
        raise ValueError("research_dataset_snapshot_format_unsupported")
    rows, manifest = restore_dataset_snapshot(stored["payload"],
        observation_cutoff=stored["observation_cutoff"])
    if (manifest.dataset_version != dataset_version or manifest.content_hash != stored["content_hash"]
        or manifest.content_hash != stored["dataset_content_hash"] or manifest.row_count != stored["row_count"]
        or _json(manifest.to_dict()) != _json(stored["dataset_manifest"])):
        raise ValueError("research_dataset_snapshot_identity_mismatch")
    return rows, manifest
