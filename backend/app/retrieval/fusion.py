from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from uuid import UUID

from app.retrieval.models import FusedHit, SearchHit

RRF_K = 60


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[SearchHit]],
    *,
    k: int = RRF_K,
) -> list[FusedHit]:
    if k <= 0:
        raise ValueError("k must be positive")

    scores: dict[UUID, float] = defaultdict(float)
    best_ranks: dict[UUID, int] = {}
    chunks = {}
    source_hits: dict[UUID, list[SearchHit]] = defaultdict(list)

    for ranking in rankings:
        seen = set()
        for hit in ranking:
            chunk_id = hit.chunk.id
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
            scores[chunk_id] += 1.0 / (k + hit.rank)
            best_ranks[chunk_id] = min(best_ranks.get(chunk_id, hit.rank), hit.rank)
            chunks.setdefault(chunk_id, hit.chunk)
            source_hits[chunk_id].append(hit)

    ordered_ids = sorted(
        scores,
        key=lambda chunk_id: (
            -scores[chunk_id],
            best_ranks[chunk_id],
            str(chunk_id),
        ),
    )
    return [
        FusedHit(
            chunk=chunks[chunk_id],
            score=scores[chunk_id],
            source_hits=tuple(source_hits[chunk_id]),
        )
        for chunk_id in ordered_ids
    ]
