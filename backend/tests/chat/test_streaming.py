from __future__ import annotations

import asyncio
import json

from app.chat.streaming import stub_event_stream


def test_stub_event_stream_emits_expected_events_and_calls_on_complete() -> None:
    completed: list[str] = []

    async def on_complete(text: str) -> None:
        completed.append(text)

    async def collect() -> list[dict[str, object]]:
        events = []
        async for chunk in stub_event_stream("hello world", on_complete=on_complete):
            line = chunk.decode()
            if line.startswith("data: ") and not line.startswith("data: [DONE]"):
                events.append(json.loads(line.removeprefix("data: ").strip()))
        return events

    events = asyncio.run(collect())

    types = [event["type"] for event in events]
    assert types == ["start", "text-start", "text-delta", "text-delta", "text-end", "finish"]
    assert completed == ["hello world"]
