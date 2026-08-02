from __future__ import annotations

from pathlib import Path

from core.durable_event_stream import DurableEventStream, EventEnvelope
from data.provider_contracts import (
    AssetClass,
    Capability,
    CertificationState,
    InstrumentKind,
    ProviderCapabilityManifest,
)

ROOT = Path(__file__).resolve().parents[1]


def test_performance_reconciliation_is_isolated_resumable_and_diagnostic() -> None:
    source = (ROOT / "services" / "performance_ledger.py").read_text("utf-8")
    sweep = source[source.index("async def reconcile_all_performance_ledgers"):source.index("async def performance_ledger_health")]
    assert "async with session.begin_nested()" in sweep
    assert "User.id > int(after_user_id)" in sweep
    assert "telegram_user_id=%s internal_user_id=%s" in sweep
    assert "failed_users_by_reason" in sweep
    assert "all_examined_users_failed=true" in sweep
    assert "performance_reconciliation:cursor" in sweep
    assert "performance_reconciliation:retry" in sweep
    assert "performance_reconciliation:dlq" in sweep
    assert "persist_performance_reconciliation_result" in source


def test_finalized_policy_migration_is_audited_and_human_corrections_survive() -> None:
    source = (ROOT / "services" / "performance_ledger.py").read_text("utf-8")
    reconcile = source[source.index("async def reconcile_user_performance_ledger"):source.index("class PerformanceMetrics")]
    assert '_SYSTEM_CORRECTION_ACTOR = "system:performance-policy-migration"' in source
    assert "PerformanceCorrectionAudit(" in reconcile
    assert "human_corrected" in reconcile
    assert "trg_performance_ledger_finality" in reconcile
    assert "dry_run" in reconcile
    assert "getattr(delivery, \"delivered_at_utc\", None)" in reconcile
    assert 'raise ValueError("missing_delivery_timestamp")' in reconcile
    assert "seen_signal_deliveries" in reconcile


def test_worker_commits_verified_repairs_before_failing_batch_certification() -> None:
    source = (ROOT / "worker" / "worker.py").read_text("utf-8")
    block = source[source.index("performance_result = await reconcile_all_performance_ledgers"):source.index("await run_with_db_retry", source.index("performance_result = await reconcile_all_performance_ledgers"))]
    assert block.index("await session.commit()") < block.index("persist_performance_reconciliation_result")
    assert block.index("persist_performance_reconciliation_result") < block.index("performance_result.certification_failed")


def test_owner_rebuild_and_audit_commands_are_registered() -> None:
    owner = (ROOT / "signalrank_telegram" / "owner_commands.py").read_text("utf-8")
    bot = (ROOT / "signalrank_telegram" / "bot.py").read_text("utf-8")
    assert "async def performance_rebuild_command" in owner
    assert "async def performance_audit_command" in owner
    assert 'CommandHandler("performance_rebuild"' in bot
    assert 'CommandHandler("performance_audit"' in bot



def test_performance_health_uses_distinct_delivery_scope_and_mismatch_gate() -> None:
    source = (ROOT / "services" / "performance_ledger.py").read_text("utf-8")
    health = source[source.index("async def performance_ledger_health"):source.index("async def get_user_performance_report")]
    assert "select(SignalDelivery.user_id, SignalDelivery.signal_id)" in health
    assert ".distinct()" in health
    assert "outcome_to_ledger_mismatch" in health
    assert "await session.stream(audit_stmt)" in health
    assert "mismatch_count == 0" in health

def test_partitioned_event_envelope_is_deterministic_and_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("DURABLE_EVENT_STREAM_ENABLED", raising=False)
    stream = DurableEventStream(partitions=32)
    assert stream.enabled is False
    assert stream.partition_for("account:123") == stream.partition_for("account:123")
    assert stream.stream_name("account:123").startswith("signalrankai:events:v2:p")
    envelope = EventEnvelope(
        event_type="SignalDelivered",
        partition_key="user:42",
        user_id="42",
        signal_id="sig-1",
        payload={"delivery_id": 7},
    )
    fields = envelope.as_stream_fields()
    assert fields["event_type"] == "SignalDelivered"
    assert '"delivery_id":7' in fields["payload"]


def test_provider_manifest_separates_declared_from_certified_capability() -> None:
    manifest = ProviderCapabilityManifest(
        provider="example",
        capabilities=frozenset({Capability.LIVE_QUOTES, Capability.EXECUTION}),
        asset_classes=frozenset({AssetClass.CRYPTO}),
        instrument_kinds=frozenset({InstrumentKind.SPOT}),
        certification={
            Capability.LIVE_QUOTES: CertificationState.PRODUCTION_CERTIFIED,
            Capability.EXECUTION: CertificationState.DECLARED,
        },
    )
    assert manifest.supports(Capability.EXECUTION)
    assert not manifest.supports(Capability.EXECUTION, certified_only=True)
    assert manifest.supports(Capability.LIVE_QUOTES, certified_only=True)


def test_release_identity_is_v1368() -> None:
    version = (ROOT / "core" / "version.py").read_text("utf-8")
    assert 'CODE_VERSION = "1.3.6.8"' in version
    assert "performance-ledger-scale-hotfix" in version
