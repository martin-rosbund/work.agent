"""Paged Teams selection with opaque, expiring continuation tokens."""

import json
import time

from cryptography.fernet import InvalidToken

from app.core.security import decrypt, encrypt
from app.services import setting
from .client import Graph


def chat_page(db, continuation=None):
    path = "/me/chats?$expand=members&$top=50&$orderby=lastMessagePreview/createdDateTime desc"
    if continuation:
        try:
            cursor = json.loads(decrypt(continuation))
            if cursor["purpose"] != "chat-picker" or cursor["expires"] < time.time():
                raise ValueError()
            path = cursor["path"]
        except (InvalidToken, ValueError, KeyError, TypeError):
            raise ValueError("Die Chat-Auswahl ist abgelaufen. Bitte Quellen erneut laden.") from None
    graph = Graph(db, ["Chat.Read"])
    try:
        data = graph.request("GET", path)
        own_id = setting(db, "microsoft_account").get("oid")
        rows = []
        for chat in data.get("value", []):
            names = [
                member["displayName"]
                for member in (chat.get("members") or [])
                if (not own_id or member.get("userId") != own_id) and member.get("displayName")
            ]
            rows.append({
                "id": chat["id"], "chatType": chat.get("chatType"),
                "topic": chat.get("topic") or ", ".join(names) or "Teams-Unterhaltung",
                "participants": names,
            })
        next_path = data.get("@odata.nextLink")
        next_token = encrypt(json.dumps({
            "purpose": "chat-picker", "path": next_path, "expires": time.time() + 900,
        })) if next_path else None
        db.commit()
        return {"items": rows, "continuation": next_token}
    finally:
        graph.close()
