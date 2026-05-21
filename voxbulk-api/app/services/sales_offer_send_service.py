from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.sales_offer_email_default import SALES_OFFER_EMAIL_BODY, SALES_OFFER_EMAIL_SUBJECT, SALES_OFFER_WHATSAPP_BODY
from app.models.lead_sales_task import LeadSalesTask
from app.models.plan import Plan
from app.models.promo_offer import PromoOffer
from app.services.promo_offer_service import PromoOfferService
from app.services.smtp_mailer_service import SmtpMailerError, SmtpMailerService
from app.services.telnyx_messaging_service import TelnyxMessagingService
from app.services.transactional_email_service import TransactionalEmailService, substitute_placeholders


class SalesOfferSendError(RuntimeError):
    pass


class SalesOfferSendService:
    @staticmethod
    def _first_name(contact_name: str | None) -> str:
        if contact_name and contact_name.strip():
            return contact_name.strip().split()[0]
        return "there"

    @staticmethod
    def _trial_line(trial_days: int) -> str:
        return f"{trial_days}-day free trial" if trial_days else "special offer"

    @staticmethod
    def _offer_line(*, offer_type: str, trial_days: int = 0, survey_contacts: int = 0, interview_contacts: int = 0) -> str:
        if offer_type == "survey_credits":
            count = max(0, int(survey_contacts or 0))
            label = "free survey contact" if count == 1 else "free survey contacts"
            return f"{count} {label}" if count else "free survey offer"
        if offer_type == "interview_credits":
            count = max(0, int(interview_contacts or 0))
            label = "free interview" if count == 1 else "free interviews"
            return f"{count} {label}" if count else "free interview offer"
        return SalesOfferSendService._trial_line(int(trial_days or 0))

    @staticmethod
    def _offer_summary(
        *,
        offer_type: str,
        plan: Plan | None,
        trial_days: int = 0,
        survey_contacts: int = 0,
        interview_contacts: int = 0,
    ) -> str:
        if offer_type == "survey_credits":
            count = max(0, int(survey_contacts or 0))
            return f"Includes {count} survey contact{'s' if count != 1 else ''} after signup."
        if offer_type == "interview_credits":
            count = max(0, int(interview_contacts or 0))
            return f"Includes {count} AI interview session{'s' if count != 1 else ''} after signup."
        summary = SalesOfferSendService._plan_summary(plan, trial_days=trial_days)
        return summary or (f"{trial_days}-day trial included" if trial_days else "Special subscription offer")

    @staticmethod
    def _variables_from_promo(
        *,
        contact_name: str | None,
        promo: PromoOffer,
        signup_url: str,
        plan: Plan | None,
    ) -> dict[str, str]:
        offer_type = PromoOfferService.normalize_offer_type(promo.offer_type)
        trial_days = int(promo.trial_days or 0)
        survey_contacts = int(promo.survey_contacts_included or 0)
        interview_contacts = int(promo.interview_contacts_included or 0)
        offer_line = SalesOfferSendService._offer_line(
            offer_type=offer_type,
            trial_days=trial_days,
            survey_contacts=survey_contacts,
            interview_contacts=interview_contacts,
        )
        offer_summary = SalesOfferSendService._offer_summary(
            offer_type=offer_type,
            plan=plan,
            trial_days=trial_days,
            survey_contacts=survey_contacts,
            interview_contacts=interview_contacts,
        )
        first = SalesOfferSendService._first_name(contact_name)
        plan_summary = SalesOfferSendService._plan_summary(plan, trial_days=trial_days)
        return {
            "first_name": first,
            "offer_line": offer_line,
            "offer_summary": offer_summary,
            "trial_line": offer_line,
            "promo_name": promo.name,
            "plan_summary": plan_summary or offer_summary,
            "signup_url": signup_url,
            "plan_name": plan.name if plan else "",
            "plan_price": f"£{int(plan.price_gbp_pence or 0) / 100:.0f}" if plan else "",
            "trial_days": str(trial_days),
            "survey_contacts_included": str(survey_contacts),
            "interview_contacts_included": str(interview_contacts),
            "calls_included": str(int(plan.calls_included or 0) if plan else 0),
            "whatsapp_included": str(int(plan.whatsapp_included or 0) if plan else 0),
            "sms_included": str(int(plan.sms_included or 0) if plan else 0),
        }

    @staticmethod
    def _plan_summary(plan: Plan | None, *, trial_days: int) -> str:
        if plan is None:
            return f"{trial_days}-day trial included" if trial_days else "Special offer"
        price = f"£{int(plan.price_gbp_pence or 0) / 100:.0f}/mo"
        parts = []
        if int(plan.calls_included or 0) > 0:
            parts.append(f"{plan.calls_included} calls")
        if int(plan.whatsapp_included or 0) > 0:
            parts.append(f"{plan.whatsapp_included} WhatsApp")
        if int(plan.sms_included or 0) > 0:
            parts.append(f"{plan.sms_included} SMS")
        quota = ", ".join(parts) if parts else "usage limits apply"
        return f"{plan.name} · {price} · {quota}"

    @staticmethod
    def _template_variables(
        *,
        contact_name: str | None,
        promo_name: str,
        signup_url: str,
        trial_days: int,
        plan: Plan | None,
    ) -> dict[str, str]:
        first = SalesOfferSendService._first_name(contact_name)
        trial_line = SalesOfferSendService._trial_line(trial_days)
        return {
            "first_name": first,
            "trial_line": trial_line,
            "promo_name": promo_name,
            "plan_summary": SalesOfferSendService._plan_summary(plan, trial_days=trial_days),
            "signup_url": signup_url,
            "plan_name": plan.name if plan else "",
            "plan_price": f"£{int(plan.price_gbp_pence or 0) / 100:.0f}" if plan else "",
            "trial_days": str(trial_days),
            "calls_included": str(int(plan.calls_included or 0) if plan else 0),
            "whatsapp_included": str(int(plan.whatsapp_included or 0) if plan else 0),
            "sms_included": str(int(plan.sms_included or 0) if plan else 0),
        }

    @staticmethod
    def _whatsapp_body(db: Session, variables: dict[str, str]) -> str:
        from app.services.whatsapp_template_service import WhatsAppTemplateService

        return WhatsAppTemplateService.render_body(
            db,
            template_key="sales_offer",
            variables=variables,
            fallback=SALES_OFFER_WHATSAPP_BODY,
        )

    @staticmethod
    def _log_sales_whatsapp(db: Session, *, task: LeadSalesTask, body: str, result) -> None:
        from app.services.sales_automation_service import SalesAutomationService

        org_id = SalesAutomationService._platform_org_id(db)
        if org_id and result.ok:
            try:
                TelnyxMessagingService.log_outbound(
                    db,
                    org_id=org_id,
                    to_number=task.phone or "",
                    from_number=None,
                    body=body,
                    result=result,
                )
            except Exception:
                pass

    @staticmethod
    def _send_email(db: Session, *, to_addr: str, variables: dict[str, str]) -> None:
        sent, err = TransactionalEmailService.send_templated_optional(
            db,
            template_key="sales_offer",
            to_email=to_addr,
            variables=variables,
        )
        if sent:
            return
        if err and err not in ("unknown_template", None):
            raise SmtpMailerError(err)
        subject = substitute_placeholders(SALES_OFFER_EMAIL_SUBJECT, variables)
        body = substitute_placeholders(SALES_OFFER_EMAIL_BODY, variables)
        SmtpMailerService.send_html(db, to_addr=to_addr, subject=subject, body=body)

    @staticmethod
    def send_for_task(
        db: Session,
        *,
        task: LeadSalesTask,
        offer_type: str = "dental_trial",
        plan_code: str = "dental_1",
        trial_days: int = 15,
        free_call_credits: int = 0,
        survey_contacts_included: int = 0,
        interview_contacts_included: int = 0,
        send_email: bool = True,
        send_whatsapp: bool = True,
    ) -> dict:
        if not task.email and not task.phone:
            raise SalesOfferSendError("Lead has no email or phone number")

        promo = PromoOfferService.create_for_sales_task(
            db,
            task_id=task.id,
            contact_name=task.contact_name,
            email=task.email,
            phone=task.phone,
            offer_type=offer_type,
            plan_code=plan_code,
            trial_days=trial_days,
            free_call_credits=free_call_credits,
            survey_contacts_included=survey_contacts_included,
            interview_contacts_included=interview_contacts_included,
        )
        signup_url = PromoOfferService.signup_url(promo.code)
        plan = None
        if promo.plan_code:
            plan = db.execute(select(Plan).where(Plan.code == promo.plan_code.strip().lower())).scalar_one_or_none()
        if plan is None and plan_code:
            plan = db.execute(select(Plan).where(Plan.code == plan_code.strip().lower())).scalar_one_or_none()
        variables = SalesOfferSendService._variables_from_promo(
            contact_name=task.contact_name,
            promo=promo,
            signup_url=signup_url,
            plan=plan,
        )
        plain = SalesOfferSendService._whatsapp_body(db, variables)

        log: dict = {"promo_code": promo.code, "signup_url": signup_url, "email": None, "whatsapp": None}
        errors: list[str] = []

        if send_email and task.email:
            try:
                SalesOfferSendService._send_email(db, to_addr=task.email, variables=variables)
                log["email"] = {"ok": True, "to": task.email}
            except SmtpMailerError as e:
                log["email"] = {"ok": False, "error": str(e)}
                errors.append(f"Email: {e}")

        if send_whatsapp and task.phone:
            try:
                result = TelnyxMessagingService.send_whatsapp(db, to_number=task.phone, body=plain, org_id=None, meter_usage=False)
                SalesOfferSendService._log_sales_whatsapp(db, task=task, body=plain, result=result)
                if not result.ok:
                    raise RuntimeError(result.detail or result.status)
                log["whatsapp"] = {"ok": True, "to": task.phone, "message_id": result.external_id}
            except Exception as e:
                log["whatsapp"] = {"ok": False, "error": str(e)}
                errors.append(f"WhatsApp: {e}")

        if send_email and not log.get("email") and task.email:
            errors.append("Email not sent")
        if send_whatsapp and not log.get("whatsapp") and task.phone:
            errors.append("WhatsApp not sent")

        if errors and not any((log.get("email") or {}).get("ok") or (log.get("whatsapp") or {}).get("ok")):
            raise SalesOfferSendError("; ".join(errors))

        task.offer_promo_code = promo.code
        task.offer_sent_at = datetime.utcnow()
        task.offer_send_log_json = json.dumps(log)
        task.updated_at = datetime.utcnow()
        db.add(task)
        db.commit()
        db.refresh(task)

        from app.services.sales_automation_service import SalesAutomationService

        SalesAutomationService.mark_offer_sent(db, task=task, promo=promo)

        log["partial_errors"] = errors
        log["ok"] = True
        return log
