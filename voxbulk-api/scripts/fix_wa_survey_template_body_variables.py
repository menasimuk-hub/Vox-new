#!/usr/bin/env python3
"""Fix WA Survey template BODY variables/examples in the database.

Rule (simple):
  - BODY with no {{1}} placeholders → plain text only, no example, example_values cleared
  - BODY with {{1}}..{{n}} placeholders → valid Meta example values kept/rebuilt

Usage (VPS):
  cd /www/voxbulk/voxbulk-api

  # Preview all survey templates
  bash scripts/fix_wa_survey_template_body_variables.sh --dry-run

  # Fix every survey template in one industry
  bash scripts/fix_wa_survey_template_body_variables.sh --industry-slug property_lettings

  # Fix + push-test one template (recommended first)
  bash scripts/fix_wa_survey_template_body_variables.sh \\
    --template-name voxbulk_survey_viewing_experience_abc_54a96f --push

  # Fix industry then push all templates in that industry
  bash scripts/fix_wa_survey_template_body_variables.sh --industry-slug property_lettings --push
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
from app.services.survey_type_service import SurveyTypeService
from app.services.survey_whatsapp_template_service import (
    SurveyWhatsappTemplateError,
    SurveyWhatsappTemplateService,
    _dumps,
    _example_values_for_storage,
    _has_remote_telnyx_id,
    _is_local_row,
    _loads,
    _meta_var_ids_in_text,
    _refresh_local_sync_status,
    fix_survey_template_draft_body_variables,
)


def _iter_templates(
    db,
    *,
    industry_slug: str | None,
    survey_type_slug: str | None,
    survey_type_id: str | None,
    template_name: str | None,
    all_survey_templates: bool,
):
    stmt = (
        select(TelnyxWhatsappTemplate)
        .where(TelnyxWhatsappTemplate.survey_type_id.isnot(None))
        .order_by(TelnyxWhatsappTemplate.name)
    )
    if template_name:
        stmt = stmt.where(TelnyxWhatsappTemplate.name == template_name.strip())
    elif survey_type_id:
        stmt = stmt.where(TelnyxWhatsappTemplate.survey_type_id == survey_type_id.strip())
    elif survey_type_slug:
        survey_type = SurveyTypeService.resolve_unique_by_slug(db, survey_type_slug.strip().lower())
        if survey_type is None:
            raise SystemExit(f"Survey type not found for slug={survey_type_slug!r}")
        stmt = stmt.where(TelnyxWhatsappTemplate.survey_type_id == survey_type.id)
    elif industry_slug:
        slug = industry_slug.strip().lower()
        industry = db.execute(select(Industry).where(Industry.slug == slug)).scalar_one_or_none()
        if industry is None:
            raise SystemExit(f"Industry not found for slug={slug!r}")
        type_ids = list(
            db.scalars(select(SurveyType.id).where(SurveyType.industry_id == industry.id))
        )
        if not type_ids:
            return []
        stmt = stmt.where(TelnyxWhatsappTemplate.survey_type_id.in_(type_ids))
    elif not all_survey_templates:
        raise SystemExit(
            "Pass a scope: --template-name, --survey-type-slug, --survey-type-id, "
            "--industry-slug, or --all-survey-templates"
        )
    return list(db.scalars(stmt))


def _body_summary(components: list) -> str:
    for comp in components:
        if not isinstance(comp, dict):
            continue
        if str(comp.get("type") or "").upper() != "BODY":
            continue
        text = str(comp.get("text") or "")
        var_ids = _meta_var_ids_in_text(text)
        if var_ids:
            return f"variables {var_ids}"
        if comp.get("example") is not None:
            return "static + stale example (will clear)"
        return "static (no variables)"
    return "no BODY"


def _apply_fix(row: TelnyxWhatsappTemplate) -> tuple[bool, str, list | None, list[str] | None]:
    draft = _loads(row.draft_components_json)
    if not isinstance(draft, list) or not draft:
        remote = _loads(row.components_json)
        draft = remote if isinstance(remote, list) and remote else None
    if not isinstance(draft, list) or not draft:
        return False, "skip — no components", None, None

    before_summary = _body_summary(draft)
    fixed = fix_survey_template_draft_body_variables(draft, row=row)
    if not fixed:
        return False, "skip — empty after fix", None, None

    changed = json.dumps(fixed, sort_keys=True) != json.dumps(draft, sort_keys=True)
    example_values = _example_values_for_storage(fixed)
    examples_changed = json.dumps(example_values, sort_keys=True) != json.dumps(
        _loads(row.example_values_json) or [], sort_keys=True
    )
    if not changed and not examples_changed:
        return False, f"ok — {_body_summary(fixed)}", None, None

    after_summary = _body_summary(fixed)
    return True, f"{before_summary} -> {after_summary}", fixed, example_values


def _push_scope(db, *, rows: list[TelnyxWhatsappTemplate], args) -> int:
    fail_count = 0
    ok_count = 0

    if args.template_name:
        if len(rows) != 1:
            print(f"Push skipped — expected 1 template, found {len(rows)}", file=sys.stderr)
            return 1
        row = rows[0]
        try:
            result = SurveyWhatsappTemplateService.push_to_telnyx(db, row)
            ok_count += 1
            print(f"PUSH OK  {row.name}: {result.get('sync_message') or result.get('message')}")
        except SurveyWhatsappTemplateError as exc:
            fail_count += 1
            print(f"PUSH FAIL {row.name}: {exc}", file=sys.stderr)
        return 1 if fail_count else 0

    if args.survey_type_id or args.survey_type_slug:
        survey_type_id = args.survey_type_id.strip() if args.survey_type_id else ""
        if not survey_type_id:
            survey_type = SurveyTypeService.resolve_unique_by_slug(db, args.survey_type_slug.strip().lower())
            if survey_type is None:
                print(f"Survey type not found: {args.survey_type_slug}", file=sys.stderr)
                return 1
            survey_type_id = survey_type.id
        summary = SurveyWhatsappTemplateService.push_all_for_survey_type(db, survey_type_id)
        ok_count = int(summary.get("pushed") or 0)
        fail_count = int(summary.get("error_count") or 0)
        print(summary.get("message") or summary)
        for err in summary.get("errors") or []:
            print(
                f"  FAIL {err.get('template_name') or err.get('template_id')}: {err.get('error')}",
                file=sys.stderr,
            )
        return 1 if fail_count else 0

    if args.industry_slug:
        slug = args.industry_slug.strip().lower()
        industry = db.execute(select(Industry).where(Industry.slug == slug)).scalar_one_or_none()
        if industry is None:
            print(f"Industry not found for slug={slug!r}", file=sys.stderr)
            return 1
        summary = SurveyWhatsappTemplateService.push_all_for_industry(db, industry.id)
        ok_count = int(summary.get("pushed") or 0)
        fail_count = int(summary.get("error_count") or 0)
        print(summary.get("message") or summary)
        for err in summary.get("errors") or []:
            print(
                f"  FAIL {err.get('survey_type_name') or err.get('survey_type_id')} · "
                f"{err.get('template_name') or err.get('template_id')}: {err.get('error')}",
                file=sys.stderr,
            )
        return 1 if fail_count else 0

    if args.all_survey_templates:
        fail_count = 0
        ok_count = 0
        for row in rows:
            try:
                result = SurveyWhatsappTemplateService.push_to_telnyx(db, row)
                ok_count += 1
                print(f"PUSH OK  {row.name}: {result.get('sync_message') or result.get('message')}")
            except SurveyWhatsappTemplateError as exc:
                fail_count += 1
                print(f"PUSH FAIL {row.name}: {exc}", file=sys.stderr)
        print(f"\nPush done — OK: {ok_count}, failed: {fail_count}")
        return 1 if fail_count else 0

    print("Push skipped — no scope matched", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fix WA Survey template BODY variables/examples (static = clear, variables = examples)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only — no DB writes or push")
    parser.add_argument("--all-survey-templates", action="store_true", help="Every template linked to a survey type")
    parser.add_argument("--industry-slug", default="", help="Limit to one industry slug")
    parser.add_argument("--survey-type-slug", default="", help="Limit to one survey type slug")
    parser.add_argument("--survey-type-id", default="", help="Limit to one survey type UUID")
    parser.add_argument("--template-name", default="", help="Limit to one Meta template name")
    parser.add_argument(
        "--push",
        action="store_true",
        help="After fixing, push to Telnyx for the same scope (use with --template-name to test one)",
    )
    args = parser.parse_args()

    with get_sessionmaker()() as db:
        rows = _iter_templates(
            db,
            industry_slug=args.industry_slug.strip() or None,
            survey_type_slug=args.survey_type_slug.strip() or None,
            survey_type_id=args.survey_type_id.strip() or None,
            template_name=args.template_name.strip() or None,
            all_survey_templates=args.all_survey_templates,
        )
        if not rows:
            print("No templates matched the scope.")
            return 0

        scanned = 0
        fixed_count = 0
        skipped = 0

        for row in rows:
            scanned += 1
            label = row.display_name or row.name
            changed, detail, fixed_components, example_values = _apply_fix(row)
            if not changed:
                skipped += 1
                if args.dry_run or "skip" in detail or detail.startswith("ok"):
                    print(f"{'[dry-run] ' if args.dry_run else ''}{row.name} ({label}): {detail}")
                continue
            fixed_count += 1
            print(f"{'[dry-run] ' if args.dry_run else ''}fix {row.name} ({label}): {detail}")
            if args.dry_run:
                continue
            row.draft_components_json = _dumps(fixed_components)
            row.example_values_json = _dumps(example_values or [])
            if _is_local_row(row) or not _has_remote_telnyx_id(row):
                row.components_json = _dumps(fixed_components)
            row.local_sync_status = _refresh_local_sync_status(row)
            db.add(row)

        if not args.dry_run and fixed_count:
            db.commit()

        print(
            f"\nFix done — scanned {scanned}, "
            f"{'would fix' if args.dry_run else 'fixed'} {fixed_count}, unchanged/skipped {skipped}"
        )

        if args.push and not args.dry_run:
            print("")
            return _push_scope(db, rows=rows, args=args)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
