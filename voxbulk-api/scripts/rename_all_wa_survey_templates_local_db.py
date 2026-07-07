#!/usr/bin/env python3
"""Rename all WA Survey templates to was_* names (local DB only, no Meta push).

Also enforces category=UTILITY and lints every template for Meta utility compliance.

Usage:
  python scripts/rename_all_wa_survey_templates_local_db.py --dry-run
  python scripts/rename_all_wa_survey_templates_local_db.py --apply
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
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.industry_service import SYSTEM_SURVEY_INDUSTRY_SLUG
from app.services.survey_industry_seed_service import INDUSTRY_CATALOG
from app.services.survey_system_template_service import SYSTEM_TEMPLATE_KINDS, SurveySystemTemplateService
from app.services.survey_wa_context_regenerate_service import _body_from_components
from app.services.survey_whatsapp_template_service import (
    SYNC_LOCAL_CHANGES,
    SurveyWhatsappTemplateService,
    _effective_components,
)
from app.services.wa_template_privacy import PRIVACY_MODE_ON, resolve_row_privacy_mode
from app.services.wa_template_utility_lint import lint_utility_template
from seed_data.wa_survey_template_naming import is_was_survey_name, lang_suffix, was_industry_topic_name, was_system_template_name

import importlib.util

_emp_spec = importlib.util.spec_from_file_location(
    "fix_employee_survey_local_db",
    ROOT / "scripts" / "fix_employee_survey_local_db.py",
)
_emp = importlib.util.module_from_spec(_emp_spec)
assert _emp_spec.loader is not None
_emp_spec.loader.exec_module(_emp)

_button_label_strings = _emp._button_label_strings
_find_template_for_type = _emp._find_template_for_type
_lang_suffix = lang_suffix

REPORT_DIR = ROOT / "seed-data" / "wa-survey" / "migration-reports"
EMPLOYEE_SLUG = "employee_survey"


def _lint_row(row: TelnyxWhatsappTemplate, *, employee: bool, system: bool) -> list[str]:
    body = _body_from_components(_effective_components(row)) or row.body_preview or ""
    buttons = _button_label_strings(row)
    result = lint_utility_template(
        body=body,
        buttons=buttons,
        language=row.language,
        meta_category=str(row.category or "utility"),
        require_transaction_anchor=not (employee or system),
        allow_variables=system,
    )
    return [f"{i.field}: {i.message}" for i in result.issues]


def _allocate_name(
    industry_slug: str,
    topic_name: str,
    language: str | None,
    used: set[str],
) -> str:
    lang = _lang_suffix(language)
    for seq in range(1, 100):
        candidate = was_industry_topic_name(
            industry_slug, topic_name, seq=seq, language=lang
        )
        if candidate not in used:
            used.add(candidate)
            return candidate
    raise RuntimeError(f"Could not allocate unique name for {industry_slug}/{topic_name}")


def _rename_industry_pass(db, *, apply: bool, report: dict) -> None:
    catalog_slugs = [item["slug"] for item in INDUSTRY_CATALOG]
    used_names: set[str] = {
        str(r[0])
        for r in db.execute(
            select(TelnyxWhatsappTemplate.name).where(
                TelnyxWhatsappTemplate.name.like("was_%")
            )
        ).all()
    }

    for slug in catalog_slugs:
        industry = db.execute(select(Industry).where(Industry.slug == slug)).scalar_one_or_none()
        if industry is None:
            report["skipped_industries"].append({"slug": slug, "reason": "missing_industry"})
            continue

        pairs = _find_template_for_type(db, industry.id)
        ind_entry = {"slug": slug, "renames": [], "utility_fixes": [], "lint_failures": []}

        for row, st in pairs:
            current = str(row.name or "").strip().lower()
            if is_was_survey_name(row.name):
                report["already_named"] += 1
                target = current
            else:
                target = _allocate_name(slug, st.name, row.language, used_names)
                entry = {
                    "id": row.id,
                    "survey_type": st.name,
                    "old_name": row.name,
                    "new_name": target,
                }
                ind_entry["renames"].append(entry)
                report["renames"].append({**entry, "industry": slug})
                if apply:
                    row = SurveyWhatsappTemplateService.rename_for_meta_sync(db, row, target)

            cat = str(row.category or "").upper()
            if cat != "UTILITY":
                ind_entry["utility_fixes"].append(
                    {"id": row.id, "name": row.name, "old_category": row.category}
                )
                report["utility_category_fixes"].append(
                    {"id": row.id, "name": row.name, "old_category": row.category}
                )
                if apply:
                    row.category = "UTILITY"
                    row.local_sync_status = SYNC_LOCAL_CHANGES
                    db.add(row)

            issues = _lint_row(row, employee=(slug == EMPLOYEE_SLUG), system=False)
            if issues:
                fail = {"id": row.id, "name": row.name, "survey_type": st.name, "issues": issues[:5]}
                ind_entry["lint_failures"].append(fail)
                report["lint_failures"].append({**fail, "industry": slug})

        report["industries"][slug] = ind_entry
        print(
            f"{slug}: renames={len(ind_entry['renames'])} "
            f"utility={len(ind_entry['utility_fixes'])} "
            f"lint={len(ind_entry['lint_failures'])}"
        )


def _system_kind_for_type(st: SurveyType) -> str | None:
    kind = str(st.system_template_kind or "").strip().lower()
    return kind if kind in SYSTEM_TEMPLATE_KINDS else None


def _rename_system_pass(db, *, apply: bool, report: dict) -> None:
    industry = db.execute(
        select(Industry).where(Industry.slug == SYSTEM_SURVEY_INDUSTRY_SLUG)
    ).scalar_one_or_none()
    if industry is None:
        report["system"]["error"] = "system industry missing"
        return

    SurveySystemTemplateService.ensure_system_survey_types(db)
    used_names: set[str] = {
        str(r[0])
        for r in db.execute(
            select(TelnyxWhatsappTemplate.name).where(
                TelnyxWhatsappTemplate.name.like("was_system_%")
            )
        ).all()
    }

    # Active templates per kind+privacy — rename sendable keepers first.
    for kind in SYSTEM_TEMPLATE_KINDS:
        st = SurveySystemTemplateService.survey_type_for_kind(db, kind)
        rows = list(
            db.execute(
                select(TelnyxWhatsappTemplate)
                .join(
                    SurveyTypeTemplate,
                    SurveyTypeTemplate.template_id == TelnyxWhatsappTemplate.id,
                )
                .where(SurveyTypeTemplate.survey_type_id == st.id)
                .order_by(TelnyxWhatsappTemplate.active_for_survey.desc(), TelnyxWhatsappTemplate.id.asc())
            ).scalars()
        )
        orphans = list(
            db.execute(
                select(TelnyxWhatsappTemplate).where(
                    TelnyxWhatsappTemplate.survey_type_id == st.id
                )
            ).scalars()
        )
        seen = {int(r.id) for r in rows}
        for o in orphans:
            if int(o.id) not in seen:
                rows.append(o)

        if kind == "welcome":
            targets: list[tuple[TelnyxWhatsappTemplate, str]] = []
            for row in rows:
                if not row.active_for_survey:
                    continue
                privacy = resolve_row_privacy_mode(row)
                variant = "anonymous" if privacy == PRIVACY_MODE_ON else "named"
                name = was_system_template_name("welcome", privacy_mode=privacy, language=row.language)
                targets.append((row, name))
        else:
            active = [r for r in rows if r.active_for_survey]
            pool = active or rows[:1]
            name = was_system_template_name(kind, language=pool[0].language if pool else "en_GB")
            targets = [(r, name) for r in pool]

        for row, target in targets:
            current = str(row.name or "").strip().lower()
            entry = {
                "id": row.id,
                "kind": kind,
                "old_name": row.name,
                "new_name": target,
                "active": bool(row.active_for_survey),
            }
            if current == target:
                report["already_named"] += 1
            elif target in used_names and current != target:
                # Second welcome variant — should not collide; bump seq if needed.
                for seq in range(2, 10):
                    alt = was_system_template_name(
                        kind,
                        privacy_mode=resolve_row_privacy_mode(row),
                        seq=seq,
                        language=row.language,
                    )
                    if alt not in used_names:
                        target = alt
                        entry["new_name"] = target
                        break
            if current != target:
                used_names.add(target)
                report["system"]["renames"].append(entry)
                report["renames"].append({**entry, "industry": SYSTEM_SURVEY_INDUSTRY_SLUG})
                if apply:
                    row = SurveyWhatsappTemplateService.rename_for_meta_sync(db, row, target)

            cat = str(row.category or "").upper()
            if cat != "UTILITY":
                report["utility_category_fixes"].append(
                    {"id": row.id, "name": row.name, "old_category": row.category, "kind": kind}
                )
                if apply:
                    row.category = "UTILITY"
                    row.local_sync_status = SYNC_LOCAL_CHANGES
                    db.add(row)

            issues = _lint_row(row, employee=False, system=True)
            if issues:
                fail = {"id": row.id, "name": row.name, "kind": kind, "issues": issues[:5]}
                report["system"]["lint_failures"].append(fail)
                report["lint_failures"].append({**fail, "industry": SYSTEM_SURVEY_INDUSTRY_SLUG})

    print(
        f"system: renames={len(report['system']['renames'])} "
        f"lint={len(report['system']['lint_failures'])}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Rename all WA Survey templates to was_*")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        print("Pass --dry-run or --apply", file=sys.stderr)
        return 1

    report: dict = {
        "at": datetime.now(timezone.utc).isoformat(),
        "dry_run": bool(args.dry_run),
        "renames": [],
        "already_named": 0,
        "utility_category_fixes": [],
        "lint_failures": [],
        "industries": {},
        "system": {"renames": [], "lint_failures": []},
        "skipped_industries": [],
    }

    db = get_sessionmaker()()
    try:
        _rename_industry_pass(db, apply=args.apply, report=report)
        _rename_system_pass(db, apply=args.apply, report=report)

        if args.apply:
            db.commit()

        # Post-check: any catalog/system rows still on legacy names?
        legacy_count = db.execute(
            select(TelnyxWhatsappTemplate)
            .join(SurveyType, SurveyType.id == TelnyxWhatsappTemplate.survey_type_id)
            .join(Industry, Industry.id == SurveyType.industry_id)
            .where(
                Industry.slug.in_([i["slug"] for i in INDUSTRY_CATALOG] + [SYSTEM_SURVEY_INDUSTRY_SLUG]),
                TelnyxWhatsappTemplate.active_for_survey.is_(True),
                ~TelnyxWhatsappTemplate.name.like("was_%"),
            )
        ).scalars().all()
        report["legacy_active_remaining"] = [
            {"id": r.id, "name": r.name} for r in legacy_count[:20]
        ]
        report["legacy_active_count"] = len(legacy_count)

        marketing_count = db.execute(
            select(TelnyxWhatsappTemplate)
            .join(SurveyType, SurveyType.id == TelnyxWhatsappTemplate.survey_type_id)
            .join(Industry, Industry.id == SurveyType.industry_id)
            .where(
                Industry.slug.in_([i["slug"] for i in INDUSTRY_CATALOG] + [SYSTEM_SURVEY_INDUSTRY_SLUG]),
                TelnyxWhatsappTemplate.category == "MARKETING",
            )
        ).scalars().all()
        report["marketing_remaining"] = [{"id": r.id, "name": r.name} for r in marketing_count[:20]]
        report["marketing_count"] = len(marketing_count)

        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = REPORT_DIR / f"was-rename-{stamp}.json"
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

        print(f"renames={len(report['renames'])}")
        print(f"already_named={report['already_named']}")
        print(f"utility_fixes={len(report['utility_category_fixes'])}")
        print(f"lint_failures={len(report['lint_failures'])}")
        print(f"legacy_active_remaining={report['legacy_active_count']}")
        print(f"marketing_remaining={report['marketing_count']}")
        print(f"report={out_path}")
        ok = (
            report["legacy_active_count"] == 0
            and report["marketing_count"] == 0
            and len(report["lint_failures"]) == 0
        )
        return 0 if ok or args.dry_run else 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
