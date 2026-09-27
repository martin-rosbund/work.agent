from fastapi import HTTPException
from sqlalchemy import select

from app import ai
from app.core.events import event
from app.models import (
    Conversation,
    Item,
    Job,
    Message,
    Proposal,
)
from app.services import (
    enqueue,
    item_dict,
    serialize,
    visible_item,
)

from .schemas import ChatInput, ConversationInput

PREFIX = "/api/v1"


def conversations(session=None, db=None, archived=False):
    return [
        serialize(c)
        for c in db.scalars(
            select(Conversation).where(Conversation.archived == archived).order_by(Conversation.created_at.desc())
        )
    ]


def create_conversation(body: ConversationInput, session=None, db=None):
    linked = [visible_item(db, item_id) for item_id in body.item_ids]
    thread = linked[0].thread_key if len(linked) == 1 else None
    if thread:
        existing = db.scalar(
            select(Conversation).where(Conversation.thread_key == thread)
        )
        if existing:
            existing.archived = False
            db.commit()
            return serialize(existing)
    row = Conversation(
        title=linked[0].title if linked else body.title,
        item_ids=body.item_ids,
        thread_key=thread,
    )
    db.add(row)
    db.commit()
    return serialize(row)


def link_conversation(
    conversation_id: str, body: ConversationInput, session=None, db=None
):
    row = db.get(Conversation, conversation_id)
    if not row:
        raise HTTPException(404, "Chat nicht gefunden.")
    for item_id in body.item_ids:
        visible_item(db, item_id)
    row.item_ids = list(set(row.item_ids + body.item_ids))
    row.title = body.title
    db.commit()
    return serialize(row)


def conversation_detail(conversation_id: str, session=None, db=None):
    row = db.get(Conversation, conversation_id)
    if not row:
        raise HTTPException(404, "Chat nicht gefunden.")
    linked = []
    ids = set(row.item_ids)
    if row.thread_key:
        ids.update(db.scalars(select(Item.id).where(Item.thread_key == row.thread_key)))
    for item_id in ids:
        try:
            linked.append(item_dict(db, visible_item(db, item_id)))
        except HTTPException:
            linked.append(
                {
                    "id": item_id,
                    "available": False,
                    "title": "Quelle nicht mehr verfügbar",
                }
            )
    return {
        "conversation": serialize(row),
        "items": linked,
        "messages": [
            serialize(m)
            for m in db.scalars(
                select(Message)
                .where(Message.conversation_id == row.id)
                .order_by(Message.created_at)
            )
        ],
        "proposals": [
            serialize(p)
            for p in db.scalars(
                select(Proposal)
                .where(Proposal.conversation_id == row.id)
                .order_by(Proposal.created_at.desc())
            )
        ],
    }


def chat_message(conversation_id: str, body: ChatInput, session=None, db=None):
    conversation = db.scalar(select(Conversation).where(Conversation.id == conversation_id).with_for_update())
    if not conversation:
        raise HTTPException(404, "Chat nicht gefunden.")
    if conversation.archived:
        raise HTTPException(409, "Bitte den Chat zuerst wiederherstellen.")
    ai.conversation_items(db, conversation)
    existing = db.scalar(select(Job).where(Job.dedupe_key == f"chat:{conversation_id}"))
    if existing:
        raise HTTPException(409, "In diesem Chat läuft bereits eine Antwort.")
    db.add(Message(conversation_id=conversation_id, role="user", content=body.content))
    enqueue(db, "chat", {"conversation_id": conversation_id}, f"chat:{conversation_id}")
    db.commit()
    return {"ok": True}


def archive_conversation(conversation_id, archived, db):
    row = db.get(Conversation, conversation_id)
    if not row:
        raise HTTPException(404, "Chat nicht gefunden.")
    row.archived = archived
    event(db, "conversation.updated", conversation_id=row.id)
    db.commit()
    return serialize(row)


def delete_conversation(conversation_id, db):
    row = db.scalar(select(Conversation).where(Conversation.id == conversation_id).with_for_update())
    if not row:
        raise HTTPException(404, "Chat nicht gefunden.")
    has_messages = db.scalar(select(Message.id).where(Message.conversation_id == row.id).limit(1))
    has_proposals = db.scalar(select(Proposal.id).where(Proposal.conversation_id == row.id).limit(1))
    has_job = db.scalar(select(Job.id).where(Job.dedupe_key == f"chat:{row.id}").limit(1))
    if has_messages or has_proposals or has_job:
        raise HTTPException(409, "Chats mit Nachrichten oder Vorschlägen können nur archiviert werden.")
    db.delete(row)
    event(db, "conversation.deleted", conversation_id=conversation_id)
    db.commit()
    return {"ok": True}
