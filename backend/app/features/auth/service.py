import secrets
import time

from fastapi import HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError

from app import demo
from app.config import (
    SETUP_TOKEN_FILE,
)
from app.core.config import SESSION_COOKIE
from app.models import (
    LoginSession,
    Source,
    User,
    now,
)
from app.security import (
    check_origin,
    new_session,
    password_hasher,
    token_hash,
    verify_password,
)
from app.services import (
    DEFAULT_AGENT,
    put_setting,
)

from .schemas import Login

PREFIX = "/api/v1"
attempts = {}


def auth_status(request: Request, db=None):
    user = db.get(User, 1)
    token = request.cookies.get(SESSION_COOKIE, "")
    session = db.get(LoginSession, token_hash(token)) if token else None
    return {
        "initialized": bool(user),
        "authenticated": bool(session and session.expires > now()),
        "csrf": session.csrf if session and session.expires > now() else None,
        "demo": bool(user and user.demo),
    }


def rate_limit(request):
    key = request.client.host if request.client else "local"
    recent = [t for t in attempts.get(key, []) if time.monotonic() - t < 60]
    if len(recent) >= 10:
        raise HTTPException(429, "Zu viele Anmeldeversuche. Bitte eine Minute warten.")
    attempts[key] = recent + [time.monotonic()]


def setup(body: Login, request: Request, response: Response, db=None):
    check_origin(request)
    rate_limit(request)
    if db.get(User, 1):
        raise HTTPException(409, "Anwendung wurde bereits eingerichtet.")
    if not SETUP_TOKEN_FILE.exists() or not secrets.compare_digest(
        request.headers.get("x-setup-token", ""), SETUP_TOKEN_FILE.read_text().strip()
    ):
        raise HTTPException(
            403, "Einrichtungscode fehlt. Bitte über scripts/start.ps1 öffnen."
        )
    db.add(
        User(id=1, password_hash=password_hasher.hash(body.password), demo=body.demo)
    )
    put_setting(db, "agent", DEFAULT_AGENT)
    for kind, name in [("uploads", "Meine Dokumente"), ("knowledge", "Mein Wissen")]:
        db.add(Source(kind=kind, name=name, status="ok", ai_enabled=False))
    db.flush()
    if body.demo:
        demo.seed(db)
    session = new_session(db, response)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Einrichtung wurde bereits abgeschlossen.")
    return {"csrf": session.csrf}


def login(body: Login, request: Request, response: Response, db=None):
    check_origin(request)
    rate_limit(request)
    user = db.get(User, 1)
    if not user or not verify_password(user.password_hash, body.password):
        raise HTTPException(401, "Passwort stimmt nicht.")
    session = new_session(db, response)
    db.commit()
    return {"csrf": session.csrf}


def logout(response: Response, session=None, db=None):
    db.delete(db.get(LoginSession, session.id))
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}
