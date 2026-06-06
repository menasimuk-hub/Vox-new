"""Bulk-generate normal WA Survey library templates (one per industry survey type)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.industry import Industry
from app.models.survey_type import SurveyType
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.industry_service import IndustryService, SYSTEM_SURVEY_INDUSTRY_SLUG
from app.services.survey_industry_scope import template_matches_survey_industry
from app.services.survey_step_bank_service import MIDDLE_STEP_ROLES, normalize_step_role
from app.services.survey_system_template_service import SYSTEM_TEMPLATE_KINDS
from app.services.survey_type_template_service import (
    SurveyTypeTemplateService,
    template_belongs_to_survey_type,
)
from app.services.survey_wa_template_pack_service import (
    SurveyWaTemplatePackError,
    SurveyWaTemplatePackService,
)
from app.services.wa_template_privacy import PRIVACY_MODE_OFF

DEFAULT_LIBRARY_STEP_ROLE = "rating"
SYSTEM_STEP_ROLES = frozenset({"start", "completion"})


@dataclass(frozen=True)
class BulkLibraryTarget:
    industry: Industry
    survey_type: SurveyType


@dataclass
class BulkLibraryResult:
    industry_slug: str
    industry_name: str
    survey_type_slug: str
    survey_type_name: str
    status: str
    reason: str
    template_id: int | None = None
    step_role: str | None = None

    def log_line(self) -> str:
        tid = f" template_id={self.template_id}" if self.template_id else ""
        role = f" step_role={self.step_role}" if self.step_role else ""
        return (
            f"[{self.status.upper()}] {self.industry_name} ({self.industry_slug})"
            f" → {self.survey_type_name} ({self.survey_type_slug})"
            f"{role}{tid} — {self.reason}"
        )


class SurveyWaBulkLibraryTemplateService:
    @staticmethod
    def normalize_step_role(raw: str | None) -> str:
        role = normalize_step_role(str(raw or DEFAULT_LIBRARY_STEP_ROLE))
        if role not in MIDDLE_STEP_ROLES:
            raise SurveyWaTemplatePackError(
                f"step_role must be one of: {', '.join(MIDDLE_STEP_ROLES)}"
            )
        return role

    @staticmethod
    def iter_targets(
        db: Session,
        *,
        industry_slug: str | None = None,
        survey_type_slug: str | None = None,
    ) -> Iterator[BulkLibraryTarget]:
        """Yield active, non-system industry + survey type pairs."""
        industry_slug_key = str(industry_slug or "").strip().lower()
        survey_slug_key = str(survey_type_slug or "").strip().lower()

        stmt = (
            select(Industry)
            .where(Industry.is_active.is_(True))
            .where(or_(Industry.is_hidden.is_(False), Industry.is_hidden.is_(None)))
            .where(Industry.slug != SYSTEM_SURVEY_INDUSTRY_SLUG)
            .order_by(Industry.sort_order.asc(), Industry.name.asc())
        )
        if industry_slug_key:
            stmt = stmt.where(Industry.slug == industry_slug_key)

        for industry in db.execute(stmt).scalars():
            if IndustryService.is_slug_tombstoned(db, industry.slug):
                continue

            type_stmt = (
                select(SurveyType)
                .where(SurveyType.industry_id == industry.id)
                .where(SurveyType.is_active.is_(True))
                .where(SurveyType.system_template_kind.is_(None))
                .order_by(SurveyType.sort_order.asc(), SurveyType.name.asc())
            )
            if survey_slug_key:
                type_stmt = type_stmt.where(SurveyType.slug == survey_slug_key)

            for survey_type in db.execute(type_stmt).scalars():
                if survey_type.system_template_kind in SYSTEM_TEMPLATE_KINDS:
                    continue
                yield BulkLibraryTarget(industry=industry, survey_type=survey_type)

    @staticmethod
    def find_existing_library_template(
        db: Session,
        *,
        survey_type: SurveyType,
        step_role: str,
    ) -> TelnyxWhatsappTemplate | None:
        """Duplicate = linked template for this survey type with the same middle step_role."""
        expected_role = normalize_step_role(step_role)
        for mapping in SurveyTypeTemplateService.list_for_survey_type(db, survey_type.id):
            tpl = db.get(TelnyxWhatsappTemplate, mapping.template_id)
            if tpl is None or not tpl.active_for_survey:
                continue
            if not template_belongs_to_survey_type(tpl, survey_type):
                continue
            if not template_matches_survey_industry(tpl, survey_type, mapping=mapping):
                continue
            role = normalize_step_role(str(tpl.step_role or ""))
            if role in SYSTEM_STEP_ROLES:
                continue
            if role == expected_role:
                return tpl
        return None

    @staticmethod
    def process_target(
        db: Session,
        *,
        target: BulkLibraryTarget,
        step_role: str,
        dry_run: bool = False,
        overwrite: bool = False,
        instruction: str = "",
    ) -> BulkLibraryResult:
        industry = target.industry
        survey_type = target.survey_type
        role = SurveyWaBulkLibraryTemplateService.normalize_step_role(step_role)

        existing = SurveyWaBulkLibraryTemplateService.find_existing_library_template(
            db,
            survey_type=survey_type,
            step_role=role,
        )
        if existing is not None and not overwrite:
            return BulkLibraryResult(
                industry_slug=industry.slug,
                industry_name=industry.name,
                survey_type_slug=survey_type.slug,
                survey_type_name=survey_type.name,
                status="skipped",
                reason=f"existing library template for step_role={role}",
                template_id=int(existing.id),
                step_role=role,
            )

        if dry_run:
            action = "would overwrite" if existing else "would create"
            return BulkLibraryResult(
                industry_slug=industry.slug,
                industry_name=industry.name,
                survey_type_slug=survey_type.slug,
                survey_type_name=survey_type.name,
                status="dry_run",
                reason=f"{action} one {role} template (LOCAL_DRAFT, no Telnyx sync)",
                template_id=int(existing.id) if existing else None,
                step_role=role,
            )

        generated = SurveyWaTemplatePackService.generate_library_template(
            db,
            survey_type=survey_type,
            step_role=role,
            purpose=str(survey_type.name or "").strip(),
            instruction=instruction,
            privacy_mode=PRIVACY_MODE_OFF,
            industry_id=industry.id,
        )
        template_payload = dict(generated["template"])
        if existing is not None and overwrite:
            template_payload["id"] = int(existing.id)

        saved = SurveyWaTemplatePackService.save_selected_templates(
            db,
            survey_type=survey_type,
            templates=[template_payload],
            privacy_mode=PRIVACY_MODE_OFF,
            purpose=str(survey_type.name or "").strip(),
            instruction=instruction,
            industry_id=industry.id,
            replace_step_bank=False,
        )
        saved_rows = saved.get("templates") or []
        if not saved_rows:
            errors = saved.get("errors") or ["save failed"]
            raise SurveyWaTemplatePackError("; ".join(str(e) for e in errors[:3]))

        template_id = int(saved_rows[0]["id"])
        return BulkLibraryResult(
            industry_slug=industry.slug,
            industry_name=industry.name,
            survey_type_slug=survey_type.slug,
            survey_type_name=survey_type.name,
            status="created" if existing is None else "overwritten",
            reason="saved as LOCAL_DRAFT under survey type (manual Telnyx sync required)",
            template_id=template_id,
            step_role=role,
        )

    @staticmethod
    def run_bulk(
        db: Session,
        *,
        dry_run: bool = False,
        limit: int | None = None,
        overwrite: bool = False,
        industry_slug: str | None = None,
        survey_type_slug: str | None = None,
        step_role: str = DEFAULT_LIBRARY_STEP_ROLE,
        instruction: str = "",
    ) -> dict[str, Any]:
        role = SurveyWaBulkLibraryTemplateService.normalize_step_role(step_role)
        results: list[BulkLibraryResult] = []
        processed = 0

        for target in SurveyWaBulkLibraryTemplateService.iter_targets(
            db,
            industry_slug=industry_slug,
            survey_type_slug=survey_type_slug,
        ):
            if limit is not None and processed >= max(0, int(limit)):
                break
            processed += 1
            try:
                result = SurveyWaBulkLibraryTemplateService.process_target(
                    db,
                    target=target,
                    step_role=role,
                    dry_run=dry_run,
                    overwrite=overwrite,
                    instruction=instruction,
                )
            except SurveyWaTemplatePackError as exc:
                result = BulkLibraryResult(
                    industry_slug=target.industry.slug,
                    industry_name=target.industry.name,
                    survey_type_slug=target.survey_type.slug,
                    survey_type_name=target.survey_type.name,
                    status="failed",
                    reason=str(exc),
                    step_role=role,
                )
            results.append(result)

        summary = {
            "created": sum(1 for r in results if r.status == "created"),
            "overwritten": sum(1 for r in results if r.status == "overwritten"),
            "skipped": sum(1 for r in results if r.status == "skipped"),
            "failed": sum(1 for r in results if r.status == "failed"),
            "dry_run": sum(1 for r in results if r.status == "dry_run"),
            "total": len(results),
            "step_role": role,
            "dry_run_mode": bool(dry_run),
            "overwrite_mode": bool(overwrite),
        }
        return {"summary": summary, "results": results}
