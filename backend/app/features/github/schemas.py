from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas import ConversationView


class ConnectionInput(BaseModel):
    owner: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")
    name: str = Field(min_length=1, max_length=200)
    token: str = Field(min_length=10, max_length=1000)


class ConnectionUpdate(BaseModel):
    token: str | None = Field(default=None, min_length=10, max_length=1000)
    enabled: bool | None = None


class ConnectionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    owner: str
    name: str
    enabled: bool
    demo: bool
    status: str
    error: str | None
    last_discovery: datetime | None
    retry_at: datetime | None


class RepositoryUpdate(BaseModel):
    enabled: bool | None = None
    ai_enabled: bool | None = None


class RepositoryView(BaseModel):
    id: str
    connection_id: str
    source_id: str
    owner: str
    name: str
    full_name: str
    web_url: str
    default_branch: str
    archived: bool
    enabled: bool
    ai_enabled: bool
    status: str
    error: str | None
    demo: bool
    last_sync: datetime | None


class PullRequestView(BaseModel):
    number: int
    title: str
    url: str
    state: str


class IssueView(BaseModel):
    id: str
    repository_id: str
    repository: str
    owner: str
    item_id: str
    number: int
    title: str
    description: str
    author: str
    web_url: str
    state: str
    local_status: str
    labels: list[str]
    assignees: list[str]
    milestone: str | None
    pull_requests: list[PullRequestView]
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    ai_enabled: bool
    demo: bool
    codex_prompt: str


class CommentView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    author: str
    body: str
    web_url: str
    updated_at: datetime


class IssueDetail(IssueView):
    comments: list[CommentView]
    conversations: list[ConversationView]


class IssuePage(BaseModel):
    items: list[IssueView]
    total: int


class SyncInput(BaseModel):
    connection_id: str | None = None
    repository_id: str | None = None


class LocalStatusInput(BaseModel):
    status: str = Field(pattern="^(new|in_progress|done|archived)$")


class ConnectionTest(BaseModel):
    ok: bool
    repositories: int
    message: str
