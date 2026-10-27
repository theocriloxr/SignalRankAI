"""Exercise catalogue pagination against SQL, including the formerly starved tail."""
import sqlite3

import pytest

from data.database_universe import load_database_universe


class CatalogueSession:
    def __init__(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.executescript("""
            CREATE TABLE instruments (instrument_id INTEGER, canonical_symbol TEXT,
                asset_class TEXT, active BOOLEAN, tradable BOOLEAN, discovery_status TEXT);
            CREATE TABLE provider_instruments (canonical_instrument_id INTEGER,
                data_enabled BOOLEAN, market_status TEXT);
            CREATE TABLE instrument_certifications (instrument_id INTEGER);
        """)
        self.connection.executemany("INSERT INTO instruments VALUES (?, ?, ?, 1, 1, ?)",
            [(i, f"ASSET{i:04}", "crypto" if i % 2 else "equity", "analysis_ready") for i in range(2501)])
        self.connection.executemany("INSERT INTO provider_instruments VALUES (?, 1, 'active')",
            [(i,) for i in range(2501)] * 2)  # duplicate providers must not duplicate symbols
        self.queries = []

    async def execute(self, statement, params):
        self.queries.append(dict(params))
        rows = self.connection.execute(str(statement), params).fetchall()
        return type("Result", (), {"all": lambda _: rows})()


@pytest.mark.asyncio
async def test_complete_universe_includes_tail_beyond_old_2000_cap():
    session = CatalogueSession()
    try:
        symbols = await load_database_universe(session, page_size=200)
        assert symbols == [f"ASSET{i:04}" for i in range(2501)]
        assert len(session.queries) == 13
        assert all(q["limit"] == 200 for q in session.queries)
        assert session.queries[-1]["after_symbol"] == "ASSET2399"
    finally:
        session.connection.close()


@pytest.mark.asyncio
async def test_explicit_limit_and_class_aliases_preserve_eligibility():
    session = CatalogueSession()
    try:
        session.connection.execute("UPDATE instruments SET tradable=0 WHERE instrument_id=0")
        session.connection.execute("UPDATE provider_instruments SET data_enabled=0 WHERE canonical_instrument_id=2")
        symbols = await load_database_universe(session, asset_classes=["stocks"], limit=253, page_size=100)
        assert symbols == [f"ASSET{i:04}" for i in range(4,510,2)]
        assert [q["limit"] for q in session.queries] == [100,100,53]
        assert all(q["asset_class_0"] == "equity" for q in session.queries)
        assert await load_database_universe(session, asset_classes=["equity') OR 1=1 --"]) == []
    finally:
        session.connection.close()
