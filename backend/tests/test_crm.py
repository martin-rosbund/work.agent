import json

import httpx
import pytest
from sqlalchemy import select

from app import actions
from app.integrations.crm.client import CRM, CrmError, origin
from app.integrations.crm.mapping import TYPES, status_closed
from app.integrations.crm.sync import sync_source
from app.models import Item, Source, Proposal
from app.services import put_setting, setting
from app.security import decrypt


def seed(db, kind="crm_office", writable=True):
    put_setting(
        db,
        "crm",
        {
            "id": "test-connection",
            "token": "unused-with-fake",
            "url": "https://crm.example.test",
            "person": 42,
        },
    )
    source = Source(
        kind=kind,
        config={"crm_connection_id": "test-connection"},
        name=TYPES[kind]["label"],
        writable=writable,
        enabled=True,
        status="ok",
    )
    db.add(source)
    db.flush()
    return source


@pytest.mark.parametrize(
    "value",
    [
        "http://evil.test",
        "https://user:secret@example.test",
        "https://example.test/path",
        "https://example.test/?token=x",
        "file:///secret",
    ],
)
def test_bad_origins(value):
    with pytest.raises(ValueError):
        origin(value)


def test_transport_never_follows_redirects_or_echoes_secrets(monkeypatch):
    real_client, calls = httpx.Client, []

    def dispatch(request):
        calls.append(request)
        return httpx.Response(
            302, headers={"location": "https://other.test"}, text="secret-token"
        )

    monkeypatch.setattr(
        "app.integrations.crm.client.httpx.Client",
        lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(dispatch)),
    )
    client = CRM(url="https://crm.example.test", token="secret-token")
    with pytest.raises(CrmError) as error:
        client.request("GET", "/api/current/person")
    assert "secret-token" not in str(error.value)
    assert error.value.status == 302
    assert len(calls) == 1
    assert calls[0].headers["Authorization"] == "Bearer secret-token"
    client.close()


class FakeCRM:
    records = []
    statuses = [
        {"handle": "custom_done", "description": "Fertig geprüft", "isOpen": False}
    ]
    writes = []
    fail_write = False

    def __init__(self, *args, **kwargs):
        pass

    def close(self):
        pass

    def rows(self, entity, filters=None, relations=None):
        if entity in {s["catalog"] for s in TYPES.values()}:
            return self.statuses
        assert filters and (
            filters.get("responsiblePerson") == 42
            or filters.get("assigneePerson") == 42
            or filters.get("$or")
            == [{"assigneePerson": 42}, {"participants": {"handle": 42}}]
        )
        return self.records

    def request(self, method, path, data=None, params=None):
        if path == "/api/current/person":
            return {"handle": 42, "firstName": "Test", "lastName": "Person"}
        if path.startswith("/api/current/permission/"):
            return {"allowRead": True, "allowInsert": True, "allowUpdate": True}
        self.writes.append((method, path, data, params))
        if self.fail_write:
            raise CrmError(503, "CRM nicht erreichbar.")
        return {"handle": 77}


@pytest.fixture
def fake(monkeypatch):
    FakeCRM.records, FakeCRM.writes, FakeCRM.fail_write = [], [], False
    FakeCRM.statuses = [
        {"handle": "custom_done", "description": "Fertig geprüft", "isOpen": False}
    ]
    for module in [
        "app.features.crm.service",
        "app.integrations.crm.sync",
        "app.integrations.crm.actions",
    ]:
        monkeypatch.setattr(module + ".CRM", FakeCRM)
    return FakeCRM


def test_connection_encrypts_token_creates_five_sources_and_disconnects(
    logged, db, fake
):
    result = logged.put(
        "/api/v1/crm",
        json={
            "url": "http://localhost:5173",
            "api_url": "http://localhost:3000",
            "token": "personal-secret",
        },
    )
    assert result.status_code == 200, result.text
    assert "personal-secret" not in result.text
    db.expire_all()
    assert decrypt(setting(db, "crm")["token"]) == "personal-secret"
    sources = list(db.scalars(select(Source).where(Source.kind.in_(TYPES))))
    assert len(sources) == 5
    assert all(not s.writable and not s.ai_enabled for s in sources)
    assert (
        logged.put("/api/v1/crm", json={"url": "https://different.test"}).status_code
        == 409
    )
    assert logged.delete("/api/v1/crm").status_code == 200
    db.expire_all()
    assert "token" not in setting(db, "crm")
    assert all(not s.enabled for s in sources)


