"""Smart Card QR session flow — contact → questions → lead + email."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.smart_card import (
    SMART_CARD_PREVIEW_TESTS_LIMIT,
    SmartCardCompany,
    SmartCardLead,
    SmartCardQuestionTemplate,
    SmartCardRepresentative,
    SmartCardResponse,
    SmartCardSession,
)
from app.services.smart_card.company_service import SmartCardCompanyService, SmartCardEntitlementService
from app.services.smart_card.email_service import SmartCardEmailService

logger = logging.getLogger(__name__)

DEFAULT_STEPS = ("contact", "interest", "role", "timeline", "follow_up", "consent_info", "open_feedback")


def _score_lead(*, interest: str | None, timeline: str | None, consent: str | None) -> str:
    c = (consent or "").lower()
    if c in {"no", "n"}:
        return "cold"
    t = (timeline or "").lower()
    if any(x in t for x in ("asap", "this week", "week", "soon", "immediate")):
        return "hot"
    if any(x in t for x in ("month", "this month")):
        return "warm"
    if interest and len(interest.strip()) > 40:
        return "warm"
    return "cold"


def _ai_summary(lead: SmartCardLead, rep_name: str) -> str:
    parts = [
        f"{lead.name or 'A visitor'} from {lead.company or 'an unknown company'}",
        f"spoke with {rep_name}",
    ]
    if lead.interest:
        parts.append(f"Interest: {lead.interest[:200]}")
    if lead.buying_timeline:
        parts.append(f"Timeline: {lead.buying_timeline}")
    parts.append(f"Score: {lead.lead_score or 'n/a'}")
    return ". ".join(parts) + "."


def _follow_up_draft(lead: SmartCardLead) -> str:
    name = (lead.name or "there").split()[0]
    return (
        f"Hi {name}, thanks for scanning our Smart Card QR. "
        f"Happy to share more on {lead.interest or 'our products'} — "
        f"when works for a quick follow-up?"
    )


class SmartCardSessionError(ValueError):
    pass


class SmartCardSessionFlowService:
    @staticmethod
    def _prompts(db: Session) -> dict[str, str]:
        rows = db.execute(select(SmartCardQuestionTemplate)).scalars().all()
        return {r.question_key: r.prompt for r in rows}

    @staticmethod
    def _contact_capture(company: SmartCardCompany) -> str:
        cfg = None
        if company.question_config_json:
            try:
                cfg = json.loads(company.question_config_json)
            except Exception:
                cfg = None
        if isinstance(cfg, dict):
            mode = str(cfg.get("contact_capture") or "offer_both").strip().lower()
            if mode in {"offer_both", "manual_only", "card_only"}:
                return mode
        return "offer_both"

    @staticmethod
    def _contact_step_key(company: SmartCardCompany) -> str:
        mode = SmartCardSessionFlowService._contact_capture(company)
        if mode == "card_only":
            return "contact_card_only"
        if mode == "manual_only":
            return "contact_manual"
        return "contact"

    @staticmethod
    def _steps_for_company(company: SmartCardCompany) -> list[str]:
        cfg = None
        if company.question_config_json:
            try:
                cfg = json.loads(company.question_config_json)
            except Exception:
                cfg = None
        contact_key = SmartCardSessionFlowService._contact_step_key(company)
        system_skip = {
            "contact",
            "contact_web",
            "contact_card_only",
            "contact_manual",
            "contact_company",
            "contact_mobile",
            "contact_confirm",
            "thank_you",
            "company_card",
            "post_complete_handoff",
        }
        if isinstance(cfg, dict) and isinstance(cfg.get("selected_keys"), list) and cfg["selected_keys"]:
            keys = [
                str(k)
                for k in cfg["selected_keys"]
                if str(k).strip() and str(k).strip() not in system_skip
            ]
            # Always start with contact (mode-aware)
            return [contact_key, *keys]
        return [contact_key, *[k for k in DEFAULT_STEPS if k != "contact"]]

    @staticmethod
    def start_session(
        db: Session,
        *,
        rep: SmartCardRepresentative,
        channel: str = "web",
        visitor_phone: str | None = None,
        visitor_email: str | None = None,
        name: str | None = None,
        company_name: str | None = None,
    ) -> dict[str, Any]:
        mode = SmartCardEntitlementService.access_mode(db, rep.org_id)
        if mode == "expired":
            raise SmartCardSessionError("expired")
        if mode == "preview_exhausted":
            raise SmartCardSessionError("preview_exhausted")

        company = SmartCardCompanyService.get_or_create(db, rep.org_id)
        is_preview = mode == "preview"
        if is_preview:
            company.preview_tests_used = int(company.preview_tests_used or 0) + 1
            company.updated_at = datetime.utcnow()
            db.add(company)
            if company.preview_tests_used > SMART_CARD_PREVIEW_TESTS_LIMIT:
                raise SmartCardSessionError("preview_exhausted")

        steps = SmartCardSessionFlowService._steps_for_company(company)
        state = {
            "steps": steps,
            "step_index": 0,
            "name": name,
            "company": company_name,
            "visitor_email": visitor_email,
            "visitor_phone": visitor_phone,
            "answers": {},
        }
        session = SmartCardSession(
            id=str(uuid.uuid4()),
            org_id=rep.org_id,
            representative_id=rep.id,
            channel=channel[:16],
            visitor_phone=visitor_phone,
            status="active",
            current_step=steps[0] if steps else "contact",
            state_json=json.dumps(state),
            is_preview=is_preview,
        )
        db.add(session)
        rep.scan_count = int(rep.scan_count or 0) + 1
        rep.updated_at = datetime.utcnow()
        db.add(rep)
        db.flush()

        prompts = SmartCardSessionFlowService._prompts(db)
        first = steps[0] if steps else "contact"
        prompt = prompts.get(first) or prompts.get("contact") or "Please continue."
        return {
            "ok": True,
            "session_id": session.id,
            "is_preview": is_preview,
            "contact_capture": SmartCardSessionFlowService._contact_capture(company),
            "step": session.current_step,
            "prompt": prompt,
            "steps": steps,
            "step_index": 0,
            "step_total": len(steps),
            "allow_voice": False,
        }

    @staticmethod
    def _load_state(session: SmartCardSession) -> dict[str, Any]:
        try:
            return json.loads(session.state_json or "{}")
        except Exception:
            return {"steps": list(DEFAULT_STEPS), "step_index": 0, "answers": {}}

    @staticmethod
    def advance(
        db: Session,
        *,
        session: SmartCardSession,
        answer: str,
        answer_source: str = "text",
        original_text: str | None = None,
        answer_text_en: str | None = None,
        voice_job_id: str | None = None,
    ) -> dict[str, Any]:
        if session.status != "active":
            raise SmartCardSessionError("Session is not active")
        state = SmartCardSessionFlowService._load_state(session)
        steps: list[str] = list(state.get("steps") or DEFAULT_STEPS)
        idx = int(state.get("step_index") or 0)
        step = steps[idx] if 0 <= idx < len(steps) else None
        text = str(answer or "").strip()
        src = str(answer_source or "text").strip().lower() or "text"
        orig = (str(original_text).strip() if original_text is not None else "") or None
        en = (str(answer_text_en).strip() if answer_text_en is not None else "") or None
        if src == "voice":
            if not orig:
                orig = text or None
            if not en:
                en = text or None

        if step in {"contact", "contact_card_only", "contact_manual", "contact_web"}:
            # Accept "Name | Company | email | phone" or plain name
            parts = [p.strip() for p in text.replace("\n", "|").split("|") if p.strip()]
            if parts:
                state["name"] = parts[0]
            if len(parts) > 1:
                state["company"] = parts[1]
            if len(parts) > 2 and "@" in parts[2]:
                state["visitor_email"] = parts[2]
            if len(parts) > 3:
                state["visitor_phone"] = parts[3]
            elif len(parts) > 2 and "@" not in parts[2]:
                state["visitor_phone"] = parts[2]
        else:
            state.setdefault("answers", {})[step or "unknown"] = text
            if step == "interest":
                state["interest"] = text
            if step == "timeline":
                state["timeline"] = text
            if step == "consent_info":
                state["consent"] = text

        db.add(
            SmartCardResponse(
                org_id=session.org_id,
                session_id=session.id,
                question_key=step or "unknown",
                answer_text=text[:8000],
                original_text=(orig[:8000] if orig else None),
                answer_text_en=(en[:8000] if en else None),
                answer_source=src[:16],
                voice_job_id=(str(voice_job_id).strip() or None) if voice_job_id else None,
            )
        )

        idx += 1
        state["step_index"] = idx
        if idx >= len(steps):
            return SmartCardSessionFlowService._complete(db, session=session, state=state)

        next_step = steps[idx]
        session.current_step = next_step
        session.state_json = json.dumps(state)
        session.updated_at = datetime.utcnow()
        db.add(session)
        db.flush()
        prompts = SmartCardSessionFlowService._prompts(db)
        contactish = str(next_step).startswith("contact")
        return {
            "ok": True,
            "session_id": session.id,
            "done": False,
            "step": next_step,
            "prompt": prompts.get(next_step, "Please continue."),
            "answer_source": answer_source,
            "step_index": idx,
            "step_total": len(steps),
            "allow_voice": (not contactish) and next_step not in {"consent_info"},
        }

    @staticmethod
    def apply_card_ocr(
        db: Session,
        *,
        session: SmartCardSession,
        name: str | None,
        company: str | None,
        email: str | None,
        phone: str | None,
    ) -> dict[str, Any]:
        state = SmartCardSessionFlowService._load_state(session)
        if name:
            state["name"] = name
        if company:
            state["company"] = company
        if email:
            state["visitor_email"] = email
        if phone:
            state["visitor_phone"] = phone
        session.state_json = json.dumps(state)
        session.updated_at = datetime.utcnow()
        db.add(session)
        db.flush()
        return {
            "ok": True,
            "extracted": {
                "name": state.get("name"),
                "company": state.get("company"),
                "email": state.get("visitor_email"),
                "phone": state.get("visitor_phone"),
            },
            "prompt": "Please confirm these details are correct (Yes), or type corrections as Name | Company | email | phone.",
            "step": "contact",
        }

    @staticmethod
    def _complete(db: Session, *, session: SmartCardSession, state: dict[str, Any]) -> dict[str, Any]:
        rep = db.get(SmartCardRepresentative, session.representative_id)
        if rep is None:
            raise SmartCardSessionError("Representative missing")

        answers = state.get("answers") or {}
        lead = SmartCardLead(
            id=str(uuid.uuid4()),
            org_id=session.org_id,
            representative_id=rep.id,
            session_id=session.id,
            visitor_phone=state.get("visitor_phone") or session.visitor_phone,
            visitor_email=state.get("visitor_email"),
            name=state.get("name"),
            company=state.get("company"),
            interest=state.get("interest") or answers.get("interest"),
            buying_timeline=state.get("timeline") or answers.get("timeline"),
            consent=state.get("consent") or answers.get("consent_info"),
            channel=session.channel,
            follow_up_status="open",
        )
        lead.lead_score = _score_lead(
            interest=lead.interest,
            timeline=lead.buying_timeline,
            consent=lead.consent,
        )
        lead.ai_summary = _ai_summary(lead, rep.name)
        lead.suggested_follow_up = _follow_up_draft(lead)
        db.add(lead)
        db.flush()

        session.status = "completed"
        session.lead_id = lead.id
        session.completed_at = datetime.utcnow()
        session.state_json = json.dumps(state)
        session.updated_at = datetime.utcnow()
        db.add(session)
        db.flush()

        try:
            SmartCardEmailService.notify_rep_lead(db, rep=rep, lead=lead)
        except Exception:
            logger.exception("smart_card_lead_email_failed")

        # Hot-lead alert to the rep's mobile — best-effort, never blocks completion.
        score = str(lead.lead_score or "").lower()
        if score in {"hot", "high"} and getattr(rep, "mobile", None):
            try:
                from app.services.smart_card.hot_lead_notify_service import notify_hot_lead

                notify_hot_lead(db, rep=rep, lead=lead)
            except Exception:
                logger.exception("smart_card_hot_lead_notify_dispatch_failed lead=%s", lead.id)

        return {
            "ok": True,
            "done": True,
            "session_id": session.id,
            "lead_id": lead.id,
            "lead_score": lead.lead_score,
            "message": "Thank you — we have shared your details with the representative.",
            "suggested_follow_up": lead.suggested_follow_up,
        }
