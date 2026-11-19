from pathlib import Path
from uuid import UUID

import httpx
from google.genai.types import HttpRetryOptions
from pydantic_ai import Agent, ModelRetry, NativeOutput, RunContext
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.google import GoogleModel, GoogleModelSettings
from pydantic_ai.providers.google import GoogleProvider

from app.assistant.deps import DocumentAgentDeps
from app.assistant.outputs import GroundedAnswer
from app.config import Settings
from app.grounding.validator import (
    GroundingError,
    normalize_citation_markers,
    normalize_markdown_line_breaks,
    safe_status_answer,
    validate_answer,
)
from app.retrieval.models import Chunk, RetrievalFilters

_RETRYABLE_MODEL_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})


def _retry_on_transient_model_error(exc: Exception) -> bool:
    if isinstance(exc, ModelHTTPError):
        return exc.status_code in _RETRYABLE_MODEL_STATUS_CODES
    return isinstance(exc, httpx.TransportError)


def _google_model(name: str, settings: Settings, *, attempts: int) -> GoogleModel:
    return GoogleModel(
        name,
        provider=GoogleProvider(
            api_key=settings.gemini_api_key.get_secret_value(),
            retry_options=HttpRetryOptions(
                attempts=attempts,
                initial_delay=1,
                max_delay=3,
                http_status_codes=sorted(_RETRYABLE_MODEL_STATUS_CODES),
            ),
        ),
    )


async def search_filings(
    ctx: RunContext[DocumentAgentDeps],
    query: str,
    tickers: list[str] | None = None,
    fiscal_years: list[int] | None = None,
    filing_types: list[str] | None = None,
) -> list[Chunk]:
    """Search curated filings by topic and optional company/year/type filters."""
    ctx.deps.count_tool(search=True)
    try:
        filters = RetrievalFilters(
            tuple(tickers or ()), tuple(fiscal_years or ()), tuple(filing_types or ())
        )
        if not query.strip():
            raise ValueError("query must not be blank")
    except ValueError as exc:
        raise ModelRetry(str(exc)) from exc
    passages = await ctx.deps.retriever.search_filings(query, filters)
    return ctx.deps.register_passages(passages)


async def read_chunk(ctx: RunContext[DocumentAgentDeps], chunk_id: UUID) -> Chunk:
    """Read a full chunk already exposed during this turn."""
    ctx.deps.count_tool()
    return ctx.deps.require_chunk(chunk_id)


async def read_surrounding_chunks(
    ctx: RunContext[DocumentAgentDeps],
    chunk_id: UUID,
    before: int = 1,
    after: int = 1,
) -> list[Chunk]:
    """Read up to eight neighboring chunks on either side of an exposed chunk."""
    ctx.deps.count_tool()
    ctx.deps.require_chunk(chunk_id)
    if not 0 <= before <= 8 or not 0 <= after <= 8:
        raise ModelRetry("before and after must be between 0 and 8")
    chunks = await ctx.deps.retriever.read_surrounding_chunks(
        chunk_id, before=before, after=after
    )
    return ctx.deps.register(list(chunks))


def build_agent(settings: Settings) -> Agent[DocumentAgentDeps, GroundedAnswer]:
    model = FallbackModel(
        _google_model(settings.gemini_chat_model, settings, attempts=1),
        _google_model(settings.gemini_fallback_chat_model, settings, attempts=2),
        fallback_on=_retry_on_transient_model_error,
    )
    agent = Agent(
        model,
        deps_type=DocumentAgentDeps,
        output_type=NativeOutput(GroundedAnswer),
        instructions=Path(__file__)
        .with_name("instructions.md")
        .read_text(encoding="utf-8"),
        model_settings=GoogleModelSettings(
            thinking=(
                False
                if settings.gemini_reasoning_effort == "none"
                else settings.gemini_reasoning_effort
            ),
            timeout=60,
            max_tokens=16_384,
        ),
        retries={"tools": 1, "output": 2},
        tools=[search_filings, read_chunk, read_surrounding_chunks],
    )

    @agent.output_validator
    def enforce_grounding(
        ctx: RunContext[DocumentAgentDeps], output: GroundedAnswer
    ) -> GroundedAnswer:
        try:
            output = normalize_markdown_line_breaks(output)
            output = normalize_citation_markers(output)
            if output.status != "answered" and output.citations:
                raise GroundingError(
                    "Abstentions and refusals cannot contain citations"
                )
            output = safe_status_answer(output)
            validate_answer(output, ctx.deps.evidence)
        except GroundingError as exc:
            raise ModelRetry(str(exc)) from exc
        return output

    return agent
