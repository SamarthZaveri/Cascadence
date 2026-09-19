"""Phase 2 evidence, relationship review and ingestion audit."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = "20260918_02"
down_revision = "20260918_01"
branch_labels = None
depends_on = None

def upgrade():
    op.create_index("uq_company_sec_cik", "companies", ["sec_cik"], unique=True, postgresql_where=sa.text("sec_cik IS NOT NULL"))
    op.create_table("signals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id")),
        sa.Column("source_type", sa.Enum("sec_filing", "news", "satellite", "ais", "viirs", name="signal_source_type"), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
        sa.Column("extracted_data", postgresql.JSONB(), nullable=False),
        sa.Column("severity_score", sa.Float()),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("severity_score >= 0 AND severity_score <= 1", name="ck_signal_severity"))
    op.create_index("ix_signal_company_time", "signals", ["company_id", "observed_at"])
    op.create_table("supply_relationships",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("supplier_id", sa.Uuid(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("customer_id", sa.Uuid(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("source_signal_id", sa.Uuid(), sa.ForeignKey("signals.id")),
        sa.Column("relationship_type", sa.String(), nullable=False),
        sa.Column("criticality", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("provenance", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("supplier_id <> customer_id", name="ck_supply_not_self"),
        sa.CheckConstraint("criticality >= 0 AND criticality <= 1", name="ck_supply_criticality"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_supply_confidence"),
        sa.CheckConstraint("status IN ('pending','approved','rejected')", name="ck_supply_status"),
        sa.CheckConstraint("provenance IN ('sec_filing','synthetic')", name="ck_supply_provenance"),
        sa.CheckConstraint("provenance = 'synthetic' OR source_signal_id IS NOT NULL", name="ck_supply_evidence"))
    op.create_index("ix_supply_status", "supply_relationships", ["status"])
    op.create_table("ingestion_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("tickers", postgresql.JSONB(), nullable=False),
        sa.Column("summary", postgresql.JSONB(), nullable=False),
        sa.Column("errors", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint("status IN ('running','success','partial','failed')", name="ck_ingestion_status"))
    op.add_column("risk_scores", sa.Column("input_basis", sa.String(), nullable=False, server_default="synthetic_scenario"))
    op.add_column("risk_scores", sa.Column("evidence_count", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.create_check_constraint("ck_risk_evidence_count", "risk_scores", "evidence_count >= 0")

def downgrade():
    op.drop_constraint("ck_risk_evidence_count", "risk_scores", type_="check")
    op.drop_column("risk_scores", "evidence_count")
    op.drop_column("risk_scores", "input_basis")
    op.drop_table("ingestion_runs")
    op.drop_table("supply_relationships")
    op.drop_table("signals")
    sa.Enum(name="signal_source_type").drop(op.get_bind(), checkfirst=True)
    op.drop_index("uq_company_sec_cik", table_name="companies")
