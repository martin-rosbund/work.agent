from html.parser import HTMLParser
from urllib.parse import quote, urlparse

import httpx
import msal
from sqlalchemy import select

from app.config import APP_ORIGIN, MAX_FILE_BYTES
from app.models import Setting, Source
from app.security import decrypt, encrypt
from app.services import put_setting, setting

"""Delegated Microsoft Graph access. Reads and approved writes use the same account."""

GRAPH = "https://graph.microsoft.com/v1.0"

READ_SCOPES = {
    "mail": ["Mail.Read"],
    "chat": ["Chat.Read"],
    "channel": [
        "Team.ReadBasic.All",
        "Channel.ReadBasic.All",
        "ChannelMessage.Read.All",
    ],
    "calendar": ["Calendars.Read"],
    "todo": ["Tasks.Read"],
    "drive": ["Files.Read.All", "Sites.Read.All"],
}

WRITE_SCOPES = {
    "mail": ["Mail.ReadWrite", "Mail.Send"],
    "chat": ["ChatMessage.Send"],
    "channel": ["ChannelMessage.Send"],
    "calendar": ["Calendars.ReadWrite"],
    "todo": ["Tasks.ReadWrite"],
}


class GraphError(Exception):
    def __init__(self, status, message, retry_after=60):
        super().__init__(message)
        self.status, self.retry_after = status, retry_after


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.ignore = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.ignore += 1
        if tag in {"br", "p", "div", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.ignore:
            self.ignore -= 1

    def handle_data(self, data):
        if not self.ignore:
            self.parts.append(data)


def plain(value):
    parser = TextParser()
    parser.feed(value or "")
    return "".join(parser.parts).strip()


def q(value):
    return quote(str(value), safe="")


def required_scopes(db):
    scopes = {"User.Read"}
    for source in db.scalars(select(Source).where(Source.enabled.is_(True))):
        scopes.update(READ_SCOPES.get(source.kind, []))
        if source.writable:
            scopes.update(WRITE_SCOPES.get(source.kind, []))
    return sorted(scopes)


def msal_client(db):
    cfg = setting(db, "microsoft")
    if not cfg.get("tenant_id") or not cfg.get("client_id") or not cfg.get("secret"):
        raise GraphError(401, "Microsoft-Verbindung zuerst einrichten.")
    cache = msal.SerializableTokenCache()
    stored = setting(db, "msal_cache").get("encrypted")
    if stored:
        cache.deserialize(decrypt(stored))
    app = msal.ConfidentialClientApplication(
        cfg["client_id"],
        client_credential=decrypt(cfg["secret"]),
        authority=f"https://login.microsoftonline.com/{cfg['tenant_id']}",
        token_cache=cache,
    )
    return app, cache


def save_cache(db, cache):
    if cache.has_state_changed:
        put_setting(db, "msal_cache", {"encrypted": encrypt(cache.serialize())})


def start_auth(db, scopes=None):
    app, _ = msal_client(db)
    flow = app.initiate_auth_code_flow(
        scopes=scopes or required_scopes(db),
        redirect_uri=f"{APP_ORIGIN}/api/v1/microsoft/callback",
    )
    return flow


def finish_auth(db, flow, params):
    # Serialize token-cache updates across callback, API discovery and the worker.
    db.scalar(select(Setting).where(Setting.key == "microsoft").with_for_update())
    app, cache = msal_client(db)
    result = app.acquire_token_by_auth_code_flow(flow, params)
    if "access_token" not in result:
        raise GraphError(
            401, "Microsoft-Anmeldung fehlgeschlagen oder Zustimmung fehlt."
        )
    claims = result.get("id_token_claims", {})
    existing = setting(db, "microsoft_account")
    identity = claims.get("oid")
    if existing.get("oid") and existing["oid"] != identity:
        raise GraphError(
            403, "Diese Installation ist bereits mit einem anderen Benutzer verbunden."
        )
    put_setting(
        db,
        "microsoft_account",
        {
            "oid": identity,
            "name": claims.get("name", ""),
            "username": claims.get("preferred_username", ""),
        },
    )
    save_cache(db, cache)


def access_token(db, scopes):
    db.scalar(select(Setting).where(Setting.key == "microsoft").with_for_update())
    app, cache = msal_client(db)
    accounts = app.get_accounts()
    result = (
        app.acquire_token_silent(scopes or ["User.Read"], account=accounts[0])
        if accounts
        else None
    )
    save_cache(db, cache)
    if not result or "access_token" not in result:
        raise GraphError(
            401, "Bitte Microsoft erneut verbinden und die benötigten Rechte freigeben."
        )
    return result["access_token"]


class Graph:
    def __init__(self, db, scopes=None, token=None):
        self.token = token or access_token(db, scopes or required_scopes(db))
        self.client = httpx.Client(timeout=40)

    def close(self):
        self.client.close()

    def request(self, method, path, payload=None, extra_headers=None):
        url = path if path.startswith("https://") else GRAPH + path
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "graph.microsoft.com"
            or not parsed.path.startswith("/v1.0/")
        ):
            raise ValueError("Ungültiger Graph-Fortsetzungslink.")
        response = self.client.request(
            method,
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Prefer": 'IdType="ImmutableId", outlook.timezone="UTC"',
                **(extra_headers or {}),
            },
        )
        if response.status_code >= 400:
            code = ""
            try:
                code = response.json().get("error", {}).get("code", "")
            except ValueError:
                pass
            raise GraphError(
                response.status_code,
                f"Microsoft Graph: {response.status_code} {code}",
                int(response.headers.get("Retry-After", "60"))
                if response.headers.get("Retry-After", "60").isdigit()
                else 60,
            )
        return response.json() if response.content else {}

    def pages(self, path):
        result, delta = [], None
        for _ in range(10000):
            data = self.request("GET", path)
            result.extend(data.get("value", []))
            delta = data.get("@odata.deltaLink", delta)
            path = data.get("@odata.nextLink")
            if not path:
                return result, delta
        raise GraphError(
            413, "Import zu groß; bitte Quelle oder Zeitraum einschränken."
        )

    def download(self, drive_id, item_id):
        url = f"{GRAPH}/drives/{q(drive_id)}/items/{q(item_id)}/content"
        headers = {"Authorization": f"Bearer {self.token}"}
        for _ in range(4):
            with self.client.stream("GET", url, headers=headers) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    url = response.headers["location"]
                    host = urlparse(url).hostname or ""
                    if urlparse(url).scheme != "https" or not any(
                        host.endswith(suffix)
                        for suffix in (
                            ".sharepoint.com",
                            ".1drv.com",
                            ".onedrive.com",
                            ".sharepoint-df.com",
                        )
                    ):
                        raise GraphError(400, "Unzulässiges Download-Ziel.")
                    headers = {}
                    continue
                if response.status_code >= 400:
                    raise GraphError(
                        response.status_code,
                        "Datei konnte nicht heruntergeladen werden.",
                    )
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_FILE_BYTES:
                        raise GraphError(413, "Datei überschreitet 25 MB.")
                    chunks.append(chunk)
                return b"".join(chunks)
        raise GraphError(400, "Zu viele Download-Weiterleitungen.")


