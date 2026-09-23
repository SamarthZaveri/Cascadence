"""Phase 3: real locations, cases and location-scoped observations."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260920_03"
down_revision = "20260918_02"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("monitored_locations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("slug", sa.String(), nullable=False, unique=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("radius_km", sa.Float(), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint("latitude BETWEEN -80 AND 80", name="ck_location_latitude"),
        sa.CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_location_longitude"),
        sa.CheckConstraint("radius_km > 0 AND radius_km <= 20", name="ck_location_radius"))
    op.create_table("company_locations",
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id"), primary_key=True),
        sa.Column("location_id", sa.Uuid(), sa.ForeignKey("monitored_locations.id"), primary_key=True),
        sa.Column("relationship", sa.String(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False))
    op.create_table("disruption_cases",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("summary", sa.String(), nullable=False),
        sa.Column("event_start", sa.Date(), nullable=False),
        sa.Column("event_end", sa.Date()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reported_status", sa.String(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False))
    op.create_index("ix_case_company_date", "disruption_cases", ["company_id", "event_start"])
    op.add_column("signals", sa.Column("location_id", sa.Uuid(), sa.ForeignKey("monitored_locations.id")))
    op.create_index("ix_signal_location_time", "signals", ["location_id", "observed_at"])
    op.drop_constraint("ck_supply_provenance", "supply_relationships", type_="check")
    op.create_check_constraint("ck_supply_provenance", "supply_relationships", "provenance IN ('sec_filing','public_source','synthetic')")


def downgrade():
    db = op.get_bind()
    if db.scalar(sa.text("SELECT count(*) FROM monitored_locations")) or db.scalar(sa.text("SELECT count(*) FROM disruption_cases")) or db.scalar(sa.text("SELECT count(*) FROM supply_relationships WHERE provenance='public_source'")):
        raise RuntimeError("Export/remove Phase 3 records explicitly before downgrading")
    op.drop_constraint("ck_supply_provenance", "supply_relationships", type_="check")
    op.create_check_constraint("ck_supply_provenance", "supply_relationships", "provenance IN ('sec_filing','synthetic')")
    op.drop_index("ix_signal_location_time", table_name="signals")
    op.drop_column("signals", "location_id")
    op.drop_table("disruption_cases")
    op.drop_table("company_locations")
    op.drop_table("monitored_locations")
