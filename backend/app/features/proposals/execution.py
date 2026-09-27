from datetime import datetime

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select

from app.graph import WRITE_SCOPES, Graph, GraphError, q
from app.models import Item, Proposal, Source, now, uid
from app.integrations.crm.client import CrmError
from app.integrations.crm.mapping import TYPES as CRM_TYPES, TASK_KINDS
from app.services import (
    agent_config,
    audit,
    digest,
    enqueue,
    save_knowledge,
    visible_item,
)


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str | None = None
    item_id: str | None = None
    title: str | None = Field(default=None, max_length=500)
    subject: str | None = Field(default=None, max_length=500)
    body: str | None = Field(default=None, max_length=30000)
    content: str | None = Field(default=None, max_length=100000)
    recipient: str | None = None
    due: str | None = None
    start: str | None = None
    end: str | None = None
    attendees: list[str] = Field(default_factory=list, max_length=100)
    expected_version: int | None = None
    crm_updated_at: str | None = Field(default=None, max_length=100)
    crm_status: str | None = Field(default=None, max_length=100)
    crm_category: str | None = Field(default=None, max_length=100)
    crm_type: str | None = Field(default=None, max_length=100)
    crm_forecast: str | None = Field(default=None, max_length=100)
    crm_origin: str | None = Field(default=None, max_length=100)
    crm_loss_reason: str | None = Field(default=None, max_length=100)


KINDS = {
    "reply_email",
    "reply_teams",
    "create_event",
    "update_event",
    "create_task",
    "update_task",
    "complete_task",
    "knowledge",
}


def validate_payload(kind, payload):
    if kind not in KINDS:
        raise ValueError("Unbekannte Aktion.")
    try:
        parsed = Payload(**payload).model_dump(exclude_none=True)
    except ValidationError as exc:
        raise ValueError("Ungültige Aktionsdaten: " + str(exc)) from exc
    # Explicitly clearing a CRM due date differs from leaving it unchanged.
    if payload.get("crm_updated_at") and "due" in payload and payload["due"] is None:
        parsed["due"] = None
    required = {
        "reply_email": ["source_id", "item_id", "body", "recipient"],
        "reply_teams": ["source_id", "item_id", "body", "recipient"],
        "create_event": ["source_id", "subject", "start", "end"],
        "update_event": ["source_id", "item_id", "subject", "start", "end"],
        "create_task": ["title"],
        "update_task": ["source_id", "item_id", "title"],
        "complete_task": ["source_id", "item_id"],
        "knowledge": ["title", "content"],
    }[kind]
    if any(not parsed.get(key) for key in required):
        raise ValueError("Erforderliche Angaben fehlen: " + ", ".join(required))
    if parsed.get("due"):
        datetime.fromisoformat(parsed["due"])
    if kind in {"create_event", "update_event"}:
        start, end = (
            datetime.fromisoformat(parsed["start"].replace("Z", "+00:00")),
            datetime.fromisoformat(parsed["end"].replace("Z", "+00:00")),
        )
        if not start.tzinfo or not end.tzinfo or end <= start:
            raise ValueError(
                "Termin benötigt Start und Ende mit Zeitzone; Ende muss nach Start liegen."
            )
        if any(
            "@" not in address or "\n" in address for address in parsed["attendees"]
        ):
            raise ValueError("Ungültige Teilnehmeradresse.")
    return parsed


