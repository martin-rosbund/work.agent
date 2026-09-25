"""GitHub discovery and resumable issue import, shared by API jobs and worker."""

from datetime import timedelta
from urllib.parse import quote

from sqlalchemy import delete, select

from app.core.events import event
from app.core.jobs import enqueue
from app.core.models import Item, Source, now
from app.core.utils import date
from app.features.content.ingestion import upsert
from app.features.github.models import (
    GitHubCache,
    GitHubComment,
    GitHubConnection,
    GitHubIssue,
    GitHubRepository,
)
from app.integrations.github.client import GitHubClient, GitHubError


def handle_error(db, connection, exc, source=None):
    if exc.status == 429:
        connection.retry_at = now() + timedelta(seconds=exc.retry_after)
        connection.status = "rate_limited"
        if source:
            source.next_sync = connection.retry_at
    elif exc.status == 401 or (source is None and exc.status in {403, 404}):
        connection.status = "reauth" if exc.status == 401 else "forbidden"
        for repo in db.scalars(
            select(GitHubRepository).where(
                GitHubRepository.connection_id == connection.id
            )
        ):
            linked = db.get(Source, repo.source_id)
            linked.status, linked.error = connection.status, str(exc)
    elif source and exc.status in {403, 404, 410}:
        source.status, source.error = "forbidden", str(exc)
    else:
        connection.status = "error"
        if source:
            source.status, source.error = "error", str(exc)
    connection.error = str(exc)
    event(db, "github.error", connection_id=connection.id, error=str(exc))
    db.commit()


def discover(db, connection):
    if not connection.enabled or connection.demo:
        return
    client = GitHubClient(db, connection)
    seen = set()
    event(db, "github.progress", phase="discovery", imported=0)
    db.commit()
    try:
        for data in client.pages(
            "/user/repos?per_page=100&sort=full_name&affiliation=owner,collaborator,organization_member"
        ):
            if data["owner"]["login"].casefold() != connection.owner.casefold():
                continue
            external = str(data["id"])
            seen.add(external)
            repo = db.scalar(
                select(GitHubRepository).where(
                    GitHubRepository.connection_id == connection.id,
                    GitHubRepository.external_id == external,
                )
            )
            if not repo:
                source = Source(
                    kind="github",
                    name=data["full_name"],
                    ai_enabled=False,
                    writable=False,
                )
                db.add(source)
                db.flush()
                repo = GitHubRepository(
                    connection_id=connection.id,
                    source_id=source.id,
                    external_id=external,
                )
                db.add(repo)
            source = db.get(Source, repo.source_id)
            repo.owner, repo.name, repo.full_name = (
                data["owner"]["login"],
                data["name"],
                data["full_name"],
            )
            repo.web_url, repo.default_branch = (
                data["html_url"],
                data.get("default_branch", "main"),
            )
            repo.archived = data.get("archived", False)
            source.name = repo.full_name
            if source.status not in {"reauth", "forbidden"}:
                source.status, source.error = "ok", None
            db.flush()
            source.config = {"repository_id": repo.id, "connection_id": connection.id}
            if source.enabled:
                enqueue(db, "sync", {"source_id": source.id}, "sync:" + source.id)
        # Only reconcile after all pages succeeded; interrupted discovery cannot
        # accidentally revoke repositories from a page that was never fetched.
        for repo in db.scalars(
            select(GitHubRepository).where(
                GitHubRepository.connection_id == connection.id
            )
        ):
            if repo.external_id not in seen:
                source = db.get(Source, repo.source_id)
                source.status, source.error = (
                    "forbidden",
                    "Repository nicht mehr mit diesem Token erreichbar.",
                )
        (
            connection.last_discovery,
            connection.status,
            connection.error,
            connection.retry_at,
        ) = now(), "ok", None, None
        connection.next_discovery = now() + timedelta(minutes=15)
        db.execute(
            delete(GitHubCache).where(
                GitHubCache.connection_id == connection.id,
                GitHubCache.fetched_at < now() - timedelta(days=7),
            )
        )
        event(
            db, "github.discovered", connection_id=connection.id, repositories=len(seen)
        )
        db.commit()
    except GitHubError as exc:
        handle_error(db, connection, exc)
        raise
    finally:
        client.close()


