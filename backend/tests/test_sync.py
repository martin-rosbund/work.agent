import pytest
import httpx
from sqlalchemy import select, func
from app.models import Item, Source, Job, Proposal, now
from app import graph, worker
from app.services import enqueue


def test_pagination_and_host_validation(db):
    g = graph.Graph(db, token="fake")
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if len(calls) == 1:
            return httpx.Response(
                200,
                json={
                    "value": [{"id": "1"}],
                    "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/messages?page=2",
                },
            )
        return httpx.Response(
            200,
            json={
                "value": [{"id": "2"}],
                "@odata.deltaLink": "https://graph.microsoft.com/v1.0/me/messages/delta?token=x",
            },
        )

    g.client = httpx.Client(transport=httpx.MockTransport(handler))
    rows, delta = g.pages("/me/messages")
    assert [r["id"] for r in rows] == ["1", "2"] and delta.endswith("token=x")
    with pytest.raises(ValueError):
        g.pages("https://evil.example/v1.0/me/messages")
    g.close()


def test_mail_incremental_update_and_delete(db):
    source = Source(
        kind="mail", name="Inbox", config={"folder_id": "inbox"}, ai_enabled=True
    )
    db.add(source)
    db.commit()

    class MockGraph:
        rows = [
            {
                "id": "1",
                "subject": "A",
                "body": {"content": "Hello"},
                "receivedDateTime": now().isoformat() + "Z",
                "from": {"emailAddress": {"address": "a@example.com"}},
            }
        ]

        def pages(self, path):
            return self.rows, "https://graph.microsoft.com/v1.0/delta?token=1"

    fake = MockGraph()
    graph._sync(db, source, fake)
    db.commit()
    assert db.scalar(select(func.count()).select_from(Item)) == 1
    assert not list(db.scalars(select(Job).where(Job.kind == "analyze")))
    graph._sync(db, source, fake)
    db.commit()
    assert db.scalar(select(func.count()).select_from(Item)) == 1
    fake.rows = [fake.rows[0] | {"body": {"content": "Changed"}}]
    graph._sync(db, source, fake)
    db.commit()
    item = db.scalar(select(Item))
    assert item.version == 2 and item.body == "Changed"
    assert len(list(db.scalars(select(Job).where(Job.kind == "analyze")))) == 1
    fake.rows = [{"id": "1", "@removed": {"reason": "deleted"}}]
    graph._sync(db, source, fake)
    db.commit()
    assert not item.available


def test_teams_channel_replies_and_deletion(db):
    source = Source(
        kind="channel", name="Team", config={"team_id": "t", "channel_id": "c"}
    )
    db.add(source)
    db.commit()

    def message(id, content):
        return {
            "id": id,
            "createdDateTime": now().isoformat() + "Z",
            "body": {"content": content},
        }

    class MockGraph:
        def pages(self, path):
            return (
                [message("r", "Antwort")]
                if "/replies" in path
                else [message("p", "Frage")]
            ), None

    graph._sync(db, source, MockGraph())
    db.commit()
    items = list(db.scalars(select(Item)))
    assert len(items) == 2 and len({i.thread_key for i in items}) == 1


def test_retry_after_is_preserved(db):
    g = graph.Graph(db, token="fake")
    g.client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                429,
                headers={"Retry-After": "123"},
                json={"error": {"code": "Throttled"}},
            )
        )
    )
    with pytest.raises(graph.GraphError) as e:
        g.request("GET", "/me")
    assert e.value.retry_after == 123


def test_restart_never_replays_uncertain_action(db):
    from datetime import timedelta

    p = Proposal(kind="create_task", payload={"title": "x"}, status="executing")
    db.add(p)
    db.flush()
    job = Job(
        kind="execute",
        payload={"proposal_id": p.id},
        status="running",
        started_at=now() - timedelta(minutes=20),
    )
    db.add(job)
    db.commit()
    worker.recover(db)
    db.commit()
    assert p.status == "unknown" and job.status == "failed"


def test_worker_completes_job_and_emits_event(db):
    from app.services import save_knowledge

    note = save_knowledge(db, "Worker note", "content")
    db.commit()
    job = db.scalar(select(Job).where(Job.kind == "export"))
    job.status = "running"
    db.commit()
    worker.run_job(job.id)
    db.expire_all()
    assert db.get(Job, job.id).status == "done"


def test_delta_failure_does_not_advance_cursor(db, monkeypatch):
    source = Source(
        kind="mail",
        name="Inbox",
        config={"folder_id": "inbox"},
        cursor={"delta": "old"},
    )
    db.add(source)
    db.commit()

    class BrokenGraph:
        def pages(self, path):
            raise graph.GraphError(429, "throttled", 90)

    with pytest.raises(graph.GraphError):
        graph._sync(db, source, BrokenGraph())
    assert source.cursor == {"delta": "old"}


