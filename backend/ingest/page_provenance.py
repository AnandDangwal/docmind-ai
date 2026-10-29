"""Recover source page numbers from branded filing footers in SEC HTML."""

from __future__ import annotations

import re
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

_REPOSITORY_DIR = Path(__file__).resolve().parents[2]
_DOWNLOAD_DIR = _REPOSITORY_DIR / "data" / "downloads"
_APPLE_PAGE_MARKER = re.compile(
    r"Apple Inc\.\s*\|\s*\d{4} Form 10-K\s*\|\s*(\d+)",
    flags=re.IGNORECASE,
)
_TOKEN = re.compile(r"[a-z0-9]+")


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"head", "script", "style", "ix:hidden"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"head", "script", "style", "ix:hidden"}:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth and data.strip():
            self.parts.append(data)


def _normalized_tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return _TOKEN.findall(normalized)


def _html_path(markdown_path: Path) -> Path:
    relative = markdown_path.resolve().relative_to(
        _REPOSITORY_DIR / "data" / "markdown"
    )
    return (_DOWNLOAD_DIR / relative).with_suffix(".htm")


class PageResolver:
    def __init__(self, pages: list[tuple[int, str]]) -> None:
        self._pages = [
            (page, " ".join(_normalized_tokens(text))) for page, text in pages
        ]

    @classmethod
    def from_markdown(cls, markdown_path: Path) -> PageResolver | None:
        try:
            html_path = _html_path(markdown_path)
        except ValueError:
            return None
        if not html_path.is_file():
            return None

        parser = _VisibleTextParser()
        parser.feed(html_path.read_text(encoding="utf-8"))
        visible_text = " ".join(parser.parts)
        markers = list(_APPLE_PAGE_MARKER.finditer(visible_text))
        if not markers:
            return None

        pages: list[tuple[int, str]] = []
        start = 0
        for marker in markers:
            pages.append((int(marker.group(1)), visible_text[start : marker.start()]))
            start = marker.end()
        return cls(pages)

    def page_for_text(self, text: str) -> int | None:
        tokens = _normalized_tokens(text)
        if len(tokens) < 6:
            return None

        width = min(14, len(tokens))
        for start in range(0, len(tokens) - width + 1, max(1, width // 2)):
            phrase = " ".join(tokens[start : start + width])
            matches = [page for page, page_text in self._pages if phrase in page_text]
            if len(matches) == 1:
                return matches[0]
        return None
