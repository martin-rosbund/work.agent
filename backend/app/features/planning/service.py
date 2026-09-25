from sqlalchemy import select

from app.core.models import Item, Source, uid
from app.features.content.service import items


def tasks(db, offset=0, limit=100):
    return items(kind="task", offset=offset, limit=limit, db=db)


def calendar(db, offset=0, limit=100):
    return items(kind="calendar", offset=offset, limit=limit, db=db)


def create_local_task(db, payload, origin=None):
    """Called only by approved action execution; never grants approval itself."""
    local = db.scalar(select(Source).where(Source.kind == "local_tasks"))
    if not local:
        local = Source(kind="local_tasks", name="Lokale Aufgaben", status="ok")
        db.add(local)
        db.flush()
    item = Item(
        source_id=local.id,
        external_id=uid(),
        kind="task",
        title=payload["title"],
        body=payload.get("body", ""),
        meta={"due": payload.get("due"), "origin": origin},
    )
    db.add(item)
    db.flush()
    return item
