"""Development-only seed. It never creates a user or bypasses authentication."""

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.demo import seed
from app.core.models import Source
from app.features.github.demo import seed as seed_github


def main():
    with SessionLocal() as db:
        seed_github(db)
        db.commit()


if __name__ == "__main__":
    main()
