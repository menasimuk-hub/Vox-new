---
name: add-api-endpoint
description: Add a new FastAPI endpoint to voxbulk-api following the router→service→schema→model pattern with tenant scoping. Use when adding or modifying a backend endpoint, route, or API in the VoxBulk FastAPI app (voxbulk-api/).
---

# Add a VoxBulk API endpoint

Follow the layered pattern: **schema → service → router → register → migrate → test**. Keep routers thin; put logic in a service.

## Checklist

```
- [ ] 1. Define Pydantic request/response schema in app/schemas/
- [ ] 2. Implement logic in a *_service.py (new or existing)
- [ ] 3. Add the route to a router in app/routers/ (thin handler)
- [ ] 4. Register the router in main.py (if new) via app.include_router(...)
- [ ] 5. If models changed: add an Alembic migration + alembic upgrade head
- [ ] 6. Add/adjust a test in tests/ and run pytest
```

## 1. Schema (`app/schemas/`)
Define `...In` (request) and `...Out` (response) Pydantic models. Reuse existing schema modules where the resource already exists.

## 2. Service (`app/services/<feature>_service.py`)
All business logic lives here. Accept the DB session and the current principal; **scope every query to the principal's organisation**. Follow naming of existing services (e.g. `survey_results_service.py`).

## 3. Router (`app/routers/<feature>.py`)
Thin handler — validate, call the service, return the schema:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import CurrentPrincipal, get_current_principal

router = APIRouter(prefix="/<feature>", tags=["<feature>"])

@router.get("", response_model=list[ThingOut])
def list_things(
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(get_current_principal),
):
    return ThingService(db).list_for_org(principal.organisation_id)
```

## 4. Register (only for a new router)
In `main.py`, import the router and add `app.include_router(<feature>_router)` alongside the others.

## 5. Migration (only if a model changed)
See the `alembic-migration` skill. Never edit the DB by hand.

## 6. Test
Add/extend a test under `voxbulk-api/tests/`, then run `pytest` from `voxbulk-api/`.

## Guardrails
- Never trust a tenant header — tenancy comes from the JWT principal.
- Don't log/return decrypted secrets (Fernet via `app/core/security.py`).
- Keep webhook HMAC signature verification intact.
