from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal
from uuid import UUID

RetrievalSource = Literal["semantic", "lexical"]


@dataclass(frozen=True, slots=True)
class RetrievalFilters:
    tickers: tuple[str, ...] = ()
    fiscal_years: tuple[int, ...] = ()
    filing_types: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        tickers = tuple(
            dict.fromkeys(ticker.strip().upper() for ticker in self.tickers)
        )
        filing_types = tuple(
            dict.fromkeys(
                filing_type.strip().upper() for filing_type in self.filing_types
            )
        )
        fiscal_years = tuple(dict.fromkeys(self.fiscal_years))
        if any(not ticker for ticker in tickers):
            raise ValueError("tickers must not contain empty values")
        if any(not filing_type for filing_type in filing_types):
            raise ValueError("filing_types must not contain empty values")
        if any(year <= 0 for year in fiscal_years):
            raise ValueError("fiscal_years must contain positive years")
        object.__setattr__(self, "tickers", tickers)
        object.__setattr__(self, "filing_types", filing_types)
        object.__setattr__(self, "fiscal_years", fiscal_years)


@dataclass(frozen=True, slots=True)
class Chunk:
    id: UUID
    document_id: UUID
    chunk_index: int
    content: str
    page: int | None
    section: str | None
    token_count: int
    ticker: str
    company_name: str
    filing_type: str
    filing_date: date
    fiscal_year: int
    accession_number: str
    source_url: str


@dataclass(frozen=True, slots=True)
class SearchHit:
    chunk: Chunk
    source: RetrievalSource
    rank: int
    score: float


@dataclass(frozen=True, slots=True)
class FusedHit:
    chunk: Chunk
    score: float
    source_hits: tuple[SearchHit, ...]


@dataclass(frozen=True, slots=True)
class RetrievedPassage:
    rank: int
    fused_score: float
    anchor: Chunk
    neighbors: tuple[Chunk, ...]
    source_hits: tuple[SearchHit, ...]