@pytest.mark.parametrize("primary", [True, False])
def test_calendar_uses_supported_graph_endpoint_and_reconciles(db, primary):
    source = Source(kind="calendar", name="Calendar", config={"calendar_id": "cal"})
    db.add(source)
    db.commit()

    class MockGraph:
        rows = [
            {
                "id": "event",
                "subject": "Meeting",
                "start": {"dateTime": now().isoformat()},
            }
        ]
        paths = []

        def request(self, method, path):
            assert path.startswith("/me/calendars/cal?")
            return {"id": "cal", "isDefaultCalendar": primary}

        def pages(self, path):
            self.paths.append(path)
            return (
                self.rows,
                "https://graph.microsoft.com/v1.0/me/calendarView/delta?token=x"
                if primary
                else None,
            )

    fake = MockGraph()
    graph._sync(db, source, fake)
    db.commit()
    expected = (
        "/me/calendarView/delta?" if primary else "/me/calendars/cal/calendarView?"
    )
    assert fake.paths[0].startswith(expected)
    item = db.scalar(select(Item))
    fake.rows = [{"id": "event", "@removed": {}}] if primary else []
    graph._sync(db, source, fake)
    db.commit()
    assert not item.available
    if primary:
        assert "token=x" in fake.paths[1]


def test_partial_mail_delta_preserves_content_without_new_analysis(db):
    source = Source(kind="mail", name="Mail", config={}, ai_enabled=True)
    db.add(source)
    db.commit()

    class MockGraph:
        message = {
            "id": "mail",
            "subject": "Title",
            "body": {"content": "Original"},
            "receivedDateTime": now().isoformat() + "Z",
        }
        partial = False

        def pages(self, path):
            return [{"id": "mail", "isRead": True}] if self.partial else [
                self.message
            ], "https://graph.microsoft.com/v1.0/delta?token=x"

        def request(self, method, path):
            return self.message | {"isRead": True}

    fake = MockGraph()
    graph._sync(db, source, fake)
    db.commit()
    fake.partial = True
    graph._sync(db, source, fake)
    db.commit()
    item = db.scalar(select(Item))
    assert item.body == "Original" and item.title == "Title" and item.version == 1
    assert item.meta["is_read"]
    assert not list(db.scalars(select(Job).where(Job.kind == "analyze")))


def test_reset_mail_cursor_reconciles_missing_messages(db):
    source = Source(kind="mail", name="Mail", config={}, last_sync=now())
    db.add(source)
    db.flush()
    old = Item(
        source_id=source.id,
        external_id="gone",
        kind="mail",
        title="Gone",
        occurred_at=now(),
    )
    db.add(old)
    db.commit()

    class EmptyGraph:
        def pages(self, path):
            return [], "https://graph.microsoft.com/v1.0/delta?new=x"

    graph._sync(db, source, EmptyGraph())
    db.commit()
    assert not old.available


def test_drive_limits_downloads_to_selected_subtree_and_removes_moved_files(db):
    source = Source(
        kind="drive",
        name="Project folder",
        config={"drive_id": "drive", "folder_id": "project"},
    )
    db.add(source)
    db.commit()

    class MockGraph:
        downloads = []
        incremental = False

        def request(self, method, path):
            assert path == "/drives/drive/items/project"
            return {"id": "project", "folder": {}}

        def file(self, id, parent):
            return {
                "id": id,
                "name": id + ".txt",
                "file": {},
                "parentReference": {"id": parent},
                "eTag": "v1",
            }

        def pages(self, path):
            if "token=latest" in path:
                return (
                    [],
                    "https://graph.microsoft.com/v1.0/drives/drive/root/delta?token=1",
                )
            if path.endswith("/items/project/children"):
                return [{"id": "sub", "folder": {}}], None
            if path.endswith("/items/sub/children"):
                return [self.file("inside", "sub")], None
            return [
                self.file("outside", "private"),
                self.file("inside", "private"),
            ], "https://graph.microsoft.com/v1.0/drives/drive/root/delta?token=2"

        def download(self, drive, id):
            self.downloads.append(id)
            return b"Project knowledge"

    fake = MockGraph()
    graph._sync(db, source, fake)
    db.commit()
    item = db.scalar(select(Item))
    assert fake.downloads == ["inside"] and item.available
    graph._sync(db, source, fake)
    db.commit()
    assert fake.downloads == ["inside"] and not item.available
    assert db.scalar(select(func.count()).select_from(Item)) == 1
