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
    enrich_step_payload,
    parse_contact_capture,
    parse_question_config,
)
from app.services.customer_feedback.feedback_answer_service import TRANSLATION_UNAVAILABLE_EN
from app.services.expo.business_card_ocr_service import (
    ExpoBusinessCardService,
    is_placeholder_email,
    is_placeholder_phone,
)
from app.services.expo.scoring_service import score_lead

THANK_YOU_TEXT = "Thanks so much for stopping by our stand — we'll be in touch soon!"
CONTACT_CONFIRM_PROMPT = "Please check your details and continue."

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


def _empty_step_result(
    *,
    done: bool,
    prompt: str | None,
    question_key: str | None = None,
    contact_substep: str | None = None,
    channel: str = "web",
) -> dict[str, Any]:
    base = {"done": done, "awaiting_pick": False, "candidates": None, "assets": None, "prompt": prompt}
    return enrich_step_payload(
        base,
        question_key=question_key,
        contact_substep=contact_substep,
        channel=channel,
    )


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
        out = {
            "session_id": session.id,
            "done": False,
            "prompt": prompt,
            "superseded_sessions": closed,
        }
        if str(first.get("key") or "") == CONTACT_STEP_KEY:
            return enrich_step_payload(
                out,
                question_key=CONTACT_STEP_KEY,
                contact_substep="awaiting",
                channel=channel_l,
            )
        return enrich_step_payload(
            out,
            question_key=str(first.get("key") or ""),
            channel=channel_l,
        )

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
        original_text: str | None = None,
        answer_text_en: str | None = None,
        detected_language: str | None = None,
        voice_job_id: str | None = None,
        business_card_path: str | None = None,
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

        contact_sub = str(state.get("contact_substep") or "").strip().lower()
        contact_in_progress = contact_sub in {"awaiting", "company", "mobile", "confirm", "card_retry"}
        if key == CONTACT_STEP_KEY or contact_in_progress:
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
                business_card_path=business_card_path,
            )

        original = str(original_text or clean).strip() or clean
        answer_en = str(answer_text_en or clean).strip() or clean
        # Never persist the CF sentinel — Expo leads should show the original transcript
        if not answer_en or answer_en == TRANSLATION_UNAVAILABLE_EN:
            answer_en = original or clean
        if detected_language:
            session.detected_language = str(detected_language)[:16]
        response_id = str(uuid.uuid4())
        db.add(
            ExpoResponse(
                id=response_id,
                session_id=session.id,
                org_id=session.org_id,
                booth_id=booth.id,
                question_key=key,
                answer_text=answer_en,
                original_text=original,
                answer_text_en=answer_en,
                step_order=step_index + 1,
                answer_source=source,
                created_at=datetime.utcnow(),
            )
        )
        if voice_job_id:
            from app.models.expo import ExpoVoiceNoteJob

            job = db.get(ExpoVoiceNoteJob, voice_job_id)
            if job is not None:
                job.response_id = response_id
                job.updated_at = datetime.utcnow()
                db.add(job)

        if lead is not None:
            ExpoSessionFlowService._apply_answer_to_lead(lead, key, answer_en)
            if detected_language and not lead.detected_language:
                lead.detected_language = str(detected_language)[:32]
            db.add(lead)

        session.current_step = step_index + 1
        db.add(session)

        if key in {"interest", "need_price_list", "need_catalogue", "products_wanted"} and lead is not None:
            interest_text = answer_en
            if key == "need_price_list" and _looks_affirmative(answer_en):
                interest_text = "price list pricing price"
            elif key == "need_catalogue" and _looks_affirmative(answer_en):
                interest_text = "catalogue catalog brochure"
            elif key in {"need_price_list", "need_catalogue"} and not _looks_affirmative(answer_en):
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
        business_card_path: str | None = None,
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
                if fields.get("phone"):
                    # Always overwrite web-pending / web-card placeholders on lead + session
                    lead.visitor_phone = fields["phone"][:32]
                    session.visitor_phone = fields["phone"][:32]
                if business_card_path:
                    lead.business_card_path = str(business_card_path)[:2000]
                lead.updated_at = datetime.utcnow()
                db.add(lead)
                db.add(session)
            for fk in ("name", "company", "email", "phone"):
                if fields.get(fk):
                    _log(f"card_{fk}", str(fields[fk]), "ocr")

            has_identity = bool(fields.get("name") or fields.get("company") or fields.get("email") or fields.get("phone"))
            if not has_identity:
                # OCR failed / unreadable — keep contact open so visitor can retry or type
                state["contact_substep"] = "awaiting"
                state["contact_via"] = "card_retry"
                if business_card_path:
                    state["business_card_path"] = business_card_path
                ExpoSessionFlowService._save_state(session, state)
                db.add(session)
                db.commit()
                return _empty_step_result(
                    done=False,
                    prompt=(
                        "I couldn't read that card clearly. "
                        "Please try a clearer photo, or enter your name, company, mobile and email below."
                    ),
                    question_key=CONTACT_STEP_KEY,
                    contact_substep="awaiting",
                    channel=channel,
                )

            state["contact_via"] = "card"
            state["card_fields"] = {k: v for k, v in fields.items() if v}
            confirm = ExpoBusinessCardService.confirmation_message(fields)

            # Web: always show editable confirm so placeholders never stick and visitor can fix OCR
            if channel == "web":
                state["contact_substep"] = "confirm"
                ExpoSessionFlowService._save_state(session, state)
                db.add(session)
                db.commit()
                out = _empty_step_result(
                    done=False,
                    prompt=CONTACT_CONFIRM_PROMPT,
                    question_key=CONTACT_STEP_KEY,
                    contact_substep="confirm",
                    channel="web",
                )
                out["contact_via"] = "card"
                out["card_fields"] = {
                    "name": fields.get("name") or (lead.name if lead else None),
                    "company": fields.get("company") or (lead.company if lead else None),
                    "email": fields.get("email")
                    or (None if lead is None or is_placeholder_email(lead.visitor_email) else lead.visitor_email),
                    "phone": fields.get("phone")
                    or (None if is_placeholder_phone(session.visitor_phone) else session.visitor_phone),
                }
                return out

            state.pop("contact_substep", None)
            ExpoSessionFlowService._save_state(session, state)
            if steps and str(steps[0].get("key") or "") == CONTACT_STEP_KEY:
                session.current_step = 1
            db.add(session)
            db.commit()
            nxt = ExpoSessionFlowService._next_prompt(db, session=session, booth=booth, lead=lead)
            next_prompt = str(nxt.get("prompt") or "").strip()
            nxt["prompt"] = f"{confirm}\n\n{next_prompt}".strip() if next_prompt else confirm
            nxt["contact_via"] = "card"
            nxt["card_fields"] = fields
            return nxt

        if sub == "confirm":
            # Structured confirm is handled by confirm_contact(); text fallback treats answer as name
            return _empty_step_result(
                done=False,
                prompt=CONTACT_CONFIRM_PROMPT,
                question_key=CONTACT_STEP_KEY,
                contact_substep="confirm",
                channel=channel,
            )

        if sub == "awaiting" and capture == "card_only" and not is_image:
            return _empty_step_result(
                done=False,
                prompt=contact_prompt_for_mode("card_only", channel=channel),
                question_key=CONTACT_STEP_KEY,
                contact_substep="awaiting",
                channel=channel,
            )

        if sub == "awaiting":
            # Typed name
            if not answer:
                prompt = contact_prompt_for_mode(capture, channel=channel)
                return _empty_step_result(
                    done=False,
                    prompt=prompt,
                    question_key=CONTACT_STEP_KEY,
                    contact_substep="awaiting",
                    channel=channel,
                )
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
            return _empty_step_result(
                done=False,
                prompt=CONTACT_COMPANY_PROMPT,
                question_key=CONTACT_STEP_KEY,
                contact_substep="company",
                channel=channel,
            )

        if sub == "company":
            if not answer:
                return _empty_step_result(
                    done=False,
                    prompt=CONTACT_COMPANY_PROMPT,
                    question_key=CONTACT_STEP_KEY,
                    contact_substep="company",
                    channel=channel,
                )
            _log("company", answer, answer_source)
            if lead is not None:
                lead.company = answer[:255]
                lead.updated_at = datetime.utcnow()
                db.add(lead)
            # WhatsApp already has the visitor mobile; web still needs a real (non-placeholder) number
            need_mobile = channel == "web" and is_placeholder_phone(session.visitor_phone)
            if need_mobile:
                state["contact_substep"] = "mobile"
                ExpoSessionFlowService._save_state(session, state)
                db.add(session)
                db.commit()
                return _empty_step_result(
                    done=False,
                    prompt=CONTACT_MOBILE_PROMPT,
                    question_key=CONTACT_STEP_KEY,
                    contact_substep="mobile",
                    channel=channel,
                )
            state.pop("contact_substep", None)
            ExpoSessionFlowService._save_state(session, state)
            if steps and str(steps[0].get("key") or "") == CONTACT_STEP_KEY:
                session.current_step = 1
            db.add(session)
            db.commit()
            return ExpoSessionFlowService._next_prompt(db, session=session, booth=booth, lead=lead)

        if sub == "mobile":
            if not answer:
                return _empty_step_result(
                    done=False,
                    prompt=CONTACT_MOBILE_PROMPT,
                    question_key=CONTACT_STEP_KEY,
                    contact_substep="mobile",
                    channel=channel,
                )
            if answer.lower() in _YES_WORDS or answer.lower() in _NO_WORDS:
                return _empty_step_result(
                    done=False,
                    prompt="Please enter a real mobile number (with country code if possible).",
                    question_key=CONTACT_STEP_KEY,
                    contact_substep="mobile",
                    channel=channel,
                )
            _log("mobile", answer, answer_source)
            session.visitor_phone = answer[:32]
            if lead is not None:
                lead.visitor_phone = answer[:32]
                lead.updated_at = datetime.utcnow()
                db.add(lead)
            state.pop("contact_substep", None)
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
    def confirm_contact(
        db: Session,
        *,
        session: ExpoSession,
        name: str | None = None,
        company: str | None = None,
        mobile: str | None = None,
        email: str | None = None,
    ) -> dict[str, Any]:
        """Web editable confirm after card OCR (or manual fill). Rejects placeholder email/phone."""
        booth = db.get(ExpoBooth, session.booth_id)
        if booth is None:
            return _empty_step_result(done=True, prompt=THANK_YOU_TEXT)
        lead = ExpoSessionFlowService._lead_for_session(db, session)
        state = ExpoSessionFlowService._load_state(session)
        channel = str(session.channel or "web").lower()

        clean_name = str(name or "").strip()
        clean_company = str(company or "").strip()
        clean_mobile = str(mobile or "").strip()
        clean_email = str(email or "").strip().lower()

        if not clean_name:
            out = _empty_step_result(
                done=False,
                prompt="Please enter your full name to continue.",
                question_key=CONTACT_STEP_KEY,
                contact_substep="confirm",
                channel=channel,
            )
            out["card_fields"] = {
                "name": clean_name or None,
                "company": clean_company or None,
                "email": clean_email or None,
                "phone": clean_mobile or None,
            }
            return out
        if not clean_mobile or is_placeholder_phone(clean_mobile) or clean_mobile.lower() in _YES_WORDS | _NO_WORDS:
            out = _empty_step_result(
                done=False,
                prompt="Please enter a real mobile number.",
                question_key=CONTACT_STEP_KEY,
                contact_substep="confirm",
                channel=channel,
            )
            out["card_fields"] = {
                "name": clean_name,
                "company": clean_company or None,
                "email": clean_email or None,
                "phone": None,
            }
            return out
        if not clean_email or is_placeholder_email(clean_email) or "@expo.local" in clean_email:
            out = _empty_step_result(
                done=False,
                prompt="Please enter a real email address.",
                question_key=CONTACT_STEP_KEY,
                contact_substep="confirm",
                channel=channel,
            )
            out["card_fields"] = {
                "name": clean_name,
                "company": clean_company or None,
                "email": None,
                "phone": clean_mobile,
            }
            return out

        now = datetime.utcnow()
        session.visitor_phone = clean_mobile[:32]
        session.visitor_email = clean_email[:255]
        if lead is not None:
            lead.name = clean_name[:255]
            lead.company = (clean_company[:255] if clean_company else lead.company)
            lead.visitor_phone = clean_mobile[:32]
            lead.visitor_email = clean_email[:255]
            lead.updated_at = now
            db.add(lead)
        for key, val, src in (
            ("name", clean_name, "confirm"),
            ("company", clean_company or "", "confirm"),
            ("mobile", clean_mobile, "confirm"),
            ("email", clean_email, "confirm"),
        ):
            if not val:
                continue
            db.add(
                ExpoResponse(
                    id=str(uuid.uuid4()),
                    session_id=session.id,
                    org_id=session.org_id,
                    booth_id=booth.id,
                    question_key=key,
                    answer_text=val[:4000],
                    original_text=val[:4000],
                    answer_text_en=val[:4000],
                    step_order=1,
                    answer_source=src,
                    created_at=now,
                )
            )

        state["contact_via"] = state.get("contact_via") or "confirm"
        state.pop("contact_substep", None)
        state["card_fields"] = {
            "name": clean_name,
            "company": clean_company or None,
            "email": clean_email,
            "phone": clean_mobile,
        }
        ExpoSessionFlowService._save_state(session, state)
        steps = ExpoSessionFlowService.steps_for_booth(booth)
        if steps and str(steps[0].get("key") or "") == CONTACT_STEP_KEY:
            session.current_step = 1
        db.add(session)
        db.commit()
        return ExpoSessionFlowService._next_prompt(db, session=session, booth=booth, lead=lead)

    @staticmethod
    def _apply_answer_to_lead(lead: ExpoLead, key: str, text: str) -> None:
        clean = text.strip()
        if not clean or clean == TRANSLATION_UNAVAILABLE_EN:
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
        key = str(next_step.get("key") or "")
        channel = str(session.channel or "whatsapp").lower()
        prompt = str(next_step.get("prompt") or "")
        if channel == "web" and next_step.get("prompt_web"):
            prompt = str(next_step.get("prompt_web") or prompt)
        return _empty_step_result(
            done=False,
            prompt=prompt,
            question_key=key,
            channel=channel,
        )

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
