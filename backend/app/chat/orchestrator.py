from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import asdict
from uuid import UUID, uuid4

import httpx
import structlog
from pydantic_ai import Agent
from pydantic_ai.exceptions import AgentRunError, ModelHTTPError
from pydantic_ai.usage import UsageLimits
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.deps import DocumentAgentDeps
from app.assistant.outputs import GroundedAnswer
from app.chat.messages import (
    UIMessage,
    assistant_text_to_parts,
    stored_messages_to_history,
    text_from_parts,
    ui_message_to_parts,
)
from app.chat.streaming import (
    answer_event_stream,
    done_event,
    error_event,
    sse_event,
    status_event,
)
from app.database.chats import (
    create_citations,
    create_message,
    list_messages_for_thread,
)
from app.database.models import MessageRole
from app.database.session import AsyncSessionLocal
from app.grounding.validator import (
    GroundingError,
    citation_parts,
    safe_status_answer,
    validate_answer,
)
from app.retrieval.retriever import DocumentRetriever

logger = structlog.get_logger(__name__)

QUESTION_FAILURE = (
    "The question could not be saved, so the assistant did not start. Please try again."
)
RETRIEVAL_FAILURE = (
    "The filings could not be searched right now. Check the service connection and try again."
)
ANALYSIS_FAILURE = (
    "The filings were found, but the assistant could not analyze them. Please try again."
)
GROUNDING_FAILURE = (
    "The draft answer could not be verified against the filings, so it was withheld."
)


async def run_chat_turn(
    session: AsyncSession,
    thread_id: UUID,
    messages: list[UIMessage],
    *,
    user_id: UUID,
    agent: Agent[DocumentAgentDeps, GroundedAnswer],
    retriever: DocumentRetriever,
) -> AsyncIterator[bytes]:
    message_id = uuid4()
    yield sse_event({"type": "start", "messageId": str(message_id)})
    yield status_event("searching")

    question = text_from_parts(ui_message_to_parts(messages[-1])).strip()
    try:
        history = stored_messages_to_history(
            await list_messages_for_thread(session, thread_id=thread_id)
        )
        await create_message(
            session,
            thread_id=thread_id,
            role=MessageRole.user,
            parts=assistant_text_to_parts(question),
        )
        # Finish the question transaction before any external generation work.
        await session.commit()
    except SQLAlchemyError as exc:
        logger.warning("chat_turn.failed", stage="question", error_type=type(exc).__name__)
        yield error_event(QUESTION_FAILURE)
        yield done_event()
        return

    deps = DocumentAgentDeps(user_id, thread_id, retriever)
    try:
        chunks = deps.register_passages(await retriever.search_filings(question))
    except (httpx.HTTPError, SQLAlchemyError, ValueError) as exc:
        logger.warning("chat_turn.failed", stage="searching", error_type=type(exc).__name__)
        yield error_event(RETRIEVAL_FAILURE)
        yield done_event()
        return

    yield status_event("analyzing")
    prompt = json.dumps(
        {"question": question, "retrieved_evidence": [asdict(c) for c in chunks]},
        default=str,
    )
    try:
        result = await agent.run(
            prompt,
            deps=deps,
            message_history=history,
            usage_limits=UsageLimits(request_limit=12),
        )
    except GroundingError as exc:
        logger.warning("chat_turn.failed", stage="verifying", error_type=type(exc).__name__)
        yield error_event(GROUNDING_FAILURE)
        yield done_event()
        return
    except (AgentRunError, ModelHTTPError, httpx.HTTPError, SQLAlchemyError) as exc:
        logger.warning("chat_turn.failed", stage="analyzing", error_type=type(exc).__name__)
        yield error_event(ANALYSIS_FAILURE)
        yield done_event()
        return

    yield status_event("verifying")
    answer = result.output
    if answer.status != "answered" and not answer.citations:
        answer = safe_status_answer(answer)
    try:
        validate_answer(answer, deps.evidence)
        citations = citation_parts(answer, deps.evidence)
    except GroundingError as exc:
        logger.warning("chat_turn.failed", stage="verifying", error_type=type(exc).__name__)
        yield error_event(GROUNDING_FAILURE)
        yield done_event()
        return

    answer_status_part = {
        "type": "data-answer-status",
        "data": {"status": answer.status},
    }
    parts = assistant_text_to_parts(answer.answer) + [answer_status_part] + citations

    async def on_complete() -> None:
        async with AsyncSessionLocal() as assistant_session, assistant_session.begin():
            await create_message(
                assistant_session,
                thread_id=thread_id,
                role=MessageRole.assistant,
                parts=parts,
                message_id=message_id,
            )
            await create_citations(
                assistant_session, message_id=message_id, parts=citations
            )

    async for event in answer_event_stream(
        answer.answer,
        message_id=str(message_id),
        answer_status=answer.status,
        citations=citations,
        on_complete=on_complete,
    ):
        yield event
