from fastapi import APIRouter
from app.api.dependencies import Auth, DB
from . import service
from .schemas import CrmConnectionInput, CrmConnectionView, CrmOptionsView

router = APIRouter(prefix="/api/v1/crm", tags=["crm"])


@router.get("", response_model=CrmConnectionView)
def connection(session=Auth, db=DB):
    return service.connection(db=db)


@router.put("", response_model=CrmConnectionView)
def connect(body: CrmConnectionInput, session=Auth, db=DB):
    return service.connect(body, db=db)


@router.post("/test", response_model=CrmConnectionView)
def test_connection(session=Auth, db=DB):
    return service.test_connection(db=db)


@router.delete("", response_model=CrmConnectionView)
def disconnect(session=Auth, db=DB):
    return service.disconnect(db=db)


@router.get("/options/{kind}", response_model=CrmOptionsView)
def options(kind: str, session=Auth, db=DB):
    return service.options(kind, db=db)
