"""Rewrite Customer Feedback WhatsApp templates for Meta UTILITY compliance."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackIndustry, FeedbackWaTemplate
from app.services.customer_feedback.feedback_marketing_policy import is_marketing_wa_template
from app.services.customer_feedback.feedback_telnyx_push_service import (
    FeedbackTelnyxPushError,
    list_feedback_templates_for_industry,
    push_feedback_template_to_telnyx,
)
from app.services.customer_feedback.survey_config_service import ENGLISH_TEMPLATE_LANGUAGES
from app.services.survey_wa_utility_rewrite_service import (
    _extract_leading_emoji,
    _prepend_leading_emoji,
    _rule_based_utility_body,
    rewrite_body_for_utility,
)
from app.services.wa_migration_progress import migration_progress
from app.services.wa_template_utility_lint import assert_utility_template, clamp_utility_button_labels, lint_utility_template

logger = logging.getLogger(__name__)

FEEDBACK_INDUSTRY_SLUGS: tuple[str, ...] = (
    "restaurant",
    "retail",
    "salon",
    "hotel",
    "fitness",
    "events",
    "others",
)


@dataclass
class FeedbackUtilityRewriteResult:
    template_id: str
    template_key: str
    language: str
    ok: bool
    old_body: str
    new_body: str
    message: str
    pushed: bool = False
    lint_ok: bool = True


def _parse_buttons(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def rewrite_feedback_body(
    db: Session,
    *,
    original_body: str,
    buttons: list[str],
    template_key: str,
    use_llm: bool = True,
    llm_provider: str = "openai",
    llm_model: str | None = None,
) -> str:
    if not use_llm:
        return _rule_based_utility_body(original_body, topic_hint=template_key.replace("_", " "))
    return rewrite_body_for_utility(
        db,
        original_body=original_body,
        button_labels=buttons,
        template_name=f"feedback_{template_key}",
        display_name=template_key,
        use_llm=use_llm,
        llm_provider=llm_provider,
        llm_model=llm_model,
    )


def apply_utility_rewrite_to_feedback_row(
    db: Session,
    row: FeedbackWaTemplate,
    *,
    use_llm: bool = True,
    llm_provider: str = "openai",
    llm_model: str | None = None,
    skip_lint: bool = False,
) -> tuple[str, str]:
    if is_marketing_wa_template(row):
        raise ValueError(f"Marketing template excluded from utility migration: {row.template_key}")

    buttons = clamp_utility_button_labels(_parse_buttons(row.buttons_json))
    old_body = str(row.body_text or "").strip()
    if not old_body:
        raise ValueError(f"Missing body_text for {row.template_key}")

    new_body = rewrite_feedback_body(
        db,
        original_body=old_body,
        buttons=buttons,
        template_key=str(row.template_key or ""),
        use_llm=use_llm,
        llm_provider=llm_provider,
        llm_model=llm_model,
    )
    leading_emoji, _ = _extract_leading_emoji(old_body)
    new_body = _prepend_leading_emoji(leading_emoji, new_body)

    if not skip_lint:
        lint = lint_utility_template(
            body=new_body,
            buttons=buttons,
            language=row.language,
            meta_category="utility",
            template_key=row.template_key,
        )
        if not lint.ok:
            msgs = "; ".join(i.message for i in lint.issues)
            raise ValueError(f"Utility lint failed for {row.template_key}: {msgs}")

    row.body_text = new_body
    row.meta_category = "utility"
    row.telnyx_sync_status = "draft"
    db.add(row)
    db.commit()
    db.refresh(row)
    return old_body, new_body


def list_feedback_english_templates_for_industry(db: Session, industry_slug: str) -> list[FeedbackWaTemplate]:
    industry = db.execute(
        select(FeedbackIndustry).where(FeedbackIndustry.slug == str(industry_slug).strip().lower()).limit(1)
    ).scalar_one_or_none()
    if industry is None:
        raise ValueError(f"Feedback industry not found: {industry_slug}")
    ids = {row.id for row in list_feedback_templates_for_industry(db, industry.id)}
    if not ids:
        return []
    rows = db.execute(
        select(FeedbackWaTemplate)
        .where(
            FeedbackWaTemplate.id.in_(ids),
            FeedbackWaTemplate.language.in_(ENGLISH_TEMPLATE_LANGUAGES),
            FeedbackWaTemplate.is_active.is_(True),
        )
        .order_by(FeedbackWaTemplate.step_order, FeedbackWaTemplate.template_key)
    ).scalars().all()
    return [row for row in rows if not is_marketing_wa_template(row)]


def process_feedback_industry(
    db: Session,
    industry_slug: str,
    *,
    dry_run: bool = False,
    save: bool = False,
    push: bool = False,
    languages: list[str] | None = None,
    use_llm: bool = True,
    llm_provider: str = "openai",
) -> list[FeedbackUtilityRewriteResult]:
    results: list[FeedbackUtilityRewriteResult] = []
    rows = list_feedback_english_templates_for_industry(db, industry_slug)
    lang_filter = {str(x).strip().lower() for x in (languages or ["en", "ar"])}
    total = len(rows)
    migration_progress(f"\n>>> Feedback industry: {industry_slug} ({total} EN templates)")

    for index, row in enumerate(rows, start=1):
        template_key = str(row.template_key or "")
        try:
            migration_progress(f"[{index}/{total}] {industry_slug}/{template_key} ({row.language}) …")
            buttons = clamp_utility_button_labels(_parse_buttons(row.buttons_json))
            old_body = str(row.body_text or "").strip()
            if dry_run:
                new_body = rewrite_feedback_body(
                    db,
                    original_body=old_body,
                    buttons=buttons,
                    template_key=str(row.template_key or ""),
                    use_llm=use_llm,
                    llm_provider=llm_provider,
                )
                lint = lint_utility_template(
                    body=new_body,
                    buttons=buttons,
                    language=row.language,
                    meta_category="utility",
                    template_key=row.template_key,
                )
                results.append(
                    FeedbackUtilityRewriteResult(
                        template_id=row.id,
                        template_key=str(row.template_key or ""),
                        language=str(row.language or ""),
                        ok=lint.ok,
                        old_body=old_body,
                        new_body=new_body,
                        message="dry-run",
                        lint_ok=lint.ok,
                    )
                )
                continue

            if not save and not push:
                results.append(
                    FeedbackUtilityRewriteResult(
                        template_id=row.id,
                        template_key=str(row.template_key or ""),
                        language=str(row.language or ""),
                        ok=False,
                        old_body=old_body,
                        new_body="",
                        message="Specify --save or --push",
                        lint_ok=False,
                    )
                )
                continue

            old_body, new_body = apply_utility_rewrite_to_feedback_row(
                db, row, use_llm=use_llm, llm_provider=llm_provider
            )
            pushed = False
            msg = "saved"
            if push and ("en" in lang_filter or str(row.language).lower().startswith("en")):
                assert_utility_template(
                    body=new_body,
                    buttons=buttons,
                    language=row.language,
                    meta_category="utility",
                    template_key=row.template_key,
                )
                push_feedback_template_to_telnyx(db, row)
                pushed = True
                msg = "saved and pushed"
            migration_progress(f"  -> OK {msg}")
            results.append(
                FeedbackUtilityRewriteResult(
                    template_id=row.id,
                    template_key=str(row.template_key or ""),
                    language=str(row.language or ""),
                    ok=True,
                    old_body=old_body,
                    new_body=new_body,
                    message=msg,
                    pushed=pushed,
                )
            )
        except (FeedbackTelnyxPushError, ValueError) as exc:
            migration_progress(f"  -> FAIL {exc}")
            results.append(
                FeedbackUtilityRewriteResult(
                    template_id=row.id,
                    template_key=str(row.template_key or ""),
                    language=str(row.language or ""),
                    ok=False,
                    old_body=str(row.body_text or ""),
                    new_body="",
                    message=str(exc),
                    lint_ok=False,
                )
            )
    return results
