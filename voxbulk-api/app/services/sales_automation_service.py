from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.sales_automation_defaults import (
    SALES_OFFER_FOLLOWUP_WHATSAPP_BODY,
    SALES_OFFER_KEYWORD_CONFIRM_WHATSAPP_BODY,
    SALES_OPT_IN_WHATSAPP_BODY,
)
from app.models.lead_sales_task import LeadSalesTask
from app.models.plan import Plan
from app.models.promo_offer import PromoOffer
from app.models.sales_conversation_state import SalesConversationState
from app.services.agents.base import AgentMessage
from app.services.lead_sales_service import get_lead_sales_settings
from app.services.messaging_log_service import normalize_e164
from app.services.providers.openai_service import OpenAIProviderService
from app.services.sales_offer_send_service import SalesOfferSendError, SalesOfferSendService
from app.services.telnyx_messaging_service import TelnyxMessagingService
from app.services.transactional_email_service import substitute_placeholders

logger = logging.getLogger(__name__)

_OFFER_KEYWORD_RE = re.compile(
    r"\b(send\s*(me\s*)?(the\s*)?offer|get\s*(the\s*)?offer|yes\s*send|send\s*link|i\s*want\s*(the\s*)?offer)\b",
    re.I,
)
_STOP_RE = re.compile(r"\b(stop|unsubscribe|opt\s*out|leave\s*me\s*alone|do\s*not\s*contact|dont\s*contact)\b", re.I)
_HELP_RE = re.compile(
    r"\b(help|can't|cannot|dont\s*know|don't\s*know|how\s*do|confused|issue|problem|broken|stuck|support)\b",
    re.I,
)

_WA_TEMPLATE_FALLBACKS = {
    "sales_opt_in": SALES_OPT_IN_WHATSAPP_BODY,
    "sales_offer_followup": SALES_OFFER_FOLLOWUP_WHATSAPP_BODY,
    "sales_offer_keyword_confirm": SALES_OFFER_KEYWORD_CONFIRM_WHATSAPP_BODY,
}

_SALES_HELP_SYSTEM = (
    "You are VOXBULK sales support on WhatsApp. The customer received a trial signup link but has NOT signed up yet. "
    "Reply in 2-4 short sentences, British English, friendly and clear. "
    "Always include the signup URL when relevant. Give simple steps: tap link → create account → start trial. "
    "Do NOT tell them to use the dashboard chat panel — they do not have an account yet. "
    "If they need a human, say a team member will follow up. No markdown, no bullet lists."
)


