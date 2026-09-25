"""Migration acceptance in disposable databases on the DEVELOPMENT database server."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

if os.environ.get("APP_ORIGIN") != "http://localhost:5173":
    raise RuntimeError(
        "Migration verification requires the isolated development environment."
    )
base = make_url(os.environ["DATABASE_URL"])


def migrate(name, revision):
    if not name.startswith("workagent_migration_"):
        raise ValueError("Not a migration fixture database.")
    environment = os.environ | {
        "DATABASE_URL": base.set(database=name).render_as_string(hide_password=False)
    }
    subprocess.run(
        ["alembic", "upgrade", revision], cwd="/app", env=environment, check=True
    )


def fingerprint(engine):
    with engine.connect() as conn:
        tables = (
            conn.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename NOT LIKE 'github_%' AND tablename <> 'alembic_version' ORDER BY tablename"
                )
            )
            .scalars()
            .all()
        )
        data = {}
        for table in tables:
            # Names come exclusively from PostgreSQL's catalog; quote identifiers.
            quoted = engine.dialect.identifier_preparer.quote(table)
            rows = (
                conn.execute(text(f"SELECT row_to_json(t) FROM {quoted} t"))
                .scalars()
                .all()
            )
            data[table] = sorted(
                json.dumps(row, sort_keys=True, default=str) for row in rows
            )
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest(), {
            k: len(v) for k, v in data.items()
        }


if len(sys.argv) > 1:
    name = sys.argv[1]
    engine = create_engine(base.set(database=name))
    before, counts = fingerprint(engine)
    migrate(name, "head")
    after, _ = fingerprint(engine)
    assert before == after, "Existing data changed during upgrade"
    print("PASS backup upgrade: original rows unchanged", counts)
else:
    name = "workagent_migration_fresh_" + uuid4().hex[:8]
    with create_engine(base, isolation_level="AUTOCOMMIT").connect() as conn:
        conn.execute(text("CREATE DATABASE " + name))
    migrate(name, "head")
    engine = create_engine(base.set(database=name))
    with engine.connect() as conn:
        assert (
            conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            == "0002"
        )
        assert conn.execute(text("SELECT count(*) FROM github_issues")).scalar() == 0
        assert (
            conn.execute(
                text("SELECT extname FROM pg_extension WHERE extname='vector'")
            ).scalar()
            == "vector"
        )
    print("PASS fresh migration to 0002:", name)
