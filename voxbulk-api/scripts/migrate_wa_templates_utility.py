#!/usr/bin/env python3
"""Orchestrate Meta UTILITY migration for WA Survey, Customer Feedback, and AI Interview templates.

Languages: Survey EN only | Feedback EN+AR | Interview EN only

Usage:
  cd voxbulk-api && source .venv/bin/activate
  python scripts/migrate_wa_templates_utility.py --product survey --phase 1 --dry-run
  python scripts/migrate_wa_templates_utility.py --product feedback --phase 1 --rewrite-only --translate-ar
  python scripts/migrate_wa_templates_utility.py --product feedback --phase 1 --push --languages en,ar
  python scripts/migrate_wa_templates_utility.py --product interview --dry-run --push
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.constants.wa_utility_migration import EXPECTED_WABA_ID, META_BUSINESS_PORTFOLIO_ID
from app.core.database import get_sessionmaker
from app.models.industry import Industry
from app.models.survey_type import SurveyType
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.customer_feedback.feedback_template_translation_service import translate_templates_to_arabic
from app.services.customer_feedback.feedback_telnyx_push_service import (
    FeedbackTelnyxPushError,
    push_all_feedback_templates_for_industry,
    push_feedback_template_to_telnyx,
)
from app.services.customer_feedback.feedback_wa_utility_rewrite_service import process_feedback_industry
from app.services.interview_whatsapp_template_service import InterviewWhatsappTemplateService
from app.services.survey_wa_utility_rewrite_service import process_template_names
from app.services.telnyx_voice_service import _telnyx_config, resolve_telnyx_whatsapp_waba_id
from app.services.wa_template_utility_lint import lint_utility_template

SURVEY_PHASES: list[list[str]] = [
    ["healthcare_dental", "recruitment_staffing"],
    ["hospitality_food", "hotel_accommodation"],
    ["property_lettings", "retail_ecommerce"],
    ["automotive", "education_training"],
    ["legal_accountancy", "fitness_wellness"],
    ["financial_services", "logistics_delivery"],
    ["events_entertainment", "employee_survey"],
]

FEEDBACK_PHASES: list[list[str]] = [
    ["restaurant", "retail"],
    ["salon", "hotel"],
    ["fitness", "events"],
    ["others"],
]

REPORT_DIR = ROOT / "seed-data" / "wa-survey" / "migration-reports"


def _verify_waba_id(db) -> tuple[bool, str]:
    try:
        config = _telnyx_config(db)
    except Exception as exc:
        return False, f"Telnyx not configured: {exc}"
    configured = str(config.get("whatsapp_waba_id") or config.get("waba_id") or "").strip()
    resolved = resolve_telnyx_whatsapp_waba_id(db, config)
    effective = configured or resolved
    if not effective:
        return False, f"No WABA ID — set Admin → Telnyx → WhatsApp WABA ID to {EXPECTED_WABA_ID}"
    if effective != EXPECTED_WABA_ID:
        return False, f"WABA mismatch: active={effective!r} expected={EXPECTED_WABA_ID!r}"
    return True, effective


def _survey_template_names_for_industry(db, industry_slug: str) -> list[str]:
    slug = industry_slug.strip().lower()
    industry = db.execute(select(Industry).where(Industry.slug == slug)).scalar_one_or_none()
    if industry is None:
        raise ValueError(f"Survey industry not found: {industry_slug}")
    type_ids = list(db.scalars(select(SurveyType.id).where(SurveyType.industry_id == industry.id)))
    if not type_ids:
        return []
    rows = db.execute(
        select(TelnyxWhatsappTemplate.name)
        .where(
            TelnyxWhatsappTemplate.survey_type_id.in_(type_ids),
            TelnyxWhatsappTemplate.step_role == "abc_choice",
        )
        .order_by(TelnyxWhatsappTemplate.name)
    ).all()
    return [str(name) for (name,) in rows if name]


def _parse_languages(raw: str | None) -> list[str]:
    if not raw:
        return ["en", "ar"]
    return [part.strip().lower() for part in str(raw).split(",") if part.strip()]


def _write_report(payload: dict[str, Any], *, product: str, phase: int | None) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"{product}-phase{phase}" if phase else product
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = REPORT_DIR / f"migration-{suffix}-{ts}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def _run_survey_phase(
    db,
    *,
    phase: int,
    dry_run: bool,
    rewrite_only: bool,
    push: bool,
    sync_remote: bool,
    no_llm: bool,
) -> dict[str, Any]:
    industries = SURVEY_PHASES[phase - 1]
    all_results: list[dict[str, Any]] = []
    names: list[str] = []
    for slug in industries:
        names.extend(_survey_template_names_for_industry(db, slug))

    if not names:
        return {"product": "survey", "phase": phase, "industries": industries, "warning": "no templates found", "results": []}

    results = process_template_names(
        db,
        names,
        sync_remote=sync_remote,
        push=push and not dry_run and not rewrite_only,
        dry_run=dry_run or rewrite_only,
        use_deepseek=not no_llm,
    )
    for item in results:
        all_results.append(
            {
                "template_name": item.template_name,
                "ok": item.ok,
                "message": item.message,
                "pushed": item.pushed,
                "old_body": item.old_body[:120],
                "new_body": item.new_body[:120],
            }
        )
    failed = sum(1 for r in results if not r.ok)
    return {
        "product": "survey",
        "phase": phase,
        "industries": industries,
        "language": "en_GB",
        "template_count": len(names),
        "ok_count": len(results) - failed,
        "failed_count": failed,
        "results": all_results,
    }


def _run_feedback_phase(
    db,
    *,
    phase: int,
    dry_run: bool,
    rewrite_only: bool,
    push: bool,
    translate_ar: bool,
    languages: list[str],
    no_llm: bool,
) -> dict[str, Any]:
    industries = FEEDBACK_PHASES[phase - 1]
    industry_reports: list[dict[str, Any]] = []
    total_en = 0
    total_ar = 0
    failed = 0

    for slug in industries:
        rewrite_results = process_feedback_industry(
            db,
            slug,
            dry_run=dry_run or (rewrite_only and not push),
            rewrite_only=rewrite_only,
            push=push and not dry_run,
            languages=languages,
            use_llm=not no_llm,
        )
        en_count = len(rewrite_results)
        ar_count = 0
        translate_summary: dict[str, Any] | None = None
        push_summary: dict[str, Any] | None = None

        if translate_ar and not dry_run:
            translate_summary = translate_templates_to_arabic(
                db,
                industry_slug=slug,
                force=True,
                use_llm=not no_llm,
                push_telnyx=False,
                dry_run=False,
            )
            ar_count = int(translate_summary.get("translated") or 0) + int(translate_summary.get("skipped") or 0)

        if push and not dry_run:
            try:
                push_summary = push_all_feedback_templates_for_industry(
                    db,
                    industry_slug=slug,
                    dry_run=False,
                )
            except FeedbackTelnyxPushError as exc:
                push_summary = {"error": str(exc)}

        if push and not dry_run and "ar" in languages:
            from app.services.customer_feedback.feedback_template_translation_service import list_english_source_templates
            from app.services.customer_feedback.feedback_template_translation_service import find_translated_template

            for source in list_english_source_templates(db, industry_slug=slug):
                ar_row = find_translated_template(db, source, language="ar")
                if ar_row is None:
                    continue
                lint = lint_utility_template(
                    body=ar_row.body_text,
                    buttons=json.loads(ar_row.buttons_json or "[]") if ar_row.buttons_json else [],
                    language="ar",
                    meta_category="utility",
                    template_key=ar_row.template_key,
                )
                if not lint.ok:
                    failed += 1
                    continue
                try:
                    push_feedback_template_to_telnyx(db, ar_row)
                except FeedbackTelnyxPushError:
                    failed += 1

        phase_failed = sum(1 for r in rewrite_results if not r.ok)
        failed += phase_failed
        total_en += en_count
        total_ar = max(total_ar, ar_count)
        industry_reports.append(
            {
                "industry_slug": slug,
                "en_templates": en_count,
                "ar_templates": ar_count,
                "en_ar_paired": en_count == ar_count if ar_count else None,
                "failed": phase_failed,
                "rewrite_results": [
                    {
                        "template_key": r.template_key,
                        "language": r.language,
                        "ok": r.ok,
                        "lint_ok": r.lint_ok,
                        "message": r.message,
                        "pushed": r.pushed,
                    }
                    for r in rewrite_results
                ],
                "translate": translate_summary,
                "push": push_summary,
            }
        )

    return {
        "product": "feedback",
        "phase": phase,
        "industries": industries,
        "languages": languages,
        "en_count": total_en,
        "ar_count": total_ar,
        "en_ar_paired": total_en == total_ar if total_ar else False,
        "failed_count": failed,
        "industry_reports": industry_reports,
    }


def _run_interview(db, *, dry_run: bool, push: bool) -> dict[str, Any]:
    from app.data.interview_whatsapp_template_catalog import INTERVIEW_WA_TEMPLATE_SPECS
    from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate

    InterviewWhatsappTemplateService.ensure_catalog_seeded(db)
    rows = list(
        db.execute(
            select(TelnyxWhatsappTemplate).where(
                TelnyxWhatsappTemplate.sales_template_key.in_(
                    [spec["sales_template_key"] for spec in INTERVIEW_WA_TEMPLATE_SPECS]
                )
            )
        ).scalars()
    )
    results: list[dict[str, Any]] = []
    failed = 0
    for row in rows:
        spec = next(
            (s for s in INTERVIEW_WA_TEMPLATE_SPECS if s["sales_template_key"] == row.sales_template_key),
            None,
        )
        body = str((spec or {}).get("body") or row.display_name or "")
        lint = lint_utility_template(
            body=body,
            buttons=[],
            language="en_GB",
            meta_category="utility",
            require_transaction_anchor=False,
            allow_variables=True,
        )
        item = {
            "name": row.name,
            "sales_template_key": row.sales_template_key,
            "lint_ok": lint.ok,
            "lint_issues": [i.message for i in lint.issues],
            "pushed": False,
        }
        if not lint.ok:
            failed += 1
            results.append(item)
            continue
        if push and not dry_run:
            try:
                InterviewWhatsappTemplateService.push_to_telnyx(db, row)
                item["pushed"] = True
            except Exception as exc:
                item["error"] = str(exc)
                failed += 1
        results.append(item)
    return {
        "product": "interview",
        "language": "en_GB",
        "template_count": len(rows),
        "failed_count": failed,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="WA UTILITY template migration orchestrator")
    parser.add_argument("--product", choices=["survey", "feedback", "interview", "all"], required=True)
    parser.add_argument("--phase", type=int, help="Phase number (survey 1-7, feedback 1-4)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rewrite-only", action="store_true")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--sync-remote", action="store_true")
    parser.add_argument("--translate-ar", action="store_true", help="Feedback: translate EN to AR after rewrite")
    parser.add_argument("--languages", default="en,ar", help="Feedback push languages (default: en,ar)")
    parser.add_argument("--no-llm", action="store_true", help="Rule-based rewrite only")
    parser.add_argument(
        "--skip-waba-check",
        action="store_true",
        help=f"Skip WABA verification (default checks {EXPECTED_WABA_ID})",
    )
    parser.add_argument("--json", action="store_true", help="Print full JSON summary")
    args = parser.parse_args()

    if args.product in {"survey", "feedback"} and not args.phase:
        parser.error("--phase is required for survey and feedback products")

    languages = _parse_languages(args.languages)
    reports: list[dict[str, Any]] = []

    with get_sessionmaker()() as db:
        waba_ok, waba_msg = True, ""
        if args.push and not args.skip_waba_check:
            waba_ok, waba_msg = _verify_waba_id(db)
            if not waba_ok:
                print(f"ERROR: {waba_msg}", file=sys.stderr)
                return 1
            print(f"WABA OK: {waba_msg}")

        products = ["survey", "feedback", "interview"] if args.product == "all" else [args.product]
        for product in products:
            if product == "survey":
                phase = args.phase or 1
                if phase < 1 or phase > len(SURVEY_PHASES):
                    print(f"Invalid survey phase {phase}", file=sys.stderr)
                    return 1
                reports.append(
                    _run_survey_phase(
                        db,
                        phase=phase,
                        dry_run=args.dry_run,
                        rewrite_only=args.rewrite_only,
                        push=args.push,
                        sync_remote=args.sync_remote,
                        no_llm=args.no_llm,
                    )
                )
            elif product == "feedback":
                phase = args.phase or 1
                if phase < 1 or phase > len(FEEDBACK_PHASES):
                    print(f"Invalid feedback phase {phase}", file=sys.stderr)
                    return 1
                reports.append(
                    _run_feedback_phase(
                        db,
                        phase=phase,
                        dry_run=args.dry_run,
                        rewrite_only=args.rewrite_only,
                        push=args.push,
                        translate_ar=args.translate_ar,
                        languages=languages,
                        no_llm=args.no_llm,
                    )
                )
            else:
                reports.append(_run_interview(db, dry_run=args.dry_run, push=args.push))

    summary = {
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "waba_id": EXPECTED_WABA_ID,
        "meta_business_portfolio_id": META_BUSINESS_PORTFOLIO_ID,
        "waba_verified": waba_msg if args.push and not args.skip_waba_check else None,
        "dry_run": args.dry_run,
        "reports": reports,
    }
    failed_total = sum(int(r.get("failed_count") or 0) for r in reports)
    report_path = _write_report(summary, product=args.product, phase=args.phase)
    print(f"Report: {report_path}")
    for report in reports:
        print(
            f"{report.get('product')} phase={report.get('phase')} "
            f"templates={report.get('template_count') or report.get('en_count')} "
            f"failed={report.get('failed_count')}"
        )
    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    return 1 if failed_total else 0


if __name__ == "__main__":
    raise SystemExit(main())
