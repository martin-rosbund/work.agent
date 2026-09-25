from pydantic import BaseModel


class ItemStatus(BaseModel):
    status: str
