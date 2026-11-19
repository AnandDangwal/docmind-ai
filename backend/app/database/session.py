from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator

from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

if sys.platform == "win32":
    # psycopg's async driver requires the selector loop; Windows defaults to
    # the proactor loop, which raises InterfaceError on connect.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def normalize_database_url(raw_url: str) -> str:
    url = make_url(raw_url)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    return url.render_as_string(hide_password=False)


engine = create_async_engine(
    normalize_database_url(settings.database_url.get_secret_value()),
    pool_pre_ping=True,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
        await session.commit()
