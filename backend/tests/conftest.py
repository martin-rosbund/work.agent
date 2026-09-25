import os
import tempfile
from pathlib import Path
import pytest
from cryptography.fernet import Fernet

TEST_ROOT = Path(tempfile.mkdtemp(prefix="workagent-tests-"))
test_url = os.getenv("TEST_DATABASE_URL", "sqlite:///" + str(TEST_ROOT / "tests.db"))
if not test_url.startswith("sqlite:") and not test_url.endswith("/workagent_test"):
    raise RuntimeError("Tests require a dedicated workagent_test database.")
os.environ["DATABASE_URL"] = test_url
os.environ["DATA_DIR"] = str(TEST_ROOT / "data")
os.environ["MASTER_KEY_FILE"] = str(TEST_ROOT / "master")
os.environ["SETUP_TOKEN_FILE"] = str(TEST_ROOT / "setup")
(TEST_ROOT / "master").write_bytes(Fernet.generate_key())
(TEST_ROOT / "setup").write_text("test-setup-token")
from app.db import Base, engine, SessionLocal
from app import models
from app.main import app, attempts
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def database():
    if engine.dialect.name == "postgresql":
        from sqlalchemy import text

        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    attempts.clear()
    yield


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client():
    with TestClient(app, base_url="http://localhost:8080") as instance:
        yield instance


@pytest.fixture
def logged(client):
    response = client.post(
        "/api/v1/auth/setup",
        json={"password": "test-password-very-long", "demo": False},
        headers={
            "X-Setup-Token": "test-setup-token",
            "Origin": "http://localhost:8080",
        },
    )
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf"]
    client.headers["Origin"] = "http://localhost:8080"
    return client


@pytest.fixture
def mail(db):
    from app.models import Source, Item
    from app.services import replace_chunks, put_setting, DEFAULT_AGENT

    source = Source(
        kind="mail",
        name="My inbox",
        config={"folder_id": "inbox"},
        status="ok",
        enabled=True,
        ai_enabled=True,
        writable=True,
    )
    db.add(source)
    db.flush()
    item = Item(
        source_id=source.id,
        external_id="msg-123",
        kind="mail",
        title="Projekt Alpha",
        body="Projekt Alpha braucht eine Freigabe.",
        sender="Lena",
        thread_key="thread-1",
        meta={"email": "lena@example.com"},
    )
    db.add(item)
    db.flush()
    replace_chunks(db, item)
    put_setting(db, "agent", DEFAULT_AGENT)
    db.commit()
    return source, item
