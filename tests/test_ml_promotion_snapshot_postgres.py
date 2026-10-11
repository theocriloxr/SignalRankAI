"""Actual registry transactions with synthetic model/qualification fixtures.

These tests verify review/write identity and row ownership, not model quality,
forward performance, authorization issuance or production promotion acceptance.
"""
from contextlib import asynccontextmanager
from datetime import datetime
from importlib import import_module
import asyncio
import base64
import hashlib
import json
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.models import MLModelArtifact
from ml.artifact_store import artifact_review_hash, promote_active_candidate_artifact
from ml.model_registry import compute_feature_schema_hash


@pytest_asyncio.fixture
async def registry(monkeypatch):
    raw = os.getenv("DATABASE_URL", "")
    if not raw:
        if os.getenv("SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED") == "1":
            pytest.fail("isolated PostgreSQL required")
        pytest.skip("isolated PostgreSQL not configured")
    url = make_url(raw)
    assert url.get_backend_name() == "postgresql" and url.host in {"127.0.0.1", "localhost"}
    assert os.getenv("APP_ENV") == "test" and "test" in (url.database or "")
    schema = "ml_registry_test_" + uuid4().hex[:16]
    admin = create_async_engine(url.set(drivername="postgresql+asyncpg"))
    engine = create_async_engine(url.set(drivername="postgresql+asyncpg"),
        connect_args={"server_settings": {"search_path": schema}})
    try:
        async with admin.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        async with engine.begin() as connection:
            def migrate(sync_connection):
                from alembic.migration import MigrationContext
                from alembic.operations import Operations
                with Operations.context(MigrationContext.configure(sync_connection)):
                    import_module("db.migrations.versions.0033_ml_learning_runtime").upgrade()
            await connection.run_sync(migrate)
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        @asynccontextmanager
        async def owned_session(**_kwargs):
            async with sessions() as session:
                yield session
        monkeypatch.setattr("db.session.get_session", owned_session)
        yield sessions
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin.dispose()


def payload(name, parent=""):
    # Real integrity checks operate on deterministic bytes; no booster is loaded.
    model = ("synthetic-model:" + name).encode()
    return {"version": name, "schema_version": 4, "feature_cols": ["synthetic_feature"],
        "feature_schema_hash_sha256": compute_feature_schema_hash(["synthetic_feature"]),
        "model_bytes_b64": base64.b64encode(model).decode(),
        "artifact_hash_sha256": hashlib.sha256(model).hexdigest(),
        "parent_model_hash_sha256": parent,
        "training_meta": {"offline_quality_gate": {"passed": True},
            "lineage": {"eligible": True}, "candidate_forward_gate": {"required": True},
            "champion_comparison": {"enabled": True, "reason": "noninferior" if parent else "no_existing_champion"}}}


async def replace(sessions, slot, value, *, registry_hash=None):
    async with sessions() as session:
        await session.execute(update(MLModelArtifact).where(MLModelArtifact.model_name == slot,
            MLModelArtifact.is_active.is_(True)).values(is_active=False))
        row = MLModelArtifact(model_name=slot, model_version=value["version"],
            feature_schema_version="4", artifact_hash_sha256=registry_hash or value["artifact_hash_sha256"],
            payload=value, metrics={"calibration": {"validated": True}}, source_counts={},
            is_active=True, trained_at=datetime(2026, 10, 1))
        session.add(row)
        await session.commit()
        return row.id


async def active(sessions, slot):
    async with sessions() as session:
        return (await session.execute(select(MLModelArtifact).where(
            MLModelArtifact.model_name == slot, MLModelArtifact.is_active.is_(True)))).scalars().one_or_none()


async def reviewed_pair(sessions):
    primary = payload("primary")
    primary_id = await replace(sessions, "primary", primary)
    candidate = payload("candidate", primary["artifact_hash_sha256"])
    candidate_id = await replace(sessions, "candidate", candidate)
    return {"expected_artifact_hash_sha256": candidate["artifact_hash_sha256"],
        "expected_candidate_id": candidate_id, "expected_primary_id": primary_id,
        "expected_primary_hash_sha256": primary["artifact_hash_sha256"],
        "expected_candidate_review_hash": artifact_review_hash(await active(sessions, "candidate")),
        "expected_primary_review_hash": artifact_review_hash(await active(sessions, "primary"))}


