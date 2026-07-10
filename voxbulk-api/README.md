# VOXBULK API (FastAPI)

Production-ready FastAPI backend foundation for VOXBULK (multi-tenant B2B SaaS for businesses across industries).

## Setup

### 1) Create a virtualenv (Python 3.11+)

```bash
python -m venv .venv
```

Activate:

- PowerShell:

```bash
.\.venv\Scripts\Activate.ps1
```

- macOS/Linux:

```bash
source .venv/bin/activate
```

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

### 3) Configure environment

Copy example env and adjust values:

```bash
copy .env.example .env
```

## Generate `ENCRYPTION_KEY`

Fernet key (URL-safe base64). Run:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Paste the output into `.env` as `ENCRYPTION_KEY`.

## Database & Alembic migrations

### Initialize database connection

Set `DATABASE_URL` in `.env`, e.g.

```text
mysql+pymysql://user:pass@127.0.0.1:3306/retover
```

### Run migrations

From `voxbulk-api/`:

```bash
alembic upgrade head
```

## Run the dev server

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```text
GET http://localhost:8000/health
```

## Run Celery worker

Ensure Redis is running and configured via `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND`, then:

```bash
celery -A app.workers.celery_app:celery_app worker -l INFO
```

## Run tests

```bash
pytest
```

## Notes

- **Multi-tenant enforcement**: tenant scoping is derived from JWT claims (user + organisation relationship) and enforced via dependencies. No tenant header is used as the primary boundary.
- **Timezone**: UK-local logic uses `zoneinfo` (`Europe/London`).
  - `zoneinfo` uses **system timezone data**. On some Windows setups, `Europe/London` may be unavailable; if so, install the `tzdata` Python package in the runtime environment.
- **Password hashing**: currently standardized on `pbkdf2_sha256` (Passlib). This is intentional to keep hashing deterministic in local Windows environments where bcrypt backends can be unstable. Revisit before production if you require bcrypt/argon2.