class SalesAutomationService:
    @staticmethod
    def _now() -> datetime:
        return datetime.utcnow()

    @staticmethod
    def _normalize_phone(phone: str | None) -> str | None:
        raw = str(phone or "").strip()
        if not raw:
            return None
        try:
            return normalize_e164(raw)
        except ValueError:
            digits = re.sub(r"\D", "", raw)
            return digits or raw

    @staticmethod
    def _platform_org_id(db: Session) -> str | None:
        from app.services.provider_settings import ProviderSettingsService
        from app.models.organisation import Organisation

        cfg, _ = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
        config = cfg if isinstance(cfg, dict) else {}
        for candidate in (
            str(config.get("messaging_org_id") or "").strip(),
            str(config.get("default_messaging_org_id") or "").strip(),
        ):
            if candidate and db.get(Organisation, candidate):
                return candidate
        fallback = db.execute(select(Organisation.id).order_by(Organisation.created_at.asc()).limit(1)).scalar_one_or_none()
        return str(fallback) if fallback else None

    @staticmethod
    def _render_template(db: Session, *, template_key: str, variables: dict[str, str]) -> str:
        from app.services.whatsapp_template_service import WhatsAppTemplateService

        return WhatsAppTemplateService.render_body(
            db,
            template_key=template_key,
            variables=variables,
            fallback=_WA_TEMPLATE_FALLBACKS.get(template_key, ""),
        )

    @staticmethod
    def _template_variables(
        task: LeadSalesTask,
        *,
        signup_url: str = "",
        promo_name: str = "",
        trial_days: int = 0,
        promo: PromoOffer | None = None,
        plan: Plan | None = None,
    ) -> dict[str, str]:
        if promo is not None:
            return SalesOfferSendService._variables_from_promo(
                contact_name=task.contact_name,
                promo=promo,
                signup_url=signup_url,
                plan=plan,
            )
        first = SalesOfferSendService._first_name(task.contact_name)
        trial_line = SalesOfferSendService._trial_line(int(trial_days or 0))
        return {
            "first_name": first,
            "offer_line": trial_line,
            "offer_summary": promo_name or "VOXBULK trial",
            "trial_line": trial_line,
            "promo_name": promo_name or "VOXBULK trial",
            "signup_url": signup_url,
            "plan_summary": "",
            "plan_name": "",
            "plan_price": "",
            "trial_days": str(int(trial_days or 0)),
            "survey_contacts_included": "0",
            "interview_contacts_included": "0",
            "calls_included": "0",
            "whatsapp_included": "0",
            "sms_included": "0",
        }

    @staticmethod
    def _send_whatsapp(
        db: Session,
        *,
        task: LeadSalesTask,
        body: str,
        template_key: str | None = None,
        variables: dict[str, str] | None = None,
    ) -> tuple[bool, str | None]:
        if not task.phone:
            return False, "No phone number"
        text = body
        if template_key and variables is not None:
            text = SalesAutomationService._render_template(db, template_key=template_key, variables=variables)
        from app.services.sales_whatsapp_send_service import send_sales_whatsapp

        result = send_sales_whatsapp(
            db,
            to_number=task.phone,
            template_key=template_key,
            body=text,
            variables=variables,
        )
        org_id = SalesAutomationService._platform_org_id(db)
        if org_id:
            try:
                TelnyxMessagingService.log_outbound(
                    db,
                    org_id=org_id,
                    to_number=task.phone,
                    from_number=None,
                    body=text,
                    result=result,
                )
            except Exception:
                pass
        if not result.ok:
            return False, result.detail or result.status
        return True, result.external_id

    @staticmethod
    def get_state(db: Session, task_id: str) -> SalesConversationState | None:
        return db.execute(
            select(SalesConversationState).where(SalesConversationState.lead_sales_task_id == task_id)
        ).scalar_one_or_none()

    @staticmethod
    def get_or_create_state(db: Session, task: LeadSalesTask) -> SalesConversationState:
        row = SalesAutomationService.get_state(db, task.id)
        if row is not None:
            return row
        now = SalesAutomationService._now()
        row = SalesConversationState(
            lead_sales_task_id=task.id,
            prospect_phone=SalesAutomationService._normalize_phone(task.phone),
            prospect_email=(task.email or "").strip().lower() or None,
            stage="pending",
            automation_paused=bool(task.automation_paused),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def state_to_dict(row: SalesConversationState | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "id": row.id,
            "stage": row.stage,
            "automation_paused": bool(row.automation_paused),
            "opt_in_sent_at": row.opt_in_sent_at.isoformat() if row.opt_in_sent_at else None,
            "offer_sent_at": row.offer_sent_at.isoformat() if row.offer_sent_at else None,
            "followup_due_at": row.followup_due_at.isoformat() if row.followup_due_at else None,
            "followup_sent_at": row.followup_sent_at.isoformat() if row.followup_sent_at else None,
            "last_inbound_at": row.last_inbound_at.isoformat() if row.last_inbound_at else None,
            "last_outbound_at": row.last_outbound_at.isoformat() if row.last_outbound_at else None,
            "last_error": row.last_error,
        }

    @staticmethod
    def find_task_by_phone(db: Session, phone: str) -> LeadSalesTask | None:
        norm = SalesAutomationService._normalize_phone(phone)
        if not norm:
            return None
        tasks = db.execute(select(LeadSalesTask).order_by(LeadSalesTask.updated_at.desc()).limit(200)).scalars().all()
        for task in tasks:
            if SalesAutomationService._normalize_phone(task.phone) == norm:
                return task
        return None

    @staticmethod
    def _parse_outcome(task: LeadSalesTask) -> dict[str, Any]:
        raw = str(task.outcome_json or "").strip()
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _should_auto_offer(task: LeadSalesTask, outcome: dict[str, Any], *, call_status: str = "completed") -> bool:
        if call_status != "completed":
            return False
        stage = str(outcome.get("deal_stage") or "").strip().lower()
        if stage == "not_interested":
            return False
        if outcome.get("interested_to_buy") or outcome.get("demo_agreed"):
            return True
        if stage in {"won_intent", "demo_booked", "qualified", "follow_up"}:
            return True
        transcript = str(task.sales_transcript_text or "").strip()
        if len(transcript) >= 60:
            return True
        # Completed outbound call — send offer even when Telnyx transcript is still syncing.
        return bool(task.email or task.phone)

    @staticmethod
    def _set_task_error(db: Session, task: LeadSalesTask, message: str | None) -> None:
        task.last_error = (str(message or "").strip() or None)[:2000] if message else None
        task.updated_at = SalesAutomationService._now()
        db.add(task)
        state = SalesAutomationService.get_state(db, task.id)
        if state is not None:
            state.last_error = task.last_error
            state.updated_at = SalesAutomationService._now()
            db.add(state)
        db.commit()

    @staticmethod
    def _apply_automation_result(db: Session, task: LeadSalesTask, result: dict[str, Any]) -> None:
        db.refresh(task)
        if result.get("ok"):
            task.last_error = None
        elif result.get("error"):
            task.last_error = str(result["error"])[:2000]
        elif result.get("skipped"):
            reason = str(result.get("reason") or "").strip()
            if reason and reason not in {"offer_already_sent", "automation_disabled", "no_action_for_outcome"}:
                task.last_error = reason[:2000]
        task.updated_at = SalesAutomationService._now()
        db.add(task)
        state = SalesAutomationService.get_state(db, task.id)
        if state is not None:
            if result.get("error"):
                state.last_error = str(result["error"])[:2000]
            elif result.get("ok"):
                state.last_error = None
            state.updated_at = SalesAutomationService._now()
            db.add(state)
        db.commit()

    @staticmethod
    def run_post_call_automation(db: Session, task: LeadSalesTask, *, call_status: str = "completed") -> dict[str, Any]:
        try:
            result = SalesAutomationService.handle_post_call(db, task, call_status=call_status)
            SalesAutomationService._apply_automation_result(db, task, result)
            return result
        except Exception as exc:
            logger.exception("post_call_automation_failed", extra={"task_id": task.id})
            SalesAutomationService._set_task_error(db, task, str(exc))
            return {"ok": False, "error": str(exc)}

    @staticmethod
    def _should_send_opt_in(task: LeadSalesTask, outcome: dict[str, Any], *, call_status: str) -> bool:
        if call_status == "no_answer":
            return True
        stage = str(outcome.get("deal_stage") or "").strip().lower()
        return stage in {"follow_up", "not_interested", "no_answer"}

    @staticmethod
    def mark_offer_sent(
        db: Session,
        *,
        task: LeadSalesTask,
        promo: PromoOffer | None = None,
        followup_days: int | None = None,
    ) -> SalesConversationState:
        settings = get_lead_sales_settings(db)
        days = int(followup_days if followup_days is not None else settings.sales_followup_days or 7)
        now = SalesAutomationService._now()
        row = SalesAutomationService.get_or_create_state(db, task)
        row.stage = "offer_sent"
        row.offer_sent_at = task.offer_sent_at or now
        row.followup_due_at = row.offer_sent_at + timedelta(days=max(1, days))
        row.prospect_phone = SalesAutomationService._normalize_phone(task.phone)
        row.prospect_email = (task.email or "").strip().lower() or row.prospect_email
        if promo is not None:
            row.promo_offer_id = promo.id
        row.last_outbound_at = now
        row.updated_at = now
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def mark_signed_up(db: Session, *, promo_offer_id: str) -> None:
        row = db.execute(
            select(SalesConversationState).where(SalesConversationState.promo_offer_id == promo_offer_id)
        ).scalar_one_or_none()
        if row is None:
            return
        now = SalesAutomationService._now()
        row.stage = "signed_up"
        row.updated_at = now
        db.add(row)
        db.commit()

    @staticmethod
    def send_opt_in(db: Session, task: LeadSalesTask) -> dict[str, Any]:
        settings = get_lead_sales_settings(db)
        if not settings.sales_automation_enabled or task.automation_paused:
            return {"ok": False, "skipped": True, "reason": "automation_disabled"}
        row = SalesAutomationService.get_or_create_state(db, task)
        if row.automation_paused or row.stage in {"opted_out", "signed_up"}:
            return {"ok": False, "skipped": True, "reason": row.stage}
        if row.opt_in_sent_at and row.stage != "pending":
            return {"ok": False, "skipped": True, "reason": "opt_in_already_sent"}

        variables = SalesAutomationService._template_variables(task)
        ok, err = SalesAutomationService._send_whatsapp(
            db, task=task, body="", template_key="sales_opt_in", variables=variables
        )
        now = SalesAutomationService._now()
        if ok:
            row.stage = "opt_in_sent"
            row.opt_in_sent_at = now
            row.last_outbound_at = now
            row.last_error = None
        else:
            row.last_error = err
        row.updated_at = now
        db.add(row)
        db.commit()
        return {"ok": ok, "error": err, "stage": row.stage}

    @staticmethod
    def send_offer_for_task(
        db: Session,
        task: LeadSalesTask,
        *,
        source: str = "manual",
        resend_only: bool = False,
        template_id: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        force_resend: bool = False,
    ) -> dict[str, Any]:
        from app.services.sales_offer_template_service import resolve_template_for_task

        clean_email = str(email or "").strip().lower() or None
        clean_phone = str(phone or "").strip() or None
        if clean_email:
            task.email = clean_email
        if clean_phone:
            task.phone = clean_phone
        if clean_email or clean_phone:
            task.updated_at = SalesAutomationService._now()
            db.add(task)
            db.commit()
            db.refresh(task)

        if task.offer_sent_at and task.offer_promo_code and resend_only:
            from app.services.promo_offer_service import PromoOfferService

            promo = PromoOfferService.get_by_code(db, task.offer_promo_code)
            signup_url = PromoOfferService.signup_url(task.offer_promo_code) if promo else ""
            plan = None
            if promo and promo.plan_code:
                plan = db.execute(select(Plan).where(Plan.code == promo.plan_code.strip().lower())).scalar_one_or_none()
            variables = SalesAutomationService._template_variables(
                task,
                signup_url=signup_url,
                promo_name=promo.name if promo else task.offer_promo_code,
                trial_days=int(promo.trial_days if promo else 15),
                promo=promo,
                plan=plan,
            )
            ok, err = SalesAutomationService._send_whatsapp(
                db,
                task=task,
                body="",
                template_key="sales_offer_keyword_confirm",
                variables=variables,
            )
            if ok:
                row = SalesAutomationService.get_or_create_state(db, task)
                now = SalesAutomationService._now()
                row.last_outbound_at = now
                row.updated_at = now
                db.add(row)
                db.commit()
            return {"ok": ok, "resent": True, "signup_url": signup_url, "error": err}

        template = resolve_template_for_task(db, task, template_id=template_id)
        if template is None:
            settings = get_lead_sales_settings(db)
            try:
                result = SalesOfferSendService.send_for_task(
                    db,
                    task=task,
                    offer_type=str(settings.sales_auto_offer_type or "dental_trial"),
                    plan_code=str(settings.sales_auto_plan_code or "dental_1"),
                    trial_days=int(settings.sales_auto_trial_days or 15),
                    send_email=bool(task.email),
                    send_whatsapp=bool(task.phone),
                )
            except SalesOfferSendError as exc:
                category = SalesAutomationService._parse_outcome(task).get("recommended_offer") or "subscription"
                SalesAutomationService._set_task_error(db, task, str(exc))
                return {
                    "ok": False,
                    "error": (
                        f"{exc} Also check Lead sales → Offer templates for {category} "
                        "and Admin → Email settings (SMTP)."
                    ),
                }
            result["template_id"] = None
            result["template_name"] = "Settings default offer"
            result["offer_type"] = str(settings.sales_auto_offer_type or "dental_trial")
            result["recommended_offer"] = SalesAutomationService._parse_outcome(task).get("recommended_offer")
            promo = None
            if task.offer_promo_code:
                promo = db.execute(select(PromoOffer).where(PromoOffer.code == task.offer_promo_code)).scalar_one_or_none()
            SalesAutomationService.mark_offer_sent(db, task=task, promo=promo)
            meta = {"last_offer_source": source}
            row = SalesAutomationService.get_state(db, task.id)
            if row is not None:
                row.meta_json = json.dumps(meta)
                row.last_error = None
                db.add(row)
                db.commit()
            task.last_error = None
            if result.get("partial_errors"):
                task.last_error = "; ".join(result["partial_errors"])[:2000]
                db.add(task)
                db.commit()
            result["automation"] = True
            result["ok"] = True
            return result

        try:
            result = SalesOfferSendService.send_for_task_with_template(
                db,
                task=task,
                template=template,
                send_email=bool(task.email),
                send_whatsapp=bool(task.phone),
            )
        except SalesOfferSendError as exc:
            SalesAutomationService._set_task_error(db, task, str(exc))
            return {"ok": False, "error": str(exc)}

        result["template_id"] = template.id
        result["template_name"] = template.name
        result["offer_type"] = template.offer_type
        result["recommended_offer"] = SalesAutomationService._parse_outcome(task).get("recommended_offer")

        promo = None
        if task.offer_promo_code:
            promo = db.execute(select(PromoOffer).where(PromoOffer.code == task.offer_promo_code)).scalar_one_or_none()
        SalesAutomationService.mark_offer_sent(db, task=task, promo=promo)
        meta = {"last_offer_source": source}
        row = SalesAutomationService.get_state(db, task.id)
        if row is not None:
            row.meta_json = json.dumps(meta)
            row.last_error = None
            db.add(row)
            db.commit()
        task.last_error = None
        if result.get("partial_errors"):
            task.last_error = "; ".join(result["partial_errors"])[:2000]
            db.add(task)
            db.commit()
        result["automation"] = True
        result["ok"] = True
        return result

    @staticmethod
    def handle_post_call(db: Session, task: LeadSalesTask, *, call_status: str = "completed") -> dict[str, Any]:
        settings = get_lead_sales_settings(db)
        if not settings.sales_automation_enabled or task.automation_paused:
            reason = "automation_disabled" if not settings.sales_automation_enabled else "automation_paused"
            logger.info(
                "post_call_automation_skipped",
                extra={"task_id": task.id, "reason": reason},
            )
            return {"ok": False, "skipped": True, "reason": reason}

        outcome = SalesAutomationService._parse_outcome(task)
        if task.offer_sent_at:
            return {"ok": False, "skipped": True, "reason": "offer_already_sent"}

        if not task.email and not task.phone:
            logger.info(
                "post_call_automation_skipped",
                extra={"task_id": task.id, "reason": "no_contact_details"},
            )
            return {"ok": False, "skipped": True, "reason": "no_contact_details"}

        if SalesAutomationService._should_auto_offer(task, outcome, call_status=call_status):
            logger.info(
                "post_call_automation_send_offer",
                extra={"task_id": task.id, "deal_stage": outcome.get("deal_stage")},
            )
            return SalesAutomationService.send_offer_for_task(db, task, source="post_call_auto_offer")

        if SalesAutomationService._should_send_opt_in(task, outcome, call_status=call_status):
            logger.info(
                "post_call_automation_send_opt_in",
                extra={"task_id": task.id, "deal_stage": outcome.get("deal_stage"), "call_status": call_status},
            )
            return SalesAutomationService.send_opt_in(db, task)

        logger.info(
            "post_call_automation_no_action",
            extra={"task_id": task.id, "deal_stage": outcome.get("deal_stage"), "call_status": call_status},
        )
        return {"ok": False, "skipped": True, "reason": "no_action_for_outcome"}

    @staticmethod
    def _promo_is_redeemed(db: Session, state: SalesConversationState) -> bool:
        if not state.promo_offer_id:
            return False
        promo = db.get(PromoOffer, state.promo_offer_id)
        if promo is None and state.lead_sales_task_id:
            task = db.get(LeadSalesTask, state.lead_sales_task_id)
            if task and task.offer_promo_code:
                promo = db.execute(select(PromoOffer).where(PromoOffer.code == task.offer_promo_code)).scalar_one_or_none()
        if promo is None:
            return False
        return int(promo.redemption_count or 0) >= int(promo.max_redemptions or 1)

    @staticmethod
    def process_due_followups(db: Session) -> dict[str, int]:
        now = SalesAutomationService._now()
        stats = {"checked": 0, "sent": 0, "skipped": 0, "errors": 0}
        rows = list(
            db.execute(
                select(SalesConversationState).where(
                    SalesConversationState.stage == "offer_sent",
                    SalesConversationState.followup_due_at <= now,
                    SalesConversationState.followup_sent_at.is_(None),
                    SalesConversationState.automation_paused.is_(False),
                )
            ).scalars().all()
        )
        for state in rows:
            stats["checked"] += 1
            if state.stage == "opted_out":
                stats["skipped"] += 1
                continue
            if SalesAutomationService._promo_is_redeemed(db, state):
                state.stage = "signed_up"
                state.updated_at = now
                db.add(state)
                stats["skipped"] += 1
                continue
            task = db.get(LeadSalesTask, state.lead_sales_task_id)
            if task is None or task.automation_paused:
                stats["skipped"] += 1
                continue
            from app.services.promo_offer_service import PromoOfferService

            signup_url = ""
            promo_name = "VOXBULK trial"
            trial_days = int(get_lead_sales_settings(db).sales_auto_trial_days or 15)
            promo = None
            plan = None
            if task.offer_promo_code:
                promo = PromoOfferService.get_by_code(db, task.offer_promo_code)
                if promo:
                    signup_url = PromoOfferService.signup_url(promo.code)
                    promo_name = promo.name
                    trial_days = int(promo.trial_days or trial_days)
                    if promo.plan_code:
                        plan = db.execute(select(Plan).where(Plan.code == promo.plan_code.strip().lower())).scalar_one_or_none()
            variables = SalesAutomationService._template_variables(
                task,
                signup_url=signup_url,
                promo_name=promo_name,
                trial_days=trial_days,
                promo=promo,
                plan=plan,
            )
            ok, err = SalesAutomationService._send_whatsapp(
                db, task=task, body="", template_key="sales_offer_followup", variables=variables
            )
            if ok:
                state.stage = "followup_sent"
                state.followup_sent_at = now
                state.last_outbound_at = now
                state.last_error = None
                stats["sent"] += 1
            else:
                state.last_error = err
                stats["errors"] += 1
            state.updated_at = now
            db.add(state)
        db.commit()
        return stats

    @staticmethod
    def _generate_help_reply(db: Session, *, task: LeadSalesTask, inbound_text: str, signup_url: str) -> str:
        user_block = "\n".join(
            [
                f"Contact: {task.contact_name or 'prospect'}",
                f"Company: {task.company_name or 'unknown'}",
                f"Signup URL: {signup_url or 'not available'}",
                f"Customer WhatsApp message: {inbound_text}",
            ]
        )
        try:
            result = OpenAIProviderService.complete(
                db,
                system_prompt=_SALES_HELP_SYSTEM,
                messages=[AgentMessage(role="user", content=user_block)],
                max_tokens=280,
                temperature=0.3,
                provider="deepseek",
            )
            text = str(result.assistant_text or "").strip()
            if text:
                if signup_url and signup_url not in text:
                    text = f"{text}\n\nYour signup link: {signup_url}"
                return text[:1200]
        except Exception as exc:
            logger.warning("sales_automation_ai_reply_failed", extra={"error": str(exc)})
        if signup_url:
            return (
                f"Hi {SalesOfferSendService._first_name(task.contact_name)}, no worries — tap this link to create your account: "
                f"{signup_url} If anything fails, reply here and we'll help."
            )
        return "Thanks for your message — a team member will follow up shortly."

    @staticmethod
    def handle_inbound_whatsapp(
        db: Session,
        *,
        from_phone: str,
        body: str,
        log_id: str | None = None,
    ) -> dict[str, Any]:
        text = str(body or "").strip()
        if not text:
            return {"ok": True, "ignored": True}

        task = SalesAutomationService.find_task_by_phone(db, from_phone)
        if task is None:
            return {"ok": True, "ignored": True, "reason": "no_matching_task"}

        state = SalesAutomationService.get_or_create_state(db, task)
        now = SalesAutomationService._now()
        state.last_inbound_at = now
        state.last_inbound_body = text[:2000]
        state.updated_at = now

        if state.automation_paused or task.automation_paused or state.stage == "opted_out":
            db.add(state)
            db.commit()
            return {"ok": True, "ignored": True, "reason": "paused_or_opted_out"}

        if _STOP_RE.search(text):
            state.stage = "opted_out"
            db.add(state)
            db.commit()
            ok, _ = SalesAutomationService._send_whatsapp(
                db,
                task=task,
                body="Understood — we won't message you again about this offer. Reply anytime if you change your mind.",
            )
            return {"ok": True, "action": "opted_out", "replied": ok}

        wants_offer = bool(_OFFER_KEYWORD_RE.search(text))
        if wants_offer:
            if task.offer_sent_at:
                result = SalesAutomationService.send_offer_for_task(db, task, source="keyword_resend", resend_only=True)
            else:
                result = SalesAutomationService.send_offer_for_task(db, task, source="keyword_offer")
            state.stage = "offer_sent" if result.get("ok") else state.stage
            db.add(state)
            db.commit()
            return {"ok": True, "action": "send_offer", "result": result}

        needs_help = bool(_HELP_RE.search(text)) or state.stage in {"offer_sent", "followup_sent", "opt_in_sent", "replied"}
        if needs_help and task.phone:
            from app.services.promo_offer_service import PromoOfferService

            signup_url = ""
            if task.offer_promo_code:
                signup_url = PromoOfferService.signup_url(task.offer_promo_code)
            reply = SalesAutomationService._generate_help_reply(db, task=task, inbound_text=text, signup_url=signup_url)
            ok, err = SalesAutomationService._send_whatsapp(db, task=task, body=reply)
            state.stage = "replied"
            state.last_outbound_at = now if ok else state.last_outbound_at
            state.last_error = err
            db.add(state)
            db.commit()
            return {"ok": ok, "action": "ai_help_reply", "error": err, "log_id": log_id}

        db.add(state)
        db.commit()
        return {"ok": True, "ignored": True, "reason": "no_matching_intent"}

    @staticmethod
    def set_task_automation_paused(db: Session, task: LeadSalesTask, paused: bool) -> SalesConversationState:
        task.automation_paused = bool(paused)
        task.updated_at = SalesAutomationService._now()
        db.add(task)
        row = SalesAutomationService.get_or_create_state(db, task)
        row.automation_paused = bool(paused)
        row.updated_at = SalesAutomationService._now()
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
