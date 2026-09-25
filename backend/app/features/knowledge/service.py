from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy import select

from app.config import (
    DATA_DIR,
    MAX_FILE_BYTES,
    SUPPORTED_EXTENSIONS,
)
from app.models import (
    Item,
    KnowledgeVersion,
    Source,
    uid,
)
from app.services import (
    enqueue,
    item_dict,
    replace_chunks,
    save_knowledge,
    serialize,
)

from .schemas import NoteInput, RestoreVersion

PREFIX = "/api/v1"


async def upload(file: UploadFile = None, session=None, db=None):
    name = Path((file.filename or "Dokument").replace("\\", "/")).name
    suffix = Path(name).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(415, "Dieses Dateiformat wird nicht unterstützt.")
    folder = DATA_DIR / "originals"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{uid()}{suffix}"
    size = 0
    try:
        with target.open("wb") as stream:
            while content := (await file.read(1024 * 1024)):
                size += len(content)
                if size > MAX_FILE_BYTES:
                    raise HTTPException(413, "Datei überschreitet 25 MB.")
                stream.write(content)
        source = db.scalar(select(Source).where(Source.kind == "uploads"))
        row = Item(
            source_id=source.id,
            external_id=uid(),
            kind="document",
            title=name,
            file_path=str(target),
            processing="pending",
        )
        db.add(row)
        db.flush()
        enqueue(db, "extract", {"item_id": row.id, "version": row.version})
        db.commit()
        return item_dict(db, row)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


def create_note(body: NoteInput, session=None, db=None):
    item = save_knowledge(db, body.title, body.content)
    db.commit()
    return item_dict(db, item)


def update_note(item_id: str, body: NoteInput, session=None, db=None):
    item = save_knowledge(db, body.title, body.content, item_id, body.expected_version)
    db.commit()
    return item_dict(db, item)


def versions(item_id: str, session=None, db=None):
    return [
        serialize(v)
        for v in db.scalars(
            select(KnowledgeVersion)
            .where(KnowledgeVersion.item_id == item_id)
            .order_by(KnowledgeVersion.version.desc())
        )
    ]


def restore_note(item_id: str, body: RestoreVersion, session=None, db=None):
    version = db.scalar(
        select(KnowledgeVersion).where(
            KnowledgeVersion.item_id == item_id,
            KnowledgeVersion.version == body.version,
        )
    )
    if not version:
        raise HTTPException(404, "Version nicht gefunden.")
    item = save_knowledge(
        db,
        version.title,
        version.content,
        item_id,
        body.expected_version,
        version.citations,
    )
    db.commit()
    return item_dict(db, item)


def reindex(session=None, db=None):
    for item in db.scalars(select(Item).where(Item.available.is_(True))):
        if item.file_path:
            enqueue(db, "extract", {"item_id": item.id, "version": item.version})
        else:
            replace_chunks(db, item)
            source = db.get(Source, item.source_id)
            if source.ai_enabled:
                enqueue(db, "embed", {"item_id": item.id})
        if item.kind == "knowledge":
            enqueue(db, "export", {"item_id": item.id})
    db.commit()
    return {"ok": True}
