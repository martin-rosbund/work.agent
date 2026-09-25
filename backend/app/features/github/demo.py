from sqlalchemy import select

from app.core.models import Source, now

from .models import GitHubConnection, GitHubRepository
from .sync import import_issue


def seed(db):
    if db.scalar(select(GitHubConnection).where(GitHubConnection.demo.is_(True))):
        return
    connection = GitHubConnection(
        owner="demo-team", name="GitHub · Demo", token="", demo=True, status="ok"
    )
    db.add(connection)
    db.flush()
    for index, name in enumerate(["work-agent", "team-portal"]):
        source = Source(
            kind="github",
            name="demo-team/" + name,
            config={"demo": True},
            ai_enabled=False,
            status="ok",
        )
        db.add(source)
        db.flush()
        repo = GitHubRepository(
            connection_id=connection.id,
            source_id=source.id,
            external_id=str(index),
            owner=connection.owner,
            name=name,
            full_name=source.name,
            web_url="https://github.com/demo-team/" + name,
        )
        db.add(repo)
        db.flush()
        source.config = {
            "demo": True,
            "repository_id": repo.id,
            "connection_id": connection.id,
        }
        for number, title, state in [
            (42, "Kalender: Zeitzone beim Planen berücksichtigen", "open"),
            (43, "Barrierefreie Beschriftung der Suche", "closed"),
        ]:
            stamp = now().isoformat() + "Z"
            data = {
                "id": index * 100 + number,
                "number": number,
                "title": title,
                "state": state,
                "body": "## Demo-Issue\n\nBeim Planen müssen Termine in Europe/Berlin angezeigt werden.\n\n**Abnahme:** Sommer- und Winterzeit prüfen.",
                "user": {"login": "alex-demo"},
                "labels": [{"name": "bug" if state == "open" else "enhancement"}],
                "assignees": [{"login": "sam-demo"}],
                "milestone": {"title": "Version 0.2"},
                "html_url": repo.web_url + "/issues/" + str(number),
                "created_at": stamp,
                "updated_at": stamp,
                "closed_at": stamp if state == "closed" else None,
            }
            comments = [
                {
                    "id": number,
                    "user": {"login": "sam-demo"},
                    "body": "Reproduziert. Bitte den Zeitwechsel im Test abdecken.",
                    "updated_at": stamp,
                    "html_url": data["html_url"] + "#issuecomment-demo",
                }
            ]
            links = (
                [
                    {
                        "number": 44,
                        "title": "Zeitzonenprüfung ergänzen",
                        "url": repo.web_url + "/pull/44",
                        "state": "open",
                    }
                ]
                if state == "open"
                else []
            )
            import_issue(db, source, repo, data, comments, links, True)
