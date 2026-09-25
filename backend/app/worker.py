import time
from datetime import timedelta

from sqlalchemy import delete, select, update

from app.core.logging import worker_failure
from app.features.github import sync as github_sync
from app.features.github.models import GitHubConnection
from app.integrations.github.client import GitHubError

from . import actions, ai
from .connectors import connector_for
from .db import SessionLocal
from .extract import extract
from .graph import GraphError
from .models import Event, Item, Job, Proposal, Source, now
from .services import (
    agent_config,
    enqueue,
    event,
    export_knowledge,
    put_setting,
    replace_chunks,
)


def schedule(db):
    github_sync.schedule(db)
    for source in db.scalars(
        select(Source).where(Source.enabled.is_(True), Source.next_sync <= now())
    ):
        if source.kind in {"uploads", "knowledge", "local_tasks"} or source.config.get(
            "demo"
        ):
            continue
        if source.status in {"reauth", "forbidden"}:
            continue
        enqueue(db, "sync", {"source_id": source.id}, f"sync:{source.id}")
        source.next_sync = now() + timedelta(
            minutes=2 if source.kind in {"mail", "chat", "channel"} else 5
        )


def recover(db):
    for job in db.scalars(
        select(Job)
        .where(Job.status == "running", Job.started_at < now() - timedelta(minutes=10))
        .with_for_update(skip_locked=True)
    ):
        if job.kind == "execute":
            proposal = db.get(Proposal, job.payload["proposal_id"])
            if proposal and proposal.status == "executing":
                proposal.status, proposal.result = (
                    "unknown",
                    {
                        "error": "Hintergrundprozess wurde während der Ausführung beendet. Bitte bei Microsoft prüfen."
                    },
                )
                job.status, job.error = "failed", "Ausführungsergebnis unklar."
            elif proposal and proposal.status in {
                "done",
                "demo_done",
                "unknown",
                "failed",
            }:
                job.status = "done"
            else:
                job.status = "pending"
        else:
            job.status = "pending"


def claim(db):
    job = db.scalar(
        select(Job)
        .where(Job.status == "pending", Job.run_after <= now())
        .order_by(Job.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job:
        job.status, job.started_at, job.attempts = "running", now(), job.attempts + 1
        db.commit()
    return job.id if job else None


def perform(db, job):
    p = job.payload
    if job.kind == "github_discover":
        connection = db.get(GitHubConnection, p["connection_id"])
        if connection:
            github_sync.discover(db, connection)
    elif job.kind == "sync":
        source = db.get(Source, p["source_id"])
        if source and source.enabled and not source.config.get("demo"):
            connector_for(source.kind).sync(db, source)
    elif job.kind == "extract":
        item = db.get(Item, p["item_id"])
        if item and item.available and item.version == p["version"]:
            sections = extract(item.file_path)
            item.body = "\n\n".join(f"{locator}\n{text}" for locator, text in sections)
            item.processing, item.processing_error = "ready", None
            replace_chunks(db, item, sections)
    elif job.kind == "export":
        export_knowledge(db, p["item_id"])
    elif job.kind == "embed":
        ai.embed_item(db, p["item_id"])
    elif job.kind == "chat":
        ai.chat(db, p["conversation_id"])
    elif job.kind == "analyze":
        ai.analyze(db, p["item_id"], p.get("background", False))
    elif job.kind == "execute":
        actions.execute(db, p["proposal_id"])


def run_job(job_id):
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        try:
            perform(db, job)
            job.status, job.error = "done", None
            if job.kind in {"sync", "chat", "github_discover"}:
                job.dedupe_key = None
            event(db, "job.done", job_id=job.id, kind=job.kind)
            db.commit()
        except Exception as exc:
            db.rollback()
            job = db.get(Job, job_id)
            message = str(exc.detail) if hasattr(exc, "detail") else str(exc)
            # Do not persist raw third-party exception bodies, which may echo request contents.
            safe = (
                message[:500]
                if isinstance(exc, (ValueError, GraphError, GitHubError))
                or hasattr(exc, "detail")
                else f"{type(exc).__name__}: Verarbeitung fehlgeschlagen. Verbindung und Einstellungen prüfen."
            )
            job.error = safe
            if job.kind == "execute":
                proposal = db.get(Proposal, job.payload["proposal_id"])
                if proposal and proposal.status == "executing":
                    proposal.status, proposal.result = "unknown", {"error": safe}
                elif proposal and proposal.status == "approved":
                    proposal.status, proposal.result = "failed", {"error": safe}
                job.status = "failed"
            elif isinstance(exc, GitHubError):
                if exc.status in {401, 403, 404, 410}:
                    job.status, job.dedupe_key = "failed", None
                else:
                    job.status = "pending"
                    job.run_after = now() + timedelta(
                        seconds=max(
                            exc.retry_after, min(3600, 30 * 2 ** min(job.attempts, 6))
                        )
                    )
            elif isinstance(exc, GraphError) and job.kind == "sync":
                source = db.get(Source, job.payload["source_id"])
                if exc.status in {401, 403, 404}:
                    source.status = "reauth" if exc.status == 401 else "forbidden"
                    source.error, job.status, job.dedupe_key = safe, "failed", None
                else:
                    if exc.status == 410:
                        source.cursor = {}
                    source.status, source.error = "error", safe
                    job.status = "pending"
                    job.run_after = now() + timedelta(
                        seconds=max(
                            exc.retry_after, min(3600, 30 * 2 ** min(job.attempts, 6))
                        )
                    )
            elif "Tageslimit" in safe or "pausiert" in safe:
                job.status, job.run_after = "pending", now() + timedelta(minutes=15)
            elif job.attempts < 3 and not hasattr(exc, "status_code"):
                job.status, job.run_after = (
                    "pending",
                    now() + timedelta(seconds=30 * job.attempts),
                )
            else:
                job.status = "failed"
                if job.kind in {"sync", "chat", "github_discover"}:
                    job.dedupe_key = None
                if job.kind == "extract":
                    item = db.get(Item, job.payload["item_id"])
                    if item:
                        item.processing, item.processing_error = "error", safe
            event(db, "job.error", job_id=job.id, kind=job.kind, error=safe)
            db.commit()


def main():
    last_housekeeping = 0
    while True:
        try:
            with SessionLocal() as db:
                if time.monotonic() - last_housekeeping > 30:
                    recover(db)
                    schedule(db)
                    put_setting(db, "worker", {"heartbeat": now().isoformat()})
                    db.execute(
                        delete(Event).where(
                            Event.created_at < now() - timedelta(days=1)
                        )
                    )
                    db.commit()
                    last_housekeeping = time.monotonic()
                job_id = claim(db)
            if job_id:
                run_job(job_id)
            else:
                time.sleep(2)
        except Exception as exc:
            worker_failure(exc)
            time.sleep(5)


if __name__ == "__main__":
    main()
