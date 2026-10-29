from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    citation_id: str = Field(
        description="Short display label such as C1 or C2; never a chunk UUID"
    )
    chunk_id: UUID = Field(description="Exact UUID of the cited exposed chunk")


class GroundedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["answered", "insufficient_evidence", "refused"]
    answer: str = Field(min_length=1)
    citations: list[Citation]
