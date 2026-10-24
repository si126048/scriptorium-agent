"""Initial independent research schema."""
from alembic import op
from scriptorium.research.schema_v1 import metadata

revision = 'research_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    metadata.create_all(op.get_bind())


def downgrade():
    metadata.drop_all(op.get_bind())
