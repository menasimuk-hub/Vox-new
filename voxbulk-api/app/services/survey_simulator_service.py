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
from app.services.survey_flow_constants import FLOW_ENGINE_GRAPH, FLOW_ENGINE_LINEAR
from app.services.survey_flow_picker_service import SurveyFlowPickerService
from app.services.survey_picker_settings_service import SurveyPickerSettingsService
from app.services.survey_generation_service import SurveyGenerationService
from app.services.survey_session_service import SurveySessionService
from app.services.survey_wa_test_pack_seed_service import SurveyWaTestPackSeedService
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
    }
    if session:
        picker_dbg = SurveyFlowPickerService.latest_picker_debug(db, session.id)
        if picker_dbg:
            state["picker_debug"] = picker_dbg
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
    ) -> dict[str, Any]:
        SurveyWaTestPackSeedService.ensure_test_pack(db)
        pm = normalize_privacy_mode(privacy_mode)
        engine = str(flow_engine or FLOW_ENGINE_LINEAR).strip().lower()
        roles = selected_step_roles
        if not roles:
            roles = ["start", "rating", "yes_no", "helpfulness", "reason", "completion"]

        branches = flow_branches
        if branches is None:
            branches = AI_PICKER_TEST_BRANCHES if ai_picker_enabled else DEFAULT_GRAPH_BRANCHES

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
        return {
            "ok": True,
            "state": _session_state(db, order=order, recipient=recipient, session=session),
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
