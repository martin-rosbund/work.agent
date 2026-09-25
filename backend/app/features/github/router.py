from fastapi import APIRouter, Query

from app.api.dependencies import DB, Auth
from app.api.schemas import ConversationView, Ok

from . import service
from .schemas import (
    ConnectionInput,
    ConnectionTest,
    ConnectionUpdate,
    ConnectionView,
    IssueDetail,
    IssuePage,
    LocalStatusInput,
    RepositoryUpdate,
    RepositoryView,
    SyncInput,
)

router = APIRouter(prefix="/api/v1/github", tags=["GitHub"])


@router.get("/connections", response_model=list[ConnectionView])
def connections(session=Auth, db=DB):
    return service.connections(db)


@router.post("/connections", response_model=ConnectionView)
def create_connection(body: ConnectionInput, session=Auth, db=DB):
    return service.save_connection(db, body)


@router.patch("/connections/{identity}", response_model=ConnectionView)
def update_connection(identity: str, body: ConnectionUpdate, session=Auth, db=DB):
    return service.change_connection(db, identity, body)


@router.post("/connections/{identity}/test", response_model=ConnectionTest)
def test_connection(identity: str, session=Auth, db=DB):
    return service.test_connection(db, identity)


@router.get("/repositories", response_model=list[RepositoryView])
def repositories(session=Auth, db=DB):
    return service.repositories(db)


@router.patch("/repositories/{identity}", response_model=RepositoryView)
def update_repository(identity: str, body: RepositoryUpdate, session=Auth, db=DB):
    return service.change_repository(db, identity, body)


@router.get("/issues", response_model=IssuePage)
def issues(
    owner: str | None = None,
    repository_id: str | None = None,
    state: str | None = Query(None, pattern="^(open|closed)$"),
    label: str | None = None,
    assignee: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session=Auth,
    db=DB,
):
    return service.issues(
        db, owner, repository_id, state, label, assignee, offset, limit
    )


@router.get("/issues/{identity}", response_model=IssueDetail)
def issue_detail(identity: str, session=Auth, db=DB):
    return service.detail(db, identity)


@router.patch("/issues/{identity}", response_model=IssueDetail)
def update_issue(identity: str, body: LocalStatusInput, session=Auth, db=DB):
    return service.local_status(db, identity, body)


@router.post("/issues/{identity}/conversation", response_model=ConversationView)
def link_chat(identity: str, session=Auth, db=DB):
    return service.link_chat(db, identity)


@router.post("/sync", response_model=Ok)
def sync(body: SyncInput, session=Auth, db=DB):
    return service.synchronize(db, body)
