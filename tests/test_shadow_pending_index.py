"""Real PostgreSQL coverage for the concurrent index and tracked-state transitions."""
from importlib import import_module
import os
from uuid import uuid4

import psycopg2
from psycopg2 import sql
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_pending_shadow_index_preserves_results_and_avoids_history_scan():
    raw = os.getenv('DATABASE_URL','')
    if not raw:
        if os.getenv('SIGNALRANK_POSTGRES_INTEGRATION_REQUIRED') == '1':
            pytest.fail('isolated PostgreSQL required')
        pytest.skip('isolated PostgreSQL not configured')
    source = make_url(raw)
    assert os.getenv('APP_ENV') == 'test' and source.get_backend_name() == 'postgresql'
    assert source.host in {'127.0.0.1','localhost'} and 'test' in (source.database or '')
    name = 'signalrank_index_test_' + uuid4().hex[:12]
    admin = psycopg2.connect(source.set(drivername='postgresql',database='postgres').render_as_string(hide_password=False))
    admin.autocommit = True
    engine = None
    created = False
    try:
        with admin.cursor() as cursor:
            cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        created = True
        engine = create_engine(source.set(drivername='postgresql+psycopg2',database=name))
        with engine.connect() as connection:
            connection.execute(text('CREATE TABLE decision_log(id BIGINT PRIMARY KEY,decision TEXT,meta JSONB,created_at TIMESTAMP NOT NULL)'))
            connection.execute(text("""INSERT INTO decision_log SELECT n,'rejected',
                CASE WHEN n<=100 THEN '{"layer":"ml"}'::jsonb ELSE '{"layer":"ml","outcome_tracked_at":"2026-10-01"}'::jsonb END,
                TIMESTAMP '2026-10-01'+n*INTERVAL '1 second' FROM generate_series(1,100000) n"""))
            connection.commit()
            migration = import_module('db.migrations.versions.0054_shadow_pending_index')
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                migration.upgrade()  # adopt an already valid operational index safely
            connection.execute(text('ANALYZE decision_log'))
            query = "SELECT count(*),min(created_at),max(created_at) FROM decision_log WHERE decision='rejected' AND meta->>'layer'='ml' AND meta->>'outcome_tracked_at' IS NULL"
            result = connection.execute(text(query)).first()
            assert result[0] == 100
            plan = connection.execute(text('EXPLAIN (FORMAT JSON) '+query)).scalar_one()
            assert migration.INDEX in str(plan), plan
            connection.execute(text("UPDATE decision_log SET meta=meta||'{\"outcome_tracked_at\":\"2026-10-12\"}'::jsonb WHERE id=1"))
            assert connection.execute(text(query)).first()[0] == 99
            connection.commit()
            with Operations.context(MigrationContext.configure(connection)):
                migration.downgrade()
            assert connection.execute(text(query)).first()[0] == 99
            connection.commit()
            connection.execute(text("CREATE INDEX ix_decision_log_ml_pending_created ON decision_log(created_at) WHERE decision='rejected'"))
            connection.commit()
            with pytest.raises(DBAPIError,match='shadow_pending_index_invalid_or_definition_mismatch'):
                with Operations.context(MigrationContext.configure(connection)):
                    migration.upgrade()
            connection.rollback()
            assert connection.execute(text(query)).first()[0] == 99
    finally:
        if engine:
            engine.dispose()
        try:
            if created:
                with admin.cursor() as cursor:
                    cursor.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
        finally:
            admin.close()
