from datetime import timedelta
import httpx
import pytest
from sqlalchemy import select, func
from app.core.models import Source, Item, Job, now
from app.core.security import encrypt, decrypt
from app.features.github.models import (
    GitHubCache,
    GitHubConnection,
    GitHubRepository,
    GitHubIssue,
    GitHubComment,
)
from app.features.github import sync, service
from app.features.github.demo import seed
from app.integrations.github.client import GitHubClient, GitHubError
from app.features.github.schemas import ConnectionUpdate
from app import ai, worker

HTTPClient = httpx.Client


def test_delete_empty_connection_removes_cache_and_preserves_other_connections(
    logged, db, connection
):
    identity = connection.id
    other = GitHubConnection(owner="other", name="Other", token=encrypt("other-token"))
    db.add(other)
    db.add(
        GitHubCache(connection_id=identity, path="/user/repos", payload={"data": []})
    )
    db.commit()
    response = logged.delete(f"/api/v1/github/connections/{identity}")
    assert response.status_code == 200, response.text
    db.expire_all()
    assert db.get(GitHubConnection, identity) is None
    assert db.get(GitHubConnection, other.id) is not None
    assert db.scalar(select(func.count()).select_from(GitHubCache)) == 0
    assert logged.delete(f"/api/v1/github/connections/{identity}").status_code == 404


def test_delete_connection_with_repositories_is_blocked(logged, db):
    seed(db)
    db.commit()
    repo = db.scalar(select(GitHubRepository))
    before = logged.get("/api/v1/github/issues").json()["total"]
    response = logged.delete(f"/api/v1/github/connections/{repo.connection_id}")
    assert response.status_code == 409
    assert "deaktivieren" in response.json()["detail"]
    assert logged.get("/api/v1/github/issues").json()["total"] == before


def test_delete_connection_requires_login(client):
    assert client.delete("/api/v1/github/connections/missing").status_code == 401


def test_label_options_and_local_status_filter_respect_source_visibility(logged, db):
    seed(db)
    db.commit()
    row = db.scalar(select(GitHubIssue))
    item = db.get(Item, row.item_id)
    item.status = "in_progress"
    row.labels = ["bug", "feature"]
    db.commit()
    result = logged.get("/api/v1/github/issues", params={"local_status": "in_progress", "label": "bug"})
    assert result.status_code == 200
    assert result.json()["total"] == 1
    assert result.json()["items"][0]["id"] == row.id
    assert "feature" in logged.get("/api/v1/github/labels").json()
    db.get(Source, item.source_id).enabled = False
    db.commit()
    assert logged.get("/api/v1/github/issues", params={"local_status": "in_progress"}).json()["total"] == 0
    assert "feature" not in logged.get("/api/v1/github/labels").json()
    assert logged.get("/api/v1/github/issues", params={"local_status": "invalid"}).status_code == 422


@pytest.fixture
def connection(db):
    row = GitHubConnection(
        owner="acme", name="Acme", token=encrypt("github_pat_not_a_real_token")
    )
    db.add(row)
    db.commit()
    return row


def repository(identity=1, owner="acme"):
    return {
        "id": identity,
        "owner": {"login": owner},
        "name": "project" + str(identity),
        "full_name": f"{owner}/project{identity}",
        "html_url": f"https://github.com/{owner}/project{identity}",
    }


def issue(number=1, state="open"):
    return {
        "id": number,
        "number": number,
        "title": "Zeitzonenfehler",
        "body": "Sommerzeit prüfen",
        "state": state,
        "user": {"login": "alex"},
        "labels": [{"name": "bug"}],
        "assignees": [{"login": "sam"}],
        "milestone": {"title": "Release"},
        "html_url": f"https://github.com/acme/project1/issues/{number}",
        "created_at": "2026-01-01T12:00:00Z",
        "updated_at": now().isoformat() + "Z",
    }


def mock_http(monkeypatch, handler):
    original = HTTPClient
    monkeypatch.setattr(
        "app.integrations.github.client.httpx.Client",
        lambda **kw: original(transport=httpx.MockTransport(handler), **kw),
    )


