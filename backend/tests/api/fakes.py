from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.database.models import MessageRole


@dataclass
class FakeThread:
    user_id: UUID
    title: str | None = None
    id: UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class FakeMessage:
    thread_id: UUID
    role: MessageRole
    parts: list[dict[str, Any]]
    id: UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class FakeChatStore:
    def __init__(self) -> None:
        self.threads: dict[UUID, FakeThread] = {}
        self.messages: list[FakeMessage] = []

    def seed_thread(self, *, owner_id: UUID) -> FakeThread:
        thread = FakeThread(user_id=owner_id)
        self.threads[thread.id] = thread
        return thread

    async def create_thread(
        self, _session: object, *, user_id: UUID, title: str | None
    ) -> FakeThread:
        thread = FakeThread(user_id=user_id, title=title)
        self.threads[thread.id] = thread
        return thread

    async def list_threads_for_user(
        self, _session: object, *, user_id: UUID
    ) -> list[FakeThread]:
        return sorted(
            (t for t in self.threads.values() if t.user_id == user_id),
            key=lambda t: t.created_at,
            reverse=True,
        )

    async def get_thread(
        self, _session: object, *, thread_id: UUID
    ) -> FakeThread | None:
        return self.threads.get(thread_id)

    async def list_messages_for_thread(
        self, _session: object, *, thread_id: UUID
    ) -> list[FakeMessage]:
        return [m for m in self.messages if m.thread_id == thread_id]

    async def create_message(
        self,
        _session: object,
        *,
        thread_id: UUID,
        role: MessageRole,
        parts: list[dict[str, Any]],
        message_id: UUID | None = None,
    ) -> FakeMessage:
        message = FakeMessage(thread_id=thread_id, role=role, parts=parts)
        if message_id is not None:
            message.id = message_id
        self.messages.append(message)
        return message
