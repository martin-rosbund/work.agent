from pydantic import BaseModel, Field


class NoteInput(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(max_length=100000)
    expected_version: int | None = None


class RestoreVersion(BaseModel):
    version: int
    expected_version: int
