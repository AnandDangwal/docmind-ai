import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest

import app.chat.orchestrator as module
from app.assistant.outputs import Citation, GroundedAnswer
from app.chat.messages import UIMessage
from tests.retrieval.test_retriever import _chunk


def test_initial_retrieval_balances_explicit_companies():
    async def run():
        calls = []

        async def search_balanced(question, filters, **kwargs):
            calls.extend((item, kwargs) for item in filters)
            return []

        await module._retrieve_initial_evidence(
            SimpleNamespace(search_filings_balanced=search_balanced),
            "Compare Amazon, Apple, Google, Microsoft and Nvidia profit in 2024",
        )

        assert [filters.tickers for filters, _ in calls] == [
            ("AAPL",),
            ("AMZN",),
            ("GOOGL",),
            ("MSFT",),
            ("NVDA",),
        ]
        assert all(filters.fiscal_years == (2024,) for filters, _ in calls)
        assert all(
            options == {"top_k_per_filter": 4, "neighbor_window": 1}
            for _, options in calls
        )

    asyncio.run(run())


def test_turn_emits_start_and_searching_before_database_or_model_work():
    async def run():
        async def should_not_run():
            raise AssertionError("work started before the initial stream events")

        stream = module.run_chat_turn(
            SimpleNamespace(commit=should_not_run),
            UUID(int=10),
            [
                UIMessage(
                    id="new",
                    role="user",
                    parts=[{"type": "text", "text": "Sales?"}],
                )
            ],
            user_id=UUID(int=20),
            agent=SimpleNamespace(),
            retriever=SimpleNamespace(),
        )

        first = json.loads((await asyncio.wait_for(anext(stream), 0.1))[6:])
        second = json.loads((await asyncio.wait_for(anext(stream), 0.1))[6:])
        await stream.aclose()

        assert first["type"] == "start"
        assert second == {
            "type": "data-status",
            "data": {"stage": "searching"},
            "transient": True,
        }

    asyncio.run(run())


def test_analysis_failure_distinguishes_transient_provider_outage():
    message, failure_kind, statuses = module._analysis_failure(
        module.FallbackExceptionGroup(
            "models unavailable",
            [
                module.ModelHTTPError(503, "primary"),
                module.ModelHTTPError(429, "fallback"),
            ],
        )
    )

    assert message == module.MODEL_BUSY_FAILURE
    assert failure_kind == "provider_transient"
    assert statuses == [503, 429]


def test_ambiguous_latest_filing_returns_persisted_clarification(monkeypatch):
    async def run():
        writes = []

        async def commit():
            pass

        async def create(session, **kwargs):
            writes.append(kwargs)

        async def history(*args, **kwargs):
            return []

        async def citations(session, **kwargs):
            assert kwargs["parts"] == []

        async def unexpected(*args, **kwargs):
            raise AssertionError(
                "Ambiguous latest scope must not call retrieval or Gemini"
            )

        @asynccontextmanager
        async def transaction():
            yield

        @asynccontextmanager
        async def sessions():
            yield SimpleNamespace(begin=transaction)

        monkeypatch.setattr(module, "create_message", create)
        monkeypatch.setattr(module, "create_citations", citations)
        monkeypatch.setattr(module, "list_messages_for_thread", history)
        monkeypatch.setattr(module, "AsyncSessionLocal", sessions)

        stream = module.run_chat_turn(
            SimpleNamespace(commit=commit),
            UUID(int=10),
            [
                UIMessage(
                    id="new",
                    role="user",
                    parts=[
                        {
                            "type": "text",
                            "text": "Summarize the latest filing, with citations.",
                        }
                    ],
                )
            ],
            user_id=UUID(int=20),
            agent=SimpleNamespace(run=unexpected),
            retriever=SimpleNamespace(
                search_filings=unexpected,
                load_relevant_filings=unexpected,
            ),
        )
        raw = [part.decode() async for part in stream]
        events = [json.loads(part[6:]) for part in raw if "[DONE]" not in part]

        assert events[-1]["type"] == "finish"
        assert any(
            event.get("data", {}).get("status") == "insufficient_evidence"
            for event in events
        )
        answer = "".join(
            event["delta"] for event in events if event["type"] == "text-delta"
        )
        assert "specify the company" in answer
        assert [write["role"] for write in writes] == [
            module.MessageRole.user,
            module.MessageRole.assistant,
        ]

    asyncio.run(run())


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

        async def search(question, filters=None, **kwargs):
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
                response=SimpleNamespace(model_name="test-model"),
                output=GroundedAnswer(
                    status="answered",
                    answer="Sales changed. [C1]",
                    citations=[
                        Citation(
                            citation_id="C1",
                            chunk_id=UUID(int=2 if failure == "grounding" else 1),
                        )
                    ],
                ),
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
            event["data"]["stage"] for event in events if event["type"] == "data-status"
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


def test_replacement_turn_uses_only_history_before_target(monkeypatch):
    async def run():
        target_id = uuid4()
        replacement_calls = []
        writes = []

        async def commit():
            pass

        async def replace(session, **kwargs):
            replacement_calls.append(kwargs)
            return [
                SimpleNamespace(
                    role="user",
                    parts=[{"type": "text", "text": "Earlier question"}],
                ),
                SimpleNamespace(
                    role="assistant",
                    parts=[{"type": "text", "text": "Earlier answer"}],
                ),
            ]

        async def create(session, **kwargs):
            writes.append(kwargs)

        async def create_source_citations(session, **kwargs):
            pass

        async def unexpected_history(*args, **kwargs):
            raise AssertionError("Replacement history must come from replace_user_turn")

        async def search(question, filters=None, **kwargs):
            return []

        async def generate(prompt, **kwargs):
            assert len(kwargs["message_history"]) == 2
            assert "Earlier question" not in prompt
            return SimpleNamespace(
                response=SimpleNamespace(model_name="test-model"),
                output=GroundedAnswer(
                    status="insufficient_evidence",
                    answer="Not enough evidence.",
                    citations=[],
                ),
            )

        @asynccontextmanager
        async def transaction():
            yield

        @asynccontextmanager
        async def sessions():
            yield SimpleNamespace(begin=transaction)

        monkeypatch.setattr(module, "replace_user_turn", replace)
        monkeypatch.setattr(module, "create_message", create)
        monkeypatch.setattr(module, "create_citations", create_source_citations)
        monkeypatch.setattr(module, "list_messages_for_thread", unexpected_history)
        monkeypatch.setattr(module, "AsyncSessionLocal", sessions)

        messages = [
            UIMessage(
                id=str(target_id),
                role="user",
                parts=[{"type": "text", "text": "Edited question"}],
            )
        ]
        stream = module.run_chat_turn(
            SimpleNamespace(commit=commit),
            UUID(int=10),
            messages,
            user_id=UUID(int=20),
            agent=SimpleNamespace(run=generate),
            retriever=SimpleNamespace(search_filings=search),
            replace_message_id=target_id,
        )
        _ = [part async for part in stream]

        assert replacement_calls == [
            {
                "thread_id": UUID(int=10),
                "message_id": target_id,
                "parts": [{"type": "text", "text": "Edited question"}],
                "title": "Edited question",
            }
        ]
        assert len(writes) == 1
        assert writes[0]["role"] == module.MessageRole.assistant

    asyncio.run(run())
