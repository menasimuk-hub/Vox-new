"""AI Demo Agent — requests, magic links, sessions, tools, sales handoff."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import secrets
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.data.ai_demo_email_default import DEMO_INVITE_EMAIL_BODY, DEMO_INVITE_EMAIL_SUBJECT
from app.data.ai_demo_kb_defaults import DEMO_KB_SEED, tool_subset_json
from app.data.ai_demo_whatsapp_defaults import DEMO_EMAIL_SENT_BODY, DEMO_EMAIL_SENT_TEMPLATE_NAME
from app.models.demo_knowledge_base import DemoKnowledgeBase
from app.models.demo_platform_settings import DemoPlatformSettings
from app.models.demo_request import DemoRequest
from app.models.demo_session import DemoSession
from app.models.frontpage_lead_call import FrontpageLeadCall
from app.services.interview_whatsapp_send_service import InterviewWhatsappSendService
from app.services.telnyx_lead_variables import normalize_lead_phone, resolve_lead_location
from app.services.transactional_email_service import TransactionalEmailService

logger = logging.getLogger(__name__)

TOKEN_DAYS = 7
RESEND_MAX_PER_HOUR = 5
SOFT_CAP_MINUTES_DEFAULT = 7
SERVICE_CODES = ("recruitment", "surveys", "feedback", "expo", "smart_card")
SOURCE_DEMO = "ai_demo_agent"

# Admin Settings regions — visitor WhatsApp country → which agent talks.
DEMO_AGENT_REGIONS: tuple[tuple[str, str], ...] = (
    ("DEFAULT", "Default (fallback)"),
    ("GB", "United Kingdom"),
    ("AU", "Australia"),
    ("CA", "Canada"),
    ("US", "United States"),
    ("IE", "Ireland"),
    ("SC", "Scotland"),
    ("SA", "Saudi Arabia"),
    ("EG", "Egypt / Arabic"),
    ("AE", "United Arab Emirates"),
)

# Longest-prefix match for E.164 → region code.
_DIAL_PREFIX_TO_REGION: tuple[tuple[str, str], ...] = (
    ("+353", "IE"),
    ("+971", "AE"),
    ("+966", "SA"),
    ("+61", "AU"),
    ("+44", "GB"),
    ("+20", "EG"),
    ("+1", "US"),
)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AiDemoError(Exception):
    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _utcnow() -> datetime:
    return datetime.utcnow()


def token_hmac(raw_token: str) -> str:
    key = get_settings().jwt_secret_key.encode("utf-8")
    return hmac.new(key, raw_token.encode("utf-8"), hashlib.sha256).hexdigest()


def resend_signature(request_id: str) -> str:
    key = get_settings().jwt_secret_key.encode("utf-8")
    return hmac.new(key, f"demo-resend:{request_id}".encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def verify_resend_signature(request_id: str, sig: str) -> bool:
    expected = resend_signature(request_id)
    return hmac.compare_digest(expected, str(sig or "").strip())


def _json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _public_origin() -> str:
    return get_settings().public_app_origin.rstrip("/")


def _normalize_lang(value: str | None) -> str:
    code = str(value or "en").strip().lower()
    if code.startswith("ar"):
        return "ar"
    return "en"


def _normalize_website(raw: str) -> str:
    url = str(raw or "").strip()
    if not url:
        raise AiDemoError("Company website is required")
    if not re.match(r"^https?://", url, re.I):
        url = f"https://{url}"
    return url[:512]


def _normalize_whatsapp(raw: str | None, *, required: bool = True) -> str | None:
    text = str(raw or "").strip()
    if not text:
        if required:
            raise AiDemoError("Enter a valid WhatsApp number including country code")
        return None
    location = resolve_lead_location(phone=text)
    e164, _ = normalize_lead_phone(text, location)
    phone = (e164 or text).replace(" ", "")
    if not phone.startswith("+") or len(phone) < 8:
        raise AiDemoError("Enter a valid WhatsApp number including country code")
    return phone[:40]


class AiDemoService:
    @staticmethod
    def ensure_knowledge_bases(db: Session) -> None:
        created = False
        for row in DEMO_KB_SEED:
            existing = db.execute(
                select(DemoKnowledgeBase).where(DemoKnowledgeBase.service_code == row["service_code"])
            ).scalar_one_or_none()
            if existing is not None:
                continue
            db.add(
                DemoKnowledgeBase(
                    service_code=row["service_code"],
                    title=row["title"],
                    system_prompt=row["system_prompt"],
                    fact_sheet=row["fact_sheet"],
                    demo_script=row["demo_script"],
                    tool_subset=tool_subset_json(row.get("tool_subset")),
                    sort_order=int(row.get("sort_order") or 0),
                    is_active=True,
                )
            )
            created = True
        if created:
            db.commit()

    @staticmethod
    def upsert_knowledge_bases(db: Session) -> dict[str, Any]:
        """Refresh demo KB talk/sales copy from repo defaults (AI demo KBs only)."""
        updated = 0
        created = 0
        for row in DEMO_KB_SEED:
            existing = db.execute(
                select(DemoKnowledgeBase).where(DemoKnowledgeBase.service_code == row["service_code"])
            ).scalar_one_or_none()
            if existing is None:
                db.add(
                    DemoKnowledgeBase(
                        service_code=row["service_code"],
                        title=row["title"],
                        system_prompt=row["system_prompt"],
                        fact_sheet=row["fact_sheet"],
                        demo_script=row["demo_script"],
                        tool_subset=tool_subset_json(row.get("tool_subset")),
                        sort_order=int(row.get("sort_order") or 0),
                        is_active=True,
                    )
                )
                created += 1
                continue
            existing.title = row["title"]
            existing.system_prompt = row["system_prompt"]
            existing.fact_sheet = row["fact_sheet"]
            existing.demo_script = row["demo_script"]
            existing.tool_subset = tool_subset_json(row.get("tool_subset"))
            existing.sort_order = int(row.get("sort_order") or 0)
            existing.is_active = True
            existing.updated_at = _utcnow()
            db.add(existing)
            updated += 1
        db.commit()
        return {"ok": True, "created": created, "updated": updated}

    @staticmethod
    def get_settings(db: Session) -> DemoPlatformSettings:
        row = db.get(DemoPlatformSettings, "default")
        if row is None:
            row = DemoPlatformSettings(id="default")
            db.add(row)
            db.commit()
            db.refresh(row)
        return row

    @staticmethod
    def _loads_agent_by_region(row: DemoPlatformSettings) -> dict[str, str]:
        try:
            raw = json.loads(row.agent_by_region_json or "{}")
        except Exception:
            raw = {}
        if not isinstance(raw, dict):
            return {}
        out: dict[str, str] = {}
        for key, value in raw.items():
            k = str(key or "").strip().upper()
            v = str(value or "").strip()
            if k and v:
                out[k] = v
        return out

    @staticmethod
    def serialize_settings(row: DemoPlatformSettings) -> dict[str, Any]:
        return {
            "provider_agent_id": row.provider_agent_id,
            "agent_by_region": AiDemoService._loads_agent_by_region(row),
            "default_voice": row.default_voice,
            "soft_cap_minutes": row.soft_cap_minutes,
            "from_email": row.from_email,
            "notes": row.notes,
            "regions": [{"code": code, "label": label} for code, label in DEMO_AGENT_REGIONS],
        }

    @staticmethod
    def update_settings(db: Session, payload: dict[str, Any]) -> DemoPlatformSettings:
        row = AiDemoService.get_settings(db)
        if "provider_agent_id" in payload:
            row.provider_agent_id = (str(payload.get("provider_agent_id") or "").strip() or None)
        if "agent_by_region" in payload:
            raw = payload.get("agent_by_region")
            cleaned: dict[str, str] = {}
            if isinstance(raw, dict):
                allowed = {code for code, _ in DEMO_AGENT_REGIONS}
                for key, value in raw.items():
                    k = str(key or "").strip().upper()
                    v = str(value or "").strip()
                    if k in allowed and v:
                        cleaned[k] = v
            row.agent_by_region_json = json.dumps(cleaned) if cleaned else None
            # Keep legacy single field in sync with DEFAULT when present.
            if cleaned.get("DEFAULT"):
                from app.models.agent import AgentDefinition

                agent = db.get(AgentDefinition, cleaned["DEFAULT"])
                if agent and str(agent.telnyx_assistant_id or "").strip():
                    row.provider_agent_id = str(agent.telnyx_assistant_id).strip()
        if "default_voice" in payload:
            row.default_voice = (str(payload.get("default_voice") or "").strip() or None)
        if "soft_cap_minutes" in payload and payload["soft_cap_minutes"] is not None:
            row.soft_cap_minutes = max(3, min(30, int(payload["soft_cap_minutes"])))
        if "from_email" in payload:
            row.from_email = (str(payload.get("from_email") or "").strip().lower() or None)
        if "notes" in payload:
            row.notes = str(payload.get("notes") or "") or None
        row.updated_at = _utcnow()
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def list_voice_agents(db: Session) -> list[dict[str, Any]]:
        """Active Admin → Agents that have a Telnyx assistant id (for Settings pickers)."""
        from app.models.agent import AgentDefinition

        rows = list(
            db.execute(
                select(AgentDefinition)
                .where(AgentDefinition.is_active.is_(True))
                .order_by(AgentDefinition.accent_region.asc(), AgentDefinition.name.asc())
            ).scalars()
        )
        items: list[dict[str, Any]] = []
        for a in rows:
            telnyx_id = str(a.telnyx_assistant_id or "").strip()
            if not telnyx_id:
                continue
            region = str(a.accent_region or "").strip().upper() or None
            items.append(
                {
                    "id": a.id,
                    "name": a.name,
                    "slug": a.slug,
                    "accent_region": region,
                    "gender": a.gender,
                    "voice_label": a.voice_label,
                    "telnyx_assistant_id": telnyx_id,
                    "label": (
                        f"{a.name}"
                        + (f" · {region}" if region else "")
                        + (f" · {a.gender}" if a.gender else "")
                    ),
                }
            )
        return items

    @staticmethod
    def duplicate_region_agents_for_demo(db: Session, *, dry_run: bool = False) -> dict[str, Any]:
        """Clone mapped region agents into AI Demo–only AgentDefinitions + Telnyx assistants.

        Never mutates the source interview/Talk-to-us assistants — creates new Telnyx IDs
        and remaps demo_platform_settings.agent_by_region_json to the copies.
        """
        from uuid import uuid4

        from app.models.agent import AgentDefinition
        from app.services.telnyx_assistant_service import (
            create_telnyx_assistant,
            normalize_telnyx_assistant_id,
            template_assistant_create_defaults,
        )

        settings = AiDemoService.get_settings(db)
        mapping = AiDemoService._loads_agent_by_region(settings)
        if not mapping:
            # Fall back to legacy provider_agent_id → invent DEFAULT mapping from matching agent
            legacy = str(settings.provider_agent_id or "").strip()
            if legacy:
                src = db.execute(
                    select(AgentDefinition).where(AgentDefinition.telnyx_assistant_id == legacy)
                ).scalars().first()
                if src is None:
                    src = db.execute(
                        select(AgentDefinition).where(
                            AgentDefinition.telnyx_assistant_id == normalize_telnyx_assistant_id(legacy)
                        )
                    ).scalars().first()
                if src:
                    mapping = {"DEFAULT": src.id}
            if not mapping:
                raise AiDemoError(
                    "No AI Demo region agents configured. Set at least DEFAULT in Settings first.",
                    status_code=400,
                )

        results: list[dict[str, Any]] = []
        new_map: dict[str, str] = {}
        seen_source: dict[str, str] = {}  # source agent id -> new demo agent id

        for region, source_id in mapping.items():
            source = db.get(AgentDefinition, source_id)
            if source is None:
                results.append({"region": region, "ok": False, "error": "source_agent_missing", "source_id": source_id})
                continue
            # Already an AI Demo copy — keep
            if str(source.slug or "").startswith("ai-demo-") or str(source.name or "").startswith("AI Demo"):
                new_map[region] = source.id
                results.append(
                    {
                        "region": region,
                        "ok": True,
                        "skipped": True,
                        "reason": "already_demo_agent",
                        "agent_id": source.id,
                        "name": source.name,
                        "telnyx_assistant_id": source.telnyx_assistant_id,
                    }
                )
                continue

            if source.id in seen_source:
                new_map[region] = seen_source[source.id]
                results.append(
                    {
                        "region": region,
                        "ok": True,
                        "reused_copy": True,
                        "agent_id": seen_source[source.id],
                    }
                )
                continue

            src_telnyx = str(source.telnyx_assistant_id or "").strip()
            if not src_telnyx:
                results.append({"region": region, "ok": False, "error": "source_missing_telnyx", "source_id": source.id})
                continue

            demo_slug = f"ai-demo-{source.slug}"[:120]
            existing_copy = db.execute(
                select(AgentDefinition).where(AgentDefinition.slug == demo_slug)
            ).scalar_one_or_none()
            demo_name = f"AI Demo — {source.name}"[:255]

            if dry_run:
                results.append(
                    {
                        "region": region,
                        "ok": True,
                        "dry_run": True,
                        "would_create": demo_name,
                        "from_telnyx": src_telnyx,
                        "existing_copy_id": existing_copy.id if existing_copy else None,
                    }
                )
                continue

            template = template_assistant_create_defaults(db, src_telnyx)
            created = create_telnyx_assistant(
                db,
                name=demo_name,
                instructions=(
                    "You are the VoxBulk AI demo guide. Talk like a human — ask, listen, show the dashboard, "
                    "and help them see if VoxBulk fits. Sales will send the best offer — never invent discounts."
                ),
                model=template.get("model"),
                greeting="Hi — quick check before we dive in: what's the annoying part right now?",
                voice_settings=template.get("voice_settings"),
            )
            new_telnyx = normalize_telnyx_assistant_id(str(created.get("id") or created.get("assistant_id") or ""))
            if not new_telnyx:
                results.append({"region": region, "ok": False, "error": "telnyx_create_failed", "raw": created})
                continue

            if existing_copy:
                copy = existing_copy
                copy.name = demo_name
                copy.telnyx_assistant_id = new_telnyx
                copy.system_prompt = source.system_prompt
                copy.accent_region = source.accent_region
                copy.gender = source.gender
                copy.voice_label = source.voice_label
                copy.voice_type_label = source.voice_type_label
                copy.default_voice = source.default_voice
                copy.is_active = True
                copy.supports_interview = False
                copy.supports_survey = False
                copy.is_default_interview = False
                copy.updated_at = _utcnow()
            else:
                copy = AgentDefinition(
                    id=str(uuid4()),
                    name=demo_name,
                    slug=demo_slug,
                    description=f"Dedicated AI Demo voice agent (cloned from {source.name}). Do not use for interviews.",
                    system_prompt=source.system_prompt or "You are the VoxBulk AI demo guide.",
                    conversation_style=source.conversation_style,
                    default_model=source.default_model,
                    default_voice=source.default_voice,
                    voice_label=source.voice_label,
                    voice_type_label=source.voice_type_label,
                    accent_region=source.accent_region,
                    gender=source.gender,
                    telnyx_assistant_id=new_telnyx,
                    is_active=True,
                    supports_interview=False,
                    supports_survey=False,
                    supports_lead_sales=True,
                    is_default_interview=False,
                    is_default_survey=False,
                )
                db.add(copy)
            db.flush()
            seen_source[source.id] = copy.id
            new_map[region] = copy.id
            results.append(
                {
                    "region": region,
                    "ok": True,
                    "agent_id": copy.id,
                    "name": copy.name,
                    "slug": copy.slug,
                    "telnyx_assistant_id": new_telnyx,
                    "cloned_from": source.id,
                    "cloned_from_telnyx": src_telnyx,
                }
            )

        if not dry_run and new_map:
            settings.agent_by_region_json = json.dumps(new_map)
            if new_map.get("DEFAULT"):
                demo_default = db.get(AgentDefinition, new_map["DEFAULT"])
                if demo_default and demo_default.telnyx_assistant_id:
                    settings.provider_agent_id = str(demo_default.telnyx_assistant_id).strip()
            settings.notes = (
                (settings.notes or "")
                + "\n[ai-demo] Region map remapped to dedicated AI Demo agents."
            ).strip()
            settings.updated_at = _utcnow()
            db.add(settings)
            db.commit()

        return {"ok": True, "dry_run": dry_run, "agent_by_region": new_map, "results": results}

    @staticmethod
    def normalize_voice_region(value: str | None) -> str | None:
        code = str(value or "").strip().upper()
        if not code:
            return None
        allowed = {c for c, _ in DEMO_AGENT_REGIONS}
        if code not in allowed:
            raise AiDemoError(f"Unknown voice region: {code}. Use one of {', '.join(sorted(allowed))}.")
        return code

    @staticmethod
    def infer_visitor_region(req: DemoRequest) -> str:
        override = str(getattr(req, "voice_region", None) or "").strip().upper()
        if override:
            return override
        phone = str(req.whatsapp_e164 or "").strip()
        if phone:
            digits = phone if phone.startswith("+") else f"+{phone.lstrip('+')}"
            for prefix, region in _DIAL_PREFIX_TO_REGION:
                if digits.startswith(prefix):
                    return region
        lang = str(req.preferred_language or "").strip().lower()
        if lang.startswith("ar"):
            return "SA"
        return "GB"

    @staticmethod
    def resolve_assistant_for_request(db: Session, req: DemoRequest) -> dict[str, Any]:
        """Pick Telnyx assistant from per-region map → DEFAULT → legacy id → Talk-to-us."""
        from app.models.agent import AgentDefinition
        from app.models.frontpage_call_setting import FrontpageCallSetting

        settings = AiDemoService.get_settings(db)
        region = AiDemoService.infer_visitor_region(req)
        mapping = AiDemoService._loads_agent_by_region(settings)

        def _from_agent_id(agent_id: str | None) -> tuple[str | None, AgentDefinition | None]:
            aid = str(agent_id or "").strip()
            if not aid:
                return None, None
            agent = db.get(AgentDefinition, aid)
            if agent is None:
                return None, None
            telnyx = str(agent.telnyx_assistant_id or "").strip()
            return (telnyx or None), agent

        assistant_id: str | None = None
        agent_row: AgentDefinition | None = None
        source = "none"

        for key in (region, "DEFAULT"):
            mapped = mapping.get(key)
            if not mapped:
                continue
            assistant_id, agent_row = _from_agent_id(mapped)
            if assistant_id:
                source = f"region:{key}"
                break

        if not assistant_id:
            legacy = str(settings.provider_agent_id or "").strip()
            if legacy:
                assistant_id = legacy
                source = "legacy_provider_agent_id"

        if not assistant_id:
            fp = db.get(FrontpageCallSetting, "default")
            if fp and (fp.voice_provider or "").lower() == "telnyx":
                assistant_id = str(fp.provider_agent_id or "").strip() or None
                if assistant_id:
                    source = "frontpage_talk_to_us"

        return {
            "assistant_id": assistant_id,
            "region": region,
            "source": source,
            "agent_id": agent_row.id if agent_row else None,
            "agent_name": agent_row.name if agent_row else None,
        }

    @staticmethod
    def _ensure_tracking_token(db: Session, req: DemoRequest) -> str:
        token = str(req.tracking_token or "").strip()
        if token:
            return token
        token = secrets.token_urlsafe(24)
        req.tracking_token = token
        db.add(req)
        db.commit()
        db.refresh(req)
        return token

    @staticmethod
    def _api_origin() -> str:
        from app.services.brand_assets import api_public_origin

        return (api_public_origin().rstrip("/") or "https://api.voxbulk.com")

    @staticmethod
    def _tracked_demo_link(tracking_token: str, raw_demo_url: str) -> str:
        from urllib.parse import quote

        api = AiDemoService._api_origin()
        return f"{api}/public/ai-demo/c/{tracking_token}?u={quote(raw_demo_url, safe='')}"

    @staticmethod
    def _open_pixel_url(tracking_token: str) -> str:
        api = AiDemoService._api_origin()
        return f"{api}/public/ai-demo/o/{tracking_token}.gif"

    @staticmethod
    def _apply_email_tracking(html: str, tracking_token: str) -> str:
        """Inject open pixel (links already use tracked demo_link var)."""
        out = str(html or "")
        token = str(tracking_token or "").strip()
        if not token or not out.strip():
            return out
        if "o.gif" in out and "/public/ai-demo/" in out:
            return out
        pixel = (
            f'<img src="{AiDemoService._open_pixel_url(token)}" width="1" height="1" '
            f'alt="" style="display:none!important;width:1px;height:1px;border:0;" />'
        )
        if re.search(r"</body\s*>", out, re.I):
            return re.sub(r"</body\s*>", pixel + "</body>", out, count=1, flags=re.I)
        return out + pixel

    @staticmethod
    def record_open(db: Session, tracking_token: str) -> None:
        token = str(tracking_token or "").strip()
        if not token:
            return
        req = db.execute(select(DemoRequest).where(DemoRequest.tracking_token == token)).scalar_one_or_none()
        if req is None:
            return
        now = _utcnow()
        if req.opened_at is None:
            req.opened_at = now
        req.open_count = int(req.open_count or 0) + 1
        req.updated_at = now
        db.add(req)
        db.commit()

    @staticmethod
    def record_click_and_destination(db: Session, tracking_token: str, destination: str) -> str:
        from urllib.parse import unquote

        token = str(tracking_token or "").strip()
        dest = unquote(str(destination or "").strip())
        public = _public_origin()
        fallback = f"{public}/demo"
        if not dest.startswith("http://") and not dest.startswith("https://"):
            dest = fallback
        # Only allow our public site destinations
        if not dest.startswith(public) and "voxbulk.com" not in dest:
            dest = fallback

        req = db.execute(select(DemoRequest).where(DemoRequest.tracking_token == token)).scalar_one_or_none()
        if req is not None:
            now = _utcnow()
            if req.link_clicked_at is None:
                req.link_clicked_at = now
            req.click_count = int(req.click_count or 0) + 1
            if req.opened_at is None:
                req.opened_at = now
                req.open_count = max(int(req.open_count or 0), 1)
            req.updated_at = now
            db.add(req)
            db.commit()
        return dest

    @staticmethod
    def create_web_request(
        db: Session,
        *,
        contact_name: str,
        email: str,
        company_name: str,
        whatsapp: str,
        website: str,
        preferred_language: str,
        message: str,
        honeypot: str | None = None,
    ) -> DemoRequest | None:
        if str(honeypot or "").strip():
            return None  # type: ignore[return-value]

        name = str(contact_name or "").strip()
        mail = str(email or "").strip().lower()
        company = str(company_name or "").strip()
        msg = str(message or "").strip()
        if len(name) < 2:
            raise AiDemoError("Please enter your name")
        if not _EMAIL_RE.match(mail):
            raise AiDemoError("Enter a valid email")
        if len(company) < 2:
            raise AiDemoError("Company name is required")
        if len(msg) < 10:
            raise AiDemoError("Please write at least 10 characters")

        pending = db.execute(
            select(DemoRequest).where(
                DemoRequest.email == mail,
                DemoRequest.status == "pending",
            )
        ).scalar_one_or_none()
        if pending is not None:
            return pending

        req = DemoRequest(
            source="web",
            status="pending",
            contact_name=name[:255],
            email=mail[:255],
            company_name=company[:255],
            whatsapp_e164=_normalize_whatsapp(whatsapp, required=True),
            website=_normalize_website(website),
            preferred_language=_normalize_lang(preferred_language),
            message=msg[:4000],
        )
        db.add(req)
        db.commit()
        db.refresh(req)
        return req

    @staticmethod
    def list_requests(
        db: Session,
        *,
        status: str | None = None,
        source: str | None = None,
        limit: int = 100,
    ) -> list[DemoRequest]:
        q = select(DemoRequest).order_by(DemoRequest.created_at.desc()).limit(max(1, min(limit, 500)))
        if status:
            q = q.where(DemoRequest.status == status.strip().lower())
        if source:
            q = q.where(DemoRequest.source == source.strip().lower())
        return list(db.execute(q).scalars().all())

    @staticmethod
    def get_request(db: Session, request_id: str) -> DemoRequest:
        row = db.get(DemoRequest, str(request_id or "").strip())
        if row is None:
            raise AiDemoError("Demo request not found", status_code=404)
        return row

    @staticmethod
    def reject_request(db: Session, request_id: str, *, reason: str | None, admin_id: str | None) -> DemoRequest:
        req = AiDemoService.get_request(db, request_id)
        if req.status == "completed" or req.demo_completed_at:
            raise AiDemoError("Cannot reject a completed demo")
        req.status = "rejected"
        req.rejected_at = _utcnow()
        req.reject_reason = (str(reason or "").strip() or None)
        req.approved_by = admin_id
        req.updated_at = _utcnow()
        db.add(req)
        db.commit()
        db.refresh(req)
        return req

    @staticmethod
    def _issue_token(db: Session, req: DemoRequest) -> tuple[DemoSession, str]:
        # Invalidate unused active tokens
        open_sessions = db.execute(
            select(DemoSession).where(
                DemoSession.request_id == req.id,
                DemoSession.used_at.is_(None),
                DemoSession.status.in_(("issued", "verified", "active")),
            )
        ).scalars().all()
        now = _utcnow()
        for s in open_sessions:
            s.status = "invalidated"
            s.ended_at = now
            db.add(s)

        raw = secrets.token_urlsafe(32)
        session = DemoSession(
            request_id=req.id,
            token_hmac=token_hmac(raw),
            status="issued",
            language=req.preferred_language or "en",
            expires_at=now + timedelta(days=TOKEN_DAYS),
            services_explored=_json_dumps([]),
            questions_asked=_json_dumps([]),
            volume_needs=_json_dumps({}),
            ui_events_log=_json_dumps([]),
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session, raw

    @staticmethod
    def _demo_urls(raw_token: str, request_id: str) -> dict[str, str]:
        base = _public_origin()
        return {
            "demo_link": f"{base}/demo/session?token={raw_token}",
            "resend_link": f"{base}/demo/resend?request={request_id}&sig={resend_signature(request_id)}",
        }

    @staticmethod
    def _send_invite_email(
        db: Session,
        req: DemoRequest,
        *,
        raw_token: str,
        subject_override: str | None = None,
        body_override: str | None = None,
    ) -> tuple[bool, str | None]:
        tracking = AiDemoService._ensure_tracking_token(db, req)
        urls = AiDemoService._demo_urls(raw_token, req.id)
        tracked_demo = AiDemoService._tracked_demo_link(tracking, urls["demo_link"])
        settings = AiDemoService.get_settings(db)
        support = settings.from_email or "hello@voxbulk.com"
        variables = {
            "contact_name": req.contact_name,
            "company_name": req.company_name,
            "preferred_language": "Arabic" if req.preferred_language == "ar" else "English",
            "demo_link": tracked_demo,
            "resend_link": urls["resend_link"],
            "support_email": support,
            "website": req.website,
        }
        if subject_override or body_override:
            from app.services.smtp_mailer_service import SmtpMailerService

            subject = subject_override or DEMO_INVITE_EMAIL_SUBJECT
            body = body_override or DEMO_INVITE_EMAIL_BODY
            for key, val in variables.items():
                subject = subject.replace("{{" + key + "}}", str(val))
                body = body.replace("{{" + key + "}}", str(val))
            body = AiDemoService._apply_email_tracking(body, tracking)
            try:
                SmtpMailerService.send_html(
                    db,
                    to_addr=req.email,
                    subject=subject,
                    body=body,
                    reply_to=support,
                )
                req.email_sent_at = _utcnow()
                db.add(req)
                db.commit()
                return True, None
            except Exception as exc:
                logger.exception("demo_invite_override_mail_failed")
                return False, str(exc)[:240]

        # Load template then inject tracking (do not rely on DB body already having pixel)
        from app.services.email_template_service import EmailTemplateService

        EmailTemplateService.ensure_system_templates(db)
        subject, body, enabled = EmailTemplateService.get_send_content(db, key="demo_invite")
        if not enabled and not (subject or body):
            subject, body = DEMO_INVITE_EMAIL_SUBJECT, DEMO_INVITE_EMAIL_BODY
        for key, val in variables.items():
            subject = subject.replace("{{" + key + "}}", str(val))
            body = body.replace("{{" + key + "}}", str(val))
        body = AiDemoService._apply_email_tracking(body, tracking)
        try:
            from app.services.smtp_mailer_service import SmtpMailerService

            SmtpMailerService.send_html(
                db,
                to_addr=req.email,
                subject=subject or DEMO_INVITE_EMAIL_SUBJECT,
                body=body or DEMO_INVITE_EMAIL_BODY,
                reply_to=support,
            )
            req.email_sent_at = _utcnow()
            db.add(req)
            db.commit()
            return True, None
        except Exception as exc:
            logger.exception("demo_invite_mail_failed")
            # Fallback to transactional helper without tracking injection
            sent, err = TransactionalEmailService.send_templated_optional(
                db,
                template_key="demo_invite",
                to_email=req.email,
                variables=variables,
            )
            if sent:
                req.email_sent_at = _utcnow()
                db.add(req)
                db.commit()
            return bool(sent), err or str(exc)[:240]

    @staticmethod
    def _send_wa_notice(db: Session, req: DemoRequest) -> None:
        if not str(req.whatsapp_e164 or "").strip():
            return
        settings = AiDemoService.get_settings(db)
        from_email = settings.from_email or "hello@voxbulk.com"
        body = (
            DEMO_EMAIL_SENT_BODY.replace("{{1}}", req.contact_name)
            .replace("{{2}}", req.company_name)
            .replace("{{3}}", from_email)
        )
        try:
            InterviewWhatsappSendService.send_template_or_plain(
                db,
                to_number=str(req.whatsapp_e164),
                body=body,
                org_id=None,
                template_name=DEMO_EMAIL_SENT_TEMPLATE_NAME,
                template_components=[
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": req.contact_name[:60]},
                            {"type": "text", "text": req.company_name[:60]},
                            {"type": "text", "text": from_email[:60]},
                        ],
                    }
                ],
                require_template=False,
                service_code="ai_demo",
            )
        except Exception:
            logger.exception("demo_wa_notice_failed request_id=%s", req.id)

    @staticmethod
    def approve_and_send(
        db: Session,
        request_id: str,
        *,
        admin_id: str | None,
        subject_override: str | None = None,
        body_override: str | None = None,
        skip_wa: bool = False,
        voice_region: str | None = None,
    ) -> dict[str, Any]:
        req = AiDemoService.get_request(db, request_id)
        if req.status == "rejected":
            raise AiDemoError("Request was rejected")
        if req.demo_completed_at:
            raise AiDemoError("Demo already completed")

        if voice_region is not None:
            req.voice_region = AiDemoService.normalize_voice_region(voice_region)
            db.add(req)
            db.flush()

        session, raw = AiDemoService._issue_token(db, req)
        sent, err = AiDemoService._send_invite_email(
            db,
            req,
            raw_token=raw,
            subject_override=subject_override,
            body_override=body_override,
        )
        if not sent:
            raise AiDemoError(err or "Failed to send demo invite email", status_code=502)

        if not skip_wa and str(req.whatsapp_e164 or "").strip():
            AiDemoService._send_wa_notice(db, req)

        req.status = "approved"
        req.approved_at = _utcnow()
        req.approved_by = admin_id
        req.updated_at = _utcnow()
        db.add(req)
        db.commit()
        db.refresh(req)
        urls = AiDemoService._demo_urls(raw, req.id)
        return {
            "request": AiDemoService.serialize_request(req),
            "session_id": session.id,
            "demo_link": urls["demo_link"],
            "resend_link": urls["resend_link"],
            "email_sent": True,
        }

    @staticmethod
    def create_manual_and_send(
        db: Session,
        *,
        contact_name: str,
        email: str,
        company_name: str,
        whatsapp: str | None,
        website: str | None,
        preferred_language: str,
        message: str | None,
        admin_id: str | None,
        lead_sales_task_id: str | None = None,
        subject_override: str | None = None,
        body_override: str | None = None,
        skip_wa: bool = False,
        source: str = "manual",
        voice_region: str | None = None,
    ) -> dict[str, Any]:
        name = str(contact_name or "").strip()
        mail = str(email or "").strip().lower()
        company = str(company_name or "").strip() or "—"
        if not _EMAIL_RE.match(mail):
            raise AiDemoError("Valid email is required")
        if len(name) < 2:
            name = mail.split("@")[0][:255] or "Guest"

        region = AiDemoService.normalize_voice_region(voice_region)
        req = DemoRequest(
            source=source[:20],
            status="pending",
            contact_name=name[:255],
            email=mail[:255],
            company_name=company[:255],
            whatsapp_e164=_normalize_whatsapp(whatsapp, required=False),
            website=_normalize_website(website or "https://voxbulk.com"),
            preferred_language=_normalize_lang(preferred_language),
            voice_region=region,
            message=(str(message or "").strip() or None),
            lead_sales_task_id=(str(lead_sales_task_id or "").strip() or None),
        )
        db.add(req)
        db.commit()
        db.refresh(req)
        return AiDemoService.approve_and_send(
            db,
            req.id,
            admin_id=admin_id,
            subject_override=subject_override,
            body_override=body_override,
            skip_wa=skip_wa or not str(req.whatsapp_e164 or "").strip(),
        )

    @staticmethod
    def batch_send(
        db: Session,
        *,
        recipients: list[dict[str, Any]],
        admin_id: str | None,
        preferred_language: str = "en",
        message: str | None = None,
        skip_wa: bool = True,
        voice_region: str | None = None,
    ) -> dict[str, Any]:
        if not recipients:
            raise AiDemoError("Add at least one email")
        if len(recipients) > 50:
            raise AiDemoError("Batch limit is 50 emails per send")

        results: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for raw in recipients:
            email = str(raw.get("email") or "").strip().lower()
            try:
                out = AiDemoService.create_manual_and_send(
                    db,
                    contact_name=str(raw.get("contact_name") or "").strip() or email.split("@")[0],
                    email=email,
                    company_name=str(raw.get("company_name") or "").strip() or "—",
                    whatsapp=str(raw.get("whatsapp") or "").strip() or None,
                    website=str(raw.get("website") or "").strip() or "https://voxbulk.com",
                    preferred_language=str(raw.get("preferred_language") or preferred_language),
                    message=str(raw.get("message") or message or "").strip() or "AI demo invite",
                    admin_id=admin_id,
                    skip_wa=skip_wa or not str(raw.get("whatsapp") or "").strip(),
                    source="manual_batch",
                    voice_region=str(raw.get("voice_region") or voice_region or "").strip() or None,
                )
                results.append({"email": email, "ok": True, "request_id": out["request"]["id"]})
            except AiDemoError as exc:
                errors.append({"email": email, "error": exc.message})
            except Exception as exc:
                logger.exception("demo_batch_send_failed email=%s", email)
                errors.append({"email": email, "error": str(exc)[:200]})
        return {
            "sent": len(results),
            "failed": len(errors),
            "results": results,
            "errors": errors,
        }

    @staticmethod
    def admin_resend(db: Session, request_id: str, *, admin_id: str | None, skip_wa: bool = False) -> dict[str, Any]:
        req = AiDemoService.get_request(db, request_id)
        if req.demo_completed_at:
            raise AiDemoError("Demo already completed — resend blocked")
        if req.status == "rejected":
            raise AiDemoError("Request was rejected")
        return AiDemoService.approve_and_send(db, request_id, admin_id=admin_id, skip_wa=skip_wa)

    @staticmethod
    def public_resend(db: Session, *, request_id: str, sig: str) -> dict[str, Any]:
        if not verify_resend_signature(request_id, sig):
            raise AiDemoError("Invalid resend link", status_code=403)
        req = AiDemoService.get_request(db, request_id)
        if req.demo_completed_at:
            raise AiDemoError("This demo is already complete")
        if req.status not in ("approved", "active", "pending"):
            raise AiDemoError("Demo invite is not available")
        if req.status == "pending":
            raise AiDemoError("Your demo is still awaiting approval")

        since = _utcnow() - timedelta(hours=1)
        recent = db.execute(
            select(DemoSession).where(
                DemoSession.request_id == req.id,
                DemoSession.created_at >= since,
            )
        ).scalars().all()
        if len(list(recent)) >= RESEND_MAX_PER_HOUR:
            raise AiDemoError("Too many resend attempts. Please wait and try again.")

        return AiDemoService.approve_and_send(db, req.id, admin_id=None, skip_wa=False)

    @staticmethod
    def verify_token(db: Session, raw_token: str) -> dict[str, Any]:
        raw = str(raw_token or "").strip()
        if len(raw) < 10:
            raise AiDemoError("Invalid or expired demo link", status_code=403)
        digest = token_hmac(raw)
        session = db.execute(select(DemoSession).where(DemoSession.token_hmac == digest)).scalar_one_or_none()
        if session is None:
            raise AiDemoError("Invalid or expired demo link", status_code=403)
        if session.used_at is not None:
            raise AiDemoError(
                "This link was already used. Open your email and tap Resend demo link.",
                status_code=410,
            )
        if session.expires_at < _utcnow():
            session.status = "expired"
            db.add(session)
            db.commit()
            raise AiDemoError(
                "This link expired. Open your email and tap Resend demo link.",
                status_code=410,
            )
        req = AiDemoService.get_request(db, session.request_id)
        if req.demo_completed_at:
            raise AiDemoError("This demo is already complete", status_code=410)

        session.used_at = _utcnow()
        session.status = "verified"
        db.add(session)
        db.commit()
        db.refresh(session)

        memory = _json_loads(req.conversation_memory, {})
        return {
            "session_id": session.id,
            "request_id": req.id,
            "contact_name": req.contact_name,
            "company_name": req.company_name,
            "email": req.email,
            "language": session.language or req.preferred_language,
            "has_memory": bool(memory),
            "memory": memory,
            "services": list(SERVICE_CODES),
            "soft_cap_minutes": AiDemoService.get_settings(db).soft_cap_minutes or SOFT_CAP_MINUTES_DEFAULT,
        }

    @staticmethod
    def _selected_services_from_memory(req: DemoRequest, session: DemoSession) -> list[str]:
        memory = _json_loads(req.conversation_memory, {})
        raw = memory.get("selected_services") if isinstance(memory, dict) else None
        if not raw:
            raw = _json_loads(session.services_explored, [])
        if not isinstance(raw, list):
            return []
        out: list[str] = []
        for item in raw:
            code = str(item or "").strip().lower()
            if code in SERVICE_CODES and code not in out:
                out.append(code)
        return out

    @staticmethod
    def _build_runtime_prompt(db: Session, req: DemoRequest, session: DemoSession, *, service_code: str | None) -> dict[str, str]:
        from app.data.ai_demo_walkthrough_seed import PRICING_WALKTHROUGH, prompt_numbers_for_service

        AiDemoService.ensure_knowledge_bases(db)
        overview = db.execute(
            select(DemoKnowledgeBase).where(DemoKnowledgeBase.service_code == "platform_overview")
        ).scalar_one_or_none()
        selected = AiDemoService._selected_services_from_memory(req, session)
        code = (service_code or session.active_service_code or (selected[0] if selected else "") or "").strip() or None
        kb = None
        if code:
            kb = db.execute(
                select(DemoKnowledgeBase).where(DemoKnowledgeBase.service_code == code, DemoKnowledgeBase.is_active.is_(True))
            ).scalar_one_or_none()

        memory = _json_loads(req.conversation_memory, {})
        lang = session.language or req.preferred_language or "en"
        lang_line = "Respond in Arabic." if lang == "ar" else "Respond in English."

        parts = [
            overview.system_prompt if overview else "",
            overview.fact_sheet if overview else "",
            lang_line,
            f"Visitor name: {req.contact_name}. Company: {req.company_name}. Website: {req.website}.",
            f"Their message: {req.message or '(none)'}.",
            "Recording: one brief consent clause in the greeting — not a lecture.",
            "Hard soft cap about 7 minutes — wrap up with end_demo when time is up.",
            "PRICING RULES: " + "; ".join(PRICING_WALKTHROUGH.get("recommend_rules") or []),
            "Close promise: sales will send the best offer — never invent promo codes or discounts.",
        ]
        if selected:
            parts.append(
                "PRE-SELECTED SERVICES (cover in this order, one fully then transition): "
                + ", ".join(selected)
                + ". After a short need question for the first one, go straight into that walkthrough — do not ask them to pick from all five."
            )
        else:
            parts.append(
                "No services pre-selected — ask one discovery question about customers/candidates/leads/event, then switch_kb."
            )

        if memory:
            parts.append("RESUME MEMORY (do not restart from scratch): " + _json_dumps(memory))

        if code:
            nums = prompt_numbers_for_service(code)
            if nums:
                parts.append(nums)

        if selected:
            first = selected[0].replace("_", " ")
            greeting = (
                f"Hi {req.contact_name} — quick one before we jump into {first}: "
                "what's the annoying part for you right now? This call may be recorded for our sales team."
            )
        elif memory and memory.get("active_service_code"):
            greeting = (
                f"Hey {req.contact_name}, welcome back. Last time we were on "
                f"{str(memory.get('active_service_code')).replace('_', ' ')}. Want to pick up there?"
            )
        else:
            greeting = (
                f"Hi {req.contact_name} — good to meet you. This call may be recorded for sales. "
                "What's actually costing you time right now — customers, candidates, sales leads, or an event?"
            )

        if kb:
            parts.extend(
                [
                    f"ACTIVE PRODUCT KB ({kb.service_code}):",
                    kb.system_prompt,
                    "FACTS:",
                    kb.fact_sheet,
                    "DEMO BEAT:",
                    kb.demo_script,
                ]
            )
        else:
            parts.append("No product KB loaded yet — ask what they need and call switch_kb.")

        return {
            "system_prompt": "\n\n".join(p for p in parts if p).strip(),
            "first_message": greeting if lang != "ar" else (
                f"مرحباً {req.contact_name}، مكالمة قصيرة وقد تُسجَّل لفريق المبيعات. "
                "ما الذي يزعجك الآن — العملاء، المرشحون، العملاء المحتملون، أم فعالية؟"
            ),
        }

    @staticmethod
    def start_session(
        db: Session,
        *,
        session_id: str,
        selected_services: list[str] | None = None,
    ) -> dict[str, Any]:
        session = db.get(DemoSession, str(session_id or "").strip())
        if session is None:
            raise AiDemoError("Session not found", status_code=404)
        if session.status not in ("verified", "active"):
            raise AiDemoError("Session is not ready to start", status_code=409)
        req = AiDemoService.get_request(db, session.request_id)

        cleaned: list[str] = []
        for item in selected_services or []:
            code = str(item or "").strip().lower()
            if code in SERVICE_CODES and code not in cleaned:
                cleaned.append(code)
        if cleaned:
            session.services_explored = _json_dumps(cleaned)
            session.active_service_code = cleaned[0]
            AiDemoService.update_memory(
                db,
                req,
                {
                    "selected_services": cleaned,
                    "active_service_code": cleaned[0],
                    "services_explored": cleaned,
                },
            )

        resolved = AiDemoService.resolve_assistant_for_request(db, req)
        assistant_id = str(resolved.get("assistant_id") or "").strip()
        if not assistant_id:
            raise AiDemoError(
                "Demo Telnyx assistant is not configured. "
                "Set region agents in Admin → AI Marketing → AI Demos → Settings "
                "(use Duplicate AI Demo agents to create dedicated copies).",
                status_code=503,
            )
        # Safety: prefer AI Demo–named agents; warn in logs if shared id is used
        agent_name = str(resolved.get("agent_name") or "")
        if agent_name and not agent_name.startswith("AI Demo") and "ai-demo" not in agent_name.lower():
            logger.warning(
                "demo_start_non_dedicated_agent session=%s agent=%s assistant=%s — run duplicate_region_agents_for_demo",
                session.id,
                agent_name,
                assistant_id,
            )
        logger.info(
            "demo_start_assistant session=%s region=%s source=%s agent=%s assistant=%s selected=%s",
            session.id,
            resolved.get("region"),
            resolved.get("source"),
            agent_name,
            assistant_id,
            cleaned,
        )

        runtime = AiDemoService._build_runtime_prompt(
            db, req, session, service_code=session.active_service_code
        )
        try:
            from app.services.telnyx_assistant_service import prepare_telnyx_webrtc_call

            prep = prepare_telnyx_webrtc_call(
                db,
                assistant_id,
                runtime["system_prompt"],
                greeting=runtime["first_message"],
                language="ar" if (session.language or "") == "ar" else "en",
            )
        except Exception as exc:
            raise AiDemoError(str(exc), status_code=503) from exc

        # Create / attach frontpage lead for recording trail
        lead = None
        if session.frontpage_lead_call_id:
            lead = db.get(FrontpageLeadCall, session.frontpage_lead_call_id)
        if lead is None:
            from app.services.frontpage_lead_service import generate_lead_code

            lead = FrontpageLeadCall(
                lead_code=generate_lead_code(),
                contact_name=req.contact_name,
                company_name=req.company_name,
                email=req.email,
                phone=req.whatsapp_e164,
                source=SOURCE_DEMO,
                status="started",
                voice_provider="telnyx",
                provider_agent_id=assistant_id,
                started_at=_utcnow(),
                lead_data_json=_json_dumps(
                    {
                        "demo_request_id": req.id,
                        "demo_session_id": session.id,
                        "website": req.website,
                        "preferred_language": req.preferred_language,
                        "message": req.message,
                        "selected_services": cleaned,
                    }
                ),
            )
            db.add(lead)
            db.flush()
            session.frontpage_lead_call_id = lead.id
            req.frontpage_lead_call_id = lead.id

        session.status = "active"
        session.started_at = session.started_at or _utcnow()
        req.status = "active"
        req.updated_at = _utcnow()
        db.add(session)
        db.add(req)
        db.commit()

        return {
            "session_id": session.id,
            "call_id": lead.id if lead else None,
            "lead_code": lead.lead_code if lead else None,
            "voice_provider": "telnyx",
            "soft_cap_minutes": AiDemoService.get_settings(db).soft_cap_minutes or SOFT_CAP_MINUTES_DEFAULT,
            "active_service_code": session.active_service_code,
            "selected_services": cleaned or AiDemoService._selected_services_from_memory(req, session),
            "telnyx": {
                "configured": True,
                "agent_id": prep.get("assistant_id") or assistant_id,
                "web_calls_enabled": True,
                "prompt_synced": bool(prep.get("prompt_synced")),
                "first_message": runtime["first_message"],
                "recording_channels": prep.get("recording_channels", "dual"),
                "custom_headers": [
                    row
                    for row in (
                        {"name": "X-Vox-Demo-Session-Id", "value": session.id},
                        {"name": "X-Vox-Demo-Request-Id", "value": req.id},
                        {"name": "X-Vox-Call-Id", "value": lead.id if lead else ""},
                    )
                    if str(row.get("value") or "").strip()
                ],
            },
        }

    @staticmethod
    def _append_ui_event(db: Session, session: DemoSession, event: dict[str, Any]) -> None:
        events = _json_loads(session.ui_events_log, [])
        if not isinstance(events, list):
            events = []
        event = {**event, "at": _utcnow().isoformat() + "Z", "id": str(uuid4())}
        events.append(event)
        session.ui_events_log = _json_dumps(events[-200:])
        db.add(session)

    @staticmethod
    def update_memory(db: Session, req: DemoRequest, patch: dict[str, Any]) -> None:
        memory = _json_loads(req.conversation_memory, {})
        if not isinstance(memory, dict):
            memory = {}
        memory.update({k: v for k, v in patch.items() if v is not None})
        memory["updated_at"] = _utcnow().isoformat() + "Z"
        req.conversation_memory = _json_dumps(memory)
        req.updated_at = _utcnow()
        db.add(req)
        db.commit()

    @staticmethod
    def handle_tool(
        db: Session,
        *,
        tool_name: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        name = str(tool_name or "").strip().lower()
        dynamic = payload.get("dynamic_variables") if isinstance(payload.get("dynamic_variables"), dict) else {}
        session_id = (
            str(payload.get("session_id") or dynamic.get("demo_session_id") or dynamic.get("X-Vox-Demo-Session-Id") or "")
            .strip()
        )
        if not session_id:
            # Telnyx may pass custom headers differently
            session_id = str(payload.get("demo_session_id") or "").strip()
        session = db.get(DemoSession, session_id) if session_id else None
        if session is None:
            # Best-effort: latest active session for email match is not available; fail soft for Telnyx
            logger.warning("demo_tool_missing_session tool=%s payload_keys=%s", name, list(payload.keys())[:20])
            return {"status": "error", "message": "Unknown demo session"}

        req = AiDemoService.get_request(db, session.request_id)
        args = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else payload

        if name == "switch_kb":
            code = str(args.get("service") or args.get("service_code") or "").strip().lower()
            if code not in SERVICE_CODES:
                return {"status": "error", "message": f"Unknown service: {code}"}
            session.active_service_code = code
            explored = _json_loads(session.services_explored, [])
            if code not in explored:
                explored.append(code)
            session.services_explored = _json_dumps(explored)
            AiDemoService.update_memory(
                db,
                req,
                {"active_service_code": code, "services_explored": explored, "contact_name": req.contact_name},
            )
            runtime = AiDemoService._build_runtime_prompt(db, req, session, service_code=code)
            resolved = AiDemoService.resolve_assistant_for_request(db, req)
            assistant_id = str(resolved.get("assistant_id") or "").strip()
            if assistant_id:
                try:
                    from app.services.telnyx_assistant_service import prepare_telnyx_webrtc_call

                    prepare_telnyx_webrtc_call(
                        db,
                        assistant_id,
                        runtime["system_prompt"],
                        greeting=f"Sure — switching to {code.replace('_', ' ')}.",
                        language="ar" if session.language == "ar" else "en",
                    )
                except Exception:
                    logger.exception("demo_switch_kb_resync_failed")
            AiDemoService._append_ui_event(
                db,
                session,
                {"type": "switch_kb", "service": code, "transition": f"Switching to {code}"},
            )
            db.commit()
            return {"status": "ok", "service": code, "message": f"Switched to {code}"}

        if name == "show_result_panel":
            data = args.get("json") if "json" in args else args.get("data") or args
            AiDemoService._append_ui_event(db, session, {"type": "show_result_panel", "data": data})
            db.commit()
            return {"status": "ok"}

        if name == "show_link":
            AiDemoService._append_ui_event(
                db,
                session,
                {"type": "show_link", "url": args.get("url"), "label": args.get("label") or "Open link"},
            )
            db.commit()
            return {"status": "ok"}

        if name == "show_qr_code":
            from app.core.config import get_settings as _get_settings
            from app.data.ai_demo_walkthrough_seed import walkthrough_for_service

            label = str(args.get("label") or "Scan to try it").strip() or "Scan to try it"
            service = str(args.get("service") or session.active_service_code or "feedback").strip().lower()
            raw_data = args.get("data") or args.get("url")
            if not raw_data:
                base = str(getattr(_get_settings(), "public_site_base_url", None) or "https://voxbulk.com").rstrip("/")
                path = walkthrough_for_service(service).get("live_qr_path") or "/demo/live-feedback"
                raw_data = f"{base}{path}?session={session.id}&service={service}"
            AiDemoService._append_ui_event(
                db,
                session,
                {
                    "type": "show_qr_code",
                    "data": raw_data,
                    "url": raw_data,
                    "label": label,
                    "service": service,
                },
            )
            db.commit()
            return {"status": "ok", "url": raw_data}

        if name == "highlight_dashboard":
            action = str(args.get("action") or "highlight").strip().lower()
            if action not in ("highlight", "navigate", "filter", "open_chart"):
                action = "highlight"
            event = {
                "type": "highlight_dashboard",
                "action": action,
                "section": args.get("section") or session.active_service_code,
                "target": args.get("target"),
                "location": args.get("location"),
                "range": args.get("range") or args.get("range_key"),
                "view": args.get("view"),
                "delay_ms": int(args.get("delay_ms") or 400),
            }
            AiDemoService._append_ui_event(db, session, event)
            db.commit()
            return {"status": "ok", "action": action}

        if name == "show_pricing":
            from app.data.ai_demo_walkthrough_seed import PRICING_WALKTHROUGH

            recommendation = str(args.get("recommendation") or args.get("recommend") or "").strip() or None
            AiDemoService._append_ui_event(
                db,
                session,
                {
                    "type": "show_pricing",
                    "data": PRICING_WALKTHROUGH,
                    "recommendation": recommendation,
                    "service": args.get("service") or session.active_service_code,
                },
            )
            AiDemoService.update_memory(
                db,
                req,
                {"pricing_shown": True, "pricing_recommendation": recommendation},
            )
            db.commit()
            return {"status": "ok", "message": "Pricing panel shown. Explain differences and recommend."}

        if name == "request_sales_offer":
            note = str(args.get("note") or args.get("summary") or "").strip()
            volumes = args.get("volumes") if isinstance(args.get("volumes"), dict) else None
            if volumes:
                session.volume_needs = _json_dumps(volumes)
            AiDemoService.update_memory(
                db,
                req,
                {
                    "sales_offer_requested": True,
                    "sales_offer_note": note or "Visitor interested — sales to send best offer",
                    "volume_needs": volumes or _json_loads(session.volume_needs, {}),
                },
            )
            # Flag frontpage lead for sales follow-up (no email from demo)
            lead = None
            if session.frontpage_lead_call_id:
                lead = db.get(FrontpageLeadCall, session.frontpage_lead_call_id)
            if lead is not None:
                data = _json_loads(lead.lead_data_json, {})
                if not isinstance(data, dict):
                    data = {}
                data["sales_offer_requested"] = True
                data["sales_offer_note"] = note
                data["sales_followup"] = "Send best offer — do not auto-email promo from demo"
                lead.lead_data_json = _json_dumps(data)
                if lead.status in ("started", "active", None, ""):
                    lead.status = "needs_sales_offer"
                db.add(lead)
            AiDemoService._append_ui_event(
                db,
                session,
                {"type": "request_sales_offer", "note": note, "cta": "book_sales_call"},
            )
            db.commit()
            return {
                "status": "ok",
                "message": "Flagged for sales. Tell them our sales team will send the best offer — no promo codes from you.",
            }

        if name == "set_voice_lang":
            voice = str(args.get("voice") or "").strip() or None
            lang = _normalize_lang(args.get("lang") or args.get("language"))
            session.voice = voice
            session.language = lang
            req.preferred_language = lang
            AiDemoService.update_memory(db, req, {"language": lang, "voice": voice})
            AiDemoService._append_ui_event(db, session, {"type": "set_voice_lang", "voice": voice, "lang": lang})
            db.commit()
            return {"status": "ok", "lang": lang}

        if name == "log_volume_needs":
            volumes = args.get("volumes") if isinstance(args.get("volumes"), dict) else args
            session.volume_needs = _json_dumps(volumes)
            AiDemoService.update_memory(db, req, {"volume_needs": volumes})
            AiDemoService._append_ui_event(db, session, {"type": "log_volume_needs", "volumes": volumes})
            db.commit()
            return {"status": "ok"}

        if name == "end_demo":
            summary = str(args.get("summary") or "").strip()
            return AiDemoService.complete_session(
                db,
                session_id=session.id,
                summary=summary,
                transcript=str(args.get("transcript") or "") or None,
            )

        return {"status": "error", "message": f"Unknown tool: {name}"}

    @staticmethod
    def poll_events(db: Session, *, session_id: str, after_id: str | None = None) -> list[dict[str, Any]]:
        session = db.get(DemoSession, str(session_id or "").strip())
        if session is None:
            raise AiDemoError("Session not found", status_code=404)
        events = _json_loads(session.ui_events_log, [])
        if not isinstance(events, list):
            return []
        if not after_id:
            return events
        out: list[dict[str, Any]] = []
        seen = False
        for ev in events:
            if seen:
                out.append(ev)
            elif str(ev.get("id") or "") == after_id:
                seen = True
        return out

    @staticmethod
    def complete_session(
        db: Session,
        *,
        session_id: str,
        summary: str | None = None,
        transcript: str | None = None,
        recording_path: str | None = None,
        duration_seconds: int | None = None,
    ) -> dict[str, Any]:
        session = db.get(DemoSession, str(session_id or "").strip())
        if session is None:
            raise AiDemoError("Session not found", status_code=404)
        req = AiDemoService.get_request(db, session.request_id)

        now = _utcnow()
        session.status = "completed"
        session.ended_at = now
        if duration_seconds is not None:
            session.duration_seconds = int(duration_seconds)
        if transcript:
            session.transcript_log = transcript[:50000]
        AiDemoService._append_ui_event(
            db,
            session,
            {"type": "end_demo", "summary": summary or "", "cta": "book_sales_call"},
        )

        explored = _json_loads(session.services_explored, [])
        volumes = _json_loads(session.volume_needs, {})
        AiDemoService.update_memory(
            db,
            req,
            {
                "summary": summary,
                "services_explored": explored,
                "volume_needs": volumes,
                "active_service_code": session.active_service_code,
                "completed": True,
            },
        )
        req.demo_completed_at = now
        req.status = "completed"
        req.updated_at = now

        lead = None
        if session.frontpage_lead_call_id:
            lead = db.get(FrontpageLeadCall, session.frontpage_lead_call_id)
        if lead is None:
            from app.services.frontpage_lead_service import generate_lead_code

            lead = FrontpageLeadCall(
                lead_code=generate_lead_code(),
                contact_name=req.contact_name,
                company_name=req.company_name,
                email=req.email,
                phone=req.whatsapp_e164,
                source=SOURCE_DEMO,
                status="completed",
                voice_provider="telnyx",
                completed_at=now,
            )
            db.add(lead)
            db.flush()
            session.frontpage_lead_call_id = lead.id
            req.frontpage_lead_call_id = lead.id

        lead.status = "completed"
        lead.completed_at = now
        if transcript:
            lead.transcript_text = transcript[:50000]
        if recording_path:
            lead.recording_path = recording_path[:512]
        if duration_seconds is not None:
            lead.duration_seconds = int(duration_seconds)
        lead_data = _json_loads(lead.lead_data_json, {})
        if not isinstance(lead_data, dict):
            lead_data = {}
        lead_data.update(
            {
                "demo_request_id": req.id,
                "demo_session_id": session.id,
                "interest_summary": summary or lead_data.get("interest_summary"),
                "services_explored": explored,
                "volume_needs": volumes,
                "website": req.website,
                "preferred_language": req.preferred_language,
                "message": req.message,
                "demo_completed": True,
            }
        )
        lead.lead_data_json = _json_dumps(lead_data)
        db.add(lead)
        db.add(session)
        db.add(req)
        db.commit()

        try:
            from app.services.lead_sales_service import create_sales_task_from_lead

            task, _created = create_sales_task_from_lead(db, lead.id)
            if task is not None:
                req.lead_sales_task_id = task.id
                db.add(req)
                db.commit()
        except Exception:
            logger.exception("demo_sales_task_create_failed")

        return {
            "status": "ok",
            "session_id": session.id,
            "request_id": req.id,
            "lead_id": lead.id,
            "cta": "book_sales_call",
            "summary": summary,
        }

    @staticmethod
    def serialize_request(req: DemoRequest) -> dict[str, Any]:
        return {
            "id": req.id,
            "source": req.source,
            "status": req.status,
            "contact_name": req.contact_name,
            "email": req.email,
            "company_name": req.company_name,
            "whatsapp_e164": req.whatsapp_e164,
            "website": req.website,
            "preferred_language": req.preferred_language,
            "voice_region": req.voice_region,
            "message": req.message,
            "admin_notes": req.admin_notes,
            "approved_at": req.approved_at.isoformat() + "Z" if req.approved_at else None,
            "rejected_at": req.rejected_at.isoformat() + "Z" if req.rejected_at else None,
            "reject_reason": req.reject_reason,
            "demo_completed_at": req.demo_completed_at.isoformat() + "Z" if req.demo_completed_at else None,
            "frontpage_lead_call_id": req.frontpage_lead_call_id,
            "lead_sales_task_id": req.lead_sales_task_id,
            "conversation_memory": _json_loads(req.conversation_memory, {}),
            "email_sent_at": req.email_sent_at.isoformat() + "Z" if req.email_sent_at else None,
            "opened_at": req.opened_at.isoformat() + "Z" if req.opened_at else None,
            "open_count": int(req.open_count or 0),
            "link_clicked_at": req.link_clicked_at.isoformat() + "Z" if req.link_clicked_at else None,
            "click_count": int(req.click_count or 0),
            "created_at": req.created_at.isoformat() + "Z" if req.created_at else None,
        }

    @staticmethod
    def get_request_detail(db: Session, request_id: str) -> dict[str, Any]:
        req = AiDemoService.get_request(db, request_id)
        out = AiDemoService.serialize_request(req)
        sessions = db.execute(
            select(DemoSession).where(DemoSession.request_id == req.id).order_by(DemoSession.created_at.desc())
        ).scalars().all()
        out["sessions"] = [
            {
                "id": s.id,
                "status": s.status,
                "active_service_code": s.active_service_code,
                "services_explored": _json_loads(s.services_explored, []),
                "volume_needs": _json_loads(s.volume_needs, {}),
                "started_at": s.started_at.isoformat() + "Z" if s.started_at else None,
                "ended_at": s.ended_at.isoformat() + "Z" if s.ended_at else None,
                "used_at": s.used_at.isoformat() + "Z" if s.used_at else None,
                "expires_at": s.expires_at.isoformat() + "Z" if s.expires_at else None,
                "duration_seconds": s.duration_seconds,
                "transcript_log": (s.transcript_log or "")[:20000] or None,
            }
            for s in sessions
        ]
        lead = None
        if req.frontpage_lead_call_id:
            lead = db.get(FrontpageLeadCall, req.frontpage_lead_call_id)
        if lead is not None:
            lead_data = _json_loads(lead.lead_data_json, {})
            out["lead"] = {
                "id": lead.id,
                "lead_code": lead.lead_code,
                "status": lead.status,
                "recommendation": lead.recommendation,
                "sentiment": lead.sentiment,
                "transcript_text": lead.transcript_text,
                "recording_path": lead.recording_path,
                "duration_seconds": lead.duration_seconds,
                "interest_summary": lead_data.get("interest_summary") if isinstance(lead_data, dict) else None,
                "services_explored": lead_data.get("services_explored") if isinstance(lead_data, dict) else None,
                "volume_needs": lead_data.get("volume_needs") if isinstance(lead_data, dict) else None,
            }
        else:
            out["lead"] = None
        return out

    @staticmethod
    def list_knowledge_bases(db: Session) -> list[dict[str, Any]]:
        AiDemoService.ensure_knowledge_bases(db)
        rows = db.execute(select(DemoKnowledgeBase).order_by(DemoKnowledgeBase.sort_order)).scalars().all()
        return [
            {
                "id": r.id,
                "service_code": r.service_code,
                "title": r.title,
                "system_prompt": r.system_prompt,
                "fact_sheet": r.fact_sheet,
                "demo_script": r.demo_script,
                "tool_subset": _json_loads(r.tool_subset, []),
                "sort_order": r.sort_order,
                "is_active": r.is_active,
                "updated_at": r.updated_at.isoformat() + "Z" if r.updated_at else None,
            }
            for r in rows
        ]

    @staticmethod
    def update_knowledge_base(db: Session, service_code: str, payload: dict[str, Any]) -> dict[str, Any]:
        AiDemoService.ensure_knowledge_bases(db)
        row = db.execute(
            select(DemoKnowledgeBase).where(DemoKnowledgeBase.service_code == service_code.strip().lower())
        ).scalar_one_or_none()
        if row is None:
            raise AiDemoError("Knowledge base not found", status_code=404)
        for field in ("title", "system_prompt", "fact_sheet", "demo_script"):
            if field in payload and payload[field] is not None:
                setattr(row, field, str(payload[field]))
        if "tool_subset" in payload and payload["tool_subset"] is not None:
            row.tool_subset = _json_dumps(payload["tool_subset"])
        if "is_active" in payload and payload["is_active"] is not None:
            row.is_active = bool(payload["is_active"])
        row.updated_at = _utcnow()
        db.add(row)
        db.commit()
        return AiDemoService.list_knowledge_bases(db)

    @staticmethod
    def get_walkthrough_data(db: Session, *, session_id: str, service: str | None = None) -> dict[str, Any]:
        from app.data.ai_demo_walkthrough_seed import PRICING_WALKTHROUGH, walkthrough_for_service

        session = db.get(DemoSession, str(session_id or "").strip())
        if session is None:
            raise AiDemoError("Session not found", status_code=404)
        code = str(service or session.active_service_code or "feedback").strip().lower()
        data = walkthrough_for_service(code)
        return {
            "session_id": session.id,
            "service": code,
            "data": data,
            "pricing": PRICING_WALKTHROUGH,
            "selected_services": AiDemoService._selected_services_from_memory(
                AiDemoService.get_request(db, session.request_id), session
            ),
        }

    @staticmethod
    def submit_live_demo_response(
        db: Session,
        *,
        session_id: str,
        service: str,
        score: int | None = None,
        comment: str | None = None,
        name: str | None = None,
        company: str | None = None,
        location: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Visitor completed a demo QR flow — push live_response UI event (no real org write)."""
        session = db.get(DemoSession, str(session_id or "").strip())
        if session is None:
            raise AiDemoError("Session not found", status_code=404)
        svc = str(service or session.active_service_code or "feedback").strip().lower()
        payload = {
            "service": svc,
            "score": score,
            "comment": (comment or "").strip()[:500],
            "name": (name or "").strip()[:120] or "You",
            "company": (company or "").strip()[:120],
            "location": (location or "").strip()[:80] or "Leeds",
            "at": _utcnow().isoformat() + "Z",
        }
        if extra and isinstance(extra, dict):
            payload.update({k: v for k, v in extra.items() if k not in payload})
        AiDemoService._append_ui_event(
            db,
            session,
            {"type": "live_response", "service": svc, "data": payload},
        )
        db.commit()
        return {"ok": True, "event": "live_response", "data": payload}
