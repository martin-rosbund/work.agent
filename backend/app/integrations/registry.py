"""Read-only source boundary. Approved writes belong exclusively to actions.py."""

from typing import Protocol

from sqlalchemy.orm import Session

from app import graph
from app.models import Source


class SourceConnector(Protocol):
    def sync(self, db: Session, source: Source) -> None: ...

    def discover(
        self,
        db: Session,
        kind: str,
        parent: str | None = None,
        site_url: str | None = None,
    ) -> list[dict]: ...


class MicrosoftConnector:
    def sync(self, db, source):
        return graph.sync_source(db, source)

    def discover(self, db, kind, parent=None, site_url=None):
        return graph.discover(db, kind, parent, site_url)


class GitHubConnector:
    def sync(self, db, source):
        from app.features.github.sync import sync_source

        return sync_source(db, source)

    def discover(self, db, kind, parent=None, site_url=None):
        raise ValueError("GitHub-Repositories werden über die GitHub-Verbindungen ausgewählt.")


def connector_for(kind: str) -> SourceConnector:
    if kind == "github":
        return GitHubConnector()
    if kind in graph.READ_SCOPES:
        return MicrosoftConnector()
    raise ValueError("Für diese Quelle ist kein externer Konnektor registriert.")