@pytest.mark.asyncio
@pytest.mark.parametrize("slot", ["primary", "candidate"])
@pytest.mark.parametrize("in_place", [False, True])
async def test_replacement_during_forward_review_cannot_borrow_old_approval(registry, monkeypatch, slot, in_place):
    import ml.candidate_forward as forward

    await reviewed_pair(registry)
    replacement_id = None

    async def synthetic_evidence(_candidate):
        nonlocal replacement_id
        previous = await active(registry, slot)
        # Identical bytes/hash, but a new row and revised qualification metadata.
        changed = json.loads(json.dumps(previous.payload))
        changed["training_meta"]["review_context"] = "successor-not-reviewed"
        if in_place:
            async with registry() as session:
                await session.execute(update(MLModelArtifact).where(MLModelArtifact.id == previous.id).values(payload=changed))
                await session.commit()
            replacement_id = previous.id
        else:
            replacement_id = await replace(registry, slot, changed)
        return {"eligible": True, "status": "eligible", "scope": "synthetic_race_fixture"}

    monkeypatch.setattr(forward, "evaluate_candidate_forward_evidence", synthetic_evidence)
    result = await forward.promote_candidate_from_forward_proof(authorization_id="synthetic-operator-approval")
    assert result["ok"] is False and result["reason"] == "durable_promotion_failed"
    assert result["promotion"]["reason"] == slot + "_snapshot_changed"
    assert (await active(registry, slot)).id == replacement_id
    assert (await active(registry, "primary")).model_version == "primary"


@pytest.mark.asyncio
async def test_new_champion_after_review_rejects_old_parent(registry):
    expected = await reviewed_pair(registry)
    successor_id = await replace(registry, "primary", payload("successor"))
    result = await promote_active_candidate_artifact(**expected)
    assert result == {"ok": False, "reason": "primary_snapshot_changed"}
    assert (await active(registry, "primary")).id == successor_id


@pytest.mark.asyncio
async def test_registry_column_cannot_claim_another_valid_payload_hash(registry):
    expected = await reviewed_pair(registry)
    primary = await active(registry, "primary")
    wrong = payload("different-bytes", primary.artifact_hash_sha256)
    expected["expected_candidate_id"] = await replace(registry, "candidate", wrong,
        registry_hash=expected["expected_artifact_hash_sha256"])
    expected["expected_candidate_review_hash"] = artifact_review_hash(await active(registry, "candidate"))
    result = await promote_active_candidate_artifact(**expected)
    assert not result["ok"] and result["reason"] == "candidate_integrity_failed"
    assert result["payload_identity_matches_registry"] is False
    assert (await active(registry, "primary")).id == expected["expected_primary_id"]


@pytest.mark.asyncio
async def test_concurrent_review_commits_replace_the_champion_once(registry):
    expected = await reviewed_pair(registry)
    results = await asyncio.wait_for(asyncio.gather(
        promote_active_candidate_artifact(**expected), promote_active_candidate_artifact(**expected)), timeout=10)
    assert sorted(result["reason"] for result in results) == ["candidate_promoted", "primary_snapshot_changed"]
    assert sum(result["ok"] for result in results) == 1
    primary = await active(registry, "primary")
    assert primary.artifact_hash_sha256 == expected["expected_artifact_hash_sha256"]
    async with registry() as session:
        rows = (await session.execute(select(MLModelArtifact).where(MLModelArtifact.model_name == "primary"))).scalars().all()
        assert len(rows) == 2 and sum(row.is_active for row in rows) == 1


@pytest.mark.asyncio
async def test_initial_promotion_requires_no_parent_and_preserves_candidate(registry):
    candidate = payload("initial")
    candidate_id = await replace(registry, "candidate", candidate)
    result = await promote_active_candidate_artifact(expected_candidate_id=candidate_id,
        expected_artifact_hash_sha256=candidate["artifact_hash_sha256"],
        expected_primary_id=None, expected_primary_hash_sha256="",
        expected_candidate_review_hash=artifact_review_hash(await active(registry, "candidate")),
        expected_primary_review_hash="")
    assert result["ok"] and result["reason"] == "candidate_promoted"
    assert (await active(registry, "primary")).artifact_hash_sha256 == candidate["artifact_hash_sha256"]
    assert (await active(registry, "candidate")).id == candidate_id


@pytest.mark.asyncio
async def test_parent_mismatch_with_valid_review_identity_fails_before_write(registry):
    expected = await reviewed_pair(registry)
    orphan = payload("orphan", "f" * 64)
    expected.update(expected_artifact_hash_sha256=orphan["artifact_hash_sha256"],
        expected_candidate_id=await replace(registry, "candidate", orphan))
    expected["expected_candidate_review_hash"] = artifact_review_hash(await active(registry, "candidate"))
    assert await promote_active_candidate_artifact(**expected) == {
        "ok": False, "reason": "candidate_parent_champion_changed"}
    assert (await active(registry, "primary")).id == expected["expected_primary_id"]
