from uuid import UUID

from pydantic import BaseModel, Field


class AgentSettings(BaseModel):
    model: str = Field(default="", max_length=200)
    embedding_model: str = Field(default="text-embedding-3-small", max_length=200)
    instructions: str = Field(max_length=15000)
    style: str = Field(max_length=2000)
    daily_limit: int = Field(ge=1, le=10000)
    paused: bool
    allowed_actions: list[str]


class KeySettings(BaseModel):
    api_key: str = Field(min_length=10, max_length=1000)


class MicrosoftSettings(BaseModel):
    tenant_id: UUID
    client_id: UUID
    client_secret: str = Field(default="", max_length=2000)


class AuthStart(BaseModel):
    kind: str | None = None
    write: bool = False


class SourceInput(BaseModel):
    kind: str
    name: str = Field(min_length=1, max_length=300)
    config: dict = Field(default_factory=dict)
    enabled: bool = True
    ai_enabled: bool = False
    writable: bool = False


class SourceUpdate(BaseModel):
    enabled: bool | None = None
    ai_enabled: bool | None = None
    writable: bool | None = None
    days: int | None = Field(default=None, ge=1, le=3650)
