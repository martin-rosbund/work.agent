from fastapi import HTTPException
from sqlalchemy import select, func, cast, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import JSONB

from app.core.events import audit, event
from app.core.jobs import enqueue
from app.core.models import Conversation, Item, Source, now
from app.core.security import encrypt
from app.core.utils import serialize
from app.features.chats.schemas import ConversationInput
from app.features.chats.service import create_conversation
from app.features.connections.schemas import SourceUpdate
from app.features.connections.service import update_source
from app.features.content.storage import visible_item
from app.features.github.models import (
    GitHubCache,
    GitHubComment,
    GitHubConnection,
    GitHubIssue,
    GitHubRepository,
)
from app.features.github.schemas import CommentView, ConnectionView
from app.features.github.sync import handle_error
from app.integrations.github.client import GitHubClient, GitHubError


def connection(db, identity):
    row = db.get(GitHubConnection, identity)
    if not row:
        raise HTTPException(404, "GitHub-Verbindung nicht gefunden.")
    return row


def connections(db):
    return [
        ConnectionView.model_validate(c)
        for c in db.scalars(select(GitHubConnection).order_by(GitHubConnection.name))
    ]


def save_connection(db, body):
    row = GitHubConnection(owner=body.owner, name=body.name, token=encrypt(body.token))
    db.add(row)
    db.flush()
    audit(db, "github.connection.created", connection_id=row.id, owner=row.owner)
    db.commit()
    return ConnectionView.model_validate(row)


def change_connection(db, identity, body):
    row = connection(db, identity)
    if row.demo and body.token:
        raise HTTPException(409, "Für echte Zugangsdaten eine neue Verbindung anlegen.")
    if body.token:
        row.token = encrypt(body.token)
        row.retry_at = None
    if body.enabled is not None:
        row.enabled = body.enabled
    row.status, row.error, row.next_discovery = (
        ("pending" if row.enabled else "disabled"),
        None,
        now(),
    )
    for repo in db.scalars(
        select(GitHubRepository).where(GitHubRepository.connection_id == row.id)
    ):
        source = db.get(Source, repo.source_id)
        # Keep excluded repositories excluded across token rotation/reconnect.
        source.status = "ok" if row.enabled and row.demo else "forbidden"
        source.error = (
            (
                "Erneute Repository-Erkennung ausstehend."
                if row.enabled
                else "GitHub-Verbindung deaktiviert."
            )
            if not row.demo or not row.enabled
            else None
        )
    audit(
        db,
        "github.connection.updated",
        connection_id=row.id,
        enabled=row.enabled,
        token_changed=bool(body.token),
    )
    db.commit()
    return ConnectionView.model_validate(row)


def delete_connection(db, identity):
    row = connection(db, identity)
    if db.scalar(
        select(GitHubRepository.id)
        .where(GitHubRepository.connection_id == identity)
        .limit(1)
    ):
        raise HTTPException(
            409,
            "Diese Verbindung enthält importierte Repositories. Bitte stattdessen deaktivieren.",
        )
    db.execute(delete(GitHubCache).where(GitHubCache.connection_id == identity))
    audit(db, "github.connection.deleted", connection_id=identity, owner=row.owner)
    db.delete(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409, "Die Verbindung wird gerade synchronisiert. Bitte erneut versuchen."
        ) from None
    return {"ok": True}


def test_connection(db, identity):
    row = connection(db, identity)
    if row.demo:
        return {
            "ok": True,
            "repositories": 2,
            "message": "Demoverbindung – keine Anfrage an GitHub.",
        }
    client = GitHubClient(db, row)
    try:
        count = sum(
            1
            for repo in client.pages("/user/repos?per_page=100")
            if repo["owner"]["login"].casefold() == row.owner.casefold()
        )
        return {
            "ok": count > 0,
            "repositories": count,
            "message": "Lesender Verbindungstest erfolgreich."
            if count
            else "Keine Repositories dieses Eigentümers erreichbar. Tokenauswahl und Organisationsfreigabe prüfen.",
        }
    except GitHubError as exc:
        handle_error(db, row, exc)
        raise
    finally:
        client.close()


def repositories(db):
    result = []
    for repo in db.scalars(
        select(GitHubRepository).order_by(GitHubRepository.full_name)
    ):
        source = db.get(Source, repo.source_id)
        data = serialize(repo)
        data.update(
            {
                key: getattr(source, key)
                for key in ["enabled", "ai_enabled", "status", "error", "last_sync"]
            }
        )
        data["demo"] = bool(source.config.get("demo"))
        result.append(data)
    return result


def change_repository(db, identity, body):
    repo = db.get(GitHubRepository, identity)
    if not repo:
        raise HTTPException(404, "Repository nicht gefunden.")
    update_source(
        repo.source_id, SourceUpdate(**body.model_dump(exclude_none=True)), db=db
    )
    return next(row for row in repositories(db) if row["id"] == identity)


