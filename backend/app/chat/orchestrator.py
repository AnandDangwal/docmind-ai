from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from dataclasses import asdict
from time import perf_counter
from uuid import UUID, uuid4

import httpx
import structlog
from pydantic_ai import Agent
from pydantic_ai.exceptions import (
    AgentRunError,
    ContentFilterError,
    FallbackExceptionGroup,
    ModelHTTPError,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
)
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
    replace_user_turn,
)
from app.database.models import MessageRole
from app.database.session import AsyncSessionLocal
from app.grounding.validator import (
    GroundingError,
    citation_parts,
    safe_status_answer,
    validate_answer,
)
from app.retrieval.models import RetrievalFilters, RetrievedPassage
from app.retrieval.retriever import DocumentRetriever
from app.retrieval.scope import filters_from_question

logger = structlog.get_logger(__name__)

QUESTION_FAILURE = (
    "The question could not be saved, so the assistant did not start. Please try again."
)
RETRIEVAL_FAILURE = "The filings could not be searched right now. Check the service connection and try again."
ANALYSIS_FAILURE = "The filings were found, but the assistant could not analyze them. Please try again."
MODEL_BUSY_FAILURE = (
    "The filings were found, but the AI analysis service is temporarily busy. "
    "The primary and fallback models were tried; please try again shortly."
)
MODEL_CONFIGURATION_FAILURE = (
    "The filings were found, but the AI analysis service rejected its model "
    "configuration. Please contact support."
)
ANALYSIS_LIMIT_FAILURE = (
    "The filings were found, but this analysis exceeded the model request limit. "
    "Please narrow the company, period, or metric and try again."
)
CONTENT_FILTER_FAILURE = (
    "The filings were found, but the AI provider declined to process this request. "
    "Please rephrase it or contact support if the problem continues."
)
GROUNDING_FAILURE = (
    "The draft answer could not be verified against the filings, so it was withheld."
)
_RETRYABLE_MODEL_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})
_BROAD_RESEARCH_TERMS = (
    "across",
    "compare",
    "comparison",
    "entire filing",
    "whole filing",
    "summarize",
    "summary",
)
_MULTI_COMPANY_TERMS = (
    "all companies",
    "each company",
    "every company",
    "five companies",
    "across companies",
)


def _elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 1)


def _leaf_exceptions(exc: BaseException) -> list[BaseException]:
    if isinstance(exc, BaseExceptionGroup):
        return [leaf for child in exc.exceptions for leaf in _leaf_exceptions(child)]
    return [exc]


def _analysis_failure(exc: BaseException) -> tuple[str, str, list[int]]:
    leaves = _leaf_exceptions(exc)
    model_errors = [leaf for leaf in leaves if isinstance(leaf, ModelHTTPError)]
    statuses = [error.status_code for error in model_errors]
    if statuses and all(status in _RETRYABLE_MODEL_STATUS_CODES for status in statuses):
        return MODEL_BUSY_FAILURE, "provider_transient", statuses
    if model_errors:
        return MODEL_CONFIGURATION_FAILURE, "provider_rejected", statuses
    if any(isinstance(leaf, UsageLimitExceeded) for leaf in leaves):
        return ANALYSIS_LIMIT_FAILURE, "request_limit", statuses
    if any(isinstance(leaf, ContentFilterError) for leaf in leaves):
        return CONTENT_FILTER_FAILURE, "content_filter", statuses
    if any(isinstance(leaf, UnexpectedModelBehavior) for leaf in leaves):
        return GROUNDING_FAILURE, "invalid_model_output", statuses
    if any(isinstance(leaf, httpx.HTTPError) for leaf in leaves):
        return MODEL_BUSY_FAILURE, "provider_network", statuses
    return ANALYSIS_FAILURE, "agent_error", statuses


def _latest_scope_is_ambiguous(question: str, filters: RetrievalFilters) -> bool:
    normalized = question.casefold()
    return (
        filters.latest_only
        and not filters.tickers
        and not any(term in normalized for term in _MULTI_COMPANY_TERMS)
    )


async def _retrieve_initial_evidence(
    retriever: DocumentRetriever, question: str
) -> list[RetrievedPassage]:
    filters = filters_from_question(question)
    if len(filters.tickers) <= 1:
        return await retriever.search_filings(question, filters)

    company_filters = tuple(
        RetrievalFilters(
            tickers=(ticker,),
            fiscal_years=filters.fiscal_years,
            filing_types=filters.filing_types,
        )
        for ticker in filters.tickers
    )
    return await retriever.search_filings_balanced(
        question,
        company_filters,
        top_k_per_filter=4,
        neighbor_window=1,
    )


