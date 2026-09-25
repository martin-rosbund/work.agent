"""Idempotent additions for already configured demo installations."""

from app.core.database import SessionLocal
from app.core.models import User
from app.features.github.demo import seed

if __name__ == "__main__":
    with SessionLocal() as db:
        user = db.get(User, 1)
        if user and user.demo:
            seed(db)
            db.commit()
