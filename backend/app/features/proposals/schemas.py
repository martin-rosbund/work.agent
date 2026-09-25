from pydantic import BaseModel


class ProposalInput(BaseModel):
    kind: str
    payload: dict
    item_id: str | None = None
    conversation_id: str | None = None
    version: int | None = None


class VersionInput(BaseModel):
    version: int
