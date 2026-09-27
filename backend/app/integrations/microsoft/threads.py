"""One inbox item per Teams conversation, with an idempotent message history."""

from collections import defaultdict

from sqlalchemy import select

from app.features.content.ingestion import upsert
from app.models import Conversation, Item
from app.services import date, setting

from .client import plain


def thread_item(db, source, thread):
    return db.scalar(select(Item).where(
        Item.source_id == source.id,
        Item.thread_key == f"{source.id}:{thread}",
        Item.meta["teams_conversation"].as_boolean() == True,
    ))


def save_thread(db, source, thread, messages, *, row=None, initial=False,
                reopen=False, status=None):
    ordered = sorted(messages.values(), key=lambda m: (m["created_at"], m["id"]))
    incoming = [m for m in ordered if m["incoming"]]
    if not ordered:
        if row:
            row.available = False
            row.meta = {**row.meta, "teams_messages": []}
        return row
    latest = ordered[-1]
    if source.kind == "chat":
        title = (f"Chat mit {incoming[-1]['sender']}"
                 if source.config.get("mode") == "all_direct_incoming" and incoming
                 else source.name)
    else:
        title = ordered[0].get("subject") or ordered[0]["body"][:100] or source.name
    meta = {
        "teams_conversation": True,
        "teams_messages": ordered,
        "latest_message": latest["body"],
        "message_count": len(ordered),
        "chat_id": thread if source.kind == "chat" else None,
        "root_id": thread if source.kind == "channel" else ordered[0]["id"],
        "team_id": source.config.get("team_id"),
        "channel_id": source.config.get("channel_id"),
    }
    body = "\n\n".join(f"{m['sender']} · {m['created_at']}\n{m['body']}" for m in ordered)
    row, _ = upsert(
        db, source, row.external_id if row else "conversation:" + thread,
        source.kind, title, body, latest["sender"], date(latest["created_at"]),
        thread, latest.get("web_url", ""), meta, initial=initial,
    )
    if status is not None:
        row.status = status
    elif reopen and row.status == "done":
        row.status = "new"
    if source.config.get("mode") == "all_direct_incoming" and not incoming:
        row.available = False
    return row


def migrate_threads(db, source):
    """Fold existing messages without resetting completed conversations or IDs."""
    groups = defaultdict(list)
    for item in db.scalars(select(Item).where(
        Item.source_id == source.id, Item.available.is_(True),
    )):
        if item.meta.get("teams_conversation"):
            continue
        thread = (item.meta.get("chat_id") or source.config.get("chat_id")
                  if source.kind == "chat" else item.meta.get("root_id"))
        if thread:
            groups[thread].append(item)
    for thread, items in groups.items():
        items.sort(key=lambda i: (i.occurred_at, i.id))
        existing = thread_item(db, source, thread)
        canonical = existing or items[0]
        messages = {m["id"]: m for m in canonical.meta.get("teams_messages", [])}
        for item in items:
            identity = (item.meta.get("root_id") if source.kind == "chat"
                        else item.external_id)
            identity = identity or item.external_id
            messages[identity] = {
                "id": identity, "created_at": item.occurred_at.isoformat(),
                "sender": item.sender, "body": item.body, "incoming": True,
                "subject": item.title if source.kind == "channel" else "",
                "web_url": item.web_url,
            }
        statuses = {item.status for item in [canonical, *items]}
        status = next((s for s in ("new", "in_progress", "waiting", "done") if s in statuses))
        save_thread(db, source, thread, messages, row=canonical, initial=True, status=status)
        retired = {item.id for item in items if item.id != canonical.id}
        for item in items:
            if item.id in retired:
                item.available = False
                item.thread_key = ""
                item.meta = {**item.meta, "merged_into": canonical.id}
        for conversation in db.scalars(select(Conversation)):
            if retired.intersection(conversation.item_ids):
                conversation.item_ids = list(dict.fromkeys(
                    canonical.id if i in retired else i for i in conversation.item_ids
                ))
    db.flush()
    return set(groups)


def sync_thread(db, source, thread, rows, *, cutoff, full=False, initial=False):
    row = thread_item(db, source, thread)
    previous = {m["id"]: m for m in row.meta.get("teams_messages", [])} if row else {}
    messages = dict(previous)
    own_id = setting(db, "microsoft_account").get("oid")
    seen = set()
    new_incoming = False
    for entry in rows:
        identity = entry["id"]
        seen.add(identity)
        sender = ((entry.get("from") or {}).get("user") or {})
        if (entry.get("deletedDateTime") or entry.get("@removed")
                or entry.get("messageType", "message") != "message"):
            messages.pop(identity, None)
            continue
        if date(entry.get("createdDateTime")) < cutoff:
            continue
        if source.config.get("mode") == "all_direct_incoming" and not sender.get("id"):
            messages.pop(identity, None)
            continue
        incoming = not own_id or sender.get("id") != own_id
        # Edits, overlap pages and deletions do not reopen completed work.
        if incoming and identity not in previous:
            new_incoming = True
        messages[identity] = {
            "id": identity,
            "created_at": date(entry.get("createdDateTime")).isoformat(),
            "sender": sender.get("displayName") or "Teams-Kontakt",
            "body": plain((entry.get("body") or {}).get("content", "")),
            "incoming": incoming, "subject": entry.get("subject") or "",
            "web_url": entry.get("webUrl") or "",
        }
    if full:
        messages = {key: value for key, value in messages.items()
                    if key in seen or date(value["created_at"]) < cutoff}
    return save_thread(db, source, thread, messages, row=row, initial=initial or not new_incoming,
                       reopen=new_incoming)
