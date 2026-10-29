from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Literal

import structlog
from fastapi.responses import StreamingResponse

logger = structlog.get_logger(__name__)

PipelineStage = Literal["searching", "analyzing", "verifying", "saving"]
AnswerStatus = Literal["answered", "insufficient_evidence", "refused"]

_STREAM_HEADERS = {
    "x-vercel-ai-ui-message-stream": "v1",
    "Cache-Control": "no-cache",
}


def sse_event(event: dict[str, object]) -> bytes:
    return f"data: {json.dumps(event)}\n\n".encode()


def status_event(stage: PipelineStage) -> bytes:
    return sse_event(
        {"type": "data-status", "data": {"stage": stage}, "transient": True}
    )


def error_event(message: str) -> bytes:
    return sse_event({"type": "error", "errorText": message})


def done_event() -> bytes:
    return b"data: [DONE]\n\n"


async def answer_event_stream(
    text: str,
    *,
    message_id: str,
    answer_status: AnswerStatus,
    citations: list[dict],
    on_complete: Callable[[], Awaitable[None]],
) -> AsyncIterator[bytes]:
    """Only already-validated text may enter this encoder."""
    part_id = f"{message_id}-text"

    yield sse_event({"type": "text-start", "id": part_id})

    words = text.split(" ")
    for index, word in enumerate(words):
        delta = word if index == len(words) - 1 else f"{word} "
        yield sse_event({"type": "text-delta", "id": part_id, "delta": delta})

    yield sse_event({"type": "text-end", "id": part_id})
    yield sse_event(
        {"type": "data-answer-status", "data": {"status": answer_status}}
    )
    for citation in citations:
        yield sse_event(citation)
    yield status_event("saving")
    try:
        await on_complete()
    except Exception:
        logger.exception(
            "chat_stream.persist_assistant_message_failed", message_id=message_id
        )
        yield error_event(
            "The verified answer could not be saved. Reload this thread before trying again."
        )
        yield done_event()
        return
    yield sse_event({"type": "finish"})
    yield done_event()


def build_stream_response(generator: AsyncIterator[bytes]) -> StreamingResponse:
    return StreamingResponse(
        generator, media_type="text/event-stream", headers=_STREAM_HEADERS
    )
