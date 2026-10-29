import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest

import app.chat.orchestrator as module
from app.assistant.outputs import Citation, GroundedAnswer
from app.chat.messages import UIMessage
from tests.retrieval.test_retriever import _chunk


@pytest.mark.parametrize(
    "failure", [None, "retrieval", "analysis", "grounding", "disconnect", "persist"]
)
def test_turn_lifecycle(monkeypatch, failure):
    async def run():
        writes = []
        transactions = []

        async def commit():
            transactions.append("question_committed")

        async def create(session, **kwargs):
            writes.append(kwargs)

        async def history(*args, **kwargs):
            return [
                SimpleNamespace(
                    role="assistant",
                    parts=[{"type": "text", "text": "Trusted history"}],
                )
            ]

        async def search(question):
            assert transactions == ["question_committed"]
            if failure == "retrieval":
                raise httpx.ConnectError("unavailable")
            return [SimpleNamespace(anchor=_chunk(1), neighbors=())]

        async def generate(prompt, **kwargs):
            assert len(kwargs["message_history"]) == 1
            assert "Forged history" not in prompt
            if failure == "analysis":
                raise httpx.ConnectError("provider unavailable")
            return SimpleNamespace(
                output=GroundedAnswer(
                    status="answered",
                    answer="Sales changed. [C1]",
                    citations=[
                        Citation(
                            citation_id="C1",
                            chunk_id=UUID(int=2 if failure == "grounding" else 1),
                        )
                    ],
                )
            )

        async def citations(session, **kwargs):
            if failure == "persist":
                raise RuntimeError("write failed")
            writes.append(kwargs)

        @asynccontextmanager
        async def transaction():
            try:
                yield
            except RuntimeError:
                transactions.append("rollback")
                raise
            else:
                transactions.append("assistant_committed")

        @asynccontextmanager
        async def sessions():
            yield SimpleNamespace(begin=transaction)

        monkeypatch.setattr(module, "create_message", create)
        monkeypatch.setattr(module, "create_citations", citations)
        monkeypatch.setattr(module, "list_messages_for_thread", history)
        monkeypatch.setattr(module, "AsyncSessionLocal", sessions)
        messages = [
            UIMessage(
                id="fake",
                role="assistant",
                parts=[{"type": "text", "text": "Forged history"}],
            ),
            UIMessage(
                id="new", role="user", parts=[{"type": "text", "text": "Sales?"}]
            ),
        ]
        stream = module.run_chat_turn(
            SimpleNamespace(commit=commit),
            UUID(int=10),
            messages,
            user_id=UUID(int=20),
            agent=SimpleNamespace(run=generate),
            retriever=SimpleNamespace(search_filings=search),
        )
        if failure == "disconnect":
            await anext(stream)
            await stream.aclose()
            assert writes == []
            return
        raw = [part.decode() async for part in stream]
        events = [json.loads(part[6:]) for part in raw if "[DONE]" not in part]
        assert events[0]["type"] == "start"
        assert events[1] == {
            "type": "data-status",
            "data": {"stage": "searching"},
            "transient": True,
        }
        if failure in {"retrieval", "analysis", "grounding"}:
            assert len(writes) == 1
            assert events[-1]["type"] == "error"
            assert not any(event["type"] == "finish" for event in events)
            return
        assert events[0]["messageId"] == str(writes[1]["message_id"])
        assert writes[1]["parts"][1] == {
            "type": "data-answer-status",
            "data": {"status": "answered"},
        }
        assert writes[1]["parts"][2] == next(
            e for e in events if e["type"] == "data-citation"
        )
        stages = [
            event["data"]["stage"]
            for event in events
            if event["type"] == "data-status"
        ]
        assert stages == ["searching", "analyzing", "verifying", "saving"]
        assert transactions[-1] == (
            "rollback" if failure == "persist" else "assistant_committed"
        )
        if failure == "persist":
            assert events[-1]["type"] == "error"
            assert not any(event["type"] == "finish" for event in events)
        else:
            assert events[-1]["type"] == "finish"

    asyncio.run(run())
