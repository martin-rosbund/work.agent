"""Convert reviewed assistant text into a local reply draft; never sends mail."""

from fastapi import HTTPException
from sqlalchemy import select

from app.core.events import audit, event
from app.core.models import Conversation, Message, Proposal
from app.services import agent_config, serialize, visible_item
from app.actions import validate_payload


def create_email_reply(db, conversation_id, body):
    conversation = db.get(Conversation, conversation_id)
    message = db.get(Message, body.message_id)
    if not conversation or not message or message.conversation_id != conversation_id or message.role != "assistant":
        raise HTTPException(404, "Antwort in diesem Arbeitschat nicht gefunden.")
    item = visible_item(db, body.item_id)
    if item.kind != "mail" or not (
        item.id in conversation.item_ids
        or (conversation.thread_key and item.thread_key == conversation.thread_key)
    ):
        raise HTTPException(400, "Bitte eine E-Mail aus diesem Arbeitschat auswählen.")
    if "reply_email" not in agent_config(db)["allowed_actions"]:
        raise HTTPException(403, "Bitte E-Mail-Antworten unter Dein Agent erlauben.")
    if not item.meta.get("email"):
        raise HTTPException(400, "Die ursprüngliche Absenderadresse fehlt.")
    text = body.body.strip()
    if not text:
        raise HTTPException(400, "Bitte einen Antworttext eingeben.")
    payload = validate_payload("reply_email", {
        "source_id": item.source_id, "item_id": item.id,
        "body": text, "recipient": item.meta["email"], "subject": item.title,
    })
    # Repeated clicks cannot create identical pending replies.
    for existing in db.scalars(select(Proposal).where(
        Proposal.conversation_id == conversation_id,
        Proposal.kind == "reply_email", Proposal.status == "draft",
    )):
        if existing.payload == payload:
            return serialize(existing)
    proposal = Proposal(
        conversation_id=conversation_id, item_id=item.id,
        kind="reply_email", payload=payload,
        citations=[{"item_id": item.id, "title": item.title, "locator": "Original", "version": item.version}],
    )
    db.add(proposal)
    db.flush()
    audit(db, "proposal.email_draft.created", proposal_id=proposal.id, message_id=message.id)
    event(db, "proposal.created", conversation_id=conversation_id, proposal_id=proposal.id)
    db.commit()
    return serialize(proposal)
