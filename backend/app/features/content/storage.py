from fastapi import HTTPException
from sqlalchemy import delete

from app.core.jobs import enqueue
from app.core.settings import agent_config
from app.core.utils import serialize
from app.models import Chunk, Item, Source


def visible_item(db, item_id, ai=False):
    item = db.get(Item, item_id)
    source = db.get(Source, item.source_id) if item else None
    if (
        not item
        or not item.available
        or (not source)
        or (not source.enabled)
        or (source.status in {"forbidden", "reauth"})
    ):
        raise HTTPException(404, "Quelle nicht verfügbar.")
    if ai and (not source.ai_enabled):
        raise HTTPException(403, "Für diese Quelle ist keine KI-Verarbeitung erlaubt.")
    return item


def replace_chunks(db, item, sections=None):
    db.execute(delete(Chunk).where(Chunk.item_id == item.id))
    for locator, content in sections or [("Text", item.body)]:
        for offset in range(0, len(content), 2400):
            text = content[offset : offset + 2800].strip()
            if text:
                db.add(
                    Chunk(
                        item_id=item.id,
                        text=text,
                        locator=f"{locator} · Abschnitt {offset // 2400 + 1}",
                        version=item.version,
                    )
                )
    source = db.get(Source, item.source_id)
    if source and source.ai_enabled and source.enabled:
        enqueue(
            db,
            "embed",
            {"item_id": item.id},
            f"embed:{item.id}:{item.version}:{agent_config(db)['embedding_model']}",
        )


def item_dict(db, item, *, preview=False):
    data = serialize(item)
    if preview and item.meta.get("teams_conversation"):
        data["meta"] = {key: value for key, value in item.meta.items()
                        if key != "teams_messages"}
        data["body"] = item.meta.get("latest_message", "")[:150]
    data.pop("file_path", None)
    source = db.get(Source, item.source_id)
    data["source_name"] = source.name if source else ""
    data["ai_enabled"] = bool(source and source.ai_enabled)
    data["source_kind"] = source.kind if source else ""
    if item.meta.get("citations"):
        citations = []
        for citation in item.meta["citations"]:
            origin = db.get(Item, citation.get("item_id"))
            origin_source = db.get(Source, origin.source_id) if origin else None
            available = bool(
                origin
                and origin.available
                and origin_source
                and origin_source.enabled
                and (origin_source.status not in {"reauth", "forbidden"})
            )
            citations.append(citation | {"available": available})
        data["meta"] = item.meta | {"citations": citations}
    return data
