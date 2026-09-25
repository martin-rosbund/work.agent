from pydantic import BaseModel, Field


class ConversationInput(BaseModel):
    title: str = Field(default="Neuer Arbeitschat", max_length=500)
    item_ids: list[str] = Field(default_factory=list, max_length=100)


class ChatInput(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
