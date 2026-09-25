import hashlib
import json
from datetime import datetime, timezone

from app.models import (
    now,
)


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()


def date(value):
    if not value:
        return now()
    return (
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
        if ("+" in value or value.endswith("Z"))
        else datetime.fromisoformat(value)
    )


def serialize(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}
