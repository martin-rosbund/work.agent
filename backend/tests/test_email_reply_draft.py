from sqlalchemy import select

from app.core.models import Conversation, Message, Proposal, Job
from app.services import put_setting, DEFAULT_AGENT


def setup_chat(db, item):
    chat = Conversation(title="Reply", item_ids=[item.id])
    db.add(chat)
    db.flush()
    message = Message(conversation_id=chat.id, role="assistant", content="A short reply.")
    db.add(message)
    db.commit()
    return chat, message


def test_convert_assistant_answer_to_local_email_draft_without_sending(logged, db, mail):
    source, item = mail
    chat, message = setup_chat(db, item)
    payload = {"message_id": message.id, "item_id": item.id, "body": "Reviewed reply"}
    response = logged.post(f"/api/v1/conversations/{chat.id}/email-reply-draft", json=payload)
    assert response.status_code == 200, response.text
    draft = response.json()
    assert draft["kind"] == "reply_email" and draft["status"] == "draft"
    assert draft["payload"]["recipient"] == item.meta["email"]
    assert draft["payload"]["body"] == "Reviewed reply"
    assert not list(db.scalars(select(Job).where(Job.kind == "execute")))
    repeated = logged.post(f"/api/v1/conversations/{chat.id}/email-reply-draft", json=payload)
    assert repeated.json()["id"] == draft["id"]
    assert len(list(db.scalars(select(Proposal)))) == 1


def test_reply_draft_rejects_wrong_chat_disabled_action_and_empty_text(logged, db, mail):
    _, item = mail
    chat, message = setup_chat(db, item)
    other, other_message = setup_chat(db, item)
    url = f"/api/v1/conversations/{chat.id}/email-reply-draft"
    payload = {"message_id": other_message.id, "item_id": item.id, "body": "Reply"}
    assert logged.post(url, json=payload).status_code == 404
    payload["message_id"] = message.id
    assert logged.post(url, json=payload | {"body": "  "}).status_code == 400
    put_setting(db, "agent", DEFAULT_AGENT | {"allowed_actions": []})
    db.commit()
    assert logged.post(url, json=payload).status_code == 403
    assert not list(db.scalars(select(Proposal)))


def test_reply_draft_cannot_target_unlinked_mail(logged, db, mail):
    _, item = mail
    chat, message = setup_chat(db, item)
    chat.item_ids = []
    db.commit()
    response = logged.post(f"/api/v1/conversations/{chat.id}/email-reply-draft", json={
        "message_id": message.id, "item_id": item.id, "body": "Reply",
    })
    assert response.status_code == 400
