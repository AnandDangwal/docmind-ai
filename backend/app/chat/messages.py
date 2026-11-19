from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)


class UIMessagePart(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str


class UIMessage(BaseModel):
    id: str
    role: Literal["user", "assistant", "system"]
    parts: list[UIMessagePart]


class ChatStreamRequest(BaseModel):
    thread_id: UUID = Field(alias="threadId")
    messages: list[UIMessage]
    replace_message_id: UUID | None = Field(default=None, alias="replaceMessageId")

    @model_validator(mode="after")
    def require_question(self) -> ChatStreamRequest:
        if not self.messages or self.messages[-1].role != "user":
            raise ValueError("A final user message is required")
        if not text_from_parts(ui_message_to_parts(self.messages[-1])).strip():
            raise ValueError("A nonblank user text message is required")
        if (
            self.replace_message_id is not None
            and self.messages[-1].id != str(self.replace_message_id)
        ):
            raise ValueError("The replacement target must be the final user message")
        return self


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


def text_from_parts(parts: list[dict]) -> str:
    return "\n".join(
        part["text"]
        for part in parts
        if part.get("type") == "text" and isinstance(part.get("text"), str)
    )


def stored_messages_to_history(messages: list) -> list[ModelMessage]:
    history: list[ModelMessage] = []
    for message in messages:
        text = text_from_parts(message.parts)
        if not text.strip():
            continue
        if message.role == "user":
            history.append(ModelRequest(parts=[UserPromptPart(text)]))
        elif message.role == "assistant":
            history.append(ModelResponse(parts=[TextPart(text)]))
    return history
