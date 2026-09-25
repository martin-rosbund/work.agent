from fastapi import APIRouter

from app.api.dependencies import DB, Auth
from app.api.schemas import *

from . import service
from .schemas import ItemStatus

router = APIRouter(tags=["content"])
PREFIX = "/api/v1"


@router.get(PREFIX + "/items", response_model=list[ItemView])
def items(
    kind: str | None = None,
    source_id: str | None = None,
    offset: int = 0,
    limit: int = 100,
    session=Auth,
    db=DB,
):
    return service.items(
        kind=kind,
        source_id=source_id,
        offset=offset,
        limit=limit,
        session=session,
        db=db,
    )


@router.get(PREFIX + "/items/{item_id}", response_model=ItemView)
def get_item(item_id: str, session=Auth, db=DB):
    return service.get_item(item_id=item_id, session=session, db=db)


@router.get(PREFIX + "/items/{item_id}/file")
def get_file(item_id: str, session=Auth, db=DB):
    return service.get_file(item_id=item_id, session=session, db=db)


@router.get(PREFIX + "/items/{item_id}/citation", response_model=CitationView)
def citation(
    item_id: str,
    locator: str = "Original",
    version: int | None = None,
    session=Auth,
    db=DB,
):
    return service.citation(
        item_id=item_id, locator=locator, version=version, session=session, db=db
    )


@router.patch(PREFIX + "/items/{item_id}", response_model=ItemView)
def item_status(item_id: str, body: ItemStatus, session=Auth, db=DB):
    return service.item_status(item_id=item_id, body=body, session=session, db=db)


@router.post(PREFIX + "/items/{item_id}/analyze", response_model=JobView)
def analyze_item(item_id: str, session=Auth, db=DB):
    return service.analyze_item(item_id=item_id, session=session, db=db)


@router.get(PREFIX + "/search", response_model=list[SearchHit])
def search(q: str, session=Auth, db=DB):
    return service.search(q=q, session=session, db=db)
