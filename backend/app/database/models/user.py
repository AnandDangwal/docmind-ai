from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base


class User(Base):
    """One row per authenticated user. `id` matches `auth.users.id` (FK added in Alembic)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    threads: Mapped[list["ChatThread"]] = relationship(back_populates="owner")
