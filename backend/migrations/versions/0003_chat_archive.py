"""Add persistent conversation archive."""
from alembic import op
import sqlalchemy as sa

revision = "0003_chat_archive"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("conversations", sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("conversations", "archived")
