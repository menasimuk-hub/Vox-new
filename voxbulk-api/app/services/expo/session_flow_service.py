"""Expo channel-agnostic conversation engine — shared by the WhatsApp adapter and the public web fallback.

Returns plain data (next prompt text, pending asset candidates, delivered assets) so each channel
adapter can format it however it needs to (WhatsApp text messages vs. JSON for the web widget).
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.expo import ExpoBooth, ExpoLead, ExpoResponse, ExpoSession
from app.services.expo.intent_router import (
    PENDING_CORRECTION_KEY,
    apply_lead_field,
    detect_intent,
    prompt_for_correction,
)
from app.services.expo.offer_delivery_service import (
    load_booth_assets,
    mark_lead_offer_sent,
    resolve_pick_reply,
)
from app.services.expo.question_bank import (
    CONTACT_COMPANY_PROMPT,
    CONTACT_MOBILE_PROMPT,
    CONTACT_STEP_KEY,
    DEFAULT_COMPANY_CARD,
    OPEN_FEEDBACK_KEY,
    WEB_CHOICE_OPTIONS,
    build_company_card_text,
    build_thank_you_message,
    contact_prompt_for_mode,
    enrich_step_payload,
    get_template_prompt,
    parse_contact_capture,
    parse_question_config,
    parse_representative_contacts,
    with_topic_emoji,
)
from app.services.customer_feedback.feedback_answer_service import TRANSLATION_UNAVAILABLE_EN
from app.services.expo.business_card_ocr_service import (
    ExpoBusinessCardService,
    is_placeholder_email,
    is_placeholder_phone,
)
from app.services.expo.scoring_service import score_lead

THANK_YOU_TEXT = "Thanks so much for stopping by our stand — we'll be in touch soon!"
CONTACT_CONFIRM_PROMPT = "✅ Please check your details and continue."

_YES_WORDS = frozenset({"yes", "y", "yeah", "yep", "sure", "ok", "okay", "please", "affirmative"})
_NO_WORDS = frozenset({"no", "n", "nope", "nah", "negative", "not interested", "no thanks"})

_EMOJI_DIGITS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]


def _emoji_digit(n: int) -> str:
    if 1 <= n <= len(_EMOJI_DIGITS):
        return _EMOJI_DIGITS[n - 1]
    return f"{n}."


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


_PURPOSE_OPTION_LABEL = {
    "catalogue": "Catalogue",
    "price_list": "Price list",
    "product": "Product",
    "product_sheet": "Product sheet",
    "other": "File",
}

_PURPOSE_SORT = {
    "catalogue": 10,
    "product_sheet": 20,
    "price_list": 30,
    "product": 40,
    "other": 50,
}

# WhatsApp keycap digits users often tap/copy from the prompt.
_KEYCAP_DIGIT_MAP = {
    "1️⃣": "1",
    "2️⃣": "2",
    "3️⃣": "3",
    "4️⃣": "4",
    "5️⃣": "5",
    "6️⃣": "6",
    "7️⃣": "7",
    "8️⃣": "8",
    "9️⃣": "9",
    "🔟": "10",
}


def _parse_pick_numbers(text: str) -> list[int]:
    """Extract 1-based option numbers from replies like 1, 1. 1️⃣, 1) or 1,2."""
    raw = str(text or "").strip()
    if not raw:
        return []
    normalized = raw
    for emoji, digit in _KEYCAP_DIGIT_MAP.items():
        normalized = normalized.replace(emoji, digit)
    # Strip variation selectors / RTL marks that WhatsApp sometimes inserts.
    normalized = re.sub(r"[\u200e\u200f\ufe0f\u20e3]", "", normalized)
    found: list[int] = []
    seen: set[int] = set()
    for match in re.finditer(r"\d+", normalized):
        try:
            n = int(match.group(0))
        except ValueError:
            continue
        if n < 1 or n in seen:
            continue
        seen.add(n)
        found.append(n)
    return found


def _classify_booth_assets(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalise purpose, dedupe by id, and sort category → product → purpose."""
    from app.services.expo.offer_delivery_service import normalize_asset_purpose

    normalised: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for a in assets:
        aid = str(a.get("id") or "").strip()
        if aid and aid in seen_ids:
            continue
        if aid:
            seen_ids.add(aid)
        purpose = normalize_asset_purpose(a.get("purpose"))
        blob = " ".join(
            [
                str(a.get("title") or ""),
                str(a.get("short_description") or ""),
                str(a.get("asset_key") or ""),
                str(a.get("match_keywords") or ""),
            ]
        ).lower()
        if purpose == "product":
            if any(w in blob for w in ("price", "pricing", "pricelist", "price list", "rates", "tariff")):
                purpose = "price_list"
            elif any(w in blob for w in ("catalogue", "catalog", "brochure", "lookbook")):
                purpose = "catalogue"
        normalised.append({**a, "purpose": purpose})

    normalised.sort(
        key=lambda row: (
            str(row.get("category_name") or "zzz").lower(),
            str(row.get("product_name") or "").lower(),
            int(_PURPOSE_SORT.get(str(row.get("purpose") or "other"), 99)),
            int(row.get("sort_order") or 100),
            str(row.get("title") or "").lower(),
        )
    )

    # Drop duplicate uploads of the same file (same path/url/title) so the menu
    # doesn't list e.g. Catalogue + Product sheet for one PDF.
    deduped: list[dict[str, Any]] = []
    seen_files: set[str] = set()
    for row in normalised:
        fingerprint = (
            str(row.get("storage_path") or "").strip().lower()
            or str(row.get("external_url") or "").strip().lower()
            or str(row.get("title") or "").strip().lower()
        )
        if fingerprint and fingerprint in seen_files:
            continue
        if fingerprint:
            seen_files.add(fingerprint)
        deduped.append(row)
    return deduped


