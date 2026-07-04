#!/usr/bin/env python3
"""Fix and push buttoned WA Survey templates per industry (buttonless excluded).

Usage:
  cd voxbulk-api && source .venv/bin/activate
  python3 scripts/fix_and_push_wa_templates.py --industry-slug employee_survey --dry-run
  python3 scripts/fix_and_push_wa_templates.py --industry-slug employee_survey --repair-first --utility-rewrite --push-delay 2
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import get_sessionmaker
from app.services.survey_wa_utility_rewrite_service import process_template_names
from app.services.survey_whatsapp_template_service import (
    SurveyWhatsappTemplateError,
    SurveyWhatsappTemplateService,
)
from app.services.wa_template_meta_sync import format_template_push_error

from scripts.wa_not_pushed_lib import (
    is_not_on_meta,
    iter_survey_keeper_rows,
    row_summary,
    split_buttoned_buttonless,
)

repair_mod = importlib.util.spec_from_file_location(
    "repair_wa_survey_template_drafts",
    ROOT / "scripts" / "repair_wa_survey_template_drafts.py",
)
if repair_mod is None or repair_mod.loader is None:
    raise SystemExit("Could not load repair_wa_survey_template_drafts.py")
repair = importlib.util.module_from_spec(repair_mod)
repair_mod.loader.exec_module(repair)

REPORT_DIR = ROOT / "seed-data" / "wa-survey" / "migration-reports"


def _repair_row(row) -> bool:
    draft = repair._loads(row.draft_components_json)
    if not isinstance(draft, list) or not draft:
        return False
    normalized = repair._normalize_draft_components(draft)
    changed = json.dumps(normalized, sort_keys=True) != json.dumps(draft, sort_keys=True)
    had_invalid = repair._body_example_invalid(draft)
    if not changed and not had_invalid:
        return False
    row.draft_components_json = repair._dumps(normalized)
    row.example_values_json = repair._dumps(repair._example_values_for_storage(normalized))
    row.local_sync_status = repair._refresh_local_sync_status(row)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix + push buttoned survey templates for one industry")
    parser.add_argument("--industry-slug", required=True, help="Industry slug, e.g. employee_survey")
    parser.add_argument("--push-delay", type=float, default=2.0, help="Seconds between pushes")
    parser.add_argument("--repair-first", action="store_true", help="Repair invalid draft BODY examples")
    parser.add_argument("--utility-rewrite", action="store_true", help="Utility-rewrite bodies before push")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-feedback", action="store_true", help="Not implemented — survey only")
    args = parser.parse_args()

    if args.include_feedback:
        print("--include-feedback is not supported; survey buttoned templates only.", file=sys.stderr)
        return 1

    industry_slug = args.industry_slug.strip()
    ok_count = 0
    fail_count = 0
    repaired = 0
    failures: list[dict] = []

    with get_sessionmaker()() as db:
        try:
            keepers = iter_survey_keeper_rows(db, industry_slug=industry_slug)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        buttoned, buttonless = split_buttoned_buttonless(keepers)
        targets = [row for row in buttoned if is_not_on_meta(row)]

        print(f"Industry: {industry_slug}")
        print(f"Buttoned (in scope):   {len(buttoned)}")
        print(f"Buttonless (skipped):  {len(buttonless)}")
        print(f"Not on Meta (targets): {len(targets)}")
        print()

        if args.dry_run:
            for row in targets:
                print(f"  would process: {row.name}")
            return 0

        if args.repair_first and not args.utility_rewrite:
            for row in targets:
                db.refresh(row)
                if _repair_row(row):
                    db.add(row)
                    repaired += 1
            if repaired:
                db.commit()

        if args.utility_rewrite:
            names = [str(row.name) for row in targets]
            rewrite_results = process_template_names(
                db,
                names,
                save=True,
                push=True,
                dry_run=False,
                skip_already_pushed=False,
                push_delay_seconds=max(0.0, float(args.push_delay or 0)),
            )
            for r in rewrite_results:
                if r.ok and r.pushed:
                    ok_count += 1
                    print(f"  OK {r.template_name}: {r.message}")
                elif r.ok:
                    ok_count += 1
                    print(f"  OK {r.template_name}: {r.message}")
                else:
                    fail_count += 1
                    failures.append({"name": r.template_name, "error": r.message, "phase": "utility_rewrite"})
                    print(f"  FAIL {r.template_name}: {r.message}", file=sys.stderr)
        else:
            for row in targets:
                db.refresh(row)
                if args.repair_first and _repair_row(row):
                    db.add(row)
                    db.commit()
                    db.refresh(row)
                    repaired += 1

                name = str(row.name)
                print(f"Pushing {name} …", flush=True)
                try:
                    SurveyWhatsappTemplateService.push_to_telnyx(db, row, force_approved_update=True)
                    ok_count += 1
                    print(f"  OK {name}")
                except SurveyWhatsappTemplateError as exc:
                    fail_count += 1
                    err = format_template_push_error(exc)
                    failures.append({"name": name, "error": err, "phase": "push"})
                    print(f"  FAIL {name}: {err}", file=sys.stderr)

                if args.push_delay > 0:
                    time.sleep(args.push_delay)

    report = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "industry_slug": industry_slug,
        "buttoned_total": len(buttoned),
        "buttonless_skipped": len(buttonless),
        "targets": len(targets),
        "repaired_drafts": repaired,
        "ok": ok_count,
        "failed": fail_count,
        "failures": failures,
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slug_safe = industry_slug.replace("/", "_")
    report_path = REPORT_DIR / f"fix-push-{slug_safe}-{stamp}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nDone — OK: {ok_count}, failed: {fail_count}, repaired: {repaired}")
    print(f"Report: {report_path}")
    return 1 if fail_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