def issue_view(db, issue):
    item = visible_item(db, issue.item_id)
    repo = db.get(GitHubRepository, issue.repository_id)
    source = db.get(Source, repo.source_id)
    return serialize(issue) | {
        "repository": repo.full_name,
        "owner": repo.owner,
        "title": item.title,
        "description": item.meta.get("description", item.body),
        "author": item.sender,
        "web_url": item.web_url,
        "local_status": item.status,
        "ai_enabled": source.ai_enabled,
        "demo": bool(source.config.get("demo")),
        "codex_prompt": f"fix issue {repo.full_name}#{issue.number}",
    }


def issues(
    db,
    owner=None,
    repository_id=None,
    state=None,
    label=None,
    assignee=None,
    offset=0,
    limit=50,
    local_status=None,
):
    query = (
        select(GitHubIssue)
        .join(Item, Item.id == GitHubIssue.item_id)
        .join(Source, Source.id == Item.source_id)
        .join(GitHubRepository, GitHubRepository.id == GitHubIssue.repository_id)
        .where(
            Item.available.is_(True),
            Source.enabled.is_(True),
            Source.status.not_in(["reauth", "forbidden"]),
        )
    )
    if owner:
        query = query.where(GitHubRepository.owner == owner)
    if repository_id:
        query = query.where(GitHubIssue.repository_id == repository_id)
    if state:
        query = query.where(GitHubIssue.state == state)
    if local_status:
        query = query.where(Item.status == local_status)
    for column, value in [(GitHubIssue.labels, label), (GitHubIssue.assignees, assignee)]:
        if value:
            if db.bind.dialect.name == "postgresql":
                query = query.where(cast(column, JSONB).contains([value]))
            else:
                values = func.json_each(column).table_valued("value")
                query = query.where(select(1).select_from(values).where(values.c.value == value).exists())
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(GitHubIssue.updated_at.desc(), GitHubIssue.id).offset(offset).limit(limit))
    return {
        "items": [issue_view(db, row) for row in rows],
        "total": total,
    }


def issue_labels(db):
    rows = db.scalars(
        select(GitHubIssue.labels)
        .join(Item, Item.id == GitHubIssue.item_id)
        .join(Source, Source.id == Item.source_id)
        .where(
            Item.available.is_(True), Source.enabled.is_(True),
            Source.status.not_in(["reauth", "forbidden"]),
        )
    )
    return sorted({label for labels in rows for label in labels}, key=str.casefold)


def issue(db, identity):
    row = db.get(GitHubIssue, identity)
    if not row:
        raise HTTPException(404, "Issue nicht gefunden.")
    visible_item(db, row.item_id)
    return row


def detail(db, identity):
    row = issue(db, identity)
    result = issue_view(db, row)
    result["comments"] = [
        CommentView.model_validate(c)
        for c in db.scalars(
            select(GitHubComment)
            .where(GitHubComment.issue_id == identity)
            .order_by(GitHubComment.updated_at)
        )
    ]
    result["conversations"] = [
        serialize(c)
        for c in db.scalars(select(Conversation))
        if row.item_id in c.item_ids
    ]
    return result


def link_chat(db, identity):
    row = issue(db, identity)
    return create_conversation(ConversationInput(item_ids=[row.item_id]), db=db)


def local_status(db, identity, body):
    row = issue(db, identity)
    db.get(Item, row.item_id).status = body.status
    audit(db, "github.issue.local_status", issue_id=identity, status=body.status)
    db.commit()
    return detail(db, identity)


def synchronize(db, body):
    jobs = []
    if body.repository_id:
        repo = db.get(GitHubRepository, body.repository_id)
        if not repo:
            raise HTTPException(404, "Repository nicht gefunden.")
        source = db.get(Source, repo.source_id)
        if not source.enabled:
            raise HTTPException(409, "Repository ist ausgeschlossen.")
        if not source.config.get("demo"):
            jobs.append(
                enqueue(db, "sync", {"source_id": source.id}, "sync:" + source.id)
            )
    else:
        rows = (
            [connection(db, body.connection_id)]
            if body.connection_id
            else db.scalars(select(GitHubConnection))
        )
        for row in rows:
            if row.enabled and not row.demo:
                jobs.append(
                    enqueue(
                        db,
                        "github_discover",
                        {"connection_id": row.id},
                        "github_discover:" + row.id,
                    )
                )
    for job in jobs:
        if job.status in {"done", "failed"}:
            job.status, job.attempts = "pending", 0
        job.run_after = now()
    event(db, "github.queued", jobs=len(jobs), demo=not jobs)
    db.commit()
    return {"ok": True}