@pytest.mark.parametrize("kind", list(TYPES))
def test_sync_imports_distinct_entity_and_dynamic_status(db, fake, kind):
    source = seed(db, kind)
    spec = TYPES[kind]
    fake.records = [
        {
            "handle": 10,
            "title": "Prüfdatensatz",
            spec["body"]: "Inhalt",
            spec["status"]: "custom_done",
            "updatedAt": "2026-09-27T10:00:00Z",
            "startDate": "2026-09-28T08:00:00Z",
            "endDate": "2026-09-28T09:00:00Z",
        }
    ]
    sync_source(db, source)
    db.flush()
    item = db.scalar(select(Item).where(Item.source_id == source.id))
    assert item.meta["crm_entity"] == spec["entity"]
    assert item.status == "done"
    assert item.meta["crm_status_label"] == "Fertig geprüft"
    version = item.version
    fake.statuses[0]["isOpen"] = True
    sync_source(db, source)
    assert item.status == "new"
    assert (
        item.version == version
    )  # Status flags can change without the record changing.
    fake.records = []
    sync_source(db, source)
    assert not item.available


def test_closed_flag_wins_over_open_for_sales_and_custom_status():
    assert status_closed("crm_sales", {"isClosed": True, "isOpen": True})
    assert not status_closed("crm_office", {"isClosed": False, "isOpen": False})


def make_proposal(db, source, kind, payload):
    p = Proposal(
        kind=kind,
        payload=actions.validate_payload(kind, {"source_id": source.id, **payload}),
    )
    db.add(p)
    db.commit()
    return p


@pytest.mark.parametrize("kind", list(TYPES))
def test_approved_create_uses_correct_crm_entity_and_owner(db, fake, kind):
    source = seed(db, kind)
    payload = {"title": "Test", "body": "Beschreibung"}
    action = "create_task"
    if kind == "crm_sales":
        payload["crm_origin"] = "custom-origin"
    if kind == "crm_event":
        action = "create_event"
        payload = {
            "subject": "Test",
            "start": "2026-10-01T08:00:00+02:00",
            "end": "2026-10-01T09:00:00+02:00",
        }
    p = make_proposal(db, source, action, payload)
    actions.execute(db, p.id)
    assert not fake.writes
    actions.approve(db, p.id, p.version)
    actions.execute(db, p.id)
    assert p.status == "done"
    method, path, data, params = fake.writes[0]
    assert method == "POST"
    assert path == "/api/generic/" + TYPES[kind]["entity"]
    assert data[TYPES[kind]["owner"]] == 42
    assert "creatorPerson" not in data
    if kind == "crm_event":
        assert data["sendCalendarInvitations"] is False


def test_crm_completion_requires_dynamic_closed_status_and_atomic_version(db, fake):
    source = seed(db)
    record = {
        "handle": 10,
        "title": "Test",
        "updatedAt": "2026-09-27T10:00:00Z",
        "status": "custom_done",
    }
    fake.records = [record]
    sync_source(db, source)
    item = db.scalar(select(Item).where(Item.source_id == source.id))
    p = make_proposal(
        db,
        source,
        "complete_task",
        {
            "item_id": item.id,
            "crm_updated_at": record["updatedAt"],
            "crm_status": "custom_done",
        },
    )
    actions.approve(db, p.id, p.version)
    actions.execute(db, p.id)
    assert p.status == "done"
    assert fake.writes[0][3] == {
        "handle": "10",
        "expectedUpdatedAt": record["updatedAt"],
    }
    assert fake.writes[0][2] == {"status": "custom_done"}


def test_remote_conflict_never_overwrites(db, fake):
    source = seed(db)
    fake.records = [
        {"handle": 10, "title": "Test", "updatedAt": "2026-09-27T10:00:00Z"}
    ]
    sync_source(db, source)
    item = db.scalar(select(Item))
    p = make_proposal(
        db,
        source,
        "update_task",
        {
            "item_id": item.id,
            "title": "Geändert",
            "crm_updated_at": item.meta["crm_updated_at"],
        },
    )
    actions.approve(db, p.id, p.version)
    fake.records[0]["updatedAt"] = "2026-09-27T11:00:00Z"
    actions.execute(db, p.id)
    assert p.status == "failed"
    assert not fake.writes


