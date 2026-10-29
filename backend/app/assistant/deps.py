from dataclasses import dataclass, field
from uuid import UUID

from pydantic_ai import ModelRetry

from app.retrieval.models import Chunk, RetrievedPassage
from app.retrieval.retriever import DocumentRetriever


@dataclass
class DocumentAgentDeps:
    user_id: UUID
    thread_id: UUID
    retriever: DocumentRetriever
    evidence: dict[UUID, Chunk] = field(default_factory=dict)
    search_calls: int = 0
    tool_calls: int = 0

    def count_tool(self, *, search: bool = False) -> None:
        if self.tool_calls >= 8 or (search and self.search_calls >= 3):
            raise ModelRetry(
                "Tool budget exhausted. Answer from available evidence or abstain."
            )
        self.tool_calls += 1
        self.search_calls += int(search)

    def register(self, chunks: list[Chunk]) -> list[Chunk]:
        exposed = []
        for chunk in chunks:
            if chunk.id not in self.evidence and len(self.evidence) >= 40:
                continue
            self.evidence[chunk.id] = chunk
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
