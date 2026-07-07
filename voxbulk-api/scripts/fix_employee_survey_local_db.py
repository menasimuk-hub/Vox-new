#!/usr/bin/env python3
"""Fix Employee Survey templates in local DB only (no Meta push).

Usage:
  python scripts/fix_employee_survey_local_db.py --dry-run
  python scripts/fix_employee_survey_local_db.py --apply
"""
from __future__ import annotations

import argparse
import json
import re
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
    SurveyWhatsappTemplateService,
    _body_preview,
    _buttons_from_components,
    _dumps,
    _effective_components,
    _loads,
    _normalize_draft_components,
)
from app.services.wa_template_utility_lint import clamp_utility_button_labels, lint_utility_template

MD_PATH = ROOT / "seed-data" / "wa-survey" / "employee-experience.md"
REPORT_DIR = ROOT / "seed-data" / "wa-survey" / "migration-reports"
INDUSTRY_SLUG = "employee_survey"

_EXTRA_TOPIC_BUTTONS: dict[str, list[str]] = {
    "facility access comfort": ["Very easy", "Comfortable", "Difficult"],
    "hand-off wait time": ["Very short", "Acceptable", "Too long"],
    "information clarity": ["Very clear", "Clear", "Unclear"],
    "issue resolution rating": ["Very satisfied", "Satisfied", "Unsatisfied"],
    "overall experience today": ["Exceeded", "Met expectations", "Below expectations"],
}


def _best_first_button_labels(options: list[str]) -> list[str]:
    """Best/highest rating first, worst/lowest last (WhatsApp shows button 1 at top)."""
    from app.services.survey_wa_flow_constants import LOW_RATING_LABELS, order_scale_labels

    labels = [str(o).strip() for o in options if str(o).strip()][:3]
    if len(labels) < 2:
        return labels
    ordered = order_scale_labels(labels, step_role="rating")
    if ordered != labels:
        return ordered
    first = labels[0].lower()
    last = labels[-1].lower()
    low_first = (
        first in LOW_RATING_LABELS
        or first.startswith(("not ", "no", "rare", "poor", "dissat", "un", "below", "too long"))
        or "difficult" in first
        or "unclear" in first
        or "overwhelm" in first
    )
    high_last = last not in LOW_RATING_LABELS and not last.startswith(("not ", "no "))
    if low_first and high_last:
        return list(reversed(labels))
    return labels


def _find_template_for_type(
    db, industry_id: str
) -> list[tuple[TelnyxWhatsappTemplate, SurveyType]]:
    return list(
        db.execute(
            select(TelnyxWhatsappTemplate, SurveyType)
            .join(SurveyType, SurveyType.id == TelnyxWhatsappTemplate.survey_type_id)
            .where(SurveyType.industry_id == industry_id)
            .order_by(SurveyType.name)
        ).all()
    )


def _topic_slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(name or "").strip().lower())
    return s.strip("_")[:48] or "topic"


def _was_name(topic_name: str, *, seq: int = 1, lang: str = "en") -> str:
    return f"was_employee_{_topic_slug(topic_name)}_{seq:03d}_{lang}"


def _lang_suffix(language: str | None) -> str:
    lang = str(language or "en_GB").strip().lower().replace("-", "_")
    if lang.startswith("ar"):
        return "ar"
    return "en"


def _is_marketing_row(row: TelnyxWhatsappTemplate) -> bool:
    return str(row.category or "").upper() == "MARKETING"


def _md_by_topic(pack) -> dict[str, MdSurveyQuestion]:
    out: dict[str, MdSurveyQuestion] = {}
    for q in pack.questions:
        out[q.name.strip().lower()] = q
    return out


def _update_buttons_only(row: TelnyxWhatsappTemplate, options: list[str]) -> bool:
    comps = _loads(row.draft_components_json) or _loads(row.components_json) or []
    if not isinstance(comps, list) or not comps:
        return False
    labels = clamp_utility_button_labels(_best_first_button_labels(options))
    if len(labels) < 2:
        return False
    changed = False
    new_comps: list[dict] = []
    for comp in comps:
        if not isinstance(comp, dict):
            new_comps.append(comp)
            continue
        if str(comp.get("type") or "").upper() == "BUTTONS":
            old_btns = comp.get("buttons") or []
            old_texts = [str(b.get("text") or "") for b in old_btns if isinstance(b, dict)]
            if old_texts != labels:
                changed = True
            new_comps.append(
                {
                    "type": "BUTTONS",
                    "buttons": [{"type": "QUICK_REPLY", "text": label} for label in labels],
                }
            )
        else:
            new_comps.append(comp)
    if not changed:
        return False
    normalized = _normalize_draft_components(new_comps, step_role="rating")
    row.draft_components_json = _dumps(normalized)
    row.body_preview = _body_preview(normalized)
    return True


def _full_update_from_md(row: TelnyxWhatsappTemplate, question: MdSurveyQuestion) -> None:
    options = clamp_utility_button_labels(_best_first_button_labels(question.options))
    components = _build_abc_choice_components(body=question.body, options=options)
    normalized = _normalize_draft_components(components, step_role="rating")
    row.draft_components_json = _dumps(normalized)
    row.body_preview = _body_preview(normalized)
    row.customer_description = question.wizard_description or question.body
    row.category = "UTILITY"
    row.local_sync_status = SYNC_LOCAL_CHANGES


