from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.sales_offer_email_default import SALES_OFFER_WHATSAPP_BODY
from app.models.lead_sales_task import LeadSalesTask
from app.models.plan import Plan
from app.models.promo_offer import PromoOffer
from app.services.promo_offer_service import PromoOfferService
from app.services.smtp_mailer_service import SmtpMailerError, SmtpMailerService
from app.services.telnyx_messaging_service import TelnyxMessagingService
from app.services.transactional_email_service import TransactionalEmailService


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
        if err in (None, "unknown_template"):
            raise SmtpMailerError(
                "sales_offer email template is disabled. Enable it under Admin → Email settings."
            )
        raise SmtpMailerError(err or "sales_offer email could not be sent — check SMTP settings.")

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
        expires_in_days: int = 30,
        template_name: str | None = None,
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
            expires_in_days=expires_in_days,
            template_name=template_name,
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

        log: dict = {
            "promo_code": promo.code,
            "signup_url": signup_url,
            "template_name": template_name,
            "email": None,
            "whatsapp": None,
        }
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
                from app.services.sales_whatsapp_send_service import send_sales_whatsapp

                result = send_sales_whatsapp(
                    db,
                    to_number=task.phone,
                    template_key="sales_offer",
                    body=plain,
                    variables=variables,
                )
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

        email_ok = bool((log.get("email") or {}).get("ok"))
        whatsapp_ok = bool((log.get("whatsapp") or {}).get("ok"))
        if errors and not email_ok and not whatsapp_ok:
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

    @staticmethod
    def send_for_task_with_template(
        db: Session,
        *,
        task: LeadSalesTask,
        template,
        send_email: bool = True,
        send_whatsapp: bool = True,
    ) -> dict:
        from app.services.promo_offer_service import PromoOfferService

        offer_type = PromoOfferService.normalize_offer_type(template.offer_type)
        plan_code = str(template.plan_code or "dental_1")
        return SalesOfferSendService.send_for_task(
            db,
            task=task,
            offer_type=offer_type,
            plan_code=plan_code,
            trial_days=int(template.trial_days or 0),
            free_call_credits=int(template.free_call_credits or 0),
            survey_contacts_included=int(template.survey_contacts_included or 0),
            interview_contacts_included=int(template.interview_contacts_included or 0),
            expires_in_days=int(template.expires_in_days or 30),
            template_name=str(template.name or "").strip() or None,
            send_email=send_email,
            send_whatsapp=send_whatsapp,
        )


def _parse_task_outcome(task: LeadSalesTask) -> dict:
    raw = str(task.outcome_json or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _platform_admin_notification_email(db: Session) -> str | None:
    from app.models.frontpage_call_setting import FrontpageCallSetting
    from app.models.organisation import Organisation
    from app.models.user import User
    from app.services.sales_automation_service import SalesAutomationService
    from app.services.smtp_settings_service import SmtpSettingsService
    from app.services.usage_wallet_service import UsageWalletService

    org_id = SalesAutomationService._platform_org_id(db)
    if org_id:
        org = db.get(Organisation, org_id)
        if org and str(org.contact_email or "").strip():
            return str(org.contact_email).strip().lower()
        billing = UsageWalletService.get_org_billing_email(db, org_id)
        if billing:
            return billing

    frontpage = db.get(FrontpageCallSetting, "default")
    if frontpage and frontpage.org_id:
        org = db.get(Organisation, frontpage.org_id)
        if org and str(org.contact_email or "").strip():
            return str(org.contact_email).strip().lower()
        billing = UsageWalletService.get_org_billing_email(db, str(frontpage.org_id))
        if billing:
            return billing

    admin = db.execute(
        select(User.email).where(User.is_active.is_(True), User.is_superuser.is_(True)).limit(1)
    ).scalar_one_or_none()
    if admin:
        return str(admin).strip().lower()

    smtp_row = SmtpSettingsService.get_row(db)
    from_email = str(smtp_row.from_email or "").strip().lower()
    return from_email if from_email and "@" in from_email else None


def send_sale_confirmation_email(db: Session, task: LeadSalesTask) -> dict[str, object]:
    """Customer confirmation + internal alert when DeepSeek marks the call as a closed sale."""
    outcome = _parse_task_outcome(task)
    stage = str(outcome.get("deal_stage") or "").strip().lower()
    interested = bool(outcome.get("interested_to_buy"))
    demo_agreed = bool(outcome.get("demo_agreed"))
    if stage != "closed" and not interested and not demo_agreed:
        return {"ok": False, "skipped": True, "reason": "outcome_not_closed_sale"}

    first = SalesOfferSendService._first_name(task.contact_name)
    customer_result: dict[str, object] = {"ok": False, "skipped": True, "reason": "no_customer_email"}
    if task.email:
        subject = "Great news — your enquiry with VoxBulk is confirmed"
        body = f"""<!DOCTYPE html><html><body style="font-family:system-ui,sans-serif;max-width:560px;margin:24px auto;color:#0f172a;line-height:1.6;">
  <p>Hi <strong>{first}</strong>,</p>
  <p>Thank you for speaking with VoxBulk today. Your enquiry is confirmed and a team member will be in touch shortly.</p>
  <p>For more information, visit <a href="https://voxbulk.com">voxbulk.com</a>.</p>
  <p style="font-size:12px;color:#64748b;">— VOXBULK Sales</p>
</body></html>"""
        SmtpMailerService.send_html(db, to_addr=str(task.email).strip(), subject=subject, body=body)
        customer_result = {"ok": True, "to": task.email}

    admin_email = _platform_admin_notification_email(db)
    admin_result: dict[str, object] = {"ok": False, "skipped": True, "reason": "no_admin_email"}
    if admin_email:
        summary = str(outcome.get("outcome_summary") or "").strip() or "No summary available."
        transcript_excerpt = str(task.sales_transcript_text or "").strip()[:500]
        lead_name = str(task.contact_name or "Unknown").strip()
        company = str(task.company_name or "Unknown").strip()
        admin_subject = f"Sale closed — {lead_name} {company}".strip()
        admin_body = "\n".join(
            [
                f"Lead: {lead_name}",
                f"Company: {company}",
                f"Phone: {task.phone or '—'}",
                f"Email: {task.email or '—'}",
                "",
                f"Call summary: {summary}",
                "",
                "Transcript excerpt:",
                transcript_excerpt or "(not available yet)",
            ]
        )
        SmtpMailerService.send_plain(db, to_addr=admin_email, subject=admin_subject, body=admin_body)
        admin_result = {"ok": True, "to": admin_email}

    return {"ok": True, "customer": customer_result, "admin": admin_result}