def _consent_asset_option_label(asset: dict[str, Any]) -> str:
    purpose = str(asset.get("purpose") or "product")
    kind = _PURPOSE_OPTION_LABEL.get(purpose, "File")
    product = str(asset.get("product_name") or "").strip()
    title = str(asset.get("title") or "Download").strip() or "Download"
    if product and product.lower() not in title.lower():
        return f"{product} — {kind}"
    if title.lower().startswith(kind.lower()):
        return title
    return f"{kind}: {title}"


def _format_consent_menu_lines(assets: list[dict[str, Any]], *, offer: str) -> list[str]:
    """Category-grouped numbered menu for WhatsApp / web consent."""
    lines = [with_topic_emoji("consent_info", f"Would you like our {offer}?")]
    if any(str(a.get("category_name") or "").strip() for a in assets):
        lines.append("Organised by category — reply with the number(s), e.g. 1 or 1,2")
    else:
        lines.append("Reply with the number(s), e.g. 1 or 1,2")

    current_cat: str | None = None
    for idx, a in enumerate(assets, start=1):
        cat = str(a.get("category_name") or "").strip() or "Files"
        if cat != current_cat:
            current_cat = cat
            lines.append("")
            lines.append(f"📁 {cat}")
        lines.append(f"{_emoji_digit(idx)} {_consent_asset_option_label(a)}")

    lines.append("")
    lines.append(f"{_emoji_digit(len(assets) + 1)} No thanks")
    return lines


def _format_product_list_prompt(assets: list[dict[str, Any]]) -> str:
    """Numbered list of every booth asset for the "what do you have?" hybrid intent."""
    organised = _classify_booth_assets(assets)
    if not organised:
        return "We don't have any files loaded yet — please ask our stand team."
    lines = _format_consent_menu_lines(organised, offer="files")
    lines[0] = "📦 Here's what we have available:"
    return "\n".join(lines)


