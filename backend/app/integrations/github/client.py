"""GET-only transport with persisted conditional requests and bounded pagination."""

from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import httpx
from sqlalchemy import select

from app.core.models import now
from app.core.security import decrypt
from app.features.github.models import GitHubCache

API = "https://api.github.com"


class GitHubError(Exception):
    def __init__(self, status, message, retry_after=0):
        super().__init__(message)
        self.status, self.retry_after = status, retry_after


class GitHubClient:
    def __init__(self, db, connection):
        self.db, self.connection = db, connection
        self.http = httpx.Client(
            timeout=40,
            follow_redirects=False,
            headers={
                "Authorization": "Bearer " + decrypt(connection.token),
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "Work-Agent/0.2",
            },
        )

    def close(self):
        self.http.close()

    def get(self, path, conditional=True):
        parsed = urlparse(path)
        if parsed.scheme or parsed.netloc:
            if parsed.scheme != "https" or parsed.netloc != "api.github.com":
                raise ValueError("Ungültiges GitHub-Paginierungsziel.")
            path = parsed.path + ("?" + parsed.query if parsed.query else "")
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("Ungültiger GitHub-Pfad.")
        if self.connection.retry_at and self.connection.retry_at > now():
            raise GitHubError(
                429,
                "GitHub-Abfragelimit: Fortsetzung nach der Wartezeit.",
                int((self.connection.retry_at - now()).total_seconds()) + 1,
            )
        cached = self.db.scalar(
            select(GitHubCache).where(
                GitHubCache.connection_id == self.connection.id,
                GitHubCache.path == path,
            )
        )
        headers = (
            {"If-None-Match": cached.etag}
            if conditional and cached and cached.etag
            else {}
        )
        response = self.http.get(API + path, headers=headers)
        if response.status_code == 304 and cached:
            return cached.payload["data"], cached.payload.get("next")
        if response.status_code == 429 or (
            response.status_code == 403
            and (
                response.headers.get("x-ratelimit-remaining") == "0"
                or "retry-after" in response.headers
            )
        ):
            wait = 60
            retry = response.headers.get("retry-after", "")
            if retry.isdigit():
                wait = int(retry)
            elif retry:
                try:
                    wait = int(
                        (
                            parsedate_to_datetime(retry).replace(tzinfo=None) - now()
                        ).total_seconds()
                    )
                except ValueError:
                    pass
            reset = response.headers.get("x-ratelimit-reset", "")
            if reset.isdigit():
                from datetime import datetime, timezone

                wait = max(
                    wait, int(int(reset) - datetime.now(timezone.utc).timestamp())
                )
            raise GitHubError(
                429, "GitHub-Abfragelimit erreicht; automatische Pause.", max(1, wait)
            )
        if response.status_code >= 300:
            messages = {
                401: "GitHub-Token ungültig oder abgelaufen.",
                403: "GitHub-Zugriff verweigert. Tokenrechte und Organisationsfreigabe prüfen.",
                404: "GitHub-Repository oder Inhalt nicht mehr zugänglich.",
            }
            raise GitHubError(
                response.status_code,
                messages.get(
                    response.status_code, "GitHub ist vorübergehend nicht erreichbar."
                ),
            )
        data = response.json()
        next_url = response.links.get("next", {}).get("url")
        if conditional:
            if not cached:
                cached = GitHubCache(connection_id=self.connection.id, path=path)
                self.db.add(cached)
            cached.etag = response.headers.get("etag")
            cached.payload, cached.fetched_at = {"data": data, "next": next_url}, now()
            # A page is durable before following its next link. No domain cursor is
            # advanced until the complete import succeeds; retries remain idempotent.
            self.db.commit()
        return data, next_url

    def pages(self, path):
        seen = set()
        while path:
            if path in seen or len(seen) >= 10000:
                raise ValueError(
                    "GitHub-Paginierung konnte nicht abgeschlossen werden."
                )
            seen.add(path)
            data, path = self.get(path)
            if not isinstance(data, list):
                raise ValueError("GitHub lieferte keine Ergebnisliste.")
            yield from data