def test_multiple_owners_discovery_pagination_new_repositories_and_revocation(
    db, connection, monkeypatch
):
    batch = [repository(), repository(2, "other")]

    def handler(request):
        assert request.method == "GET"
        if request.url.params.get("page") == "2":
            return httpx.Response(200, json=[repository(3)])
        return httpx.Response(
            200,
            json=batch,
            headers={"Link": '<https://api.github.com/user/repos?page=2>; rel="next"'},
        )

    mock_http(monkeypatch, handler)
    sync.discover(db, connection)
    assert len(service.repositories(db)) == 2
    assert all(not r["ai_enabled"] and r["enabled"] for r in service.repositories(db))
    batch[:] = [repository(4)]
    sync.discover(db, connection)
    repos = service.repositories(db)
    assert len(repos) == 3
    assert next(r for r in repos if r["name"] == "project1")["status"] == "forbidden"
    # A different owner has its own connection and independent consent scope.
    other = GitHubConnection(
        owner="other", name="Other", token=encrypt("another-token")
    )
    db.add(other)
    db.commit()
    batch.append(repository(2, "other"))
    sync.discover(db, other)
    assert {r["owner"] for r in service.repositories(db)} == {"acme", "other"}


def test_conditional_requests_survive_new_client_and_retain_next_link(
    db, connection, monkeypatch
):
    calls = []

    def handler(request):
        calls.append(request)
        if request.headers.get("if-none-match") == '"v1"':
            return httpx.Response(304)
        return httpx.Response(
            200,
            json=[repository()],
            headers={
                "etag": '"v1"',
                "link": '<https://api.github.com/second>; rel="next"',
            },
        )

    mock_http(monkeypatch, handler)
    one = GitHubClient(db, connection)
    expected = one.get("/first")
    one.close()
    two = GitHubClient(db, connection)
    assert two.get("/first") == expected
    assert calls[1].headers["if-none-match"] == '"v1"'
    with pytest.raises(ValueError):
        two.get("https://evil.example/steal-token")
    two.close()


def test_import_comments_pr_filter_closed_reopen_and_no_duplicates(
    db, connection, monkeypatch
):
    data = issue()
    comments = [
        {
            "id": 9,
            "body": "erste Fassung",
            "user": {"login": "sam"},
            "updated_at": now().isoformat(),
            "html_url": "https://github.com/acme/project1/issues/1#comment",
        }
    ]

    def handler(request):
        path = request.url.path
        if path == "/user/repos":
            return httpx.Response(200, json=[repository()])
        if path.endswith("/comments"):
            return httpx.Response(200, json=comments)
        if path.endswith("/timeline"):
            return httpx.Response(
                200,
                json=[
                    {
                        "source": {
                            "issue": {
                                "number": 8,
                                "title": "Fix",
                                "html_url": "https://github.com/acme/project1/pull/8",
                                "state": "open",
                                "pull_request": {"url": "pr"},
                            }
                        }
                    }
                ],
            )
        return httpx.Response(
            200, json=[data, issue(7) | {"pull_request": {"url": "pr"}}]
        )

    mock_http(monkeypatch, handler)
    sync.discover(db, connection)
    repo = db.scalar(select(GitHubRepository))
    source = db.get(Source, repo.source_id)
    sync.sync_source(db, source)
    row = db.scalar(select(GitHubIssue))
    assert db.scalar(select(func.count()).select_from(GitHubIssue)) == 1
    assert row.pull_requests[0]["number"] == 8
    assert not db.scalar(select(Job).where(Job.kind == "analyze"))
    assert not ai.search(db, "Sommerzeit", ai=True)
    assert ai.search(db, "Sommerzeit", ai=False)
    version = db.get(Item, row.item_id).version
    comments[0]["body"] = "korrigierte Fassung"
    data["state"] = "closed"
    sync.sync_source(db, source)
    assert row.state == "closed"
    assert db.get(Item, row.item_id).version > version
    assert db.scalar(select(GitHubComment)).body == "korrigierte Fassung"
    data["state"] = "open"
    comments.clear()
    sync.sync_source(db, source)
    assert row.state == "open"
    assert db.scalar(select(func.count()).select_from(GitHubComment)) == 0
    assert db.scalar(select(func.count()).select_from(GitHubIssue)) == 1