class ExpoSessionFlowService:
    @staticmethod
    def steps_for_booth(booth: ExpoBooth) -> list[dict[str, Any]]:
        return parse_question_config(booth.question_config_json)

    @staticmethod
    def _attach_progress(result: dict[str, Any], *, session: ExpoSession, booth: ExpoBooth | None) -> dict[str, Any]:
        out = dict(result or {})
        steps = ExpoSessionFlowService.steps_for_booth(booth) if booth is not None else []
        total = max(1, len(steps))
        idx = int(session.current_step or 0)
        if out.get("awaiting_pick"):
            # Product pick is an interstitial — keep the same slide number as the current step.
            display = min(max(idx, 1), total)
        elif out.get("done"):
            display = total
        else:
            display = min(idx + 1, total) if total else 1
        out["step_index"] = display
        out["step_total"] = total
        return out

    @staticmethod
    def _lead_summary(db: Session, *, session: ExpoSession, lead: ExpoLead | None) -> dict[str, Any]:
        if lead is None:
            lead = ExpoSessionFlowService._lead_for_session(db, session)
        answers = (
            db.execute(
                select(ExpoResponse)
                .where(ExpoResponse.session_id == session.id)
                .order_by(ExpoResponse.step_order.asc(), ExpoResponse.created_at.asc())
            )
            .scalars()
            .all()
        )
        return {
            "name": (lead.name if lead else None) or None,
            "company": (lead.company if lead else None) or None,
            "email": (lead.visitor_email if lead else None) or session.visitor_email,
            "mobile": (lead.visitor_phone if lead else None) or session.visitor_phone,
            "interest": (lead.interest if lead else None) or None,
            "timeline": (lead.buying_timeline if lead else None) or None,
            "answers": [
                {
                    "key": r.question_key,
                    "answer": r.answer_text_en or r.answer_text,
                }
                for r in answers
                if r.question_key and str(r.answer_text or "").strip()
            ],
        }

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
    def find_recent_completed_session(db: Session, *, visitor_phone: str, hours: int = 48) -> ExpoSession | None:
        """Most recent completed Expo session for this phone — for post-questionnaire handoff."""
        phone = str(visitor_phone or "").strip()
        if not phone:
            return None
        cutoff = datetime.utcnow() - timedelta(hours=max(1, int(hours or 48)))
        return db.execute(
            select(ExpoSession)
            .where(
                ExpoSession.visitor_phone == phone,
                ExpoSession.status == "completed",
                ExpoSession.completed_at >= cutoff,
            )
            .order_by(ExpoSession.completed_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    @staticmethod
    def record_post_complete_question(
        db: Session,
        *,
        session: ExpoSession,
        lead: ExpoLead | None,
        text: str,
    ) -> None:
        """Log a message sent after the questionnaire completed — doesn't reopen the flow."""
        clean = str(text or "").strip()
        if not clean:
            return
        db.add(
            ExpoResponse(
                id=str(uuid.uuid4()),
                session_id=session.id,
                org_id=session.org_id,
                booth_id=session.booth_id,
                question_key="visitor_question",
                answer_text=clean[:4000],
                original_text=clean[:4000],
                answer_text_en=clean[:4000],
                step_order=0,
                answer_source="text",
                created_at=datetime.utcnow(),
            )
        )
        if lead is not None:
            lead.follow_up_status = "visitor_question"
            lead.updated_at = datetime.utcnow()
            db.add(lead)
        db.commit()

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
        from app.services.expo.booth_service import (
            booth_access_block_reason,
            booth_requires_preview_quota,
        )

        blocked = booth_access_block_reason(booth)
        if blocked:
            raise ValueError(blocked)

        # One phone → one active Expo booth chat. New QR always wins (stops catalog mix-ups).
        closed = ExpoSessionFlowService.supersede_active_sessions(
            db,
            visitor_phone=visitor_phone,
            reason="new_booth_scan",
        )
        booth.scan_count = int(booth.scan_count or 0) + 1
        if booth_requires_preview_quota(booth):
            booth.preview_tests_used = int(getattr(booth, "preview_tests_used", 0) or 0) + 1
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
                "prompt": build_thank_you_message(
                    booth.question_config_json,
                    company_name=booth.company_display_name or booth.name,
                ),
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
        channel = str(session.channel or "whatsapp").lower()

        # --- Hybrid intents: corrections + product requests, resolved before any answer is
        # recorded against the current step. Corrections/product asks are allowed mid-contact-
        # capture too (a visitor spotting a typo shouldn't have to finish the questionnaire first).
        pending_field = str(state.get(PENDING_CORRECTION_KEY) or "").strip()
        if pending_field:
            if not clean:
                return _empty_step_result(
                    done=False,
                    prompt=prompt_for_correction(pending_field),
                    question_key=key or CONTACT_STEP_KEY,
                    contact_substep=contact_sub or None,
                    channel=channel,
                )
            confirm_msg = apply_lead_field(lead, pending_field, clean) if lead is not None else "Details updated."
            if lead is not None:
                lead.updated_at = datetime.utcnow()
                db.add(lead)
            state.pop(PENDING_CORRECTION_KEY, None)
            ExpoSessionFlowService._save_state(session, state)
            db.add(session)
            db.commit()
            return ExpoSessionFlowService._stay_on_current(
                db,
                session=session,
                booth=booth,
                lead=lead,
                steps=steps,
                step_index=step_index,
                state=state,
                lead_prompt=f"✅ {confirm_msg}",
            )

        # Bare contact answers (name / company / mobile / OCR photo) must never be swallowed by
        # intent detection — only an unambiguous "change my ..." request interrupts contact capture.
        allow_full_intents = not (key == CONTACT_STEP_KEY or contact_in_progress)
        intent = detect_intent(clean)
        if intent and not allow_full_intents and not str(intent.get("intent") or "").startswith("change_"):
            intent = None

        if intent:
            kind = str(intent.get("intent") or "")
            if kind.startswith("change_") and lead is not None:
                field = str(intent.get("field") or "").strip()
                value = str(intent.get("value") or "").strip()
                if field and value:
                    confirm_msg = apply_lead_field(lead, field, value)
                    lead.updated_at = datetime.utcnow()
                    db.add(lead)
                    db.commit()
                    return ExpoSessionFlowService._stay_on_current(
                        db,
                        session=session,
                        booth=booth,
                        lead=lead,
                        steps=steps,
                        step_index=step_index,
                        state=state,
                        lead_prompt=f"✅ {confirm_msg}",
                    )
                if field:
                    state[PENDING_CORRECTION_KEY] = field
                    ExpoSessionFlowService._save_state(session, state)
                    db.add(session)
                    db.commit()
                    return _empty_step_result(
                        done=False,
                        prompt=prompt_for_correction(field),
                        question_key=key or CONTACT_STEP_KEY,
                        contact_substep=contact_sub or None,
                        channel=channel,
                    )
            elif kind == "list_products":
                assets = load_booth_assets(db, booth.id)
                return ExpoSessionFlowService._stay_on_current(
                    db,
                    session=session,
                    booth=booth,
                    lead=lead,
                    steps=steps,
                    step_index=step_index,
                    state=state,
                    lead_prompt=_format_product_list_prompt(assets),
                )
            elif kind == "send_all":
                if key == "consent_info":
                    # Normalise to "all" and let the existing consent_info branch below deliver
                    # the assets and advance the step exactly like a normal consent answer.
                    clean = "all"
                elif lead is not None:
                    assets = load_booth_assets(db, booth.id)
                    if assets:
                        delivered, _clarify = ExpoSessionFlowService._deliver_consent_assets(
                            db, booth=booth, lead=lead, answer="all"
                        )
                        db.commit()
                        result = ExpoSessionFlowService._stay_on_current(
                            db,
                            session=session,
                            booth=booth,
                            lead=lead,
                            steps=steps,
                            step_index=step_index,
                            state=state,
                            lead_prompt="✅ Sending you everything we have.",
                        )
                        if delivered:
                            result["assets"] = delivered
                            result["deliver_now"] = True
                        return result
            elif kind == "skip":
                is_open_step = key == OPEN_FEEDBACK_KEY or (key not in WEB_CHOICE_OPTIONS and key != "consent_info")
                if is_open_step:
                    # Legitimate skip on an open question — record the literal reply and advance
                    # exactly like any other answer (handled by the normal flow below).
                    pass
                # Choice/consent steps: don't treat "skip" as a command either — fall through so
                # the raw reply is stored and scored like a normal (likely negative) answer.
            # Any other/incomplete intent falls through to the normal answer flow below.

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
        # WhatsApp choice questions are relayed as numbered options — a bare digit reply
        # maps back to the matching option's value instead of being stored as "2".
        # consent_info uses a *dynamic* asset menu (not WEB_CHOICE_OPTIONS Yes/No) — never remap it.
        if key != "consent_info" and key in WEB_CHOICE_OPTIONS and answer_en.strip().isdigit():
            opts = WEB_CHOICE_OPTIONS[key]
            idx = int(answer_en.strip())
            if 1 <= idx <= len(opts):
                mapped_val = str(opts[idx - 1].get("value") or "").strip()
                if mapped_val:
                    original = mapped_val
                    answer_en = mapped_val
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

        # Catalogue / price-list download step — deliver selected assets then continue.
        if key == "consent_info" and lead is not None:
            # Prefer the visitor's raw digit reply (never the Yes/No bank remap).
            consent_answer = clean if _parse_pick_numbers(clean) else answer_en
            if str(answer_en or "").strip().lower() in {"yes", "y"} and _parse_pick_numbers(clean):
                consent_answer = clean
            state = ExpoSessionFlowService._load_state(session)
            menu_ids = state.get("consent_menu_ids")
            menu_assets = None
            if isinstance(menu_ids, list) and menu_ids:
                by_id = {str(a.get("id") or ""): a for a in _classify_booth_assets(load_booth_assets(db, booth.id))}
                menu_assets = [by_id[str(i)] for i in menu_ids if str(i) in by_id]
                if not menu_assets:
                    menu_assets = None
            delivered, clarify = ExpoSessionFlowService._deliver_consent_assets(
                db, booth=booth, lead=lead, answer=consent_answer, menu_assets=menu_assets
            )
            if clarify:
                # Stay on consent and re-show the full organised menu + clarify line.
                session.current_step = step_index
                db.add(session)
            else:
                state.pop("consent_menu_ids", None)
                ExpoSessionFlowService._save_state(session, state)
                db.add(session)
            db.commit()
            if clarify:
                consent_ui = ExpoSessionFlowService._consent_prompt_with_assets(
                    db,
                    booth=booth,
                    channel=str(session.channel or "whatsapp").lower(),
                    base_prompt="",
                    lead=lead,
                    session=session,
                )
                if consent_ui is not None:
                    full = str(consent_ui.get("prompt") or "").strip()
                    consent_ui["prompt"] = f"{clarify}\n\n{full}" if full else clarify
                    return consent_ui
            result = ExpoSessionFlowService._next_prompt(db, session=session, booth=booth, lead=lead)
            if delivered:
                result["assets"] = delivered
                result["deliver_now"] = True
                if result.get("done"):
                    result["thank_you_followup"] = result.get("prompt")
            return result

        # Interest / product answers only enrich the lead — do NOT send files before consent.
        # Catalogue / price-list delivery happens exclusively via consent_info.
        if key in {"need_price_list", "need_catalogue"} and lead is not None and not _looks_affirmative(answer_en):
            db.commit()
            return ExpoSessionFlowService._next_prompt(db, session=session, booth=booth, lead=lead)

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

        # Photo of business card → OCR + skip typed contact fields (also accepted mid-flow
        # while we're still collecting company/mobile, not only on the first prompt).
        if sub in {"awaiting", "company", "mobile"} and is_image and capture != "manual_only":
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

            # WhatsApp: the visitor's mobile is already known from the sender number, so the
            # only common gap after a business-card scan is a missing company name.
            company_present = bool((lead.company if lead else None) or fields.get("company"))
            if not company_present:
                state["contact_substep"] = "company"
                ExpoSessionFlowService._save_state(session, state)
                db.add(session)
                db.commit()
                out = _empty_step_result(
                    done=False,
                    prompt=f"{confirm}\n\n{CONTACT_COMPANY_PROMPT}".strip(),
                    question_key=CONTACT_STEP_KEY,
                    contact_substep="company",
                    channel=channel,
                )
                out["contact_via"] = "card"
                out["card_fields"] = fields
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
        elif key == "follow_up":
            lead.follow_up_status = clean[:32] if len(clean) <= 32 else "requested"
        elif key in ("consent_info", "consent"):
            # Affirmative / any asset pick counts as interested in materials.
            lower = clean.lower()
            lead.consent_acknowledged = (
                _looks_affirmative(clean)
                or ("no thanks" not in lower and lower not in _NO_WORDS and lower != "no")
            )
        lead.updated_at = datetime.utcnow()

    @staticmethod
    def _deliver_consent_assets(
        db: Session,
        *,
        booth: ExpoBooth,
        lead: ExpoLead,
        answer: str,
        menu_assets: list[dict[str, Any]] | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Map a catalogue/price-list reply to downloadable assets.

        Returns ``(delivered, clarify)``. Accepts numbered picks ("1", "1️⃣", "1,2", "both") and
        purpose words ("catalogue", "price list") in addition to titles/ids. When the visitor
        sends a bare "Yes" and the booth offers more than one asset, nothing is delivered —
        ``clarify`` carries a short re-prompt so the caller can ask which one(s) they want
        instead of sending every file.
        """
        raw = str(answer or "").strip()
        lower = raw.lower()
        # Never treat a Yes/No remap as a download pick — digits must select menu rows.
        if lower in {"yes", "y", "yeah", "yep", "sure", "ok", "okay", "please", "affirmative"}:
            # Fall through to affirmative clarify below after loading assets.
            pass

        assets = menu_assets if menu_assets is not None else _classify_booth_assets(load_booth_assets(db, booth.id))
        if not assets:
            return [], None

        # "No thanks" / decline (also the last numbered option).
        picks = _parse_pick_numbers(raw)
        no_index = len(assets) + 1
        if lower in _NO_WORDS or lower in {"no thanks", "no, thanks"} or picks == [no_index]:
            return [], None

        tokens = [t.strip() for t in re.split(r"[,;/&]+|\band\b", lower) if t.strip()]
        meaningful = [
            t for t in tokens if t not in _NO_WORDS and t not in {"no thanks", "no, thanks"}
        ]

        chosen: list[dict[str, Any]] = []
        seen_idx: set[int] = set()

        def _add(i: int) -> None:
            if 0 <= i < len(assets) and i not in seen_idx:
                seen_idx.add(i)
                chosen.append(assets[i])

        if lower in {"both", "all", "everything", "all of them"} or (
            picks and set(picks) == set(range(1, len(assets) + 1))
        ):
            for i in range(len(assets)):
                _add(i)
        else:
            for n in picks:
                if n == no_index:
                    continue
                _add(n - 1)

            if not chosen and meaningful:
                for tok in meaningful:
                    if tok in {"catalogue", "catalog", "brochure"}:
                        for i, a in enumerate(assets):
                            if a.get("purpose") == "catalogue":
                                _add(i)
                    elif tok in {"price", "prices", "pricing", "price list", "pricelist"}:
                        for i, a in enumerate(assets):
                            if a.get("purpose") == "price_list":
                                _add(i)
                    elif tok in {"sheet", "product sheet", "datasheet"}:
                        for i, a in enumerate(assets):
                            if a.get("purpose") == "product_sheet":
                                _add(i)

            if not chosen and meaningful:
                for i, a in enumerate(assets):
                    aid = str(a.get("id") or "")
                    title = str(a.get("title") or "").strip().lower()
                    product = str(a.get("product_name") or "").strip().lower()
                    key = str(a.get("asset_key") or "").strip().lower()
                    for tok in meaningful:
                        if tok in {aid.lower(), title, key, product} or (title and title in tok) or (tok and tok in title):
                            _add(i)
                            break

            if not chosen and _looks_affirmative(lower) and not picks:
                if len(assets) > 1:
                    if len(assets) == 2:
                        clarify = "Please reply 1, 2, or both — which would you like?"
                    else:
                        nums = ", ".join(str(i) for i in range(1, len(assets) + 1))
                        clarify = f"Please reply with a number ({nums}) — which would you like?"
                    return [], clarify
                _add(0)

        if not chosen:
            # Digit reply that was out of range — ask again instead of skipping the step.
            if picks:
                nums = ", ".join(str(i) for i in range(1, len(assets) + 1))
                return [], f"Please reply with a number ({nums}) — which would you like?"
            return [], None

        delivered: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        from app.services.expo.offer_delivery_service import asset_public_url_for_lead

        for asset in chosen:
            aid = str(asset.get("id") or "")
            if not aid or aid in seen_ids:
                continue
            seen_ids.add(aid)
            mark_lead_offer_sent(db, lead, asset)
            row = dict(asset)
            row["url"] = asset_public_url_for_lead(asset, booth.qr_token, lead.id)
            delivered.append(row)
        if delivered:
            lead.consent_acknowledged = True
            db.add(lead)
            try:
                from app.services.expo.expo_email_service import ExpoEmailService

                ExpoEmailService.send_visitor_catalogue(db, booth=booth, lead=lead, assets=delivered)
            except Exception:
                logger = __import__("logging").getLogger(__name__)
                logger.exception("expo_visitor_catalogue_email_failed lead=%s", lead.id)
        return delivered, None

    @staticmethod
    def _consent_prompt_with_assets(
        db: Session,
        *,
        booth: ExpoBooth,
        channel: str,
        base_prompt: str,
        lead: ExpoLead | None = None,
        session: ExpoSession | None = None,
    ) -> dict[str, Any] | None:
        """Build the catalogue/price-list ask, or None to skip when the booth has no assets.

        Asset metadata always goes in ``asset_options`` — never in the deliverable ``assets``
        list here — so the WhatsApp relay (which only ever sends files listed in ``assets``)
        can't push documents before the visitor has actually said what they want.
        """
        assets = _classify_booth_assets(load_booth_assets(db, booth.id))
        if not assets:
            return None
        channel_l = str(channel or "").lower()

        # Persist menu order so "1" always maps to the same file the visitor just saw.
        if session is not None:
            state = ExpoSessionFlowService._load_state(session)
            state["consent_menu_ids"] = [str(a.get("id") or "") for a in assets if a.get("id")]
            ExpoSessionFlowService._save_state(session, state)
            db.add(session)

        options = [
            {
                "value": str(idx),
                "label": _consent_asset_option_label(a),
                "category": str(a.get("category_name") or "") or None,
                "purpose": a.get("purpose"),
            }
            for idx, a in enumerate(assets, start=1)
            if a.get("id") or a.get("title")
        ]
        options.append({"value": str(len(assets) + 1), "label": "No thanks"})

        has_catalogue = any(str(a.get("purpose") or "") == "catalogue" for a in assets)
        has_price = any(str(a.get("purpose") or "") == "price_list" for a in assets)
        if has_catalogue and has_price:
            offer = "catalogue and price list"
        elif has_price:
            offer = "price list"
        elif has_catalogue:
            offer = "catalogue"
        else:
            offer = "files"

        asset_options = [
            {
                "id": a.get("id"),
                "title": a.get("title"),
                "short_description": a.get("short_description"),
                "kind": a.get("kind"),
                "purpose": a.get("purpose"),
                "product_name": a.get("product_name"),
                "category_name": a.get("category_name"),
                "label": _consent_asset_option_label(a),
            }
            for a in assets
        ]

        result: dict[str, Any] = {
            "done": False,
            "awaiting_pick": False,
            "candidates": None,
            "assets": [],
            "asset_options": asset_options,
            "question_key": "consent_info",
            "input": "multi_choice",
            "options": options,
            "allow_voice": False,
        }

        if channel_l == "web":
            # Grouped labels for the web multi-select cards.
            named_parts: list[str] = []
            for a in assets[:8]:
                cat = str(a.get("category_name") or "").strip()
                label = _consent_asset_option_label(a)
                named_parts.append(f"{cat}: {label}" if cat else label)
            named = ", ".join(named_parts)
            result["prompt"] = with_topic_emoji(
                "consent_info",
                f"Would you like our {offer}? We have: {named}. Select all you'd like to download.",
            )
            if lead is not None:
                from app.services.expo.offer_delivery_service import asset_public_url_for_lead

                # Preview URLs on options only — deliverable ``assets`` stay empty until the visitor picks.
                result["asset_options"] = [
                    {
                        **opt,
                        "url": asset_public_url_for_lead(a, booth.qr_token, lead.id),
                    }
                    for opt, a in zip(asset_options, assets)
                ]
            return result

        # WhatsApp — category-grouped numbered emoji prompt.
        result["prompt"] = "\n".join(_format_consent_menu_lines(assets, offer=offer))
        return result

    @staticmethod
    def _delivered_assets_payload(
        db: Session,
        *,
        booth: ExpoBooth,
        lead: ExpoLead | None,
    ) -> list[dict[str, Any]]:
        """Rebuild delivered asset dicts (with tracked URLs) for web thank-you."""
        if lead is None:
            return []
        from app.services.expo.offer_delivery_service import (
            asset_public_url_for_lead,
            lead_assets_sent_list,
            load_booth_assets,
        )

        sent = lead_assets_sent_list(lead)
        if not sent:
            return []
        by_id = {str(a.get("id") or ""): a for a in load_booth_assets(db, booth.id)}
        by_key = {str(a.get("asset_key") or ""): a for a in by_id.values()}
        out: list[dict[str, Any]] = []
        for item in sent:
            if isinstance(item, str):
                asset = by_key.get(item) or by_id.get(item)
            elif isinstance(item, dict):
                asset = by_id.get(str(item.get("asset_id") or "")) or by_key.get(str(item.get("asset_key") or ""))
            else:
                asset = None
            if not asset:
                continue
            row = dict(asset)
            row["url"] = asset_public_url_for_lead(asset, booth.qr_token, lead.id)
            out.append(row)
        return out

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
        result["deliver_now"] = True
        return result

    # ------------------------------------------------------------------
    # Hybrid intent helpers — re-render the current step without advancing
    # ------------------------------------------------------------------

    @staticmethod
    def _current_step_result(
        db: Session,
        *,
        session: ExpoSession,
        booth: ExpoBooth,
        lead: ExpoLead | None,
        steps: list[dict[str, Any]],
        step_index: int,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        """Re-render the prompt for whatever step the visitor is currently sitting on, without
        consuming an answer or advancing — used after a correction / product-list / send-all
        hybrid intent so the questionnaire doesn't skip a question."""
        channel = str(session.channel or "whatsapp").lower()
        contact_sub = str(state.get("contact_substep") or "").strip().lower()
        at_contact = bool(steps) and step_index == 0 and str(steps[0].get("key") or "") == CONTACT_STEP_KEY
        if at_contact and contact_sub in {"", "awaiting", "company", "mobile", "confirm", "card_retry"}:
            sub = contact_sub or "awaiting"
            capture = parse_contact_capture(booth.question_config_json)
            prompt_map = {
                "awaiting": contact_prompt_for_mode(capture, channel=channel),
                "card_retry": contact_prompt_for_mode(capture, channel=channel),
                "company": CONTACT_COMPANY_PROMPT,
                "mobile": CONTACT_MOBILE_PROMPT,
                "confirm": CONTACT_CONFIRM_PROMPT,
            }
            return _empty_step_result(
                done=False,
                prompt=prompt_map.get(sub, prompt_map["awaiting"]),
                question_key=CONTACT_STEP_KEY,
                contact_substep=sub,
                channel=channel,
            )

        if step_index >= len(steps):
            return ExpoSessionFlowService._complete(db, session=session, booth=booth, lead=lead)

        step = steps[step_index]
        key = str(step.get("key") or "")
        if key == "consent_info":
            consent_ui = ExpoSessionFlowService._consent_prompt_with_assets(
                db,
                booth=booth,
                channel=channel,
                base_prompt=str(step.get("prompt_web") or step.get("prompt") or ""),
                lead=lead,
                session=session,
            )
            if consent_ui is not None:
                return consent_ui

        prompt = str(step.get("prompt") or "")
        if channel == "web" and step.get("prompt_web"):
            prompt = str(step.get("prompt_web") or prompt)
        prompt = with_topic_emoji(key, prompt)
        if channel == "whatsapp" and key in WEB_CHOICE_OPTIONS and key != "consent_info":
            opts = WEB_CHOICE_OPTIONS[key]
            lines = [prompt, ""]
            for idx, opt in enumerate(opts, start=1):
                lines.append(f"{_emoji_digit(idx)} {opt.get('label') or opt.get('value')}")
            lines.append("")
            lines.append("Reply with the number, e.g. 1")
            prompt = "\n".join(line for line in lines if line is not None).strip()
        return _empty_step_result(done=False, prompt=prompt, question_key=key, channel=channel)

    @staticmethod
    def _stay_on_current(
        db: Session,
        *,
        session: ExpoSession,
        booth: ExpoBooth,
        lead: ExpoLead | None,
        steps: list[dict[str, Any]],
        step_index: int,
        state: dict[str, Any],
        lead_prompt: str,
    ) -> dict[str, Any]:
        """Confirmation/info message followed by a re-ask of the current step's prompt."""
        current = ExpoSessionFlowService._current_step_result(
            db,
            session=session,
            booth=booth,
            lead=lead,
            steps=steps,
            step_index=step_index,
            state=state,
        )
        base_prompt = str(current.get("prompt") or "").strip()
        current["prompt"] = f"{lead_prompt}\n\n{base_prompt}".strip() if base_prompt else lead_prompt
        return current

    # ------------------------------------------------------------------
    # Question flow continuation / completion
    # ------------------------------------------------------------------

    @staticmethod
    def _next_prompt(db: Session, *, session: ExpoSession, booth: ExpoBooth, lead: ExpoLead | None) -> dict[str, Any]:
        steps = ExpoSessionFlowService.steps_for_booth(booth)
        step_index = int(session.current_step or 0)
        channel = str(session.channel or "whatsapp").lower()

        # Skip catalogue step when the booth has nothing to download.
        while step_index < len(steps):
            next_step = steps[step_index]
            key = str(next_step.get("key") or "")
            if key == "consent_info":
                consent_ui = ExpoSessionFlowService._consent_prompt_with_assets(
                    db,
                    booth=booth,
                    channel=channel,
                    base_prompt=str(next_step.get("prompt_web") or next_step.get("prompt") or ""),
                    lead=lead,
                    session=session,
                )
                if consent_ui is None:
                    session.current_step = step_index + 1
                    db.add(session)
                    step_index += 1
                    continue
                db.commit()
                return consent_ui
            prompt = str(next_step.get("prompt") or "")
            if channel == "web" and next_step.get("prompt_web"):
                prompt = str(next_step.get("prompt_web") or prompt)
            prompt = with_topic_emoji(key, prompt)
            if channel == "whatsapp" and key in WEB_CHOICE_OPTIONS and key != "consent_info":
                opts = WEB_CHOICE_OPTIONS[key]
                lines = [prompt, ""]
                for idx, opt in enumerate(opts, start=1):
                    lines.append(f"{_emoji_digit(idx)} {opt.get('label') or opt.get('value')}")
                lines.append("")
                lines.append("Reply with the number, e.g. 1")
                prompt = "\n".join(line for line in lines if line is not None).strip()
            return _empty_step_result(
                done=False,
                prompt=prompt,
                question_key=key,
                channel=channel,
            )

        db.commit()
        return ExpoSessionFlowService._complete(db, session=session, booth=booth, lead=lead)

    @staticmethod
    def current_prompt(db: Session, *, session: ExpoSession, booth: ExpoBooth | None = None) -> dict[str, Any]:
        """Return the current step's prompt without consuming an answer (web resume)."""
        if booth is None:
            booth = db.get(ExpoBooth, session.booth_id)
        if booth is None:
            return _empty_step_result(done=True, prompt=THANK_YOU_TEXT)

        lead = ExpoSessionFlowService._lead_for_session(db, session)
        if session.status != "active":
            out = _empty_step_result(done=True, prompt=THANK_YOU_TEXT)
            out["summary"] = ExpoSessionFlowService._lead_summary(db, session=session, lead=lead)
            return ExpoSessionFlowService._attach_progress(out, session=session, booth=booth)

        state = ExpoSessionFlowService._load_state(session)
        channel = str(session.channel or "whatsapp").lower()

        if state.get("pending_asset_pick"):
            out = {
                "done": False,
                "awaiting_pick": True,
                "candidates": state.get("pending_asset_pick") or [],
                "assets": None,
                "prompt": None,
            }
            return ExpoSessionFlowService._attach_progress(out, session=session, booth=booth)

        steps = ExpoSessionFlowService.steps_for_booth(booth)
        step_index = int(session.current_step or 0)
        contact_sub = str(state.get("contact_substep") or "").strip().lower()
        at_contact_step = bool(steps) and step_index == 0 and str(steps[0].get("key") or "") == CONTACT_STEP_KEY
        if at_contact_step and contact_sub in {"", "awaiting", "company", "mobile", "confirm", "card_retry"}:
            sub = contact_sub or "awaiting"
            capture = parse_contact_capture(booth.question_config_json)
            prompt_map = {
                "awaiting": contact_prompt_for_mode(capture, channel=channel),
                "card_retry": contact_prompt_for_mode(capture, channel=channel),
                "company": CONTACT_COMPANY_PROMPT,
                "mobile": CONTACT_MOBILE_PROMPT,
                "confirm": CONTACT_CONFIRM_PROMPT,
            }
            out = _empty_step_result(
                done=False,
                prompt=prompt_map.get(sub, prompt_map["awaiting"]),
                question_key=CONTACT_STEP_KEY,
                contact_substep=sub,
                channel=channel,
            )
            if lead is not None and sub == "confirm":
                out["card_fields"] = {
                    "name": lead.name,
                    "company": lead.company,
                    "email": lead.visitor_email,
                    "phone": lead.visitor_phone,
                }
            return ExpoSessionFlowService._attach_progress(out, session=session, booth=booth)

        result = ExpoSessionFlowService._next_prompt(db, session=session, booth=booth, lead=lead)
        return ExpoSessionFlowService._attach_progress(result, session=session, booth=booth)

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
        thank = build_thank_you_message(
            booth.question_config_json if booth else None,
            company_name=(booth.company_display_name or booth.name) if booth else None,
        )
        summary = ExpoSessionFlowService._lead_summary(db, session=session, lead=lead)
        delivered: list[dict[str, Any]] = []
        if booth is not None and lead is not None:
            delivered = ExpoSessionFlowService._delivered_assets_payload(db, booth=booth, lead=lead)
            if lead.consent_acknowledged or delivered:
                try:
                    from app.services.expo.expo_email_service import ExpoEmailService

                    ExpoEmailService.notify_exhibitor_lead(db, booth=booth, lead=lead, assets=delivered)
                except Exception:
                    logger = __import__("logging").getLogger(__name__)
                    logger.exception("expo_exhibitor_lead_email_failed lead=%s", lead.id)
        db.commit()
        out = _empty_step_result(done=True, prompt=thank)
        out["summary"] = summary
        # Web thank-you download buttons only — WhatsApp must NOT re-send these files.
        if delivered:
            out["assets"] = delivered
            out["deliver_now"] = False

        # Closing "company card" — sent by the channel adapter before the thank-you message so
        # representative contact details land last in the visitor's chat.
        if booth is not None:
            reps = parse_representative_contacts(getattr(booth, "representative_contacts_json", None))
            website = getattr(booth, "company_website", None)
            company_name = booth.company_display_name or booth.name
            if reps or website or company_name:
                from app.services.brand_assets import api_public_origin

                api_base = api_public_origin().rstrip("/")
                logo_url = None
                try:
                    from app.models.organisation import Organisation

                    org = db.get(Organisation, booth.org_id)
                    if org is not None and getattr(org, "logo_storage_key", None):
                        logo_url = f"{api_base}/public/expo/{booth.qr_token}/logo"
                except Exception:
                    logo_url = None
                card_intro = get_template_prompt(db, "company_card", DEFAULT_COMPANY_CARD)
                card_text = build_company_card_text(
                    intro=card_intro,
                    company_name=company_name,
                    website=website,
                    reps=reps,
                    logo_url=logo_url,
                )
                out["company_card"] = card_text
                out["representatives"] = reps
                out["company_website"] = website
                out["company_logo_url"] = logo_url
                out["pre_thank_you_messages"] = [card_text]
                if getattr(booth, "qr_token", None):
                    vcard_url = f"{api_base}/public/expo/{booth.qr_token}/vcard"
                    out["vcard_url"] = vcard_url
                    out["vcard_url_hint"] = vcard_url
                    safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(company_name or "contact"))[:40] or "contact"
                    out["vcard_document"] = {
                        "url": vcard_url,
                        "filename": f"{safe_name}.vcf",
                        "caption": "📇 Save our contact to your phone",
                    }

        # Hot-lead alert to the exhibitor's mobile — best-effort, never blocks completion.
        if lead is not None and str(lead.lead_score or "").lower() == "hot" and getattr(booth, "notify_mobile", None):
            try:
                from app.services.expo.hot_lead_notify_service import notify_hot_lead

                notified = notify_hot_lead(db, booth=booth, lead=lead)
                out["hot_notify_pending"] = not notified
            except Exception:
                logger = __import__("logging").getLogger(__name__)
                logger.exception("expo_hot_lead_notify_dispatch_failed lead=%s", lead.id)
                out["hot_notify_pending"] = True

        return ExpoSessionFlowService._attach_progress(out, session=session, booth=booth)

    @staticmethod
    def stop(db: Session, *, session: ExpoSession) -> dict[str, Any]:
        """Visitor stopped mid-flow — keep collected data, mark completed, return summary."""
        lead = ExpoSessionFlowService._lead_for_session(db, session)
        booth = db.get(ExpoBooth, session.booth_id)
        if session.status != "active":
            out = _empty_step_result(done=True, prompt=THANK_YOU_TEXT)
            out["summary"] = ExpoSessionFlowService._lead_summary(db, session=session, lead=lead)
            return ExpoSessionFlowService._attach_progress(out, session=session, booth=booth)
        return ExpoSessionFlowService._complete(db, session=session, booth=booth, lead=lead)

    @staticmethod
    def go_back(db: Session, *, session: ExpoSession) -> dict[str, Any]:
        """Rewind one questionnaire step (web Back). Keeps lead data; removes last answer row."""
        if session.status != "active":
            return ExpoSessionFlowService.stop(db, session=session)

        booth = db.get(ExpoBooth, session.booth_id)
        if booth is None:
            return ExpoSessionFlowService.stop(db, session=session)

        lead = ExpoSessionFlowService._lead_for_session(db, session)
        state = ExpoSessionFlowService._load_state(session)
        channel = str(session.channel or "whatsapp").lower()

        # Cancel interstitial product pick without losing the interest answer.
        if state.get("pending_asset_pick"):
            state.pop("pending_asset_pick", None)
            ExpoSessionFlowService._save_state(session, state)
            db.add(session)
            db.commit()
            return ExpoSessionFlowService._attach_progress(
                ExpoSessionFlowService._next_prompt(db, session=session, booth=booth, lead=lead),
                session=session,
                booth=booth,
            )

        step_index = int(session.current_step or 0)
        steps = ExpoSessionFlowService.steps_for_booth(booth)

        if step_index <= 0:
            # Already on contact — reset contact UI for re-edit.
            state["contact_substep"] = "awaiting"
            ExpoSessionFlowService._save_state(session, state)
            session.current_step = 0
            db.add(session)
            db.commit()
            prompt = contact_prompt_for_mode(parse_contact_capture(booth.question_config_json), channel=channel)
            out = _empty_step_result(
                done=False,
                prompt=prompt,
                question_key=CONTACT_STEP_KEY,
                contact_substep="awaiting",
                channel=channel,
            )
            out["at_start"] = True
            return ExpoSessionFlowService._attach_progress(out, session=session, booth=booth)

        # Delete the answer that advanced us onto the current step.
        prev_index = step_index - 1
        prev_key = str(steps[prev_index].get("key") or "") if prev_index < len(steps) else ""
        last = (
            db.execute(
                select(ExpoResponse)
                .where(ExpoResponse.session_id == session.id)
                .order_by(ExpoResponse.created_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if last is not None and (not prev_key or last.question_key == prev_key or last.question_key == CONTACT_STEP_KEY):
            db.delete(last)

        session.current_step = prev_index
        db.add(session)

        if prev_key == CONTACT_STEP_KEY or prev_index == 0:
            state["contact_substep"] = "confirm"
            ExpoSessionFlowService._save_state(session, state)
            db.commit()
            out = _empty_step_result(
                done=False,
                prompt=CONTACT_CONFIRM_PROMPT,
                question_key=CONTACT_STEP_KEY,
                contact_substep="confirm",
                channel=channel,
            )
            if lead is not None:
                out["card_fields"] = {
                    "name": lead.name,
                    "company": lead.company,
                    "email": lead.visitor_email,
                    "phone": lead.visitor_phone,
                }
            return ExpoSessionFlowService._attach_progress(out, session=session, booth=booth)

        db.commit()
        result = ExpoSessionFlowService._next_prompt(db, session=session, booth=booth, lead=lead)
        return ExpoSessionFlowService._attach_progress(result, session=session, booth=booth)

    # ------------------------------------------------------------------
    # Hybrid asset offer helpers already defined above
    # ------------------------------------------------------------------