def _requires_complete_filings(question: str, filters: RetrievalFilters) -> bool:
    normalized = question.casefold()
    return (
        len(filters.tickers) > 1
        or len(filters.fiscal_years) > 1
        or any(term in normalized for term in _BROAD_RESEARCH_TERMS)
    )


async def _map_relevant_filings(
    *,
    agent: Agent[DocumentAgentDeps, GroundedAnswer],
    retriever: DocumentRetriever,
    filters: RetrievalFilters,
    question: str,
    user_id: UUID,
    thread_id: UUID,
) -> tuple[list, list[dict], bool]:
    groups = await retriever.load_relevant_filing_groups(filters)
    semaphore = asyncio.Semaphore(3)

    async def research(chunks):
        async with semaphore:
            map_deps = DocumentAgentDeps(user_id, thread_id, retriever)
            exposed = map_deps.register(chunks)
            prompt = json.dumps(
                {
                    "task": (
                        "Prepare a concise factual research memo for this one filing. "
                        "Address only dimensions relevant to the question, preserve units "
                        "and fiscal periods, and identify unavailable requested metrics."
                    ),
                    "question": question,
                    "coverage_complete": True,
                    "retrieved_evidence": [asdict(chunk) for chunk in exposed],
                },
                default=str,
            )
            result = await agent.run(
                prompt,
                deps=map_deps,
                usage_limits=UsageLimits(request_limit=64),
            )
            if result.output.status != "answered":
                return None
            cited = [
                map_deps.evidence[citation.chunk_id]
                for citation in result.output.citations
            ]
            note = re.sub(r"\s*\[C[1-9]\d*\]", "", result.output.answer)
            first = chunks[0]
            return {
                "filing": {
                    "ticker": first.ticker,
                    "fiscal_year": first.fiscal_year,
                    "filing_date": first.filing_date.isoformat(),
                    "accession_number": first.accession_number,
                },
                "memo": note,
                "evidence_chunk_ids": [str(chunk.id) for chunk in cited],
            }, cited

    results = await asyncio.gather(
        *(research(chunks) for chunks in groups), return_exceptions=True
    )
    notes: list[dict] = []
    evidence = {}
    complete = True
    for result in results:
        if isinstance(result, BaseException) or result is None:
            complete = False
            continue
        note, cited = result
        notes.append(note)
        evidence.update((chunk.id, chunk) for chunk in cited)
    return list(evidence.values()), notes, complete and len(notes) == len(groups)


