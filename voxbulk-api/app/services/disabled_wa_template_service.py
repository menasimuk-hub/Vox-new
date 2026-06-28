"""Admin service — disabled WA template list with flag enforcement."""

from __future__ import annotations

import io
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackWaTemplate
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


class DisabledWaTemplateService:
    @staticmethod
    def hidden_feedback_survey_type_ids(db: Session) -> set[str]:
        """Customer-feedback survey type ids that must be hidden from the user dashboard
        because a WA template tied to them is currently disabled."""
        ids: set[str] = set()
        rows = db.execute(
            select(DisabledWaTemplate).where(
                DisabledWaTemplate.disabled.is_(True),
                DisabledWaTemplate.target_kind == "feedback",
                DisabledWaTemplate.target_id.is_not(None),
            )
        ).scalars()
        for row in rows:
            tpl = db.get(FeedbackWaTemplate, row.target_id)
            if tpl is not None and tpl.survey_type_id:
                ids.add(tpl.survey_type_id)
        return ids

    @staticmethod
    def hidden_platform_survey_type_ids(db: Session) -> set[str]:
        """Platform WA survey type ids hidden because a tied template is disabled."""
        ids: set[str] = set()
        rows = db.execute(
            select(DisabledWaTemplate).where(
                DisabledWaTemplate.disabled.is_(True),
                DisabledWaTemplate.target_kind == "platform",
                DisabledWaTemplate.target_id.is_not(None),
            )
        ).scalars()
        for row in rows:
            try:
                tpl = db.get(TelnyxWhatsappTemplate, int(row.target_id))
            except (TypeError, ValueError):
                tpl = None
            if tpl is not None and tpl.survey_type_id:
                ids.add(tpl.survey_type_id)
        return ids

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
            row = DisabledWaTemplate(
                id=str(uuid.uuid4()),
                normalized_name=key,
                raw_name=name,
                product_line=str(resolved.get("product_line") or ""),
                industry_name=str(resolved.get("industry_name") or "Unknown"),
                survey_type_name=str(resolved.get("survey_type_name") or "Unknown"),
                target_kind=target_kind,
                target_id=target_id,
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
