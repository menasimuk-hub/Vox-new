"""WA Survey publish readiness — step bank, outcomes, flows, picker (P5 admin)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.survey_type import SurveyType
from app.services.survey_flow_constants import (
    FLOW_STATUS_PUBLISHED,
    NEXT_RESOLUTION_AI_ASSISTED,
    NODE_TYPE_QUESTION,
    OUTCOME_KEYS,
)
from app.services.survey_flow_definition_service import (
    SurveyFlowDefinitionService,
    flow_definition_to_dict,
)
from app.services.survey_outcome_template_service import (
    SurveyOutcomeTemplateService,
    build_variable_context,
)
from app.services.survey_picker_settings_service import SurveyPickerSettingsService
from app.services.survey_step_bank_service import SurveyStepBankService
from app.services.wa_template_privacy import normalize_privacy_mode, privacy_mode_to_variant


def _count_ai_assisted_nodes(snap: dict[str, Any] | None) -> int:
    if not snap:
        return 0
    count = 0
    for n in snap.get("nodes") or []:
        if not isinstance(n, dict):
            continue
        if str(n.get("next_resolution") or "").strip().lower() == NEXT_RESOLUTION_AI_ASSISTED:
            count += 1
    return count


class SurveyWaReadinessService:
    @staticmethod
    def build_outcome_matrix(
        db: Session,
        *,
        survey_type: SurveyType,
        privacy_mode: str,
    ) -> list[dict[str, Any]]:
        pm = normalize_privacy_mode(privacy_mode)
        registry = SurveyOutcomeTemplateService.get_registry(
            db, survey_type=survey_type, privacy_mode=pm
        )
        ctx = build_variable_context(
            first_name="there", org_name="Your business", organiser="the team"
        )
        rows: list[dict[str, Any]] = []
        for ok in OUTCOME_KEYS:
            row = registry.get(ok)
            terr: list[str] = []
            twarn: list[str] = []
            action_type = "send_text"
            template_id = None
            template_name = None
            status = None
            if row is not None:
                template_id = row.id
                template_name = row.display_name or row.name
                status = str(row.status or "").upper()
                terr, twarn = SurveyOutcomeTemplateService.validate_template_row(
                    row, survey_type=survey_type, privacy_mode=pm, outcome_key=ok
                )
                action, _, _ = SurveyOutcomeTemplateService.resolve_outcome_action(
                    db,
                    survey_type=survey_type,
                    privacy_mode=pm,
                    outcome_key=ok,
                    context=ctx,
                )
                action_type = str(action.get("action_type") or "send_text")
            else:
                twarn.append("No completion template in bank — runtime uses text fallback")
                _, _, twarn2 = SurveyOutcomeTemplateService.resolve_outcome_action(
                    db,
                    survey_type=survey_type,
                    privacy_mode=pm,
                    outcome_key=ok,
                    context=ctx,
                )
                twarn.extend(twarn2)

            rows.append(
                {
                    "outcome_key": ok,
                    "template_id": template_id,
                    "template_name": template_name,
                    "status": status,
                    "approved": status == "APPROVED" if status else False,
                    "action_type": action_type,
                    "will_text_fallback": action_type != "send_template" or bool(twarn),
                    "errors": terr,
                    "warnings": twarn,
                }
            )
        return rows

    @staticmethod
    def readiness(
        db: Session,
        *,
        survey_type_id: str,
        privacy_mode: str = "off",
        variant: str | None = None,
    ) -> dict[str, Any]:
        st = db.get(SurveyType, survey_type_id)
        if st is None:
            return {"ok": False, "errors": ["Survey type not found"], "warnings": []}

        pm = normalize_privacy_mode(privacy_mode)
        var = variant or privacy_mode_to_variant(pm)
        errors: list[str] = []
        warnings: list[str] = []

        bank = SurveyStepBankService.get_bank(db, survey_type=st, variant=var, privacy_mode=pm)
        missing = list(bank.get("missing_roles") or [])
        if missing:
            warnings.append(f"Step bank missing roles: {', '.join(missing)}")
        start = (bank.get("by_role") or {}).get("start")
        if not start:
            errors.append("No start template in step bank for this privacy mode")
        elif str(start.get("status") or "").upper() != "APPROVED":
            warnings.append(
                f"Start template not APPROVED (status={start.get('status')}) — orders may fail to open survey"
            )

        outcome_matrix = SurveyWaReadinessService.build_outcome_matrix(
            db, survey_type=st, privacy_mode=pm
        )
        for row in outcome_matrix:
            for e in row.get("errors") or []:
                errors.append(f"outcome.{row['outcome_key']}: {e}")
            for w in row.get("warnings") or []:
                warnings.append(f"outcome.{row['outcome_key']}: {w}")

        flows = SurveyFlowDefinitionService.list_for_survey_type(db, survey_type_id, privacy_mode=pm)
        published = SurveyFlowDefinitionService.get_published_default(
            db, survey_type_id=survey_type_id, privacy_mode=pm
        )
        if not published:
            warnings.append(
                "No published default graph flow for this privacy mode — use linear flow_engine or publish a flow"
            )

        flow_validation: dict[str, Any] | None = None
        ai_assisted_node_count = 0
        validate_flow_id = published.id if published else None
        if not validate_flow_id and flows:
            drafts = [f for f in flows if f.get("status") != FLOW_STATUS_PUBLISHED]
            if drafts:
                validate_flow_id = drafts[0]["id"]
        if validate_flow_id:
            mq = int(st.max_length or 6)
            flow_validation = SurveyFlowDefinitionService.validate(db, validate_flow_id, max_question_visits=mq)
            for e in flow_validation.get("errors") or []:
                errors.append(f"flow: {e}")
            for w in flow_validation.get("warnings") or []:
                warnings.append(f"flow: {w}")
            snap = flow_validation.get("snapshot_preview")
            if isinstance(snap, dict):
                ai_assisted_node_count = _count_ai_assisted_nodes(snap)
                if ai_assisted_node_count and not SurveyPickerSettingsService.is_platform_picker_enabled(db):
                    warnings.append(
                        f"Flow has {ai_assisted_node_count} AI-assisted node(s) but platform AI picker is disabled"
                    )

        picker = SurveyPickerSettingsService.get_settings(db)
        picker["platform_enabled"] = SurveyPickerSettingsService.is_platform_picker_enabled(db)

        return {
            "ok": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "survey_type_id": survey_type_id,
            "privacy_mode": pm,
            "variant": var,
            "step_bank": {
                "missing_roles": missing,
                "available_roles": list(bank.get("available_roles") or []),
                "pack_size": bank.get("pack_size"),
            },
            "outcome_matrix": outcome_matrix,
            "flows": flows,
            "published_flow": flow_definition_to_dict(published) if published else None,
            "flow_validation": flow_validation,
            "ai_assisted_node_count": ai_assisted_node_count,
            "picker": picker,
            "can_publish_graph": bool(flow_validation and flow_validation.get("ok")),
        }