"""Broker listings must survive real SQLAlchemy rollback and session closure."""
from contextlib import asynccontextmanager
from datetime import datetime
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.models import BrokerConnection
from services import broker_connections, mt5_client
import db.session


@pytest.mark.asyncio
@pytest.mark.parametrize("owner", [101, 202, 303])
@pytest.mark.parametrize("operation", ["list", "default", "explicit", "execution_enabled", "wrong_owner", "wrong_platform"])
async def test_listing_materializes_owned_public_rows_before_rollback(monkeypatch, owner, operation):
    engine = create_engine("sqlite://")
    BrokerConnection.__table__.create(engine)
    try:
        with Session(engine, expire_on_commit=False) as seed:
            for connection_id, user_id, preferred, created in (
                ("owner-secondary", 101, False, datetime(2026, 1, 1)),
                ("owner-default", 101, True, datetime(2026, 1, 2)),
                ("other-owner", 202, True, datetime(2026, 1, 3)),
            ):
                seed.add(BrokerConnection(
                    connection_id=connection_id, user_id=user_id, platform="mt5",
                    connector="metaapi", account_ref="12345678", environment="demo",
                    auth_mode="encrypted_password", status="credentials_saved",
                    secret_encrypted="private-ciphertext", credential_key_id="private-key-id",
                    permissions={"trade": False}, capabilities={}, meta={},
                    execution_enabled=False, is_default=preferred, created_at=created,
                ))
            seed.commit()

        @asynccontextmanager
        async def get_session(**kwargs):
            with Session(engine, expire_on_commit=False) as session:
                class AsyncAdapter:
                    async def execute(self, statement):
                        return session.execute(statement)

                    async def rollback(self):
                        session.rollback()

                yield AsyncAdapter()

        monkeypatch.setattr(broker_connections, "get_session", get_session)
        monkeypatch.setattr(db.session, "get_session", get_session)
        expected = {101: ["owner-default", "owner-secondary"], 202: ["other-owner"], 303: []}
        if operation == "list":
            result = await broker_connections.list_connections(owner)
            ids = expected[owner]
        else:
            options = {
                "default": {},
                "explicit": {"connection_id": "owner-secondary"},
                "execution_enabled": {"require_execution_enabled": True},
                "wrong_owner": {"connection_id": "other-owner"},
                "wrong_platform": {"platform": "mt4"},
            }[operation]
            snapshot = await mt5_client.get_platform_metatrader_connection(owner, **options)
            result = [snapshot] if snapshot else []
            ids = expected[owner][:1] if operation == "default" else []
            if operation == "explicit" and owner == 101:
                ids = ["owner-secondary"]
            if operation == "wrong_owner" and owner == 202:
                ids = ["other-owner"]
        assert [row["connection_id"] for row in result] == ids
        serialized = json.dumps(result, default=str)
        assert "private-ciphertext" not in serialized
        assert "private-key-id" not in serialized
        assert "12345678" not in serialized
        for row in result:
            assert row["account_ref_masked"] == "****5678"
            assert row["account_classification"] == "DEMO"
            assert row["status"] == "credentials_saved"
            assert row["credential_encrypted"] is True
            assert row["execution_enabled"] is False
    finally:
        engine.dispose()
