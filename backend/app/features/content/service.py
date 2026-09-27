from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import (
    FileResponse,
)
from sqlalchemy import select

from app import ai
from app.models import (
    Chunk,
    Item,
    KnowledgeVersion,
    Source,
)
from app.services import (
    enqueue,
    item_dict,
    serialize,
    visible_item,
)

from .schemas import ItemStatus

PREFIX = "/api/v1"


def items(
    kind: str | None = None,
    source_id: str | None = None,
    offset: int = 0,
    limit: int = 100,
    session=None,
    db=None,
):
    query = (
        select(Item)
        .join(Source)
        .where(
            Item.available.is_(True),
            Source.enabled.is_(True),
            Source.status.not_in(["forbidden", "reauth"]),
        )
    )
    if kind == "inbox":
        query = query.where(Item.kind.in_(["mail", "chat", "channel"]))
    elif kind:
        query = query.where(Item.kind.in_(kind.split(",")))
    if source_id:
        query = query.where(Item.source_id == source_id)
    return [
        item_dict(db, i, preview=True)
        for i in db.scalars(
            query.order_by(Item.occurred_at.desc())
            .offset(max(0, offset))
            .limit(min(200, max(1, limit)))
        )
    ]


def get_item(item_id: str, session=None, db=None):
    return item_dict(db, visible_item(db, item_id))


def get_file(item_id: str, session=None, db=None):
    item = visible_item(db, item_id)
    if not item.file_path or not Path(item.file_path).is_file():
        raise HTTPException(404, "Originaldatei nicht vorhanden.")
    return FileResponse(
        item.file_path, filename=item.title, media_type="application/octet-stream"
    )


def citation(
    item_id: str,
    locator: str = "Original",
    version: int | None = None,
    session=None,
    db=None,
):
    item = visible_item(db, item_id)
    requested = version or item.version
    if requested != item.version:
        if item.kind == "knowledge":
            old = db.scalar(
                select(KnowledgeVersion).where(
                    KnowledgeVersion.item_id == item.id,
                    KnowledgeVersion.version == requested,
                )
            )
            if old:
                return {
                    "text": old.content,
                    "locator": "Gespeicherte Wissensfassung",
                    "version": old.version,
                }
        raise HTTPException(
            409,
            "Diese Fundstelle bezieht sich auf eine ältere Dokumentversion. Bitte die Quelle erneut suchen.",
        )
    if locator in {"Original", "Demo"}:
        content = item.body
    else:
        chunk = db.scalar(
            select(Chunk).where(
                Chunk.item_id == item.id,
                Chunk.locator == locator,
                Chunk.version == requested,
            )
        )
        if not chunk:
            raise HTTPException(
                404, "Fundstelle nicht mehr verfügbar. Bitte die Quelle erneut suchen."
            )
        content = chunk.text
    return {"text": content, "locator": locator, "version": requested}


def item_status(item_id: str, body: ItemStatus, session=None, db=None):
    if body.status not in {"new", "in_progress", "waiting", "done"}:
        raise HTTPException(400, "Unbekannter Status.")
    item = visible_item(db, item_id)
    if item.kind in {"task", "calendar"} and (
        db.get(Source, item.source_id).kind == "todo"
        or db.get(Source, item.source_id).kind.startswith("crm_")
    ):
        raise HTTPException(
            400,
            "Externe Aufgaben und Termine bitte über einen freigegebenen Vorschlag ändern.",
        )
    item.status = body.status
    db.commit()
    return item_dict(db, item)


def analyze_item(item_id: str, session=None, db=None):
    item = visible_item(db, item_id, ai=True)
    job = enqueue(db, "analyze", {"item_id": item.id, "background": False})
    db.commit()
    return serialize(job)


def search(q: str, session=None, db=None):
    return ai.search(db, q, limit=30)
