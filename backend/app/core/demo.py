from datetime import timedelta

from app.graph import upsert
from app.models import Source, now
from app.services import save_knowledge


def seed(db):
    from app.features.github.demo import seed as seed_github

    seed_github(db)
    sources = {}
    for kind, name in [
        ("mail", "Outlook · Demo"),
        ("chat", "Teams · Produktteam · Demo"),
        ("calendar", "Kalender · Demo"),
        ("todo", "Aufgaben · Demo"),
    ]:
        source = Source(
            kind=kind,
            name=name,
            config={"demo": True},
            status="ok",
            ai_enabled=True,
            writable=True,
        )
        db.add(source)
        db.flush()
        sources[kind] = source
    entries = [
        (
            "mail",
            "launch",
            "Freigabe für den Oktober-Launch",
            "Hallo, willkommen zurück! Können wir den Launch am 8. Oktober bestätigen? Uns fehlen noch die Rückmeldung vom Design und die finale Prüfung der Dokumentation. Kannst du das koordinieren? Viele Grüße, Lena",
            "Lena Hoffmann",
            15,
            {"email": "lena@example.com"},
        ),
        (
            "chat",
            "review",
            "Kurzer Abgleich zur API-Dokumentation",
            "Die neue API-Dokumentation liegt bereit. Magst du bis morgen Feedback geben? Die Authentifizierung und die Beispiele brauchen noch einen zweiten Blick.",
            "Jonas Weber",
            42,
            {"chat_id": "demo"},
        ),
        (
            "mail",
            "workshop",
            "Workshop: nächste Schritte und Verantwortlichkeiten",
            "Danke für die Vorbereitung. Bitte ergänze die Verantwortlichkeiten und schicke uns einen Vorschlag für einen 30-minütigen Folgetermin nächste Woche.",
            "Miriam Bauer",
            95,
            {"email": "miriam@example.com"},
        ),
    ]
    for kind, eid, title, body, sender, minutes, meta in entries:
        item, _ = upsert(
            db,
            sources[kind],
            eid,
            kind,
            title,
            body,
            sender,
            now() - timedelta(minutes=minutes),
            eid,
            meta=meta | {"demo": True},
            initial=True,
        )
        item.summary = "Rückmeldung und nächste Schritte abstimmen."
    upsert(
        db,
        sources["calendar"],
        "meeting",
        "calendar",
        "Produkt-Abstimmung",
        "Offene Punkte für die nächste Veröffentlichung.",
        occurred_at=now() + timedelta(hours=2),
        meta={
            "demo": True,
            "start": {
                "dateTime": (now() + timedelta(hours=2)).isoformat(),
                "timeZone": "UTC",
            },
            "end": {
                "dateTime": (now() + timedelta(hours=2, minutes=30)).isoformat(),
                "timeZone": "UTC",
            },
        },
        initial=True,
    )
    upsert(
        db,
        sources["todo"],
        "task",
        "task",
        "Release-Checkliste aktualisieren",
        "Designfreigabe und Dokumentation prüfen.",
        meta={
            "demo": True,
            "due": {"dateTime": (now() + timedelta(days=1)).isoformat()},
            "task_status": "notStarted",
        },
        initial=True,
    )
    note = save_knowledge(
        db,
        "So arbeite ich",
        "# Meine Arbeitsweise\n\n- Antworten sollen freundlich, knapp und verbindlich sein.\n- Vor Terminzusagen prüfe ich Abhängigkeiten.\n- Entscheidungen bekommen eine Quelle und ein Datum.\n\nDiese Notiz ist ein bearbeitbares Demo-Beispiel.",
    )
    db.get(Source, note.source_id).ai_enabled = True
