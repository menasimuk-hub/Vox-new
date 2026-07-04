#!/usr/bin/env python3
"""Push one WA Survey template to Meta with full error detail.

Usage:
  cd voxbulk-api && source .venv/bin/activate
  python3 scripts/push_wa_one_verbose.py voxbulk_survey_interview_process_rating_abc_3107e6
  python3 scripts/push_wa_one_verbose.py TEMPLATE_NAME --dry-run
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
    SurveyWhatsappTemplateService,
    _effective_components,
    prepare_components_for_telnyx_push,
    resolve_template_sync_branch,
    template_row_has_buttons,
)
from app.services.wa_template_meta_sync import format_template_push_error, parse_meta_error_from_provider_detail


def main() -> int:
    parser = argparse.ArgumentParser(description="Push one survey WA template with verbose Meta errors")
    parser.add_argument("template_name", help="Meta template name")
    parser.add_argument("--dry-run", action="store_true", help="Validate payload only")
    parser.add_argument(
        "--no-force-update",
        action="store_true",
        help="Do not force approved update (same as normal Sync)",
    )
    args = parser.parse_args()

    name = args.template_name.strip()
    with get_sessionmaker()() as db:
        row = db.scalar(select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.name == name))
        if row is None:
            print(f"NOT FOUND: {name}", file=sys.stderr)
            return 1

        raw = _effective_components(row)
        branch, branch_error = resolve_template_sync_branch(row, raw)

        print("=== TEMPLATE ===")
        print(f"name:             {row.name}")
        print(f"language:         {row.language}")
        print(f"category:         {row.category}")
        print(f"status:           {row.status}")
        print(f"telnyx_record_id: {row.telnyx_record_id}")
        print(f"has_buttons:      {template_row_has_buttons(row)}")
        print(f"sync_branch:      {branch}")
        if branch_error:
            print(f"branch_note:      {branch_error}")
        print(f"last_push_error:  {row.last_push_error or '(none)'}")
        print()

        if not template_row_has_buttons(row):
            print("SKIP: template has no buttons — not in Meta push scope.", file=sys.stderr)
            return 1

        try:
            prepared = prepare_components_for_telnyx_push(raw, row=row)
        except SurveyWhatsappTemplateError as exc:
            print("=== PREPARE FAILED ===")
            print(format_template_push_error(exc))
            payload = getattr(exc, "payload", None)
            if payload:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 1

        body = next((c for c in prepared if str(c.get("type") or "").upper() == "BODY"), None)
        buttons = next((c for c in prepared if str(c.get("type") or "").upper() == "BUTTONS"), None)
        print("=== BODY ===")
        print(json.dumps(body, indent=2, ensure_ascii=False))
        if buttons:
            print("\n=== BUTTONS ===")
            print(json.dumps(buttons, indent=2, ensure_ascii=False))
        print()

        if args.dry_run:
            print("DRY RUN — payload OK, Meta not called.")
            return 0

        force = not args.no_force_update
        print(f"=== PUSHING (force_approved_update={force}) ===")
        try:
            result = SurveyWhatsappTemplateService.push_to_telnyx(db, row, force_approved_update=force)
            print("OK")
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
            return 0
        except SurveyWhatsappTemplateError as exc:
            print("=== PUSH FAILED ===")
            print(format_template_push_error(exc))
            payload = getattr(exc, "payload", None) or {}
            print("\n=== PAYLOAD ===")
            print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
            provider = str(payload.get("provider_error") or "")
            if provider:
                meta = parse_meta_error_from_provider_detail(provider)
                print("\n=== PARSED META ERROR ===")
                print(json.dumps(meta, indent=2, ensure_ascii=False, default=str))
            db.refresh(row)
            print(f"\nlast_push_error (DB): {row.last_push_error}")
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
