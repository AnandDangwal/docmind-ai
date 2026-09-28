from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ChatMessage, ChatThread, MessageRole


async def create_thread(session: AsyncSession, *, user_id: UUID, title: str | None) -> ChatThread:
    thread = ChatThread(user_id=user_id, title=title)
    session.add(thread)
    await session.flush()
    return thread


async def list_threads_for_user(session: AsyncSession, *, user_id: UUID) -> list[ChatThread]:
    result = await session.execute(
        select(ChatThread).where(ChatThread.user_id == user_id).order_by(ChatThread.created_at.desc())
    )
    return list(result.scalars().all())


async def get_thread(session: AsyncSession, *, thread_id: UUID) -> ChatThread | None:
    return await session.get(ChatThread, thread_id)


async def list_messages_for_thread(session: AsyncSession, *, thread_id: UUID) -> list[ChatMessage]:
    result = await session.execute(
        select(ChatMessage).where(ChatMessage.thread_id == thread_id).order_by(ChatMessage.created_at)
    )
    return list(result.scalars().all())


async def create_message(
    session: AsyncSession, *, thread_id: UUID, role: MessageRole, parts: list[dict]
) -> ChatMessage:
    message = ChatMessage(thread_id=thread_id, role=role, parts=parts)
    session.add(message)
    await session.flush()
    return message
