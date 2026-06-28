from __future__ import annotations

import csv
import io
import json
import logging
import re
import smtplib
import ssl
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.encryption import get_encryptor
from app.models.ai_team_message import AiTeamMessage
from app.models.ai_team_prospect import AiTeamProspect
from app.models.ai_team_settings import AiTeamSettings
from app.models.promo_offer import PromoOffer
from app.services.agents.base import AgentMessage
from app.services.apollo_service import ApolloService, ApolloServiceError
from app.services.promo_offer_service import PromoOfferService
from app.services.provider_settings import ProviderSettingsService
from app.services.providers.openai_service import OpenAIProviderService
from app.services.resend_service import ResendService, ResendServiceError

logger = logging.getLogger(__name__)

_DEFAULT_WRITING = (
    "Write a short, direct cold email to {first_name} who is {job_title} at {company} in the {sector} sector. "
    "Focus on saving time on customer feedback. Mention AI phone calls and WhatsApp surveys. "
    "Offer promo code {promo_code}. Under 120 words. No fluff. End with one soft question."
)
_DEFAULT_SIGNATURE = "Best,\nVoxBulk team · voxbulk.com"

_DEFAULT_EMAIL_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:'DM Sans',Arial,sans-serif;line-height:1.65;color:#2a2620;max-width:560px;margin:0 auto;padding:28px 24px;background:#fbf8f3;">
  <div style="background:#ffffff;border:1px solid rgba(42,38,32,0.08);border-radius:12px;padding:28px 24px;">
    <p style="margin:0 0 16px;font-size:15px;">Hi {{first_name}},</p>
    {{body}}
    <p style="margin:24px 0 0;font-size:14px;color:#6b6458;">Use code <strong style="color:#854F0B;font-family:monospace;">{{promo_code}}</strong> to start your free trial at {{company}}.</p>
    <p style="margin:28px 0 0;font-size:12px;color:#9a9288;border-top:1px solid rgba(42,38,32,0.08);padding-top:16px;">VoxBulk · voxbulk.com · outreach@voxbulk.com</p>
  </div>