def test_uncertain_write_not_replayed(db, fake):
    source = seed(db)
    p = make_proposal(db, source, "create_task", {"title": "Test"})
    actions.approve(db, p.id, p.version)
    fake.fail_write = True
    actions.execute(db, p.id)
    assert p.status == "unknown"
    actions.execute(db, p.id)
    assert len(fake.writes) == 1


def test_partial_sync_never_hides_existing_data(db, monkeypatch, fake):
    source = seed(db)
    item = Item(
        source_id=source.id, external_id="10", kind="task", title="Bleibt vorhanden"
    )
    db.add(item)
    db.flush()

    def fail(*args, **kwargs):
        raise CrmError(503, "Seite nicht geladen")

    monkeypatch.setattr(fake, "rows", fail)
    with pytest.raises(CrmError):
        sync_source(db, source)
    assert item.available


def test_http_pagination_checks_all_pages(monkeypatch):
    client = CRM(url="https://crm.example.test", token="test")
    pages = []

    def request(method, path, data=None, params=None):
        pages.append(params)
        page = params["page"]
        return {"data": [{"handle": page}], "meta": {"totalPages": 2, "total": 2}}

    monkeypatch.setattr(client, "request", request)
    assert len(client.rows("internalCase", {"responsiblePerson": 42})) == 2
    assert len(pages) == 2
    assert json.loads(pages[0]["filter"]) == {"responsiblePerson": 42}
    client.close()


def test_status_reconfigured_after_approval_prevents_completion(db, fake):
    source = seed(db)
    fake.records = [
        {
            "handle": 10,
            "title": "Test",
            "updatedAt": "2026-09-27T10:00:00Z",
            "status": "custom_done",
        }
    ]
    sync_source(db, source)
    item = db.scalar(select(Item))
    p = make_proposal(
        db,
        source,
        "complete_task",
        {
            "item_id": item.id,
            "crm_status": "custom_done",
            "crm_updated_at": item.meta["crm_updated_at"],
        },
    )
    actions.approve(db, p.id, p.version)
    fake.statuses[0]["isOpen"] = True
    actions.execute(db, p.id)
    assert p.status == "failed"
    assert not fake.writes


def test_new_crm_after_disconnect_cannot_reuse_old_proposals(logged, db, fake):
    assert (
        logged.put(
            "/api/v1/crm", json={"url": "https://first.test", "token": "first-token"}
        ).status_code
        == 200
    )
    old_sources = logged.get("/api/v1/sources").json()
    old_source = next(s for s in old_sources if s["kind"] == "crm_office")
    assert logged.delete("/api/v1/crm").status_code == 200
    assert (
        logged.put(
            "/api/v1/crm", json={"url": "https://second.test", "token": "second-token"}
        ).status_code
        == 200
    )
    new_sources = logged.get("/api/v1/sources").json()
    assert old_source["id"] not in {s["id"] for s in new_sources}
    assert (
        logged.patch(
            "/api/v1/sources/" + old_source["id"], json={"enabled": True}
        ).status_code
        == 401
    )
    db.expire_all()
    with pytest.raises(CrmError):
        sync_source(db, db.get(Source, old_source["id"]))


def test_dynamic_status_choices_are_not_fixed(logged, fake):
    original_rows = fake.rows

    def rows(self, entity, filters=None, relations=None):
        if entity.endswith("Category"):
            return [{"handle": "custom-category", "description": "Eigene Kategorie"}]
        return original_rows(self, entity, filters, relations)

    fake.rows = rows
    try:
        response = logged.get("/api/v1/crm/options/crm_office")
        assert response.status_code == 200
        assert response.json()["statuses"] == [
            {"value": "custom_done", "label": "Fertig geprüft", "closed": True}
        ]
    finally:
        fake.rows = original_rows


def test_crm_due_date_can_be_cleared_without_changing_other_fields(db, fake):
    source = seed(db, "crm_effort")
    fake.records = [
        {
            "handle": 10,
            "title": "Test",
            "updatedAt": "2026-09-27T10:00:00Z",
            "expectedCompletionDate": "2026-10-01",
            "requirementsMarkdown": "Bleibt",
        }
    ]
    sync_source(db, source)
    item = db.scalar(select(Item))
    p = make_proposal(
        db,
        source,
        "update_task",
        {
            "item_id": item.id,
            "title": item.title,
            "body": item.body,
            "due": None,
            "crm_updated_at": item.meta["crm_updated_at"],
        },
    )
    actions.approve(db, p.id, p.version)
    actions.execute(db, p.id)
    assert fake.writes[0][2]["expectedCompletionDate"] is None
    assert fake.writes[0][2]["requirementsMarkdown"] == "Bleibt"


