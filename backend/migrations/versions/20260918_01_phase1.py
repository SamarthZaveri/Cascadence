"""Phase 1 companies, model versions and risk history.

Revision ID: 20260918_01
Revises: 7fd68b6689ff
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260918_01"
down_revision = "7fd68b6689ff"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("neo4j_id", sa.String(), nullable=False, unique=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("ticker", sa.String()),
        sa.Column("sec_cik", sa.String()),
        sa.Column("industry", sa.String()),
        sa.Column("hq_country", sa.String()),
        sa.Column("hq_lat", sa.Float()),
        sa.Column("hq_lng", sa.Float()),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "model_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("architecture", sa.Enum("gcn", "gat", "graphsage", "temporal",
                  name="model_architecture"), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metrics", postgresql.JSONB(), nullable=False),
        sa.Column("artifact_path", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
    )
    op.create_index("uq_one_active_model", "model_versions", ["is_active"],
                    unique=True, postgresql_where=sa.text("is_active = true"))
    op.create_table(
        "risk_scores",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("model_version_id", sa.Uuid(), sa.ForeignKey("model_versions.id"),
                  nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("graph_snapshot_id", sa.String(), nullable=False),
        sa.CheckConstraint("score >= 0 AND score <= 1", name="ck_risk_score_range"),
    )
    op.create_index("ix_risk_company_time", "risk_scores", ["company_id", "computed_at", "id"])


def downgrade():
    op.drop_table("risk_scores")
    op.drop_table("model_versions")
    sa.Enum(name="model_architecture").drop(op.get_bind(), checkfirst=True)
    op.drop_table("companies")
