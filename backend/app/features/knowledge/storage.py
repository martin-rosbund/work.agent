import json

from fastapi import HTTPException
from sqlalchemy import select

from app.config import DATA_DIR
from app.core.events import audit
from app.core.jobs import enqueue
from app.core.utils import digest
from app.features.content.storage import replace_chunks
from app.models import (
    Item,
    KnowledgeVersion,
    Source,
)


def save_knowledge(
    db, title, content, item_id=None, expected_version=None, citations=None
):
    source = db.scalar(select(Source).where(Source.kind == "knowledge"))
    if not source:
        source = Source(
            kind="knowledge", name="Mein Wissen", status="ok", ai_enabled=False
        )
        db.add(source)
        db.flush()
    if item_id:
        item = db.scalar(select(Item).where(Item.id == item_id).with_for_update())
        if not item or item.kind != "knowledge":
            raise HTTPException(404, "Notiz nicht gefunden.")
        if expected_version != item.version:
            raise HTTPException(
                409,
                "Die Notiz wurde zwischenzeitlich geÃ¤ndert. Bitte die aktuelle Version vergleichen.",
            )
        item.version += 1
        item.title, item.body = title, content
    else:
        from app.models import uid

        item = Item(
            source_id=source.id,
            external_id=uid(),
            kind="knowledge",
            title=title,
            body=content,
            status="done",
        )
        db.add(item)
        db.flush()
    item.content_hash = digest([title, content])
    item.meta = {
        "citations": citations
        if citations is not None
        else item.meta.get("citations", [])
    }
    db.add(
        KnowledgeVersion(
            item_id=item.id,
            version=item.version,
            title=title,
            content=content,
            citations=item.meta["citations"],
        )
    )
    replace_chunks(db, item)
    enqueue(db, "export", {"item_id": item.id}, f"export:{item.id}:{item.version}")
    audit(db, "knowledge.saved", item_id=item.id, version=item.version)
    return item


def export_knowledge(db, item_id):
    item = db.get(Item, item_id)
    folder = DATA_DIR / "knowledge"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{item.id}.md"
    # The current DB version wins; delayed exports cannot overwrite it with old content.
    text = f"---\nid: {item.id}\nversion: {item.version}\ntitle: {json.dumps(item.title, ensure_ascii=False)}\n---\n\n{item.body}\n"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(target)
