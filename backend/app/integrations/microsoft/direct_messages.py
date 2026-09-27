"""Resumable inbox for incoming messages from every one-to-one Teams chat."""

from datetime import timedelta

from sqlalchemy import select

from app.core.models import Item, now
from app.features.content.ingestion import remove_item, upsert
from app.services import date, setting
from .client import GraphError, plain, q


def sync_direct_messages(db, source, graph):
    own_id = setting(db, "microsoft_account").get("oid")
    if not own_id:
        raise GraphError(401, "Bitte Microsoft erneut verbinden.")
    cutoff = now() - timedelta(days=int(source.config.get("days", 90)))
    cursor = dict(source.cursor)
    states = dict(cursor.get("chats", {}))
    pending = list(cursor.get("pending", []))
    if not pending:
        chats, _ = graph.pages(
            "/me/chats?$filter=chatType eq 'oneOnOne'&$expand=lastMessagePreview&$top=50"
        )
        visible = set()
        for chat in chats:
            if chat.get("chatType") != "oneOnOne":
                continue
            chat_id = chat["id"]
            visible.add(chat_id)
            preview = chat.get("lastMessagePreview") or {}
            stamp = [preview.get(key) for key in (
                "id", "createdDateTime", "lastModifiedDateTime", "deletedDateTime"
            )]
            state = states.get(chat_id, {})
            full = not state.get("full") or date(state["full"]) < now() - timedelta(days=1)
            # Preview is only a fast-path hint. Daily reconciliation catches
            # changes/deletions to older messages that leave the preview unchanged.
            if not full and any(stamp) and state.get("preview") == stamp:
                continue
            if not state and preview.get("createdDateTime") and date(preview["createdDateTime"]) < cutoff:
                continue
            pending.append({"id": chat_id, "preview": stamp, "full": full})
        for item in db.scalars(select(Item).where(Item.source_id == source.id)):
            if item.meta.get("chat_id") not in visible:
                item.available = False
        states = {key: value for key, value in states.items() if key in visible}
        cursor.update(chats=states, pending=pending)
        source.cursor = dict(cursor)
        db.commit()

    # Yield regularly so mail, interactive chats and other sources keep running.
    for task in pending[:10]:
        chat_id = task["id"]
        state = states.get(chat_id, {})
        started = now()
        since = cutoff if task["full"] or not state.get("since") else date(state["since"])
        path = (
            f"/chats/{q(chat_id)}/messages?$top=50&$orderby=lastModifiedDateTime desc"
            f"&$filter=lastModifiedDateTime gt {since.isoformat()}Z"
        )
        try:
            rows, _ = graph.pages(path)
        except GraphError as exc:
            if exc.status not in {403, 404}:
                raise
            for item in db.scalars(select(Item).where(Item.source_id == source.id)):
                if item.meta.get("chat_id") == chat_id:
                    item.available = False
            states.pop(chat_id, None)
        else:
            seen = set()
            for message in rows:
                external_id = chat_id + ":" + message["id"]
                sender = ((message.get("from") or {}).get("user") or {})
                if (
                    message.get("deletedDateTime")
                    or message.get("messageType", "message") != "message"
                    or not sender.get("id") or sender["id"] == own_id
                ):
                    remove_item(db, source.id, external_id)
                    continue
                if date(message.get("createdDateTime")) < cutoff:
                    continue
                seen.add(external_id)
                body = plain((message.get("body") or {}).get("content", ""))
                upsert(
                    db, source, external_id, "chat",
                    message.get("subject") or body[:100] or "Teams-Nachricht",
                    body, sender.get("displayName") or "Teams-Kontakt",
                    date(message.get("createdDateTime")), chat_id,
                    message.get("webUrl") or "",
                    {"chat_id": chat_id, "root_id": message["id"], "incoming": True},
                    initial=not state,
                )
            if task["full"]:
                for item in db.scalars(select(Item).where(
                    Item.source_id == source.id, Item.occurred_at >= cutoff,
                )):
                    if item.meta.get("chat_id") == chat_id and item.external_id not in seen:
                        item.available = False
            states[chat_id] = {
                "preview": task["preview"],
                "since": (started - timedelta(minutes=5)).isoformat(),
                "full": started.isoformat() if task["full"] else state.get("full"),
            }
        pending = pending[1:]
        cursor.update(chats=states, pending=pending)
        source.cursor = dict(cursor)
        db.commit()

    source.status, source.error = "ok", None
    source.next_sync = now() + (timedelta(seconds=5) if pending else timedelta(minutes=2))
    if not pending:
        source.last_sync = now()