def _button_label_strings(components_or_row) -> list[str]:
    if hasattr(components_or_row, "draft_components_json"):
        comps = _effective_components(components_or_row)
    else:
        comps = components_or_row
    raw = _buttons_from_components(comps)
    out: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(str(item.get("label") or item.get("text") or "").strip())
        else:
            out.append(str(item or "").strip())
    return [x for x in out if x]


def _lint_row(row: TelnyxWhatsappTemplate) -> list[str]:
    body = _body_from_components(_effective_components(row)) or row.body_preview or ""
    buttons = _button_label_strings(row)
    result = lint_utility_template(
        body=body,
        buttons=buttons,
        language=row.language,
        meta_category="utility",
        require_transaction_anchor=False,
    )
    return [f"{i.field}: {i.message}" for i in result.issues]


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix employee_survey templates locally")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        print("Pass --dry-run or --apply", file=sys.stderr)
        return 1

    if not MD_PATH.is_file():
        print(f"Missing {MD_PATH}", file=sys.stderr)
        return 1

    pack = parse_md_survey_pack(MD_PATH.read_text(encoding="utf-8"), source_name=str(MD_PATH))
    md_map = _md_by_topic(pack)
    report: dict = {
        "at": datetime.now(timezone.utc).isoformat(),
        "industry_slug": INDUSTRY_SLUG,
        "dry_run": bool(args.dry_run),
        "marketing_fixes": [],
        "button_fixes": [],
        "renames": [],
        "lint_failures": [],
        "skipped": [],
    }

    db = get_sessionmaker()()
    try:
        industry = db.execute(select(Industry).where(Industry.slug == INDUSTRY_SLUG)).scalar_one_or_none()
        if industry is None:
            print(f"Industry {INDUSTRY_SLUG!r} not found", file=sys.stderr)
            return 1

        pairs = _find_template_for_type(db, industry.id)
        report["template_rows"] = len(pairs)

        for row, st in pairs:
            q = md_map.get(str(st.name or "").strip().lower())
            extra_buttons = _EXTRA_TOPIC_BUTTONS.get(str(st.name or "").strip().lower())

            entry_base = {
                "id": row.id,
                "survey_type": st.name,
                "old_name": row.name,
                "old_category": row.category,
            }

            if _is_marketing_row(row) and q is not None:
                old_body = _body_from_components(_effective_components(row)) or row.body_preview
                if args.apply:
                    _full_update_from_md(row, q)
                    row.step_role = row.step_role or "abc_choice"
                    db.add(row)
                report["marketing_fixes"].append(
                    {
                        **entry_base,
                        "old_body": (old_body or "")[:200],
                        "new_body": q.body[:200],
                        "new_buttons": q.options,
                    }
                )
            elif q is not None:
                old_btns = _button_label_strings(row)
                target_btns = clamp_utility_button_labels(_best_first_button_labels(q.options))
                body_text = (_body_from_components(_effective_components(row)) or "").lower()
                needs_body = "recent visit" in body_text or "following your visit" in body_text
                if args.apply:
                    if needs_body:
                        _full_update_from_md(row, q)
                    elif old_btns != target_btns:
                        _update_buttons_only(row, q.options)
                    row.category = "UTILITY"
                    row.local_sync_status = SYNC_LOCAL_CHANGES
                    row.step_role = row.step_role or "abc_choice"
                    db.add(row)
                if old_btns != target_btns or needs_body:
                    report["button_fixes"].append(
                        {
                            **entry_base,
                            "old_buttons": old_btns,
                            "new_buttons": target_btns,
                            "body_rewritten": needs_body,
                        }
                    )
            elif extra_buttons is not None:
                old_btns = _button_label_strings(row)
                target_btns = clamp_utility_button_labels(_best_first_button_labels(extra_buttons))
                if args.apply:
                    if old_btns != target_btns:
                        _update_buttons_only(row, extra_buttons)
                    row.category = "UTILITY"
                    row.local_sync_status = SYNC_LOCAL_CHANGES
                    row.step_role = row.step_role or "abc_choice"
                    db.add(row)
                if old_btns != target_btns:
                    report["button_fixes"].append(
                        {**entry_base, "old_buttons": old_btns, "new_buttons": target_btns}
                    )
            else:
                if args.apply:
                    row.category = "UTILITY"
                    row.local_sync_status = SYNC_LOCAL_CHANGES
                    db.add(row)
                report["skipped"].append({"survey_type": st.name, "reason": "no_md_block"})

            new_name = _was_name(st.name, lang=_lang_suffix(row.language))
            if str(row.name or "").strip().lower() != new_name:
                report["renames"].append({**entry_base, "new_name": new_name})
                if args.apply:
                    row = SurveyWhatsappTemplateService.rename_for_meta_sync(db, row, new_name)

            issues = _lint_row(row)
            if issues:
                report["lint_failures"].append(
                    {"id": row.id, "name": row.name, "survey_type": st.name, "issues": issues[:5]}
                )

        if args.apply:
            db.commit()

        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = REPORT_DIR / f"employee-fix-{stamp}.json"
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

        print(f"template_rows={report.get('template_rows', 0)}")
        print(f"marketing_fixes={len(report['marketing_fixes'])}")
        print(f"button_fixes={len(report['button_fixes'])}")
        print(f"renames={len(report['renames'])}")
        print(f"lint_failures={len(report['lint_failures'])}")
        print(f"skipped={len(report['skipped'])}")
        print(f"report={out_path}")
        return 0 if not report["lint_failures"] else 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
