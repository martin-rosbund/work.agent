import asyncio
import json
from html import escape

from fastapi import Request
from fastapi.responses import (
    StreamingResponse,
)
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import (
    Audit,
    Event,
    Job,
    LoginSession,
    Usage,
    now,
)
from app.services import (
    serialize,
    setting,
)

PREFIX = "/api/v1"


def api_documentation(request: Request):
    """Self-contained API reference, compatible with the application's local-only CSP."""
    schema = request.app.openapi()
    routes = []
    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            routes.append(
                f"<details><summary><b>{escape(method.upper())}</b> {escape(path)} — {escape(operation.get('summary', ''))}</summary>"
                + "<pre>"
                + escape(json.dumps(operation, indent=2, ensure_ascii=False))
                + "</pre></details>"
            )
    return (
        '<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Work Agent · REST-API</title><style>body{font:16px system-ui;max-width:1100px;margin:40px auto;padding:0 20px;color:#173438}details{padding:14px;border-bottom:1px solid #ddd}summary{cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f1;padding:16px}a{color:#416c40}</style><h1>Work Agent · REST-API v1</h1><p>Sitzung: HttpOnly-Cookie. Schreibende Anfragen benötigen den X-CSRF-Token aus /auth/status. Einrichtung und Anmeldung prüfen zusätzlich den Browser-Ursprung.</p><p><a href="/api/v1/openapi.json">Vollständige OpenAPI-Spezifikation</a> · <a href="/">Zum Arbeitsraum</a></p>'
        + "".join(routes)
        + "<h2>Datenmodelle</h2><pre>"
        + escape(json.dumps(schema.get("components", {}), indent=2, ensure_ascii=False))
        + "</pre></html>"
    )


def health(db=None):
    db.execute(select(1))
    return {"status": "ok"}


def activity(session=None, db=None):
    return {
        "jobs": [
            serialize(j)
            for j in db.scalars(select(Job).order_by(Job.created_at.desc()).limit(50))
        ],
        "audit": [
            serialize(a)
            for a in db.scalars(select(Audit).order_by(Audit.id.desc()).limit(50))
        ],
        "usage": {
            "calls": db.scalar(select(func.count()).select_from(Usage)),
            "input_tokens": db.scalar(select(func.sum(Usage.input_tokens))) or 0,
            "output_tokens": db.scalar(select(func.sum(Usage.output_tokens))) or 0,
        },
        "worker": setting(db, "worker"),
    }


async def events(request: Request, after: int | None = None, session=None):

    async def stream():
        with SessionLocal() as initial_db:
            last_id = request.headers.get("last-event-id", "")
            cursor = (
                after
                if after is not None
                else int(last_id)
                if last_id.isdigit()
                else initial_db.scalar(select(func.max(Event.id))) or 0
            )
        while not await request.is_disconnected():
            with SessionLocal() as db:
                active = db.get(LoginSession, session.id)
                if not active or active.expires < now():
                    return
                rows = list(
                    db.scalars(
                        select(Event)
                        .where(Event.id > cursor)
                        .order_by(Event.id)
                        .limit(100)
                    )
                )
                for row in rows:
                    cursor = row.id
                    yield f"id: {row.id}\ndata: {json.dumps({'kind': row.kind, 'payload': row.payload}, ensure_ascii=False)}\n\n"
            yield ": heartbeat\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"}
    )
