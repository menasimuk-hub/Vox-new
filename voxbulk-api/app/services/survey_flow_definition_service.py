"""CRUD and publish for WA Survey flow definitions (P2)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.survey_flow import SurveyFlowDefinition, SurveyFlowEdge, SurveyFlowNode, SurveyFlowOutcome
from app.models.survey_type import SurveyType
from app.services.survey_flow_compiler_service import snapshot_from_db_rows, validate_flow_snapshot
from app.services.survey_flow_constants import (
    FLOW_STATUS_DRAFT,
    FLOW_STATUS_PUBLISHED,
    NODE_TYPE_OUTCOME,
    NODE_TYPE_QUESTION,
    OUTCOME_KEYS,
)
from app.services.survey_step_bank_service import SurveyStepBankService, normalize_step_role
from app.services.wa_template_privacy import normalize_privacy_mode, privacy_mode_to_variant


def flow_definition_to_dict(row: SurveyFlowDefinition) -> dict[str, Any]:
    return {
        "id": row.id,
        "survey_type_id": row.survey_type_id,
        "privacy_mode": row.privacy_mode,
        "slug": row.slug,
        "name": row.name,
        "status": row.status,
        "version": row.version,
        "is_default": row.is_default,
        "entry_node_key": row.entry_node_key,
        "fallback_outcome_key": row.fallback_outcome_key,
        "description": row.description,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


class SurveyFlowDefinitionService:
    @staticmethod
    def list_for_survey_type(
        db: Session,
        survey_type_id: str,
        *,
        privacy_mode: str | None = None,
    ) -> list[dict[str, Any]]:
        q = select(SurveyFlowDefinition).where(SurveyFlowDefinition.survey_type_id == survey_type_id)
        if privacy_mode:
            q = q.where(SurveyFlowDefinition.privacy_mode == normalize_privacy_mode(privacy_mode))
        rows = list(db.execute(q.order_by(SurveyFlowDefinition.updated_at.desc())).scalars())
        return [flow_definition_to_dict(r) for r in rows]

    @staticmethod
    def get_flow(db: Session, flow_id: str) -> SurveyFlowDefinition | None:
        return db.get(SurveyFlowDefinition, flow_id)

    @staticmethod
    def get_published_default(
        db: Session,
        *,
        survey_type_id: str,
        privacy_mode: str,
    ) -> SurveyFlowDefinition | None:
        pm = normalize_privacy_mode(privacy_mode)
        return db.execute(
            select(SurveyFlowDefinition).where(
                SurveyFlowDefinition.survey_type_id == survey_type_id,
                SurveyFlowDefinition.privacy_mode == pm,
                SurveyFlowDefinition.status == FLOW_STATUS_PUBLISHED,
                SurveyFlowDefinition.is_default.is_(True),
            )
        ).scalar_one_or_none()

    @staticmethod
    def load_graph(db: Session, flow_id: str) -> dict[str, Any] | None:
        row = db.get(SurveyFlowDefinition, flow_id)
        if row is None:
            return None
        nodes = list(
            db.execute(select(SurveyFlowNode).where(SurveyFlowNode.flow_id == flow_id)).scalars()
        )
        edges = list(
            db.execute(select(SurveyFlowEdge).where(SurveyFlowEdge.flow_id == flow_id)).scalars()
        )
        outcomes = list(
            db.execute(select(SurveyFlowOutcome).where(SurveyFlowOutcome.flow_id == flow_id)).scalars()
        )
        return {
            "definition": flow_definition_to_dict(row),
            "nodes": [
                {
                    "node_key": n.node_key,
                    "node_type": n.node_type,
                    "step_role": n.step_role,
                    "template_id": n.template_id,
                    "title": n.title,
                    "is_terminal": n.is_terminal,
                    "outcome_key": n.outcome_key,
                    "sort_order": n.sort_order,
                    "metadata_json": n.metadata_json,
                }
                for n in nodes
            ],
            "edges": [
                {
                    "from_node_key": e.from_node_key,
                    "to_node_key": e.to_node_key,
                    "priority": e.priority,
                    "rule_key": e.rule_key,
                    "condition_json": e.condition_json,
                    "label": e.label,
                }
                for e in edges
            ],
            "outcomes": [
                {
                    "outcome_key": o.outcome_key,
                    "node_key": o.node_key,
                    "action_type": o.action_type,
                    "template_id": o.template_id,
                    "message_body": o.message_body,
                }
                for o in outcomes
            ],
        }

    @staticmethod
    def create_draft(db: Session, payload: dict[str, Any]) -> SurveyFlowDefinition:
        survey_type_id = str(payload.get("survey_type_id") or "").strip()
        if not survey_type_id:
            raise ValueError("survey_type_id is required")
        st = db.get(SurveyType, survey_type_id)
        if st is None:
            raise ValueError("Survey type not found")
        pm = normalize_privacy_mode(payload.get("privacy_mode"))
        now = datetime.utcnow()
        row = SurveyFlowDefinition(
            id=str(uuid.uuid4()),
            survey_type_id=survey_type_id,
            privacy_mode=pm,
            slug=str(payload.get("slug") or "default").strip() or "default",
            name=str(payload.get("name") or "Survey flow").strip() or "Survey flow",
            status=FLOW_STATUS_DRAFT,
            version=int(payload.get("version") or 1),
            is_default=bool(payload.get("is_default", False)),
            entry_node_key=str(payload.get("entry_node_key") or "").strip() or "rating",
            fallback_outcome_key=str(payload.get("fallback_outcome_key") or "neutral").strip(),
            description=payload.get("description"),
            created_at=now,
            updated_at=now,
        )
        if row.fallback_outcome_key not in OUTCOME_KEYS:
            raise ValueError("fallback_outcome_key must be happy, neutral, or unhappy")
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def replace_graph(db: Session, flow_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        row = db.get(SurveyFlowDefinition, flow_id)
        if row is None:
            raise ValueError("Flow not found")
        if str(row.status) == FLOW_STATUS_PUBLISHED:
            raise ValueError("Cannot edit a published flow; create a new draft version")

        for model in (SurveyFlowEdge, SurveyFlowOutcome, SurveyFlowNode):
            for item in list(db.execute(select(model).where(model.flow_id == flow_id)).scalars()):
                db.delete(item)

        nodes_in = payload.get("nodes") or []
        edges_in = payload.get("edges") or []
        outcomes_in = payload.get("outcomes") or []
        now = datetime.utcnow()

        if payload.get("entry_node_key"):
            row.entry_node_key = str(payload["entry_node_key"]).strip()
        if payload.get("fallback_outcome_key"):
            fb = str(payload["fallback_outcome_key"]).strip()
            if fb not in OUTCOME_KEYS:
                raise ValueError("fallback_outcome_key must be happy, neutral, or unhappy")
            row.fallback_outcome_key = fb
        if payload.get("name"):
            row.name = str(payload["name"]).strip()
        row.updated_at = now

        for n in nodes_in:
            if not isinstance(n, dict):
                continue
            db.add(
                SurveyFlowNode(
                    id=str(uuid.uuid4()),
                    flow_id=flow_id,
                    node_key=str(n["node_key"]),
                    node_type=str(n["node_type"]),
                    step_role=n.get("step_role"),
                    template_id=n.get("template_id"),
                    title=n.get("title"),
                    is_terminal=bool(n.get("is_terminal")),
                    outcome_key=n.get("outcome_key"),
                    sort_order=n.get("sort_order"),
                    metadata_json=json.dumps(n.get("metadata") or n.get("question") or {}, ensure_ascii=False)
                    if n.get("metadata") or n.get("question")
                    else None,
                    created_at=now,
                )
            )
        for e in edges_in:
            if not isinstance(e, dict):
                continue
            cond = e.get("condition_json")
            cond_raw = json.dumps(cond, ensure_ascii=False) if cond is not None else None
            db.add(
                SurveyFlowEdge(
                    id=str(uuid.uuid4()),
                    flow_id=flow_id,
                    from_node_key=str(e["from_node_key"]),
                    to_node_key=str(e["to_node_key"]),
                    priority=int(e.get("priority") or 100),
                    rule_key=str(e.get("rule_key") or "branch.custom"),
                    condition_json=cond_raw,
                    label=e.get("label"),
                    created_at=now,
                )
            )
        for o in outcomes_in:
            if not isinstance(o, dict):
                continue
            ok = str(o.get("outcome_key") or "")
            if ok not in OUTCOME_KEYS:
                raise ValueError(f"Invalid outcome_key: {ok}")
            db.add(
                SurveyFlowOutcome(
                    id=str(uuid.uuid4()),
                    flow_id=flow_id,
                    outcome_key=ok,
                    node_key=str(o["node_key"]),
                    action_type=str(o.get("action_type") or "send_text"),
                    template_id=o.get("template_id"),
                    message_body=o.get("message_body"),
                    sort_order=int(o.get("sort_order") or 0),
                    created_at=now,
                )
            )
        db.add(row)
        db.commit()
        return SurveyFlowDefinitionService.load_graph(db, flow_id) or {}

    @staticmethod
    def validate(db: Session, flow_id: str, *, max_question_visits: int | None = None) -> dict[str, Any]:
        graph = SurveyFlowDefinitionService.load_graph(db, flow_id)
        if not graph:
            return {"ok": False, "errors": ["Flow not found"]}
        row = db.get(SurveyFlowDefinition, flow_id)
        st = db.get(SurveyType, row.survey_type_id) if row else None
        mq = max_question_visits or (st.max_length if st else 6)
        snap = SurveyFlowDefinitionService.build_snapshot(db, flow_id, max_question_visits=mq)
        errors = validate_flow_snapshot(snap)
        warnings: list[str] = list(snap.get("outcome_warnings") or [])
        if row:
            variant = privacy_mode_to_variant(row.privacy_mode)
            if st:
                bank = SurveyStepBankService.get_bank(db, survey_type=st, variant=variant, privacy_mode=row.privacy_mode)
                for n in snap.get("nodes") or []:
                    if n.get("node_type") == NODE_TYPE_QUESTION:
                        role = normalize_step_role(str(n.get("step_role") or ""))
                        if role and role not in (bank.get("by_role") or {}):
                            errors.append(f"step_role not in step bank: {role}")
                from app.services.survey_outcome_template_service import SurveyOutcomeTemplateService

                for ok in ("happy", "neutral", "unhappy"):
                    reg = SurveyOutcomeTemplateService.get_registry(
                        db, survey_type=st, privacy_mode=row.privacy_mode
                    )
                    if ok not in reg:
                        warnings.append(f"No bank completion template for outcome={ok}")
        return {"ok": not errors, "errors": errors, "warnings": warnings, "snapshot_preview": snap}

    @staticmethod
    def build_snapshot(
        db: Session,
        flow_id: str,
        *,
        max_question_visits: int,
        questions_by_role: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        row = db.get(SurveyFlowDefinition, flow_id)
        if row is None:
            raise ValueError("Flow not found")
        nodes = list(db.execute(select(SurveyFlowNode).where(SurveyFlowNode.flow_id == flow_id)).scalars())
        edges = list(db.execute(select(SurveyFlowEdge).where(SurveyFlowEdge.flow_id == flow_id)).scalars())
        outcomes = list(db.execute(select(SurveyFlowOutcome).where(SurveyFlowOutcome.flow_id == flow_id)).scalars())
        snap = snapshot_from_db_rows(
            flow_id=flow_id,
            version=row.version,
            entry_node_key=row.entry_node_key,
            fallback_outcome_key=row.fallback_outcome_key,
            max_question_visits=max_question_visits,
            nodes=nodes,
            edges=edges,
            outcomes=outcomes,
            questions_by_role=questions_by_role,
        )
        st = db.get(SurveyType, row.survey_type_id)
        if st:
            from app.services.survey_outcome_template_service import (
                SurveyOutcomeTemplateService,
                build_variable_context,
            )

            snap = SurveyOutcomeTemplateService.enrich_snapshot_outcomes(
                db,
                snapshot=snap,
                survey_type=st,
                privacy_mode=row.privacy_mode,
                context=build_variable_context(first_name="there", org_name="Your business", organiser="the team"),
            )
        return snap

    @staticmethod
    def publish(db: Session, flow_id: str, *, max_question_visits: int = 6) -> dict[str, Any]:
        validation = SurveyFlowDefinitionService.validate(db, flow_id, max_question_visits=max_question_visits)
        if not validation.get("ok"):
            raise ValueError("; ".join(validation.get("errors") or ["Validation failed"]))
        row = db.get(SurveyFlowDefinition, flow_id)
        if row is None:
            raise ValueError("Flow not found")
        if row.is_default:
            others = list(
                db.execute(
                    select(SurveyFlowDefinition).where(
                        SurveyFlowDefinition.survey_type_id == row.survey_type_id,
                        SurveyFlowDefinition.privacy_mode == row.privacy_mode,
                        SurveyFlowDefinition.is_default.is_(True),
                        SurveyFlowDefinition.id != flow_id,
                    )
                ).scalars()
            )
            for o in others:
                o.is_default = False
                db.add(o)
        row.status = FLOW_STATUS_PUBLISHED
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        return {"ok": True, "flow": flow_definition_to_dict(row)}

    @staticmethod
    def resolve_snapshot_for_order(
        db: Session,
        *,
        config: dict[str, Any],
        survey_type: SurveyType,
        questions: list[dict[str, Any]],
        page_roles: list[str],
        closing_body: str,
    ) -> tuple[dict[str, Any], str | None]:
        """
        Returns (snapshot, flow_definition_id) for graph mode orders.
        Uses published default flow if flow_definition_id set, else auto-compiles linear graph.
        """
        from app.services.survey_flow_compiler_service import compile_linear_graph
        from app.services.survey_flow_config_service import max_question_visits

        mq = max_question_visits(config, survey_type_max_length=survey_type.max_length)
        pm = normalize_privacy_mode(config.get("privacy_mode"))
        fid = str(config.get("flow_definition_id") or "").strip() or None
        branches = config.get("flow_branches") if isinstance(config.get("flow_branches"), list) else None

        if fid:
            row = db.get(SurveyFlowDefinition, fid)
            if row is None or row.status != FLOW_STATUS_PUBLISHED:
                raise ValueError("flow_definition_id must reference a published flow")
            qmap = {
                normalize_step_role(str(q.get("step_role") or "")): q
                for q in questions
                if isinstance(q, dict)
            }
            snap = SurveyFlowDefinitionService.build_snapshot(
                db, fid, max_question_visits=mq, questions_by_role=qmap
            )
            from app.services.survey_outcome_template_service import (
                SurveyOutcomeTemplateService,
                build_variable_context,
            )

            snap = SurveyOutcomeTemplateService.enrich_snapshot_outcomes(
                db,
                snapshot=snap,
                survey_type=survey_type,
                privacy_mode=pm,
                context=build_variable_context(
                    first_name="there",
                    org_name=str(config.get("organisation_name") or "Your business"),
                    organiser=str(config.get("survey_organiser_name") or "the team"),
                ),
            )
            return snap, fid

        snap = compile_linear_graph(
            page_roles=page_roles,
            questions=questions,
            max_question_visits=mq,
            closing_body=closing_body,
            flow_definition_id=None,
            branches=branches,
        )
        errors = validate_flow_snapshot(snap)
        if errors:
            raise ValueError("; ".join(errors))
        from app.services.survey_outcome_template_service import (
            SurveyOutcomeTemplateService,
            build_variable_context,
        )

        snap = SurveyOutcomeTemplateService.enrich_snapshot_outcomes(
            db,
            snapshot=snap,
            survey_type=survey_type,
            privacy_mode=pm,
            context=build_variable_context(
                first_name="there",
                org_name=str(config.get("organisation_name") or "Your business"),
                organiser=str(config.get("survey_organiser_name") or "the team"),
            ),
        )
        return snap, None
