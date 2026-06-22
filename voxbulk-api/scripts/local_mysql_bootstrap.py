"""Create local MySQL user/database from DATABASE_URL in .env (non-destructive by default).

By default this does NOT drop your database — it only creates missing user/db and runs migrations.
Use --fresh to drop and recreate the database (wipes all local data).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

import pymysql
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

API_ROOT = Path(__file__).resolve().parents[1]


def load_env() -> None:
    env_path = API_ROOT / ".env"
    if not env_path.is_file() or env_path.stat().st_size == 0:
        print(f"ERROR: Missing or empty {env_path}")
        sys.exit(1)
    load_dotenv(env_path, override=True)


def parse_mysql_url(url: str) -> tuple[str, str, str, str, int]:
    parsed = urlparse(url)
    if parsed.scheme not in {"mysql", "mysql+pymysql"}:
        print(f"ERROR: DATABASE_URL must be mysql+pymysql://... (got {parsed.scheme})")
        sys.exit(1)
    user = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    host = parsed.hostname or "127.0.0.1"
    port = int(parsed.port or 3306)
    db = (parsed.path or "").lstrip("/")
    if not user or not db:
        print("ERROR: DATABASE_URL must include username and database name")
        sys.exit(1)
    return user, password, db, host, port


def bootstrap_mysql(*, root_password: str, app_user: str, app_pass: str, app_db: str, host: str, fresh: bool) -> None:
    print(f"Ensuring MySQL database `{app_db}` and user `{app_user}`@{host}...")
    conn = pymysql.connect(
        host=host,
        user="root",
        password=root_password,
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            if fresh:
                print("WARNING: --fresh will DROP the database and erase all local data.")
                cur.execute(f"DROP DATABASE IF EXISTS `{app_db}`")
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{app_db}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            for grant_host in ("localhost", "127.0.0.1", "%"):
                cur.execute(
                    f"CREATE USER IF NOT EXISTS '{app_user}'@'{grant_host}' IDENTIFIED BY %s",
                    (app_pass,),
                )
                cur.execute(
                    f"GRANT ALL PRIVILEGES ON `{app_db}`.* TO '{app_user}'@'{grant_host}'"
                )
            cur.execute("FLUSH PRIVILEGES")
            cur.execute(f"USE `{app_db}`")
            cur.execute("SHOW TABLES LIKE 'alembic_version'")
            if cur.fetchone() is None:
                cur.execute(
                    "CREATE TABLE alembic_version ("
                    "version_num VARCHAR(255) NOT NULL, "
                    "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)"
                    ")"
                )
    finally:
        conn.close()
    print("MySQL bootstrap OK.")


def test_app_connection(url: str, app_user: str, app_db: str, host: str) -> None:
    print(f"Testing app connection: {app_user}@{host}/{app_db}")
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("Connection OK.")


def run_migrations() -> None:
    print("Running alembic upgrade head...")
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=API_ROOT,
        check=True,
    )
    print("Migrations OK.")


def seed_demo_accounts() -> None:
    print("Ensuring local demo accounts (passwords from LOCAL_* in .env)...")
    subprocess.run(
        [sys.executable, "-c", "from dotenv import load_dotenv; load_dotenv('.env'); from main import _ensure_local_demo_admin, _ensure_local_demo_user; _ensure_local_demo_admin(); _ensure_local_demo_user(); print('Demo accounts OK.')"],
        cwd=API_ROOT,
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap local MySQL for VoxBulk API")
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Drop and recreate the database (destructive — wipes local data)",
    )
    args = parser.parse_args()

    os.chdir(API_ROOT)
    load_env()

    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        print("ERROR: DATABASE_URL not set in .env")
        sys.exit(1)

    app_user, app_pass, app_db, host, _port = parse_mysql_url(url)

    root_password = os.environ.get("MYSQL_ROOT_PASSWORD", "").strip()
    if not root_password:
        print("ERROR: Set MYSQL_ROOT_PASSWORD for this run (MySQL root password).")
        sys.exit(1)

    try:
        bootstrap_mysql(
            root_password=root_password,
            app_user=app_user,
            app_pass=app_pass,
            app_db=app_db,
            host=host,
            fresh=bool(args.fresh),
        )
    except pymysql.err.OperationalError as exc:
        print(f"ERROR: Could not connect as MySQL root: {exc}")
        print("Check MySQL is running and MYSQL_ROOT_PASSWORD is correct.")
        sys.exit(1)

    test_app_connection(url, app_user, app_db, host)
    run_migrations()
    seed_demo_accounts()
    print("\nDone.")
    print("Dashboard: user@user.com / testtest1 (or LOCAL_DASHBOARD_* from .env)")
    print("Admin:     zaghlolno@gmail.com / testtest1 (or LOCAL_ADMIN_* from .env)")


if __name__ == "__main__":
    main()
