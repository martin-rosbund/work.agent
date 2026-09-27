from datetime import timedelta
from sqlalchemy import select

from app.features.content.ingestion import upsert, remove_item
from app.models import Item, now
from app.services import date, setting
from .client import CRM, CrmError, check_connection
from .mapping import TYPES, handle, personal_filter, status_closed


def sync_source(db, source):
    check_connection(db, source)
    client = CRM(db)
    try:
        spec = TYPES[source.kind]
        records = client.rows(
            spec["entity"], personal_filter(source.kind, setting(db, "crm")["person"])
        )
        statuses = {handle(s): s for s in client.rows(spec["catalog"])}
        seen = set()
        for record in records:
            key = handle(record)
            seen.add(key)
            import_record(
                db, source, record, statuses.get(handle(record.get(spec["status"])), {})
            )
        # Only reconcile after ALL pages and status catalog succeeded.
        for item in db.scalars(select(Item).where(Item.source_id == source.id)):
            if item.external_id not in seen:
                remove_item(db, source.id, item.external_id)
        source.status, source.error = "ok", None
        source.last_sync, source.next_sync = now(), now() + timedelta(minutes=5)
    finally:
        client.close()


def import_record(db, source, record, status):
    spec = TYPES[source.kind]
    key = handle(record)
    meta = {
        "crm_entity": spec["entity"],
        "crm_updated_at": record.get("updatedAt"),
        "crm_status": handle(record.get(spec["status"])),
        "crm_status_label": status.get("description")
        or status.get("title")
        or handle(record.get(spec["status"])),
        "crm_fields": {
            k: handle(record.get(k))
            for k in (
                "category",
                "type",
                "forecast",
                "source",
                "lossReason",
                "priority",
            )
        },
        "due": record.get(spec.get("due", "")),
    }
    if source.kind == "crm_event":
        if not record.get("startDate") or not record.get("endDate"):
            raise CrmError(
                403, "CRM-Termin ohne lesbare Start-/Endzeit. Feldrechte prüfen."
            )
        meta.update(
            start={"dateTime": record.get("startDate"), "timeZone": "UTC"},
            end={"dateTime": record.get("endDate"), "timeZone": "UTC"},
            all_day=record.get("isAllDay", False),
            recurrence=record.get("recurrenceRule"),
        )
    item, _ = upsert(
        db,
        source,
        key,
        "calendar" if source.kind == "crm_event" else "task",
        record.get("title") or "(Ohne Titel)",
        record.get(spec["body"]) or "",
        occurred_at=date(record.get("startDate") or record.get("updatedAt")),
        web_url=setting(db, "crm")["url"] + f"/table/{spec['entity']}?open={key}",
        meta=meta,
        initial=source.last_sync is None,
    )
    item.status = "done" if status_closed(source.kind, status) else "new"
    return item
