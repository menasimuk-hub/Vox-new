"""Expo channel-agnostic conversation engine — shared by the WhatsApp adapter and the public web fallback.

Returns plain data (next prompt text, pending asset candidates, delivered assets) so each channel
adapter can format it however it needs to (WhatsApp text messages vs. JSON for the web widget).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.expo import ExpoBooth, ExpoLead, ExpoResponse, ExpoSession
from app.services.expo.offer_delivery_service import (
    load_booth_assets,
    mark_lead_offer_sent,
    pick_assets_for_interest,
    resolve_pick_reply,
)
from app.services.expo.question_bank import (
    CONTACT_COMPANY_PROMPT,
    CONTACT_MOBILE_PROMPT,
    CONTACT_STEP_KEY,
    build_thank_you_message,
    contact_prompt_for_mode,
    parse_contact_capture,
    parse_question_config,
)
from app.services.expo.business_card_ocr_service import ExpoBusinessCardService
from app.services.expo.scoring_service import score_lead

THANK_YOU_TEXT = "Thanks so much for stopping by our stand — we'll be in touch soon!"

_YES_WORDS = frozenset({"yes", "y", "yeah", "yep", "sure", "ok", "okay", "please", "affirmative"})
_NO_WORDS = frozenset({"no", "n", "nope", "nah", "negative", "not interested", "no thanks"})


def _looks_affirmative(text: str) -> bool:
    lower = str(text or "").strip().lower()
    if not lower:
        return False
    if lower in _NO_WORDS:
        return False
    if lower in _YES_WORDS:
        return True
    return lower.startswith("yes")


def _empty_step_result(*, done: bool, prompt: str | None) -> dict[str, Any]:
    return {"done": done, "awaiting_pick": False, "candidates": None, "assets": None, "prompt": prompt}


class ExpoSessionFlowService:
    @staticmethod
    def steps_for_booth(booth: ExpoBooth) -> list[dict[str, Any]]:
        return parse_question_config(booth.question_config_json)

    @staticmethod
    def find_active_session(db: Session, *, visitor_phone: str) -> ExpoSession | None:
        cutoff = datetime.utcnow() - timedelta(hours=24)
        return db.execute(
            select(ExpoSession)
            .where(
                ExpoSession.visitor_phone == visitor_phone,
                ExpoSession.status == "active",
                ExpoSession.started_at >= cutoff,
            )
            .order_by(ExpoSession.started_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    @staticmethod
    def supersede_active_sessions(
        db: Session,
        *,
        visitor_phone: str,
        reason: str = "new_booth_scan",
        except_session_id: str | None = None,
    ) -> int:
        """End every active Expo session for this phone (shared WA line, many booths).

        Prevents Stand A questions/PDFs from continuing after the visitor scans Stand B.
        Does not send thank-you or mark leads completed — status becomes ``superseded``.
        """
        phone = str(visitor_phone or "").strip()
        if not phone:
            return 0
        cutoff = datetime.utcnow() - timedelta(hours=24)
        rows = (
            db.execute(
                select(ExpoSession).where(
                    ExpoSession.visitor_phone == phone,
                    ExpoSession.status == "active",
                    ExpoSession.started_at >= cutoff,
                )
            )
            .scalars()
            .all()
        )
        now = datetime.utcnow()
        closed = 0
        for session in rows:
            if except_session_id and session.id == except_session_id:
                continue
            state = ExpoSessionFlowService._load_state(session)
            state["superseded_reason"] = str(reason or "new_booth_scan")[:64]
            state["superseded_at"] = now.isoformat()
            ExpoSessionFlowService._save_state(session, state)
            session.status = "superseded"
            session.completed_at = now
            db.add(session)
            closed += 1
        if closed:
            db.flush()
        return closed

    @staticmethod
    def phone_has_recent_expo_activity(db: Session, *, visitor_phone: str, hours: int = 24) -> bool:
        """True when this phone recently ran an Expo booth chat (active or just completed).

        Used to keep post-questionnaire replies (e.g. “No problem”) from falling into
        sales-automation keyword handlers on the shared WhatsApp line.
        """
        phone = str(visitor_phone or "").strip()
        if not phone:
            return False
        cutoff = datetime.utcnow() - timedelta(hours=max(1, int(hours or 24)))
        row = db.execute(
            select(ExpoSession.id)
            .where(
                ExpoSession.visitor_phone == phone,
                ExpoSession.started_at >= cutoff,
            )
            .limit(1)
        ).scalar_one_or_none()
        return row is not None

    @staticmethod
    def _lead_for_session(db: Session, session: ExpoSession) -> ExpoLead | None:
        return db.execute(select(ExpoLead).where(ExpoLead.session_id == session.id)).scalar_one_or_none()

    @staticmethod
    def _load_state(session: ExpoSession) -> dict[str, Any]:
        try:
            data = json.loads(session.session_state_json or "{}")
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    @staticmethod
    def _save_state(session: ExpoSession, state: dict[str, Any]) -> None:
        session.session_state_json = json.dumps(state)

    # ------------------------------------------------------------------
    # New session
    # ------------------------------------------------------------------

    @staticmethod
    def start_session(
        db: Session,
        *,
        booth: ExpoBooth,
        channel: str,
        visitor_phone: str,
        visitor_email: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        # One phone → one active Expo booth chat. New QR always wins (stops catalog mix-ups).
        closed = ExpoSessionFlowService.supersede_active_sessions(
            db,
            visitor_phone=visitor_phone,
            reason="new_booth_scan",
        )
        booth.scan_count = int(booth.scan_count or 0) + 1
        db.add(booth)

        now = datetime.utcnow()
        session = ExpoSession(
            id=str(uuid.uuid4()),
            org_id=booth.org_id,
            booth_id=booth.id,
            channel=str(channel or "whatsapp")[:16],
            visitor_phone=visitor_phone,
            visitor_email=visitor_email,
            status="active",
            current_step=0,
            session_state_json=json.dumps({}),
            started_at=now,
            created_at=now,
        )
        db.add(session)
        db.flush()

        lead = ExpoLead(
            id=str(uuid.uuid4()),
            org_id=booth.org_id,
            booth_id=booth.id,
            exhibition_id=booth.exhibition_id,
            session_id=session.id,
            visitor_phone=visitor_phone,
            visitor_email=visitor_email,
            name=name,
            created_at=now,
            updated_at=now,
        )
        db.add(lead)

        steps = ExpoSessionFlowService.steps_for_booth(booth)
        if not steps:
            session.status = "failed"
            db.add(session)
            db.commit()
            return {
                "session_id": session.id,
                "done": True,
                "prompt": build_thank_you_message(booth.question_config_json),
                "superseded_sessions": closed,
            }

        first = steps[0]
        channel_l = str(channel or "whatsapp").lower()
        if str(first.get("key") or "") == CONTACT_STEP_KEY:
            capture = parse_contact_capture(booth.question_config_json)
            prompt = contact_prompt_for_mode(capture, channel=channel_l)
            if channel_l == "web" and first.get("prompt_web"):
                # Prefer mode-aware prompt; stored prompt_web may be stale
                prompt = contact_prompt_for_mode(capture, channel="web")
            state = {"contact_substep": "awaiting"}
            session.session_state_json = json.dumps(state)
            db.add(session)
        else:
            prompt = str(first.get("prompt") or "")

        # Web start may already include name
        if name and lead is not None:
            lead.name = str(name)[:255]
            db.add(lead)

        db.commit()
        return {
            "session_id": session.id,
            "done": False,
            "prompt": prompt,
            "superseded_sessions": closed,
        }

    # ------------------------------------------------------------------
    # Advancing an existing session
    # ------------------------------------------------------------------

    @staticmethod
    def advance(
        db: Session,
        *,
        session: ExpoSession,
        answer: str,
        answer_source: str = "text",
        contact_fields: dict[str, str | None] | None = None,
    ) -> dict[str, Any]:
        booth = db.get(ExpoBooth, session.booth_id)
        if booth is None:
            session.status = "failed"
            db.add(session)
            db.commit()
            return _empty_step_result(done=True, prompt=THANK_YOU_TEXT)

        lead = ExpoSessionFlowService._lead_for_session(db, session)
        state = ExpoSessionFlowService._load_state(session)
        clean = str(answer or "").strip()
        source = str(answer_source or "text").strip().lower() or "text"

        if state.get("pending_asset_pick"):
            return ExpoSessionFlowService._resolve_pick(
                db, session=session, booth=booth, lead=lead, state=state, text=clean
            )

        steps = ExpoSessionFlowService.steps_for_booth(booth)
        step_index = int(session.current_step or 0)
        if step_index >= len(steps):
            return ExpoSessionFlowService._complete(db, session=session, booth=booth, lead=lead)

        step = steps[step_index]
        key = str(step.get("key") or "")

        if key == CONTACT_STEP_KEY or state.get("contact_substep"):
            return ExpoSessionFlowService._advance_contact(
                db,
                session=session,
                booth=booth,
                lead=lead,
                state=state,
                answer=clean,
                answer_source=source,
                steps=steps,
                contact_fields=contact_fields,
            )

        db.add(
            ExpoResponse(
                id=str(uuid.uuid4()),
                session_id=session.id,
                org_id=session.org_id,
                booth_id=booth.id,
                question_key=key,
                answer_text=clean,
                original_text=clean,
                answer_text_en=clean,
                step_order=step_index + 1,
                answer_source=source,
                created_at=datetime.utcnow(),
            )
        )

        if lead is not None:
            ExpoSessionFlowService._apply_answer_to_lead(lead, key, clean)
            db.add(lead)

        session.current_step = step_index + 1
        db.add(session)

        if key in {"interest", "need_price_list", "need_catalogue", "products_wanted"} and lead is not None:
            interest_text = clean
            if key == "need_price_list" and _looks_affirmative(clean):
                interest_text = "price list pricing price"
            elif key == "need_catalogue" and _looks_affirmative(clean):
                interest_text = "catalogue catalog brochure"
            elif key in {"need_price_list", "need_catalogue"} and not _looks_affirmative(clean):
                db.commit()
                return ExpoSessionFlowService._next_prompt(db, session=session, booth=booth, lead=lead)
            offer_mode, candidates = ExpoSessionFlowService._offer_after_interest(
                db, booth=booth, interest_text=interest_text
            )
            if offer_mode in ("list", "full") and candidates:
                state["pending_asset_pick"] = candidates
                ExpoSessionFlowService._save_state(session, state)
                db.add(session)
                db.commit()
                return {"done": False, "awaiting_pick": True, "candidates": candidates, "assets": None, "prompt": None}
            if offer_mode == "direct" and candidates:
                asset = candidates[0]
                mark_lead_offer_sent(db, lead, asset)
                db.add(lead)
                db.commit()
                result = ExpoSessionFlowService._next_prompt(db, session=session, booth=booth, lead=lead)
                result["assets"] = [asset]
                return result

        db.commit()
        return ExpoSessionFlowService._next_prompt(db, session=session, booth=booth, lead=lead)

    @staticmethod
    def _advance_contact(
        db: Session,
        *,
        session: ExpoSession,
        booth: ExpoBooth,
        lead: ExpoLead | None,
        state: dict[str, Any],
        answer: str,
        answer_source: str,
        steps: list[dict[str, Any]],
        contact_fields: dict[str, str | None] | None = None,
    ) -> dict[str, Any]:
        """Business-card photo OCR fills contact + skips name/company/mobile; otherwise collect them in order."""
        sub = str(state.get("contact_substep") or "awaiting").strip().lower()
        channel = str(session.channel or "whatsapp").lower()
        capture = parse_contact_capture(booth.question_config_json)
        is_image = answer_source in {"image", "photo", "business_card", "card"}

        def _log(key: str, text: str, source: str) -> None:
            db.add(
                ExpoResponse(
                    id=str(uuid.uuid4()),
                    session_id=session.id,
                    org_id=session.org_id,
                    booth_id=booth.id,
                    question_key=key,
                    answer_text=text[:4000],
                    original_text=text[:4000],
                    answer_text_en=text[:4000],
                    step_order=int(session.current_step or 0) + 1,
                    answer_source=source,
                    created_at=datetime.utcnow(),
                )
            )

        # Photo of business card → OCR + skip typed contact fields
        if sub == "awaiting" and is_image and capture != "manual_only":
            fields = {k: (str(v).strip() if v else None) for k, v in (contact_fields or {}).items()}
            _log("business_card", answer or "[business card image]", "image")
            if lead is not None:
                if fields.get("name"):
                    lead.name = fields["name"][:255]
                if fields.get("company"):
                    lead.company = fields["company"][:255]
                if fields.get("email"):
                    lead.visitor_email = fields["email"][:255]
                    session.visitor_email = fields["email"][:255]
                # Prefer card phone only when we don't already have WA from-number
                if fields.get("phone") and not str(lead.visitor_phone or session.visitor_phone or "").strip():
                    lead.visitor_phone = fields["phone"][:32]
                    session.visitor_phone = fields["phone"][:32]
                lead.updated_at = datetime.utcnow()
                db.add(lead)
                db.add(session)
            for fk in ("name", "company", "email", "phone"):
                if fields.get(fk):
                    _log(f"card_{fk}", str(fields[fk]), "ocr")
            state["contact_substep"] = "done"
            state["contact_via"] = "card"
            state["card_fields"] = {k: v for k, v in fields.items() if v}
            ExpoSessionFlowService._save_state(session, state)
            if steps and str(steps[0].get("key") or "") == CONTACT_STEP_KEY:
                session.current_step = 1
            db.add(session)
            db.commit()
            confirm = ExpoBusinessCardService.confirmation_message(fields)
            nxt = ExpoSessionFlowService._next_prompt(db, session=session, booth=booth, lead=lead)
            next_prompt = str(nxt.get("prompt") or "").strip()
            nxt["prompt"] = f"{confirm}\n\n{next_prompt}".strip() if next_prompt else confirm
            nxt["contact_via"] = "card"
            nxt["card_fields"] = fields
            return nxt

        if sub == "awaiting" and capture == "card_only" and not is_image:
            return _empty_step_result(
                done=False,
                prompt=contact_prompt_for_mode("card_only", channel=channel),
            )

        if sub == "awaiting":
            # Typed name
            if not answer:
                prompt = contact_prompt_for_mode(capture, channel=channel)
                return _empty_step_result(done=False, prompt=prompt)
            _log("name", answer, answer_source)
            if lead is not None:
                lead.name = answer[:255]
                lead.updated_at = datetime.utcnow()
                db.add(lead)
            state["contact_substep"] = "company"
            state["contact_via"] = "manual"
            ExpoSessionFlowService._save_state(session, state)
            db.add(session)
            db.commit()
            return _empty_step_result(done=False, prompt=CONTACT_COMPANY_PROMPT)

        if sub == "company":
            if not answer:
                return _empty_step_result(done=False, prompt=CONTACT_COMPANY_PROMPT)
            _log("company", answer, answer_source)
            if lead is not None:
                lead.company = answer[:255]
                lead.updated_at = datetime.utcnow()
                db.add(lead)
            # WhatsApp already has the visitor mobile; web still needs it if not set
            need_mobile = channel == "web" and not str(session.visitor_phone or "").strip()
            if need_mobile:
                state["contact_substep"] = "mobile"
                ExpoSessionFlowService._save_state(session, state)
                db.add(session)
                db.commit()
                return _empty_step_result(done=False, prompt=CONTACT_MOBILE_PROMPT)
            state["contact_substep"] = "done"
            ExpoSessionFlowService._save_state(session, state)
            if steps and str(steps[0].get("key") or "") == CONTACT_STEP_KEY:
                session.current_step = 1
            db.add(session)
            db.commit()
            return ExpoSessionFlowService._next_prompt(db, session=session, booth=booth, lead=lead)

        if sub == "mobile":
            if not answer:
                return _empty_step_result(done=False, prompt=CONTACT_MOBILE_PROMPT)
            _log("mobile", answer, answer_source)
            session.visitor_phone = answer[:32]
            if lead is not None:
                lead.visitor_phone = answer[:32]
                lead.updated_at = datetime.utcnow()
                db.add(lead)
            state["contact_substep"] = "done"
            ExpoSessionFlowService._save_state(session, state)
            if steps and str(steps[0].get("key") or "") == CONTACT_STEP_KEY:
                session.current_step = 1
            db.add(session)
            db.commit()
            return ExpoSessionFlowService._next_prompt(db, session=session, booth=booth, lead=lead)

        # Already done — advance past contact
        if steps and str(steps[0].get("key") or "") == CONTACT_STEP_KEY and int(session.current_step or 0) == 0:
            session.current_step = 1
            db.add(session)
            db.commit()
        return ExpoSessionFlowService._next_prompt(db, session=session, booth=booth, lead=lead)

    @staticmethod
    def _apply_answer_to_lead(lead: ExpoLead, key: str, text: str) -> None:
        clean = text.strip()
        if not clean:
            return
        if key == "name":
            lead.name = clean[:255]
        elif key == "company":
            lead.company = clean[:255]
        elif key == "interest":
            lead.interest = clean
        elif key == "timeline":
            lead.buying_timeline = clean[:255]
        elif key in ("consent_info", "consent"):
            lead.consent_acknowledged = _looks_affirmative(clean)
        lead.updated_at = datetime.utcnow()

    # ------------------------------------------------------------------
    # Hybrid asset offer (fires right after the "interest" answer)
    # ------------------------------------------------------------------

    @staticmethod
    def _offer_after_interest(db: Session, *, booth: ExpoBooth, interest_text: str) -> tuple[str, list[dict[str, Any]]]:
        assets = load_booth_assets(db, booth.id)
        if not assets:
            return "none", []
        return pick_assets_for_interest(interest_text, assets)

    @staticmethod
    def _resolve_pick(
        db: Session,
        *,
        session: ExpoSession,
        booth: ExpoBooth,
        lead: ExpoLead | None,
        state: dict[str, Any],
        text: str,
    ) -> dict[str, Any]:
        pending = state.get("pending_asset_pick") or []
        match = resolve_pick_reply(text, pending)
        if match is None:
            return {
                "done": False,
                "awaiting_pick": True,
                "candidates": pending,
                "assets": None,
                "prompt": None,
                "retry": True,
            }

        if lead is not None:
            mark_lead_offer_sent(db, lead, match)
            db.add(lead)

        state.pop("pending_asset_pick", None)
        ExpoSessionFlowService._save_state(session, state)
        db.add(session)
        db.commit()

        result = ExpoSessionFlowService._next_prompt(db, session=session, booth=booth, lead=lead)
        result["assets"] = [match]
        return result

    # ------------------------------------------------------------------
    # Question flow continuation / completion
    # ------------------------------------------------------------------

    @staticmethod
    def _next_prompt(db: Session, *, session: ExpoSession, booth: ExpoBooth, lead: ExpoLead | None) -> dict[str, Any]:
        steps = ExpoSessionFlowService.steps_for_booth(booth)
        step_index = int(session.current_step or 0)
        if step_index >= len(steps):
            return ExpoSessionFlowService._complete(db, session=session, booth=booth, lead=lead)
        next_step = steps[step_index]
        return _empty_step_result(done=False, prompt=str(next_step.get("prompt") or ""))

    @staticmethod
    def _complete(
        db: Session,
        *,
        session: ExpoSession,
        lead: ExpoLead | None,
        booth: ExpoBooth | None = None,
    ) -> dict[str, Any]:
        if lead is None:
            lead = ExpoSessionFlowService._lead_for_session(db, session)
        if lead is not None:
            # Always compute + store the score; whether it's surfaced to the customer
            # is a booth-package display concern (lead_scoring_enabled), not a flow concern.
            lead.lead_score = score_lead(
                interest=lead.interest,
                timeline=lead.buying_timeline,
                consent=bool(lead.consent_acknowledged),
            )
            lead.updated_at = datetime.utcnow()
            db.add(lead)

        session.status = "completed"
        session.completed_at = datetime.utcnow()
        db.add(session)
        if booth is None:
            booth = db.get(ExpoBooth, session.booth_id)
        thank = build_thank_you_message(booth.question_config_json if booth else None)
        db.commit()
        return _empty_step_result(done=True, prompt=thank)

    @staticmethod
    def stop(db: Session, *, session: ExpoSession) -> dict[str, Any]:
        """Visitor sent a STOP-family keyword — end the session politely, same as normal completion."""
        lead = ExpoSessionFlowService._lead_for_session(db, session)
        booth = db.get(ExpoBooth, session.booth_id)
        return ExpoSessionFlowService._complete(db, session=session, booth=booth, lead=lead)
