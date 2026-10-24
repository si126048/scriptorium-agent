"""Persistent unified conversations, algorithm entities and checkpointed research.

This imports a frozen schema snapshot, never the mutable runtime metadata.
"""
from alembic import op
from scriptorium.research.schema_v3 import metadata

revision = 'research_0003'
down_revision = 'research_0002'
branch_labels = None
depends_on = None
NEW_TABLES = ['r_conversations', 'r_messages', 'r_entities', 'r_research_runs', 'r_research_steps', 'r_decisions']


def upgrade():
    metadata.create_all(op.get_bind(), tables=[t for t in metadata.sorted_tables if t.name in NEW_TABLES])


def downgrade():
    metadata.drop_all(op.get_bind(), tables=[t for t in metadata.sorted_tables if t.name in NEW_TABLES])
