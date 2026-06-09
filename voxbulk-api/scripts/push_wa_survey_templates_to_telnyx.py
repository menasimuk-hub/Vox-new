#!/usr/bin/env python3
"""Push WA Survey WhatsApp templates to Telnyx/Meta (CLI — no admin UI required).

Always injects Meta-required BODY examples at push time. Run repair first if drafts
were saved with invalid examples like {"body_text": [[]]}.

Usage (local):
  cd voxbulk-api
  .venv/bin/python scripts/push_wa_survey_templates_to_telnyx.py --template-name voxbulk_survey_post_visit_satisfaction_abc_09efa5
  .venv/bin/python scripts/push_wa_survey_templates_to_telnyx.py --industry-slug employee_survey
  .venv/bin/python scripts/push_wa_survey_templates_to_telnyx.py --survey-type-id UUID

VPS (recommended order):
  cd /www/voxbulk && git pull
  cd /www/voxbulk/voxbulk-api
  bash scripts/repair_wa_survey_template_drafts.sh --industry-slug employee_survey
  bash scripts/push_wa_survey_templates_to_telnyx.sh --industry-slug employee_survey
  cd /www/voxbulk && bash vox.sh restart
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.industry import Industry
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.industry_service import IndustryService
from app.services.survey_whatsapp_template_service import (
    SurveyWhatsappTemplateError,
    SurveyWhatsappTemplateService,
)


def _push_one(db, row: TelnyxWhatsappTemplate) -> tuple[bool, str]:
    try:
        result = SurveyWhatsappTemplateService.push_to_telnyx(db, row)
        msg = result.get("sync_message") or result.get("message") or "Synced"
        return True, str(msg)
    except SurveyWhatsappTemplateError as exc:
        return False, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Push WA Survey templates to Telnyx/Meta")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--template-name", help="Single Meta template name, e.g. voxbulk_survey_...")
    group.add_argument("--survey-type-id", help="Push all templates linked to one survey type")
    group.add_argument("--industry-slug", help="Push all templates for every survey type in an industry")
    group.add_argument("--industry-id", help="Push all templates for every survey type in an industry (UUID)")
    parser.add_argument(
        "--repair-first",
        action="store_true",
        help="Run repair_wa_survey_template_drafts.py on the same scope before pushing",
    )
    args = parser.parse_args()

    if args.repair_first:
        repair_args = [sys.executable, str(ROOT / "scripts/repair_wa_survey_template_drafts.py")]
        if args.template_name:
            repair_args.extend(["--template-name", args.template_name.strip()])
        elif args.industry_slug:
            repair_args.extend(["--industry-slug", args.industry_slug.strip()])
        elif args.industry_id:
            industry = None
            with get_sessionmaker()() as db:
                industry = IndustryService.get_industry(db, args.industry_id.strip())
            if industry is None:
                print(f"Industry not found: {args.industry_id}", file=sys.stderr)
                return 1
            repair_args.extend(["--industry-slug", industry.slug])
        import subprocess

        print("Repairing drafts first…")
        subprocess.check_call(repair_args)

    ok_count = 0
    fail_count = 0

    with get_sessionmaker()() as db:
        if args.template_name:
            name = args.template_name.strip()
            row = db.execute(
                select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.name == name)
            ).scalar_one_or_none()
            if row is None:
                print(f"Template not found: {name}", file=sys.stderr)
                return 1
            ok, msg = _push_one(db, row)
            if ok:
                ok_count += 1
                print(f"OK  {name}: {msg}")
            else:
                fail_count += 1
                print(f"FAIL {name}: {msg}", file=sys.stderr)
        elif args.survey_type_id:
            summary = SurveyWhatsappTemplateService.push_all_for_survey_type(db, args.survey_type_id.strip())
            ok_count = int(summary.get("pushed") or 0)
            fail_count = int(summary.get("error_count") or 0)
            print(summary.get("message") or summary)
            for err in summary.get("errors") or []:
                print(
                    f"  FAIL {err.get('template_name') or err.get('template_id')}: {err.get('error')}",
                    file=sys.stderr,
                )
        else:
            industry_id = args.industry_id.strip() if args.industry_id else ""
            if not industry_id:
                slug = args.industry_slug.strip().lower()
                industry = db.execute(select(Industry).where(Industry.slug == slug)).scalar_one_or_none()
                if industry is None:
                    print(f"Industry not found for slug={slug!r}", file=sys.stderr)
                    return 1
                industry_id = industry.id
            summary = SurveyWhatsappTemplateService.push_all_for_industry(db, industry_id)
            ok_count = int(summary.get("pushed") or 0)
            fail_count = int(summary.get("error_count") or 0)
            print(summary.get("message") or summary)
            for err in summary.get("errors") or []:
                print(
                    f"  FAIL {err.get('survey_type_name') or err.get('survey_type_id')} · "
                    f"{err.get('template_name') or err.get('template_id')}: {err.get('error')}",
                    file=sys.stderr,
                )

    print(f"\nDone — pushed OK: {ok_count}, failed: {fail_count}")
    return 1 if fail_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
