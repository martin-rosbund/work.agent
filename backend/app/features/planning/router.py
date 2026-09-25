from fastapi import APIRouter, Query

from app.api.dependencies import DB, Auth

from . import service
from .schemas import CalendarView, TaskView

router = APIRouter(prefix="/api/v1", tags=["Aufgaben und Kalender"])


@router.get("/tasks", response_model=list[TaskView])
def tasks(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    session=Auth,
    db=DB,
):
    return service.tasks(db, offset, limit)


@router.get("/calendar", response_model=list[CalendarView])
def calendar(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    session=Auth,
    db=DB,
):
    return service.calendar(db, offset, limit)
