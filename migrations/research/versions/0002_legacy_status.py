"""Allow legacy anchor mappings without truncating their stable identifier."""
from alembic import op
import sqlalchemy as sa

revision = 'research_0002'
down_revision = 'research_0001'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('r_legacy', 'status', type_=sa.String(96), existing_type=sa.String(32))


def downgrade():
    # Anchor mappings must be exported before narrowing the status column.
    op.alter_column('r_legacy', 'status', type_=sa.String(32), existing_type=sa.String(96))
