"""Read-only GitHub connections, repository scopes, issues and conditional cache."""

from alembic import op
from migrations.schema_v0002 import (
    GitHubConnection,
    GitHubRepository,
    GitHubIssue,
    GitHubComment,
    GitHubCache,
)

revision = "0002"
down_revision = "0001"
tables = [
    GitHubConnection.__table__,
    GitHubRepository.__table__,
    GitHubIssue.__table__,
    GitHubComment.__table__,
    GitHubCache.__table__,
]


def upgrade():
    for table in tables:
        table.create(op.get_bind())


def downgrade():
    for table in reversed(tables):
        table.drop(op.get_bind())
