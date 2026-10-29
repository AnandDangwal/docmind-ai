"""Paid, opt-in checks: uv run pytest -m integration tests/assistant -s."""

import asyncio
import json
from dataclasses import asdict
from uuid import uuid4

import pytest
from pydantic_ai.usage import UsageLimits

from app.assistant.agent import build_agent
from app.assistant.deps import DocumentAgentDeps
from app.config import settings
from app.database.session import AsyncSessionLocal
from app.grounding.validator import citation_parts, validate_answer
from app.retrieval.embeddings import GeminiQueryEmbedder
from app.retrieval.retriever import DocumentRetriever

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "question,expected",
    [
        ("What net sales did Apple disclose for fiscal 2023?", "answered"),
        ("Did it improve?", "insufficient_evidence"),
        (
            "Across Apple's 2021–2025 filings, how did Services revenue change?",
            "answered",
        ),
        (
            "Do the filings prove that generative AI improved margins for these companies? Distinguish disclosed evidence from causal inference.",
            "causal_boundary",
        ),
    ],
)
def test_live_grounding(question, expected):
    async def run():
        retriever = DocumentRetriever(AsyncSessionLocal, GeminiQueryEmbedder())
        deps = DocumentAgentDeps(uuid4(), uuid4(), retriever)
        chunks = deps.register_passages(await retriever.search_filings(question))
        result = await build_agent(settings).run(
            json.dumps(
                {
                    "question": question,
                    "retrieved_evidence": [asdict(c) for c in chunks],
                },
                default=str,
            ),
            deps=deps,
            usage_limits=UsageLimits(request_limit=12),
        )
        validate_answer(result.output, deps.evidence)
        print(result.output.model_dump_json(indent=2))
        if expected == "causal_boundary":
            if result.output.status == "answered":
                limitation = result.output.answer.lower()
                assert any(
                    phrase in limitation
                    for phrase in (
                        "does not prove",
                        "do not prove",
                        "do not universally prove",
                        "does not establish",
                        "do not establish",
                        "cannot conclude",
                        "cannot be established",
                    )
                )
            else:
                assert result.output.status == "insufficient_evidence"
        elif expected:
            assert result.output.status == expected
        if question.startswith("What net sales"):
            assert "383" in result.output.answer
        for part in citation_parts(result.output, deps.evidence):
            assert part["data"]["filingDate"]
            assert part["data"]["sourceUrl"]
            assert part["data"]["excerpt"]
            assert part["data"]["page"]

    asyncio.run(run())
