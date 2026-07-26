from __future__ import annotations

import csv
import io
import json
import logging
import re
import smtplib
import ssl
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.encryption import get_encryptor
from app.models.ai_team_apify_run import AiTeamApifyRun
from app.models.ai_team_message import AiTeamMessage
from app.models.ai_team_prospect import AiTeamProspect
from app.models.ai_team_settings import AiTeamSettings
from app.models.promo_offer import PromoOffer
from app.services.agents.base import AgentMessage
from app.services.apify_service import ApifyService, ApifyServiceError
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
            "email_delivery_provider": (row.email_delivery_provider or "smtp").strip().lower() or "smtp",
            "resend_sending_domain": row.resend_sending_domain,
            "apify_token_configured": bool(AiTeamService._apify_token_configured(db, row)),
            "apify_exhibitor_actor_id": row.apify_exhibitor_actor_id or "",
            "apify_contact_actor_id": row.apify_contact_actor_id or "",
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
            "smtp_configured": bool(row.smtp_host and row.smtp_username and row.smtp_password_enc),
            "apify_connected": bool(AiTeamService._apify_token_configured(db, row)),
        }

    @staticmethod
    def update_settings(db: Session, payload: dict[str, Any]) -> AiTeamSettings:
        row = AiTeamService.get_settings(db)
        now = AiTeamService._now()
        scalar_fields = [
            "search_sector", "search_country", "search_company_size", "search_title_keywords", "search_city_region",
            "sender_name", "reply_to_email", "from_email", "writing_instruction", "email_signature",
            "email_language", "email_tone", "promo_code_prefix", "promo_offer_type", "promo_code_mode",
            "smtp_host", "smtp_username", "inbox_email", "resend_sending_domain", "email_delivery_provider",
            "apify_exhibitor_actor_id", "apify_contact_actor_id",
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
                val = str(payload[key] or "").strip()
                if key == "email_delivery_provider":
                    val = val.lower()
                    if val not in {"smtp", "resend"}:
                        val = "smtp"
                setattr(row, key, val)
        for key in int_fields:
            if key in payload:
                setattr(row, key, int(payload[key] or 0))
        for key in bool_fields:
            if key in payload:
                setattr(row, key, bool(payload[key]))
        if payload.get("smtp_password"):
            enc = get_encryptor()
            row.smtp_password_enc = enc.encrypt_str(str(payload["smtp_password"]))
        if payload.get("apify_token"):
            token = str(payload["apify_token"]).strip()
            if token:
                # Primary store: provider_configs (same durable path as Apollo).
                ProviderSettingsService.upsert_platform_config(
                    db, provider="apify", is_enabled=True, config={"api_key": token}
                )
                # Also keep ai_team_settings.apify_token_enc when the column exists.
                try:
                    row.apify_token_enc = get_encryptor().encrypt_str(token)
                except Exception:
                    pass
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
    def _apify_token_from_provider(db: Session) -> str:
        try:
            cfg, _ = ProviderSettingsService.get_platform_config_decrypted(db, provider="apify")
            return str((cfg or {}).get("api_key") or "").strip()
        except Exception:
            return ""

    @staticmethod
    def _apify_token_configured(db: Session, settings: AiTeamSettings | None = None) -> bool:
        if AiTeamService._apify_token_from_provider(db):
            return True
        row = settings or AiTeamService.get_settings(db)
        return bool(getattr(row, "apify_token_enc", None))

    @staticmethod
    def _apify_token(settings: AiTeamSettings, db: Session | None = None) -> str:
        if db is not None:
            from_provider = AiTeamService._apify_token_from_provider(db)
            if from_provider:
                return from_provider
        if not getattr(settings, "apify_token_enc", None):
            return ""
        try:
            return get_encryptor().decrypt_str(settings.apify_token_enc)
        except Exception:
            return ""

    @staticmethod
    def save_provider_keys(
        db: Session,
        *,
        apollo_api_key: str | None = None,
        resend_api_key: str | None = None,
        apify_api_key: str | None = None,
    ) -> None:
        if apollo_api_key is not None and str(apollo_api_key).strip():
            ProviderSettingsService.upsert_platform_config(
                db, provider="apollo", is_enabled=True, config={"api_key": str(apollo_api_key).strip()}
            )
        if resend_api_key is not None and str(resend_api_key).strip():
            ProviderSettingsService.upsert_platform_config(
                db, provider="resend", is_enabled=True, config={"api_key": str(resend_api_key).strip()}
            )
        if apify_api_key is not None and str(apify_api_key).strip():
            ProviderSettingsService.upsert_platform_config(
                db, provider="apify", is_enabled=True, config={"api_key": str(apify_api_key).strip()}
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
        from_addr = AiTeamService._from_address(settings)
        if prospect_id:
            prospect = db.get(AiTeamProspect, prospect_id)
            if prospect is None:
                raise AiTeamServiceError("Prospect not found")
            rendered = AiTeamService.render_email_html(db, settings, prospect=prospect)
        else:
            rendered = AiTeamService.template_preview(db, use_sample=True)
        subject = f"[Test] {rendered['subject']}"
        result = AiTeamService._deliver_email(
            db,
            settings,
            to_email=to_addr,
            subject=subject,
            text=rendered["text"],
            html=rendered["html"],
        )
        return {
            "ok": True,
            "message": f"Test email sent to {to_addr} via {result.get('provider')}",
            "email_id": result.get("email_id"),
            "provider": result.get("provider"),
        }

    @staticmethod
    def _delivery_provider(settings: AiTeamSettings) -> str:
        provider = str(settings.email_delivery_provider or "smtp").strip().lower()
        if provider not in {"smtp", "resend"}:
            return "smtp"
        return provider

    @staticmethod
    def _smtp_password(settings: AiTeamSettings) -> str:
        if not settings.smtp_password_enc:
            return ""
        return get_encryptor().decrypt_str(settings.smtp_password_enc)

    @staticmethod
    def _send_via_smtp(
        settings: AiTeamSettings,
        *,
        to_email: str,
        subject: str,
        text: str,
        html: str | None = None,
    ) -> dict[str, Any]:
        host = (settings.smtp_host or "").strip()
        port = int(settings.smtp_port or 587)
        user = (settings.smtp_username or "").strip()
        pwd = AiTeamService._smtp_password(settings)
        from_email = (settings.from_email or user or "").strip()
        if not host or not user or not pwd:
            raise AiTeamServiceError("SMTP host, username, and password are required")
        if not from_email or "@" not in from_email:
            raise AiTeamServiceError("From email is not configured")

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = AiTeamService._from_address(settings) if settings.sender_name else from_email
        msg["To"] = to_email
        reply_to = (settings.reply_to_email or "").strip()
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.attach(MIMEText(text or "", "plain", "utf-8"))
        if html:
            msg.attach(MIMEText(html, "html", "utf-8"))

        context = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=30, context=context) as server:
                server.login(user, pwd)
                server.sendmail(from_email, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(user, pwd)
                server.sendmail(from_email, [to_email], msg.as_string())
        return {"ok": True, "provider": "smtp", "email_id": None}

    @staticmethod
    def _deliver_email(
        db: Session,
        settings: AiTeamSettings,
        *,
        to_email: str,
        subject: str,
        text: str,
        html: str | None = None,
    ) -> dict[str, Any]:
        provider = AiTeamService._delivery_provider(settings)
        if provider == "smtp":
            return AiTeamService._send_via_smtp(
                settings, to_email=to_email, subject=subject, text=text, html=html
            )
        api_key = AiTeamService._resend_key(db)
        from_addr = AiTeamService._from_address(settings)
        if not from_addr or "@" not in from_addr:
            raise AiTeamServiceError("From email is not configured")
        try:
            result = ResendService.send_email(
                api_key,
                from_email=from_addr,
                to_email=to_email,
                subject=subject,
                text=text,
                html=html,
                reply_to=(settings.reply_to_email or None),
            )
        except ResendServiceError as exc:
            raise AiTeamServiceError(str(exc)) from exc
        return {"ok": True, "provider": "resend", "email_id": result.get("email_id")}

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
    def import_prospect_rows(
        db: Session,
        rows: list[dict[str, Any]],
        *,
        source: str,
        apply_min_score: bool = False,
        auto_draft: bool | None = None,
    ) -> dict[str, Any]:
        settings = AiTeamService.get_settings(db)
        keywords = [k.strip() for k in (settings.search_title_keywords or "").split(",") if k.strip()]
        do_draft = settings.auto_draft_emails if auto_draft is None else bool(auto_draft)
        created = 0
        skipped = 0
        prospects: list[dict[str, Any]] = []

        for raw in rows:
            email = str(raw.get("email") or "").strip().lower()
            if not email or "@" not in email:
                skipped += 1
                continue
            exists = db.execute(select(AiTeamProspect).where(AiTeamProspect.email == email)).scalar_one_or_none()
            if exists is not None:
                skipped += 1
                continue

            first_name = str(raw.get("first_name") or "").strip()
            last_name = str(raw.get("last_name") or "").strip()
            company = str(raw.get("company_name") or raw.get("company") or "").strip()
            job_title = str(raw.get("job_title") or "").strip()
            sector = str(raw.get("sector") or settings.search_sector or "").strip().lower()
            country = str(raw.get("country_code") or raw.get("country") or "GB").strip().upper()[:8] or "GB"
            score = int(raw.get("match_score") or 0)
            if not score:
                score = AiTeamService._score_prospect(job_title, company, keywords) if job_title else 70
            if apply_min_score and score < int(settings.search_min_score or 60):
                skipped += 1
                continue
            if not sector:
                sector = AiTeamService._infer_sector(job_title, company, settings.search_sector) or "general"

            profile = raw.get("profile_json")
            if isinstance(profile, dict):
                profile_json = json.dumps(profile)
            elif isinstance(profile, str) and profile.strip():
                profile_json = profile
            else:
                profile_json = json.dumps({k: v for k, v in raw.items() if k != "profile_json"})

            now = AiTeamService._now()
            prospect = AiTeamProspect(
                first_name=first_name,
                last_name=last_name,
                email=email,
                job_title=job_title,
                company_name=company,
                sector=sector,
                country_code=country,
                match_score=score,
                status="new",
                source=str(source or "paste")[:32],
                profile_json=profile_json,
                created_at=now,
                updated_at=now,
            )
            db.add(prospect)
            db.flush()
            AiTeamService.ensure_promo_for_prospect(db, prospect, settings)
            if do_draft:
                try:
                    AiTeamService.draft_email_for_prospect(db, prospect, settings)
                except Exception as exc:
                    logger.warning("ai_team_draft_failed", extra={"email": email, "error": str(exc)})
                    prospect.status = "new"
                    prospect.last_error = f"Draft failed: {exc}"
                    prospect.updated_at = AiTeamService._now()
                    db.add(prospect)
            else:
                prospect.status = "new"
                db.add(prospect)
            created += 1
            prospects.append(AiTeamService.prospect_to_dict(db, prospect))

        db.commit()
        return {"ok": True, "created": created, "skipped": skipped, "prospects": prospects[:20]}

    @staticmethod
    def _parse_email_line(line: str) -> dict[str, Any] | None:
        raw = str(line or "").strip()
        if not raw or raw.startswith("#"):
            return None
        # Name <email@x.com>
        m = re.match(r"^(.+?)\s*<([^>]+@[^>]+)>\s*$", raw)
        if m:
            name = m.group(1).strip().strip('"').strip("'")
            email = m.group(2).strip().lower()
            parts = name.split(None, 1)
            return {
                "email": email,
                "first_name": parts[0] if parts else "",
                "last_name": parts[1] if len(parts) > 1 else "",
            }
        # email, first, last, company
        if "," in raw:
            bits = [b.strip() for b in raw.split(",")]
            email = bits[0].lower()
            if "@" not in email:
                return None
            return {
                "email": email,
                "first_name": bits[1] if len(bits) > 1 else "",
                "last_name": bits[2] if len(bits) > 2 else "",
                "company_name": bits[3] if len(bits) > 3 else "",
            }
        if "@" in raw and " " not in raw:
            return {"email": raw.lower()}
        # fallback: find email token
        em = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", raw, re.I)
        if not em:
            return None
        email = em.group(0).lower()
        name_part = raw[: em.start()].strip(" ,;-")
        parts = name_part.split(None, 1) if name_part else []
        return {
            "email": email,
            "first_name": parts[0] if parts else "",
            "last_name": parts[1] if len(parts) > 1 else "",
        }

    @staticmethod
    def import_emails_text(
        db: Session,
        text: str,
        *,
        company_name: str = "",
        sector: str = "",
        source: str = "paste",
    ) -> dict[str, Any]:
        lines = str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
        rows: list[dict[str, Any]] = []
        for line in lines:
            parsed = AiTeamService._parse_email_line(line)
            if not parsed:
                continue
            if company_name and not parsed.get("company_name"):
                parsed["company_name"] = company_name
            if sector:
                parsed["sector"] = sector
            parsed["match_score"] = 75
            rows.append(parsed)
        if not rows:
            raise AiTeamServiceError("No valid emails found to import")
        return AiTeamService.import_prospect_rows(db, rows, source=source or "paste", apply_min_score=False)

    @staticmethod
    def import_csv_prospects(db: Session, raw: bytes, mapping: dict[str, str]) -> dict[str, Any]:
        email_col = str(mapping.get("email") or "").strip()
        if not email_col:
            raise AiTeamServiceError("Map which CSV column contains email")
        from app.utils.text_decoding import decode_uploaded_text

        text = decode_uploaded_text(raw)
        reader = csv.DictReader(io.StringIO(text))

        def col(name: str) -> str:
            return str(mapping.get(name) or "").strip()

        rows: list[dict[str, Any]] = []
        for row in reader:
            email = str(row.get(email_col) or "").strip().lower()
            if not email or "@" not in email:
                continue
            rows.append(
                {
                    "email": email,
                    "first_name": str(row.get(col("first_name")) or "").strip(),
                    "last_name": str(row.get(col("last_name")) or "").strip(),
                    "company_name": str(row.get(col("company_name")) or row.get(col("company")) or "").strip(),
                    "job_title": str(row.get(col("job_title")) or "").strip(),
                    "sector": str(row.get(col("sector")) or "").strip().lower(),
                    "country_code": str(row.get(col("country_code")) or row.get(col("country")) or "GB").strip().upper()[:8],
                    "profile_json": dict(row),
                }
            )
        return AiTeamService.import_prospect_rows(db, rows, source="csv", apply_min_score=False)

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
        raw_type = str(settings.promo_offer_type or "").strip().lower()
        payload: dict[str, Any] = {
            "code": code,
            "name": f"AI Team · {prospect.company_name or prospect.email}",
            "expires_in_days": max(1, int(settings.promo_expiry_days or 14)),
            "max_redemptions": max(1, int(settings.promo_max_uses or 1)),
            "prospect_email": prospect.email,
            "prospect_name": f"{prospect.first_name} {prospect.last_name}".strip(),
        }
        if offer_type in {"expo", "expo_trial"} or raw_type in {"expo", "expo_trial"}:
            payload["benefit_kind"] = "free_usage"
            payload["service_kind"] = "expo"
            payload["usage_amount"] = value
        else:
            payload["offer_type"] = offer_type
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
    def list_prospects(
        db: Session,
        *,
        status: str | None = None,
        q: str | None = None,
        source: str | None = None,
    ) -> list[AiTeamProspect]:
        stmt = select(AiTeamProspect).order_by(AiTeamProspect.updated_at.desc())
        if status:
            stmt = stmt.where(AiTeamProspect.status == status)
        if source:
            stmt = stmt.where(AiTeamProspect.source == source)
        rows = list(db.execute(stmt).scalars().all())
        if q:
            needle = q.lower()
            rows = [
                r for r in rows
                if needle in (r.email or "").lower()
                or needle in (r.company_name or "").lower()
                or needle in f"{r.first_name} {r.last_name}".lower()
                or needle in (r.source or "").lower()
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
        from_addr = AiTeamService._from_address(settings)
        if not from_addr or "@" not in from_addr:
            raise AiTeamServiceError("From email is not configured")

        # Daily send cap
        day_start = AiTeamService._now().replace(hour=0, minute=0, second=0, microsecond=0)
        sent_today = db.scalar(
            select(func.count()).select_from(AiTeamProspect).where(AiTeamProspect.sent_at >= day_start)
        ) or 0
        # Count new sends only when this prospect has not been sent yet today as first touch;
        # follow-ups still respect a soft cap via emails_sent_count checks below.
        max_day = max(1, int(settings.max_emails_per_day or 10))
        if prospect.sent_at is None and sent_today >= max_day:
            raise AiTeamServiceError(f"Daily send limit reached ({max_day})")

        subj = (subject or prospect.draft_subject or "").strip()
        text = (body or prospect.draft_body or "").strip()
        if not subj or not text:
            raise AiTeamServiceError("Email subject and body are required")

        rendered = AiTeamService.render_email_html(db, settings, prospect=prospect, body_text=text)
        html_out = rendered["html"]
        text_out = rendered["text"]

        try:
            result = AiTeamService._deliver_email(
                db,
                settings,
                to_email=prospect.email,
                subject=subj,
                text=text_out,
                html=html_out,
            )
        except AiTeamServiceError as exc:
            prospect.last_error = str(exc)
            prospect.updated_at = AiTeamService._now()
            db.add(prospect)
            db.commit()
            raise

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
        prospect.sent_at = prospect.sent_at or now
        prospect.approved_at = prospect.approved_at or now
        prospect.emails_sent_count = int(prospect.emails_sent_count or 0) + 1
        if result.get("email_id"):
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
        pwd = AiTeamService._smtp_password(settings)
        if not pwd:
            raise AiTeamServiceError("SMTP password is required")
        to_addr = str(to_email or settings.inbox_email or settings.from_email or user).strip()
        result = AiTeamService._send_via_smtp(
            settings,
            to_email=to_addr,
            subject="VoxBulk AI Team SMTP test",
            text="SMTP connection test from AI Team settings.",
            html="<p>SMTP connection test from AI Team settings.</p>",
        )
        return {"ok": True, "message": f"SMTP test sent to {to_addr}", "provider": result.get("provider")}

    @staticmethod
    def test_apify(db: Session, *, token: str | None = None, check_actor: bool = False) -> dict[str, Any]:
        settings = AiTeamService.get_settings(db)
        key = str(token or "").strip() or AiTeamService._apify_token(settings, db=db)
        actor = None
        if check_actor:
            actor = (settings.apify_exhibitor_actor_id or settings.apify_contact_actor_id or "").strip() or None
        try:
            return ApifyService.test_connection(key, actor_id=actor)
        except ApifyServiceError as exc:
            raise AiTeamServiceError(str(exc)) from exc

    @staticmethod
    def test_all_connections(db: Session, *, to_email: str | None = None) -> dict[str, Any]:
        settings = AiTeamService.get_settings(db)
        checks: list[dict[str, Any]] = []

        # Apify
        try:
            apify = AiTeamService.test_apify(db)
            checks.append({"id": "apify", "ok": True, "message": apify.get("message") or "Apify OK"})
        except Exception as exc:
            checks.append({"id": "apify", "ok": False, "message": str(exc)})

        # Email delivery
        provider = AiTeamService._delivery_provider(settings)
        to_addr = str(to_email or settings.inbox_email or settings.reply_to_email or settings.from_email or "").strip()
        try:
            if provider == "smtp":
                if not (settings.smtp_host and settings.smtp_username and settings.smtp_password_enc):
                    raise AiTeamServiceError("SMTP is not fully configured")
                if to_addr and "@" in to_addr:
                    smtp = AiTeamService.test_smtp(settings, to_email=to_addr, db=db)
                    checks.append({"id": "email", "ok": True, "message": smtp.get("message") or "SMTP OK"})
                else:
                    # Login-only style check without requiring recipient
                    host = settings.smtp_host
                    port = int(settings.smtp_port or 587)
                    user = settings.smtp_username
                    pwd = AiTeamService._smtp_password(settings)
                    context = ssl.create_default_context()
                    if port == 465:
                        with smtplib.SMTP_SSL(host, port, timeout=20, context=context) as server:
                            server.login(user, pwd)
                    else:
                        with smtplib.SMTP(host, port, timeout=20) as server:
                            server.starttls(context=context)
                            server.login(user, pwd)
                    checks.append({"id": "email", "ok": True, "message": "SMTP login OK (no test recipient)"})
            else:
                key = AiTeamService._resend_key(db)
                if not key:
                    raise AiTeamServiceError("Resend API key is not configured")
                from_email = AiTeamService._from_address(settings)
                fallback = to_addr or settings.from_email
                res = ResendService.test_connection(key, from_email=from_email, to_email=fallback)
                checks.append({"id": "email", "ok": True, "message": res.get("message") or "Resend OK"})
        except Exception as exc:
            checks.append({"id": "email", "ok": False, "message": str(exc)})

        # From address
        from_ok = bool(settings.from_email and "@" in settings.from_email)
        checks.append({
            "id": "from_email",
            "ok": from_ok,
            "message": settings.from_email if from_ok else "From email is not configured",
        })

        # Promo
        promo_ok = bool(settings.promo_code_prefix)
        checks.append({
            "id": "promo",
            "ok": promo_ok,
            "message": f"Promo prefix {settings.promo_code_prefix or '—'} · type {settings.promo_offer_type or '—'}",
        })

        # DeepSeek (optional)
        try:
            deepseek_view = ProviderSettingsService.get_platform_config_admin_view(db, provider="deepseek")
            deepseek_ok, _ = AiTeamService._provider_connection_flags(deepseek_view)
            checks.append({
                "id": "deepseek",
                "ok": deepseek_ok,
                "message": "DeepSeek configured" if deepseek_ok else "DeepSeek not configured (AI drafts need it)",
            })
        except Exception as exc:
            checks.append({"id": "deepseek", "ok": False, "message": str(exc)})

        all_ok = all(c["ok"] for c in checks if c["id"] in {"apify", "email", "from_email"})
        return {"ok": all_ok, "provider": provider, "checks": checks}

    @staticmethod
    def _run_to_dict(row: AiTeamApifyRun) -> dict[str, Any]:
        return {
            "id": row.id,
            "apify_run_id": row.apify_run_id,
            "actor_id": row.actor_id,
            "expo_url": row.expo_url,
            "status": row.status,
            "dataset_id": row.dataset_id,
            "item_count": row.item_count,
            "imported_count": row.imported_count,
            "error": row.error,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        }

    @staticmethod
    def start_apify_run(db: Session, *, expo_url: str, actor_id: str | None = None) -> dict[str, Any]:
        settings = AiTeamService.get_settings(db)
        token = AiTeamService._apify_token(settings, db=db)
        if not token:
            raise AiTeamServiceError("Apify API token is not configured")
        url = str(expo_url or "").strip()
        if not url.startswith("http"):
            raise AiTeamServiceError("Enter a valid expo directory URL (https://…)")
        actor = str(actor_id or settings.apify_exhibitor_actor_id or settings.apify_contact_actor_id or "").strip()
        if not actor:
            raise AiTeamServiceError("Configure an Apify actor ID in settings")

        # Common actor input keys — actors ignore unknown fields
        run_input = {
            "startUrls": [{"url": url}],
            "url": url,
            "expoUrl": url,
            "expo_url": url,
        }
        try:
            started = ApifyService.start_actor_run(token, actor_id=actor, run_input=run_input)
        except ApifyServiceError as exc:
            raise AiTeamServiceError(str(exc)) from exc

        now = AiTeamService._now()
        row = AiTeamApifyRun(
            apify_run_id=started.get("apify_run_id"),
            actor_id=actor,
            expo_url=url,
            status=str(started.get("status") or "READY"),
            dataset_id=started.get("dataset_id"),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"ok": True, "run": AiTeamService._run_to_dict(row)}

    @staticmethod
    def list_apify_runs(db: Session, *, limit: int = 30) -> list[dict[str, Any]]:
        rows = list(
            db.execute(
                select(AiTeamApifyRun).order_by(AiTeamApifyRun.created_at.desc()).limit(max(1, min(limit, 100)))
            ).scalars().all()
        )
        return [AiTeamService._run_to_dict(r) for r in rows]

    @staticmethod
    def refresh_apify_run(db: Session, run_id: str) -> dict[str, Any]:
        row = db.get(AiTeamApifyRun, run_id)
        if row is None:
            raise AiTeamServiceError("Apify run not found")
        settings = AiTeamService.get_settings(db)
        token = AiTeamService._apify_token(settings, db=db)
        if not token or not row.apify_run_id:
            raise AiTeamServiceError("Cannot refresh run — missing Apify token or run id")
        try:
            remote = ApifyService.get_run(token, apify_run_id=row.apify_run_id)
        except ApifyServiceError as exc:
            raise AiTeamServiceError(str(exc)) from exc

        now = AiTeamService._now()
        row.status = str(remote.get("status") or row.status)
        if remote.get("dataset_id"):
            row.dataset_id = remote.get("dataset_id")
        row.stats_json = json.dumps(remote.get("stats") or {})
        row.updated_at = now
        if str(row.status).upper() in {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}:
            row.finished_at = row.finished_at or now
            if str(row.status).upper() != "SUCCEEDED":
                row.error = row.error or f"Run ended with status {row.status}"
            elif row.dataset_id:
                try:
                    items = ApifyService.fetch_dataset_items(token, dataset_id=row.dataset_id, limit=5000)
                    row.item_count = len(items)
                except ApifyServiceError as exc:
                    row.error = str(exc)
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"ok": True, "run": AiTeamService._run_to_dict(row)}

    @staticmethod
    def preview_apify_run(db: Session, run_id: str, *, limit: int = 25) -> dict[str, Any]:
        row = db.get(AiTeamApifyRun, run_id)
        if row is None:
            raise AiTeamServiceError("Apify run not found")
        settings = AiTeamService.get_settings(db)
        token = AiTeamService._apify_token(settings, db=db)
        if not token or not row.dataset_id:
            raise AiTeamServiceError("Dataset not ready yet — wait for the run to succeed")
        try:
            items = ApifyService.fetch_dataset_items(token, dataset_id=row.dataset_id, limit=500)
        except ApifyServiceError as exc:
            raise AiTeamServiceError(str(exc)) from exc

        contacts = []
        for item in items:
            normalized = ApifyService.normalize_contact_item(
                item, expo_url=row.expo_url, run_id=row.apify_run_id or row.id
            )
            if normalized:
                contacts.append(normalized)
        return {
            "ok": True,
            "run": AiTeamService._run_to_dict(row),
            "total_items": len(items),
            "contacts_with_email": len(contacts),
            "preview": contacts[: max(1, min(limit, 100))],
        }

    @staticmethod
    def import_apify_run(db: Session, run_id: str) -> dict[str, Any]:
        preview = AiTeamService.preview_apify_run(db, run_id, limit=5000)
        contacts = []
        # Re-fetch full normalized list
        row = db.get(AiTeamApifyRun, run_id)
        settings = AiTeamService.get_settings(db)
        token = AiTeamService._apify_token(settings, db=db)
        items = ApifyService.fetch_dataset_items(token, dataset_id=row.dataset_id, limit=5000)
        for item in items:
            normalized = ApifyService.normalize_contact_item(
                item, expo_url=row.expo_url, run_id=row.apify_run_id or row.id
            )
            if normalized:
                contacts.append(normalized)
        if not contacts:
            raise AiTeamServiceError("No contacts with email found in this Apify dataset")
        result = AiTeamService.import_prospect_rows(db, contacts, source="apify", apply_min_score=False)
        row.imported_count = int(row.imported_count or 0) + int(result.get("created") or 0)
        row.item_count = len(items)
        row.updated_at = AiTeamService._now()
        db.add(row)
        db.commit()
        return {
            "ok": True,
            "run": AiTeamService._run_to_dict(row),
            "created": result.get("created"),
            "skipped": result.get("skipped"),
            "contacts_with_email": len(contacts),
            "total_items": preview.get("total_items"),
        }

    @staticmethod
    def process_due_followups(db: Session) -> dict[str, Any]:
        settings = AiTeamService.get_settings(db)
        if not settings.auto_followup or settings.agent_paused:
            return {"ok": True, "sent": 0, "skipped": 0, "message": "Follow-ups paused or disabled"}
        after_days = max(1, int(settings.followup_after_days or 3))
        max_followups = max(0, int(settings.max_followups or 2))
        if max_followups <= 0:
            return {"ok": True, "sent": 0, "skipped": 0, "message": "max_followups is 0"}
        cutoff = AiTeamService._now() - timedelta(days=after_days)
        rows = list(
            db.execute(
                select(AiTeamProspect).where(
                    AiTeamProspect.status.in_(["sent", "opened"]),
                    AiTeamProspect.sent_at.isnot(None),
                    AiTeamProspect.sent_at <= cutoff,
                    AiTeamProspect.replied_at.is_(None),
                )
            ).scalars().all()
        )
        sent = 0
        skipped = 0
        for prospect in rows:
            if int(prospect.followups_sent or 0) >= max_followups:
                skipped += 1
                continue
            # Space follow-ups by followup_after_days from last outbound
            last_msg = db.execute(
                select(AiTeamMessage)
                .where(AiTeamMessage.prospect_id == prospect.id, AiTeamMessage.direction == "outbound")
                .order_by(AiTeamMessage.created_at.desc())
            ).scalars().first()
            if last_msg and last_msg.created_at and last_msg.created_at > cutoff:
                skipped += 1
                continue
            subject = f"Re: {prospect.draft_subject or 'quick follow-up'}"
            body = (
                f"Hi {prospect.first_name or 'there'},\n\n"
                f"Just bumping this in case it got buried. Happy to share a short demo of how "
                f"VoxBulk helps teams like {prospect.company_name or 'yours'} capture expo leads.\n\n"
                f"{settings.email_signature or _DEFAULT_SIGNATURE}"
            )
            try:
                AiTeamService.send_prospect_email(db, prospect, subject=subject, body=body)
                prospect.followups_sent = int(prospect.followups_sent or 0) + 1
                prospect.updated_at = AiTeamService._now()
                db.add(prospect)
                db.commit()
                sent += 1
            except Exception as exc:
                skipped += 1
                logger.warning("ai_team_followup_failed", extra={"prospect_id": prospect.id, "error": str(exc)})
        return {"ok": True, "sent": sent, "skipped": skipped}

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
