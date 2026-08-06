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
    SmartCardCategory,
    SmartCardCompany,
    SmartCardLead,
    SmartCardProduct,
    SmartCardQuestionTemplate,
    SmartCardRepresentative,
    SmartCardRepresentativeProduct,
    SmartCardResponse,
    SmartCardSession,
)
from app.services.expo.question_bank import (
    NO_WORDS,
    WEB_CHOICE_OPTIONS,
    WEB_MULTI_CHOICE_KEYS,
    WEB_VOICE_KEYS,
    format_numbered_prompt,
    looks_affirmative,
    parse_pick_numbers,
)
from app.services.smart_card.company_service import SmartCardCompanyService, SmartCardEntitlementService
from app.services.smart_card.email_service import SmartCardEmailService

logger = logging.getLogger(__name__)

DEFAULT_STEPS = (
    "contact",
    "interest",
    "role",
    "timeline",
    "decision_maker",
    "budget",
    "volume",
    "follow_up",
    "consent_info",
    "open_feedback",
)

CONTACT_STEPS = frozenset({"contact", "contact_web", "contact_card_only", "contact_manual"})

# Steps that offer the representative's assigned catalogue products instead of a plain Yes/No.
PRODUCT_MENU_STEPS = frozenset({"consent_info", "products_wanted", "need_catalogue"})

NO_THANKS_VALUE = "No thanks"
NO_THANKS_LABEL = "🙅 No thanks"
WA_SKIP_HINT = "Or reply *Skip* to move on (same as web)."