def test_ticket_create_preserves_deadline_time_and_classification(db, fake):
    from datetime import datetime

    source = seed(db, "crm_ticket")
    p = make_proposal(
        db,
        source,
        "create_task",
        {
            "title": "Testticket",
            "body": "Problembeschreibung",
            "due": "2026-10-02T15:45:00+02:00",
            "crm_priority": "custom-priority",
            "crm_type": "custom-type",
            "crm_category": "custom-category",
            "crm_origin": "custom-origin",
        },
    )
    actions.approve(db, p.id, p.version)
    actions.execute(db, p.id)
    assert p.status == "done"
    method, path, data, params = fake.writes[0]
    assert path == "/api/generic/ticket"
    assert data["problemDescription"] == "Problembeschreibung"
    assert data["deadlineDate"] == "2026-10-02T15:45:00+02:00"
    assert datetime.fromisoformat(data["startDate"]).tzinfo
    assert data["priority"] == "custom-priority"
    assert data["category"] == "custom-category"
    assert data["type"] == "custom-type"
    assert data["source"] == "custom-origin"
    assert "solutionDescription" not in data


def test_ticket_update_keeps_start_and_solution_and_checks_dynamic_completion(db, fake):
    source = seed(db, "crm_ticket")
    fake.records = [
        {
            "handle": 10,
            "title": "Ticket",
            "problemDescription": "Problem",
            "solutionDescription": "Bestehende Lösung",
            "updatedAt": "2026-09-27T10:00:00Z",
            "status": "custom_done",
        }
    ]
    sync_source(db, source)
    item = db.scalar(select(Item))
    p = make_proposal(
        db,
        source,
        "update_task",
        {
            "item_id": item.id,
            "title": "Ticket geändert",
            "body": "Problem",
            "crm_updated_at": item.meta["crm_updated_at"],
            "due": None,
        },
    )
    actions.approve(db, p.id, p.version)
    actions.execute(db, p.id)
    assert p.status == "done"
    data = fake.writes[-1][2]
    assert data["deadlineDate"] is None
    assert "startDate" not in data and "solutionDescription" not in data
    p = make_proposal(
        db,
        source,
        "complete_task",
        {
            "item_id": item.id,
            "crm_updated_at": item.meta["crm_updated_at"],
            "crm_status": "custom_done",
        },
    )
    actions.approve(db, p.id, p.version)
    actions.execute(db, p.id)
    assert fake.writes[-1][2] == {"status": "custom_done"}


def test_ticket_catalogs_are_loaded_dynamically(logged, fake, monkeypatch):
    catalogs = []

    def rows(self, entity, filters=None, relations=None):
        catalogs.append(entity)
        return [{"handle": "custom", "description": "Eigener Wert", "isOpen": False}]

    monkeypatch.setattr(fake, "rows", rows)
    result = logged.get("/api/v1/crm/options/crm_ticket")
    assert result.status_code == 200
    assert set(catalogs) == {
        "ticketStatus",
        "ticketPriority",
        "ticketType",
        "ticketCategory",
        "ticketSource",
    }
    assert result.json()["statuses"][0]["closed"] is True
    assert result.json()["priorities"][0]["value"] == "custom"


def test_existing_connection_adds_ticket_source_without_new_ai_consent(
    logged, db, fake
):
    from sqlalchemy import delete

    logged.put(
        "/api/v1/crm", json={"url": "https://crm.example.test", "token": "test-token"}
    )
    db.execute(delete(Source).where(Source.kind == "crm_ticket"))
    db.commit()
    old_ids = set(db.scalars(select(Source.id)))
    assert logged.post("/api/v1/crm/test").status_code == 200
    assert logged.post("/api/v1/crm/test").status_code == 200
    db.expire_all()
    tickets = list(db.scalars(select(Source).where(Source.kind == "crm_ticket")))
    assert len(tickets) == 1
    assert not tickets[0].ai_enabled and not tickets[0].writable
    assert old_ids <= set(db.scalars(select(Source.id)))
