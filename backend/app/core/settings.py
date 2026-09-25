from app.models import (
    Setting,
)

DEFAULT_AGENT = {
    "model": "",
    "embedding_model": "text-embedding-3-small",
    "instructions": "Du bist mein persönlicher Arbeitsassistent. Antworte auf Deutsch, präzise und mit überprüfbaren Quellen. Kennzeichne Unsicherheit.",
    "style": "Freundlich, klar und verbindlich",
    "daily_limit": 100,
    "paused": False,
    "allowed_actions": [
        "reply_email",
        "reply_teams",
        "create_event",
        "create_task",
        "update_task",
        "complete_task",
        "knowledge",
    ],
}


def setting(db, key, default=None):
    row = db.get(Setting, key)
    return row.value if row else (default if default is not None else {})


def put_setting(db, key, value):
    row = db.get(Setting, key)
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))


def agent_config(db):
    return DEFAULT_AGENT | setting(db, "agent")
