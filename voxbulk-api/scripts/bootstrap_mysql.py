#!/usr/bin/env python3
"""
Bootstrap an empty MySQL database from SQLAlchemy models, then stamp Alembic to head.

Use on production VPS when `alembic upgrade head` fails on MySQL strict mode issues.
Requires DATABASE_URL=mysql+pymysql://... in voxbulk-api/.env
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import Base, get_engine  # noqa: E402
import app.models  # noqa: F401,E402


def main() -> None:
    settings = get_settings()
    url = settings.database_url
    if not url.startswith("mysql"):
        print("ERROR: Set DATABASE_URL=mysql+pymysql://user:pass@127.0.0.1:3306/dbname in .env")
        sys.exit(1)

    safe = url.split("@")[-1] if "@" in url else url
    print(f"Bootstrapping MySQL schema on {safe} ...")

    engine = get_engine()
    Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS alembic_version (
                    version_num VARCHAR(255) NOT NULL PRIMARY KEY
                )
                """
            )
        )
        conn.execute(text("ALTER TABLE alembic_version MODIFY version_num VARCHAR(255) NOT NULL"))

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.stamp(cfg, "head")
    print("OK — all tables created and Alembic stamped to head.")


if __name__ == "__main__":
    main()
