import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from db.models import Base
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.types import BigInteger

@compiles(BigInteger, 'sqlite')
def compile_biginteger_sqlite(type_, compiler, **kw):
    return 'INTEGER'

async def main():
    db_url = "sqlite+aiosqlite:///./.pytest-tmp/signalrank_test.db"
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS notification_events (
                notification_id VARCHAR(36) PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                event_type VARCHAR(96) NOT NULL,
                title VARCHAR(200) NOT NULL,
                body TEXT NOT NULL,
                severity VARCHAR(24) NOT NULL DEFAULT 'info',
                channel_data TEXT NOT NULL DEFAULT '{}',
                read_at TIMESTAMP WITHOUT TIME ZONE,
                created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
    print("Created tables")

if __name__ == "__main__":
    asyncio.run(main())
