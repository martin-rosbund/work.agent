from sqlalchemy import select

from app.models import (
    Job,
)


def enqueue(db, kind, payload, key=None):
    if key:
        existing = db.scalar(select(Job).where(Job.dedupe_key == key))
        if existing:
            return existing
    row = Job(kind=kind, payload=payload, dedupe_key=key)
    db.add(row)
    db.flush()
    return row
