---
name: alembic-migration
description: Create and apply Alembic database migrations for the VoxBulk FastAPI backend after changing SQLAlchemy models. Use when adding/altering a model, a column, an index, or any database schema change in voxbulk-api/.
---

# VoxBulk Alembic migrations

Any change to a SQLAlchemy model in `app/models/` requires a migration. Never modify the database by hand.

## Workflow

```
- [ ] 1. Edit the SQLAlchemy model in app/models/
- [ ] 2. Autogenerate a revision
- [ ] 3. Review the generated script in alembic/versions/
- [ ] 4. Apply with alembic upgrade head
- [ ] 5. Sanity-check via /health/db
```

Run all commands from `voxbulk-api/` with the venv active.

## 1–2. Generate
```bash
alembic revision --autogenerate -m "short description of change"
```

## 3. Review (important)
Open the new file in `alembic/versions/` and confirm:
- It only contains the intended `op.*` operations (no spurious drops/renames).
- It has a sensible `downgrade()`.
- Data-dependent changes (NOT NULL on a populated table, type narrowing) are handled safely — add a data backfill step or a default before enforcing constraints.

## 4. Apply
```bash
alembic upgrade head
```
Roll back one step if needed: `alembic downgrade -1`.

## 5. Verify
Hit `GET /health/db` (schema verification) and run `pytest` if behaviour changed.

## Notes
- `DATABASE_URL` comes from `voxbulk-api/.env` (MySQL in prod, SQLite locally). Autogenerate compares against the live DB, so make sure migrations are already at head before generating a new one.
- On production this runs as part of `./deploy-vps.sh`; don't run prod migrations from Windows.
