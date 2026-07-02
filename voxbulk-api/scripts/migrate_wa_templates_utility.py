#!/usr/bin/env python3
"""OpenAI 4-phase WA UTILITY migration — rewrite DB templates, save, push to Meta.

Phases:
  1 — WA Survey EN: healthcare_dental … property_lettings (5 industries, ~125)
  2 — WA Survey EN: retail_ecommerce … fitness_wellness (5 industries, ~125)
  3 — WA Survey EN: financial_services … employee_survey (4 industries, ~100)
  4 — Customer Feedback EN+AR (all 7 industries) + AI Interview EN (4)

Usage:
  cd voxbulk-api && source .venv/bin/activate
  python scripts/verify_wa_utility_waba.py
  python scripts/seed_utility_templates_to_db.py --all
  python scripts/migrate_wa_templates_utility.py --phase 1 --dry-run
  python scripts/migrate_wa_templates_utility.py --phase 1 --save --push
  python scripts/migrate_wa_templates_utility.py --phase 4 --save --push --translate-ar
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
from app.services.customer_feedback.feedback_template_translation_service import (
    find_translated_template,
    list_english_source_templates,
    translate_templates_to_arabic,
)
from app.services.customer_feedback.feedback_telnyx_push_service import (
    FeedbackTelnyxPushError,
    push_feedback_template_to_telnyx,
)
from app.services.customer_feedback.feedback_wa_utility_rewrite_service import (
    FEEDBACK_INDUSTRY_SLUGS,
    process_feedback_industry,
)
from app.services.interview_whatsapp_template_service import InterviewWhatsappTemplateService
from app.services.survey_wa_utility_rewrite_service import process_template_names
from app.services.telnyx_voice_service import _telnyx_config, resolve_telnyx_whatsapp_waba_id
from app.services.wa_template_utility_lint import lint_utility_template
from app.services.wa_template_utility_migration_service import (
    audit_all_wa_templates,
    deactivate_duplicate_and_orphan_templates,
)

MIGRATION_PHASES: list[dict[str, Any]] = [
    {
        "phase": 1,
        "kind": "survey",
        "industries": [
            "healthcare_dental",
            "recruitment_staffing",
            "hospitality_food",
            "hotel_accommodation",
            "property_lettings",
        ],
    },
    {
        "phase": 2,
        "kind": "survey",
        "industries": [
            "retail_ecommerce",
            "automotive",
            "education_training",
            "legal_accountancy",
            "fitness_wellness",
        ],
    },
    {
        "phase": 3,
        "kind": "survey",
        "industries": [
            "financial_services",
            "logistics_delivery",
            "events_entertainment",
            "employee_survey",
        ],
    },
    {
        "phase": 4,
        "kind": "feedback_interview",
        "industries": list(FEEDBACK_INDUSTRY_SLUGS),
    },
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
            TelnyxWhatsappTemplate.active_for_survey.is_(True),
        )
        .order_by(TelnyxWhatsappTemplate.name)
    ).all()
    return [str(name) for (name,) in rows if name]


def _write_report(payload: dict[str, Any], *, phase: int) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = REPORT_DIR / f"migration-phase{phase}-{ts}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def _run_survey_phase(
    db,
    *,
    industries: list[str],
    phase: int,
    dry_run: bool,
    save: bool,
    push: bool,
    sync_remote: bool,
    use_llm: bool,
    llm_provider: str,
    skip_already_pushed: bool,
    push_delay_seconds: float,
) -> dict[str, Any]:
    names: list[str] = []
    for slug in industries:
        names.extend(_survey_template_names_for_industry(db, slug))
    if not names:
        return {"kind": "survey", "phase": phase, "industries": industries, "warning": "no templates found", "results": []}

    results = process_template_names(
        db,
        names,
        sync_remote=sync_remote,
        save=save and not dry_run,
        push=push and not dry_run,
        dry_run=dry_run,
        use_llm=use_llm,
        llm_provider=llm_provider,
        skip_already_pushed=skip_already_pushed,
        push_delay_seconds=push_delay_seconds,
    )
    return {
        "kind": "survey",
        "phase": phase,
        "industries": industries,
        "template_count": len(names),
        "ok_count": sum(1 for r in results if r.ok),
        "failed_count": sum(1 for r in results if not r.ok),
        "skipped_count": sum(1 for r in results if r.ok and "skipped" in str(r.message or "").lower()),
        "results": [
            {
                "template_name": r.template_name,
                "ok": r.ok,
                "message": r.message,
                "pushed": r.pushed,
                "old_body": r.old_body[:160],
                "new_body": r.new_body[:160],
            }
            for r in results
        ],
    }


def _run_feedback_interview_phase(
    db,
    *,
    industries: list[str],
    phase: int,
    dry_run: bool,
    save: bool,
    push: bool,
    translate_ar: bool,
    use_llm: bool,
    llm_provider: str,
) -> dict[str, Any]:
    industry_reports: list[dict[str, Any]] = []
    failed = 0
    total_en = 0
    total_ar = 0

    for slug in industries:
        rewrite_results = process_feedback_industry(
            db,
            slug,
            dry_run=dry_run,
            save=save and not dry_run,
            push=push and not dry_run,
            languages=["en", "ar"],
            use_llm=use_llm,
            llm_provider=llm_provider,
        )
        en_count = len(rewrite_results)
        ar_count = 0
        translate_summary = None

        if translate_ar and save and not dry_run:
            translate_summary = translate_templates_to_arabic(
                db,
                industry_slug=slug,
                force=True,
                use_llm=use_llm,
                provider=llm_provider,
                push_telnyx=False,
                dry_run=False,
            )
            ar_count = int(translate_summary.get("translated") or 0) + int(translate_summary.get("skipped") or 0)

        if push and not dry_run:
            for source in list_english_source_templates(db, industry_slug=slug):
                ar_row = find_translated_template(db, source, language="ar")
                if ar_row is None or not ar_row.is_active:
                    failed += 1
                    continue
                lint = lint_utility_template(
                    body=ar_row.body_text,
                    buttons=json.loads(ar_row.buttons_json or "[]") if ar_row.buttons_json else [],
                    language="ar",
                    meta_category="utility",
                    template_key=ar_row.template_key,
                    require_transaction_anchor=False,
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
                "failed": phase_failed,
                "translate": translate_summary,
            }
        )

    interview_report = _run_interview(db, dry_run=dry_run, push=push and not dry_run)
    failed += int(interview_report.get("failed_count") or 0)

    return {
        "kind": "feedback_interview",
        "phase": phase,
        "industries": industries,
        "en_count": total_en,
        "ar_count": total_ar,
        "en_ar_paired": total_en == total_ar if total_ar else False,
        "failed_count": failed,
        "industry_reports": industry_reports,
        "interview": interview_report,
    }


def _run_interview(db, *, dry_run: bool, push: bool) -> dict[str, Any]:
    from app.data.interview_whatsapp_template_catalog import INTERVIEW_WA_TEMPLATE_SPECS

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
        item = {"name": row.name, "lint_ok": lint.ok, "pushed": False}
        if not lint.ok:
            failed += 1
            item["lint_issues"] = [i.message for i in lint.issues]
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
    return {"template_count": len(rows), "failed_count": failed, "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenAI 4-phase WA UTILITY migration")
    parser.add_argument("--phase", type=int, required=True, choices=[1, 2, 3, 4])
    parser.add_argument("--dry-run", action="store_true", help="Preview OpenAI rewrite only")
    parser.add_argument("--save", action="store_true", help="Save rewritten templates to DB")
    parser.add_argument("--push", action="store_true", help="Push to Telnyx/Meta (implies --save)")
    parser.add_argument("--sync-remote", action="store_true")
    parser.add_argument("--translate-ar", action="store_true", help="Phase 4: translate feedback EN to AR")
    parser.add_argument("--dedup", action="store_true", help="Deactivate duplicate/orphan rows after phase")
    parser.add_argument("--audit", action="store_true", help="Print DB audit before running phase")
    parser.add_argument("--no-llm", action="store_true", help="Rule-based rewrite only (no OpenAI)")
    parser.add_argument("--llm-provider", default="openai", help="LLM provider (default: openai)")
    parser.add_argument("--skip-waba-check", action="store_true")
    parser.add_argument(
        "--no-skip-already-pushed",
        action="store_true",
        help="Re-push templates already PENDING/APPROVED on Meta (default: skip them)",
    )
    parser.add_argument(
        "--push-delay",
        type=float,
        default=1.5,
        help="Seconds to wait between Telnyx pushes (default: 1.5)",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.push:
        args.save = True
    if not args.dry_run and not args.save and not args.push:
        parser.error("Specify --dry-run, --save, and/or --push")

    phase_cfg = MIGRATION_PHASES[args.phase - 1]
    llm_provider = str(args.llm_provider or "openai").strip().lower()
    use_llm = not args.no_llm

    with get_sessionmaker()() as db:
        if args.push and not args.skip_waba_check:
            ok, msg = _verify_waba_id(db)
            if not ok:
                print(f"ERROR: {msg}", file=sys.stderr)
                return 1
            print(f"WABA OK: {msg}")

        audit_before = audit_all_wa_templates(db) if args.audit else None

        if phase_cfg["kind"] == "survey":
            report = _run_survey_phase(
                db,
                industries=list(phase_cfg["industries"]),
                phase=args.phase,
                dry_run=args.dry_run,
                save=args.save,
                push=args.push,
                sync_remote=args.sync_remote,
                use_llm=use_llm,
                llm_provider=llm_provider,
                skip_already_pushed=not args.no_skip_already_pushed,
                push_delay_seconds=max(0.0, float(args.push_delay or 0)),
            )
        else:
            report = _run_feedback_interview_phase(
                db,
                industries=list(phase_cfg["industries"]),
                phase=args.phase,
                dry_run=args.dry_run,
                save=args.save,
                push=args.push,
                translate_ar=bool(args.translate_ar or args.phase == 4),
                use_llm=use_llm,
                llm_provider=llm_provider,
            )

        dedup = None
        if args.dedup and args.save and not args.dry_run:
            dedup = deactivate_duplicate_and_orphan_templates(db, dry_run=False)

        audit_after = audit_all_wa_templates(db) if args.audit else None

    summary = {
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "waba_id": EXPECTED_WABA_ID,
        "meta_business_portfolio_id": META_BUSINESS_PORTFOLIO_ID,
        "phase": args.phase,
        "llm_provider": llm_provider,
        "dry_run": args.dry_run,
        "save": args.save,
        "push": args.push,
        "audit_before": audit_before,
        "report": report,
        "dedup": dedup,
        "audit_after": audit_after,
    }
    path = _write_report(summary, phase=args.phase)
    print(f"Report: {path}")
    print(
        f"Phase {args.phase} kind={report.get('kind')} "
        f"templates={report.get('template_count') or report.get('en_count')} "
        f"skipped={report.get('skipped_count', 0)} "
        f"failed={report.get('failed_count')}"
    )
    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    return 1 if int(report.get("failed_count") or 0) > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
