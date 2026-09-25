"""Explicit public contracts. Persistence columns never define the HTTP contract."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Ok(BaseModel):
    ok: bool = True


class Health(BaseModel):
    status: str


class AuthStatus(BaseModel):
    initialized: bool
    authenticated: bool
    csrf: str | None = None
    demo: bool


class SessionCreated(BaseModel):
    csrf: str


class AgentProfile(BaseModel):
    model: str
    embedding_model: str
    instructions: str
    style: str
    daily_limit: int
    paused: bool
    allowed_actions: list[str]


class MicrosoftConfiguration(BaseModel):
    tenant_id: str | None = None
    client_id: str | None = None


class MicrosoftAccount(BaseModel):
    oid: str | None = None
    name: str | None = None
    username: str | None = None


class WorkerStatus(BaseModel):
    heartbeat: str | None = None


class SettingsView(BaseModel):
    agent: AgentProfile
    openai_configured: bool
    microsoft: MicrosoftConfiguration
    microsoft_configured: bool
    account: MicrosoftAccount
    redirect_uri: str
    worker: WorkerStatus


class ModelTest(BaseModel):
    ok: bool
    answer: str
    embedding_dimension: int


class AuthUrl(BaseModel):
    url: str


class MicrosoftProfile(BaseModel):
    displayName: str | None = None
    userPrincipalName: str | None = None


class DiscoveryEntry(BaseModel):
    # Graph discovery resources differ by kind and are not persisted domain models.
    model_config = ConfigDict(extra="allow")
    id: str
    name: str | None = None
    displayName: str | None = None
    topic: str | None = None


class CitationView(BaseModel):
    text: str
    locator: str
    version: int


class Citation(BaseModel):
    item_id: str
    title: str = ""
    locator: str = "Original"
    version: int = 1
    available: bool | None = None
    chunk_id: str | None = None


class SourceConfiguration(BaseModel):
    model_config = ConfigDict(extra="allow")
    demo: bool = False
    days: int = 90
    folder_id: str | None = None
    chat_id: str | None = None
    team_id: str | None = None
    channel_id: str | None = None
    calendar_id: str | None = None
    list_id: str | None = None
    drive_id: str | None = None
    repository_id: str | None = None
    connection_id: str | None = None


class SourceTime(BaseModel):
    dateTime: str
    timeZone: str | None = None


class ItemMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")
    demo: bool = False
    start: SourceTime | None = None
    end: SourceTime | None = None
    due: SourceTime | str | None = None
    citations: list[Citation] = Field(default_factory=list)


class ActionPayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    source_id: str | None = None
    item_id: str | None = None
    title: str | None = None
    subject: str | None = None
    body: str | None = None
    content: str | None = None
    recipient: str | None = None
    due: str | None = None
    start: str | None = None
    end: str | None = None
    attendees: list[str] = Field(default_factory=list)
    expected_version: int | None = None


class ActionResult(BaseModel):
    model_config = ConfigDict(extra="allow")
    error: str | None = None
    message: str | None = None


class SourceView(BaseModel):
    id: str
    kind: str
    name: str
    config: SourceConfiguration
    enabled: bool
    ai_enabled: bool
    writable: bool
    status: str
    error: str | None = None
    cursor: dict[str, Any]
    last_sync: datetime | None = None
    next_sync: datetime
    created_at: datetime


class ItemView(BaseModel):
    id: str
    source_id: str
    external_id: str
    kind: str
    title: str
    body: str
    sender: str
    occurred_at: datetime
    thread_key: str
    web_url: str
    meta: ItemMetadata
    content_hash: str
    available: bool
    status: str
    summary: str
    version: int
    processing: str
    processing_error: str | None = None
    source_name: str
    source_kind: str
    ai_enabled: bool


class UnavailableItem(BaseModel):
    id: str
    available: bool = False
    title: str


class JobView(BaseModel):
    id: str
    kind: str
    payload: dict[str, Any]
    dedupe_key: str | None = None
    status: str
    attempts: int
    run_after: datetime
    started_at: datetime | None = None
    error: str | None = None
    created_at: datetime


class SearchHit(BaseModel):
    item_id: str
    chunk_id: str
    title: str
    locator: str
    text: str
    version: int
    score: float | None = None


class KnowledgeVersionView(BaseModel):
    id: str
    item_id: str
    version: int
    title: str
    content: str
    citations: list[Citation]
    created_at: datetime


class ConversationView(BaseModel):
    id: str
    title: str
    item_ids: list[str]
    thread_key: str | None = None
    created_at: datetime


class MessageView(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    citations: list[Citation]
    created_at: datetime


class ProposalView(BaseModel):
    id: str
    conversation_id: str | None = None
    item_id: str | None = None
    kind: str
    payload: ActionPayload
    citations: list[Citation]
    version: int
    status: str
    approved_hash: str | None = None
    result: ActionResult
    created_at: datetime


class ConversationDetail(BaseModel):
    conversation: ConversationView
    items: list[ItemView | UnavailableItem]
    messages: list[MessageView]
    proposals: list[ProposalView]


class AuditView(BaseModel):
    id: int
    action: str
    detail: dict[str, Any]
    created_at: datetime


class UsageSummary(BaseModel):
    calls: int
    input_tokens: int
    output_tokens: int


class ActivityView(BaseModel):
    jobs: list[JobView]
    audit: list[AuditView]
    usage: UsageSummary
    worker: WorkerStatus
