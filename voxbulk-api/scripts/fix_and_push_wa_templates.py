#!/usr/bin/env python3
"""Fix and push buttoned WA Survey templates per industry (buttonless excluded).

Processes each template row by database id (safe when the same Meta name exists on
multiple survey-type rows).

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
from app.services.survey_wa_utility_rewrite_service import (
    _prepare_approved_template_for_utility_push,
    apply_utility_rewrite_to_row,
)
from app.services.survey_whatsapp_template_service import (
    SurveyWhatsappTemplateError,
    SurveyWhatsappTemplateService,
    _resolve_push_language,
    _try_link_existing_remote_template,
)
from app.services.wa_template_meta_sync import format_template_push_error

from scripts.wa_not_pushed_lib import (
    industry_slug_for_row,
    is_not_on_meta,
    is_on_meta_live,
    is_stale_approved_local,
    iter_survey_keeper_rows,
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


def _push_row(db, row, *, force: bool = True) -> dict:
    SurveyWhatsappTemplateService.push_to_telnyx(db, row, force_approved_update=force)
    return {"ok": True, "name": row.name}


def _link_row_from_meta(db, row) -> bool:
    lang_code, lang_error = _resolve_push_language(db, row)
    if lang_error:
        return False
    result = _try_link_existing_remote_template(db, row, language=lang_code)
    return result is not None


def _push_with_rename_retry(db, row, *, force: bool = True) -> dict:
    name = str(row.name)
    try:
        _push_row(db, row, force=force)
        return {"ok": True, "name": row.name}
    except SurveyWhatsappTemplateError as exc:
        payload = getattr(exc, "payload", None) or {}
        if payload.get("requires_rename") and payload.get("suggested_template_name"):
            new_name = str(payload["suggested_template_name"]).strip()
            print(f"  Rename {name} → {new_name} (Meta deletion lock) …", flush=True)
            row = SurveyWhatsappTemplateService.rename_for_meta_sync(db, row, new_name)
            _push_row(db, row, force=force)
            return {"ok": True, "name": row.name, "renamed_from": name}
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix + push buttoned survey templates for one industry")
    parser.add_argument("--industry-slug", required=True, help="Industry slug, e.g. employee_survey")
    parser.add_argument("--push-delay", type=float, default=2.0, help="Seconds between pushes")
    parser.add_argument("--repair-first", action="store_true", help="Repair invalid draft BODY examples")
    parser.add_argument("--utility-rewrite", action="store_true", help="Utility-rewrite bodies before push")
    parser.add_argument(
        "--link-only",
        action="store_true",
        help="Only link local rows to existing Meta templates (no rewrite/push)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-feedback", action="store_true", help="Not implemented — survey only")
    args = parser.parse_args()

    if args.include_feedback:
        print("--include-feedback is not supported; survey buttoned templates only.", file=sys.stderr)
        return 1

    industry_slug = args.industry_slug.strip()
    ok_count = 0
    fail_count = 0
    skip_count = 0
    linked_count = 0
    repaired = 0
    failures: list[dict] = []

    with get_sessionmaker()() as db:
        try:
            keepers = iter_survey_keeper_rows(db, industry_slug=industry_slug)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        buttoned, buttonless = split_buttoned_buttonless(keepers)
        if args.link_only:
            targets = [row for row in buttoned if is_stale_approved_local(row)]
        else:
            targets = [row for row in buttoned if is_not_on_meta(row)]

        print(f"Industry: {industry_slug}")
        print(f"Buttoned (in scope):   {len(buttoned)}")
        print(f"Buttonless (skipped):  {len(buttonless)}")
        print(f"Not on Meta (targets): {len(targets)}")
        if args.link_only:
            print("Mode: link-only (stale APPROVED + local id → link from Meta)")
        print()

        if args.dry_run:
            for row in targets:
                ind = industry_slug_for_row(db, row) or "?"
                live = "live" if is_on_meta_live(row) else "not-on-meta"
                print(f"  would process id={row.id} [{live}] {row.name} ({ind})")
            return 0

        total = len(targets)
        for index, row in enumerate(targets, start=1):
            db.refresh(row)
            name = str(row.name)
            print(f"[{index}/{total}] id={row.id} {name} …", flush=True)

            if args.repair_first and _repair_row(row):
                db.add(row)
                db.commit()
                db.refresh(row)
                repaired += 1

            try:
                if args.link_only:
                    if _link_row_from_meta(db, row):
                        db.refresh(row)
                        linked_count += 1
                        ok_count += 1
                        print(f"  LINKED {name} → {row.telnyx_record_id}")
                    else:
                        from app.services.survey_wa_template_fix_sync_service import (
                            sync_survey_template_from_sibling_meta_owner,
                        )

                        owner = sync_survey_template_from_sibling_meta_owner(db, row)
                        if owner is not None:
                            linked_count += 1
                            ok_count += 1
                            print(f"  SYNCED from sibling row id={owner.id}: {name}")
                        elif is_on_meta_live(row):
                            skip_count += 1
                            print(f"  SKIP already linked: {name}")
                        else:
                            fail_count += 1
                            failures.append({"id": row.id, "name": name, "error": "No matching Meta template to link", "phase": "link"})
                            print(f"  FAIL link {name}: no remote match", file=sys.stderr)
                elif args.utility_rewrite:
                    row, renamed_to = _prepare_approved_template_for_utility_push(db, row)
                    if renamed_to:
                        print(f"  Prepared clone rename → {renamed_to}", flush=True)
                    apply_utility_rewrite_to_row(db, row, use_llm=True, llm_provider="openai")
                    result = _push_with_rename_retry(db, row, force=True)
                    ok_count += 1
                    print(f"  OK {result.get('name')}")
                else:
                    result = _push_with_rename_retry(db, row, force=True)
                    ok_count += 1
                    print(f"  OK {result.get('name')}")
            except SurveyWhatsappTemplateError as exc:
                err = format_template_push_error(exc)
                payload = getattr(exc, "payload", None) or {}
                if payload.get("meta_error_kind") == "content_already_exists":
                    if _link_row_from_meta(db, row):
                        db.refresh(row)
                        linked_count += 1
                        ok_count += 1
                        print(f"  LINKED (already on Meta): {name}")
                    else:
                        from app.services.survey_wa_template_fix_sync_service import (
                            sync_survey_template_from_sibling_meta_owner,
                        )

                        owner = sync_survey_template_from_sibling_meta_owner(db, row)
                        if owner is not None:
                            linked_count += 1
                            ok_count += 1
                            print(f"  SYNCED from sibling row id={owner.id}: {name}")
                        else:
                            skip_count += 1
                            print(f"  SKIP already on Meta: {name}")
                else:
                    fail_count += 1
                    failures.append({"id": row.id, "name": name, "error": err, "phase": "push"})
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
        "linked_from_meta": linked_count,
        "skipped_already_on_meta": skip_count,
        "failed": fail_count,
        "failures": failures,
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slug_safe = industry_slug.replace("/", "_")
    report_path = REPORT_DIR / f"fix-push-{slug_safe}-{stamp}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nDone — OK: {ok_count}, linked: {linked_count}, skipped: {skip_count}, failed: {fail_count}, repaired: {repaired}")
    print(f"Report: {report_path}")
    return 1 if fail_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
