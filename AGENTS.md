# AGENTS.md

## Cursor Cloud specific instructions

VoxBulk is a multi-tenant B2B SaaS monorepo: a FastAPI backend plus three Vite/React frontends.

### Services (dev)

| Service | Dir | Dev command | Port |
|---------|-----|-------------|------|
| API (FastAPI) | `voxbulk-api` | `. .venv/bin/activate && uvicorn main:app --host 127.0.0.1 --port 8000` | 8000 |
| Public site | `voxbulk.com/frontend` | `npm run dev` | 5173 |
| Admin console | `admin.voxbulk.com/adim-web` | `npm run dev` | 5174 |
| Dashboard | `dashboard.voxbulk.com/dashboard-web` | `npm run dev` | 5175 |

The three frontends proxy `/auth`, `/admin`, `/billing`, etc. to the API on `:8000` (see each `vite.config.ts`). Standard build/lint/test scripts live in each `package.json` (`build`, `lint`, `test`); backend test command is in `voxbulk-api/README.md` (`pytest`).

### Database — use MySQL/MariaDB locally, NOT SQLite

Although `.env.example` defaults `DATABASE_URL` to SQLite, the Alembic migrations are MySQL-only (they use `ALTER COLUMN ... DROP DEFAULT`, which SQLite rejects). On SQLite the migration chain breaks midway and leaves an incomplete schema (e.g. `users` is missing `deletion_status`), so logins fail with "Database error". Local dev must use MySQL/MariaDB, matching production.

- The cloud VM runs MariaDB (installed during environment setup). Start it each session with: `sudo service mariadb start` (the update script does NOT start it).
- Local DB/user (created from `voxbulk-api/scripts/setup-local-mysql.sql`): db `sql_voxbulk`, user `sql_voxbulk` / `6xHrFN7FHr85McFn`.
- `voxbulk-api/.env` must set: `DATABASE_URL=mysql+pymysql://sql_voxbulk:6xHrFN7FHr85McFn@127.0.0.1:3306/sql_voxbulk`
- Schema bootstrap: do NOT rely on `alembic upgrade head` from scratch — `alembic_version.version_num` is too short for the long revision ids and revision ordering breaks. Instead run `python scripts/bootstrap_mysql.py` (create_all from models + stamp Alembic to head). This is the repo's sanctioned MySQL bootstrap. After that, the API's boot-time migration sees head and skips it.
- The API auto-creates/reset local sign-in accounts on boot when `ENV=development` (see `LOCAL_ADMIN_EMAIL` / `LOCAL_DASHBOARD_EMAIL` in `.env`). Default dashboard login: `user@user.com` / `testtest1`; admin: `zaghlolno@gmail.com` / `testtest1`. Dashboard login page is `http://localhost:5175/login`.

### Env files

Each frontend needs a `.env` with `VITE_API_BASE_URL=http://127.0.0.1:8000` (or leave unset to use the Vite proxy). Backend needs `voxbulk-api/.env` (copy from `.env.example`, then set the MySQL `DATABASE_URL` above). All `.env` files are gitignored.

### Optional services

Redis + Celery (worker/beat) are only needed for async jobs (WhatsApp voice-note transcription, billing webhooks, scheduled tasks) and are not required for auth/onboarding/dashboard flows. Third-party provider keys (Telnyx, VAPI, OpenAI, GoCardless, etc.) are optional and configured via Admin → Integrations.

### Tests

`pytest` (from `voxbulk-api/`) uses its own SQLite test DB (`conftest.py` sets `DATABASE_URL` to `sqlite:///./.pytest.db`), independent of the MySQL dev DB. ~1009 of ~1061 tests pass; the remaining failures are pre-existing (test-code bugs such as missing imports, and tests requiring external provider API keys) and are unrelated to environment setup. If you see "table users already exists" errors, delete the stale `voxbulk-api/.pytest.db*` files and re-run.
