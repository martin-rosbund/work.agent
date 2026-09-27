from app.integrations.microsoft import client as graph
from app.services import put_setting


def test_chat_pages_return_first_results_and_follow_opaque_cursor(logged, monkeypatch):
    from app.integrations.microsoft import chat_discovery
    calls = []

    class FakeGraph:
        def __init__(self, *args):
            pass

        def request(self, method, path):
            calls.append(path)
            if len(calls) == 1:
                return {"value": [{"id": "1", "members": [{"displayName": "Alex"}]}],
                        "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/chats?$skiptoken=next"}
            return {"value": [{"id": "2", "topic": "Project", "members": [{"displayName": "Sam"}]}]}

        def close(self):
            pass

    monkeypatch.setattr(chat_discovery, "Graph", FakeGraph)
    first = logged.get("/api/v1/microsoft/chats/page")
    assert first.status_code == 200
    assert len(calls) == 1
    assert first.json()["items"][0]["topic"] == "Alex"
    assert "graph.microsoft.com" not in first.json()["continuation"]
    second = logged.get("/api/v1/microsoft/chats/page", params={"continuation": first.json()["continuation"]})
    assert second.status_code == 200
    assert second.json()["continuation"] is None
    assert second.json()["items"][0]["participants"] == ["Sam"]


def test_chat_page_rejects_forged_cursor(db):
    import pytest
    from app.integrations.microsoft.chat_discovery import chat_page
    with pytest.raises(ValueError, match="abgelaufen"):
        chat_page(db, "https://evil.example/token")


def test_chat_discovery_handles_missing_member_names(logged, db, monkeypatch):
    put_setting(db, "microsoft_account", {"oid": "self"})
    db.commit()
    closed = []

    class FakeGraph:
        def __init__(self, db, scopes):
            assert scopes == ["Chat.Read"]

        def pages(self, path):
            assert path == "/me/chats?$expand=members"
            return [
                {"id": "mixed", "topic": None, "members": [
                    {"userId": "self", "displayName": "Own name"},
                    {"userId": "other", "displayName": "Alex"},
                    {"userId": "deleted", "displayName": None},
                    {"userId": "missing"},
                ]},
                {"id": "empty", "members": [{"displayName": None}]},
                {"id": "null-members", "members": None},
                {"id": "no-members"},
                {"id": "named", "topic": "Project", "members": None},
            ], None

        def close(self):
            closed.append(True)

    monkeypatch.setattr(graph, "Graph", FakeGraph)
    response = logged.get("/api/v1/microsoft/discover/chat")
    assert response.status_code == 200, response.text
    assert [row["topic"] for row in response.json()] == [
        "Alex", "Teams-Unterhaltung", "Teams-Unterhaltung", "Teams-Unterhaltung", "Project"
    ]
    assert closed == [True]
