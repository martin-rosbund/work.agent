import hashlib
import secrets
from datetime import timedelta
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, Request

from app.config import APP_ORIGIN, MASTER_KEY_FILE
from app.core.config import SESSION_COOKIE
from app.db import get_db
from app.models import LoginSession, now

password_hasher = PasswordHasher()


@lru_cache
def cipher():
    return Fernet(MASTER_KEY_FILE.read_bytes().strip())


def encrypt(value: str):
    return cipher().encrypt(value.encode()).decode()


def decrypt(value: str):
    return cipher().decrypt(value.encode()).decode()


def verify_password(hashed, password):
    try:
        return password_hasher.verify(hashed, password)
    except (VerifyMismatchError, VerificationError):
        return False


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def new_session(db, response):
    token = secrets.token_urlsafe(48)
    session = LoginSession(
        id=token_hash(token),
        csrf=secrets.token_urlsafe(32),
        expires=now() + timedelta(days=7),
    )
    db.add(session)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="strict",
        secure=APP_ORIGIN.startswith("https:"),
        max_age=604800,
        path="/",
    )
    return session


def check_origin(request):
    origin = request.headers.get("origin")
    if origin and origin != APP_ORIGIN:
        raise HTTPException(
            403, "Diese Anfrage stammt nicht aus der lokalen Anwendung."
        )


def authenticated(request: Request, db=Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE, "")
    session = db.get(LoginSession, token_hash(token)) if token else None
    if not session or session.expires < now():
        raise HTTPException(401, "Bitte anmelden.")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        check_origin(request)
        if not secrets.compare_digest(
            request.headers.get("x-csrf-token", ""), session.csrf
        ):
            raise HTTPException(
                403, "Sicherheitsprüfung fehlgeschlagen. Bitte neu anmelden."
            )
    return session
