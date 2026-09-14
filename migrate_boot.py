"""
Run before gunicorn on Render.
Always runs 'flask db upgrade'. If that fails because the DB has tables
but no alembic_version, it stamps head instead — but only as a fallback.
"""
import os
import sys
import subprocess
from sqlalchemy import create_engine, inspect


def main():
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("No DATABASE_URL — skipping migrations.")
        return 0

    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(url)
    insp = inspect(engine)
    tables = insp.get_table_names()
    has_alembic = "alembic_version" in tables

    # If the DB has tables but no alembic_version, we need to bootstrap.
    # Try 'upgrade' first — if it errors because tables exist, stamp head.
    if tables and not has_alembic:
        print("DB has tables but no alembic_version — attempting upgrade")
        rc = subprocess.call(["flask", "db", "upgrade"])
        if rc != 0:
            print("Upgrade failed (expected on pre-migration DB) — stamping head")
            subprocess.call(["flask", "db", "stamp", "head"])
            return 0
        return 0

    print("Running 'flask db upgrade'")
    return subprocess.call(["flask", "db", "upgrade"])


if __name__ == "__main__":
    sys.exit(main())
