"""Auto-seed removable demo data for salesman dashboard workspaces."""

from __future__ import annotations

import importlib.util
import json
import logging
import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackIndustry, FeedbackLocation, FeedbackResponse, FeedbackSession
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder
from app.services.customer_feedback.billing_service import FeedbackBillingService
from app.services.customer_feedback.feedback_results_aggregate import classify_pge, classify_yn
from app.services.customer_feedback.location_service import build_location_qr_token
from app.services.customer_feedback.seed_service import FeedbackSeedService
from app.services.customer_feedback.survey_config_service import (
    build_survey_config,
    get_system_template,
    template_for_step,
)
from app.services.customer_feedback.whatsapp_service import FeedbackWhatsappService
from app.services.org_enabled_services import (
    SERVICE_KEYS,
    merge_admin_allowed_services,
    parse_allowed_services,
    parse_enabled_services,
    serialize_allowed_services,
    serialize_enabled_services,
)
from app.services.platform_catalog_service import PlatformCatalogService

logger = logging.getLogger(__name__)

DEMO_ACCOUNT_PACK = "sales_demo_account_v1"
SALES_DEMO_PHONE_PREFIX = "+44770299"
_API_ROOT = Path(__file__).resolve().parents[2]

# Default demo volumes for a salesman workspace. Override via seed_for_org(counts=...).
DEFAULT_DEMO_COUNTS: dict[str, int] = {
    "interviews": 20,        # 4 "Advance" (pass) + 10 scoring > 50 (see _seed_interview_campaign)
    "ai_call_survey": 50,    # phone (AI call) survey responses
    "wa_survey": 200,        # WhatsApp survey responses
    "campaigns": 100,        # separate "sent" WhatsApp campaigns
    "campaign_members": 5,   # recipients per separate campaign
    "feedback_locations": 3, # QR Customer Feedback locations (one named "Demo")
}


