"""Automatic research and source collection provenance."""
from alembic import op
from scriptorium.research.schema_v6 import metadata, NEW_TABLES
revision = 'research_0006'
down_revision = 'research_0005'
branch_labels = None
depends_on = None


def upgrade():
    metadata.create_all(op.get_bind(), tables=[t for t in metadata.sorted_tables if t.name in NEW_TABLES])


def downgrade():
    metadata.drop_all(op.get_bind(), tables=[t for t in reversed(metadata.sorted_tables) if t.name in NEW_TABLES])
