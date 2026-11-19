import re
from uuid import UUID

from app.assistant.outputs import GroundedAnswer
from app.retrieval.models import Chunk

MARKER = re.compile(r"\[(C[1-9]\d*)\]")
GROUPED_MARKERS = re.compile(r"\[((?:C[1-9]\d*)(?:\s*[,;]\s*C[1-9]\d*)+)\]")
HTML_LINE_BREAK = re.compile(r"<br\s*/?>", re.IGNORECASE)
TABLE_DELIMITER = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")
SAFE_STATUS_TEXT = {
    "insufficient_evidence": (
        "There is not enough evidence in the available filings to answer this question. "
        "Please specify the company, period, and metric if applicable."
    ),
    "refused": (
        "I can't provide stock picks or trading recommendations. "
        "I can help with facts disclosed in the filings."
    ),
}


class GroundingError(ValueError):
    pass


def normalize_markdown_line_breaks(answer: GroundedAnswer) -> GroundedAnswer:
    if answer.status != "answered":
        return answer
    return answer.model_copy(
        update={"answer": HTML_LINE_BREAK.sub("\n", answer.answer)}
    )


def normalize_citation_markers(answer: GroundedAnswer) -> GroundedAnswer:
    if answer.status != "answered":
        return answer

    def expand(match: re.Match[str]) -> str:
        return " ".join(
            f"[{citation_id}]" for citation_id in re.findall(r"C\d+", match[1])
        )

    return answer.model_copy(
        update={"answer": GROUPED_MARKERS.sub(expand, answer.answer)}
    )


def safe_status_answer(answer: GroundedAnswer) -> GroundedAnswer:
    if answer.status == "answered":
        return answer
    return answer.model_copy(update={"answer": SAFE_STATUS_TEXT[answer.status]})


def _is_markdown_structure(lines: list[str], index: int) -> bool:
    line = lines[index].strip()
    if re.match(r"^#{1,6}\s+", line):
        return True
    if TABLE_DELIMITER.fullmatch(line):
        return True
    return (
        index + 1 < len(lines)
        and TABLE_DELIMITER.fullmatch(lines[index + 1].strip()) is not None
    )


def validate_answer(answer: GroundedAnswer, evidence: dict[UUID, Chunk]) -> None:
    if not answer.answer.strip():
        raise GroundingError("Answer must not be blank")
    markers = set(MARKER.findall(answer.answer))
    ids = [citation.citation_id for citation in answer.citations]
    if answer.status != "answered":
        if answer.citations or markers or re.search(r"\[C[^\]]*\]", answer.answer):
            raise GroundingError("Abstentions and refusals cannot contain citations")
        if answer.answer != SAFE_STATUS_TEXT[answer.status]:
            raise GroundingError(
                "Abstentions and refusals must use server-approved wording"
            )
        return
    if not ids or len(ids) != len(set(ids)):
        raise GroundingError("Answered output requires unique citations")
    if any(not re.fullmatch(r"C[1-9]\d*", value) for value in ids):
        raise GroundingError("Invalid citation ID")
    if markers != set(ids):
        raise GroundingError("Answer markers and declared citations must match")
    if len(re.findall(r"\[C[^\]]*\]", answer.answer)) != len(
        MARKER.findall(answer.answer)
    ):
        raise GroundingError("Malformed citation marker")
    if any(citation.chunk_id not in evidence for citation in answer.citations):
        raise GroundingError("Citation refers to evidence not retrieved this turn")
    if len({citation.chunk_id for citation in answer.citations}) != len(ids):
        raise GroundingError("Reuse one citation marker for each chunk")
    for citation in answer.citations:
        chunk = evidence[citation.chunk_id]
        if chunk.page is None and not (chunk.source_anchor or chunk.section_path or chunk.section):
            raise GroundingError("Cited evidence requires a verified page or section anchor")
    lines = answer.answer.splitlines()
    for index, line in enumerate(lines):
        line = line.strip()
        if (
            not line
            or not re.search(r"\w", line)
            or _is_markdown_structure(lines, index)
        ):
            continue
        if not MARKER.search(line):
            raise GroundingError(
                "Every substantive paragraph or bullet must cite evidence"
            )


def citation_parts(answer: GroundedAnswer, evidence: dict[UUID, Chunk]) -> list[dict]:
    validate_answer(answer, evidence)
    parts = []
    for citation in answer.citations:
        chunk = evidence[citation.chunk_id]
        parts.append(
            {
                "type": "data-citation",
                "id": citation.citation_id,
                "data": {
                    "citationId": citation.citation_id,
                    "chunkId": str(chunk.id),
                    "documentId": str(chunk.document_id),
                    "ticker": chunk.ticker,
                    "companyName": chunk.company_name,
                    "filingType": chunk.filing_type,
                    "filingDate": chunk.filing_date.isoformat(),
                    "fiscalYear": chunk.fiscal_year,
                    "page": chunk.page,
                    "section": chunk.section,
                    "sectionPath": chunk.section_path or chunk.section,
                    "sourceAnchor": chunk.source_anchor,
                    "provenanceKind": chunk.provenance_kind,
                    "excerpt": chunk.content,
                    "sourceUrl": chunk.source_url,
                },
            }
        )
    return parts
