"""Shared, idempotent import and indexing for external sources."""

from sqlalchemy import select

from app.models import Item, now
from app.services import digest, enqueue, replace_chunks


def upsert(
    db,
    source,
    external_id,
    kind,
    title,
    body="",
    sender="",
    occurred_at=None,
    thread_key="",
    web_url="",
    meta=None,
    file_path=None,
    initial=False,
):
    row = db.scalar(
        select(Item).where(Item.source_id == source.id, Item.external_id == external_id)
    )
    content_meta = dict(meta or {})
    if kind == "mail":
        content_meta.pop("is_read", None)
    fingerprint = digest([title, body, content_meta])
    if row and row.content_hash == fingerprint and row.available:
        row.meta = meta or {}
        return row, False
    if not row:
        row = Item(source_id=source.id, external_id=external_id, kind=kind, title=title)
        db.add(row)
        db.flush()
    else:
        row.version += 1
    row.title, row.body, row.sender = title, body, sender
    row.occurred_at, row.thread_key = (
        occurred_at or now(),
        f"{source.id}:{thread_key or external_id}",
    )
    row.web_url, row.meta, row.content_hash, row.available = (
        web_url,
        meta or {},
        fingerprint,
        True,
    )
    row.summary = ""
    if file_path:
        row.file_path, row.processing = file_path, "pending"
        enqueue(
            db,
            "extract",
            {"item_id": row.id, "version": row.version},
            f"extract:{row.id}:{row.version}",
        )
    else:
        replace_chunks(db, row)
    if (
        not initial
        and source.ai_enabled
        and kind in {"mail", "chat", "channel", "github_issue"}
    ):
        enqueue(
            db,
            "analyze",
            {"item_id": row.id, "background": True},
            f"analyze:{row.id}:{row.version}",
        )
    return row, True


def remove_item(db, source_id, external_id):
    row = db.scalar(
        select(Item).where(Item.source_id == source_id, Item.external_id == external_id)
    )
    if row:
        row.available = False
