"""Phase 4 immutable real-network snapshots and location knowledge time."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260925_04"
down_revision = "20260920_03"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("graph_snapshots",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False, unique=True),
        sa.Column("feature_schema", sa.String(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False))
    op.add_column("company_locations", sa.Column("available_at",
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM graph_snapshots")):
        raise RuntimeError("Export and explicitly remove Phase 4 snapshots before downgrade")
    op.drop_column("company_locations", "available_at")
    op.drop_table("graph_snapshots")
