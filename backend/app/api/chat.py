from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, get_current_user, require_thread_access
from app.chat.messages import (
    ChatMessageResponse,
    ChatStreamRequest,
    CreateThreadRequest,
    ThreadResponse,
)
from app.chat.orchestrator import run_chat_turn
from app.chat.streaming import build_stream_response
from app.database.chats import (
    create_thread,
    get_thread,
    list_messages_for_thread,
    list_threads_for_user,
)
from app.database.models import ChatThread
from app.database.session import get_db_session

router = APIRouter(prefix="/chat", tags=["chat"])


async def _load_owned_thread(
    session: AsyncSession, thread_id: UUID, current_user: CurrentUser
) -> ChatThread:
    thread = await get_thread(session, thread_id=thread_id)
    if thread is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found"
        )
    await require_thread_access(current_user, thread.user_id)
    return thread


@router.post("/threads", status_code=status.HTTP_201_CREATED)
async def create_thread_route(
    body: CreateThreadRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ThreadResponse:
    thread = await create_thread(
        session, user_id=current_user.user_id, title=body.title
    )
    return ThreadResponse.model_validate(thread)


@router.get("/threads")
async def list_threads_route(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[ThreadResponse]:
    threads = await list_threads_for_user(session, user_id=current_user.user_id)
    return [ThreadResponse.model_validate(thread) for thread in threads]


@router.get("/threads/{thread_id}/messages")
async def get_thread_messages(
    thread_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[ChatMessageResponse]:
    await _load_owned_thread(session, thread_id, current_user)
    messages = await list_messages_for_thread(session, thread_id=thread_id)
    return [ChatMessageResponse.model_validate(message) for message in messages]


@router.post("/stream")
async def stream_chat(
    body: ChatStreamRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StreamingResponse:
    await _load_owned_thread(session, body.thread_id, current_user)
    generator = run_chat_turn(
        session,
        body.thread_id,
        body.messages,
        user_id=current_user.user_id,
        agent=request.app.state.document_agent,
        retriever=request.app.state.document_retriever,
    )
    return build_stream_response(generator)
