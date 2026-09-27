import json
import secrets
from datetime import timedelta

from fastapi import HTTPException, Request, Response
from fastapi.responses import (
    RedirectResponse,
)
from sqlalchemy import select

from app import actions, ai, graph
from app.config import (
    APP_ORIGIN,
)
from app.connectors import connector_for
from app.core.config import OAUTH_COOKIE
from app.models import (
    Item,
    Source,
    now,
    uid,
)
from app.security import (
    decrypt,
    encrypt,
    token_hash,
)
from app.services import (
    agent_config,
    audit,
    enqueue,
    put_setting,
    serialize,
    setting,
)

from .schemas import (
    AgentSettings,
    AuthStart,
    KeySettings,
    MicrosoftSettings,
    SourceInput,
    SourceUpdate,
)

PREFIX = "/api/v1"


def settings(session=None, db=None):
    ms = setting(db, "microsoft")
    return {
        "agent": agent_config(db),
        "openai_configured": bool(setting(db, "openai").get("key")),
        "microsoft": {k: v for k, v in ms.items() if k != "secret"},
        "microsoft_configured": bool(ms.get("secret")),
        "account": setting(db, "microsoft_account"),
        "redirect_uri": APP_ORIGIN + "/api/v1/microsoft/callback",
        "worker": setting(db, "worker"),
    }


def update_agent(body: AgentSettings, session=None, db=None):
    if not set(body.allowed_actions) <= actions.KINDS:
        raise HTTPException(400, "Unbekannte Aktion im Agentenprofil.")
    old = agent_config(db)
    put_setting(db, "agent", body.model_dump())
    if old["embedding_model"] != body.embedding_model:
        for item in db.scalars(
            select(Item)
            .join(Source)
            .where(
                Source.enabled.is_(True),
                Source.ai_enabled.is_(True),
                Item.available.is_(True),
            )
        ):
            enqueue(db, "embed", {"item_id": item.id}, f"reindex:{uid()}:{item.id}")
    db.commit()
    return {"ok": True}


def openai_settings(body: KeySettings, session=None, db=None):
    put_setting(db, "openai", {"key": encrypt(body.api_key)})
    for item in db.scalars(
        select(Item)
        .join(Source)
        .where(
            Source.enabled.is_(True),
            Source.ai_enabled.is_(True),
            Item.available.is_(True),
            Item.processing == "ready",
        )
    ):
        enqueue(
            db, "embed", {"item_id": item.id}, f"provider-configured:{uid()}:{item.id}"
        )
    db.commit()
    return {"ok": True}


def models(session=None, db=None):
    try:
        provider = ai.OpenAIProvider(db)
        return sorted([model.id for model in provider.client.models.list().data])
    except Exception:
        raise HTTPException(
            400,
            "Modelle konnten nicht geladen werden. API-Schlüssel und Verbindung prüfen.",
        )


def openai_test(session=None, db=None):
    try:
        provider = ai.OpenAIProvider(db)
        answer, _ = provider.generate(
            "Antworte mit OK.",
            [{"role": "user", "content": "Verbindungstest ohne Arbeitsdaten."}],
        )
        vectors, _ = provider.embed(["Verbindungstest ohne Arbeitsdaten."])
        return {"ok": True, "answer": answer, "embedding_dimension": len(vectors[0])}
    except Exception:
        raise HTTPException(
            400,
            "Modelltest fehlgeschlagen. Modellnamen, API-Schlüssel und Kontingent prüfen.",
        )


def microsoft_settings(body: MicrosoftSettings, session=None, db=None):
    existing = setting(db, "microsoft")
    if (
        existing
        and (
            existing.get("tenant_id") != str(body.tenant_id)
            or existing.get("client_id") != str(body.client_id)
        )
        and setting(db, "microsoft_account")
    ):
        raise HTTPException(
            409,
            "Eine bestehende Kontoverbindung kann nicht auf eine andere App umgestellt werden.",
        )
    put_setting(
        db,
        "microsoft",
        {
            "tenant_id": str(body.tenant_id),
            "client_id": str(body.client_id),
            "secret": (
                encrypt(body.client_secret)
                if body.client_secret
                else existing.get("secret", "")
            ),
        },
    )
    db.commit()
    return {"ok": True}


def microsoft_auth(body: AuthStart, response: Response, session=None, db=None):
    scopes = set(graph.required_scopes(db))
    scopes.update(graph.READ_SCOPES.get(body.kind, []))
    if body.write:
        scopes.update(graph.WRITE_SCOPES.get(body.kind, []))
    flow = graph.start_auth(db, sorted(scopes))
    binding = secrets.token_urlsafe(32)
    put_setting(
        db,
        "oauth:" + flow["state"],
        {
            "flow": encrypt(json.dumps(flow)),
            "binding": token_hash(binding),
            "expires": (now() + timedelta(minutes=10)).isoformat(),
        },
    )
    db.commit()
    response.set_cookie(
        OAUTH_COOKIE,
        binding,
        httponly=True,
        samesite="lax",
        max_age=600,
        secure=APP_ORIGIN.startswith("https:"),
        path=PREFIX + "/microsoft/callback",
    )
    return {"url": flow["auth_uri"]}