def check_target(db, proposal):
    payload = proposal.payload
    source = (
        db.get(Source, payload.get("source_id")) if payload.get("source_id") else None
    )
    if payload.get("source_id") and not source:
        raise HTTPException(404, "Zielquelle nicht gefunden.")
    if proposal.kind == "knowledge" or (proposal.kind == "create_task" and not source):
        return None
    if (
        not source
        or not source.enabled
        or not source.writable
        or source.status in {"reauth", "forbidden"}
    ):
        raise HTTPException(
            403,
            "Schreibzugriff für diese Quelle ist nicht aktiviert oder nicht verfügbar.",
        )
    expected = {
        "reply_email": {"mail"},
        "reply_teams": {"chat", "channel"},
        "create_event": {"calendar", "crm_event"},
        "update_event": {"crm_event"},
        "create_task": {"todo"} | TASK_KINDS,
        "update_task": {"todo"} | TASK_KINDS,
        "complete_task": {"todo"} | TASK_KINDS,
    }
    if source.kind not in expected.get(proposal.kind, set()):
        raise HTTPException(400, "Aktion und Zielquelle passen nicht zusammen.")
    if payload.get("item_id"):
        item = visible_item(db, payload["item_id"])
        if item.source_id != source.id:
            raise HTTPException(400, "Nachricht gehört nicht zur Zielquelle.")
        if proposal.kind == "reply_email" and payload.get("recipient") != item.meta.get(
            "email"
        ):
            raise HTTPException(
                400, "Eine Antwort geht an den ursprünglichen Absender."
            )
        if proposal.kind == "reply_teams" and payload.get("recipient") != source.name:
            raise HTTPException(400, "Der Zielchat wurde verändert.")
    if source.kind in CRM_TYPES:
        from app.integrations.crm.actions import validate_target

        validate_target(db, source, proposal)
    return source


def approve(db, proposal_id, version):
    proposal = db.scalar(
        select(Proposal).where(Proposal.id == proposal_id).with_for_update()
    )
    if not proposal:
        raise HTTPException(404, "Vorschlag nicht gefunden.")
    if proposal.version != version or proposal.status != "draft":
        raise HTTPException(409, "Vorschlag wurde geändert oder bereits freigegeben.")
    if proposal.kind not in agent_config(db)["allowed_actions"]:
        raise HTTPException(403, "Diese Aktion ist im Agentenprofil deaktiviert.")
    proposal.payload = validate_payload(proposal.kind, proposal.payload)
    check_target(db, proposal)
    proposal.approved_hash = digest(
        {
            "kind": proposal.kind,
            "version": proposal.version,
            "payload": proposal.payload,
        }
    )
    proposal.status = "approved"
    enqueue(
        db,
        "execute",
        {"proposal_id": proposal.id},
        f"execute:{proposal.id}:{proposal.version}",
    )
    audit(
        db,
        "action.approved",
        proposal_id=proposal.id,
        version=version,
        hash=proposal.approved_hash,
    )
    return proposal