def _load_seed_module(name: str) -> Any:
    path = _API_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"demo_seed_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load seed module: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"demo_seed_{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


def _org_already_seeded(db: Session, org_id: str) -> bool:
    orders = db.execute(select(ServiceOrder).where(ServiceOrder.org_id == org_id)).scalars().all()
    for order in orders:
        try:
            cfg = json.loads(order.config_json or "{}")
        except json.JSONDecodeError:
            cfg = {}
        if cfg.get("demo_account_pack") == DEMO_ACCOUNT_PACK:
            return True
    locs = db.execute(select(FeedbackLocation).where(FeedbackLocation.org_id == org_id)).scalars().all()
    for loc in locs:
        try:
            cfg = json.loads(loc.survey_config_json or "{}")
        except json.JSONDecodeError:
            cfg = {}
        if cfg.get("demo_account_pack") == DEMO_ACCOUNT_PACK:
            return True
    return False


class DemoAccountSeedService:
    @staticmethod
    def seed_for_org(
        db: Session,
        *,
        org_id: str,
        user_id: str,
        counts: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        if _org_already_seeded(db, org_id):
            logger.info("demo_seed_skipped_already_seeded", extra={"org_id": org_id})
            return {"ok": True, "skipped": True, "reason": "already_seeded"}

        org = db.get(Organisation, org_id)
        if org is None:
            return {"ok": False, "error": "organisation_not_found"}

        vol = {**DEFAULT_DEMO_COUNTS, **(counts or {})}

        PlatformCatalogService.ensure_defaults(db)
        FeedbackSeedService.ensure_seeded(db)
        DemoAccountSeedService._enable_dashboard_modules(db, org)
        DemoAccountSeedService._ensure_feedback_subscription(db, org_id)

        interview_mod = _load_seed_module("seed_dummy_interview")
        user_account = _load_seed_module("seed_demo_user_account")
        user_account.DEMO_ACCOUNT_PACK = DEMO_ACCOUNT_PACK

        org_name = org.name or "Sales Demo"
        auto_top_up = True
        seed = 42
        debits: list[int] = []

        interview_order = DemoAccountSeedService._seed_interview_campaign(
            db,
            org_id=org_id,
            user_id=user_id,
            org=org,
            org_name=org_name,
            interview_mod=interview_mod,
            user_account=user_account,
            auto_top_up=auto_top_up,
            debits=debits,
            seed=seed,
            count=int(vol["interviews"]),
        )
        ai_order = user_account.seed_consolidated_survey(
            db,
            org_id=org_id,
            user_id=user_id,
            org=org,
            auto_top_up=auto_top_up,
            channel="ai_call",
            member_count=int(vol["ai_call_survey"]),
            title=f"Demo · AI Call Survey · {int(vol['ai_call_survey'])} members",
            seed=seed,
            debits=debits,
        )
        wa_order = user_account.seed_consolidated_survey(
            db,
            org_id=org_id,
            user_id=user_id,
            org=org,
            auto_top_up=auto_top_up,
            channel="wa",
            member_count=int(vol["wa_survey"]),
            title=f"Demo · WhatsApp Survey · {int(vol['wa_survey'])} members",
            seed=seed + 100,
            debits=debits,
        )

        # 100 separate "sent" campaigns so the surveys/campaigns history looks populated.
        campaign_ids: list[str] = []
        members_each = max(1, int(vol["campaign_members"]))
        for n in range(int(vol["campaigns"])):
            camp = user_account.seed_consolidated_survey(
                db,
                org_id=org_id,
                user_id=user_id,
                org=org,
                auto_top_up=auto_top_up,
                channel="wa",
                member_count=members_each,
                title=f"Demo Campaign #{n + 1:03d} · WhatsApp",
                seed=seed + 3000 + n,
                debits=debits,
            )
            campaign_ids.append(camp.id)

        feedback_locations = DemoAccountSeedService._seed_feedback_locations(
            db,
            org_id=org_id,
            org=org,
            seed=seed,
            location_count=int(vol["feedback_locations"]),
        )

        db.refresh(org)
        logger.info(
            "demo_seed_complete",
            extra={
                "org_id": org_id,
                "interview": interview_order.id,
                "ai_survey": ai_order.id,
                "wa_survey": wa_order.id,
                "campaigns": len(campaign_ids),
                "feedback_locations": len(feedback_locations),
            },
        )
        return {
            "ok": True,
            "skipped": False,
            "interview_order_id": interview_order.id,
            "ai_survey_order_id": ai_order.id,
            "wa_survey_order_id": wa_order.id,
            "campaign_order_ids": campaign_ids,
            "feedback_location_ids": feedback_locations,
        }

    @staticmethod
    def _enable_dashboard_modules(db: Session, org: Organisation) -> None:
        all_on = {key: True for key in SERVICE_KEYS}
        allowed = parse_allowed_services(org.allowed_services_json)
        enabled = parse_enabled_services(org.enabled_services_json)
        new_allowed, _ = merge_admin_allowed_services(allowed, enabled, all_on)
        org.allowed_services_json = serialize_allowed_services(new_allowed)
        org.enabled_services_json = serialize_enabled_services(dict(all_on))
        org.onboarding_state = "onboarding_completed"
        db.add(org)
        db.commit()
        db.refresh(org)

    @staticmethod
    def _ensure_feedback_subscription(db: Session, org_id: str) -> None:
        if FeedbackBillingService.get_active_subscription(db, org_id) is not None:
            return
        try:
            FeedbackBillingService.admin_assign_plan(
                db,
                org_id=org_id,
                plan_code="cf_business_gb",
                status="active",
            )
        except Exception as exc:
            logger.warning("demo_seed_feedback_subscription_failed", extra={"org_id": org_id, "error": str(exc)})

    @staticmethod
    def _seed_interview_campaign(
        db: Session,
        *,
        org_id: str,
        user_id: str,
        org: Organisation,
        org_name: str,
        interview_mod: Any,
        user_account: Any,
        auto_top_up: bool,
        debits: list[int],
        seed: int,
        count: int = 20,
    ) -> ServiceOrder:
        from app.services.interview_analysis_service import refresh_order_interview_report
        from app.services.platform_catalog_service import ServiceOrderService

        ROLE = interview_mod.ROLE
        contacts = user_account._interview_contacts_batch(count, success_email=None)
        config = user_account._tag_config(interview_mod._demo_config(org_name))
        config["ats_skipped"] = False
        config["delivery"] = "ai_call"
        config["demo_account_pack"] = DEMO_ACCOUNT_PACK

        order = ServiceOrderService.create_order(
            db,
            org_id=org_id,
            user_id=user_id,
            service_code="interview",
            title=f"Demo Interview · {ROLE} · {count} candidates",
            config=config,
        )
        ServiceOrderService.replace_recipients(db, order, contacts)
        db.refresh(order)
        user_account._enrich_all_ats(db, order, highlight_email=None)
        order = user_account.charge_interview_from_wallet(
            db, order, org, user_id=user_id, auto_top_up=auto_top_up, debits=debits
        )

        recipients = ServiceOrderService.get_recipients(db, order.id)
        for idx, recipient in enumerate(recipients):
            if not recipient.phone:
                continue
            row_num = recipient.row_number or (idx + 1)
            if idx < 4:
                score, recommendation, sentiment = 88 + (idx % 5), "Advance", "Enthusiastic"
            elif idx < 10:
                score, recommendation, sentiment = 58 + (idx % 14), "Hold", "Neutral"
            else:
                score, recommendation, sentiment = 42 + (idx % 8), "Decline", "Hesitant"
            payload = DemoAccountSeedService._interview_result_payload(
                interview_mod,
                row_num,
                recipient.name or "Candidate",
                score=score,
                recommendation=recommendation,
                sentiment=sentiment,
            )
            recipient.status = "completed"
            recipient.result_json = json.dumps(payload, ensure_ascii=False)
            db.add(recipient)
        db.commit()

        order = interview_mod._mark_order_finished(db, order)
        refresh_order_interview_report(db, order)
        db.refresh(order)
        return order

    @staticmethod
    def _interview_result_payload(
        interview_mod: Any,
        row_number: int,
        name: str,
        *,
        score: int,
        recommendation: str,
        sentiment: str,
    ) -> dict[str, Any]:
        from app.services.interview_analysis_service import INTERVIEW_ANALYSIS_VERSION

        rng = random.Random(row_number * 3571)
        answers = []
        for q in interview_mod.SCREENING_QUESTIONS[:3]:
            answers.append(
                {
                    "question": q,
                    "answer": f"{name.split()[0]} gave a structured answer with concrete examples.",
                    "quality": rng.choice(["strong", "adequate", "weak"]),
                }
            )
        duration = rng.randint(360, 720)
        transcript = (
            f"Agent: Hello {name}, thanks for joining.\n"
            f"Candidate: Happy to speak about the {interview_mod.ROLE} role.\n"
            + "\n".join(f"Agent: {q}\nCandidate: [detailed response]" for q in interview_mod.SCREENING_QUESTIONS)
            + "\nAgent: Thank you, we will be in touch."
        )
        return {
            "analysis": {
                "short_summary": f"{name} completed screening with score {score}.",
                "score": score,
                "recommendation": recommendation,
                "sentiment": sentiment,
                "strengths": ["Clear communication", "Relevant stack experience"],
                "concerns": [] if score >= 80 else ["Limited leadership examples"],
                "key_answers": answers,
                "completion_quality": "complete",
            },
            "analysis_saved_at": datetime.utcnow().isoformat(),
            "analysis_version": INTERVIEW_ANALYSIS_VERSION,
            "duration_seconds": duration,
            "transcript": transcript,
            "terminal_status": "completed",
            "call_summary": f"Screening completed — {recommendation}.",
            "call_control_id": f"demo-cc-{row_number:04d}",
            "provider": "telnyx_voice",
        }

    @staticmethod
    def _seed_feedback_locations(
        db: Session,
        *,
        org_id: str,
        org: Organisation,
        seed: int,
        location_count: int = 3,
    ) -> list[str]:
        feedback_seed = _load_seed_module("seed_feedback_responses_mixed")
        industry = db.execute(
            select(FeedbackIndustry).where(FeedbackIndustry.slug == "fitness").limit(1)
        ).scalar_one_or_none()
        if industry is None:
            logger.warning("demo_seed_no_feedback_industry")
            return []

        from app.models.customer_feedback import FeedbackSurveyType

        st = db.execute(
            select(FeedbackSurveyType)
            .where(FeedbackSurveyType.industry_id == industry.id)
            .order_by(FeedbackSurveyType.sort_order)
            .limit(1)
        ).scalar_one_or_none()
        if st is None:
            return []

        location_ids: list[str] = []
        rng = random.Random(seed)
        # First location is plainly "Demo" (the one to show the QR for); the rest are branches.
        all_branch_names = ["Demo", "Demo · West End", "Demo · Riverside", "Demo · North", "Demo · South"]
        location_count = max(1, int(location_count))
        branch_names = [all_branch_names[i % len(all_branch_names)] for i in range(location_count)]
        counts = [rng.randint(100, 200) for _ in range(location_count)]

        for branch_idx, (branch_name, count) in enumerate(zip(branch_names, counts)):
            survey_config = build_survey_config(
                db,
                industry_id=industry.id,
                selected_type_ids=[st.id],
                open_question_enabled=True,
                marketing_opt_in_enabled=False,
            )
            survey_config["demo_account_pack"] = DEMO_ACCOUNT_PACK
            qr_token = build_location_qr_token(company=org.name or "Demo", branch=branch_name)
            while db.execute(select(FeedbackLocation.qr_token).where(FeedbackLocation.qr_token == qr_token)).scalar_one_or_none():
                qr_token = build_location_qr_token(company=org.name or "Demo", branch=f"{branch_name}-{branch_idx}")

            now = datetime.utcnow()
            location = FeedbackLocation(
                id=str(uuid.uuid4()),
                org_id=org_id,
                industry_id=industry.id,
                survey_type_id=st.id,
                name=branch_name,
                branch_code=f"DEMO{branch_idx + 1}",
                qr_token=qr_token,
                wa_sender_country="gb",
                status="active",
                scan_count=0,
                selected_survey_type_ids_json=json.dumps([st.id]),
                open_question_enabled=True,
                marketing_opt_in_enabled=False,
                survey_config_json=json.dumps(survey_config),
                created_at=now,
                updated_at=now,
            )
            db.add(location)
            db.flush()
            DemoAccountSeedService._seed_feedback_sessions(
                db,
                org_id=org_id,
                location=location,
                count=count,
                seed=seed + branch_idx * 1000,
                feedback_seed=feedback_seed,
            )
            location.scan_count = max(int(location.scan_count or 0), count + 15)
            db.add(location)
            location_ids.append(location.id)

        db.commit()
        return location_ids

    @staticmethod
    def _seed_feedback_sessions(
        db: Session,
        *,
        org_id: str,
        location: FeedbackLocation,
        count: int,
        seed: int,
        feedback_seed: Any,
    ) -> None:
        random.seed(seed)
        steps = feedback_seed._answerable_steps(db, location)
        if not steps:
            return

        now = datetime.utcnow()
        unhappy_target = max(1, round(count * 35 / 100))
        unhappy_indices = set(random.sample(range(count), k=min(unhappy_target, count)))

        for i in range(count):
            happy = i not in unhappy_indices
            phone = f"{SALES_DEMO_PHONE_PREFIX}{i:04d}"
            days_ago = random.randint(0, 56)
            started = now - timedelta(days=days_ago, hours=random.randint(1, 20), minutes=random.randint(0, 59))
            completed = started + timedelta(minutes=random.randint(3, 25))

            session = FeedbackSession(
                id=str(uuid.uuid4()),
                org_id=org_id,
                location_id=location.id,
                visitor_phone=phone,
                status="completed",
                current_step=len(steps),
                detected_language="en_GB",
                trigger_dedupe_key=f"{phone}:{location.qr_token}",
                started_at=started,
                completed_at=completed,
                created_at=started,
            )
            db.add(session)
            db.flush()

            step_order = 0
            had_poor = False
            for step in steps:
                tpl = template_for_step(db, location, step, language="en_GB")
                if tpl is None and step.get("kind") == "open_question":
                    tpl = get_system_template(db, "open_question", language="en_GB")
                if tpl is None:
                    continue
                answer_en, original = feedback_seed._answer_for_template(tpl, happy=happy)
                if classify_pge(answer_en) == "poor" or classify_yn(answer_en) == "no":
                    had_poor = True
                step_order += 1
                survey_type_id = str(step.get("survey_type_id") or location.survey_type_id)
                db.add(
                    FeedbackResponse(
                        id=str(uuid.uuid4()),
                        session_id=session.id,
                        org_id=org_id,
                        location_id=location.id,
                        survey_type_id=survey_type_id,
                        question_key=tpl.template_key,
                        answer_text=answer_en,
                        answer_text_en=answer_en,
                        original_text=original,
                        step_order=step_order,
                        answer_source="text",
                        created_at=completed,
                    )
                )

            if not happy and had_poor:
                tell_more = get_system_template(db, "tell_us_more", language="en_GB")
                if tell_more:
                    text = random.choice(feedback_seed.TELL_US_MORE)
                    step_order += 1
                    db.add(
                        FeedbackResponse(
                            id=str(uuid.uuid4()),
                            session_id=session.id,
                            org_id=org_id,
                            location_id=location.id,
                            survey_type_id=str(location.survey_type_id),
                            question_key=tell_more.template_key,
                            answer_text=text,
                            answer_text_en=text,
                            original_text=text,
                            step_order=step_order,
                            answer_source="text",
                            created_at=completed,
                        )
                    )

            if (i + 1) % 50 == 0:
                db.commit()

        db.commit()
