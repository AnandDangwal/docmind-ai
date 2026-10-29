from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    ChatMessage,
    ChatThread,
    MessageCitation,
    MessageRole,
    User,
)


async def create_thread(
    session: AsyncSession, *, user_id: UUID, title: str | None
) -> ChatThread:
    # Supabase Auth owns signup; provision the app row using the verified caller ID.
    await session.execute(
        insert(User).values(id=user_id).on_conflict_do_nothing(index_elements=[User.id])
    )
    thread = ChatThread(user_id=user_id, title=title)
    session.add(thread)
    await session.flush()
    return thread


async def list_threads_for_user(
    session: AsyncSession, *, user_id: UUID
) -> list[ChatThread]:
    result = await session.execute(
        select(ChatThread)
        .where(ChatThread.user_id == user_id)
        .order_by(ChatThread.created_at.desc())
    )
    return list(result.scalars().all())


async def get_thread(session: AsyncSession, *, thread_id: UUID) -> ChatThread | None:
    return await session.get(ChatThread, thread_id)


async def list_messages_for_thread(
    session: AsyncSession, *, thread_id: UUID
) -> list[ChatMessage]:
    result = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.thread_id == thread_id)
        .order_by(ChatMessage.created_at)
    )
    return list(result.scalars().all())


async def create_message(
    session: AsyncSession,
    *,
    thread_id: UUID,
    role: MessageRole,
    parts: list[dict],
    message_id: UUID | None = None,
) -> ChatMessage:
    message = ChatMessage(thread_id=thread_id, role=role, parts=parts)
    if message_id is not None:
        message.id = message_id
    session.add(message)
    await session.flush()
    return message


async def create_citations(
    session: AsyncSession, *, message_id: UUID, parts: list[dict]
) -> None:
    for part in parts:
        data = part["data"]
        session.add(
            MessageCitation(
                message_id=message_id,
                chunk_id=UUID(data["chunkId"]),
                excerpt=data["excerpt"],
            )
        )
    await session.flush()
