from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import now, uid


class GitHubConnection(Base):
    __tablename__ = "github_connections"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    token: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    demo: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_discovery: Mapped[datetime] = mapped_column(DateTime, default=now)
    retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_discovery: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class GitHubRepository(Base):
    __tablename__ = "github_repositories"
    __table_args__ = (UniqueConstraint("connection_id", "external_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    connection_id: Mapped[str] = mapped_column(ForeignKey("github_connections.id"))
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), unique=True)
    external_id: Mapped[str] = mapped_column(String(40))
    owner: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    full_name: Mapped[str] = mapped_column(String(310))
    web_url: Mapped[str] = mapped_column(Text)
    default_branch: Mapped[str] = mapped_column(String(200), default="main")
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class GitHubIssue(Base):
    __tablename__ = "github_issues"
    __table_args__ = (UniqueConstraint("repository_id", "number"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    repository_id: Mapped[str] = mapped_column(ForeignKey("github_repositories.id"))
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id"), unique=True)
    number: Mapped[int] = mapped_column()
    state: Mapped[str] = mapped_column(String(20))
    labels: Mapped[list] = mapped_column(JSON, default=list)
    assignees: Mapped[list] = mapped_column(JSON, default=list)
    milestone: Mapped[str | None] = mapped_column(Text, nullable=True)
    pull_requests: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class GitHubComment(Base):
    __tablename__ = "github_comments"
    __table_args__ = (UniqueConstraint("issue_id", "external_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    issue_id: Mapped[str] = mapped_column(ForeignKey("github_issues.id"))
    external_id: Mapped[str] = mapped_column(String(40))
    author: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    web_url: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class GitHubCache(Base):
    __tablename__ = "github_http_cache"
    __table_args__ = (UniqueConstraint("connection_id", "path"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    connection_id: Mapped[str] = mapped_column(ForeignKey("github_connections.id"))
    path: Mapped[str] = mapped_column(Text)
    etag: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=now)
