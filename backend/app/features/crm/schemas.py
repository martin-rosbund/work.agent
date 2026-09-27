from pydantic import BaseModel, Field


class CrmConnectionInput(BaseModel):
    url: str = Field(max_length=1000)
    api_url: str = Field(default="", max_length=1000)
    token: str = Field(default="", max_length=4000)


class CrmConnectionView(BaseModel):
    url: str = ""
    api_url: str = ""
    configured: bool = False
    name: str = ""
    person: str = ""


class CrmChoice(BaseModel):
    value: str
    label: str
    closed: bool = False


class CrmOptionsView(BaseModel):
    statuses: list[CrmChoice]
    categories: list[CrmChoice] = []
    types: list[CrmChoice] = []
    forecasts: list[CrmChoice] = []
    origins: list[CrmChoice] = []
    loss_reasons: list[CrmChoice] = []
    priorities: list[CrmChoice] = []
