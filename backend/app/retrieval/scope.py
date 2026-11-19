import re

from app.retrieval.models import RetrievalFilters

_COMPANY_ALIASES = {
    "AAPL": ("apple", "aapl"),
    "AMZN": ("amazon", "amzn"),
    "GOOGL": ("alphabet", "google", "googl"),
    "MSFT": ("microsoft", "msft"),
    "NVDA": ("nvidia", "nvda"),
}
_YEAR_OR_RANGE = re.compile(r"\b((?:19|20)\d{2})(?:\s*[-–—]\s*((?:19|20)\d{2}))?\b")


_LATEST = re.compile(r"\b(?:latest|newest|most\s+recent)\b")


def filters_from_question(question: str) -> RetrievalFilters:
    normalized = question.casefold()
    tickers = tuple(
        ticker
        for ticker, aliases in _COMPANY_ALIASES.items()
        if any(re.search(rf"\b{re.escape(alias)}\b", normalized) for alias in aliases)
    )
    years: list[int] = []
    for match in _YEAR_OR_RANGE.finditer(normalized):
        first = int(match.group(1))
        last = int(match.group(2)) if match.group(2) else first
        values = (
            range(first, last + 1) if first <= last and last - first <= 20 else (first,)
        )
        years.extend(values)
    years = tuple(dict.fromkeys(years))
    return RetrievalFilters(
        tickers=tickers,
        fiscal_years=years,
        latest_only=_LATEST.search(normalized) is not None,
    )
