from app.retrieval.scope import filters_from_question


def test_extracts_known_companies_and_years_in_stable_order():
    filters = filters_from_question(
        "Compare Amazon, Apple, Google, Microsoft and Nvidia in 2024 and 2023."
    )

    assert filters.tickers == ("AAPL", "AMZN", "GOOGL", "MSFT", "NVDA")
    assert filters.fiscal_years == (2024, 2023)


def test_expands_inclusive_year_ranges() -> None:
    filters = filters_from_question("Compare Amazon from 2021-2025")

    assert filters.fiscal_years == (2021, 2022, 2023, 2024, 2025)


def test_company_aliases_require_whole_words():
    filters = filters_from_question("Compare pineapple sales with googling trends.")

    assert filters.tickers == ()


def test_detects_latest_filing_scope():
    assert filters_from_question("Summarize Apple's latest filing").latest_only is True
    assert (
        filters_from_question("Use the most recent filing for Microsoft").latest_only
        is True
    )
    assert filters_from_question("Summarize Apple's 2024 filing").latest_only is False