@pytest.mark.parametrize(
    "status,headers,expected",
    [
        (401, {}, "reauth"),
        (403, {}, "forbidden"),
        (403, {"x-ratelimit-remaining": "0", "retry-after": "120"}, "rate_limited"),
        (429, {"retry-after": "90"}, "rate_limited"),
    ],
)
def test_token_errors_permissions_and_durable_throttling(
    db, connection, monkeypatch, status, headers, expected
):
    mock_http(
        monkeypatch,
        lambda request: httpx.Response(
            status,
            json={"message": "secret raw body must not be stored"},
            headers=headers,
        ),
    )
    with pytest.raises(GitHubError):
        sync.discover(db, connection)
    db.expire_all()
    assert connection.status == expected
    assert "secret raw" not in connection.error
    if expected == "rate_limited":
        assert connection.retry_at > now() + timedelta(seconds=60)
        sync.schedule(db)
        assert not db.scalar(select(Job))


def test_revoked_or_excluded_repository_never_reaches_ai(db, monkeypatch):
    seed(db)
    db.commit()
    repo = db.scalar(select(GitHubRepository))
    source = db.get(Source, repo.source_id)
    source.ai_enabled = True
    source.status = "forbidden"
    db.commit()
    assert not ai.search(db, "Sommerzeit", ai=True)
    assert not service.issues(db, repository_id=repo.id)["items"]
    source.status, source.enabled = "ok", False
    db.commit()
    assert not ai.search(db, "Sommerzeit", ai=True)


def test_api_secret_redaction_filters_chat_link_and_local_status(logged, db):
    seed(db)
    db.commit()
    response = logged.post(
        "/api/v1/github/connections",
        json={"name": "Firma", "owner": "acme", "token": "github_pat_private_value"},
    )
    assert response.status_code == 200, response.text
    assert "token" not in response.json()
    stored = db.get(GitHubConnection, response.json()["id"])
    assert stored.token != "github_pat_private_value"
    assert decrypt(stored.token) == "github_pat_private_value"
    assert (
        "github_pat_private_value" not in logged.get("/api/v1/github/connections").text
    )
    rows = logged.get(
        "/api/v1/github/issues?state=open&label=bug&assignee=sam-demo"
    ).json()
    assert rows["total"] == 2
    identity = rows["items"][0]["id"]
    detail = logged.get(f"/api/v1/github/issues/{identity}").json()
    assert detail["comments"] and detail["pull_requests"]
    assert detail["codex_prompt"].startswith("fix issue demo-team/")
    first = logged.post(f"/api/v1/github/issues/{identity}/conversation").json()
    second = logged.post(f"/api/v1/github/issues/{identity}/conversation").json()
    assert first["id"] == second["id"]
    changed = logged.patch(
        f"/api/v1/github/issues/{identity}", json={"status": "done"}
    ).json()
    assert changed["local_status"] == "done" and changed["state"] == "open"
    assert len(changed["conversations"]) == 1
    repo = rows["items"][0]["repository_id"]
    assert (
        logged.patch(
            f"/api/v1/github/repositories/{repo}", json={"enabled": False}
        ).status_code
        == 200
    )
    assert logged.get(f"/api/v1/github/issues/{identity}").status_code == 404


def test_discovery_failure_on_second_page_does_not_revoke_repositories(
    db, connection, monkeypatch
):
    mock_http(monkeypatch, lambda req: httpx.Response(200, json=[repository()]))
    sync.discover(db, connection)
    source = db.scalar(select(Source))

    def failure(req):
        return (
            httpx.Response(503)
            if req.url.path == "/second"
            else httpx.Response(
                200,
                json=[],
                headers={"link": '<https://api.github.com/second>; rel="next"'},
            )
        )

    mock_http(monkeypatch, failure)
    with pytest.raises(GitHubError):
        sync.discover(db, connection)
    assert source.status == "ok"


def test_github_scheduler_and_worker_use_same_service(db, connection, monkeypatch):
    sync.schedule(db)
    db.commit()
    job = db.scalar(select(Job))
    called = []
    monkeypatch.setattr(sync, "discover", lambda db, row: called.append(row.id))
    worker.perform(db, job)
    assert called == [connection.id]
    assert connection.next_discovery > now() + timedelta(minutes=14)


