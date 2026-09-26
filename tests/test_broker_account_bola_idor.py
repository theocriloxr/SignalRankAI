from __future__ import annotations

from pathlib import Path

import pytest

from services.account_policies import _owned_connection


class _NoRowResult:
    def scalar_one_or_none(self):
        return None


class _CaptureSession:
    def __init__(self):
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _NoRowResult()


@pytest.mark.asyncio
async def test_account_policy_owner_lookup_requires_user_and_connection_id():
    session = _CaptureSession()
    with pytest.raises(LookupError, match="broker_connection_not_found"):
        await _owned_connection(
            session,
            user_id=101,
            connection_id="connection-belongs-to-user-202",
        )

    assert len(session.statements) == 1
    sql = str(session.statements[0])
    assert "broker_connections.user_id" in sql
    assert "broker_connections.connection_id" in sql


def test_all_normal_account_policy_routes_bind_authenticated_canonical_user():
    source = Path("web/platform_api.py").read_text(encoding="utf-8")

    get_block = source[
        source.index('@router.get("/broker/connections/{connection_id}/policy")'):
        source.index('@router.put("/broker/connections/{connection_id}/policy")')
    ]
    assert "get_account_policy(int(user[\"id\"]), connection_id)" in get_block
    assert "reconciliation_snapshot(int(user[\"id\"]), connection_id)" in get_block

    update_block = source[
        source.index('@router.put("/broker/connections/{connection_id}/policy")'):
        source.index('@router.post("/admin/broker/connections/{connection_id}/prop-certification")')
    ]
    assert "configure_account_policy(" in update_block
    assert "int(user[\"id\"])," in update_block
    assert "connection_id," in update_block

    freeze_block = source[
        source.index('@router.post("/broker/connections/{connection_id}/safety-freeze")'):
        source.index('@router.post("/broker/connections/{connection_id}/verify")')
    ]
    assert "set_account_frozen(" in freeze_block
    assert "int(user[\"id\"])," in freeze_block
    assert "connection_id," in freeze_block


def test_connection_execution_toggle_is_object_level_authorized():
    source = Path("services/broker_connections.py").read_text(encoding="utf-8")
    block = source[
        source.index("async def set_execution_enabled"):
        source.index("async def set_default_connection")
    ]
    assert "BrokerConnection.connection_id == str(connection_id)" in block
    assert "BrokerConnection.user_id == int(user_id)" in block
    assert "TradingAccountPolicyRecord.connection_id == str(connection_id)" in block
    assert "TradingAccountPolicyRecord.user_id == int(user_id)" in block


def test_account_selected_execution_evidence_is_connection_scoped():
    source = Path("services/execution_evidence.py").read_text(encoding="utf-8")
    assert "MT5Execution.connection_id == str(connection_id)" in source
    assert "BrokerExecution.connection_id == str(connection_id)" in source
    assert "MT5Execution.user_id == int(user_id)" in source
    assert "BrokerExecution.user_id == int(user_id)" in source


def test_telegram_opaque_selection_revalidates_owner_and_connection():
    source = Path("services/broker_account_selection.py").read_text(encoding="utf-8")
    assert "account_selection_owner_mismatch" in source
    assert "BrokerConnection.connection_id == connection_id" in source
    assert "BrokerConnection.user_id == canonical_user_id" in source
    assert "TradingAccountPolicyRecord.user_id == canonical_user_id" in source
    assert "account_policy_changed" in source


def test_prop_certification_checks_privilege_before_target_lookup():
    source = Path("web/platform_api.py").read_text(encoding="utf-8")
    block = source[
        source.index('@router.post("/admin/broker/connections/{connection_id}/prop-certification")'):
        source.index('@router.post("/broker/connections/{connection_id}/safety-freeze")')
    ]
    privilege = block.index("_platform_operator_authority(user)")
    target_lookup = block.index("SELECT user_id FROM broker_connections")
    assert privilege < target_lookup
    assert 'raise HTTPException(status_code=403' in block
    assert "certified_by_user_id=int(user[\"id\"])" in block


def test_broker_router_never_infers_account_from_prior_execution():
    source = Path("services/broker_signal_router.py").read_text(encoding="utf-8")
    assert "explicit_broker_connection_required" in source
    assert "account_scope=account_scope" in source
    assert "connection_id=(" in source


def test_account_ledger_route_binds_authenticated_canonical_user():
    source = Path("web/platform_api.py").read_text(encoding="utf-8")
    block = source[
        source.index('@router.get("/broker/connections/{connection_id}/ledger")'):
        source.index('@router.put("/broker/connections/{connection_id}/policy")')
    ]
    assert "list_account_ledger(" in block
    assert 'int(user["id"])' in block
    assert "connection_id" in block

    ledger = Path("services/trading_account_ledger.py").read_text(encoding="utf-8")
    assert "BrokerConnection.user_id == int(user_id)" in ledger
    assert "BrokerConnection.connection_id == str(connection_id)" in ledger
    assert "TradingAccountLedgerEntry.user_id == int(user_id)" in ledger
    assert "TradingAccountLedgerEntry.connection_id == str(connection_id)" in ledger
