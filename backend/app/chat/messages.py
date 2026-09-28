from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UIMessagePart(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str


class UIMessage(BaseModel):
    id: str
    role: Literal["user", "assistant", "system"]
    parts: list[UIMessagePart]


class ChatStreamRequest(BaseModel):
    thread_id: UUID
    messages: list[UIMessage]


class CreateThreadRequest(BaseModel):
    title: str | None = None


class ThreadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: Literal["user", "assistant"]
    parts: list[dict[str, Any]]
    created_at: datetime


def ui_message_to_parts(msg: UIMessage) -> list[dict[str, Any]]:
    return [part.model_dump() for part in msg.parts]


def assistant_text_to_parts(text: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": text}]
