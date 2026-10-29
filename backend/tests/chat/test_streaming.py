from __future__ import annotations

import asyncio
import json

from app.chat.streaming import answer_event_stream, status_event


def test_status_event_is_transient() -> None:
    event = json.loads(status_event("searching").decode().removeprefix("data: "))

    assert event == {
        "type": "data-status",
        "data": {"stage": "searching"},
        "transient": True,
    }


def test_answer_stream_finishes_only_after_persistence() -> None:
    completed: list[str] = []

    async def on_complete() -> None:
        completed.append("hello world")

    async def collect() -> list[dict[str, object]]:
        events = []
        async for chunk in answer_event_stream(
            "hello world",
            message_id="m1",
            answer_status="answered",
            citations=[],
            on_complete=on_complete,
        ):
            line = chunk.decode()
            if line.startswith("data: ") and not line.startswith("data: [DONE]"):
                events.append(json.loads(line.removeprefix("data: ").strip()))
        return events

    events = asyncio.run(collect())

    types = [event["type"] for event in events]
    assert types == [
        "text-start",
        "text-delta",
        "text-delta",
        "text-end",
        "data-answer-status",
        "data-status",
        "finish",
    ]
    assert events[-2] == {
        "type": "data-status",
        "data": {"stage": "saving"},
        "transient": True,
    }
    assert completed == ["hello world"]


def test_finish_is_not_sent_before_save() -> None:
    saved = False

    async def save() -> None:
        nonlocal saved
        saved = True

    async def check() -> None:
        async for chunk in answer_event_stream(
            "answer",
            message_id="m1",
            answer_status="answered",
            citations=[],
            on_complete=save,
        ):
            if b'"type": "finish"' in chunk:
                assert saved

    asyncio.run(check())


def test_persistence_failure_emits_error_without_success() -> None:
    async def fail() -> None:
        raise RuntimeError("database unavailable")

    async def collect() -> list[dict[str, object]]:
        events = []
        async for chunk in answer_event_stream(
            "validated answer",
            message_id="m1",
            answer_status="answered",
            citations=[],
            on_complete=fail,
        ):
            if chunk.startswith(b"data: {"):
                events.append(json.loads(chunk.decode().removeprefix("data: ").strip()))
        return events

    events = asyncio.run(collect())
    assert events[-1] == {
        "type": "error",
        "errorText": "The verified answer could not be saved. Reload this thread before trying again.",
    }
    assert not any(event["type"] == "finish" for event in events)
