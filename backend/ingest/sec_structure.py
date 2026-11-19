"""Recover high-confidence SEC filing hierarchy from normalized Markdown."""

from __future__ import annotations

import re
from dataclasses import dataclass

EXTRACTOR_VERSION = "sec-structure-v2"

_PART = re.compile(r"^PART\s+(I|II|III|IV)\.?$", re.IGNORECASE)
_ITEM = re.compile(r"^ITEM\s+(1[0-6]|[1-9])([A-C])?\.?\s*(.*)$", re.IGNORECASE)
_MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+")
_TABLE_LINE = re.compile(r"^\s*\|.*\|\s*$")
_BOLD_LINE = re.compile(r"^\*\*(.+?)\*\*$")
_MARKDOWN_LINK = re.compile(r"\[([^]]+)]\([^)]+\)")

_ITEM_TITLES = {
    "1": "Business", "1A": "Risk Factors", "1B": "Unresolved Staff Comments",
    "1C": "Cybersecurity", "2": "Properties", "3": "Legal Proceedings",
    "4": "Mine Safety Disclosures",
    "5": "Market for Registrant's Common Equity and Related Stockholder Matters",
    "6": "Reserved",
    "7": "Management's Discussion and Analysis of Financial Condition and Results of Operations",
    "7A": "Quantitative and Qualitative Disclosures About Market Risk",
    "8": "Financial Statements and Supplementary Data",
    "9": "Changes in and Disagreements With Accountants", "9A": "Controls and Procedures",
    "9B": "Other Information",
    "9C": "Disclosure Regarding Foreign Jurisdictions That Prevent Inspections",
    "10": "Directors, Executive Officers and Corporate Governance",
    "11": "Executive Compensation",
    "12": "Security Ownership of Certain Beneficial Owners and Management",
    "13": "Certain Relationships and Related Transactions, and Director Independence",
    "14": "Principal Accountant Fees and Services",
    "15": "Exhibits and Financial Statement Schedules", "16": "Form 10-K Summary",
}
_ITEM_ORDER = {item: index for index, item in enumerate(_ITEM_TITLES)}


@dataclass(frozen=True, slots=True)
class StructuralHeading:
    level: int
    label: str
    confidence: str


def _plain_line(line: str) -> str:
    value = _MARKDOWN_HEADING.sub("", line.strip())
    if _TABLE_LINE.fullmatch(value):
        cells = [cell.strip() for cell in value.strip("|").split("|")]
        value = " ".join(cells[:2])
        value = _MARKDOWN_LINK.sub(r"\1", value)
    return " ".join(value.split())


def canonical_heading(line: str) -> StructuralHeading | None:
    """Return a canonical PART/ITEM heading only for a standalone line."""
    text = _plain_line(line)
    part = _PART.fullmatch(text)
    if part:
        return StructuralHeading(1, f"PART {part.group(1).upper()}", "canonical")
    match = _ITEM.fullmatch(text)
    if not match:
        return None
    item = f"{match.group(1)}{(match.group(2) or '').upper()}"
    if item not in _ITEM_TITLES:
        return None
    supplied_title = match.group(3).strip(" .:-")
    canonical_title = _ITEM_TITLES[item]
    if supplied_title:
        supplied_words = set(re.findall(r"[a-z]+", supplied_title.casefold()))
        title_words = set(re.findall(r"[a-z]+", canonical_title.casefold()))
        if len(supplied_words & title_words) < min(2, len(title_words)):
            return None
    return StructuralHeading(2, f"Item {item}. {canonical_title}", "canonical")


def normalize_markdown_structure(markdown: str) -> str:
    """Promote canonical headings while ignoring TOC and repeated/backward labels."""
    lines = markdown.splitlines()
    candidates = [(i, h) for i, line in enumerate(lines) if (h := canonical_heading(line))]
    occurrences: dict[str, list[int]] = {}
    for index, heading in candidates:
        if heading.label.startswith("Item "):
            occurrences.setdefault(heading.label.split()[1].rstrip("."), []).append(index)
    early = [index for index, _ in candidates if index < max(250, len(lines) // 8)]
    compact_runs: list[list[int]] = []
    for index in early:
        if not compact_runs or index - compact_runs[-1][-1] > 6:
            compact_runs.append([index])
        else:
            compact_runs[-1].append(index)
    toc_runs = [run for run in compact_runs if len(run) >= 8]
    toc_end = max((run[-1] for run in toc_runs), default=-1)
    promoted: dict[int, StructuralHeading] = {}
    for index, heading in candidates:
        if heading.label.startswith("PART "):
            if index > toc_end:
                promoted[index] = heading
            continue
        item = heading.label.split()[1].rstrip(".")
        eligible = [value for value in occurrences[item] if value > toc_end]
        if toc_end >= 0 and not eligible:
            continue
        selected = eligible[0] if eligible else occurrences[item][0]
        if index == selected:
            promoted[index] = heading
    table_insertions: dict[int, StructuralHeading] = {}
    for index, heading in promoted.items():
        if not _TABLE_LINE.fullmatch(lines[index]):
            continue
        start = index
        while start > 0 and _TABLE_LINE.fullmatch(lines[start - 1]):
            start -= 1
        table_insertions[start] = heading

    output = []
    for index, line in enumerate(lines):
        if index in table_insertions:
            heading = table_insertions[index]
            output.append(f"{'#' * heading.level} {heading.label}")
            output.append("")
        heading = promoted.get(index)
        if heading is None or _TABLE_LINE.fullmatch(line):
            output.append(line)
        else:
            output.append(f"{'#' * heading.level} {heading.label}")
    for index, line in enumerate(output):
        match = _BOLD_LINE.fullmatch(line.strip())
        if not match or index in promoted:
            continue
        title = " ".join(match.group(1).split())
        words = title.split()
        if (
            2 <= len(words) <= 14
            and len(title) <= 120
            and not title.endswith((".", ";", ":"))
            and any(character.isalpha() for character in title)
        ):
            output[index] = f"### {title}"
    return "\n".join(output).rstrip() + "\n"


def item_order(label: str) -> int | None:
    match = re.match(r"Item\s+([0-9]+[A-C]?)", label, re.IGNORECASE)
    return _ITEM_ORDER.get(match.group(1).upper()) if match else None
