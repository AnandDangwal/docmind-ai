from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.messages import UIMessage, assistant_text_to_parts, ui_message_to_parts
from app.chat.streaming import stub_event_stream
from app.database.chats import create_message
from app.database.models import MessageRole
from app.database.session import AsyncSessionLocal

STUB_ASSISTANT_TEXT = (
    "This is a stub reply. Ingestion and grounded retrieval are not wired up yet, "
    "so I can't answer questions about filings at this point."
)


async def run_chat_turn(
    session: AsyncSession, thread_id: UUID, messages: list[UIMessage]
) -> AsyncIterator[bytes]:
    if messages and messages[-1].role == "user":
        await create_message(
            session,
            thread_id=thread_id,
            role=MessageRole.user,
            parts=ui_message_to_parts(messages[-1]),
        )

    async def on_complete(text: str) -> None:
        # The request-scoped `session` is committed and closed by the time the
        # StreamingResponse body finishes sending, so persist with a fresh session.
        async with AsyncSessionLocal() as assistant_session:
            await create_message(
                assistant_session,
                thread_id=thread_id,
                role=MessageRole.assistant,
                parts=assistant_text_to_parts(text),
            )
            await assistant_session.commit()

    return stub_event_stream(STUB_ASSISTANT_TEXT, on_complete=on_complete)
