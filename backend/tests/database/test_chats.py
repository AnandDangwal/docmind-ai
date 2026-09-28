from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.chats import (
    create_message,
    create_thread,
    get_thread,
    list_messages_for_thread,
    list_threads_for_user,
)
from app.database.models import MessageRole, User
from app.database.session import AsyncSessionLocal

pytestmark = pytest.mark.integration


@asynccontextmanager
async def _seeded_session() -> AsyncIterator[tuple[AsyncSession, uuid.UUID]]:
    async with AsyncSessionLocal() as db_session:
        user = User(id=uuid.uuid4())
        db_session.add(user)
        await db_session.flush()
        try:
            yield db_session, user.id
        finally:
            await db_session.rollback()


def _run_seeded(test_body: Callable[[AsyncSession, uuid.UUID], Awaitable[None]]) -> None:
    async def runner() -> None:
        async with _seeded_session() as (db_session, user_id):
            await test_body(db_session, user_id)

    asyncio.run(runner())


def test_thread_and_message_round_trip() -> None:
    async def body(db_session: AsyncSession, user_id: uuid.UUID) -> None:
        thread = await create_thread(db_session, user_id=user_id, title="Q3 review")
        assert thread.id is not None

        threads = await list_threads_for_user(db_session, user_id=user_id)
        assert [t.id for t in threads] == [thread.id]

        fetched = await get_thread(db_session, thread_id=thread.id)
        assert fetched is not None
        assert fetched.id == thread.id

        user_message = await create_message(
            db_session,
            thread_id=thread.id,
            role=MessageRole.user,
            parts=[{"type": "text", "text": "hello"}],
        )
        assistant_message = await create_message(
            db_session,
            thread_id=thread.id,
            role=MessageRole.assistant,
            parts=[{"type": "text", "text": "hi there"}],
        )

        messages = await list_messages_for_thread(db_session, thread_id=thread.id)
        assert [m.id for m in messages] == [user_message.id, assistant_message.id]

    _run_seeded(body)


def test_get_thread_returns_none_when_missing() -> None:
    async def body(db_session: AsyncSession, _user_id: uuid.UUID) -> None:
        result = await get_thread(db_session, thread_id=uuid.uuid4())
        assert result is None

    _run_seeded(body)
