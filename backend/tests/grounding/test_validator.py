from dataclasses import replace
from uuid import UUID

import pytest

from app.assistant.outputs import Citation, GroundedAnswer
from app.grounding.validator import (
    SAFE_STATUS_TEXT,
    GroundingError,
    citation_parts,
    normalize_citation_markers,
    safe_status_answer,
    validate_answer,
)
from tests.retrieval.test_retriever import _chunk


def answer(text="Sales declined. [C1]", ids=None, status="answered"):
    return GroundedAnswer(
        status=status,
        answer=text,
        citations=ids
        if ids is not None
        else [Citation(citation_id="C1", chunk_id=UUID(int=1))],
    )


def test_citation_metadata_is_trusted_and_page_is_nullable():
    chunk = replace(_chunk(1), content="The exact filing excerpt.")
    parts = citation_parts(answer(), {chunk.id: chunk})
    assert parts[0]["data"]["excerpt"] == chunk.content
    assert parts[0]["data"]["page"] is None
    assert parts[0]["data"]["section"] == "Item 7"


def test_grouped_citation_markers_are_normalized_before_validation():
    output = answer(
        "Two supported claims. [C1, C2]",
        [
            Citation(citation_id="C1", chunk_id=UUID(int=1)),
            Citation(citation_id="C2", chunk_id=UUID(int=2)),
        ],
    )

    normalized = normalize_citation_markers(output)

    assert normalized.answer == "Two supported claims. [C1] [C2]"
    validate_answer(normalized, {UUID(int=1): _chunk(1), UUID(int=2): _chunk(2)})


@pytest.mark.parametrize(
    "output",
    [
        answer(ids=[]),
        answer("Unsupported."),
        answer("Claim. [C2]"),
        answer("Claim. [C1]\n\nUncited claim."),
        answer("# Uncited factual heading\nClaim. [C1]"),
        answer("Claim. [C1] [C01]"),
        answer(ids=[Citation(citation_id="C1", chunk_id=UUID(int=2))]),
        answer(ids=[Citation(citation_id="C1", chunk_id=UUID(int=1))] * 2),
        answer(ids=[Citation(citation_id="bad", chunk_id=UUID(int=1))]),
        answer(status="refused"),
        answer(status="insufficient_evidence"),
        answer(" "),
    ],
)
def test_invalid_grounding_fails_closed(output):
    with pytest.raises(GroundingError):
        validate_answer(output, {UUID(int=1): _chunk(1)})


@pytest.mark.parametrize("status", ["refused", "insufficient_evidence"])
def test_abstentions_need_no_citations(status):
    cleaned = safe_status_answer(answer("Unsupported factual claim.", [], status))
    assert cleaned.answer == SAFE_STATUS_TEXT[status]
    validate_answer(cleaned, {})


@pytest.mark.parametrize("status", ["refused", "insufficient_evidence"])
def test_uncited_facts_cannot_hide_in_non_answer_status(status):
    with pytest.raises(GroundingError, match="server-approved wording"):
        validate_answer(answer("Apple revenue was $999 billion.", [], status), {})