async def run_chat_turn(
    session: AsyncSession,
    thread_id: UUID,
    messages: list[UIMessage],
    *,
    user_id: UUID,
    agent: Agent[DocumentAgentDeps, GroundedAnswer],
    retriever: DocumentRetriever,
    replace_message_id: UUID | None = None,
) -> AsyncIterator[bytes]:
    message_id = uuid4()
    turn_started_at = perf_counter()
    stage_started_at = turn_started_at
    turn_logger = logger.bind(
        user_id=str(user_id),
        thread_id=str(thread_id),
        message_id=str(message_id),
    )
    turn_logger.info(
        "chat_turn.started", replacing_message=replace_message_id is not None
    )
    yield sse_event({"type": "start", "messageId": str(message_id)})
    yield status_event("searching")

    question = text_from_parts(ui_message_to_parts(messages[-1])).strip()
    try:
        question_parts = assistant_text_to_parts(question)
        if replace_message_id is None:
            stored_history = await list_messages_for_thread(
                session, thread_id=thread_id
            )
            await create_message(
                session,
                thread_id=thread_id,
                role=MessageRole.user,
                parts=question_parts,
            )
        else:
            stored_history = await replace_user_turn(
                session,
                thread_id=thread_id,
                message_id=replace_message_id,
                parts=question_parts,
                title=question,
            )
        history = stored_messages_to_history(stored_history)
        # Finish the question transaction before any external generation work.
        await session.commit()
        turn_logger.info(
            "chat_turn.question_saved", duration_ms=_elapsed_ms(stage_started_at)
        )
    except SQLAlchemyError as exc:
        turn_logger.warning(
            "chat_turn.failed",
            stage="question",
            error_type=type(exc).__name__,
            duration_ms=_elapsed_ms(turn_started_at),
        )
        yield error_event(QUESTION_FAILURE)
        yield done_event()
        return

    deps = DocumentAgentDeps(user_id, thread_id, retriever)
    filters = filters_from_question(question)
    complete_coverage = False
    research_notes: list[dict] = []
    answer: GroundedAnswer | None = None
    stage_started_at = perf_counter()
    try:
        if _latest_scope_is_ambiguous(question, filters):
            chunks = []
            answer = safe_status_answer(
                GroundedAnswer(
                    status="insufficient_evidence",
                    answer="Scope clarification required.",
                    citations=[],
                )
            )
        elif _requires_complete_filings(question, filters) and (
            filters.tickers or filters.fiscal_years or filters.latest_only
        ):
            relevant, complete_coverage = await retriever.load_relevant_filings(filters)
            if complete_coverage:
                chunks = deps.register(relevant)
            else:
                mapped, research_notes, complete_coverage = await _map_relevant_filings(
                    agent=agent,
                    retriever=retriever,
                    filters=filters,
                    question=question,
                    user_id=user_id,
                    thread_id=thread_id,
                )
                chunks = deps.register(mapped)
        else:
            chunks = deps.register_passages(
                await _retrieve_initial_evidence(retriever, question)
            )
    except (httpx.HTTPError, SQLAlchemyError, ValueError) as exc:
        turn_logger.warning(
            "chat_turn.failed",
            stage="searching",
            error_type=type(exc).__name__,
            detail=str(exc)[:500],
            duration_ms=_elapsed_ms(turn_started_at),
            exc_info=True,
        )
        yield error_event(RETRIEVAL_FAILURE)
        yield done_event()
        return

    turn_logger.info(
        "chat_turn.search_completed",
        duration_ms=_elapsed_ms(stage_started_at),
        evidence_count=len(chunks),
        research_note_count=len(research_notes),
        coverage_complete=complete_coverage,
    )
    yield status_event("analyzing")
    stage_started_at = perf_counter()
    analysis_model = "server"
    if answer is None:
        prompt = json.dumps(
            {
                "question": question,
                "coverage_complete": complete_coverage,
                "research_notes": research_notes,
                "retrieved_evidence": [asdict(c) for c in chunks],
            },
            default=str,
        )
        try:
            result = await agent.run(
                prompt,
                deps=deps,
                message_history=history,
                usage_limits=UsageLimits(request_limit=64),
            )
            answer = result.output
            analysis_model = result.response.model_name
        except GroundingError as exc:
            turn_logger.warning(
                "chat_turn.failed",
                stage="verifying",
                error_type=type(exc).__name__,
                duration_ms=_elapsed_ms(turn_started_at),
            )
            yield error_event(GROUNDING_FAILURE)
            yield done_event()
            return
        except SQLAlchemyError as exc:
            turn_logger.warning(
                "chat_turn.failed",
                stage="analyzing",
                failure_kind="follow_up_retrieval",
                error_type=type(exc).__name__,
                duration_ms=_elapsed_ms(turn_started_at),
                exc_info=True,
            )
            yield error_event(RETRIEVAL_FAILURE)
            yield done_event()
            return
        except (FallbackExceptionGroup, AgentRunError, httpx.HTTPError) as exc:
            message, failure_kind, provider_statuses = _analysis_failure(exc)
            turn_logger.warning(
                "chat_turn.failed",
                stage="analyzing",
                failure_kind=failure_kind,
                error_type=type(exc).__name__,
                provider_statuses=provider_statuses,
                detail=str(exc)[:500],
                duration_ms=_elapsed_ms(turn_started_at),
                exc_info=True,
            )
            yield error_event(message)
            yield done_event()
            return

    turn_logger.info(
        "chat_turn.analysis_completed",
        duration_ms=_elapsed_ms(stage_started_at),
        model_name=analysis_model,
    )
    yield status_event("verifying")
    stage_started_at = perf_counter()
    assert answer is not None
    if answer.status != "answered" and not answer.citations:
        answer = safe_status_answer(answer)
    try:
        validate_answer(answer, deps.evidence)
        citations = citation_parts(answer, deps.evidence)
    except GroundingError as exc:
        turn_logger.warning(
            "chat_turn.failed",
            stage="verifying",
            error_type=type(exc).__name__,
            duration_ms=_elapsed_ms(turn_started_at),
        )
        yield error_event(GROUNDING_FAILURE)
        yield done_event()
        return

    turn_logger.info(
        "chat_turn.verification_completed",
        duration_ms=_elapsed_ms(stage_started_at),
        answer_status=answer.status,
        citation_count=len(citations),
    )
    answer_status_part = {
        "type": "data-answer-status",
        "data": {"status": answer.status},
    }
    parts = assistant_text_to_parts(answer.answer) + [answer_status_part] + citations

    async def on_complete() -> None:
        save_started_at = perf_counter()
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
        turn_logger.info(
            "chat_turn.completed",
            save_duration_ms=_elapsed_ms(save_started_at),
            duration_ms=_elapsed_ms(turn_started_at),
            answer_status=answer.status,
            citation_count=len(citations),
        )

    async for event in answer_event_stream(
        answer.answer,
        message_id=str(message_id),
        answer_status=answer.status,
        citations=citations,
        on_complete=on_complete,
    ):
        yield event
