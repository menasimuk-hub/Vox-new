# AGENTS.md — VoxBulk

Guidance for AI agents working in this repo. Read this first, then only open the files you actually need.

VoxBulk is a multi-tenant B2B SaaS platform for businesses across industries, providing WhatsApp surveys, voice agents, appointment scheduling, billing, and CRM integrations. Deep system reference lives in `ARCHITECTURE_DIAGRAM.md` — read it when you need data flows, model lists, or integration details.

## Repository map

This is a monorepo with one backend and three frontends.

| Path | App | Stack | Dev port |
|------|-----|-------|----------|
| `voxbulk-api/` | FastAPI backend (the core) | Python 3.11+, FastAPI, SQLAlchemy, Alembic, Celery, Redis | 8000 |
| `voxbulk.com/frontend/` | Public marketing site | React 19, TanStack Start/Router/Query, Vite, Tailwind | 5173 |
| `dashboard.voxbulk.com/dashboard-web/` | Customer dashboard | React 19, TanStack Start/Router/Query, Vite, Tailwind, Radix | 5175 |
| `admin.voxbulk.com/adim-web/` | Internal admin panel | React 18, React Router, Vite | 5174 |
| `scripts/` | Repo-level dev/build helper scripts (`.mjs`) | Node | — |
| `docs/` | Project documentation | — | — |

Notes:
- The admin frontend folder is literally spelled `adim-web` (typo is intentional/legacy — do not "fix" it).
- `dashboard.voxbulk.com/dashboard-web/Interview-reports/` is a separate sub-app; don't edit it unless the task is about interview reports.

## How to run / build / test

### Whole local stack (from repo root)
```bash
npm run dev          # API + public site + admin together (concurrently)
npm run dev:api      # API only
npm run dev:public   # public site only
npm run dev:admin    # admin only
```
The stack waits on `http://127.0.0.1:8000/health` before starting frontends.

### Backend (`voxbulk-api/`)
```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # PowerShell (Windows). macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
alembic upgrade head                 # apply migrations
pytest                               # run tests
celery -A app.workers.celery_app:celery_app worker -l INFO   # background worker (needs Redis)
```
Health checks: `/health`, `/health/db`, `/health/build`, `/health/pricing`.

### Frontends
```bash
# dashboard (most actively developed):
npm run dev      # vite dev
npm run build    # vite build
npm run lint     # eslint
npm run format   # prettier
npm run test     # vitest

# admin: npm run dev / npm run build (no lint/test configured)
```
`predev`/`prebuild` hooks auto-sync brand assets, build-info, and integration logos — let them run; don't hand-edit generated build-info or `public/brand/*` files.

## Backend conventions (most work happens here)

Structure under `voxbulk-api/app/`:
- `core/` — config (Pydantic settings), database session, security (JWT + Fernet encryption), logging
- `models/` — SQLAlchemy ORM (~80 models, one concern per file)
- `routers/` — FastAPI endpoints (~45 routers), registered in `main.py`
- `services/` — business logic (the bulk of the code; ~hundreds of `*_service.py` files)
- `schemas/` — Pydantic request/response models
- `workers/` — Celery tasks
- `constants/`, `utils/`, `data/` (seed data)

Rules of the road:
- **Keep logic in services, not routers.** Routers should validate, call a service, and return a schema. Follow the naming pattern of existing files (e.g. `survey_results_service.py`, `billing_lifecycle_service.py`).
- **Multi-tenancy is enforced via JWT claims** (user + organisation), applied through FastAPI dependencies — NOT via a tenant header. Never bypass org scoping when reading/writing tenant data.
- **Schema changes require an Alembic migration.** After editing a model, create/adjust a migration in `alembic/` and run `alembic upgrade head`. Never edit the DB by hand.
- **Secrets are Fernet-encrypted** (`core/security.py`, `ENCRYPTION_KEY`). Don't log or expose decrypted integration credentials.
- **Webhooks** verify HMAC signatures — preserve signature checks when touching webhook handlers (e.g. Telnyx).
- **WA template sync:** local DB is source of truth for survey/feedback names and bodies — pull from Meta is **status only**; push is **DB → Meta**. See `docs/wa-template-sync-contract.md` and `.cursor/rules/wa-template-db-source-of-truth.mdc`.
- **Timezone:** UK-local logic uses `zoneinfo` `Europe/London`. On Windows install the `tzdata` package if it's missing.
- **Password hashing** is deliberately `pbkdf2_sha256` (Passlib) for Windows stability — don't switch to bcrypt/argon2 without being asked.

## Frontend conventions

- Dashboard & public site use **TanStack Router file-based routing** under `src/routes/` — add a route file, don't hand-wire a router.
- Data fetching goes through **TanStack Query**; reuse existing API client helpers in `src/lib/` rather than calling `fetch` ad hoc.
- UI uses **Radix primitives + Tailwind**; reuse existing components in `src/components/` before adding new ones.
- Admin panel is the older **React 18 + react-router-dom** app — match its existing patterns, don't import dashboard-only deps.

## Organisation roles (RBAC)

Source of truth: `voxbulk-api/app/services/org_rbac.py` and `dashboard-web/src/lib/org-roles.ts`. Roles: `owner`, `manager`, `accountant`, `member` (legacy `receptionist` = `member`). See the `voxbulk-org-roles` rule and `ARCHITECTURE_DIAGRAM.md` for details.

## Git & deployment

- Single GitHub remote: `origin` → `https://github.com/menasimuk-hub/Vox-new.git`, branch `main`. Push/pull only there. Never reference the legacy `menasimuk-hub/Vox` repo.
- After commits: `git push origin main`.
- Production deploys from a Linux VPS via `./deploy-vps.sh` (or `./vox.sh update`) — never from Windows. See the `vps-deploy` rule for the full checklist and known git-pull conflict fixes.
- **After completing implementation work, commit and push to `origin main`** (see `.cursor/rules/always-commit-and-push.mdc`). Never commit `.env` or anything containing secrets. Skip commit only for read-only tasks or when the user said not to.

## Working norms for agents

- Prefer editing existing files over creating new ones; match the surrounding style.
- After non-trivial edits, check for linter errors (and run the relevant `pytest` / `vitest` when behaviour changed).
- Don't add narrating comments; only comment non-obvious intent.
- When a task spans backend + a frontend, change the API first (with its migration), then wire up the UI against the new contract.
- Don't touch generated/synced assets, the `Interview-reports` sub-app, or the `adim-web` spelling unless that's the task.
