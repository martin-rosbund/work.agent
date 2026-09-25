from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.api.dependencies import DB, Auth
from app.api.schemas import *

from . import service

router = APIRouter(tags=["system"])
PREFIX = "/api/v1"


@router.get(PREFIX + "/docs", include_in_schema=False, response_class=HTMLResponse)
def api_documentation(request: Request):
    return service.api_documentation(request=request)


@router.get(PREFIX + "/health", response_model=Health)
def health(db=DB):
    return service.health(db=db)


@router.get(PREFIX + "/activity", response_model=ActivityView)
def activity(session=Auth, db=DB):
    return service.activity(session=session, db=db)


@router.get(PREFIX + "/events")
async def events(request: Request, after: int | None = None, session=Auth):
    return await service.events(request=request, after=after, session=session)