def _score_lead(*, interest: str | None, timeline: str | None, consent: str | None) -> str:
    from app.services.expo.scoring_service import score_lead

    c = (consent or "").strip().lower()
    consented = c not in {"no", "n", "false", "0"}
    return score_lead(interest=interest, timeline=timeline, consent=consented)


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
    def _prompt_for(prompts: dict[str, str], step: str, channel: str) -> str:
        """Resolve the Admin-editable prompt, preferring the web variant for browser sessions."""
        if channel == "web" and step == "contact":
            web = str(prompts.get("contact_web") or "").strip()
            if web:
                return web
        return str(prompts.get(step) or "").strip() or "Please continue."

    @staticmethod
    def _rep_products(db: Session, *, representative_id: str) -> list[dict[str, str]]:
        """Catalogue products assigned to this representative, in category then product order."""
        rows = db.execute(
            select(SmartCardProduct, SmartCardCategory)
            .join(
                SmartCardRepresentativeProduct,
                SmartCardRepresentativeProduct.product_id == SmartCardProduct.id,
            )
            .join(SmartCardCategory, SmartCardCategory.id == SmartCardProduct.category_id)
            .where(SmartCardRepresentativeProduct.representative_id == representative_id)
            .order_by(
                SmartCardCategory.sort_order.asc(),
                SmartCardCategory.name.asc(),
                SmartCardProduct.sort_order.asc(),
                SmartCardProduct.name.asc(),
            )
        ).all()
        out: list[dict[str, str]] = []
        for product, category in rows:
            name = str(product.name or "").strip()
            if not name:
                continue
            out.append(
                {
                    "id": str(product.id),
                    "name": name,
                    "description": str(product.short_description or "").strip(),
                    "category_name": str(category.name or "").strip(),
                }
            )
        return out

    @staticmethod
    def _products_by_ids(db: Session, ids: list[str]) -> list[dict[str, str]]:
        """Rebuild a stored menu in its original order so reply numbers stay stable."""
        wanted = [str(i) for i in ids if str(i or "").strip()]
        if not wanted:
            return []
        rows = db.execute(
            select(SmartCardProduct, SmartCardCategory)
            .join(SmartCardCategory, SmartCardCategory.id == SmartCardProduct.category_id)
            .where(SmartCardProduct.id.in_(wanted))
        ).all()
        by_id = {
            str(product.id): {
                "id": str(product.id),
                "name": str(product.name or "").strip(),
                "description": str(product.short_description or "").strip(),
                "category_name": str(category.name or "").strip(),
            }
            for product, category in rows
        }
        return [by_id[i] for i in wanted if i in by_id and by_id[i]["name"]]

    @staticmethod
    def _product_option_label(product: dict[str, str]) -> str:
        name = product.get("name") or "Product"
        desc = (product.get("description") or "").strip()
        if desc:
            return f"{name} — {desc[:80]}"
        return name

    @staticmethod
    def _product_options(products: list[dict[str, str]]) -> list[dict[str, str]]:
        options = [
            {
                "value": p["name"],
                "label": SmartCardSessionFlowService._product_option_label(p),
                "product_id": p["id"],
                "category": p.get("category_name") or "",
            }
            for p in products
        ]
        options.append({"value": NO_THANKS_VALUE, "label": NO_THANKS_LABEL, "product_id": "", "category": ""})
        return options

    @staticmethod
    def _question_ui(
        db: Session,
        *,
        session: SmartCardSession,
        state: dict[str, Any],
        step: str,
        channel: str,
    ) -> dict[str, Any]:
        """Input kind + closed choices for one step. Mutates ``state`` to pin the product menu order."""
        if step in CONTACT_STEPS:
            return {"input": "contact", "options": [], "allow_voice": False}

        if step in PRODUCT_MENU_STEPS:
            products = SmartCardSessionFlowService._rep_products(
                db, representative_id=session.representative_id
            )
            if products:
                state["product_menu_ids"] = [p["id"] for p in products]
                return {
                    "input": "multi_choice",
                    "options": SmartCardSessionFlowService._product_options(products),
                    "allow_voice": False,
                }
            state.pop("product_menu_ids", None)

        options = WEB_CHOICE_OPTIONS.get(step)
        if options:
            return {
                "input": "multi_choice" if step in WEB_MULTI_CHOICE_KEYS else "choice",
                "options": [dict(o) for o in options],
                "allow_voice": False,
            }
        # Same as Expo web: only interest + open_feedback stay free text/voice.
        return {
            "input": "text",
            "options": [],
            "allow_voice": step in WEB_VOICE_KEYS,
        }

    @staticmethod
    def _step_payload(
        db: Session,
        *,
        session: SmartCardSession,
        state: dict[str, Any],
        steps: list[str],
        idx: int,
        channel: str,
        prompts: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        step = steps[idx] if 0 <= idx < len(steps) else (steps[0] if steps else "contact")
        chan = str(channel or "web").strip().lower() or "web"
        prompts = prompts if prompts is not None else SmartCardSessionFlowService._prompts(db)
        base_prompt = SmartCardSessionFlowService._prompt_for(prompts, step, chan)
        ui = SmartCardSessionFlowService._question_ui(
            db, session=session, state=state, step=step, channel=chan
        )
        prompt = base_prompt
        if chan == "whatsapp" and ui["options"]:
            hint = (
                "Reply with the number(s), e.g. 1 or 1,2"
                if ui["input"] == "multi_choice"
                else "Reply with the number, e.g. 1"
            )
            prompt = format_numbered_prompt(
                base_prompt, [str(o.get("label") or o.get("value")) for o in ui["options"]], hint=hint
            )
        elif chan == "whatsapp" and ui["input"] == "text":
            # Don't keep open questions as ask-only — offer Skip like Expo web.
            prompt = f"{base_prompt}\n\n{WA_SKIP_HINT}".strip()
        return {
            "step": step,
            "question_key": step,
            "prompt": prompt,
            "input": ui["input"],
            "options": ui["options"],
            "allow_voice": ui["allow_voice"],
            "step_index": idx,
            "step_total": len(steps),
        }

    @staticmethod
    def _contact_snapshot(state: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": state.get("name") or "",
            "company": state.get("company") or "",
            "email": state.get("visitor_email") or "",
            "mobile": state.get("visitor_phone") or "",
            "has_business_card": bool(state.get("business_card_path")),
        }

    @staticmethod
    def _resolve_product_reply(
        text: str, menu: list[dict[str, str]]
    ) -> tuple[list[dict[str, str]], bool]:
        """Map "1", "1,2", "1️⃣" or product names to menu entries. Returns (chosen, declined)."""
        raw = str(text or "").strip()
        lower = raw.lower()
        if not raw or not menu:
            return [], False
        picks = parse_pick_numbers(raw)
        no_index = len(menu) + 1
        if lower in NO_WORDS or lower == NO_THANKS_VALUE.lower() or picks == [no_index]:
            return [], True

        chosen: list[dict[str, str]] = []
        seen: set[str] = set()

        def _add(item: dict[str, str]) -> None:
            if item["id"] not in seen:
                seen.add(item["id"])
                chosen.append(item)

        for n in picks:
            if 1 <= n <= len(menu):
                _add(menu[n - 1])
        if not chosen:
            for item in menu:
                name = item["name"].strip().lower()
                if name and name in lower:
                    _add(item)
        if not chosen and lower in {"all", "everything", "all of them", "both"}:
            for item in menu:
                _add(item)
        return chosen, False

    @staticmethod
    def _remap_choice_reply(text: str, options: list[dict[str, Any]], *, multi: bool = True) -> str:
        from app.services.expo.question_bank import remap_choice_reply

        return remap_choice_reply(text, options, multi=multi)

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

        payload = SmartCardSessionFlowService._step_payload(
            db, session=session, state=state, steps=steps, idx=0, channel=channel
        )
        session.state_json = json.dumps(state)
        db.add(session)
        db.flush()
        return {
            "ok": True,
            "session_id": session.id,
            "is_preview": is_preview,
            "contact_capture": SmartCardSessionFlowService._contact_capture(company),
            "steps": steps,
            "contact": SmartCardSessionFlowService._contact_snapshot(state),
            **payload,
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

        channel = str(session.channel or "web").strip().lower() or "web"
        consent_value: str | None = None
        lower_answer = text.lower().strip()
        is_open_step = bool(step) and step not in CONTACT_STEPS and step not in PRODUCT_MENU_STEPS and step not in WEB_CHOICE_OPTIONS
        if is_open_step and lower_answer in {"skip", "skip this", "skip this question", "pass", "n/a", "na"}:
            text = "skip"

        if step in PRODUCT_MENU_STEPS and state.get("product_menu_ids"):
            menu = SmartCardSessionFlowService._products_by_ids(
                db, list(state.get("product_menu_ids") or [])
            )
            chosen, declined = SmartCardSessionFlowService._resolve_product_reply(text, menu)
            if chosen:
                state["selected_products"] = [{"id": p["id"], "name": p["name"]} for p in chosen]
                text = ", ".join(p["name"] for p in chosen)
                consent_value = "Yes"
            elif declined:
                state["selected_products"] = []
                text = NO_THANKS_VALUE
                consent_value = "No"
        elif step and step not in CONTACT_STEPS and WEB_CHOICE_OPTIONS.get(step):
            text = SmartCardSessionFlowService._remap_choice_reply(
                text,
                [dict(o) for o in WEB_CHOICE_OPTIONS[step]],
                multi=step in WEB_MULTI_CHOICE_KEYS,
            )

        if step in CONTACT_STEPS:
            saved = [
                state.get("name"),
                state.get("company"),
                state.get("visitor_email"),
                state.get("visitor_phone"),
            ]
            # A bare "Yes" confirms scanned card details — never overwrite the name with it.
            if any(saved) and looks_affirmative(text):
                text = " | ".join(str(v).strip() for v in saved if str(v or "").strip()) or "Confirmed"
            else:
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
                state["consent"] = (consent_value or text)[:64]

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

        payload = SmartCardSessionFlowService._step_payload(
            db, session=session, state=state, steps=steps, idx=idx, channel=channel
        )
        session.current_step = payload["step"]
        session.state_json = json.dumps(state)
        session.updated_at = datetime.utcnow()
        db.add(session)
        db.flush()
        return {
            "ok": True,
            "session_id": session.id,
            "done": False,
            "answer_source": answer_source,
            "contact": SmartCardSessionFlowService._contact_snapshot(state),
            **payload,
        }

    @staticmethod
    def go_back(db: Session, *, session: SmartCardSession) -> dict[str, Any]:
        """Rewind one step inside the same session, keeping scanned card and contact details."""
        if session.status != "active":
            raise SmartCardSessionError("Session is not active")
        state = SmartCardSessionFlowService._load_state(session)
        steps: list[str] = list(state.get("steps") or DEFAULT_STEPS)
        idx = int(state.get("step_index") or 0)
        channel = str(session.channel or "web").strip().lower() or "web"
        at_start = idx <= 0

        if not at_start:
            idx -= 1
            prev_step = steps[idx]
            row = db.execute(
                select(SmartCardResponse)
                .where(
                    SmartCardResponse.session_id == session.id,
                    SmartCardResponse.question_key == prev_step,
                )
                .order_by(SmartCardResponse.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if row is not None:
                db.delete(row)
            state["step_index"] = idx

        saved_answer = (state.get("answers") or {}).get(steps[idx] if 0 <= idx < len(steps) else "")
        payload = SmartCardSessionFlowService._step_payload(
            db, session=session, state=state, steps=steps, idx=idx, channel=channel
        )
        session.current_step = payload["step"]
        session.state_json = json.dumps(state)
        session.updated_at = datetime.utcnow()
        db.add(session)
        db.flush()
        return {
            "ok": True,
            "session_id": session.id,
            "done": False,
            "at_start": at_start,
            "saved_answer": saved_answer,
            "contact": SmartCardSessionFlowService._contact_snapshot(state),
            **payload,
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
        business_card_path: str | None = None,
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
        if business_card_path:
            state["business_card_path"] = str(business_card_path)[:2000]
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
            "contact": SmartCardSessionFlowService._contact_snapshot(state),
            "prompt": "Please confirm these details are correct (Yes), or type corrections as Name | Company | email | phone.",
            "step": session.current_step or "contact",
            "question_key": session.current_step or "contact",
            "input": "contact",
            "options": [],
            "allow_voice": False,
        }

    @staticmethod
    def _complete(db: Session, *, session: SmartCardSession, state: dict[str, Any]) -> dict[str, Any]:
        rep = db.get(SmartCardRepresentative, session.representative_id)
        if rep is None:
            raise SmartCardSessionError("Representative missing")

        answers = state.get("answers") or {}
        card_path = state.get("business_card_path")
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
            business_card_path=(str(card_path)[:2000] if card_path else None),
        )
        lead.lead_score = _score_lead(
            interest=lead.interest,
            timeline=lead.buying_timeline,
            consent=lead.consent,
        )
        selected_products = state.get("selected_products") or []
        if selected_products:
            lead.assets_sent_json = json.dumps({"products": selected_products}, ensure_ascii=False)
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

        # Catalogue delivery for the products the visitor picked — links for every channel,
        # attachments for the visitor email. Never blocks completion.
        delivery: list[dict[str, Any]] = []
        if selected_products:
            try:
                from app.services.smart_card.asset_delivery_service import (
                    build_delivery_rows,
                    mark_lead_assets_sent,
                )

                delivery = build_delivery_rows(
                    db,
                    org_id=session.org_id,
                    qr_token=rep.qr_token,
                    lead_id=lead.id,
                    product_ids=[str(p.get("id")) for p in selected_products if p.get("id")],
                )
                if delivery:
                    mark_lead_assets_sent(db, lead=lead, assets=delivery)
                    db.flush()
            except Exception:
                logger.exception("smart_card_asset_delivery_failed lead=%s", lead.id)
                delivery = []

        try:
            SmartCardEmailService.notify_rep_lead(db, rep=rep, lead=lead)
        except Exception:
            logger.exception("smart_card_lead_email_failed")

        if delivery and (lead.visitor_email or "").strip():
            try:
                SmartCardEmailService.send_visitor_catalogue(
                    db, rep=rep, lead=lead, assets=delivery
                )
            except Exception:
                logger.exception("smart_card_visitor_catalogue_failed lead=%s", lead.id)

        # Hot-lead WhatsApp alert only for WhatsApp sessions — web completions stay email-only.
        score = str(lead.lead_score or "").lower()
        is_whatsapp = str(session.channel or "").strip().lower() == "whatsapp"
        if is_whatsapp and score in {"hot", "high"} and getattr(rep, "mobile", None):
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
            "assets": [
                {
                    "id": a.get("id"),
                    "title": a.get("title"),
                    "url": a.get("url"),
                    "filename": a.get("filename"),
                    "purpose": a.get("purpose"),
                }
                for a in delivery
            ],
        }
