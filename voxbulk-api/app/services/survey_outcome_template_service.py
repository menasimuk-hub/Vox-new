"""Outcome completion template registry — scoped by industry, survey type, privacy (P3)."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.survey_type import SurveyType
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_flow_constants import (
    ACTION_SEND_TEMPLATE,
    ACTION_SEND_TEXT,
    OUTCOME_KEYS,
)
from app.services.survey_industry_scope import template_matches_survey_industry
from app.services.survey_step_bank_service import normalize_step_role
from app.services.survey_whatsapp_template_service import SurveyWhatsappTemplateService
from app.services.telnyx_whatsapp_template_sync_service import (
    TelnyxWhatsappTemplateSyncService,
    send_template_id_for_row,
)
from app.services.wa_template_privacy import normalize_privacy_mode, privacy_mode_to_variant

logger = logging.getLogger(__name__)

OUTCOME_VARIABLE_PROFILES: dict[str, dict[str, Any]] = {
    "happy": {
        "variable_keys": ["first_name", "organisation_name", "organiser_name"],
        "defaults": ["there", "our team", "the team"],
    },
    "neutral": {
        "variable_keys": ["first_name", "organisation_name"],
        "defaults": ["there", "us"],
    },
    "unhappy": {
        "variable_keys": ["first_name", "organisation_name", "organiser_name"],
        "defaults": ["there", "our team", "support"],
    },
}

DEFAULT_OUTCOME_TEXT: dict[str, str] = {
    "happy": "Thank you — we're glad you had a positive experience.",
    "neutral": "Thank you — your feedback has been recorded.",
    "unhappy": "We're sorry your experience wasn't better. Someone from our team may follow up.",
}


def _loads(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def default_outcome_variables(outcome_key: str) -> dict[str, Any]:
    return dict(OUTCOME_VARIABLE_PROFILES.get(outcome_key) or OUTCOME_VARIABLE_PROFILES["neutral"])


def parse_outcome_variables(row: TelnyxWhatsappTemplate) -> dict[str, Any]:
    custom = _loads(row.outcome_variables_json)
    if isinstance(custom, dict) and custom.get("variable_keys"):
        return custom
    ok = str(row.outcome_key or "neutral")
    return default_outcome_variables(ok if ok in OUTCOME_KEYS else "neutral")


def build_variable_context(
    *,
    first_name: str,
    org_name: str,
    organiser: str,
) -> dict[str, str]:
    return {
        "first_name": first_name,
        "organisation_name": org_name,
        "organiser_name": organiser,
        "clinic_name": org_name,
        "business_name": org_name,
    }


def resolve_variables_for_template(
    row: TelnyxWhatsappTemplate,
    *,
    context: dict[str, str],
) -> dict[str, str]:
    profile = parse_outcome_variables(row)
    keys = profile.get("variable_keys") or []
    defaults = profile.get("defaults") or []
    out: dict[str, str] = {}
    for i, key in enumerate(keys):
        k = str(key)
        val = str(context.get(k) or "").strip()
        if not val and i < len(defaults):
            val = str(defaults[i])
        if val:
            out[k] = val
    if not out:
        out = {
            "first_name": context.get("first_name", ""),
            "organisation_name": context.get("organisation_name", ""),
        }
    return out


class SurveyOutcomeTemplateService:
    @staticmethod
    def list_for_survey_type(
        db: Session,
        *,
        survey_type_id: str,
        privacy_mode: str,
        active_only: bool = True,
    ) -> list[dict[str, Any]]:
        pm = normalize_privacy_mode(privacy_mode)
        q = select(TelnyxWhatsappTemplate).where(
            TelnyxWhatsappTemplate.survey_type_id == survey_type_id,
            TelnyxWhatsappTemplate.privacy_mode == pm,
            TelnyxWhatsappTemplate.step_role == "completion",
            TelnyxWhatsappTemplate.outcome_key.isnot(None),
        )
        if active_only:
            q = q.where(TelnyxWhatsappTemplate.active_for_survey.is_(True))
        rows = list(db.execute(q.order_by(TelnyxWhatsappTemplate.outcome_key)).scalars())
        return [
            {
                "id": r.id,
                "name": r.name,
                "outcome_key": r.outcome_key,
                "status": r.status,
                "privacy_mode": r.privacy_mode,
                "display_name": r.display_name,
                "body_preview": r.body_preview,
            }
            for r in rows
        ]

    @staticmethod
    def get_registry(
        db: Session,
        *,
        survey_type: SurveyType,
        privacy_mode: str,
    ) -> dict[str, TelnyxWhatsappTemplate]:
        pm = normalize_privacy_mode(privacy_mode)
        rows = list(
            db.execute(
                select(TelnyxWhatsappTemplate).where(
                    TelnyxWhatsappTemplate.survey_type_id == survey_type.id,
                    TelnyxWhatsappTemplate.privacy_mode == pm,
                    TelnyxWhatsappTemplate.step_role == "completion",
                    TelnyxWhatsappTemplate.outcome_key.in_(list(OUTCOME_KEYS)),
                    TelnyxWhatsappTemplate.active_for_survey.is_(True),
                )
            ).scalars()
        )
        registry: dict[str, TelnyxWhatsappTemplate] = {}
        for row in rows:
            ok = str(row.outcome_key or "")
            if ok not in OUTCOME_KEYS:
                continue
            if not template_matches_survey_industry(row, survey_type):
                continue
            existing = registry.get(ok)
            if existing is None:
                registry[ok] = row
                continue
            if str(row.status or "").upper() == "APPROVED" and str(existing.status or "").upper() != "APPROVED":
                registry[ok] = row
        return registry

    @staticmethod
    def validate_template_row(
        row: TelnyxWhatsappTemplate,
        *,
        survey_type: SurveyType,
        privacy_mode: str,
        outcome_key: str,
    ) -> tuple[list[str], list[str]]:
        errors: list[str] = []
        warnings: list[str] = []
        pm = normalize_privacy_mode(privacy_mode)
        ok = str(outcome_key)
        if ok not in OUTCOME_KEYS:
            errors.append(f"Invalid outcome_key: {ok}")
        if normalize_step_role(row.step_role or "") != "completion":
            errors.append("Outcome templates must have step_role=completion")
        if str(row.outcome_key or "") != ok:
            errors.append("Template outcome_key mismatch")
        if str(row.survey_type_id or "") != survey_type.id:
            errors.append("Template survey_type_id mismatch")
        if str(row.privacy_mode or "") != pm:
            errors.append("Template privacy_mode mismatch")
        if not template_matches_survey_industry(row, survey_type):
            errors.append("Template industry does not match survey type")
        status = str(row.status or "").upper()
        if status != "APPROVED":
            warnings.append(f"Template status is {status}, not APPROVED — will use text fallback")
        return errors, warnings

    @staticmethod
    def build_template_send_payload(
        db: Session,
        row: TelnyxWhatsappTemplate,
        *,
        context: dict[str, str],
    ) -> dict[str, Any]:
        vars_for_components = resolve_variables_for_template(row, context=context)
        components = TelnyxWhatsappTemplateSyncService.build_components_for_row(row, variables=vars_for_components)
        preview = SurveyWhatsappTemplateService.build_preview(
            db,
            row,
            business_name=context.get("organisation_name", "Your business"),
            first_name=context.get("first_name", "there"),
        )
        return {
            "template_id": row.id,
            "telnyx_template_id": send_template_id_for_row(row),
            "template_name": row.name,
            "language": row.language or "en_US",
            "components": components,
            "rendered_body": preview.get("rendered_body") or row.body_preview or "",
            "variable_map": parse_outcome_variables(row),
            "variables_resolved": vars_for_components,
            "approval_status": str(row.status or "").upper(),
        }

    @staticmethod
    def resolve_outcome_action(
        db: Session,
        *,
        survey_type: SurveyType,
        privacy_mode: str,
        outcome_key: str,
        context: dict[str, str],
        message_body_fallback: str | None = None,
    ) -> tuple[dict[str, Any], list[str], list[str]]:
        """Returns (outcome_action_dict, errors, warnings) for snapshot embedding."""
        errors: list[str] = []
        warnings: list[str] = []
        ok = str(outcome_key)
        registry = SurveyOutcomeTemplateService.get_registry(db, survey_type=survey_type, privacy_mode=privacy_mode)
        row = registry.get(ok)
        fallback_text = (message_body_fallback or DEFAULT_OUTCOME_TEXT.get(ok) or DEFAULT_OUTCOME_TEXT["neutral"]).strip()

        if row is None:
            warnings.append(f"No completion template in bank for outcome={ok}; using send_text fallback")
            return (
                {
                    "outcome_key": ok,
                    "action_type": ACTION_SEND_TEXT,
                    "template_id": None,
                    "message_body": fallback_text,
                    "template_send": None,
                },
                errors,
                warnings,
            )

        terr, twarn = SurveyOutcomeTemplateService.validate_template_row(
            row, survey_type=survey_type, privacy_mode=privacy_mode, outcome_key=ok
        )
        errors.extend(terr)
        warnings.extend(twarn)

        if str(row.status or "").upper() == "APPROVED":
            template_send = SurveyOutcomeTemplateService.build_template_send_payload(db, row, context=context)
            return (
                {
                    "outcome_key": ok,
                    "action_type": ACTION_SEND_TEMPLATE,
                    "template_id": row.id,
                    "message_body": fallback_text,
                    "template_send": template_send,
                },
                errors,
                warnings,
            )

        warnings.append(f"Outcome {ok}: template not APPROVED — send_text fallback")
        return (
            {
                "outcome_key": ok,
                "action_type": ACTION_SEND_TEXT,
                "template_id": row.id,
                "message_body": fallback_text or (row.body_preview or ""),
                "template_send": None,
            },
            errors,
            warnings,
        )

    @staticmethod
    def enrich_snapshot_outcomes(
        db: Session,
        *,
        snapshot: dict[str, Any],
        survey_type: SurveyType,
        privacy_mode: str,
        context: dict[str, str],
    ) -> dict[str, Any]:
        pm = normalize_privacy_mode(privacy_mode)
        outcomes_in = snapshot.get("outcomes") or []
        enriched: list[dict[str, Any]] = []
        all_warnings: list[str] = []
        for item in outcomes_in:
            if not isinstance(item, dict):
                continue
            ok = str(item.get("outcome_key") or "")
            action, _, warnings = SurveyOutcomeTemplateService.resolve_outcome_action(
                db,
                survey_type=survey_type,
                privacy_mode=pm,
                outcome_key=ok,
                context=context,
                message_body_fallback=item.get("message_body"),
            )
            action["node_key"] = item.get("node_key")
            enriched.append({**item, **action})
            all_warnings.extend(warnings)
        out = dict(snapshot)
        out["outcomes"] = enriched
        if all_warnings:
            out["outcome_warnings"] = all_warnings
        return out
