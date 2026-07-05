"""Import Customer Feedback templates from multi-language Markdown."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackIndustry, FeedbackSurveyType, FeedbackWaTemplate
from app.services.customer_feedback.feedback_telnyx_push_service import (
    english_anchor_template,
    feedback_meta_template_name,
)
from app.services.customer_feedback.seed_service import FeedbackSeedService, _slugify
from app.services.meta_whatsapp_template_service import MetaWhatsappTemplateService
from app.services.wa_md_template_import_service import (
    build_dry_run_plan,
    infer_step_role,
    parse_md_pack,
)


class FeedbackMdImportError(ValueError):
    pass


def _resolve_industry(
    db: Session,
    *,
    industry_id: str | None = None,
    industry_slug: str | None = None,
    industry_name: str | None = None,
) -> FeedbackIndustry:
    if industry_id:
        row = db.get(FeedbackIndustry, str(industry_id).strip())
        if row is None:
            raise FeedbackMdImportError(f"Industry not found: {industry_id}")
        return row
    slug = str(industry_slug or "").strip().lower()
    if slug:
        row = db.execute(select(FeedbackIndustry).where(FeedbackIndustry.slug == slug).limit(1)).scalar_one_or_none()
        if row is not None:
            return row
    name = str(industry_name or "").strip()
    if name:
        row = db.execute(
            select(FeedbackIndustry).where(FeedbackIndustry.name.ilike(name)).limit(1)
        ).scalar_one_or_none()
        if row is not None:
            return row
    raise FeedbackMdImportError(f"Industry not found for slug={slug!r} name={name!r}")


def _list_industry_templates(db: Session, industry_id: str) -> list[FeedbackWaTemplate]:
    survey_type_ids = select(FeedbackSurveyType.id).where(FeedbackSurveyType.industry_id == industry_id)
    return list(
        db.execute(
            select(FeedbackWaTemplate).where(
                or_(
                    FeedbackWaTemplate.industry_id == industry_id,
                    FeedbackWaTemplate.survey_type_id.in_(survey_type_ids),
                )
            )
        ).scalars().all()
    )


def _collect_meta_names(
    db: Session,
    templates: list[FeedbackWaTemplate],
    *,
    industry_slug: str,
    type_slug_by_id: dict[str, str],
) -> set[str]:
    names: set[str] = set()
    for tpl in templates:
        try:
            anchor = english_anchor_template(db, tpl)
            survey_slug = type_slug_by_id.get(str(tpl.survey_type_id or ""))
            names.add(
                feedback_meta_template_name(
                    tpl,
                    industry_slug=industry_slug,
                    survey_type_slug=survey_slug,
                    name_anchor_id=anchor.id,
                )
            )
        except Exception:
            continue
    return names


def _ensure_feedback_survey_type(
    db: Session,
    *,
    industry: FeedbackIndustry,
    topic_name: str,
    sort_order: int,
    description: str,
    create_missing: bool,
) -> tuple[FeedbackSurveyType | None, bool]:
    slug = _slugify(topic_name)
    row = db.execute(
        select(FeedbackSurveyType).where(
            FeedbackSurveyType.industry_id == industry.id,
            FeedbackSurveyType.slug == slug,
        )
    ).scalar_one_or_none()
    if row is not None:
        changed = False
        if row.name != topic_name:
            row.name = topic_name
            changed = True
        if description and row.description != description:
            row.description = description[:500]
            changed = True
        if changed:
            row.updated_at = datetime.utcnow()
            db.add(row)
        return row, False
    if not create_missing:
        return None, False
    now = datetime.utcnow()
    row = FeedbackSurveyType(
        id=str(uuid.uuid4()),
        industry_id=industry.id,
        slug=slug,
        name=topic_name,
        description=description[:500] if description else None,
        sort_order=sort_order,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return row, True


def _delete_industry_templates(db: Session, industry: FeedbackIndustry) -> dict[str, Any]:
    templates = _list_industry_templates(db, industry.id)
    types = list(
        db.execute(select(FeedbackSurveyType).where(FeedbackSurveyType.industry_id == industry.id)).scalars().all()
    )
    type_slug_by_id = {t.id: t.slug for t in types}
    meta_names = _collect_meta_names(
        db, templates, industry_slug=str(industry.slug or ""), type_slug_by_id=type_slug_by_id
    )
    warnings: list[str] = []
    for name in sorted(meta_names):
        try:
            MetaWhatsappTemplateService.delete_message_template(db, name=name)
        except Exception as exc:
            warnings.append(f"{name}: Meta delete failed ({exc})")

    deleted = 0
    for tpl in templates:
        db.delete(tpl)
        deleted += 1
    db.flush()
    return {
        "deleted_templates": deleted,
        "deleted_meta_names": len(meta_names),
        "warnings": warnings,
    }


class FeedbackMdImportService:
    @staticmethod
    def parse_text(text: str, *, source_name: str = ""):
        return parse_md_pack(text, source_name=source_name)

    @staticmethod
    def dry_run_from_text(
        db: Session,
        text: str,
        *,
        industry_id: str | None = None,
        industry_slug: str | None = None,
        industry_name: str | None = None,
        replace: bool = True,
        create_missing_topics: bool = True,
        min_langs: int = 19,
        source_name: str = "",
    ) -> dict[str, Any]:
        FeedbackSeedService.ensure_seeded(db)
        industry = _resolve_industry(
            db,
            industry_id=industry_id,
            industry_slug=industry_slug,
            industry_name=industry_name,
        )
        pack = parse_md_pack(text, source_name=source_name)
        existing = _list_industry_templates(db, industry.id)
        types = list(
            db.execute(select(FeedbackSurveyType).where(FeedbackSurveyType.industry_id == industry.id)).scalars().all()
        )
        type_slug_by_id = {t.id: t.slug for t in types}
        meta_names = _collect_meta_names(
            db, existing, industry_slug=str(industry.slug or ""), type_slug_by_id=type_slug_by_id
        )
        plan = build_dry_run_plan(
            pack,
            industry_name=industry.name,
            industry_slug=industry.slug,
            existing_template_count=len(existing),
            existing_meta_name_count=len(meta_names),
            replace=replace,
            create_missing_topics=create_missing_topics,
            existing_topic_slugs={t.slug for t in types},
            min_langs=min_langs,
        )
        plan["industry_id"] = industry.id
        return plan

    @staticmethod
    def import_from_text(
        db: Session,
        text: str,
        *,
        industry_id: str | None = None,
        industry_slug: str | None = None,
        industry_name: str | None = None,
        replace: bool = True,
        create_missing_topics: bool = True,
        dry_run: bool = False,
        min_langs: int = 19,
        source_name: str = "",
    ) -> dict[str, Any]:
        if dry_run:
            return FeedbackMdImportService.dry_run_from_text(
                db,
                text,
                industry_id=industry_id,
                industry_slug=industry_slug,
                industry_name=industry_name,
                replace=replace,
                create_missing_topics=create_missing_topics,
                min_langs=min_langs,
                source_name=source_name,
            )

        preview = FeedbackMdImportService.dry_run_from_text(
            db,
            text,
            industry_id=industry_id,
            industry_slug=industry_slug,
            industry_name=industry_name,
            replace=replace,
            create_missing_topics=create_missing_topics,
            min_langs=min_langs,
            source_name=source_name,
        )
        if not preview.get("ok"):
            raise FeedbackMdImportError(
                "; ".join(preview.get("errors") or []) or "Dry-run validation failed"
            )

        FeedbackSeedService.ensure_seeded(db)
        industry = _resolve_industry(
            db,
            industry_id=industry_id,
            industry_slug=industry_slug,
            industry_name=industry_name,
        )
        pack = parse_md_pack(text, source_name=source_name)
        now = datetime.utcnow()

        delete_summary: dict[str, Any] = {}
        if replace:
            delete_summary = _delete_industry_templates(db, industry)

        types_created = 0
        types_updated = 0
        templates_created = 0
        rows_out: list[dict[str, Any]] = []

        for topic in pack.topics:
            en = next(
                (v for v in topic.variants if v.language_code.startswith("en")),
                topic.variants[0] if topic.variants else None,
            )
            desc = en.body if en else ""
            survey_type, created = _ensure_feedback_survey_type(
                db,
                industry=industry,
                topic_name=topic.name,
                sort_order=topic.index * 10,
                description=desc,
                create_missing=create_missing_topics,
            )
            if survey_type is None:
                raise FeedbackMdImportError(f"Survey topic not found and create_missing=false: {topic.name}")
            if created:
                types_created += 1
            else:
                types_updated += 1

            for variant in topic.variants:
                buttons = variant.buttons
                role = infer_step_role(buttons)
                db.add(
                    FeedbackWaTemplate(
                        id=str(uuid.uuid4()),
                        industry_id=industry.id,
                        survey_type_id=survey_type.id,
                        step_order=1,
                        template_key=survey_type.slug,
                        body_text=variant.body,
                        buttons_json=json.dumps(buttons),
                        step_role=role,
                        language=variant.language_code,
                        meta_category="utility",
                        telnyx_sync_status="draft",
                        is_active=True,
                        created_at=now,
                        updated_at=now,
                    )
                )
                templates_created += 1
                rows_out.append(
                    {
                        "survey_type_id": survey_type.id,
                        "survey_type_name": survey_type.name,
                        "language": variant.language_code,
                        "buttons": buttons,
                        "body_preview": variant.body[:80],
                    }
                )

        db.commit()
        return {
            "ok": True,
            "dry_run": False,
            "industry_id": industry.id,
            "industry_slug": industry.slug,
            "industry_name": industry.name,
            "topics_in_file": len(pack.topics),
            "survey_types_created": types_created,
            "survey_types_updated": types_updated,
            "templates_created": templates_created,
            "deleted_templates": delete_summary.get("deleted_templates", 0),
            "deleted_meta_names": delete_summary.get("deleted_meta_names", 0),
            "warnings": (delete_summary.get("warnings") or []) + preview.get("warnings", []),
            "plan_steps": preview.get("plan_steps", []),
            "rows": rows_out[:50],
            "message": (
                f"Imported {templates_created} template(s) across {len(pack.topics)} topic(s) "
                f"for {industry.name}. Sync to Meta when ready."
            ),
        }

    @staticmethod
    def import_from_file(db: Session, path: Path, **kwargs: Any) -> dict[str, Any]:
        if not path.exists():
            raise FeedbackMdImportError(f"File not found: {path}")
        text = path.read_text(encoding="utf-8")
        return FeedbackMdImportService.import_from_text(db, text, source_name=path.name, **kwargs)
