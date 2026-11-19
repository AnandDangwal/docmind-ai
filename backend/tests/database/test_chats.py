from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.chats import (
    create_citations,
    create_message,
    create_thread,
    delete_thread,
    get_thread,
    list_messages_for_thread,
    list_threads_for_user,
    replace_user_turn,
)
from app.database.models import (
    ChatMessage,
    ChatThread,
    DocumentChunk,
    MessageCitation,
    MessageRole,
    User,
)
from app.database.session import AsyncSessionLocal

pytestmark = pytest.mark.integration


def test_first_chat_provisions_user_and_second_chat_reuses_it() -> None:
    async def run():
        async with AsyncSessionLocal() as session:
            user_id = uuid.uuid4()
            try:
                assert await session.get(User, user_id) is None
                first = await create_thread(session, user_id=user_id, title=None)
                second = await create_thread(session, user_id=user_id, title=None)
                assert await session.get(User, user_id) is not None
                threads = await list_threads_for_user(session, user_id=user_id)
                assert {thread.id for thread in threads} == {first.id, second.id}
                assert first.user_id == second.user_id == user_id
            finally:
                await session.rollback()

    asyncio.run(run())


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


def _run_seeded(
    test_body: Callable[[AsyncSession, uuid.UUID], Awaitable[None]],
) -> None:
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


def test_delete_thread_cascades_to_messages() -> None:
    async def body(db_session: AsyncSession, user_id: uuid.UUID) -> None:
        thread = await create_thread(db_session, user_id=user_id, title="Delete me")
        message = await create_message(
            db_session,
            thread_id=thread.id,
            role=MessageRole.user,
            parts=[{"type": "text", "text": "Goodbye"}],
        )

        await delete_thread(db_session, thread_id=thread.id)
        db_session.expire_all()

        assert await db_session.get(ChatThread, thread.id) is None
        assert await db_session.get(ChatMessage, message.id) is None

    _run_seeded(body)


def test_citation_round_trip_and_atomic_rollback() -> None:
    async def body(db_session: AsyncSession, user_id: uuid.UUID) -> None:
        chunk = (await db_session.execute(select(DocumentChunk).limit(1))).scalar_one()
        thread = await create_thread(
            db_session, user_id=user_id, title="Grounding test"
        )
        message_id = uuid.uuid4()
        part = {
            "type": "data-citation",
            "id": "C1",
            "data": {
                "citationId": "C1",
                "chunkId": str(chunk.id),
                "excerpt": chunk.content,
            },
        }
        message = await create_message(
            db_session,
            thread_id=thread.id,
            role=MessageRole.assistant,
            parts=[{"type": "text", "text": "Claim. [C1]"}, part],
            message_id=message_id,
        )
        await create_citations(db_session, message_id=message.id, parts=[part])
        citation = (
            await db_session.execute(
                select(MessageCitation).where(MessageCitation.message_id == message.id)
            )
        ).scalar_one()
        assert citation.chunk_id == chunk.id
        assert citation.excerpt == chunk.content
        await db_session.refresh(message)
        assert message.parts[1] == part

        failed_id = uuid.uuid4()
        with pytest.raises(RuntimeError):
            async with db_session.begin_nested():
                await create_message(
                    db_session,
                    thread_id=thread.id,
                    role=MessageRole.assistant,
                    parts=[],
                    message_id=failed_id,
                )
                await create_citations(db_session, message_id=failed_id, parts=[part])
                raise RuntimeError("failed turn")
        assert await db_session.get(ChatMessage, failed_id) is None
        assert (
            not (
                await db_session.execute(
                    select(MessageCitation).where(
                        MessageCitation.message_id == failed_id
                    )
                )
            )
            .scalars()
            .all()
        )

    _run_seeded(body)


def test_replace_user_turn_preserves_history_and_deletes_later_citations() -> None:
    async def body(db_session: AsyncSession, user_id: uuid.UUID) -> None:
        chunk = (await db_session.execute(select(DocumentChunk).limit(1))).scalar_one()
        thread = await create_thread(db_session, user_id=user_id, title="Original")
        earlier = await create_message(
            db_session,
            thread_id=thread.id,
            role=MessageRole.user,
            parts=[{"type": "text", "text": "Earlier"}],
        )
        target = await create_message(
            db_session,
            thread_id=thread.id,
            role=MessageRole.user,
            parts=[{"type": "text", "text": "Original question"}],
        )
        citation_part = {
            "type": "data-citation",
            "id": "C1",
            "data": {
                "citationId": "C1",
                "chunkId": str(chunk.id),
                "excerpt": chunk.content,
            },
        }
        answer = await create_message(
            db_session,
            thread_id=thread.id,
            role=MessageRole.assistant,
            parts=[{"type": "text", "text": "Answer [C1]"}, citation_part],
        )
        await create_citations(db_session, message_id=answer.id, parts=[citation_part])

        history = await replace_user_turn(
            db_session,
            thread_id=thread.id,
            message_id=target.id,
            parts=[{"type": "text", "text": "Edited question"}],
            title="Edited question",
        )
        await db_session.flush()

        assert [message.id for message in history] == [earlier.id]
        assert target.parts == [{"type": "text", "text": "Edited question"}]
        assert await db_session.get(ChatMessage, answer.id) is None
        assert (
            not (
                await db_session.execute(
                    select(MessageCitation).where(
                        MessageCitation.message_id == answer.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert thread.title == "Original"

    _run_seeded(body)


def test_replacing_first_user_turn_updates_title() -> None:
    async def body(db_session: AsyncSession, user_id: uuid.UUID) -> None:
        thread = await create_thread(db_session, user_id=user_id, title="Original")
        target = await create_message(
            db_session,
            thread_id=thread.id,
            role=MessageRole.user,
            parts=[{"type": "text", "text": "Original question"}],
        )

        await replace_user_turn(
            db_session,
            thread_id=thread.id,
            message_id=target.id,
            parts=[{"type": "text", "text": "Edited first question"}],
            title="Edited first question",
        )

        assert thread.title == "Edited first question"

    _run_seeded(body)
