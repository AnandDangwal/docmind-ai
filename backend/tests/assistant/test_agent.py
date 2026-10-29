import asyncio
import json
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic_ai import ModelRetry
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from app.assistant.agent import (
    build_agent,
    read_chunk,
    read_surrounding_chunks,
    search_filings,
)
from app.assistant.deps import DocumentAgentDeps
from app.config import settings
from tests.retrieval.test_retriever import _chunk


def deps(retriever=None):
    return DocumentAgentDeps(UUID(int=10), UUID(int=20), retriever)


def test_evidence_registry_deduplicates_and_caps():
    context = deps()
    assert len(context.register([_chunk(i) for i in range(1, 60)])) == 40
    assert len(context.evidence) == 40
    assert context.register([_chunk(1)]) == [_chunk(1)]


def test_tools_are_bounded_and_reject_unexposed_ids():
    async def run():
        context = deps()
        ctx = SimpleNamespace(deps=context)
        with pytest.raises(ModelRetry):
            await read_chunk(ctx, UUID(int=1))
        context.register([_chunk(1)])
        assert await read_chunk(ctx, UUID(int=1)) == _chunk(1)
        with pytest.raises(ModelRetry):
            await read_surrounding_chunks(ctx, UUID(int=1), before=4)
        for _ in range(5):
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
        for _ in range(3):
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

