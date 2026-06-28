"""Admin service — disabled WA template list with flag enforcement."""

from __future__ import annotations

import io
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackIndustry, FeedbackSurveyType, FeedbackWaTemplate
from app.models.disabled_wa_template import DisabledWaTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.wa_template_industry_export_service import resolve_template_export_rows


def _normalize(name: str) -> str:
    return str(name or "").strip().lower()


def _row_to_dict(row: DisabledWaTemplate) -> dict[str, Any]:
    return {
        "id": row.id,
        "raw_name": row.raw_name,
        "normalized_name": row.normalized_name,
        "product_line": row.product_line,
        "industry_name": row.industry_name or "Unknown",
        "survey_type_name": row.survey_type_name or "Unknown",
        "target_kind": row.target_kind,
        "target_id": row.target_id,
        "disabled": row.disabled,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _resolve_target(resolved: dict[str, Any]) -> tuple[str, str | None]:
    fb_id = resolved.get("feedback_template_id")
    if fb_id:
        return "feedback", str(fb_id)
    plat_id = resolved.get("platform_template_id")
    if plat_id is not None:
        return "platform", str(plat_id)
    source = str(resolved.get("source") or "")
    if source == "feedback_db" or str(resolved.get("product_line") or "").startswith("Customer"):
        return "feedback", None
    if source in {"platform_db", "parsed_survey_name"}:
        return "platform", None
    return "unresolved", None


def _resolve_survey_type(resolved: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return (survey_type_id, survey_type_kind) for hiding the topic from the user dashboard."""
    fb_st = resolved.get("feedback_survey_type_id")
    if fb_st:
        return str(fb_st), "feedback"
    plat_st = resolved.get("platform_survey_type_id")
    if plat_st:
        return str(plat_st), "platform"
    return None, None


def _collect_feedback_survey_type_ids(db: Session, row: DisabledWaTemplate) -> set[str]:
    """Resolve which customer-feedback survey type ids a disabled template row should hide."""
    ids: set[str] = set()
    if row.survey_type_id and row.survey_type_kind in (None, "feedback"):
        ids.add(str(row.survey_type_id))

    resolved = resolve_template_export_rows(db, [row.raw_name])
    if not resolved:
        return ids
    info = resolved[0]
    primary = info.get("feedback_survey_type_id")
    if primary:
        ids.add(str(primary))
    for sid in info.get("feedback_survey_type_ids") or []:
        ids.add(str(sid))

    ind_slug = str(info.get("industry_slug") or "").strip()
    st_slug = str(info.get("survey_type_slug") or "").strip()
    if ind_slug and st_slug:
        fb_ind = db.execute(select(FeedbackIndustry).where(FeedbackIndustry.slug == ind_slug)).scalar_one_or_none()
        if fb_ind:
            for variant in {st_slug, st_slug.replace("-", "_"), st_slug.replace("_", "-")}:
                fb_st = db.execute(
                    select(FeedbackSurveyType).where(
                        FeedbackSurveyType.industry_id == fb_ind.id,
                        FeedbackSurveyType.slug == variant,
                    )
                ).scalar_one_or_none()
                if fb_st:
                    ids.add(fb_st.id)
                    break

    ind_name = str(info.get("industry_name") or row.industry_name or "").strip()
    st_name = str(info.get("survey_type_name") or row.survey_type_name or "").strip()
    if ind_name and st_name and ind_name not in {"Unknown", ""} and st_name not in {"Unknown", ""}:
        from sqlalchemy import func

        fb_st = db.execute(
            select(FeedbackSurveyType)
            .join(FeedbackIndustry, FeedbackIndustry.id == FeedbackSurveyType.industry_id)
            .where(func.lower(FeedbackIndustry.name) == ind_name.lower())
            .where(func.lower(FeedbackSurveyType.name) == st_name.lower())
        ).scalar_one_or_none()
        if fb_st:
            ids.add(fb_st.id)
    return ids


def _persist_survey_type_on_row(db: Session, row: DisabledWaTemplate) -> None:
    ids = _collect_feedback_survey_type_ids(db, row)
    if ids:
        row.survey_type_id = next(iter(ids))
        row.survey_type_kind = "feedback"
    elif not row.survey_type_kind:
        row.survey_type_kind = "none"
    row.updated_at = datetime.utcnow()


def _capture_platform_flags(row: TelnyxWhatsappTemplate) -> dict[str, bool]:
    return {
        "active_for_survey": bool(row.active_for_survey),
        "active_for_interview": bool(row.active_for_interview),
        "active_for_appointment": bool(row.active_for_appointment),
    }


def _disable_platform(row: TelnyxWhatsappTemplate) -> dict[str, bool]:
    prior = _capture_platform_flags(row)
    row.active_for_survey = False
    row.active_for_interview = False
    row.active_for_appointment = False
    row.updated_at = datetime.utcnow()
    return prior


def _restore_platform(row: TelnyxWhatsappTemplate, prior: dict[str, bool] | None) -> None:
    flags = prior or {}
    row.active_for_survey = bool(flags.get("active_for_survey", True))
    row.active_for_interview = bool(flags.get("active_for_interview", True))
    row.active_for_appointment = bool(flags.get("active_for_appointment", True))
    row.updated_at = datetime.utcnow()


def _disable_feedback(row: FeedbackWaTemplate) -> dict[str, bool]:
    prior = {"is_active": bool(row.is_active)}
    row.is_active = False
    row.updated_at = datetime.utcnow()
    return prior


def _restore_feedback(row: FeedbackWaTemplate, prior: dict[str, bool] | None) -> None:
    flags = prior or {}
    row.is_active = bool(flags.get("is_active", True))
    row.updated_at = datetime.utcnow()


def _load_prior_flags_json(raw: str | None) -> dict[str, bool] | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return {k: bool(v) for k, v in parsed.items()}
    except Exception:
        return None
    return None


def _apply_disable(db: Session, row: DisabledWaTemplate) -> None:
    _persist_survey_type_on_row(db, row)
    if row.target_kind == "platform" and row.target_id:
        tpl = db.get(TelnyxWhatsappTemplate, int(row.target_id))
        if tpl is not None:
            prior = _disable_platform(tpl)
            row.prior_flags_json = json.dumps(prior)
    elif row.target_kind == "feedback" and row.target_id:
        tpl = db.get(FeedbackWaTemplate, row.target_id)
        if tpl is not None:
            prior = _disable_feedback(tpl)
            row.prior_flags_json = json.dumps(prior)
    row.disabled = True
    row.updated_at = datetime.utcnow()


def _apply_enable(db: Session, row: DisabledWaTemplate) -> None:
    prior = _load_prior_flags_json(row.prior_flags_json)
    if row.target_kind == "platform" and row.target_id:
        tpl = db.get(TelnyxWhatsappTemplate, int(row.target_id))
        if tpl is not None:
            _restore_platform(tpl, prior)
    elif row.target_kind == "feedback" and row.target_id:
        tpl = db.get(FeedbackWaTemplate, row.target_id)
        if tpl is not None:
            _restore_feedback(tpl, prior)
    row.disabled = False
    row.updated_at = datetime.utcnow()


def _backfill_survey_types(db: Session, rows: list[DisabledWaTemplate]) -> bool:
    """Resolve and persist survey_type_id/kind for rows missing a resolved topic id."""
    pending = [r for r in rows if not r.survey_type_id or not r.survey_type_kind]
    if not pending:
        return False
    changed = False
    for row in pending:
        before_id = row.survey_type_id
        _persist_survey_type_on_row(db, row)
        if row.survey_type_id != before_id or row.survey_type_kind:
            changed = True
    if changed:
        db.commit()
    return changed


class DisabledWaTemplateService:
    @staticmethod
    def hidden_feedback_survey_type_ids(db: Session) -> set[str]:
        """Customer-feedback survey type ids hidden from the user dashboard because a
        WA template tied to them is currently disabled."""
        disabled_rows = list(
            db.execute(select(DisabledWaTemplate).where(DisabledWaTemplate.disabled.is_(True))).scalars()
        )
        if not disabled_rows:
            return set()
        _backfill_survey_types(db, disabled_rows)
        hidden: set[str] = set()
        for row in disabled_rows:
            hidden.update(_collect_feedback_survey_type_ids(db, row))
        return hidden

    @staticmethod
    def hidden_platform_survey_type_ids(db: Session) -> set[str]:
        """Platform WA survey type ids hidden because a tied template is disabled."""
        disabled_rows = list(
            db.execute(select(DisabledWaTemplate).where(DisabledWaTemplate.disabled.is_(True))).scalars()
        )
        if not disabled_rows:
            return set()
        _backfill_survey_types(db, disabled_rows)
        return {
            r.survey_type_id
            for r in disabled_rows
            if r.survey_type_kind == "platform" and r.survey_type_id
        }

    @staticmethod
    def list_rows(db: Session) -> list[dict[str, Any]]:
        rows = list(
            db.execute(
                select(DisabledWaTemplate).order_by(
                    DisabledWaTemplate.industry_name,
                    DisabledWaTemplate.survey_type_name,
                    DisabledWaTemplate.raw_name,
                )
            ).scalars()
        )
        return [_row_to_dict(r) for r in rows]

    @staticmethod
    def add_names(db: Session, names: list[str]) -> dict[str, Any]:
        cleaned = [str(n or "").strip() for n in names if str(n or "").strip()]
        if not cleaned:
            return {"ok": True, "items": DisabledWaTemplateService.list_rows(db), "added": 0, "duplicates": 0}

        existing = {
            r.normalized_name: r
            for r in db.execute(select(DisabledWaTemplate)).scalars()
        }
        seen_input: set[str] = set()
        to_resolve: list[str] = []
        duplicates = 0

        for name in cleaned:
            key = _normalize(name)
            if not key:
                continue
            if key in existing or key in seen_input:
                duplicates += 1
                continue
            seen_input.add(key)
            to_resolve.append(name)

        resolved_rows = resolve_template_export_rows(db, to_resolve) if to_resolve else []
        now = datetime.utcnow()
        added = 0

        for name, resolved in zip(to_resolve, resolved_rows):
            key = _normalize(name)
            target_kind, target_id = _resolve_target(resolved)
            survey_type_id, survey_type_kind = _resolve_survey_type(resolved)
            row = DisabledWaTemplate(
                id=str(uuid.uuid4()),
                normalized_name=key,
                raw_name=name,
                product_line=str(resolved.get("product_line") or ""),
                industry_name=str(resolved.get("industry_name") or "Unknown"),
                survey_type_name=str(resolved.get("survey_type_name") or "Unknown"),
                target_kind=target_kind,
                target_id=target_id,
                survey_type_id=survey_type_id,
                survey_type_kind=survey_type_kind,
                prior_flags_json=None,
                disabled=False,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            existing[key] = row
            added += 1

        db.commit()
        return {
            "ok": True,
            "items": DisabledWaTemplateService.list_rows(db),
            "added": added,
            "duplicates": duplicates,
        }

    @staticmethod
    def set_disabled(db: Session, row_id: str, disabled: bool) -> dict[str, Any]:
        row = db.get(DisabledWaTemplate, row_id)
        if row is None:
            raise ValueError("Template row not found")
        if disabled and not row.disabled:
            _apply_disable(db, row)
        elif not disabled and row.disabled:
            _apply_enable(db, row)
        else:
            row.disabled = disabled
            row.updated_at = datetime.utcnow()
        db.commit()
        return {"ok": True, "item": _row_to_dict(row)}

    @staticmethod
    def disable_all(db: Session) -> dict[str, Any]:
        rows = list(db.execute(select(DisabledWaTemplate)).scalars())
        count = 0
        for row in rows:
            if not row.disabled:
                _apply_disable(db, row)
                count += 1
        db.commit()
        return {"ok": True, "items": DisabledWaTemplateService.list_rows(db), "changed": count}

    @staticmethod
    def enable_all(db: Session) -> dict[str, Any]:
        rows = list(db.execute(select(DisabledWaTemplate)).scalars())
        count = 0
        for row in rows:
            if row.disabled:
                _apply_enable(db, row)
                count += 1
        db.commit()
        return {"ok": True, "items": DisabledWaTemplateService.list_rows(db), "changed": count}

    @staticmethod
    def remove(db: Session, row_id: str) -> dict[str, Any]:
        row = db.get(DisabledWaTemplate, row_id)
        if row is None:
            raise ValueError("Template row not found")
        if row.disabled:
            _apply_enable(db, row)
        db.delete(row)
        db.commit()
        return {"ok": True, "items": DisabledWaTemplateService.list_rows(db)}

    @staticmethod
    def parse_upload_content(filename: str, content: bytes) -> list[str]:
        lower = str(filename or "").lower()
        names: list[str] = []

        if lower.endswith(".xlsx"):
            import openpyxl

            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            ws = wb.active
            for row in ws.iter_rows(values_only=True):
                if not row:
                    continue
                cell = row[0]
                text = str(cell or "").strip()
                if text:
                    names.append(text)
            return names

        text = content.decode("utf-8-sig", errors="replace")
        for line in text.splitlines():
            parts = line.split(",")
            name = str(parts[0] or "").strip().strip('"')
            if name:
                names.append(name)
        return names
