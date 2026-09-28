from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

import structlog
from fastapi.responses import StreamingResponse

logger = structlog.get_logger(__name__)

_STREAM_HEADERS = {
    "x-vercel-ai-ui-message-stream": "v1",
    "Cache-Control": "no-cache",
}


def _sse(event: dict[str, object]) -> bytes:
    return f"data: {json.dumps(event)}\n\n".encode()


async def stub_event_stream(
    text: str,
    on_complete: Callable[[str], Awaitable[None]] | None = None,
) -> AsyncIterator[bytes]:
    """Emit a fixed-text reply as AI SDK data-stream-protocol events, word by word."""
    part_id = str(uuid.uuid4())

    yield _sse({"type": "start"})
    yield _sse({"type": "text-start", "id": part_id})

    words = text.split(" ")
    for index, word in enumerate(words):
        delta = word if index == len(words) - 1 else f"{word} "
        yield _sse({"type": "text-delta", "id": part_id, "delta": delta})

    yield _sse({"type": "text-end", "id": part_id})
    yield _sse({"type": "finish"})
    yield b"data: [DONE]\n\n"

    if on_complete is not None:
        try:
            await on_complete(text)
        except Exception:
            logger.exception("chat_stream.persist_assistant_message_failed")


def build_stream_response(generator: AsyncIterator[bytes]) -> StreamingResponse:
    return StreamingResponse(generator, media_type="text/event-stream", headers=_STREAM_HEADERS)
