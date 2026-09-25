from sqlalchemy import select
from app.models import Source, Item, Chunk, Conversation, Message
from app.services import visible_item, replace_chunks
from app.security import encrypt, decrypt
from app import ai
from fastapi import HTTPException
import pytest


def test_setup_requires_token_and_is_one_time(client):
    body = {"password": "test-password-very-long"}
    assert client.post("/api/v1/auth/setup", json=body).status_code == 403
    assert (
        client.post(
            "/api/v1/auth/setup",
            json=body,
            headers={
                "X-Setup-Token": "test-setup-token",
                "Origin": "https://evil.example",
            },
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/auth/setup",
            json=body,
            headers={"X-Setup-Token": "test-setup-token"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/auth/setup",
            json=body,
            headers={"X-Setup-Token": "test-setup-token"},
        ).status_code
        == 409
    )


def test_auth_csrf_and_logout(logged):
    assert logged.get("/api/v1/sources").status_code == 200
    token = logged.headers.pop("X-CSRF-Token")
    assert (
        logged.post(
            "/api/v1/knowledge", json={"title": "x", "content": "y"}
        ).status_code
        == 403
    )
    logged.headers["X-CSRF-Token"] = token
    assert logged.post("/api/v1/auth/logout").status_code == 200
    assert logged.get("/api/v1/sources").status_code == 401


def test_secret_never_returned(logged):
    assert (
        logged.put(
            "/api/v1/settings/openai", json={"api_key": "sk-not-a-real-api-key"}
        ).status_code
        == 200
    )
    data = logged.get("/api/v1/settings").json()
    assert data["openai_configured"] is True
    assert "sk-not-a-real-api-key" not in str(data)


def test_encryption_roundtrip():
    ciphertext = encrypt("secret-value")
    assert "secret-value" not in ciphertext
    assert decrypt(ciphertext) == "secret-value"


def test_ai_search_excludes_nonconsenting_disabled_and_revoked(db, mail):
    source, item = mail
    for name, enabled, consent, status, available in [
        ("private", True, False, "ok", True),
        ("disabled", False, True, "ok", True),
        ("revoked", True, True, "forbidden", True),
        ("deleted", True, True, "ok", False),
    ]:
        s = Source(
            kind="mail", name=name, enabled=enabled, ai_enabled=consent, status=status
        )
        db.add(s)
        db.flush()
        i = Item(
            source_id=s.id,
            external_id=name,
            kind="mail",
            title=name,
            body="Projekt Alpha geheim",
            available=available,
        )
        db.add(i)
        db.flush()
        replace_chunks(db, i)
    db.commit()
    assert {r["item_id"] for r in ai.search(db, "Projekt", ai=True)} == {item.id}
    assert len(ai.search(db, "Projekt", ai=False)) == 2


def test_context_rejects_revoked_link_before_any_provider_call(db, mail, monkeypatch):
    source, item = mail
    conversation = Conversation(title="Test", item_ids=[item.id])
    db.add(conversation)
    db.flush()
    source.ai_enabled = False
    db.commit()
    monkeypatch.setattr(
        ai, "OpenAIProvider", lambda *args: pytest.fail("Provider must never be called")
    )
    with pytest.raises(HTTPException):
        ai.chat(db, conversation.id)


def test_embedding_rechecks_consent(db, mail, monkeypatch):
    source, item = mail
    source.ai_enabled = False
    db.commit()
    monkeypatch.setattr(
        ai, "OpenAIProvider", lambda *args: pytest.fail("No outbound request allowed")
    )
    with pytest.raises(HTTPException):
        ai.embed_item(db, item.id)


def test_cookie_has_protection(logged):
    response = logged.post(
        "/api/v1/auth/login", json={"password": "test-password-very-long"}
    )
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_local_search_does_not_call_openai(logged, mail, monkeypatch):
    monkeypatch.setattr(
        ai, "OpenAIProvider", lambda *args: pytest.fail("Search must stay local")
    )
    assert logged.get("/api/v1/search?q=Projekt").status_code == 200


def test_hybrid_search_with_vector(db, mail):
    source, item = mail
    chunk = db.scalar(select(Chunk).where(Chunk.item_id == item.id))
    chunk.embedding = [1.0, 0.0, 0.0]
    chunk.embedding_model = "openai:test"
    chunk.embedding_dimension = 3
    db.commit()
    results = ai.search(
        db, "Freigabe", ai=True, vector=[1.0, 0.0, 0.0], model="openai:test"
    )
    assert results[0]["item_id"] == item.id
    source.ai_enabled = False
    db.commit()
    assert (
        ai.search(db, "Freigabe", ai=True, vector=[1.0, 0.0, 0.0], model="openai:test")
        == []
    )


def test_daily_background_limit(db, mail):
    from app.services import put_setting, DEFAULT_AGENT

    put_setting(db, "agent", DEFAULT_AGENT | {"daily_limit": 1})
    db.commit()
    ai.reserve_call(db, "embed", True)
    with pytest.raises(ValueError, match="Tageslimit"):
        ai.reserve_call(db, "analyze", True)
    ai.reserve_call(db, "chat", False)


def test_old_assistant_answer_from_revoked_source_is_not_sent(db, mail, monkeypatch):
    from app.services import put_setting

    source, item = mail
    conversation = Conversation(title="Independent chat", item_ids=[])
    db.add(conversation)
    db.flush()
    db.add(
        Message(
            conversation_id=conversation.id,
            role="assistant",
            content="FORBIDDEN OLD ANSWER",
            citations=[{"item_id": item.id}],
        )
    )
    db.add(Message(conversation_id=conversation.id, role="user", content="Hello"))
    source.ai_enabled = False
    put_setting(db, "openai", {"key": "placeholder"})
    db.commit()
    monkeypatch.setattr(ai, "context_for", lambda *args, **kwargs: [])
    captured = []

    class FakeProvider:
        def __init__(self, *args):
            pass

        def generate(self, instructions, messages, on_delta=None, on_proposals=None):
            captured.extend(messages)
            return "Safe answer", {"input_tokens": 1, "output_tokens": 2}

    monkeypatch.setattr(ai, "OpenAIProvider", FakeProvider)
    ai.chat(db, conversation.id)
    assert "FORBIDDEN OLD ANSWER" not in str(captured)