def import_issue(db, source, repo, data, comments, links, initial):
    issue = db.scalar(
        select(GitHubIssue).where(
            GitHubIssue.repository_id == repo.id, GitHubIssue.number == data["number"]
        )
    )
    labels = [label["name"] for label in data.get("labels", [])]
    assignees = [user["login"] for user in data.get("assignees", [])]
    body = data.get("body") or ""
    context = (
        body
        + "\n\n"
        + "\n\n".join(
            f"Kommentar von {(c.get('user') or {}).get('login', 'Gelöschtes Konto')}:\n{c.get('body') or ''}"
            for c in comments
        )
    )
    item, _ = upsert(
        db,
        source,
        str(data["id"]),
        "github_issue",
        data["title"],
        context,
        sender=(data.get("user") or {}).get("login", "Gelöschtes Konto"),
        occurred_at=date(data["updated_at"]),
        thread_key=str(data["id"]),
        web_url=data["html_url"],
        meta={
            "number": data["number"],
            "repository": repo.full_name,
            "github_state": data["state"],
            "labels": labels,
            "assignees": assignees,
            "description": body,
            "pull_requests": links,
            "demo": source.config.get("demo", False),
        },
        initial=initial,
    )
    if not issue:
        issue = GitHubIssue(
            repository_id=repo.id, item_id=item.id, number=data["number"]
        )
        db.add(issue)
    issue.state, issue.labels, issue.assignees = data["state"], labels, assignees
    issue.milestone = (data.get("milestone") or {}).get("title")
    issue.created_at, issue.updated_at = (
        date(data["created_at"]),
        date(data["updated_at"]),
    )
    issue.closed_at, issue.pull_requests = (
        date(data["closed_at"]) if data.get("closed_at") else None,
        links,
    )
    db.flush()
    existing = {
        c.external_id: c
        for c in db.scalars(
            select(GitHubComment).where(GitHubComment.issue_id == issue.id)
        )
    }
    for data in comments:
        comment = existing.pop(str(data["id"]), None)
        if not comment:
            comment = GitHubComment(issue_id=issue.id, external_id=str(data["id"]))
            db.add(comment)
        comment.author, comment.body = (data.get("user") or {}).get("login", "Gelöschtes Konto"), data.get("body") or ""
        comment.updated_at, comment.web_url = date(data["updated_at"]), data["html_url"]
    for removed in existing.values():
        db.delete(removed)
    return issue


def read_discussion(client, detail_path):
    comments = list(client.pages(detail_path + "/comments?per_page=100"))
    timeline = list(client.pages(detail_path + "/timeline?per_page=100"))
    links = {}
    for entry in timeline:
        linked = (entry.get("source") or {}).get("issue") or {}
        if linked.get("pull_request") and linked.get("html_url"):
            links[linked["html_url"]] = {
                "number": linked["number"],
                "title": linked["title"],
                "url": linked["html_url"],
                "state": linked["state"],
            }
    return comments, list(links.values())


def sync_source(db, source):
    repo = db.scalar(
        select(GitHubRepository).where(GitHubRepository.source_id == source.id)
    )
    connection = db.get(GitHubConnection, repo.connection_id) if repo else None
    if (
        not connection
        or not connection.enabled
        or connection.demo
        or not source.enabled
    ):
        return
    if connection.status in {"reauth", "forbidden"}:
        return
    client = GitHubClient(db, connection)
    started = now()
    base = f"/repos/{quote(repo.owner, safe='')}/{quote(repo.name, safe='')}/issues"
    initial = source.last_sync is None
    # Daily full open-issue reconciliation also catches deleted comments and PR
    # cross-references that do not always advance an issue's updated timestamp.
    reconcile = initial or date(
        source.cursor.get("reconciled", "2000-01-01")
    ) < started - timedelta(days=1)
    since = (
        source.cursor.get("since") or (started - timedelta(days=90)).isoformat() + "Z"
    )
    paths = [
        base
        + "?state=all&per_page=100&sort=updated&direction=asc&since="
        + quote(since)
    ]
    if reconcile:
        paths.insert(0, base + "?state=open&per_page=100")
    seen = set()
    event(db, "github.progress", phase="issues", repository=repo.full_name, imported=0)
    db.commit()
    try:
        for path in paths:
            for data in client.pages(path):
                if "pull_request" in data or data["number"] in seen:
                    continue
                seen.add(data["number"])
                detail_path = base + "/" + str(data["number"])
                comments, links = read_discussion(client, detail_path)
                import_issue(
                    db, source, repo, data, comments, links, initial
                )
                if len(seen) == 1 or len(seen) % 25 == 0:
                    event(db, "github.progress", phase="issues", repository=repo.full_name, imported=len(seen))
                db.commit()
        if reconcile:
            # Verify known issues not returned by either list: a deleted issue
            # must not remain searchable; old closed issues remain accessible.
            for known in db.scalars(
                select(GitHubIssue).where(GitHubIssue.repository_id == repo.id)
            ):
                if known.number in seen:
                    continue
                try:
                    data, _ = client.get(base + "/" + str(known.number))
                    comments, links = read_discussion(client, base + "/" + str(known.number))
                    import_issue(
                        db, source, repo, data, comments, links, initial
                    )
                except GitHubError as exc:
                    if exc.status not in {301, 302, 404, 410}:
                        raise
                    # A moved issue belongs to its new repository's consent
                    # scope. Never follow that redirect under the old source.
                    db.get(Item, known.item_id).available = False
        source.cursor = {
            "since": (started - timedelta(minutes=5)).isoformat() + "Z",
            "reconciled": started.isoformat()
            if reconcile
            else source.cursor["reconciled"],
        }
        source.last_sync, source.next_sync, source.status, source.error = (
            started,
            started + timedelta(minutes=5),
            "ok",
            None,
        )
        connection.status, connection.error, connection.retry_at = "ok", None, None
        event(db, "github.synced", repository_id=repo.id, issues=len(seen))
        db.commit()
    except GitHubError as exc:
        handle_error(db, connection, exc, source)
        raise
    finally:
        client.close()


def schedule(db):
    for connection in db.scalars(
        select(GitHubConnection).where(
            GitHubConnection.enabled.is_(True), GitHubConnection.demo.is_(False)
        )
    ):
        if connection.status in {"reauth", "forbidden"} or (
            connection.retry_at and connection.retry_at > now()
        ):
            continue
        if connection.next_discovery <= now():
            enqueue(
                db,
                "github_discover",
                {"connection_id": connection.id},
                "github_discover:" + connection.id,
            )
            connection.next_discovery = now() + timedelta(minutes=15)
