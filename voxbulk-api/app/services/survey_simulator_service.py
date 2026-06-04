"""In-browser WA Survey flow simulator — reuses production conversation/runtime (dry-run sends)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.survey_session import SurveySession
from app.models.user import User
from app.services.survey_flow_config_service import attach_flow_to_config, is_graph_flow, is_simulator_dry_run
from app.services.survey_flow_constants import (
    DECISION_BRANCH_PICKER_RESULT,
    DECISION_BRANCH_TAKE,
    FLOW_ENGINE_GRAPH,
    FLOW_ENGINE_LINEAR,
)
from app.services.survey_flow_definition_service import SurveyFlowDefinitionService
from app.services.survey_flow_picker_service import SurveyFlowPickerService
from app.services.survey_picker_settings_service import SurveyPickerSettingsService
from app.services.survey_generation_service import SurveyGenerationService
from app.services.survey_session_service import SurveySessionService
from app.services.survey_step_bank_service import SurveyStepBankService
from app.services.survey_type_service import SurveyTypeService
from app.services.survey_wa_readiness_service import SurveyWaReadinessService
from app.services.survey_wa_test_pack_seed_service import SurveyWaTestPackSeedService
from app.services.wa_template_privacy import privacy_mode_to_variant
from app.services.survey_whatsapp_conversation_service import (
    _order_config,
    _recipient_result,
    _wa_conversation,
    _whatsapp_flow,
    format_question_message,
    handle_inbound_reply,
    send_first_question,
)
from app.services.wa_template_privacy import normalize_privacy_mode

SIMULATOR_ORG_NAME = "WA Survey Simulator (internal)"
SIMULATOR_PHONE_PREFIX = "+447700900"

DEFAULT_GRAPH_BRANCHES: list[dict[str, Any]] = [
    {
        "from_step_role": "rating",
        "to_step_role": "unhappy",
        "priority": 5,
        "rule_key": "simulator.rating.low",
        "condition": {
            "op": "lte",
            "source": "last_answer.normalized_value",
            "value": "2",
            "cast": "int",
        },
    },
]

# Extra branch so rating has 3+ outgoing targets for AI picker tests (deterministic still uses conditions).
AI_PICKER_TEST_BRANCHES: list[dict[str, Any]] = [
    *DEFAULT_GRAPH_BRANCHES,
    {
        "from_step_role": "rating",
        "to_step_role": "reason",
        "priority": 12,
        "rule_key": "simulator.rating.to_reason",
        "condition": {
            "op": "lte",
            "source": "last_answer.normalized_value",
            "value": "10",
            "cast": "int",
        },
    },
]


def _templates_manifest_from_composed(generated: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start_id = generated.get("wa_template_id")
    if start_id:
        rows.append(
            {
                "step_role": "start",
                "template_id": start_id,
                "template_name": generated.get("wa_template_name"),
                "status": "APPROVED",
                "usage": "intro",
            }
        )
    for page in generated.get("pages") or []:
        if not isinstance(page, dict):
            continue
        role = str(page.get("step_role") or "")
        if role in ("start", "completion"):
            continue
        rows.append(
            {
                "step_role": role,
                "template_id": page.get("template_id"),
                "template_name": page.get("title") or page.get("display_name"),
                "status": page.get("approval_status") or page.get("status"),
                "usage": "question",
            }
        )
    snap = generated.get("flow_snapshot")
    if isinstance(snap, dict):
        for oc in snap.get("outcome_actions") or []:
            if not isinstance(oc, dict):
                continue
            rows.append(
                {
                    "step_role": "completion",
                    "outcome_key": oc.get("outcome_key"),
                    "template_id": oc.get("template_id"),
                    "template_name": (oc.get("template_send") or {}).get("template_name"),
                    "status": (oc.get("template_send") or {}).get("approval_status"),
                    "action_type": oc.get("action_type"),
                    "usage": "outcome",
                }
            )
    return rows


def _templates_manifest_from_bank(bank: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for role, item in (bank.get("by_role") or {}).items():
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "step_role": role,
                "template_id": item.get("template_id"),
                "template_name": item.get("display_name") or item.get("template_name"),
                "status": item.get("status") or item.get("approval_status"),
                "usage": "completion" if role == "completion" else ("start" if role == "start" else "question"),
            }
        )
    return rows


def _latest_branch_decision(db: Session, session_id: str) -> dict[str, Any] | None:
    for row in reversed(SurveySessionService.list_decisions(db, session_id)):
        if row.decision_kind not in (
            DECISION_BRANCH_TAKE,
            DECISION_BRANCH_PICKER_RESULT,
            "branch_evaluate",
        ):
            continue
        try:
            ctx = json.loads(row.context_json or "{}")
        except Exception:
            ctx = {}
        return {
            "decision_kind": row.decision_kind,
            "rule_key": row.rule_key,
            "picker": row.picker,
            "from_role": row.from_role,
            "to_role": row.to_role,
            "reason": row.reason,
            "context": ctx if isinstance(ctx, dict) else {},
        }
    return None


def _loads_delivery(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _ensure_simulator_org(db: Session) -> tuple[Organisation, User]:
    org = db.execute(select(Organisation).where(Organisation.name == SIMULATOR_ORG_NAME)).scalars().first()
    if org is None:
        org = Organisation(id=str(uuid.uuid4()), name=SIMULATOR_ORG_NAME)
        db.add(org)
        db.flush()
    user = db.execute(select(User).where(User.email == "wa-survey-simulator@voxbulk.internal")).scalars().first()
    if user is None:
        from app.core.security import hash_password

        user = User(
            id=str(uuid.uuid4()),
            email="wa-survey-simulator@voxbulk.internal",
            password_hash=hash_password(str(uuid.uuid4())),
            is_active=True,
        )
        db.add(user)
        db.flush()
    membership = db.execute(
        select(OrganisationMembership).where(
            OrganisationMembership.org_id == org.id,
            OrganisationMembership.user_id == user.id,
        )
    ).scalars().first()
    if membership is None:
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
    db.commit()
    return org, user


def _build_order_config(
    generated: dict[str, Any],
    *,
    flow_engine: str,
    flow_branches: list[dict[str, Any]] | None,
    force_outcome_text_fallback: bool,
    ai_picker_enabled: bool = False,
    simulator_mock_picker: bool = True,
) -> dict[str, Any]:
    wa = generated.get("whatsapp_flow") or {}
    config: dict[str, Any] = {
        "survey_channel": "whatsapp",
        "channels": ["whatsapp"],
        "survey_type_id": generated["survey_type"]["id"],
        "survey_type_slug": generated["survey_type"]["slug"],
        "privacy_mode": generated.get("privacy_mode") or "off",
        "anonymous_responses": bool(generated.get("anonymous_responses")),
        "page_count": generated.get("page_count"),
        "page_roles": generated.get("page_roles") or [],
        "whatsapp_flow": wa,
        "organisation_name": "Acme Services",
        "survey_organiser_name": "Test Team",
        "client_name": "Acme Services",
        "flow_engine": flow_engine,
        "simulator_dry_run": True,
        "simulator_force_template_fail": bool(force_outcome_text_fallback),
        "ai_picker_enabled": bool(ai_picker_enabled),
        "simulator_mock_picker": bool(simulator_mock_picker),
        "simulator_use_saved_templates": True,
    }
    extras = generated.get("order_config_flow") or {}
    if flow_engine == FLOW_ENGINE_GRAPH and extras:
        config.update(extras)
        snap = config.get("flow_snapshot")
        if isinstance(snap, dict) and ai_picker_enabled:
            snap = SurveyFlowPickerService.patch_snapshot_for_ai_test(snap)
            config = attach_flow_to_config(
                config,
                snapshot=snap,
                flow_definition_id=config.get("flow_definition_id"),
            )
    if flow_engine == FLOW_ENGINE_GRAPH and flow_branches:
        config["flow_branches"] = flow_branches
    return config


def _current_question(
    *,
    config: dict[str, Any],
    session: SurveySession | None,
    conv: dict[str, Any],
) -> dict[str, Any]:
    flow = _whatsapp_flow(config)
    questions = [q for q in (flow.get("questions") or []) if isinstance(q, dict)]
    step = int(conv.get("step") or 1)
    q: dict[str, Any] = {}
    if is_graph_flow(config) and session and session.flow_snapshot_json:
        try:
            snap = json.loads(session.flow_snapshot_json)
            node = {n["node_key"]: n for n in snap.get("nodes") or [] if isinstance(n, dict)}.get(
                session.current_node_key or ""
            )
            if node and isinstance(node.get("question"), dict):
                q = node["question"]
        except Exception:
            pass
    if not q and questions:
        idx = max(0, step - 1)
        q = questions[idx] if idx < len(questions) else questions[-1]
    total = int(conv.get("total") or len(questions) or 1)
    body = format_question_message(q, index=step, total=total) if q else ""
    return {
        "step_role": str(q.get("step_role") or session.current_node_key if session else ""),
        "node_key": session.current_node_key if session else None,
        "reply_type": q.get("reply_type"),
        "options": q.get("options") or [],
        "text": q.get("text") or "",
        "body": body,
    }


def _session_state(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    session: SurveySession | None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = _order_config(order)
    payload = _recipient_result(recipient)
    conv = _wa_conversation(payload)
    delivery = _loads_delivery(session.outcome_delivery_json if session else None)
    question = _current_question(config=config, session=session, conv=conv)
    state: dict[str, Any] = {
        "order_id": order.id,
        "recipient_id": recipient.id,
        "session_id": session.id if session else None,
        "flow_mode": session.flow_mode if session else None,
        "flow_engine": config.get("flow_engine") or FLOW_ENGINE_LINEAR,
        "status": str(recipient.status or ""),
        "completed": str(recipient.status or "").lower() == "completed",
        "step": int(conv.get("step") or 0),
        "total": int(conv.get("total") or 0),
        "current_step_role": question.get("step_role"),
        "current_node_key": question.get("node_key"),
        "question": question,
        "outcome_key": session.outcome_key if session else conv.get("outcome_key"),
        "outcome_delivery": delivery,
        "outcome_channel": delivery.get("channel"),
        "outcome_used_text_fallback": bool(delivery.get("used_text_fallback")),
        "outcome_action_type": delivery.get("action_type"),
        "outcome_body_preview": delivery.get("body_preview"),
        "answers": conv.get("answers") or [],
        "simulator_phone": recipient.phone,
        "ai_picker_enabled": bool(config.get("ai_picker_enabled")),
        "picker_invocation_count": int(session.picker_invocation_count or 0) if session else 0,
        "templates_in_use": config.get("simulator_templates_manifest") or [],
        "use_saved_templates": bool(config.get("simulator_use_saved_templates")),
        "flow_definition_id": config.get("flow_definition_id"),
    }
    if session:
        picker_dbg = SurveyFlowPickerService.latest_picker_debug(db, session.id)
        if picker_dbg:
            state["picker_debug"] = picker_dbg
        branch = _latest_branch_decision(db, session.id)
        if branch:
            state["last_branch_decision"] = branch
    if extra:
        state.update(extra)
    return state


class SurveySimulatorService:
    @staticmethod
    def list_options(db: Session) -> dict[str, Any]:
        from app.services.industry_service import IndustryService, industry_to_dict
        from app.services.survey_type_service import SurveyTypeService, survey_type_to_dict

        pack = SurveyWaTestPackSeedService.ensure_test_pack(db)
        industries = IndustryService.list_industries(db, active_only=True)
        types = SurveyTypeService.list_types(db, industry_id=pack["industry"]["id"])
        return {
            "ok": True,
            "test_pack": pack,
            "industries": industries,
            "survey_types": types,
            "default_industry_id": pack["industry"]["id"],
            "default_survey_type_id": pack["survey_type"]["id"],
            "default_privacy_mode": "off",
            "flow_engines": [FLOW_ENGINE_LINEAR, FLOW_ENGINE_GRAPH],
            "default_graph_branches": DEFAULT_GRAPH_BRANCHES,
            "ai_picker_test_branches": AI_PICKER_TEST_BRANCHES,
            "platform_picker": SurveyPickerSettingsService.get_settings(db),
        }

    @staticmethod
    def prefill_for_survey_type(
        db: Session,
        *,
        survey_type_id: str,
        privacy_mode: str = "off",
    ) -> dict[str, Any]:
        st = SurveyTypeService.get_type(db, survey_type_id)
        if st is None:
            raise ValueError("Survey type not found")
        pm = normalize_privacy_mode(privacy_mode)
        variant = privacy_mode_to_variant(pm)
        readiness = SurveyWaReadinessService.readiness(db, survey_type_id=survey_type_id, privacy_mode=pm)
        published = readiness.get("published_flow")
        flow_engine = FLOW_ENGINE_GRAPH if published else FLOW_ENGINE_LINEAR
        flow_definition_id = str(published["id"]) if published else None

        bank = SurveyStepBankService.get_bank(db, survey_type=st, variant=variant, privacy_mode=pm)
        bank_templates = _templates_manifest_from_bank(bank)

        platform_on = SurveyPickerSettingsService.is_platform_picker_enabled(db)
        ai_nodes = int(readiness.get("ai_assisted_node_count") or 0)
        ai_picker_default = bool(platform_on and ai_nodes > 0 and flow_engine == FLOW_ENGINE_GRAPH)

        blocking: list[str] = []
        for err in readiness.get("errors") or []:
            if "start template" in str(err).lower() or "step_role not in step bank" in str(err).lower():
                blocking.append(err)
        if not (bank.get("by_role") or {}).get("start"):
            blocking.append("No start template in saved step bank for this privacy mode.")

        return {
            "ok": True,
            "survey_type_id": survey_type_id,
            "survey_type_name": st.name,
            "industry_id": st.industry_id,
            "privacy_mode": pm,
            "flow_engine": flow_engine,
            "flow_definition_id": flow_definition_id,
            "published_flow": published,
            "ai_picker_enabled_default": ai_picker_default,
            "platform_picker_enabled": platform_on,
            "use_saved_templates": True,
            "templates_preview": bank_templates,
            "readiness_ok": bool(readiness.get("ok")),
            "errors": readiness.get("errors") or [],
            "warnings": readiness.get("warnings") or [],
            "blocking_errors": blocking,
            "can_start_simulation": len(blocking) == 0,
            "outcome_matrix": readiness.get("outcome_matrix") or [],
            "step_bank_missing": bank.get("missing_roles") or [],
        }

    @staticmethod
    def start(
        db: Session,
        *,
        survey_type_id: str,
        privacy_mode: str = "off",
        flow_engine: str = FLOW_ENGINE_LINEAR,
        page_count: int = 6,
        selected_step_roles: list[str] | None = None,
        flow_branches: list[dict[str, Any]] | None = None,
        force_outcome_text_fallback: bool = False,
        ai_picker_enabled: bool = False,
        simulator_mock_picker: bool = True,
        flow_definition_id: str | None = None,
        skip_test_pack_seed: bool = False,
    ) -> dict[str, Any]:
        if not skip_test_pack_seed:
            SurveyWaTestPackSeedService.ensure_test_pack(db)
        pm = normalize_privacy_mode(privacy_mode)
        engine = str(flow_engine or FLOW_ENGINE_LINEAR).strip().lower()
        roles = selected_step_roles
        if not roles:
            roles = ["start", "rating", "yes_no", "helpfulness", "reason", "completion"]

        branches = flow_branches
        if branches is None:
            branches = AI_PICKER_TEST_BRANCHES if ai_picker_enabled else DEFAULT_GRAPH_BRANCHES

        resolved_flow_id = flow_definition_id
        if engine == FLOW_ENGINE_GRAPH and not resolved_flow_id:
            pub = SurveyFlowDefinitionService.get_published_default(
                db, survey_type_id=survey_type_id, privacy_mode=pm
            )
            if pub is not None:
                resolved_flow_id = pub.id

        generated = SurveyGenerationService.generate(
            db,
            survey_type_id=survey_type_id,
            privacy_mode=pm,
            page_count=int(page_count),
            auto_select_steps=False if roles else True,
            selected_step_roles=roles,
            organisation_name="Acme Services",
            client_name="Acme Services",
            organiser_name="Test Team",
            flow_engine=engine if engine == FLOW_ENGINE_GRAPH else None,
            flow_definition_id=resolved_flow_id,
            flow_branches=branches,
        )

        config = _build_order_config(
            generated,
            flow_engine=engine,
            flow_branches=branches,
            force_outcome_text_fallback=force_outcome_text_fallback,
            ai_picker_enabled=ai_picker_enabled,
            simulator_mock_picker=simulator_mock_picker,
        )
        config["simulator_templates_manifest"] = _templates_manifest_from_composed(generated)
        if resolved_flow_id:
            config["flow_definition_id"] = resolved_flow_id

        org, user = _ensure_simulator_org(db)
        phone = f"{SIMULATOR_PHONE_PREFIX}{uuid.uuid4().int % 10000:04d}"
        now = datetime.utcnow()
        order = ServiceOrder(
            id=str(uuid.uuid4()),
            org_id=org.id,
            user_id=user.id,
            service_code="survey",
            title="WA Survey simulator",
            status="running",
            payment_status="approved",
            recipient_count=1,
            quote_total_pence=0,
            config_json=json.dumps(config, ensure_ascii=False),
            scheduled_start_at=now - timedelta(minutes=5),
            scheduled_end_at=now + timedelta(days=1),
            started_at=now,
            created_at=now,
            updated_at=now,
        )
        recipient = ServiceOrderRecipient(
            id=str(uuid.uuid4()),
            order_id=order.id,
            row_number=1,
            name="Test Recipient",
            phone=phone,
            status="sent",
            created_at=now,
        )
        db.add(order)
        db.add(recipient)
        db.commit()

        send_first_question(db, order=order, recipient=recipient, config=config)
        db.refresh(recipient)
        session = SurveySessionService.get_by_recipient(db, recipient.id)
        state = _session_state(db, order=order, recipient=recipient, session=session)
        return {
            "ok": True,
            "state": state,
            "templates_in_use": state.get("templates_in_use") or [],
            "flow_definition_id": resolved_flow_id,
        }

    @staticmethod
    def answer(db: Session, *, recipient_id: str, answer: str) -> dict[str, Any]:
        recipient = db.get(ServiceOrderRecipient, str(recipient_id or "").strip())
        if recipient is None:
            raise ValueError("recipient_id not found")
        order = db.get(ServiceOrder, recipient.order_id)
        if order is None:
            raise ValueError("order not found")
        config = _order_config(order)
        if not is_simulator_dry_run(config):
            raise ValueError("Not a simulator order")

        result = handle_inbound_reply(
            db,
            from_phone=recipient.phone or "",
            body=str(answer or "").strip(),
            org_id=order.org_id,
        )
        db.refresh(recipient)
        session = SurveySessionService.get_by_recipient(db, recipient.id)
        state = _session_state(
            db,
            order=order,
            recipient=recipient,
            session=session,
            extra={"last_handler": result},
        )
        return {"ok": True, "handler": result, "state": state}

    @staticmethod
    def get_state(db: Session, *, recipient_id: str) -> dict[str, Any]:
        recipient = db.get(ServiceOrderRecipient, str(recipient_id or "").strip())
        if recipient is None:
            raise ValueError("recipient_id not found")
        order = db.get(ServiceOrder, recipient.order_id)
        if order is None:
            raise ValueError("order not found")
        session = SurveySessionService.get_by_recipient(db, recipient.id)
        return {
            "ok": True,
            "state": _session_state(db, order=order, recipient=recipient, session=session),
        }
