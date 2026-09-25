from fastapi import APIRouter, Request, Response

from app.api.dependencies import DB, Auth
from app.api.schemas import *

from . import service
from .schemas import (
    AgentSettings,
    AuthStart,
    KeySettings,
    MicrosoftSettings,
    SourceInput,
    SourceUpdate,
)

router = APIRouter(tags=["connections"])
PREFIX = "/api/v1"


@router.get(PREFIX + "/settings", response_model=SettingsView)
def settings(session=Auth, db=DB):
    return service.settings(session=session, db=db)


@router.put(PREFIX + "/settings/agent", response_model=Ok)
def update_agent(body: AgentSettings, session=Auth, db=DB):
    return service.update_agent(body=body, session=session, db=db)


@router.put(PREFIX + "/settings/openai", response_model=Ok)
def openai_settings(body: KeySettings, session=Auth, db=DB):
    return service.openai_settings(body=body, session=session, db=db)


@router.get(PREFIX + "/openai/models", response_model=list[str])
def models(session=Auth, db=DB):
    return service.models(session=session, db=db)


@router.post(PREFIX + "/openai/test", response_model=ModelTest)
def openai_test(session=Auth, db=DB):
    return service.openai_test(session=session, db=db)


@router.put(PREFIX + "/settings/microsoft", response_model=Ok)
def microsoft_settings(body: MicrosoftSettings, session=Auth, db=DB):
    return service.microsoft_settings(body=body, session=session, db=db)


@router.post(PREFIX + "/microsoft/auth", response_model=AuthUrl)
def microsoft_auth(body: AuthStart, response: Response, session=Auth, db=DB):
    return service.microsoft_auth(body=body, response=response, session=session, db=db)


@router.get(PREFIX + "/microsoft/callback")
def microsoft_callback(request: Request, db=DB):
    return service.microsoft_callback(request=request, db=db)


@router.post(PREFIX + "/microsoft/test", response_model=MicrosoftProfile)
def microsoft_test(session=Auth, db=DB):
    return service.microsoft_test(session=session, db=db)


@router.get(PREFIX + "/microsoft/discover/{kind}", response_model=list[DiscoveryEntry])
def discover(
    kind: str,
    parent: str | None = None,
    site_url: str | None = None,
    session=Auth,
    db=DB,
):
    return service.discover(
        kind=kind, parent=parent, site_url=site_url, session=session, db=db
    )


@router.get(PREFIX + "/sources", response_model=list[SourceView])
def sources(session=Auth, db=DB):
    return service.sources(session=session, db=db)


@router.post(PREFIX + "/sources", response_model=SourceView)
def create_source(body: SourceInput, session=Auth, db=DB):
    return service.create_source(body=body, session=session, db=db)


@router.patch(PREFIX + "/sources/{source_id}", response_model=SourceView)
def update_source(source_id: str, body: SourceUpdate, session=Auth, db=DB):
    return service.update_source(source_id=source_id, body=body, session=session, db=db)


@router.post(PREFIX + "/sources/{source_id}/sync", response_model=JobView)
def sync(source_id: str, session=Auth, db=DB):
    return service.sync(source_id=source_id, session=session, db=db)
