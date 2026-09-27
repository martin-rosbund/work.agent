"""Only invoked by the approved proposal executor."""

from app.models import Item
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from app.services import setting
from .client import CRM, CrmError, check_connection
from .mapping import TYPES, handle, personal_filter, status_closed


def validate_target(db, source, proposal):
    check_connection(db, source)
    p, kind = proposal.payload, source.kind
    item = db.get(Item, p.get("item_id")) if p.get("item_id") else None
    if proposal.kind in {"create_task", "create_event"} and item:
        raise ValueError(
            "Neue CRM-Einträge dürfen keinen bestehenden Zieldatensatz ändern."
        )
    if item:
        if not p.get("crm_updated_at") or p["crm_updated_at"] != item.meta.get(
            "crm_updated_at"
        ):
            raise ValueError(
                "CRM-Version fehlt oder wurde geändert. Aufgabe/Termin erneut öffnen."
            )
        if item.meta.get("recurrence"):
            raise ValueError("Serientermine bitte direkt im CRM bearbeiten.")
    if len(p.get("title") or p.get("subject") or "") > 128:
        raise ValueError("CRM-Titel darf höchstens 128 Zeichen enthalten.")
    if p.get("attendees"):
        raise ValueError("CRM-Teilnehmer bitte direkt im CRM verwalten.")
    if kind == "crm_office" and p.get("due"):
        raise ValueError(
            "Interne CRM-Vorgänge haben kein Fälligkeitsfeld. Bitte einen separaten Termin anlegen."
        )
    if (
        kind == "crm_sales"
        and proposal.kind == "create_task"
        and not p.get("crm_origin")
    ):
        raise ValueError("Für eine Verkaufschance bitte die CRM-Herkunft auswählen.")
    if proposal.kind == "complete_task" and not p.get("crm_status"):
        raise ValueError("Bitte den abschließenden CRM-Status ausdrücklich auswählen.")


def execute(db, source, proposal):
    validate_target(db, source, proposal)
    p, spec = proposal.payload, TYPES[source.kind]
    item = db.get(Item, p.get("item_id")) if p.get("item_id") else None
    client = CRM(db)
    try:
        # Check current personal assignment as well as the CRM's atomic update token.
        if item:
            rows = client.rows(
                spec["entity"],
                {
                    **personal_filter(
                        source.kind, setting(db, "crm")["person"], writable=True
                    ),
                    "handle": int(item.external_id),
                },
            )
            if len(rows) != 1:
                raise CrmError(
                    403, "CRM-Datensatz ist nicht mehr deinem Benutzer zugeordnet."
                )
            if rows[0].get("updatedAt") != p["crm_updated_at"]:
                raise CrmError(
                    409,
                    "Datensatz im CRM geändert. Neu synchronisieren und Vorschlag erneut prüfen.",
                )
        data = {}
        if proposal.kind != "complete_task":
            data = {
                "title": p.get("title") or p.get("subject"),
                spec["body"]: p.get("body", ""),
            }
            if spec.get("due") and "due" in p:
                data[spec["due"]] = p["due"][:10] if p["due"] else None
                if source.kind == "crm_ticket" and p["due"]:
                    due = datetime.fromisoformat(p["due"].replace("Z", "+00:00"))
                    if not due.tzinfo:
                        due = due.replace(tzinfo=ZoneInfo("Europe/Berlin"))
                    data[spec["due"]] = due.isoformat()
            if source.kind == "crm_event":
                data.update(startDate=p["start"], endDate=p["end"])
            if not item:
                data[spec["owner"]] = setting(db, "crm")["person"]
                if source.kind == "crm_ticket":
                    data["startDate"] = datetime.now(timezone.utc).isoformat()
                if source.kind == "crm_event":
                    data.update(
                        sendCalendarInvitations=False,
                        createOnlineMeeting=False,
                        isOutlookAvailable=False,
                    )
        if p.get("crm_status"):
            matches = [
                s for s in client.rows(spec["catalog"]) if handle(s) == p["crm_status"]
            ]
            if not matches or (
                proposal.kind == "complete_task"
                and not status_closed(source.kind, matches[0])
            ):
                raise CrmError(
                    400,
                    "Bitte einen gültigen CRM-Status auswählen; zum Abschließen einen Endstatus.",
                )
            data[spec["status"]] = p["crm_status"]
        for key, field in {
            "crm_category": "category",
            "crm_type": "type",
            "crm_forecast": "forecast",
            "crm_origin": "source",
            "crm_loss_reason": "lossReason",
            "crm_priority": "priority",
        }.items():
            if p.get(key):
                allowed = {
                    "crm_category": {"crm_event", "crm_office", "crm_ticket"},
                    "crm_type": {"crm_event", "crm_sales", "crm_ticket"},
                    "crm_forecast": {"crm_sales"},
                    "crm_origin": {"crm_sales", "crm_ticket"},
                    "crm_loss_reason": {"crm_sales"},
                    "crm_priority": {"crm_ticket"},
                }
                if source.kind not in allowed[key]:
                    raise CrmError(
                        400, "CRM-Feld passt nicht zur gewählten Aufgabenart."
                    )
                data[field] = p[key]
        params = (
            {"handle": item.external_id, "expectedUpdatedAt": p["crm_updated_at"]}
            if item
            else None
        )
        result = client.request(
            "PATCH" if item else "POST", "/api/generic/" + spec["entity"], data, params
        )
        return {
            "external_id": handle(result) or (item.external_id if item else None),
            "message": "Aktion von ISB.CRM bestätigt.",
        }
    finally:
        client.close()
