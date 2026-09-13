"""
Run before gunicorn on Render.
- If the DB is empty, run `flask db upgrade` to create all tables.
- If the DB has tables but no alembic_version, stamp head (mark as migrated).
- Otherwise, upgrade to apply any new migrations.
"""
import os
import sys
from sqlalchemy import create_engine, inspect, text


def main():
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("No DATABASE_URL — skipping migrations.")
        return 0

    # Render uses postgres://, SQLAlchemy wants postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(url)
    insp = inspect(engine)

    tables = insp.get_table_names()
    has_alembic = "alembic_version" in tables

    # Fresh DB — let Alembic create everything
    if not tables or (len(tables) == 1 and has_alembic and not _has_real_data(engine)):
        print("DB looks empty — running 'flask db upgrade'")
        os.system("flask db upgrade")
        return 0

    # Existing DB without alembic tracking — stamp it
    if not has_alembic:
        print("DB has tables but no alembic_version — stamping head")
        os.system("flask db stamp head")
        return 0

    # Normal case — apply any new migrations
    print("Running 'flask db upgrade'")
    os.system("flask db upgrade")
    return 0


def _has_real_data(engine):
    """Check if the DB has actual user data beyond just alembic_version."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM users"))
            count = result.scalar()
            return count > 0
    except Exception:
        return False


if __name__ == "__main__":
    sys.exit(main())
