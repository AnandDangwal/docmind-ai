"""Create, verify, activate, and roll back corpus generations."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.database.models import IngestionRun


def active_run(session: Session) -> IngestionRun:
    run = session.scalar(select(IngestionRun).where(IngestionRun.status == "active"))
    if run is None:
        raise ValueError("No active corpus generation exists; run the migration first")
    return run


def create_staging_run(session: Session, extractor_version: str) -> IngestionRun:
    if session.scalar(select(IngestionRun.id).where(IngestionRun.status == "staging")):
        raise ValueError("A staging corpus generation already exists")
    run = IngestionRun(extractor_version=extractor_version, status="staging")
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def activate_run(session: Session, run_id: UUID) -> IngestionRun:
    run = session.get(IngestionRun, run_id)
    if run is None:
        raise ValueError(f"Unknown ingestion generation: {run_id}")
    if run.status not in {"staging", "retired"}:
        raise ValueError(f"Generation {run_id} cannot be activated from {run.status}")
    if run.verification_report.get("passed") is not True:
        raise ValueError("Only a verified generation can be activated")
    session.execute(
        update(IngestionRun)
        .where(IngestionRun.status == "active")
        .values(status="retired")
    )
    run.status = "active"
    run.activated_at = datetime.now(UTC)
    session.commit()
    return run
