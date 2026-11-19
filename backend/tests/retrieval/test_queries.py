from __future__ import annotations

import pytest
from sqlalchemy.dialects import postgresql

from app.database.models import EMBEDDING_DIMENSIONS
from app.retrieval.models import RetrievalFilters
from app.retrieval.queries import (
    build_full_text_query,
    build_semantic_query,
    lexical_query,
)


def _sql(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": False},
        )
    )


def test_semantic_query_uses_cosine_distance_join_filters_and_limit() -> None:
    statement = build_semantic_query(
        [0.0] * EMBEDDING_DIMENSIONS,
        limit=25,
        filters=RetrievalFilters(
            tickers=("aapl",),
            fiscal_years=(2023,),
            filing_types=("10-k",),
        ),
    )
    sql = _sql(statement)

    assert "<=>" in sql
    assert "JOIN source_documents" in sql
    assert "JOIN ingestion_runs" in sql
    assert "ingestion_runs.status" in sql
    assert "source_documents.ticker IN" in sql
    assert "source_documents.fiscal_year IN" in sql
    assert "source_documents.filing_type IN" in sql
    assert "ORDER BY (document_chunks.embedding <=>" in sql
    assert statement._limit_clause.value == 25


def test_full_text_query_uses_web_query_rank_match_and_stable_order() -> None:
    statement = build_full_text_query(
        "net sales",
        limit=50,
        filters=RetrievalFilters(),
    )
    sql = _sql(statement)

    assert "websearch_to_tsquery" in sql
    assert "@@" in sql
    assert "ts_rank_cd" in sql
    assert "JOIN ingestion_runs" in sql
    assert "ORDER BY ts_rank_cd" in sql
    assert "document_chunks.id ASC" in sql
    assert statement._limit_clause.value == 50


def test_latest_filter_selects_latest_active_filing_per_company() -> None:
    statement = build_full_text_query(
        "important disclosures",
        limit=50,
        filters=RetrievalFilters(latest_only=True),
    )
    sql = _sql(statement)

    assert "max(source_documents_1.filing_date)" in sql
    assert "source_documents_1.ticker = source_documents.ticker" in sql
    assert "ingestion_runs_1.status" in sql
    assert "source_documents.filing_date = (SELECT" in sql


def test_lexical_query_uses_relevant_terms_with_or_semantics() -> None:
    query = lexical_query(
        "Compare the performance of Amazon and Microsoft in financial year 2024 "
        "based on revenue, loss, profit, and cash flow metrics."
    )

    assert query == "revenue OR loss OR profit OR cash OR flow"


def test_filters_are_normalized_and_deduplicated() -> None:
    filters = RetrievalFilters(
        tickers=(" aapl ", "AAPL"),
        fiscal_years=(2023, 2023),
        filing_types=("10-k",),
    )

    assert filters.tickers == ("AAPL",)
    assert filters.fiscal_years == (2023,)
    assert filters.filing_types == ("10-K",)


def test_semantic_query_rejects_wrong_vector_dimension() -> None:
    with pytest.raises(ValueError, match="Expected query embedding dimension"):
        build_semantic_query(
            [0.0],
            limit=10,
            filters=RetrievalFilters(),
        )