def execute(db, proposal_id):
    proposal = db.scalar(
        select(Proposal).where(Proposal.id == proposal_id).with_for_update()
    )
    if not proposal or proposal.status != "approved":
        return
    if proposal.kind not in agent_config(db)["allowed_actions"]:
        raise HTTPException(
            403, "Diese Aktion ist im Agentenprofil inzwischen deaktiviert."
        )
    if proposal.approved_hash != digest(
        {
            "kind": proposal.kind,
            "version": proposal.version,
            "payload": proposal.payload,
        }
    ):
        raise ValueError("Freigabe stimmt nicht mit der Aktion überein.")
    source = check_target(db, proposal)
    payload = proposal.payload
    if proposal.kind == "knowledge":
        item = save_knowledge(
            db,
            payload["title"],
            payload["content"],
            payload.get("item_id"),
            payload.get("expected_version"),
            proposal.citations,
        )
        proposal.status, proposal.result = "done", {"item_id": item.id}
        audit(db, "action.executed", proposal_id=proposal.id)
        return
    if proposal.kind == "create_task" and not source:
        from app.features.planning.service import create_local_task

        item = create_local_task(db, payload, proposal.item_id)
        proposal.status, proposal.result = "done", {"item_id": item.id}
        audit(db, "action.executed", proposal_id=proposal.id)
        return
    if source.config.get("demo"):
        proposal.status, proposal.result = (
            "demo_done",
            {"message": "Nur simuliert. Es wurde nichts an Microsoft gesendet."},
        )
        audit(db, "action.simulated", proposal_id=proposal.id)
        return
    # Persist before network I/O. A worker crash here means UNKNOWN, never automatic replay.
    proposal.status = "executing"
    audit(db, "action.executing", proposal_id=proposal.id)
    db.commit()
    graph = None
    try:
        if source.kind in CRM_TYPES:
            from app.integrations.crm.actions import execute as execute_crm

            proposal.result = execute_crm(db, source, proposal)
            proposal.status = "done"
            source.next_sync = now()
            enqueue(db, "sync", {"source_id": source.id}, f"sync:{source.id}")
            audit(
                db, "action.executed", proposal_id=proposal.id, result=proposal.result
            )
            return
        graph = Graph(db, WRITE_SCOPES[source.kind])
        item = db.get(Item, payload.get("item_id")) if payload.get("item_id") else None
        if proposal.kind == "reply_email":
            result = graph.request(
                "POST",
                f"/me/messages/{q(item.external_id)}/reply",
                {
                    "message": {
                        "body": {"contentType": "Text", "content": payload["body"]},
                        "toRecipients": [
                            {"emailAddress": {"address": payload["recipient"]}}
                        ],
                    }
                },
            )
        elif proposal.kind == "reply_teams":
            if source.kind == "chat":
                chat_id = (
                    item.meta["chat_id"]
                    if source.config.get("mode") == "all_direct_incoming"
                    else source.config["chat_id"]
                )
                path = f"/chats/{q(chat_id)}/messages"
            else:
                path = f"/teams/{q(source.config['team_id'])}/channels/{q(source.config['channel_id'])}/messages/{q(item.meta['root_id'])}/replies"
            result = graph.request(
                "POST",
                path,
                {"body": {"contentType": "text", "content": payload["body"]}},
            )
        elif proposal.kind == "create_event":
            from datetime import timezone

            def utc(value):
                return (
                    datetime.fromisoformat(value.replace("Z", "+00:00"))
                    .astimezone(timezone.utc)
                    .replace(tzinfo=None)
                    .isoformat()
                )

            result = graph.request(
                "POST",
                f"/me/calendars/{q(source.config['calendar_id'])}/events",
                {
                    "subject": payload["subject"],
                    "body": {"contentType": "Text", "content": payload.get("body", "")},
                    "start": {"dateTime": utc(payload["start"]), "timeZone": "UTC"},
                    "end": {"dateTime": utc(payload["end"]), "timeZone": "UTC"},
                    "attendees": [
                        {"emailAddress": {"address": a}, "type": "required"}
                        for a in payload.get("attendees", [])
                    ],
                    "transactionId": proposal.id,
                },
            )
        else:
            base = f"/me/todo/lists/{q(source.config['list_id'])}/tasks"
            data = {
                "title": payload.get("title", ""),
                "body": {"contentType": "text", "content": payload.get("body", "")},
            }
            if payload.get("due"):
                data["dueDateTime"] = {
                    "dateTime": payload["due"][:10] + "T00:00:00",
                    "timeZone": "W. Europe Standard Time",
                }
            if proposal.kind == "complete_task":
                data = {"status": "completed"}
            if proposal.kind != "create_task":
                fresh = graph.request("GET", base + "/" + q(item.external_id))
                if (
                    item.meta.get("etag")
                    and fresh.get("@odata.etag") != item.meta["etag"]
                ):
                    raise GraphError(
                        409,
                        "Aufgabe wurde bei Microsoft geändert. Bitte synchronisieren und erneut prüfen.",
                    )
            headers = (
                {"If-Match": item.meta["etag"]}
                if item and item.meta.get("etag")
                else None
            )
            result = graph.request(
                "POST" if proposal.kind == "create_task" else "PATCH",
                (
                    base
                    if proposal.kind == "create_task"
                    else base + "/" + q(item.external_id)
                ),
                data,
                extra_headers=headers,
            )
        proposal.status, proposal.result = (
            "done",
            {
                "external_id": result.get("id"),
                "message": "Aktion von Microsoft bestätigt.",
            },
        )
        source.next_sync = now()
    except (GraphError, CrmError) as exc:
        proposal.status = (
            "failed"
            if 400 <= exc.status < 500 and exc.status not in {408, 429}
            else "unknown"
        )
        proposal.result = {"error": str(exc)}
    except Exception:
        proposal.status, proposal.result = (
            "unknown",
            {
                "error": "Ergebnis unklar. Bitte zuerst direkt im Zielsystem prüfen; kein automatischer Wiederholungsversuch."
            },
        )
    finally:
        if graph:
            graph.close()
    audit(
        db, "action." + proposal.status, proposal_id=proposal.id, result=proposal.result
    )
