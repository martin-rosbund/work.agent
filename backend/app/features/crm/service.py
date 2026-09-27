from fastapi import HTTPException
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select
from app.models import Source, now, uid
from app.security import encrypt
from app.services import audit, put_setting, setting
from app.integrations.crm.client import CRM, CrmError, origin
from app.integrations.crm.mapping import TYPES
from .schemas import CrmConnectionInput


def connection(session=None, db=None):
    cfg = setting(db, "crm")
    return {
        "url": cfg.get("url", ""),
        "api_url": cfg.get("api_url", ""),
        "configured": bool(cfg.get("token")),
        "name": cfg.get("name", ""),
        "person": str(cfg.get("person", "")),
    }


def profile(client):
    person = client.request("GET", "/api/current/person")
    if not isinstance(person, dict) or not person.get("handle"):
        raise CrmError(502, "CRM hat kein gültiges persönliches Profil geliefert.")
    return person


def connect(body: CrmConnectionInput, session=None, db=None):
    url, old = origin(body.url), setting(db, "crm")
    api_url = origin(body.api_url or body.url)
    same_origin = not old.get("url") or (
        old["url"] == url and old.get("api_url", old["url"]) == api_url
    )
    if old.get("token") and not same_origin:
        raise HTTPException(
            409, "Bitte die bestehende Verbindung vor dem Wechsel des CRM trennen."
        )
    if not body.token and not old.get("token"):
        raise HTTPException(400, "Bitte einen persönlichen API-Key eingeben.")
    client = CRM(db, url=api_url, token=body.token or None)
    try:
        person = profile(client)
        same_person = not old.get("person") or str(old["person"]) == str(
            person["handle"]
        )
        if old.get("token") and not same_person:
            raise HTTPException(
                409,
                "Bitte die bestehende Verbindung vor einem Benutzerwechsel trennen.",
            )
        with ThreadPoolExecutor(max_workers=4) as pool:
            checks = {
                kind: pool.submit(
                    client.request, "GET", "/api/current/permission/" + spec["entity"]
                )
                for kind, spec in TYPES.items()
            }
            permissions = {kind: future.result() for kind, future in checks.items()}
    finally:
        client.close()
    connection_id = old.get("id") if same_origin and same_person else None
    connection_id = connection_id or uid()
    put_setting(
        db,
        "crm",
        {
            "id": connection_id,
            "url": url,
            "api_url": api_url,
            "token": encrypt(body.token) if body.token else old["token"],
            "person": person["handle"],
            "name": person.get("displayName")
            or " ".join(filter(None, [person.get("firstName"), person.get("lastName")]))
            or str(person["handle"]),
        },
    )
    for kind, spec in TYPES.items():
        source = db.scalar(
            select(Source).where(
                Source.kind == kind,
                Source.config["crm_connection_id"].as_string() == connection_id,
            )
        )
        readable = permissions[kind].get("allowRead") is True
        if not source:
            source = Source(
                kind=kind,
                name=spec["label"],
                config={"crm_connection_id": connection_id},
                enabled=readable,
                ai_enabled=False,
                writable=False,
            )
            db.add(source)
        source.status = "pending" if readable else "forbidden"
        source.error = None if readable else "Leserecht für diesen CRM-Bereich fehlt."
        source.next_sync = now()
    audit(db, "crm.connected")
    db.commit()
    return connection(db=db)


def test_connection(session=None, db=None):
    cfg = setting(db, "crm")
    if not cfg.get("token"):
        raise CrmError(401, "Bitte zuerst die CRM-Verbindung einrichten.")
    return connect(
        CrmConnectionInput(url=cfg["url"], api_url=cfg.get("api_url", "")), db=db
    )


def disconnect(session=None, db=None):
    cfg = setting(db, "crm")
    cfg = {k: v for k, v in cfg.items() if k != "token"}
    put_setting(db, "crm", cfg)
    for source in db.scalars(select(Source).where(Source.kind.in_(TYPES))):
        source.enabled, source.writable, source.ai_enabled = False, False, False
        source.status, source.error = "reauth", "CRM-Verbindung wurde getrennt."
    audit(db, "crm.disconnected")
    db.commit()
    return connection(db=db)


def options(kind: str, session=None, db=None):
    if kind not in TYPES:
        raise HTTPException(404, "Unbekannter CRM-Bereich.")
    from app.integrations.crm.mapping import handle, status_closed

    client = CRM(db)

    def choices(entity, statuses=False):
        return [
            {
                "value": handle(row),
                "label": row.get("description") or row.get("title") or handle(row),
                "closed": status_closed(kind, row) if statuses else False,
            }
            for row in client.rows(entity)
        ]

    try:
        catalogs = {"statuses": TYPES[kind]["catalog"]}
        if kind == "crm_ticket":
            catalogs.update(
                types="ticketType",
                categories="ticketCategory",
                origins="ticketSource",
                priorities="ticketPriority",
            )
        if kind == "crm_sales":
            catalogs.update(
                types="salesOpportunityStage",
                forecasts="salesOpportunityForecast",
                origins="salesOpportunitySource",
                loss_reasons="salesOpportunityLossReason",
            )
        if kind in {"crm_office", "crm_event"}:
            catalogs["categories"] = (
                "internalCaseCategory" if kind == "crm_office" else "eventCategory"
            )
        if kind == "crm_event":
            catalogs["types"] = "eventType"
        with ThreadPoolExecutor(max_workers=5) as pool:
            pending = {
                key: pool.submit(choices, entity, key == "statuses")
                for key, entity in catalogs.items()
            }
            return {key: future.result() for key, future in pending.items()}
    finally:
        client.close()
