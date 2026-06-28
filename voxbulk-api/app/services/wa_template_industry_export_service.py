"""Resolve Meta WA template names to industry + survey type for export reports."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackIndustry, FeedbackSurveyType, FeedbackWaTemplate
from app.models.industry import Industry
from app.models.survey_type import SurveyType
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.customer_feedback.feedback_telnyx_push_service import (
    ENGLISH_TEMPLATE_LANGUAGES,
    feedback_meta_template_name,
)
from app.services.survey_type_template_service import template_name_survey_slug

_SURVEY_PACK_SUFFIX_RE = re.compile(r"^(voxbulk_survey_.+)_(abc|utu)_([a-f0-9]{6})$", re.I)
_CF_ANCHOR_RE = re.compile(r"^[a-f0-9]{6,8}$", re.I)


@dataclass
class ExportResolverContext:
    survey_slugs: list[str] = field(default_factory=list)
    survey_by_slug: dict[str, SurveyType] = field(default_factory=dict)
    industry_by_id: dict[str, Industry] = field(default_factory=dict)
    feedback_industry_by_slug: dict[str, FeedbackIndustry] = field(default_factory=dict)
    feedback_survey_by_slug: dict[tuple[str, str], FeedbackSurveyType] = field(default_factory=dict)
    feedback_survey_slugs_by_industry: dict[str, list[str]] = field(default_factory=dict)
    cf_meta_index: dict[str, dict[str, Any]] = field(default_factory=dict)


def build_export_resolver_context(db: Session) -> ExportResolverContext:
    ctx = ExportResolverContext()

    industries = list(db.execute(select(Industry)).scalars())
    ctx.industry_by_id = {row.id: row for row in industries}

    survey_types = list(db.execute(select(SurveyType)).scalars())
    ctx.survey_slugs = [st.slug for st in survey_types]
    ctx.survey_by_slug = {st.slug: st for st in survey_types}

    fb_industries = list(db.execute(select(FeedbackIndustry)).scalars())
    ctx.feedback_industry_by_slug = {row.slug: row for row in fb_industries}

    fb_survey_types = list(db.execute(select(FeedbackSurveyType)).scalars())
    for row in fb_survey_types:
        fb_ind = next((i for i in fb_industries if i.id == row.industry_id), None)
        if fb_ind is None:
            continue
        ctx.feedback_survey_by_slug[(fb_ind.slug, row.slug)] = row
        ctx.feedback_survey_slugs_by_industry.setdefault(fb_ind.slug, []).append(row.slug)

    feedback_templates = list(
        db.execute(
            select(FeedbackWaTemplate).where(FeedbackWaTemplate.language.in_(ENGLISH_TEMPLATE_LANGUAGES))
        ).scalars()
    )
    for tpl in feedback_templates:
        industry_slug = None
        survey_type_slug = None
        industry_name = ""
        survey_type_name = ""
        if tpl.industry_id:
            fb_ind = db.get(FeedbackIndustry, tpl.industry_id)
            if fb_ind:
                industry_slug = fb_ind.slug
                industry_name = fb_ind.name
        if tpl.survey_type_id:
            fb_st = db.get(FeedbackSurveyType, tpl.survey_type_id)
            if fb_st:
                survey_type_slug = fb_st.slug
                survey_type_name = fb_st.name
                if not industry_slug:
                    fb_ind = db.get(FeedbackIndustry, fb_st.industry_id)
                    if fb_ind:
                        industry_slug = fb_ind.slug
                        industry_name = fb_ind.name
        meta = feedback_meta_template_name(
            tpl,
            industry_slug=industry_slug,
            survey_type_slug=survey_type_slug,
            name_anchor_id=tpl.id,
        ).lower()
        ctx.cf_meta_index[meta] = {
            "product_line": "Customer Feedback",
            "industry_slug": industry_slug or "",
            "industry_name": industry_name,
            "survey_type_slug": survey_type_slug or "",
            "survey_type_name": survey_type_name,
            "template_key": tpl.template_key,
            "telnyx_sync_status": tpl.telnyx_sync_status,
            "source": "feedback_db",
            "feedback_template_id": tpl.id,
            "platform_template_id": None,
            "feedback_survey_type_id": tpl.survey_type_id,
            "platform_survey_type_id": None,
        }

    return ctx


def load_platform_template_index(db: Session, names: list[str]) -> dict[str, TelnyxWhatsappTemplate]:
    cleaned = [str(n or "").strip() for n in names if str(n or "").strip()]
    if not cleaned:
        return {}
    rows = list(
        db.execute(
            select(TelnyxWhatsappTemplate).where(
                func.lower(TelnyxWhatsappTemplate.name).in_([n.lower() for n in cleaned])
            )
        ).scalars()
    )
    return {row.name.lower(): row for row in rows}


def _survey_name_variant(name: str) -> str:
    match = _SURVEY_PACK_SUFFIX_RE.match(str(name or "").strip())
    if match:
        return match.group(2).lower()
    lower = str(name or "").strip().lower()
    legacy = re.search(r"_(standard|anonymous)$", lower)
    if legacy:
        return legacy.group(1)
    return ""


def parse_feedback_template_name(name: str, ctx: ExportResolverContext) -> dict[str, Any] | None:
    lower = str(name or "").strip().lower()
    if not lower.startswith("voxbulk_cf_"):
        return None
    if lower in ctx.cf_meta_index:
        return dict(ctx.cf_meta_index[lower])

    rest = lower[len("voxbulk_cf_") :]
    for ind_slug in sorted(ctx.feedback_survey_slugs_by_industry.keys(), key=len, reverse=True):
        prefix = f"{ind_slug}_"
        if not rest.startswith(prefix):
            continue
        tail = rest[len(prefix) :]
        for st_slug in sorted(ctx.feedback_survey_slugs_by_industry.get(ind_slug, []), key=len, reverse=True):
            st_prefix = f"{st_slug}_"
            if not tail.startswith(st_prefix):
                continue
            remainder = tail[len(st_prefix) :]
            anchor_parts = remainder.rsplit("_", 1)
            if len(anchor_parts) != 2 or not _CF_ANCHOR_RE.match(anchor_parts[1]):
                continue
            template_key = anchor_parts[0] or st_slug
            fb_ind = ctx.feedback_industry_by_slug.get(ind_slug)
            fb_st = ctx.feedback_survey_by_slug.get((ind_slug, st_slug))
            return {
                "product_line": "Customer Feedback",
                "industry_slug": ind_slug,
                "industry_name": fb_ind.name if fb_ind else ind_slug.replace("_", " ").title(),
                "survey_type_slug": st_slug,
                "survey_type_name": fb_st.name if fb_st else st_slug.replace("_", " ").title(),
                "template_key": template_key,
                "telnyx_sync_status": "",
                "source": "parsed_cf_name",
                "feedback_survey_type_id": fb_st.id if fb_st else None,
                "platform_survey_type_id": None,
            }
    return {
        "product_line": "Customer Feedback",
        "industry_slug": "",
        "industry_name": "",
        "survey_type_slug": "",
        "survey_type_name": "",
        "template_key": "",
        "telnyx_sync_status": "",
        "source": "unparsed_cf",
        "feedback_survey_type_id": None,
        "platform_survey_type_id": None,
    }


def parse_platform_survey_template_name(name: str, ctx: ExportResolverContext) -> dict[str, Any]:
    lower = str(name or "").strip().lower()
    slug = template_name_survey_slug(lower, known_slugs=ctx.survey_slugs)
    survey_type = ctx.survey_by_slug.get(slug or "")
    industry = ctx.industry_by_id.get(survey_type.industry_id) if survey_type else None
    return {
        "product_line": "Platform WA Survey",
        "industry_slug": industry.slug if industry else "",
        "industry_name": industry.name if industry else "",
        "survey_type_slug": slug or "",
        "survey_type_name": survey_type.name if survey_type else (slug or "").replace("_", " ").title(),
        "template_key": "",
        "telnyx_sync_status": "",
        "source": "parsed_survey_name",
        "feedback_survey_type_id": None,
        "platform_survey_type_id": survey_type.id if survey_type else None,
    }


def resolve_template_export_row(
    name: str,
    *,
    ctx: ExportResolverContext,
    platform_rows: dict[str, TelnyxWhatsappTemplate],
) -> dict[str, Any]:
    raw = str(name or "").strip()
    lower = raw.lower()
    base: dict[str, Any] = {
        "template_name": raw,
        "name_variant": _survey_name_variant(raw),
        "db_found": "no",
        "telnyx_status": "",
        "display_name": "",
        "body_preview": "",
        "source": "",
        "feedback_template_id": None,
        "platform_template_id": None,
        "feedback_survey_type_id": None,
        "platform_survey_type_id": None,
    }

    if lower.startswith("voxbulk_cf_"):
        cf = parse_feedback_template_name(raw, ctx)
        if cf:
            base.update(cf)
            base["telnyx_status"] = cf.get("telnyx_sync_status") or ""
            base["db_found"] = "yes" if cf.get("source") == "feedback_db" else "parsed"
        return base

    row = platform_rows.get(lower)
    if row is not None:
        industry = ctx.industry_by_id.get(row.industry_id) if row.industry_id else None
        survey_type = None
        if row.survey_type_id:
            for st in ctx.survey_by_slug.values():
                if st.id == row.survey_type_id:
                    survey_type = st
                    break
        if survey_type is None:
            slug = template_name_survey_slug(row.name, known_slugs=ctx.survey_slugs)
            survey_type = ctx.survey_by_slug.get(slug or "")
        if industry is None and survey_type:
            industry = ctx.industry_by_id.get(survey_type.industry_id)
        base.update(
            {
                "product_line": "Platform WA Survey",
                "industry_slug": industry.slug if industry else "",
                "industry_name": industry.name if industry else "",
                "survey_type_slug": survey_type.slug if survey_type else "",
                "survey_type_name": survey_type.name if survey_type else "",
                "template_key": row.sales_template_key or "",
                "telnyx_sync_status": row.status or "",
                "telnyx_status": row.status or "",
                "display_name": row.display_name or "",
                "body_preview": (row.body_preview or "")[:200],
                "db_found": "yes",
                "source": "platform_db",
                "feedback_template_id": None,
                "platform_template_id": row.id,
                "feedback_survey_type_id": None,
                "platform_survey_type_id": survey_type.id if survey_type else None,
            }
        )
        return base

    parsed = parse_platform_survey_template_name(raw, ctx)
    base.update(parsed)
    base["db_found"] = "parsed"
    return base


def resolve_template_export_rows(db: Session, names: list[str]) -> list[dict[str, Any]]:
    ctx = build_export_resolver_context(db)
    platform_rows = load_platform_template_index(db, names)
    out: list[dict[str, Any]] = []
    for name in names:
        text = str(name or "").strip()
        if not text:
            continue
        out.append(resolve_template_export_row(text, ctx=ctx, platform_rows=platform_rows))
    return out
