from pydantic import BaseModel, Field


class Login(BaseModel):
    password: str = Field(min_length=12, max_length=256)
    demo: bool = False
