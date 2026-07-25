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
from app.services.expo.question_bank import build_thank_you_message, parse_question_config
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
            return {"session_id": session.id, "done": True, "prompt": build_thank_you_message(booth.question_config_json)}

        db.commit()
        return {"session_id": session.id, "done": False, "prompt": str(steps[0].get("prompt") or "")}

    # ------------------------------------------------------------------
    # Advancing an existing session
    # ------------------------------------------------------------------

    @staticmethod
    def advance(db: Session, *, session: ExpoSession, answer: str, answer_source: str = "text") -> dict[str, Any]:
        booth = db.get(ExpoBooth, session.booth_id)
        if booth is None:
            session.status = "failed"
            db.add(session)
            db.commit()
            return _empty_step_result(done=True, prompt=THANK_YOU_TEXT)

        lead = ExpoSessionFlowService._lead_for_session(db, session)
        state = ExpoSessionFlowService._load_state(session)
        clean = str(answer or "").strip()

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
                answer_source=answer_source or "text",
                created_at=datetime.utcnow(),
            )
        )

        if lead is not None:
            ExpoSessionFlowService._apply_answer_to_lead(lead, key, clean)
            db.add(lead)

        session.current_step = step_index + 1
        db.add(session)

        if key == "interest" and lead is not None:
            offer_mode, candidates = ExpoSessionFlowService._offer_after_interest(db, booth=booth, interest_text=clean)
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
