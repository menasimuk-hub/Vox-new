#!/usr/bin/env python3
"""Read-only soft check for a WA survey template row (run on VPS)."""
from __future__ import annotations

import sys

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_whatsapp_template_service import (
    _effective_components,
    _refresh_local_sync_status,
    resolve_template_sync_branch,
)


def main() -> None:
    name = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    if not name:
        print("Usage: python scripts/check_wa_template_row.py <template_name>")
        sys.exit(1)

    db = get_sessionmaker()()
    try:
        rows = list(
            db.execute(select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.name == name)).scalars().all()
        )
        print(f"name={name!r} rows={len(rows)}")
        for row in rows:
            draft = _effective_components(row) or []
            body = ""
            for comp in draft:
                if isinstance(comp, dict) and str(comp.get("type") or "").upper() == "BODY":
                    body = str(comp.get("text") or "")
            branch, branch_err = resolve_template_sync_branch(row, draft)
            print("---")
            print(f"id={row.id}")
            print(f"status={row.status}")
            print(f"category={row.category}")
            print(f"active_for_survey={row.active_for_survey}")
            print(f"local_sync_status={_refresh_local_sync_status(row)}")
            print(f"sync_branch={branch}")
            print(f"sync_branch_note={branch_err or ''}")
            print(f"parent_template_id={row.parent_template_id}")
            print(f"telnyx_record_id={row.telnyx_record_id}")
            print(f"last_push_error={row.last_push_error or ''}")
            print(f"body_preview={(row.body_preview or '')[:160]}")
            print(f"draft_body={body[:160]}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
