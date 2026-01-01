from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def get_database_url() -> Optional[str]:
    url = os.getenv("DATABASE_URL")
    if not url:
        return None
    return url


def create_engine() -> Optional[AsyncEngine]:
    url = get_database_url()
    if not url:
        return None
    return create_async_engine(url, pool_pre_ping=True)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


ENGINE: Optional[AsyncEngine] = create_engine()
SessionLocal: Optional[async_sessionmaker[AsyncSession]] = (
    create_sessionmaker(ENGINE) if ENGINE is not None else None
)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")
    async with SessionLocal() as session:
        yield session
