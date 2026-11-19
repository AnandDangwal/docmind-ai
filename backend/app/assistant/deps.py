from dataclasses import dataclass, field
from uuid import UUID

from pydantic_ai import ModelRetry

from app.retrieval.models import CHUNK_CONTEXT_OVERHEAD_TOKENS, Chunk, RetrievedPassage
from app.retrieval.retriever import DocumentRetriever

MAX_EVIDENCE_TOKENS = 900_000
MAX_EVIDENCE_CHUNKS = 2_000
MAX_SEARCH_CALLS = 24
MAX_TOOL_CALLS = 48


@dataclass
class DocumentAgentDeps:
    user_id: UUID
    thread_id: UUID
    retriever: DocumentRetriever
    evidence: dict[UUID, Chunk] = field(default_factory=dict)
    search_calls: int = 0
    tool_calls: int = 0
    evidence_tokens: int = 0

    def count_tool(self, *, search: bool = False) -> None:
        if self.tool_calls >= MAX_TOOL_CALLS or (
            search and self.search_calls >= MAX_SEARCH_CALLS
        ):
            raise ModelRetry(
                "Tool budget exhausted. Answer from available evidence or abstain."
            )
        self.tool_calls += 1
        self.search_calls += int(search)

    def register(self, chunks: list[Chunk]) -> list[Chunk]:
        exposed = []
        for chunk in chunks:
            if chunk.id in self.evidence:
                exposed.append(chunk)
                continue
            if len(self.evidence) >= MAX_EVIDENCE_CHUNKS:
                continue
            context_tokens = chunk.token_count + CHUNK_CONTEXT_OVERHEAD_TOKENS
            if self.evidence_tokens + context_tokens > MAX_EVIDENCE_TOKENS:
                continue
            self.evidence[chunk.id] = chunk
            self.evidence_tokens += context_tokens
            exposed.append(chunk)
        return list({chunk.id: chunk for chunk in exposed}.values())

    def register_passages(self, passages: list[RetrievedPassage]) -> list[Chunk]:
        # Preserve ranked anchors before spending the remaining budget on neighbors.
        return self.register(
            [passage.anchor for passage in passages]
            + [chunk for passage in passages for chunk in passage.neighbors]
        )

    def require_chunk(self, chunk_id: UUID) -> Chunk:
        if chunk_id not in self.evidence:
            raise ModelRetry("Only chunk IDs exposed during this turn may be read.")
        return self.evidence[chunk_id]
