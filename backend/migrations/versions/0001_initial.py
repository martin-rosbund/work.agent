"""Initial local workspace schema."""

from alembic import op
from migrations.schema_v0001 import Base

revision = "0001"
down_revision = None


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(op.get_bind())
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX ix_chunk_fts ON chunks USING gin(to_tsvector('german', text))"
        )


def downgrade():
    Base.metadata.drop_all(op.get_bind())
