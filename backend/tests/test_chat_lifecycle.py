from app.models import Message, Proposal, Job


def create(logged):
    response = logged.post("/api/v1/conversations", json={"title": "Testchat"})
    assert response.status_code == 200
    return response.json()["id"]


def test_delete_empty_chat(logged):
    identity = create(logged)
    assert logged.delete(f"/api/v1/conversations/{identity}").status_code == 200
    assert logged.get(f"/api/v1/conversations/{identity}").status_code == 404


def test_archive_restore_preserves_content(logged, db):
    identity = create(logged)
    db.add(Message(conversation_id=identity, role="assistant", content="Antwort"))
    db.commit()
    assert logged.delete(f"/api/v1/conversations/{identity}").status_code == 409
    assert logged.patch(f"/api/v1/conversations/{identity}/archive", json={"archived": True}).status_code == 200
    assert logged.get("/api/v1/conversations").json() == []
    assert logged.get("/api/v1/conversations?archived=true").json()[0]["id"] == identity
    detail = logged.get(f"/api/v1/conversations/{identity}").json()
    assert detail["messages"][0]["content"] == "Antwort"
    assert logged.post(f"/api/v1/conversations/{identity}/messages", json={"content": "Weiter"}).status_code == 409
    assert logged.patch(f"/api/v1/conversations/{identity}/archive", json={"archived": False}).status_code == 200
    assert logged.get("/api/v1/conversations").json()[0]["id"] == identity


def test_proposals_and_pending_jobs_prevent_deletion(logged, db):
    identity = create(logged)
    db.add(Proposal(conversation_id=identity, kind="create_task", payload={}))
    db.commit()
    assert logged.delete(f"/api/v1/conversations/{identity}").status_code == 409
    second = create(logged)
    db.add(Job(kind="chat", payload={"conversation_id": second}, dedupe_key=f"chat:{second}"))
    db.commit()
    assert logged.delete(f"/api/v1/conversations/{second}").status_code == 409


def test_reopen_linked_archived_chat(logged, mail):
    _, item = mail
    body = {"item_ids": [item.id]}
    identity = logged.post("/api/v1/conversations", json=body).json()["id"]
    logged.patch(f"/api/v1/conversations/{identity}/archive", json={"archived": True})
    reopened = logged.post("/api/v1/conversations", json=body).json()
    assert reopened["id"] == identity
    assert reopened["archived"] is False


def test_archive_migration_preserves_existing_chats(tmp_path):
    import os
    import subprocess
    from sqlalchemy import create_engine, text

    url = "sqlite:///" + str(tmp_path / "migration.db")
    env = os.environ | {"DATABASE_URL": url}
    subprocess.run(["alembic", "upgrade", "0002"], env=env, check=True, capture_output=True)
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO conversations (id, title, item_ids, created_at) VALUES ('existing', 'Behalten', '[]', CURRENT_TIMESTAMP)"))
    subprocess.run(["alembic", "upgrade", "head"], env=env, check=True, capture_output=True)
    with engine.connect() as connection:
        row = connection.execute(text("SELECT title, archived FROM conversations WHERE id='existing'")).one()
        assert row == ("Behalten", 0)
    engine.dispose()
