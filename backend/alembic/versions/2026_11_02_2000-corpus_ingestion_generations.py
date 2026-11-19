"""add versioned corpus ingestion generations

Revision ID: corpus_generations
Revises: 93d1907dd1b8
Create Date: 2026-11-02 20:00:00+05:30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "corpus_generations"
down_revision: str | Sequence[str] | None = "93d1907dd1b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "source_documents",
        sa.Column("content_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "source_documents",
        sa.Column("extractor_version", sa.String(length=64), nullable=True),
    )
    op.execute(
        """
        UPDATE source_documents
        SET content_hash = encode(sha256(convert_to(markdown_content, 'UTF8')), 'hex'),
            extractor_version = 'legacy-v1';
        """
    )
    op.alter_column("source_documents", "content_hash", nullable=False)
    op.alter_column("source_documents", "extractor_version", nullable=False)
    op.create_table(
        "ingestion_runs",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("extractor_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("document_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("chunk_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "verification_report",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('staging', 'active', 'retired', 'failed')",
            name=op.f("ck_ingestion_runs_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingestion_runs")),
    )
    op.create_index(
        op.f("ix_ingestion_runs_status"), "ingestion_runs", ["status"], unique=False
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_ingestion_runs_one_active
        ON ingestion_runs (status)
        WHERE status = 'active';
        """
    )
    op.execute(
        """
        INSERT INTO ingestion_runs (
            id, extractor_version, status, document_count, chunk_count,
            verification_report, activated_at
        )
        SELECT
            gen_random_uuid(),
            'legacy-v1',
            'active',
            (SELECT count(*) FROM source_documents),
            (SELECT count(*) FROM document_chunks),
            '{"passed": true, "legacy": true}'::jsonb,
            now();
        """
    )
    op.add_column(
        "document_chunks",
        sa.Column("ingestion_run_id", sa.Uuid(), nullable=True),
    )
    op.execute(
        """
        UPDATE document_chunks
        SET ingestion_run_id = (
            SELECT id FROM ingestion_runs WHERE status = 'active'
        );
        """
    )
    op.alter_column("document_chunks", "ingestion_run_id", nullable=False)
    op.create_foreign_key(
        op.f("fk_document_chunks_ingestion_run_id_ingestion_runs"),
        "document_chunks",
        "ingestion_runs",
        ["ingestion_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        op.f("ix_document_chunks_ingestion_run_id"),
        "document_chunks",
        ["ingestion_run_id"],
        unique=False,
    )
    op.drop_constraint(
        op.f("uq_document_chunks_document_id_chunk_index"),
        "document_chunks",
        type_="unique",
    )
    op.create_unique_constraint(
        op.f("uq_document_chunks_document_id_ingestion_run_id_chunk_index"),
        "document_chunks",
        ["document_id", "ingestion_run_id", "chunk_index"],
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM document_chunks
        WHERE ingestion_run_id <> (
            SELECT id FROM ingestion_runs WHERE status = 'active'
        );
        """
    )
    op.drop_constraint(
        op.f("uq_document_chunks_document_id_ingestion_run_id_chunk_index"),
        "document_chunks",
        type_="unique",
    )
    op.create_unique_constraint(
        op.f("uq_document_chunks_document_id_chunk_index"),
        "document_chunks",
        ["document_id", "chunk_index"],
    )
    op.drop_index(
        op.f("ix_document_chunks_ingestion_run_id"), table_name="document_chunks"
    )
    op.drop_constraint(
        op.f("fk_document_chunks_ingestion_run_id_ingestion_runs"),
        "document_chunks",
        type_="foreignkey",
    )
    op.drop_column("document_chunks", "ingestion_run_id")
    op.execute("DROP INDEX IF EXISTS uq_ingestion_runs_one_active;")
    op.drop_index(op.f("ix_ingestion_runs_status"), table_name="ingestion_runs")
    op.drop_table("ingestion_runs")
    op.drop_column("source_documents", "extractor_version")
    op.drop_column("source_documents", "content_hash")
