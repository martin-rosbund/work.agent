from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.models import Item, Source, now
from app.integrations.microsoft.direct_messages import sync_direct_messages
from app.integrations.microsoft.client import GraphError
from app.services import put_setting


@pytest.fixture
def direct_source(db):
    put_setting(db, "microsoft_account", {"oid": "self"})
    source = Source(kind="chat", name="Direct", config={"mode": "all_direct_incoming"})
    db.add(source)
    db.commit()
    return source


def message(identity="1", sender="other"):
    return {"id": identity, "createdDateTime": now().isoformat() + "Z",
            "from": {"user": {"id": sender, "displayName": "Alex"}},
            "body": {"content": "Hello"}, "messageType": "message"}


class InboxGraph:
    def __init__(self):
        self.chats = [{"id": "a", "chatType": "oneOnOne"},
                      {"id": "b", "chatType": "oneOnOne"},
                      {"id": "group", "chatType": "group"}]
        self.messages = [message(), message("2", "self"), message("3") | {"from": None}]
        self.calls = []

    def pages(self, path):
        self.calls.append(path)
        if path.startswith("/me/chats"):
            return self.chats, None
        assert not path.startswith("/chats/group/")
        return self.messages, None


def test_direct_inbox_incoming_only_new_contacts_deletion_and_id_collisions(db, direct_source):
    graph = InboxGraph()
    sync_direct_messages(db, direct_source, graph)
    db.commit()
    items = list(db.scalars(select(Item)))
    assert {item.external_id for item in items} == {"conversation:a", "conversation:b"}
    assert all(len(item.meta["teams_messages"]) == 2 for item in items)
    assert all(item.meta["teams_messages"][1]["incoming"] is False for item in items)
    assert {item.meta["chat_id"] for item in items} == {"a", "b"}
    assert direct_source.last_sync is not None
    graph.chats.append({"id": "new-person", "chatType": "oneOnOne"})
    graph.messages = [message() | {"deletedDateTime": now().isoformat()}]
    sync_direct_messages(db, direct_source, graph)
    db.commit()
    assert all(not item.available for item in db.scalars(select(Item)))
    graph.messages = [message("4")]
    sync_direct_messages(db, direct_source, graph)
    db.commit()
    assert len(list(db.scalars(select(Item).where(Item.available.is_(True))))) == 3


def test_direct_inbox_yields_and_resumes_without_restarting_inventory(db, direct_source):
    graph = InboxGraph()
    graph.chats = [{"id": str(i), "chatType": "oneOnOne"} for i in range(12)]
    sync_direct_messages(db, direct_source, graph)
    db.commit()
    assert len(direct_source.cursor["pending"]) == 2
    assert direct_source.last_sync is None
    sync_direct_messages(db, direct_source, graph)
    db.commit()
    assert not direct_source.cursor["pending"]
    assert len(list(db.scalars(select(Item)))) == 12
    assert sum(path.startswith("/me/chats") for path in graph.calls) == 1


def test_direct_inbox_unchanged_preview_skips_reads_and_daily_reconcile_runs(db, direct_source):
    graph = InboxGraph()
    graph.chats = [{"id": "a", "chatType": "oneOnOne", "lastMessagePreview": message()}]
    sync_direct_messages(db, direct_source, graph)
    db.commit()
    graph.calls.clear()
    sync_direct_messages(db, direct_source, graph)
    assert len(graph.calls) == 1
    cursor = dict(direct_source.cursor)
    cursor["chats"]["a"]["full"] = (now() - timedelta(days=2)).isoformat()
    direct_source.cursor = cursor
    graph.calls.clear()
    sync_direct_messages(db, direct_source, graph)
    assert len(graph.calls) == 2


def test_direct_inbox_requires_identity(db, direct_source):
    put_setting(db, "microsoft_account", {})
    with pytest.raises(GraphError) as exc:
        sync_direct_messages(db, direct_source, InboxGraph())
    assert exc.value.status == 401


def test_api_accepts_aggregate_source_without_chat_id(logged):
    response = logged.post("/api/v1/sources", json={
        "kind": "chat", "name": "All direct", "config": {"mode": "all_direct_incoming"},
    })
    assert response.status_code == 200, response.text
    assert response.json()["config"]["mode"] == "all_direct_incoming"
    invalid = logged.post("/api/v1/sources", json={"kind": "chat", "name": "Invalid", "config": {}})
    assert invalid.status_code == 400


def test_approved_reply_uses_original_direct_chat(db, direct_source, monkeypatch):
    from app import actions
    from app.core.models import Proposal
    from app.services import DEFAULT_AGENT
    put_setting(db, "agent", DEFAULT_AGENT)
    direct_source.writable = True
    sync_direct_messages(db, direct_source, InboxGraph())
    item = db.scalar(select(Item).where(Item.external_id == "conversation:a"))
    proposal = Proposal(kind="reply_teams", item_id=item.id, payload={
        "source_id": direct_source.id, "item_id": item.id,
        "body": "Reply", "recipient": direct_source.name,
    })
    db.add(proposal)
    db.commit()
    calls = []

    class FakeGraph:
        def __init__(self, *args):
            pass

        def request(self, method, path, payload):
            calls.append((method, path))
            return {"id": "sent"}

        def close(self):
            pass

    monkeypatch.setattr(actions, "Graph", FakeGraph)
    actions.execute(db, proposal.id)
    assert not calls
    actions.approve(db, proposal.id, proposal.version)
    db.commit()
    actions.execute(db, proposal.id)
    assert calls == [("POST", "/chats/a/messages")]