</body>
</html>"""

_SAMPLE_PREVIEW_VARS = {
    "first_name": "Alex",
    "last_name": "Taylor",
    "company": "Example Estates Ltd",
    "promo_code": "TRIAL-EXAMPLE",
    "job_title": "Operations Director",
    "email": "alex.taylor@example.com",
    "sector": "property",
    "country_code": "GB",
    "body": (
        "I noticed Example Estates runs feedback across multiple branches. VoxBulk automates "
        "customer surveys by phone and WhatsApp and pushes results into your CRM before your team arrives."
    ),
}

_SECTOR_KEYWORDS = {
    "automotive": ["automotive", "aftersales", "dealership", "car"],
    "property": ["property", "estate", "real estate", "letting"],
    "dental": ["dental", "dentist", "clinic"],
    "recruitment": ["recruitment", "recruiting", "staffing", "hiring"],
}


class AiTeamServiceError(ValueError):
    pass


class AiTeamService:
    @staticmethod
    def _now() -> datetime:
        return datetime.utcnow()

    @staticmethod
    def get_settings(db: Session) -> AiTeamSettings:
        row = db.get(AiTeamSettings, "default")
        if row is None:
            now = AiTeamService._now()
            row = AiTeamSettings(
                id="default",
                search_title_keywords="",
                writing_instruction=_DEFAULT_WRITING,
                email_signature=_DEFAULT_SIGNATURE,
                updated_at=now,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
        return row

    @staticmethod
    def _provider_connection_flags(view: dict[str, Any]) -> tuple[bool, bool]:
        """Return (configured, api_key_set) from get_platform_config_admin_view."""
        secret_set = view.get("secret_set") if isinstance(view.get("secret_set"), dict) else {}
        api_key_set = bool(secret_set.get("api_key"))
        configured = bool(view.get("configured")) or api_key_set
        return configured, api_key_set

    @staticmethod
    def settings_to_dict(db: Session, row: AiTeamSettings) -> dict[str, Any]:
        apollo_view = ProviderSettingsService.get_platform_config_admin_view(db, provider="apollo")
        resend_view = ProviderSettingsService.get_platform_config_admin_view(db, provider="resend")
        deepseek_view = ProviderSettingsService.get_platform_config_admin_view(db, provider="deepseek")
        apollo_ok, apollo_key = AiTeamService._provider_connection_flags(apollo_view)
        resend_ok, resend_key = AiTeamService._provider_connection_flags(resend_view)
        deepseek_ok, _deepseek_key = AiTeamService._provider_connection_flags(deepseek_view)
        return {
            "search_sector": row.search_sector,
            "search_country": row.search_country,
            "search_company_size": row.search_company_size,
            "search_title_keywords": row.search_title_keywords,
            "search_city_region": row.search_city_region,
            "search_max_per_run": row.search_max_per_run,
            "search_min_score": row.search_min_score,
            "followup_after_days": row.followup_after_days,
            "max_followups": row.max_followups,
            "sender_name": row.sender_name,
            "reply_to_email": row.reply_to_email,
            "from_email": row.from_email,
            "writing_instruction": row.writing_instruction,
            "email_signature": row.email_signature,
            "email_html_template": row.email_html_template or AiTeamService.default_email_html_template(),
            "default_email_html_template": AiTeamService.default_email_html_template(),
            "email_language": row.email_language,
            "email_max_words": row.email_max_words,
            "email_tone": row.email_tone,
            "promo_code_prefix": row.promo_code_prefix,
            "promo_offer_type": row.promo_offer_type,
            "promo_value": row.promo_value,
            "promo_expiry_days": row.promo_expiry_days,
            "promo_max_uses": row.promo_max_uses,
            "promo_code_mode": row.promo_code_mode,
            "smtp_host": row.smtp_host,
            "smtp_port": row.smtp_port,
            "smtp_username": row.smtp_username,
            "smtp_password_configured": bool(row.smtp_password_enc),
            "inbox_email": row.inbox_email,
            "resend_sending_domain": row.resend_sending_domain,
            "run_schedule": row.run_schedule,
            "max_emails_per_day": row.max_emails_per_day,
            "sending_window": row.sending_window,
            "auto_fetch_prospects": row.auto_fetch_prospects,
            "auto_draft_emails": row.auto_draft_emails,
            "auto_followup": row.auto_followup,
            "track_opens": row.track_opens,
            "notify_on_reply": row.notify_on_reply,
            "notify_on_promo_used": row.notify_on_promo_used,
            "auto_send_without_approval": row.auto_send_without_approval,
            "apollo_credit_alert_at": row.apollo_credit_alert_at,
            "agent_paused": row.agent_paused,
            "last_agent_run_at": row.last_agent_run_at.isoformat() if row.last_agent_run_at else None,
            "apollo_connected": apollo_ok,
            "apollo_api_key_configured": apollo_key,
            "resend_connected": resend_ok,
            "resend_api_key_configured": resend_key,
            "deepseek_connected": deepseek_ok,
        }

    @staticmethod
    def update_settings(db: Session, payload: dict[str, Any]) -> AiTeamSettings:
        row = AiTeamService.get_settings(db)
        now = AiTeamService._now()
        scalar_fields = [
            "search_sector", "search_country", "search_company_size", "search_title_keywords", "search_city_region",
            "sender_name", "reply_to_email", "from_email", "writing_instruction", "email_signature",
            "email_language", "email_tone", "promo_code_prefix", "promo_offer_type", "promo_code_mode",
            "smtp_host", "smtp_username", "inbox_email", "resend_sending_domain",
            "run_schedule", "sending_window",
        ]
        int_fields = [
            "search_max_per_run", "search_min_score", "followup_after_days", "max_followups",
            "email_max_words", "promo_value", "promo_expiry_days", "promo_max_uses",
            "smtp_port", "max_emails_per_day", "apollo_credit_alert_at",
        ]
        bool_fields = [
            "auto_fetch_prospects", "auto_draft_emails", "auto_followup", "track_opens",
            "notify_on_reply", "notify_on_promo_used", "auto_send_without_approval", "agent_paused",
        ]
        text_fields = ["email_html_template"]
        for key in text_fields:
            if key in payload:
                val = payload[key]
                setattr(row, key, str(val) if val is not None else None)
        for key in scalar_fields:
            if key in payload:
                setattr(row, key, str(payload[key] or "").strip())
        for key in int_fields:
            if key in payload:
                setattr(row, key, int(payload[key] or 0))
        for key in bool_fields:
            if key in payload:
                setattr(row, key, bool(payload[key]))
        if payload.get("smtp_password"):
            enc = get_encryptor()
            row.smtp_password_enc = enc.encrypt_str(str(payload["smtp_password"]))
        row.updated_at = now
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def _apollo_key(db: Session) -> str:
        cfg, _ = ProviderSettingsService.get_platform_config_decrypted(db, provider="apollo")
        return str((cfg or {}).get("api_key") or "").strip()

    @staticmethod
    def _resend_key(db: Session) -> str:
        cfg, _ = ProviderSettingsService.get_platform_config_decrypted(db, provider="resend")
        return str((cfg or {}).get("api_key") or "").strip()

    @staticmethod
    def save_provider_keys(db: Session, *, apollo_api_key: str | None = None, resend_api_key: str | None = None) -> None:
        if apollo_api_key is not None and str(apollo_api_key).strip():
            ProviderSettingsService.upsert_platform_config(
                db, provider="apollo", is_enabled=True, config={"api_key": str(apollo_api_key).strip()}
            )
        if resend_api_key is not None and str(resend_api_key).strip():
            ProviderSettingsService.upsert_platform_config(
                db, provider="resend", is_enabled=True, config={"api_key": str(resend_api_key).strip()}
            )

    @staticmethod
    def default_email_html_template() -> str:
        return _DEFAULT_EMAIL_HTML_TEMPLATE

    @staticmethod
    def effective_html_template(settings: AiTeamSettings) -> str:
        raw = str(settings.email_html_template or "").strip()
        return raw or _DEFAULT_EMAIL_HTML_TEMPLATE

    @staticmethod
    def _body_html_fragment(text: str) -> str:
        clean = str(text or "").strip()
        if not clean:
            return "<p style=\"margin:0 0 12px;font-size:14px;color:#4A4958;\"></p>"
        parts = [p.strip() for p in re.split(r"\n\s*\n", clean) if p.strip()]
        if not parts:
            parts = [clean]
        return "".join(
            f"<p style=\"margin:0 0 12px;font-size:14px;color:#4A4958;\">{p.replace(chr(10), '<br>')}</p>"
            for p in parts
        )

    @staticmethod
    def _prospect_template_vars(db: Session, prospect: AiTeamProspect, *, body_text: str | None = None) -> dict[str, str]:
        promo = db.get(PromoOffer, prospect.promo_offer_id) if prospect.promo_offer_id else None
        body = str(body_text if body_text is not None else prospect.draft_body or "").strip()
        return {
            "first_name": prospect.first_name or "there",
            "last_name": prospect.last_name or "",
            "company": prospect.company_name or "your company",
            "promo_code": promo.code if promo else "",
            "job_title": prospect.job_title or "",
            "email": prospect.email or "",
            "sector": prospect.sector or "",
            "country_code": prospect.country_code or "GB",
            "body": body,
        }

    @staticmethod
    def render_email_html(
        db: Session,
        settings: AiTeamSettings,
        *,
        prospect: AiTeamProspect | None = None,
        variables: dict[str, str] | None = None,
        body_text: str | None = None,
        template_override: str | None = None,
    ) -> dict[str, str]:
        vars_map = dict(variables or {})
        if prospect is not None:
            vars_map = {**AiTeamService._prospect_template_vars(db, prospect, body_text=body_text), **vars_map}
        body_raw = str(vars_map.get("body") or "").strip()
        vars_map["body"] = AiTeamService._body_html_fragment(body_raw)
        template = str(template_override or AiTeamService.effective_html_template(settings))
        html = template
        for key, val in vars_map.items():
            html = html.replace("{{" + key + "}}", str(val or ""))
        text = re.sub(r"<[^>]+>", "", html)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        subject = (prospect.draft_subject if prospect else None) or "Quick idea for your team"
        return {"subject": subject, "html": html, "text": text, "body_text": body_raw}

    @staticmethod
    def prospect_email_preview(db: Session, prospect_id: str) -> dict[str, str]:
        prospect = db.get(AiTeamProspect, prospect_id)
        if prospect is None:
            raise AiTeamServiceError("Prospect not found")
        settings = AiTeamService.get_settings(db)
        return AiTeamService.render_email_html(db, settings, prospect=prospect)

    @staticmethod
    def template_preview(db: Session, *, template: str | None = None, use_sample: bool = True) -> dict[str, str]:
        settings = AiTeamService.get_settings(db)
        vars_map = dict(_SAMPLE_PREVIEW_VARS) if use_sample else {}
        return AiTeamService.render_email_html(
            db,
            settings,
            variables=vars_map,
            template_override=template,
            body_text=vars_map.get("body"),
        )

    @staticmethod
    def send_template_test_email(db: Session, *, to_email: str, prospect_id: str | None = None) -> dict[str, Any]:
        to_addr = str(to_email or "").strip()
        if not to_addr or "@" not in to_addr:
            raise AiTeamServiceError("Enter a valid test email address")
        settings = AiTeamService.get_settings(db)
        api_key = AiTeamService._resend_key(db)
        from_addr = AiTeamService._from_address(settings)
        if prospect_id:
            prospect = db.get(AiTeamProspect, prospect_id)
            if prospect is None:
                raise AiTeamServiceError("Prospect not found")
            rendered = AiTeamService.render_email_html(db, settings, prospect=prospect)
        else:
            rendered = AiTeamService.template_preview(db, use_sample=True)
        subject = f"[Test] {rendered['subject']}"
        result = ResendService.send_email(
            api_key,
            from_email=from_addr,
            to_email=to_addr,
            subject=subject,
            text=rendered["text"],
            html=rendered["html"],
            reply_to=(settings.reply_to_email or None),
        )
        return {"ok": True, "message": f"Test email sent to {to_addr}", "email_id": result.get("email_id")}

    @staticmethod
    def parse_csv_preview(raw: bytes) -> dict[str, Any]:
        from app.utils.text_decoding import decode_uploaded_text

        text = decode_uploaded_text(raw)
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise AiTeamServiceError("CSV has no header row")
        headers = [str(h or "").strip() for h in reader.fieldnames if str(h or "").strip()]
        rows: list[dict[str, str]] = []
        total = 0
        for row in reader:
            total += 1
            if len(rows) < 5:
                rows.append({k: str(v or "").strip() for k, v in row.items()})
        return {"headers": headers, "preview_rows": rows, "total_rows": total}

    @staticmethod
    def import_csv_prospects(db: Session, raw: bytes, mapping: dict[str, str]) -> dict[str, Any]:
        email_col = str(mapping.get("email") or "").strip()
        if not email_col:
            raise AiTeamServiceError("Map which CSV column contains email")
        from app.utils.text_decoding import decode_uploaded_text

        text = decode_uploaded_text(raw)
        reader = csv.DictReader(io.StringIO(text))
        settings = AiTeamService.get_settings(db)
        keywords = [k.strip() for k in (settings.search_title_keywords or "").split(",") if k.strip()]
        created = 0
        skipped = 0

        def col(name: str) -> str:
            key = str(mapping.get(name) or "").strip()
            return key

        for row in reader:
            email = str(row.get(email_col) or "").strip().lower()
            if not email or "@" not in email:
                skipped += 1
                continue
            exists = db.execute(select(AiTeamProspect).where(AiTeamProspect.email == email)).scalar_one_or_none()
            if exists is not None:
                skipped += 1
                continue
            first_name = str(row.get(col("first_name")) or "").strip()
            last_name = str(row.get(col("last_name")) or "").strip()
            company = str(row.get(col("company_name")) or row.get(col("company")) or "").strip()
            job_title = str(row.get(col("job_title")) or "").strip()
            sector = str(row.get(col("sector")) or settings.search_sector or "").strip().lower()
            country = str(row.get(col("country_code")) or row.get(col("country")) or "GB").strip().upper()[:8]
            score = AiTeamService._score_prospect(job_title, company, keywords) if job_title else 70
            if score < int(settings.search_min_score or 60):
                skipped += 1
                continue
            now = AiTeamService._now()
            if not sector:
                sector = AiTeamService._infer_sector(job_title, company, settings.search_sector)
            prospect = AiTeamProspect(
                first_name=first_name,
                last_name=last_name,
                email=email,
                job_title=job_title,
                company_name=company,
                sector=sector,
                country_code=country or "GB",
                match_score=score,
                status="new",
                source="csv",
                profile_json=json.dumps(dict(row)),
                created_at=now,
                updated_at=now,
            )
            db.add(prospect)
            db.flush()
            AiTeamService.ensure_promo_for_prospect(db, prospect, settings)
            AiTeamService.draft_email_for_prospect(db, prospect, settings)
            created += 1
        db.commit()
        return {"ok": True, "created": created, "skipped": skipped}

    @staticmethod
    def _infer_sector(job_title: str, company: str, configured: str) -> str:
        if configured:
            return configured.strip().lower()
        blob = f"{job_title} {company}".lower()
        for sector, keywords in _SECTOR_KEYWORDS.items():
            if any(k in blob for k in keywords):
                return sector
        return "general"

    @staticmethod
    def _score_prospect(job_title: str, company: str, keywords: list[str]) -> int:
        title = job_title.lower()
        hits = sum(1 for kw in keywords if kw.lower() in title)
        base = 50 + hits * 15
        if company.strip():
            base += 10
        return min(100, base)

    @staticmethod
    def _company_slug(company: str) -> str:
        clean = re.sub(r"[^A-Z0-9]+", "-", company.upper()).strip("-")
        return clean[:20] or "PROSPECT"

    @staticmethod
    def ensure_promo_for_prospect(db: Session, prospect: AiTeamProspect, settings: AiTeamSettings) -> PromoOffer:
        if prospect.promo_offer_id:
            existing = db.get(PromoOffer, prospect.promo_offer_id)
            if existing is not None:
                return existing
        existing = db.execute(
            select(PromoOffer).where(PromoOffer.ai_team_prospect_id == prospect.id, PromoOffer.is_active.is_(True))
        ).scalar_one_or_none()
        if existing is not None:
            prospect.promo_offer_id = existing.id
            db.add(prospect)
            db.commit()
            return existing

        prefix = PromoOfferService.normalize_code(settings.promo_code_prefix or "TRIAL")
        slug = AiTeamService._company_slug(prospect.company_name)
        code = PromoOfferService.normalize_code(f"{prefix}-{slug}")
        if PromoOfferService.get_by_code(db, code):
            code = PromoOfferService.normalize_code(f"{prefix}-{slug[:12]}{prospect.id[:4].upper()}")

        offer_type = PromoOfferService.normalize_offer_type(settings.promo_offer_type)
        value = max(1, int(settings.promo_value or 50))
        payload: dict[str, Any] = {
            "code": code,
            "name": f"AI Team · {prospect.company_name or prospect.email}",
            "offer_type": offer_type,
            "expires_in_days": max(1, int(settings.promo_expiry_days or 14)),
            "max_redemptions": max(1, int(settings.promo_max_uses or 1)),
            "prospect_email": prospect.email,
            "prospect_name": f"{prospect.first_name} {prospect.last_name}".strip(),
        }
        if offer_type == "survey_credits":
            payload["survey_contacts_included"] = value
        elif offer_type == "interview_credits":
            payload["interview_contacts_included"] = value
        else:
            payload["trial_days"] = value

        row = PromoOfferService.create_admin(db, payload)
        row.ai_team_prospect_id = prospect.id
        prospect.promo_offer_id = row.id
        db.add(row)
        db.add(prospect)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def prospect_to_dict(db: Session, row: AiTeamProspect) -> dict[str, Any]:
        promo = db.get(PromoOffer, row.promo_offer_id) if row.promo_offer_id else None
        return {
            "id": row.id,
            "first_name": row.first_name,
            "last_name": row.last_name,
            "full_name": f"{row.first_name} {row.last_name}".strip(),
            "email": row.email,
            "job_title": row.job_title,
            "company_name": row.company_name,
            "sector": row.sector,
            "country_code": row.country_code,
            "match_score": row.match_score,
            "status": row.status,
            "source": row.source,
            "promo_code": promo.code if promo else None,
            "promo_offer_id": row.promo_offer_id,
            "draft_subject": row.draft_subject,
            "draft_body": row.draft_body,
            "drafted_at": row.drafted_at.isoformat() if row.drafted_at else None,
            "sent_at": row.sent_at.isoformat() if row.sent_at else None,
            "opened_at": row.opened_at.isoformat() if row.opened_at else None,
            "replied_at": row.replied_at.isoformat() if row.replied_at else None,
            "converted_at": row.converted_at.isoformat() if row.converted_at else None,
            "emails_sent_count": row.emails_sent_count,
            "last_error": row.last_error,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def list_prospects(db: Session, *, status: str | None = None, q: str | None = None) -> list[AiTeamProspect]:
        stmt = select(AiTeamProspect).order_by(AiTeamProspect.updated_at.desc())
        if status:
            stmt = stmt.where(AiTeamProspect.status == status)
        rows = list(db.execute(stmt).scalars().all())
        if q:
            needle = q.lower()
            rows = [
                r for r in rows
                if needle in (r.email or "").lower()
                or needle in (r.company_name or "").lower()
                or needle in f"{r.first_name} {r.last_name}".lower()
            ]
        return rows

    @staticmethod
    def draft_email_for_prospect(db: Session, prospect: AiTeamProspect, settings: AiTeamSettings) -> AiTeamProspect:
        promo = AiTeamService.ensure_promo_for_prospect(db, prospect, settings)
        variables = {
            "first_name": prospect.first_name or "there",
            "last_name": prospect.last_name or "",
            "job_title": prospect.job_title or "your role",
            "company": prospect.company_name or "your company",
            "sector": prospect.sector or "your sector",
            "country": prospect.country_code or "GB",
            "promo_code": promo.code,
        }
        instruction = settings.writing_instruction or _DEFAULT_WRITING
        for key, val in variables.items():
            instruction = instruction.replace("{" + key + "}", str(val))

        system = (
            "You write B2B cold outreach emails for VoxBulk. Return JSON with keys subject and body. "
            f"Tone: {settings.email_tone}. Language: {settings.email_language}. "
            f"Max words: {settings.email_max_words}. Body is plain text with line breaks."
        )
        user = f"Instruction:\n{instruction}\n\nSignature to append:\n{settings.email_signature or _DEFAULT_SIGNATURE}"
        result = OpenAIProviderService.complete(
            db,
            system_prompt=system,
            messages=[AgentMessage(role="user", content=user)],
            max_tokens=600,
            temperature=0.5,
            provider="deepseek",
        )
        text = str(result.assistant_text or "").strip()
        subject = "Quick idea for your team"
        body = text
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                subject = str(parsed.get("subject") or subject).strip()
                body = str(parsed.get("body") or text).strip()
        except json.JSONDecodeError:
            if "\n" in text:
                first, rest = text.split("\n", 1)
                if first.lower().startswith("subject:"):
                    subject = first.split(":", 1)[1].strip()
                    body = rest.strip()

        now = AiTeamService._now()
        prospect.draft_subject = subject[:500]
        prospect.draft_body = body
        rendered = AiTeamService.render_email_html(db, settings, prospect=prospect, body_text=body)
        prospect.draft_body_html = rendered["html"]
        prospect.drafted_at = now
        prospect.status = "pending"
        prospect.updated_at = now
        db.add(prospect)
        db.commit()
        db.refresh(prospect)
        return prospect

    @staticmethod
    def fetch_prospects(db: Session, *, preview: bool = False, limit: int | None = None) -> dict[str, Any]:
        settings = AiTeamService.get_settings(db)
        api_key = AiTeamService._apollo_key(db)
        keywords = [k.strip() for k in (settings.search_title_keywords or "").split(",") if k.strip()]
        if not keywords:
            keywords = ["operations director", "customer experience manager"]

        per_page = limit or (5 if preview else settings.search_max_per_run)
        try:
            people = ApolloService.search_people(
                api_key,
                title_keywords=keywords,
                country=settings.search_country or None,
                city_region=settings.search_city_region or None,
                per_page=per_page,
            )
        except ApolloServiceError as exc:
            raise AiTeamServiceError(str(exc)) from exc

        created = 0
        skipped = 0
        for person in people:
            email = person["email"].lower()
            exists = db.execute(select(AiTeamProspect).where(AiTeamProspect.email == email)).scalar_one_or_none()
            if exists is not None:
                skipped += 1
                continue
            score = AiTeamService._score_prospect(person["job_title"], person["company_name"], keywords)
            if score < int(settings.search_min_score or 60):
                skipped += 1
                continue
            now = AiTeamService._now()
            sector = AiTeamService._infer_sector(person["job_title"], person["company_name"], settings.search_sector)
            row = AiTeamProspect(
                apollo_id=person.get("apollo_id"),
                first_name=person["first_name"],
                last_name=person["last_name"],
                email=email,
                job_title=person["job_title"],
                company_name=person["company_name"],
                sector=sector,
                country_code=person.get("country_code") or "GB",
                match_score=score,
                status="new",
                profile_json=json.dumps(person.get("profile_json") or {}),
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            db.flush()
            AiTeamService.ensure_promo_for_prospect(db, row, settings)
            if settings.auto_draft_emails:
                AiTeamService.draft_email_for_prospect(db, row, settings)
            created += 1
        db.commit()
        return {"ok": True, "created": created, "skipped": skipped, "preview": preview}

    @staticmethod
    def _from_address(settings: AiTeamSettings) -> str:
        name = (settings.sender_name or "VoxBulk team").strip()
        email = (settings.from_email or "").strip()
        if name and email:
            return f"{name} <{email}>"
        return email

    @staticmethod
    def send_prospect_email(db: Session, prospect: AiTeamProspect, *, subject: str | None = None, body: str | None = None) -> AiTeamProspect:
        settings = AiTeamService.get_settings(db)
        api_key = AiTeamService._resend_key(db)
        from_addr = AiTeamService._from_address(settings)
        if not from_addr or "@" not in from_addr:
            raise AiTeamServiceError("From email is not configured")

        subj = (subject or prospect.draft_subject or "").strip()
        text = (body or prospect.draft_body or "").strip()
        if not subj or not text:
            raise AiTeamServiceError("Email subject and body are required")

        rendered = AiTeamService.render_email_html(db, settings, prospect=prospect, body_text=text)
        html_out = rendered["html"]
        text_out = rendered["text"]

        try:
            result = ResendService.send_email(
                api_key,
                from_email=from_addr,
                to_email=prospect.email,
                subject=subj,
                text=text_out,
                html=html_out,
                reply_to=(settings.reply_to_email or None),
            )
        except ResendServiceError as exc:
            prospect.last_error = str(exc)
            prospect.updated_at = AiTeamService._now()
            db.add(prospect)
            db.commit()
            raise AiTeamServiceError(str(exc)) from exc

        now = AiTeamService._now()
        msg = AiTeamMessage(
            prospect_id=prospect.id,
            direction="outbound",
            from_email=settings.from_email,
            to_email=prospect.email,
            subject=subj,
            body_text=text,
            body_html=html_out,
            resend_email_id=result.get("email_id"),
            created_at=now,
        )
        prospect.status = "sent"
        prospect.sent_at = now
        prospect.approved_at = prospect.approved_at or now
        prospect.emails_sent_count = int(prospect.emails_sent_count or 0) + 1
        prospect.resend_email_id = result.get("email_id")
        prospect.last_error = None
        prospect.updated_at = now
        db.add(msg)
        db.add(prospect)
        db.commit()
        db.refresh(prospect)
        return prospect

    @staticmethod
    def approve_prospect(db: Session, prospect_id: str) -> AiTeamProspect:
        prospect = db.get(AiTeamProspect, prospect_id)
        if prospect is None:
            raise AiTeamServiceError("Prospect not found")
        settings = AiTeamService.get_settings(db)
        if not prospect.draft_body:
            AiTeamService.draft_email_for_prospect(db, prospect, settings)
        return AiTeamService.send_prospect_email(db, prospect)

    @staticmethod
    def reject_prospect(db: Session, prospect_id: str) -> AiTeamProspect:
        prospect = db.get(AiTeamProspect, prospect_id)
        if prospect is None:
            raise AiTeamServiceError("Prospect not found")
        now = AiTeamService._now()
        prospect.status = "rejected"
        prospect.rejected_at = now
        prospect.updated_at = now
        db.add(prospect)
        db.commit()
        db.refresh(prospect)
        return prospect

    @staticmethod
    def regenerate_draft(db: Session, prospect_id: str) -> AiTeamProspect:
        prospect = db.get(AiTeamProspect, prospect_id)
        if prospect is None:
            raise AiTeamServiceError("Prospect not found")
        settings = AiTeamService.get_settings(db)
        return AiTeamService.draft_email_for_prospect(db, prospect, settings)

    @staticmethod
    def update_draft(db: Session, prospect_id: str, *, subject: str, body: str) -> AiTeamProspect:
        prospect = db.get(AiTeamProspect, prospect_id)
        if prospect is None:
            raise AiTeamServiceError("Prospect not found")
        settings = AiTeamService.get_settings(db)
        now = AiTeamService._now()
        prospect.draft_subject = subject.strip()[:500]
        prospect.draft_body = body.strip()
        rendered = AiTeamService.render_email_html(db, settings, prospect=prospect, body_text=body.strip())
        prospect.draft_body_html = rendered["html"]
        prospect.drafted_at = now
        prospect.status = "pending"
        prospect.updated_at = now
        db.add(prospect)
        db.commit()
        db.refresh(prospect)
        return prospect

    @staticmethod
    def mark_converted(db: Session, prospect_id: str) -> AiTeamProspect:
        prospect = db.get(AiTeamProspect, prospect_id)
        if prospect is None:
            raise AiTeamServiceError("Prospect not found")
        now = AiTeamService._now()
        prospect.status = "converted"
        prospect.converted_at = now
        prospect.updated_at = now
        db.add(prospect)
        db.commit()
        db.refresh(prospect)
        return prospect

    @staticmethod
    def record_inbound_reply(db: Session, *, prospect_id: str, body: str, from_email: str) -> AiTeamMessage:
        prospect = db.get(AiTeamProspect, prospect_id)
        if prospect is None:
            raise AiTeamServiceError("Prospect not found")
        now = AiTeamService._now()
        msg = AiTeamMessage(
            prospect_id=prospect.id,
            direction="inbound",
            from_email=from_email,
            to_email=prospect.email,
            subject="Re: " + (prospect.draft_subject or ""),
            body_text=body,
            created_at=now,
        )
        prospect.status = "replied"
        prospect.replied_at = now
        prospect.updated_at = now
        db.add(msg)
        db.add(prospect)
        db.commit()
        db.refresh(msg)
        return msg

    @staticmethod
    def send_reply(db: Session, prospect_id: str, *, body: str) -> AiTeamMessage:
        prospect = db.get(AiTeamProspect, prospect_id)
        if prospect is None:
            raise AiTeamServiceError("Prospect not found")
        settings = AiTeamService.get_settings(db)
        subject = "Re: " + (prospect.draft_subject or "VoxBulk")
        AiTeamService.send_prospect_email(db, prospect, subject=subject, body=body)
        return db.execute(
            select(AiTeamMessage).where(AiTeamMessage.prospect_id == prospect.id).order_by(AiTeamMessage.created_at.desc())
        ).scalars().first()

    @staticmethod
    def list_messages(db: Session, prospect_id: str) -> list[AiTeamMessage]:
        return list(
            db.execute(
                select(AiTeamMessage).where(AiTeamMessage.prospect_id == prospect_id).order_by(AiTeamMessage.created_at.asc())
            ).scalars().all()
        )

    @staticmethod
    def list_replies(db: Session) -> list[AiTeamProspect]:
        return list(
            db.execute(
                select(AiTeamProspect)
                .where(AiTeamProspect.status.in_(["replied", "opened", "sent"]))
                .order_by(AiTeamProspect.replied_at.desc(), AiTeamProspect.updated_at.desc())
            ).scalars().all()
        )

    @staticmethod
    def dashboard_stats(db: Session) -> dict[str, Any]:
        pending = db.scalar(select(func.count()).select_from(AiTeamProspect).where(AiTeamProspect.status == "pending")) or 0
        sent = db.scalar(select(func.count()).select_from(AiTeamProspect).where(AiTeamProspect.status == "sent")) or 0
        opened = db.scalar(select(func.count()).select_from(AiTeamProspect).where(AiTeamProspect.status == "opened")) or 0
        replied = db.scalar(select(func.count()).select_from(AiTeamProspect).where(AiTeamProspect.status == "replied")) or 0
        converted = db.scalar(select(func.count()).select_from(AiTeamProspect).where(AiTeamProspect.status == "converted")) or 0
        week_ago = AiTeamService._now() - timedelta(days=7)
        sent_week = db.scalar(
            select(func.count()).select_from(AiTeamProspect).where(AiTeamProspect.sent_at >= week_ago)
        ) or 0
        promo_used = db.scalar(
            select(func.count()).select_from(PromoOffer).where(
                PromoOffer.ai_team_prospect_id.isnot(None), PromoOffer.redemption_count > 0
            )
        ) or 0
        total_sent = sent + opened + replied + converted
        open_rate = round((opened + replied + converted) / total_sent * 100) if total_sent else 0
        reply_rate = round(replied / total_sent * 100) if total_sent else 0
        return {
            "pending_approval": pending,
            "sent_this_week": sent_week,
            "open_rate": open_rate,
            "reply_rate": reply_rate,
            "replied_count": replied,
            "promo_used": promo_used,
            "converted": converted,
            "total_prospects": db.scalar(select(func.count()).select_from(AiTeamProspect)) or 0,
        }

    @staticmethod
    def analytics(db: Session) -> dict[str, Any]:
        stats = AiTeamService.dashboard_stats(db)
        rows = list(db.execute(select(AiTeamProspect)).scalars().all())
        funnel = {
            "found": len(rows),
            "qualified": len([r for r in rows if r.match_score >= 60]),
            "sent": len([r for r in rows if r.status in {"sent", "opened", "replied", "converted"}]),
            "opened": len([r for r in rows if r.status in {"opened", "replied", "converted"} or r.opened_at]),
            "replied": len([r for r in rows if r.status in {"replied", "converted"} or r.replied_at]),
            "converted": len([r for r in rows if r.status == "converted"]),
        }
        sectors: dict[str, dict[str, int]] = {}
        for r in rows:
            sec = r.sector or "general"
            bucket = sectors.setdefault(sec, {"sent": 0, "opened": 0, "replied": 0, "converted": 0})
            if r.status in {"sent", "opened", "replied", "converted"}:
                bucket["sent"] += 1
            if r.opened_at or r.status in {"opened", "replied", "converted"}:
                bucket["opened"] += 1
            if r.replied_at or r.status in {"replied", "converted"}:
                bucket["replied"] += 1
            if r.status == "converted":
                bucket["converted"] += 1
        sector_rows = []
        for sec, b in sectors.items():
            sent = b["sent"] or 0
            sector_rows.append({
                "sector": sec,
                "sent": sent,
                "open_pct": round(b["opened"] / sent * 100) if sent else 0,
                "reply_pct": round(b["replied"] / sent * 100) if sent else 0,
                "converted": b["converted"],
            })
        return {"stats": stats, "funnel": funnel, "sectors": sector_rows}

    @staticmethod
    def list_promo_codes(db: Session) -> list[dict[str, Any]]:
        rows = list(
            db.execute(
                select(PromoOffer).where(PromoOffer.ai_team_prospect_id.isnot(None)).order_by(PromoOffer.created_at.desc())
            ).scalars().all()
        )
        out = []
        for row in rows:
            status = "unused"
            if row.redemption_count > 0:
                status = "used"
            elif row.expires_at and row.expires_at < AiTeamService._now():
                status = "expired"
            out.append({
                **PromoOfferService.to_admin_dict(row),
                "usage_status": status,
            })
        return out

    @staticmethod
    def run_agent(db: Session) -> dict[str, Any]:
        settings = AiTeamService.get_settings(db)
        if settings.agent_paused:
            return {"ok": False, "message": "Agent is paused"}
        result = {"fetch": None, "approved": []}
        if settings.auto_fetch_prospects:
            result["fetch"] = AiTeamService.fetch_prospects(db, preview=False)
        pending = AiTeamService.list_prospects(db, status="pending")
        if settings.auto_send_without_approval:
            for p in pending[: max(0, int(settings.max_emails_per_day or 10))]:
                try:
                    AiTeamService.approve_prospect(db, p.id)
                    result["approved"].append(p.id)
                except Exception as exc:
                    logger.warning("ai_team_auto_send_failed", extra={"prospect_id": p.id, "error": str(exc)})
        settings.last_agent_run_at = AiTeamService._now()
        db.add(settings)
        db.commit()
        return {"ok": True, **result}

    @staticmethod
    def test_smtp(settings: AiTeamSettings, *, to_email: str, db: Session) -> dict[str, Any]:
        host = (settings.smtp_host or "").strip()
        port = int(settings.smtp_port or 587)
        user = (settings.smtp_username or "").strip()
        if not host or not user:
            raise AiTeamServiceError("SMTP host and username are required")
        pwd = None
        if settings.smtp_password_enc:
            pwd = get_encryptor().decrypt_str(settings.smtp_password_enc)
        if not pwd:
            raise AiTeamServiceError("SMTP password is required")
        to_addr = str(to_email or settings.inbox_email or user).strip()
        msg = f"Subject: VoxBulk AI Team SMTP test\r\nFrom: {user}\r\nTo: {to_addr}\r\n\r\nSMTP connection test from AI Team settings."
        context = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.starttls(context=context)
            server.login(user, pwd)
            server.sendmail(user, [to_addr], msg)
        return {"ok": True, "message": f"SMTP test sent to {to_addr}"}

    @staticmethod
    def generate_sample_email(db: Session) -> dict[str, Any]:
        settings = AiTeamService.get_settings(db)
        class _Sample:
            first_name = "Alex"
            last_name = "Taylor"
            email = "alex.taylor@example.com"
            job_title = "Operations director"
            company_name = "Example Estates"
            sector = "property"
            country_code = "GB"
            match_score = 88
            status = "new"
            id = "sample"
            promo_offer_id = None
            draft_subject = None
            draft_body = None
            draft_body_html = None
            drafted_at = None

        sample = _Sample()
        instruction = settings.writing_instruction or _DEFAULT_WRITING
        variables = {
            "first_name": sample.first_name,
            "last_name": sample.last_name,
            "job_title": sample.job_title,
            "company": sample.company_name,
            "sector": sample.sector,
            "country": sample.country_code,
            "promo_code": "TRIAL-EXAMPLE",
        }
        for key, val in variables.items():
            instruction = instruction.replace("{" + key + "}", str(val))
        system = (
            "You write B2B cold outreach emails for VoxBulk. Return JSON with keys subject and body. "
            f"Tone: {settings.email_tone}. Language: {settings.email_language}. "
            f"Max words: {settings.email_max_words}."
        )
        user = f"Instruction:\n{instruction}\n\nSignature:\n{settings.email_signature or _DEFAULT_SIGNATURE}"
        result = OpenAIProviderService.complete(
            db,
            system_prompt=system,
            messages=[AgentMessage(role="user", content=user)],
            max_tokens=600,
            temperature=0.5,
            provider="deepseek",
        )
        text = str(result.assistant_text or "").strip()
        subject = "Quick idea for your team"
        body = text
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                subject = str(parsed.get("subject") or subject).strip()
                body = str(parsed.get("body") or text).strip()
        except json.JSONDecodeError:
            pass
        return {"subject": subject, "body": body}
