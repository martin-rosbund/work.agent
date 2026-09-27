from datetime import timedelta

from sqlalchemy import select

from app.features.content.ingestion import upsert
from app.integrations.microsoft.threads import migrate_threads, sync_thread
from app.models import Conversation, Item, Source, now
from app.services import put_setting


def message(identity, body, sender="other", minutes=0):
    return {
        "id": identity, "createdDateTime": (now() + timedelta(minutes=minutes)).isoformat(),
        "body": {"content": body},
        "from": {"user": {"id": sender, "displayName": sender}},
    }


def source(db, kind="chat"):
    put_setting(db, "microsoft_account", {"oid": "self"})
    row = Source(kind=kind, name="Teams", config={"chat_id": "chat"})
    db.add(row)
    db.flush()
    return row


def test_thread_reopens_only_for_new_incoming_messages_and_keeps_context(db):
    src = source(db)
    cutoff = now() - timedelta(days=90)
    first = message("1", "Question")
    second = message("2", "More context", minutes=1)
    row = sync_thread(db, src, "chat", [second, first], cutoff=cutoff)
    db.flush()
    identity = row.id
    assert [m["id"] for m in row.meta["teams_messages"]] == ["1", "2"]
    row.status = "done"
    version = row.version
    sync_thread(db, src, "chat", [first, second], cutoff=cutoff)
    assert row.status == "done" and row.version == version
    edited = {**first, "body": {"content": "Edited question"}}
    sync_thread(db, src, "chat", [edited, message("3", "My answer", "self", 2)], cutoff=cutoff)
    assert row.status == "done"
    sync_thread(db, src, "chat", [message("4", "Follow-up", minutes=3)], cutoff=cutoff)
    assert row.status == "new" and row.id == identity
    assert "Edited question" in row.body and "My answer" in row.body
    assert len(list(db.scalars(select(Item)))) == 1
    row.status = "in_progress"
    sync_thread(db, src, "chat", [message("5", "Another", minutes=4)], cutoff=cutoff)
    assert row.status == "in_progress"


def test_message_deletion_and_full_reconciliation_update_the_same_thread(db):
    src = source(db)
    cutoff = now() - timedelta(days=90)
    first, second = message("1", "First"), message("2", "Second", minutes=1)
    row = sync_thread(db, src, "chat", [first, second], cutoff=cutoff)
    row.status = "done"
    sync_thread(db, src, "chat", [{**second, "deletedDateTime": now().isoformat()}], cutoff=cutoff)
    assert [m["id"] for m in row.meta["teams_messages"]] == ["1"]
    assert row.status == "done"
    sync_thread(db, src, "chat", [], cutoff=cutoff, full=True)
    assert not row.available


def test_existing_completed_messages_migrate_once_and_keep_work_chat(db):
    src = source(db)
    rows = []
    for index in range(3):
        row, _ = upsert(db, src, str(index), "chat", "Old message", f"Text {index}",
                        "Alex", now() + timedelta(minutes=index), "chat",
                        meta={"chat_id": "chat", "root_id": str(index)}, initial=True)
        row.status = "done"
        rows.append(row)
    conversation = Conversation(title="Existing work", item_ids=[rows[-1].id],
                                thread_key=rows[0].thread_key)
    db.add(conversation)
    db.flush()
    migrate_threads(db, src)
    available = list(db.scalars(select(Item).where(Item.available.is_(True))))
    assert len(available) == 1
    canonical = available[0]
    assert canonical.status == "done" and canonical.id == rows[0].id
    assert len(canonical.meta["teams_messages"]) == 3
    assert conversation.item_ids == [canonical.id]
    from app.features.agent.service import conversation_items
    src.ai_enabled = True
    src.status = "ok"
    assert [item.id for item in conversation_items(db, conversation)] == [canonical.id]
    migrate_threads(db, src)
    assert canonical.meta["message_count"] == 3
    assert len(list(db.scalars(select(Item)))) == 3


def test_channel_threads_stay_separate_and_preserve_reply_target(db):
    src = source(db, "channel")
    cutoff = now() - timedelta(days=90)
    one = sync_thread(db, src, "root-a", [message("root-a", "Topic A"),
                      message("reply", "Answer", minutes=1)], cutoff=cutoff)
    two = sync_thread(db, src, "root-b", [message("root-b", "Topic B")], cutoff=cutoff)
    assert one.id != two.id
    assert one.meta["root_id"] == "root-a" and two.meta["root_id"] == "root-b"
    assert "Answer" in one.body and "Answer" not in two.body


def test_inbox_preview_omits_history_but_detail_keeps_it(db):
    from app.features.content.service import items, get_item
    src = source(db)
    src.status = "ok"
    row = sync_thread(db, src, "chat", [message("1", "Earlier"),
                      message("2", "Latest", minutes=1)], cutoff=now() - timedelta(days=90))
    db.flush()
    preview = items(kind="inbox", db=db)[0]
    assert "teams_messages" not in preview["meta"]
    assert preview["body"] == "Latest"
    assert len(get_item(row.id, db=db)["meta"]["teams_messages"]) == 2