def microsoft_callback(request: Request, db=None):
    state = request.query_params.get("state", "")
    stored = setting(db, "oauth:" + state)
    if (
        not stored
        or graph.date(stored["expires"]) < now()
        or (
            not secrets.compare_digest(
                stored["binding"],
                token_hash(request.cookies.get(OAUTH_COOKIE, "")),
            )
        )
    ):
        raise HTTPException(
            403, "Anmeldung abgelaufen oder ungültig. Bitte erneut verbinden."
        )
    flow = json.loads(decrypt(stored["flow"]))
    from app.models import Setting

    db.delete(db.get(Setting, "oauth:" + state))
    db.commit()
    graph.finish_auth(db, flow, dict(request.query_params))
    for source in db.scalars(
        select(Source).where(
            Source.status.in_(["reauth", "forbidden"]), Source.kind != "github"
        )
    ):
        source.status, source.next_sync = ("pending", now())
    db.commit()
    response = RedirectResponse(APP_ORIGIN + "/#settings")
    response.delete_cookie(OAUTH_COOKIE, path=PREFIX + "/microsoft/callback")
    return response


def microsoft_test(session=None, db=None):
    client = graph.Graph(db, ["User.Read"])
    try:
        result = client.request("GET", "/me?$select=displayName,userPrincipalName")
        db.commit()
        return result
    finally:
        client.close()


def discover(
    kind: str,
    parent: str | None = None,
    site_url: str | None = None,
    session=None,
    db=None,
):
    result = connector_for(kind).discover(db, kind, parent, site_url)
    db.commit()
    return result


def sources(session=None, db=None):
    return [
        serialize(source)
        for source in db.scalars(select(Source).order_by(Source.created_at))
        if not source.kind.startswith("crm_")
        or source.config.get("crm_connection_id") == setting(db, "crm").get("id")
    ]


def validate_source(body):
    if body.kind not in graph.READ_SCOPES:
        raise HTTPException(400, "Unbekannte Microsoft-Quelle.")
    required = {
        "mail": ["folder_id"],
        "chat": ["chat_id"],
        "channel": ["team_id", "channel_id"],
        "calendar": ["calendar_id"],
        "todo": ["list_id"],
        "drive": ["drive_id", "folder_id"],
    }[body.kind]
    if body.kind == "chat" and body.config.get("mode") == "all_direct_incoming":
        required = []
        if body.config.get("chat_id"):
            raise HTTPException(
                400, "Bitte Einzelchat oder alle Direktnachrichten auswählen."
            )
    if any(
        (
            not isinstance(body.config.get(key), str) or not body.config[key]
            for key in required
        )
    ):
        raise HTTPException(400, "Bitte eine Quelle über die Auswahl verbinden.")
    if body.config.get("demo"):
        raise HTTPException(
            400, "Demoquellen können nicht über die Microsoft-Auswahl erstellt werden."
        )
    days = body.config.get("days", 90)
    if not isinstance(days, int) or not 1 <= days <= 3650:
        raise HTTPException(
            400, "Importzeitraum muss zwischen 1 und 3650 Tagen liegen."
        )


def create_source(body: SourceInput, session=None, db=None):
    validate_source(body)
    if body.kind == "drive" and body.config["folder_id"] == "root":
        client = graph.Graph(db, graph.READ_SCOPES["drive"])
        try:
            root = client.request(
                "GET", f"/drives/{graph.q(body.config['drive_id'])}/root"
            )
            body.config["folder_id"] = root["id"]
        finally:
            client.close()
    for source in db.scalars(select(Source).where(Source.kind == body.kind)):
        if source.config == body.config:
            raise HTTPException(409, "Diese Quelle ist bereits verbunden.")
    row = Source(**body.model_dump())
    db.add(row)
    db.commit()
    return serialize(row)


def update_source(source_id: str, body: SourceUpdate, session=None, db=None):
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(404, "Quelle nicht gefunden.")
    if source.kind.startswith("crm_") and any(
        [body.enabled, body.writable, body.ai_enabled]
    ):
        from app.integrations.crm.client import check_connection

        check_connection(db, source)
    if source.kind == "github" and body.writable:
        raise HTTPException(
            400, "GitHub-Verbindungen unterstützen ausschließlich lesenden Zugriff."
        )
    previous_ai = source.ai_enabled
    for key, value in body.model_dump(exclude_none=True).items():
        if key == "days":
            source.config = source.config | {"days": value}
            source.cursor = {}
        else:
            setattr(source, key, value)
    source.next_sync = now()
    if not previous_ai and source.ai_enabled:
        for item in db.scalars(
            select(Item).where(Item.source_id == source.id, Item.available.is_(True))
        ):
            enqueue(db, "embed", {"item_id": item.id}, f"consent:{uid()}:{item.id}")
    audit(
        db,
        "source.updated",
        source_id=source.id,
        changes=body.model_dump(exclude_none=True),
    )
    db.commit()
    return serialize(source)


def sync(source_id: str, session=None, db=None):
    source = db.get(Source, source_id)
    if not source or not source.enabled:
        raise HTTPException(404, "Aktive Quelle nicht gefunden.")
    job = enqueue(db, "sync", {"source_id": source_id}, f"sync:{source_id}")
    job.run_after = now()
    db.commit()
    return serialize(job)
