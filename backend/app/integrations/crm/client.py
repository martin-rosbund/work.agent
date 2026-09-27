"""ISB.CRM bearer API. Tokens never leave the configured origin or enter errors."""

import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.security import decrypt
from app.services import setting


class CrmError(Exception):
    def __init__(self, status, message, retry_after=30):
        self.status, self.retry_after = status, retry_after
        super().__init__(message)


def origin(value):
    parsed = urlsplit(value.strip())
    local = parsed.hostname in {"localhost", "127.0.0.1", "host.docker.internal", "::1"}
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or (parsed.scheme == "http" and not local)
    ):
        raise ValueError(
            "CRM-Adresse als HTTPS-Ursprung ohne Pfad eingeben; HTTP ist nur lokal erlaubt."
        )
    # Also validates an invalid port before storing the connection.
    parsed.port
    return urlunsplit((parsed.scheme, parsed.netloc.lower(), "", "", ""))


def check_connection(db, source):
    cfg = setting(db, "crm")
    if (
        not cfg.get("token")
        or not cfg.get("id")
        or source.config.get("crm_connection_id") != cfg["id"]
    ):
        raise CrmError(401, "Diese Quelle gehört zu einer getrennten CRM-Verbindung.")


class CRM:
    def __init__(self, db=None, *, url=None, token=None):
        cfg = setting(db, "crm") if db is not None else {}
        self.url = origin(url or cfg.get("api_url") or cfg.get("url", ""))
        if token is None:
            if not cfg.get("token"):
                raise CrmError(401, "Bitte den persönlichen CRM-API-Key hinterlegen.")
            token = decrypt(cfg["token"])
        transport_url = self.url
        parsed = urlsplit(transport_url)
        if Path("/.dockerenv").exists() and parsed.hostname in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            transport_url = f"{parsed.scheme}://host.docker.internal" + (
                f":{parsed.port}" if parsed.port else ""
            )
        self.client = httpx.Client(
            base_url=transport_url,
            timeout=30,
            follow_redirects=False,
            headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
        )

    def close(self):
        self.client.close()

    def request(self, method, path, data=None, params=None):
        if not path.startswith("/api/") or "://" in path:
            raise ValueError("Ungültiger CRM-API-Pfad.")
        try:
            response = self.client.request(method, path, json=data, params=params)
        except httpx.HTTPError as exc:
            raise CrmError(
                503,
                "CRM nicht erreichbar. Adresse, lokalen Dienst und Verbindung prüfen.",
            ) from exc
        if not 200 <= response.status_code < 300:
            status = response.status_code
            message = {
                401: "CRM-API-Key ist ungültig oder abgelaufen.",
                403: "CRM-Berechtigung fehlt für diesen Bereich oder ein Feld.",
                404: "CRM-Datensatz oder API nicht gefunden.",
                409: "Datensatz im CRM geändert. Neu synchronisieren und Vorschlag erneut prüfen.",
                429: "CRM-Anfragelimit erreicht. Später erneut versuchen.",
            }.get(
                status,
                "CRM hat die Anfrage abgelehnt. Pflichtfelder und Verbindung prüfen.",
            )
            raise CrmError(status, message)
        try:
            return response.json()
        except ValueError as exc:
            raise CrmError(
                502, "Keine gültige CRM-API-Antwort. Bitte die CRM-Adresse prüfen."
            ) from exc

    def rows(self, entity, filters=None, relations=None):
        rows, seen = [], set()
        for page in range(1, 1001):
            result = self.request(
                "GET",
                "/api/generic/" + entity,
                params={
                    "page": page,
                    "limit": 100,
                    "filter": json.dumps(filters or {}),
                    "orderBy": json.dumps({"handle": "ASC"}),
                    "relations": json.dumps(relations or []),
                },
            )
            data, meta = result.get("data"), result.get("meta", {})
            if not isinstance(data, list) or not isinstance(
                meta.get("totalPages"), int
            ):
                raise CrmError(
                    502,
                    "Unvollständige CRM-Seitenantwort. Synchronisierung abgebrochen.",
                )
            for row in data:
                key = str(row.get("handle", ""))
                if not key or key in seen:
                    raise CrmError(
                        502,
                        "CRM-Seiten haben sich während der Synchronisierung geändert.",
                    )
                seen.add(key)
            rows.extend(data)
            if page >= meta["totalPages"]:
                if len(rows) != meta.get("total", len(rows)):
                    raise CrmError(
                        502,
                        "CRM-Datenbestand während des Ladens geändert. Erneut synchronisieren.",
                    )
                return rows
        raise CrmError(
            502, "CRM-Seitenlimit erreicht. Synchronisierung nicht vollständig."
        )
