import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from app.models import Proposal, Job, Source, Item
from app.services import digest, put_setting, DEFAULT_AGENT
from app import actions


def make(db, item, source):
    p = Proposal(
        kind="reply_email",
        item_id=item.id,
        payload={
            "source_id": source.id,
            "item_id": item.id,
            "body": "Danke!",
            "recipient": "lena@example.com",
        },
    )
    db.add(p)
    db.commit()
    return p


def test_no_send_without_approval(db, mail, monkeypatch):
    source, item = mail
    p = make(db, item, source)
    monkeypatch.setattr(
        actions, "Graph", lambda *args: pytest.fail("Must not call Graph")
    )
    actions.execute(db, p.id)
    assert p.status == "draft"


def test_approval_version_and_duplicate(db, mail):
    source, item = mail
    p = make(db, item, source)
    with pytest.raises(HTTPException):
        actions.approve(db, p.id, 2)
    actions.approve(db, p.id, 1)
    db.commit()
    with pytest.raises(HTTPException):
        actions.approve(db, p.id, 1)
    assert (
        db.scalar(select(func.count()).select_from(Job).where(Job.kind == "execute"))
        == 1
    )


def test_mutated_payload_cannot_execute(db, mail):
    source, item = mail
    p = make(db, item, source)
    actions.approve(db, p.id, 1)
    db.commit()
    p.payload = p.payload | {"body": "Changed after approval"}
    db.commit()
    with pytest.raises(ValueError):
        actions.execute(db, p.id)


def test_target_and_write_permission_checked(db, mail):
    source, item = mail
    p = make(db, item, source)
    p.payload = p.payload | {"recipient": "someoneelse@example.com"}
    with pytest.raises(HTTPException):
        actions.approve(db, p.id, 1)
    p.payload = p.payload | {"recipient": "lena@example.com"}
    source.writable = False
    with pytest.raises(HTTPException):
        actions.approve(db, p.id, 1)


def test_timeout_is_unknown_and_not_replayed(db, mail, monkeypatch):
    source, item = mail
    p = make(db, item, source)
    calls = []

    class FakeGraph:
        def __init__(self, *args):
            pass

        def request(self, *args):
            calls.append(args)
            raise TimeoutError()

        def close(self):
            pass

    monkeypatch.setattr(actions, "Graph", FakeGraph)
    actions.approve(db, p.id, 1)
    db.commit()
    actions.execute(db, p.id)
    db.commit()
    assert p.status == "unknown"
    actions.execute(db, p.id)
    assert len(calls) == 1


def test_demonstration_cannot_send(db, mail, monkeypatch):
    source, item = mail
    source.config = {"demo": True}
    db.commit()
    p = make(db, item, source)
    monkeypatch.setattr(
        actions, "Graph", lambda *args: pytest.fail("Demo must not use Graph")
    )
    actions.approve(db, p.id, 1)
    db.commit()
    actions.execute(db, p.id)
    assert p.status == "demo_done"


def test_unknown_source_not_silently_local(db):
    p = Proposal(kind="create_task", payload={"source_id": "missing", "title": "Work"})
    db.add(p)
    db.commit()
    with pytest.raises(HTTPException):
        actions.approve(db, p.id, 1)


def test_disabled_action_blocks_execution(db, mail):
    source, item = mail
    p = make(db, item, source)
    actions.approve(db, p.id, 1)
    db.commit()
    put_setting(db, "agent", DEFAULT_AGENT | {"allowed_actions": []})
    db.commit()
    with pytest.raises(HTTPException):
        actions.execute(db, p.id)


def test_local_task_creation_after_approval(db):
    p = Proposal(kind="create_task", payload={"title": "Next step", "body": "Review"})
    db.add(p)
    db.commit()
    actions.approve(db, p.id, 1)
    db.commit()
    actions.execute(db, p.id)
    db.commit()
    assert db.get(Item, p.result["item_id"]).title == "Next step"


def test_calendar_requires_timezone_and_order():
    with pytest.raises(ValueError):
        actions.validate_payload(
            "create_event",
            {
                "source_id": "x",
                "subject": "test",
                "start": "2026-01-01T10:00",
                "end": "2026-01-01T11:00",
            },
        )
    with pytest.raises(ValueError):
        actions.validate_payload(
            "create_event",
            {
                "source_id": "x",
                "subject": "test",
                "start": "2026-01-01T12:00Z",
                "end": "2026-01-01T11:00Z",
            },
        )


def test_stale_editor_rejected(logged, mail):
    source, item = mail
    created = logged.post(
        "/api/v1/proposals",
        json={
            "kind": "reply_email",
            "payload": {
                "source_id": source.id,
                "item_id": item.id,
                "recipient": "lena@example.com",
                "body": "one",
            },
        },
    ).json()
    body = {
        "kind": "reply_email",
        "payload": created["payload"] | {"body": "two"},
        "version": 1,
    }
    assert (
        logged.put("/api/v1/proposals/" + created["id"], json=body).status_code == 200
    )
    assert (
        logged.post(
            "/api/v1/proposals/" + created["id"] + "/approve", json={"version": 1}
        ).status_code
        == 409
    )