def test_worker_sync_imports_github_issues_through_connector(db, connection, monkeypatch):
    def handler(request):
        assert request.method == "GET"
        if request.url.path == "/user/repos":
            return httpx.Response(200, json=[repository()])
        if request.url.path.endswith("/issues"):
            return httpx.Response(200, json=[issue()])
        if request.url.path.endswith("/issues/1"):
            return httpx.Response(200, json=issue())
        return httpx.Response(200, json=[])

    mock_http(monkeypatch, handler)
    sync.discover(db, connection)
    job = db.scalar(select(Job).where(Job.kind == "sync"))
    worker.run_job(job.id)
    db.expire_all()
    assert db.get(Job, job.id).status == "done"
    assert db.scalar(select(func.count()).select_from(GitHubIssue)) == 1
    source = db.get(Source, job.payload["source_id"])
    assert source.last_sync is not None
    assert source.status == "ok"


def test_revoked_connection_blocks_pending_embeddings_and_context(db, monkeypatch):
    from app.features.github.schemas import ConnectionUpdate
    seed(db)
    db.commit()
    row = db.scalar(select(GitHubConnection))
    repo = db.scalar(select(GitHubRepository))
    source = db.get(Source, repo.source_id)
    source.ai_enabled = True
    item = db.scalar(select(Item).where(Item.source_id == source.id))
    db.commit()
    service.change_connection(db, row.id, ConnectionUpdate(enabled=False))
    monkeypatch.setattr(ai, "OpenAIProvider", lambda *args: pytest.fail("Excluded GitHub data reached the provider"))
    from fastapi import HTTPException
    from app.services import put_setting
    put_setting(db, "openai", {"key": encrypt("never-contact-provider")})
    db.commit()
    with pytest.raises(HTTPException) as denied:
        ai.embed_item(db, item.id)
    assert denied.value.status_code == 404
    assert not ai.search(db, "Sommerzeit", ai=True)
    assert not service.issues(db)["items"]


def test_partial_import_retries_without_duplicate_issues_or_cursor_advance(db, connection, monkeypatch):
    failed = False
    def handler(request):
        nonlocal failed
        path = request.url.path
        if path == "/user/repos": return httpx.Response(200, json=[repository()])
        if path.endswith("/timeline"): return httpx.Response(200, json=[])
        if path.endswith("/comments"):
            if "/2/" in path and not failed:
                failed = True
                return httpx.Response(429, headers={"retry-after": "60"})
            return httpx.Response(200, json=[])
        return httpx.Response(200, json=[issue(1), issue(2)])
    mock_http(monkeypatch, handler)
    sync.discover(db, connection)
    source = db.scalar(select(Source))
    with pytest.raises(GitHubError): sync.sync_source(db, source)
    assert source.last_sync is None and not source.cursor
    assert db.scalar(select(func.count()).select_from(GitHubIssue)) == 1
    connection.retry_at = now() - timedelta(seconds=1)
    db.commit()
    sync.sync_source(db, source)
    assert db.scalar(select(func.count()).select_from(GitHubIssue)) == 2
    assert source.last_sync and source.cursor["since"]


def test_token_rotation_does_not_restore_context_before_verified_import(db, connection, monkeypatch):
    from app.features.github.schemas import ConnectionUpdate
    mock_http(monkeypatch, lambda request: httpx.Response(200, json=[repository()]))
    sync.discover(db, connection)
    source = db.scalar(select(Source))
    source.enabled = False
    service.change_connection(db, connection.id, ConnectionUpdate(token="replacement-token"))
    assert not source.enabled and source.status == "forbidden"
    sync.discover(db, connection)
    assert source.status == "forbidden"  # Metadata visibility is not issue access.


@pytest.mark.parametrize("removed_status", [404, 410, 301])
def test_deleted_or_transferred_issue_leaves_active_search(db, connection, monkeypatch, removed_status):
    removed = False
    def handler(request):
        path = request.url.path
        if path == "/user/repos": return httpx.Response(200, json=[repository()])
        if path.endswith("/comments") or path.endswith("/timeline"):
            return httpx.Response(200, json=[])
        if path.endswith("/issues/1"):
            return httpx.Response(removed_status, headers={"location": "https://api.github.com/repos/other/project/issues/9"})
        return httpx.Response(200, json=[] if removed else [issue()])
    mock_http(monkeypatch, handler)
    sync.discover(db, connection)
    source = db.scalar(select(Source))
    sync.sync_source(db, source)
    assert service.issues(db)["total"] == 1
    removed = True
    source.cursor = source.cursor | {"reconciled": "2000-01-01"}
    db.commit()
    sync.sync_source(db, source)
    assert service.issues(db)["total"] == 0
    assert not ai.search(db, "Sommerzeit", ai=False)