def source_scopes(source):
    return READ_SCOPES.get(source.kind, ["User.Read"])


def discover(db, kind, parent=None, site_url=None):
    scopes = READ_SCOPES.get(kind, ["User.Read"])
    graph = Graph(db, scopes)
    try:
        if kind == "mail":
            path = (
                f"/me/mailFolders/{q(parent)}/childFolders"
                if parent
                else "/me/mailFolders"
            )
        elif kind == "chat":
            path = "/me/chats?$expand=members"
        elif kind == "channel":
            path = f"/teams/{q(parent)}/channels" if parent else "/me/joinedTeams"
        elif kind == "calendar":
            path = "/me/calendars"
        elif kind == "todo":
            path = "/me/todo/lists"
        elif kind == "drive":
            if site_url:
                parsed = urlparse(site_url)
                if parsed.scheme != "https" or not (parsed.hostname or "").endswith(
                    ".sharepoint.com"
                ):
                    raise ValueError(
                        "Bitte eine gültige SharePoint-Site-Adresse eingeben."
                    )
                site = graph.request(
                    "GET", f"/sites/{parsed.hostname}:{quote(parsed.path, safe='/')}"
                )
                path = f"/sites/{q(site['id'])}/drives"
            elif parent:
                drive_id, folder_id = parent.split("|", 1)
                path = (
                    f"/drives/{q(drive_id)}/root/children"
                    if folder_id == "root"
                    else f"/drives/{q(drive_id)}/items/{q(folder_id)}/children"
                )
            else:
                drive = graph.request("GET", "/me/drive")
                return [drive]
        else:
            raise ValueError("Unbekannter Bereich.")
        rows, _ = graph.pages(path)
        if kind == "chat":
            own_id = setting(db, "microsoft_account").get("oid")
            for row in rows:
                if not row.get("topic"):
                    row["topic"] = (
                        ", ".join(
                            member.get("displayName", "")
                            for member in row.get("members", [])
                            if member.get("userId") != own_id
                        )
                        or "Teams-Unterhaltung"
                    )
        return rows
    finally:
        graph.close()
