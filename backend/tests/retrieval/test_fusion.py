from __future__ import annotations

from datetime import date
from uuid import UUID

import pytest

from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.models import Chunk, SearchHit


def _chunk(value: int) -> Chunk:
    chunk_id = UUID(int=value)
    return Chunk(
        id=chunk_id,
        document_id=UUID(int=100 + value),
        chunk_index=value,
        content=f"chunk {value}",
        page=None,
        section="Item 7",
        token_count=2,
        ticker="AAPL",
        company_name="Apple Inc.",
        filing_type="10-K",
        filing_date=date(2023, 11, 3),
        fiscal_year=2023,
        accession_number="0000320193-23-000106",
        source_url="https://example.test/filing",
    )


def _hit(value: int, source: str, rank: int) -> SearchHit:
    return SearchHit(
        chunk=_chunk(value),
        source=source,  # type: ignore[arg-type]
        rank=rank,
        score=1.0 / rank,
    )


def test_rrf_rewards_hits_found_by_both_rankings() -> None:
    semantic = [_hit(1, "semantic", 1), _hit(2, "semantic", 2)]
    lexical = [_hit(2, "lexical", 1), _hit(3, "lexical", 2)]

    fused = reciprocal_rank_fusion([semantic, lexical])

    assert [hit.chunk.id for hit in fused] == [UUID(int=2), UUID(int=1), UUID(int=3)]
    assert fused[0].score == pytest.approx(1 / 62 + 1 / 61)
    assert [hit.source for hit in fused[0].source_hits] == ["semantic", "lexical"]


def test_rrf_handles_disjoint_and_empty_rankings() -> None:
    fused = reciprocal_rank_fusion([[], [_hit(2, "lexical", 1)]])

    assert [hit.chunk.id for hit in fused] == [UUID(int=2)]


def test_rrf_counts_duplicate_chunk_only_once_per_ranking() -> None:
    duplicate = _hit(1, "semantic", 2)

    fused = reciprocal_rank_fusion([[_hit(1, "semantic", 1), duplicate]])

    assert fused[0].score == pytest.approx(1 / 61)
    assert len(fused[0].source_hits) == 1


def test_rrf_uses_best_rank_then_id_for_deterministic_ties() -> None:
    fused = reciprocal_rank_fusion([[_hit(2, "semantic", 1)], [_hit(1, "lexical", 1)]])

    assert [hit.chunk.id for hit in fused] == [UUID(int=1), UUID(int=2)]


def test_rrf_rejects_non_positive_k() -> None:
    with pytest.raises(ValueError, match="k must be positive"):
        reciprocal_rank_fusion([], k=0)
