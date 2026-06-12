"""Import Customer Feedback WhatsApp templates from english-templates.md."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackIndustry, FeedbackSurveyType, FeedbackWaTemplate

INDUSTRY_HEADINGS: dict[str, str] = {
    "RESTAURANTS & CAFES": "restaurant",
    "RETAIL SHOPS": "retail",
    "SALONS & SPAS": "salon",
    "HOTELS & HOSPITALITY": "hotel",
    "FITNESS & GYMS": "fitness",
    "EVENTS & ENTERTAINMENT": "events",
    "OTHERS (GENERAL SERVICES)": "others",
    "OTHERS": "others",
}

SYSTEM_TEMPLATES: list[dict[str, Any]] = [
    {
        "template_key": "open_question",
        "step_role": "final_feedback_text",
        "body_text": "✍️ Is there anything else you'd like to tell us about your experience today?",
        "buttons": [],
        "meta_category": "utility",
    },
    {
        "template_key": "marketing_opt_in",
        "step_role": "marketing_opt_in",
        "body_text": "📬 Would you like to hear about offers, events and news from us?",
        "buttons": ["Yes, please", "No thanks"],
        "meta_category": "marketing",
    },
    {
        "template_key": "thank_you",
        "step_role": "thank_you",
        "body_text": "🙏 Thank you — your feedback helps us improve. We really appreciate your time today.",
        "buttons": [],
        "meta_category": "utility",
    },
    {
        "template_key": "tell_us_more",
        "step_role": "tell_us_more",
        "body_text": "We're sorry to hear that. Could you tell us a bit more about what went wrong?",
        "buttons": [],
        "meta_category": "utility",
    },
]


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")
    return base[:60] or "template"


def _infer_step_role(buttons: list[str]) -> str:
    joined = " ".join(buttons).lower()
    if any(word in joined for word in ("excellent", "good", "poor", "rating")):
        return "rating"
    if any(word in joined for word in ("yes", "no", "maybe", "definitely", "unlikely")):
        return "yes_no"
    return "abc_choice"


def _default_md_path() -> Path:
    return Path(__file__).resolve().parents[2] / "seed-data" / "customer-feedback" / "english-templates.md"


def parse_templates_md(text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    current_industry: str | None = None
    current_index = 0
    for line in text.splitlines():
        heading = line.strip()
        if heading.startswith("## ") and not heading.startswith("###"):
            title = heading[3:].strip().upper()
            current_industry = INDUSTRY_HEADINGS.get(title)
            current_index = 0
            continue
        match = re.match(r"^\*\*(\d+)\s*–\s*(.+?)\*\*$", line.strip())
        if match:
            current_index = int(match.group(1))
            items.append(
                {
                    "industry_slug": current_industry,
                    "index": current_index,
                    "name": match.group(2).strip(),
                    "body": "",
                    "buttons": [],
                }
            )
            continue
        if not items:
            continue
        if line.strip().lower().startswith("body:"):
            items[-1]["body"] = line.split(":", 1)[1].strip()
        elif line.strip().lower().startswith("buttons:"):
            raw = line.split(":", 1)[1].strip()
            items[-1]["buttons"] = [part.strip() for part in raw.split("|") if part.strip()]
    return [item for item in items if item.get("industry_slug") and item.get("body")]


class FeedbackTemplateImportService:
    @staticmethod
    def import_from_md(db: Session, *, md_path: Path | None = None, replace_existing: bool = False) -> dict[str, Any]:
        path = md_path or _default_md_path()
        if not path.exists():
            raise ValueError(f"Template file not found: {path}")
        parsed = parse_templates_md(path.read_text(encoding="utf-8"))
        now = datetime.utcnow()
        imported = 0
        skipped = 0

        if replace_existing:
            for row in db.execute(select(FeedbackWaTemplate)).scalars().all():
                db.delete(row)

        industries = {row.slug: row for row in db.execute(select(FeedbackIndustry)).scalars().all()}

        for item in parsed:
            industry = industries.get(item["industry_slug"])
            if industry is None:
                skipped += 1
                continue
            survey_type = db.execute(
                select(FeedbackSurveyType)
                .where(
                    FeedbackSurveyType.industry_id == industry.id,
                    FeedbackSurveyType.sort_order == item["index"] * 10,
                )
                .limit(1)
            ).scalar_one_or_none()
            if survey_type is None:
                skipped += 1
                continue
            template_key = survey_type.slug
            existing = db.execute(
                select(FeedbackWaTemplate).where(FeedbackWaTemplate.survey_type_id == survey_type.id).limit(1)
            ).scalar_one_or_none()
            buttons = item["buttons"]
            if existing and not replace_existing:
                existing.body_text = item["body"]
                existing.buttons_json = json.dumps(buttons)
                existing.step_role = _infer_step_role(buttons)
                existing.updated_at = now
                db.add(existing)
            else:
                db.add(
                    FeedbackWaTemplate(
                        id=str(uuid.uuid4()),
                        industry_id=industry.id,
                        survey_type_id=survey_type.id,
                        step_order=1,
                        template_key=template_key,
                        body_text=item["body"],
                        buttons_json=json.dumps(buttons),
                        step_role=_infer_step_role(buttons),
                        language="en_GB",
                        meta_category="utility",
                        telnyx_sync_status="draft",
                        created_at=now,
                        updated_at=now,
                    )
                )
            imported += 1

        for idx, tpl in enumerate(SYSTEM_TEMPLATES, start=1):
            existing = db.execute(
                select(FeedbackWaTemplate).where(FeedbackWaTemplate.template_key == tpl["template_key"]).limit(1)
            ).scalar_one_or_none()
            payload = {
                "body_text": tpl["body_text"],
                "buttons_json": json.dumps(tpl.get("buttons") or []),
                "step_role": tpl["step_role"],
                "meta_category": tpl.get("meta_category") or "utility",
                "step_order": idx,
                "updated_at": now,
            }
            if existing:
                for key, value in payload.items():
                    setattr(existing, key, value)
                db.add(existing)
            else:
                db.add(
                    FeedbackWaTemplate(
                        id=str(uuid.uuid4()),
                        step_order=idx,
                        template_key=tpl["template_key"],
                        body_text=tpl["body_text"],
                        buttons_json=json.dumps(tpl.get("buttons") or []),
                        step_role=tpl["step_role"],
                        language="en_GB",
                        meta_category=tpl.get("meta_category") or "utility",
                        telnyx_sync_status="draft",
                        created_at=now,
                        updated_at=now,
                    )
                )
            imported += 1

        db.commit()
        return {"ok": True, "imported": imported, "skipped": skipped, "path": str(path)}
