#!/usr/bin/env python3
"""Fix all WA Survey abc_choice templates locally (no Meta push).

UTILITY rows: button-only updates (diversified labels, best-first).
MARKETING rows: full body + button rewrite from canonical catalog/MD.

Usage:
  python scripts/fix_all_wa_survey_local_db.py --dry-run
  python scripts/fix_all_wa_survey_local_db.py --apply
  python scripts/fix_all_wa_survey_local_db.py --apply --industry-slug healthcare_dental
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.industry import Industry
from app.models.survey_type import SurveyType
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_wa_md_seed_service import (
    MdSurveyQuestion,
    _build_abc_choice_components,
    parse_md_survey_pack,
)
from app.services.survey_wa_context_regenerate_service import _body_from_components
from app.services.survey_whatsapp_template_service import (
    SYNC_LOCAL_CHANGES,
    _body_preview,
    _buttons_from_components,
    _dumps,
    _effective_components,
    _loads,
    _normalize_draft_components,
)
from app.services.wa_template_utility_lint import clamp_utility_button_labels, lint_utility_template
from seed_data.wa_survey_abc_catalog import WA_SURVEY_ABC_CATALOG
from seed_data.wa_survey_button_diversify import diversify_question_options

# Reuse employee helpers
from scripts.fix_employee_survey_local_db import (  # noqa: E402
    _EXTRA_TOPIC_BUTTONS,
    _best_first_button_labels,
    _button_label_strings,
    _find_template_for_type,
    _full_update_from_md,
    _is_marketing_row,
    _update_buttons_only,
)

EMPLOYEE_MD = ROOT / "seed-data" / "wa-survey" / "employee-experience.md"
REPORT_DIR = ROOT / "seed-data" / "wa-survey" / "migration-reports"
EMPLOYEE_SLUG = "employee_survey"


def _catalog_by_industry() -> dict[str, dict[str, MdSurveyQuestion]]:
    out: dict[str, dict[str, MdSurveyQuestion]] = {}
    for block in WA_SURVEY_ABC_CATALOG:
        slug = str(block.get("slug") or "").strip()
        if not slug:
            continue
        m: dict[str, MdSurveyQuestion] = {}
        for q in block.get("questions") or []:
            name = str(q.get("name") or "").strip()
            if not name:
                continue
            options = diversify_question_options(name, list(q.get("options") or []))
            m[name.lower()] = MdSurveyQuestion(
                name=name,
                body=str(q.get("body") or "").strip(),
                options=options,
                wizard_description=str(q.get("body") or "").strip(),
            )
        out[slug] = m
    return out


def _employee_md_map() -> dict[str, MdSurveyQuestion]:
    if not EMPLOYEE_MD.is_file():
        return {}
    pack = parse_md_survey_pack(EMPLOYEE_MD.read_text(encoding="utf-8"), source_name=str(EMPLOYEE_MD))
    return {q.name.strip().lower(): q for q in pack.questions}


def _canonical_for_type(
    slug: str,
    survey_type_name: str,
    *,
    catalog: dict[str, dict[str, MdSurveyQuestion]],
    employee_map: dict[str, MdSurveyQuestion],
) -> MdSurveyQuestion | None:
    key = str(survey_type_name or "").strip().lower()
    if slug == EMPLOYEE_SLUG:
        q = employee_map.get(key)
        if q is not None:
            return q
    return (catalog.get(slug) or {}).get(key)


def _target_buttons(q: MdSurveyQuestion | None, extra: list[str] | None) -> list[str]:
    if q is not None:
        return clamp_utility_button_labels(_best_first_button_labels(q.options))
    if extra is not None:
        return clamp_utility_button_labels(_best_first_button_labels(extra))
    return []


def _lint_row(row: TelnyxWhatsappTemplate, *, employee: bool) -> list[str]:
    body = _body_from_components(_effective_components(row)) or row.body_preview or ""
    buttons = _button_label_strings(row)
    result = lint_utility_template(
        body=body,
        buttons=buttons,
        language=row.language,
        meta_category="utility",
        require_transaction_anchor=not employee,
    )
    return [f"{i.field}: {i.message}" for i in result.issues]


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix all WA Survey templates locally")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--industry-slug", action="append", default=[])
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        print("Pass --dry-run or --apply", file=sys.stderr)
        return 1

    catalog = _catalog_by_industry()
    employee_map = _employee_md_map()
    slugs = args.industry_slug or [b["slug"] for b in WA_SURVEY_ABC_CATALOG]

    report: dict = {
        "at": datetime.now(timezone.utc).isoformat(),
        "dry_run": bool(args.dry_run),
        "industries": {},
        "totals": {
            "template_rows": 0,
            "marketing_fixes": 0,
            "button_fixes": 0,
            "lint_failures": 0,
            "skipped": 0,
        },
    }

    db = get_sessionmaker()()
    try:
        for slug in slugs:
            industry = db.execute(select(Industry).where(Industry.slug == slug)).scalar_one_or_none()
            if industry is None:
                print(f"skip missing industry {slug}", file=sys.stderr)
                continue
            ind_report: dict = {
                "slug": slug,
                "template_rows": 0,
                "marketing_fixes": [],
                "button_fixes": [],
                "lint_failures": [],
                "skipped": [],
            }
            pairs = _find_template_for_type(db, industry.id)
            ind_report["template_rows"] = len(pairs)
            report["totals"]["template_rows"] += len(pairs)

            for row, st in pairs:
                q = _canonical_for_type(slug, st.name, catalog=catalog, employee_map=employee_map)
                extra = _EXTRA_TOPIC_BUTTONS.get(str(st.name or "").strip().lower()) if slug == EMPLOYEE_SLUG else None
                target_btns = _target_buttons(q, extra)
                old_btns = _button_label_strings(row)
                entry = {
                    "id": row.id,
                    "survey_type": st.name,
                    "name": row.name,
                    "old_category": row.category,
                }

                if _is_marketing_row(row) and (q is not None or extra is not None):
                    old_body = _body_from_components(_effective_components(row)) or row.body_preview
                    if args.apply:
                        if q is not None:
                            _full_update_from_md(row, q)
                        elif extra is not None:
                            _update_buttons_only(row, extra)
                        row.category = "UTILITY"
                        row.local_sync_status = SYNC_LOCAL_CHANGES
                        row.step_role = row.step_role or "abc_choice"
                        db.add(row)
                    ind_report["marketing_fixes"].append(
                        {
                            **entry,
                            "old_body": (old_body or "")[:200],
                            "new_body": (q.body[:200] if q else ""),
                            "new_buttons": target_btns,
                        }
                    )
                    report["totals"]["marketing_fixes"] += 1
                elif target_btns:
                    if args.apply:
                        if old_btns != target_btns:
                            src_opts = q.options if q else (extra or [])
                            _update_buttons_only(row, src_opts)
                        row.category = "UTILITY"
                        row.local_sync_status = SYNC_LOCAL_CHANGES
                        row.step_role = row.step_role or "abc_choice"
                        db.add(row)
                    if old_btns != target_btns:
                        ind_report["button_fixes"].append(
                            {**entry, "old_buttons": old_btns, "new_buttons": target_btns}
                        )
                        report["totals"]["button_fixes"] += 1
                else:
                    if args.apply:
                        row.category = "UTILITY"
                        row.local_sync_status = SYNC_LOCAL_CHANGES
                        db.add(row)
                    ind_report["skipped"].append({"survey_type": st.name, "reason": "no_canonical"})

                issues = _lint_row(row, employee=(slug == EMPLOYEE_SLUG))
                if issues:
                    ind_report["lint_failures"].append(
                        {"id": row.id, "name": row.name, "survey_type": st.name, "issues": issues[:3]}
                    )
                    report["totals"]["lint_failures"] += 1

            report["industries"][slug] = ind_report
            print(
                f"{slug}: rows={ind_report['template_rows']} "
                f"mkt={len(ind_report['marketing_fixes'])} "
                f"btn={len(ind_report['button_fixes'])} "
                f"lint={len(ind_report['lint_failures'])}"
            )

        if args.apply:
            db.commit()

        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = REPORT_DIR / f"all-industries-fix-{stamp}.json"
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"report={out_path}")
        return 0 if report["totals"]["lint_failures"] == 0 else 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
