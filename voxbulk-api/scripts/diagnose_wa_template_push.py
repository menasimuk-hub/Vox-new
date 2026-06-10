#!/usr/bin/env python3
"""Show what would be sent to Telnyx/Meta for a WA Survey template (no API call).

Usage:
  cd voxbulk-api
  .venv/bin/python scripts/diagnose_wa_template_push.py --template-name voxbulk_survey_post_visit_satisfaction_abc_09efa5
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
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_whatsapp_template_service import (
    SurveyWhatsappTemplateError,
    _effective_components,
    _loads,
    prepare_components_for_telnyx_push,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose WA template Telnyx push payload")
    parser.add_argument("--template-name", required=True, help="Meta template name")
    args = parser.parse_args()

    with get_sessionmaker()() as db:
        row = db.execute(
            select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.name == args.template_name.strip())
        ).scalar_one_or_none()
        if row is None:
            print(f"Template not found: {args.template_name}", file=sys.stderr)
            return 1

        raw = _effective_components(row)
        print(f"Template: {row.name}")
        print(f"Language: {row.language}")
        print(f"Category: {row.category}")
        print(f"Status: {row.status}")
        print("\nDraft components (stored):")
        print(json.dumps(_loads(row.draft_components_json) or raw, indent=2, ensure_ascii=False))

        try:
            prepared = prepare_components_for_telnyx_push(raw, row=row)
        except SurveyWhatsappTemplateError as exc:
            print(f"\nPREPARE ERROR: {exc}", file=sys.stderr)
            return 1

        body = next(c for c in prepared if str(c.get("type") or "").upper() == "BODY")
        print("\nPrepared BODY (sent to Telnyx):")
        print(json.dumps(body, indent=2, ensure_ascii=False))
        if "example" not in body:
            print("\nERROR: prepared BODY has no example key", file=sys.stderr)
            return 1
        print("\nOK — BODY includes Meta example.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
