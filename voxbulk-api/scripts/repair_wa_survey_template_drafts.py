#!/usr/bin/env python3
"""Repair WA Survey template drafts stored with invalid Meta BODY examples ([[]] or missing).

Drafts intentionally omit static BODY examples (Meta only needs them at push time).
This script normalizes broken rows saved before that fix.

Usage (local):
  cd voxbulk-api
  .venv/bin/python scripts/repair_wa_survey_template_drafts.py --dry-run
  .venv/bin/python scripts/repair_wa_survey_template_drafts.py

VPS:
  cd /www/voxbulk/voxbulk-api && bash scripts/repair_wa_survey_template_drafts.sh
  cd /www/voxbulk/voxbulk-api && bash scripts/repair_wa_survey_template_drafts.sh --industry-slug employee_survey
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.industry import Industry
from app.models.survey_type import SurveyType
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_whatsapp_template_service import (
    _dumps,
    _example_values_for_storage,
    _loads,
    _meta_example_is_valid,
    _normalize_draft_components,
    _refresh_local_sync_status,
)


def _body_example_invalid(components: list) -> bool:
    for comp in components:
        if not isinstance(comp, dict):
            continue
        if str(comp.get("type") or "").upper() != "BODY":
            continue
        example = comp.get("example")
        if example is None:
            return False
        return not _meta_example_is_valid(example, field="body_text")
    return False


def _iter_templates(db, *, industry_slug: str | None, template_name: str | None):
    stmt = select(TelnyxWhatsappTemplate).order_by(TelnyxWhatsappTemplate.name)
    if template_name:
        stmt = stmt.where(TelnyxWhatsappTemplate.name == template_name.strip())
    elif industry_slug:
        slug = industry_slug.strip().lower()
        industry = db.execute(select(Industry).where(Industry.slug == slug)).scalar_one_or_none()
        if industry is None:
            raise SystemExit(f"Industry not found for slug={slug!r}")
        type_ids = [
            row.id
            for row in db.execute(
                select(SurveyType.id).where(SurveyType.industry_id == industry.id)
            ).scalars()
        ]
        if not type_ids:
            return []
        stmt = stmt.where(TelnyxWhatsappTemplate.survey_type_id.in_(type_ids))
    return list(db.execute(stmt).scalars())


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair invalid WA Survey template draft components")
    parser.add_argument("--dry-run", action="store_true", help="Report only — no DB writes")
    parser.add_argument("--industry-slug", default="", help="Limit to one industry slug")
    parser.add_argument("--template-name", default="", help="Limit to one Meta template name")
    args = parser.parse_args()

    with get_sessionmaker()() as db:
        rows = _iter_templates(
            db,
            industry_slug=args.industry_slug.strip() or None,
            template_name=args.template_name.strip() or None,
        )
        scanned = 0
        repaired = 0
        invalid_before = 0

        for row in rows:
            draft = _loads(row.draft_components_json)
            if not isinstance(draft, list) or not draft:
                continue
            scanned += 1
            had_invalid = _body_example_invalid(draft)
            normalized = _normalize_draft_components(draft)
            changed = json.dumps(normalized, sort_keys=True) != json.dumps(draft, sort_keys=True)
            if had_invalid:
                invalid_before += 1
            if not changed and not had_invalid:
                continue
            repaired += 1
            label = row.display_name or row.name
            print(f"{'[dry-run] ' if args.dry_run else ''}repair {row.name} ({label})")
            if args.dry_run:
                continue
            row.draft_components_json = _dumps(normalized)
            row.example_values_json = _dumps(_example_values_for_storage(normalized))
            row.local_sync_status = _refresh_local_sync_status(row)
            db.add(row)

        if not args.dry_run and repaired:
            db.commit()

        print(
            f"\nDone — scanned {scanned} draft(s), "
            f"invalid BODY example before repair: {invalid_before}, "
            f"{'would repair' if args.dry_run else 'repaired'}: {repaired}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
