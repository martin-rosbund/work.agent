from app.models import (
    Audit,
    Event,
)


def event(db, event_kind, **payload):
    db.add(Event(kind=event_kind, payload=payload))


def audit(db, action, **detail):
    db.add(Audit(action=action, detail=detail))
