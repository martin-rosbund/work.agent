from fastapi import APIRouter, File, UploadFile

from app.api.dependencies import DB, Auth
from app.api.schemas import *

from . import service
from .schemas import NoteInput, RestoreVersion

router = APIRouter(tags=["knowledge"])
PREFIX = "/api/v1"


@router.post(PREFIX + "/documents", response_model=ItemView)
async def upload(file: UploadFile = File(...), session=Auth, db=DB):
    return await service.upload(file=file, session=session, db=db)


@router.post(PREFIX + "/knowledge", response_model=ItemView)
def create_note(body: NoteInput, session=Auth, db=DB):
    return service.create_note(body=body, session=session, db=db)


@router.put(PREFIX + "/knowledge/{item_id}", response_model=ItemView)
def update_note(item_id: str, body: NoteInput, session=Auth, db=DB):
    return service.update_note(item_id=item_id, body=body, session=session, db=db)


@router.get(
    PREFIX + "/knowledge/{item_id}/versions", response_model=list[KnowledgeVersionView]
)
def versions(item_id: str, session=Auth, db=DB):
    return service.versions(item_id=item_id, session=session, db=db)


@router.post(PREFIX + "/knowledge/{item_id}/restore", response_model=ItemView)
def restore_note(item_id: str, body: RestoreVersion, session=Auth, db=DB):
    return service.restore_note(item_id=item_id, body=body, session=session, db=db)


@router.post(PREFIX + "/knowledge/reindex/all", response_model=Ok)
def reindex(session=Auth, db=DB):
    return service.reindex(session=session, db=db)
