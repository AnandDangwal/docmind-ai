import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.function import FunctionModel

from app.assistant.agent import (
    _retry_on_transient_model_error,
    build_agent,
    read_chunk,
    read_surrounding_chunks,
    search_filings,
)
from app.assistant.deps import (
    MAX_EVIDENCE_CHUNKS,
    MAX_SEARCH_CALLS,
    MAX_TOOL_CALLS,
    DocumentAgentDeps,
)
from app.config import settings
from tests.retrieval.test_retriever import _chunk


def deps(retriever=None):
    return DocumentAgentDeps(UUID(int=10), UUID(int=20), retriever)


def test_evidence_registry_deduplicates_and_caps():
    context = deps()
    assert (
        len(context.register([_chunk(i) for i in range(1, MAX_EVIDENCE_CHUNKS + 20)]))
        == MAX_EVIDENCE_CHUNKS
    )
    assert len(context.evidence) == MAX_EVIDENCE_CHUNKS
    assert context.register([_chunk(1)]) == [_chunk(1)]


def test_agent_has_distinct_gemini_fallback_for_transient_provider_errors():
    agent = build_agent(settings)

    assert isinstance(agent.model, FallbackModel)
    assert [model.model_name for model in agent.model.models] == [
        settings.gemini_chat_model,
        settings.gemini_fallback_chat_model,
    ]
    assert _retry_on_transient_model_error(
        ModelHTTPError(503, settings.gemini_chat_model)
    )
    assert not _retry_on_transient_model_error(
        ModelHTTPError(400, settings.gemini_chat_model)
    )


def test_transient_primary_failure_runs_fallback_model():
    async def run():
        calls = []

        def unavailable(messages, info):
            calls.append("primary")
            raise ModelHTTPError(503, "primary")

        def available(messages, info):
            calls.append("fallback")
            return ModelResponse(parts=[TextPart("recovered")])

        model = FallbackModel(
            FunctionModel(unavailable),
            FunctionModel(available),
            fallback_on=_retry_on_transient_model_error,
        )
        result = await Agent(model).run("test")

        assert result.output == "recovered"
        assert calls == ["primary", "fallback"]

    asyncio.run(run())


def test_evidence_registry_counts_serialization_overhead_in_token_budget():
    context = deps()
    oversized = replace(_chunk(1), token_count=900_000)

    assert context.register([oversized]) == []
    assert context.evidence_tokens == 0


def test_tools_are_bounded_and_reject_unexposed_ids():
    async def run():
        context = deps()
        ctx = SimpleNamespace(deps=context)
        with pytest.raises(ModelRetry):
            await read_chunk(ctx, UUID(int=1))
        context.register([_chunk(1)])
        assert await read_chunk(ctx, UUID(int=1)) == _chunk(1)
        with pytest.raises(ModelRetry):
            await read_surrounding_chunks(ctx, UUID(int=1), before=9)
        for _ in range(MAX_TOOL_CALLS - context.tool_calls):
            context.count_tool()
        with pytest.raises(ModelRetry):
            context.count_tool()

    asyncio.run(run())


def test_search_filters_and_neighbors_register_evidence():
    async def run():
        calls = []

        async def search(query, filters):
            calls.append(filters)
            return []

        async def neighbors(*args, **kwargs):
            return (_chunk(2),)

        context = deps(
            SimpleNamespace(search_filings=search, read_surrounding_chunks=neighbors)
        )
        context.register([_chunk(1)])
        ctx = SimpleNamespace(deps=context)
        for _ in range(MAX_SEARCH_CALLS):
            await search_filings(ctx, "sales", tickers=["aapl"], fiscal_years=[2023])
        assert calls[0].tickers == ("AAPL",)
        with pytest.raises(ModelRetry):
            await search_filings(ctx, "sales")
        await read_surrounding_chunks(ctx, UUID(int=1))
        assert UUID(int=2) in context.evidence

    asyncio.run(run())


@pytest.mark.parametrize("correct_retry", [True, False])
def test_real_agent_validator_respects_output_retry_budget(correct_retry):
    async def run():
        calls = []

        def respond(messages, info):
            calls.append(messages)
            text = (
                "Claim. [C1]" if correct_retry and len(calls) > 1 else "Uncited claim."
            )
            return ModelResponse(
                parts=[
                    TextPart(
                        json.dumps(
                            {
                                "status": "answered",
                                "answer": text,
                                "citations": [
                                    {"citation_id": "C1", "chunk_id": str(UUID(int=1))}
                                ],
                            }
                        )
                    )
                ]
            )

        agent = build_agent(settings)
        context = deps()
        context.register([_chunk(1)])
        with agent.override(model=FunctionModel(respond)):
            if correct_retry:
                result = await agent.run("question", deps=context)
                assert "[C1]" in result.output.answer
            else:
                with pytest.raises(UnexpectedModelBehavior):
                    await agent.run("question", deps=context)
        assert len(calls) == (2 if correct_retry else 3)

    asyncio.run(run())
