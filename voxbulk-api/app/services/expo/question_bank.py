"""Expo question bank + hybrid product match helpers."""

from __future__ import annotations

import json
import re
from typing import Any

from app.services.expo.seed_service import UNIVERSAL_QUESTIONS

DEFAULT_THANK_YOU = "Thanks so much for stopping by our stand — we'll be in touch soon!"
DEFAULT_FREE_GIFT_TEXT = (
    "Please collect your free gift from our stand team — thanks for completing the short questionnaire!"
)

# Fixed contact capture — visitor can send a business-card photo OR type details.
CONTACT_STEP_KEY = "contact"
CONTACT_PROMPT_WA = (
    "Send a photo of your business card, or reply with your full name "
    "(photo skips typing name, company and mobile)."
)
CONTACT_PROMPT_WEB = (
    "Upload a photo of your business card, or enter your name and company "
    "(photo skips typing name, company and mobile)."
)
CONTACT_PROMPT_WA_CARD_ONLY = "Please send a photo of your business card to continue."
CONTACT_PROMPT_WEB_CARD_ONLY = "Please upload a photo of your business card to continue."
CONTACT_PROMPT_WA_MANUAL = "What's your full name?"
CONTACT_PROMPT_WEB_MANUAL = "What's your full name?"
CONTACT_COMPANY_PROMPT = "Which company or organisation do you represent?"
CONTACT_MOBILE_PROMPT = "What's the best mobile number to reach you on?"


def contact_prompt_for_mode(mode: str, *, channel: str = "whatsapp") -> str:
    m = str(mode or "offer_both").strip().lower()
    web = str(channel or "").lower() == "web"
    if m == "card_only":
        return CONTACT_PROMPT_WEB_CARD_ONLY if web else CONTACT_PROMPT_WA_CARD_ONLY
    if m == "manual_only":
        return CONTACT_PROMPT_WEB_MANUAL if web else CONTACT_PROMPT_WA_MANUAL
    return CONTACT_PROMPT_WEB if web else CONTACT_PROMPT_WA

# Extra qualifying questions exhibitors can toggle on (in addition to fixed contact).
# Keys with matches_products=True help route Step 4 product PDFs (price list / catalogue).
SELECTABLE_QUESTION_BANK: list[dict[str, Any]] = [
    {
        "key": "interest",
        "prompt": "What is the main thing you're looking for or interested in right now?",
        "label": "Main interest",
        "description": "Open interest — used for general matching.",
        "matches_products": True,
    },
    {
        "key": "need_price_list",
        "prompt": "Would you like our latest price list?",
        "label": "Need price list",
        "description": "Matches Step 4 products tagged with price / pricing keywords.",
        "matches_products": True,
    },
    {
        "key": "need_catalogue",
        "prompt": "Would you like our product catalogue or brochure?",
        "label": "Need catalogue",
        "description": "Matches Step 4 products tagged with catalogue / brochure keywords.",
        "matches_products": True,
    },
    {
        "key": "products_wanted",
        "prompt": "Which product or brochure should we send you?",
        "label": "Product request",
        "description": "Visitor names a product — matched to your uploaded files.",
        "matches_products": True,
    },
    {
        "key": "timeline",
        "prompt": "When are you planning to make a decision or take action on this?",
        "label": "Buying timeline",
        "description": "Used for Hot / Warm / Cold scoring.",
        "matches_products": False,
    },
    {
        "key": "sourcing",
        "prompt": "Are you sourcing for your business, or for events?",
        "label": "Business or events",
        "description": "Useful for hospitality / trade stands.",
        "matches_products": False,
    },
    {
        "key": "role",
        "prompt": "What's your role or job title?",
        "label": "Job title",
        "description": "Contact role for follow-up.",
        "matches_products": False,
    },
    {
        "key": "decision_maker",
        "prompt": "Are you the decision-maker for this, or recommending to someone else?",
        "label": "Decision-maker",
        "description": "Buying authority signal.",
        "matches_products": False,
    },
    {
        "key": "budget",
        "prompt": "Do you have a rough budget in mind for this?",
        "label": "Budget",
        "description": "Optional budget band.",
        "matches_products": False,
    },
    {
        "key": "volume",
        "prompt": "Roughly what volume or quantity are you thinking about?",
        "label": "Volume / quantity",
        "description": "Order size / volume.",
        "matches_products": False,
    },
    {
        "key": "follow_up",
        "prompt": "How would you prefer we follow up — WhatsApp, email, or a call?",
        "label": "Follow-up preference",
        "description": "Preferred contact channel after the show.",
        "matches_products": False,
    },
    {
        "key": "consent_info",
        "prompt": "Would you like us to send you our latest information and special offers? (Yes / No)",
        "label": "Marketing consent",
        "description": "GDPR-style consent for offers.",
        "matches_products": False,
    },
]

_DEFAULT_SELECTED_KEYS = ("interest", "need_price_list", "need_catalogue", "timeline", "consent_info")
_BANK_BY_KEY = {q["key"]: q for q in SELECTABLE_QUESTION_BANK}


def list_selectable_questions(
    db: Any | None = None,
    *,
    addon_question: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if db is not None:
        try:
            from sqlalchemy import select

            from app.models.expo import ExpoQuestionTemplate

            db_rows = db.execute(
                select(ExpoQuestionTemplate)
                .where(ExpoQuestionTemplate.is_active.is_(True))
                .order_by(ExpoQuestionTemplate.sort_order.asc())
            ).scalars().all()
            for r in db_rows:
                rows.append(
                    {
                        "key": r.question_key,
                        "prompt": r.prompt,
                        "label": r.label,
                        "description": r.description or "",
                        "matches_products": bool(r.matches_products),
                        "id": r.id,
                    }
                )
        except Exception:
            rows = []
    if not rows:
        rows = [dict(q) for q in SELECTABLE_QUESTION_BANK]
    addon = str(addon_question or "").strip()
    if addon and not any(r.get("key") == "industry_addon" for r in rows):
        rows.insert(
            min(2, len(rows)),
            {
                "key": "industry_addon",
                "prompt": addon,
                "label": "Industry question",
                "description": "Industry-specific follow-up from the Expo industry.",
                "matches_products": False,
            },
        )
    return rows


def default_question_config(
    *,
    include_industry_addon: bool = False,
    addon_question: str | None = None,
    free_gift_enabled: bool = False,
    free_gift_text: str | None = None,
    thank_you_message: str | None = None,
    selected_question_keys: list[str] | None = None,
    contact_capture: str = "offer_both",
) -> dict[str, Any]:
    keys = list(selected_question_keys) if selected_question_keys else list(_DEFAULT_SELECTED_KEYS)
    if include_industry_addon and str(addon_question or "").strip() and "industry_addon" not in keys:
        # Place before consent when present
        if "consent_info" in keys:
            keys.insert(keys.index("consent_info"), "industry_addon")
        else:
            keys.append("industry_addon")

    steps: list[dict[str, Any]] = [
        {
            "key": CONTACT_STEP_KEY,
            "kind": "contact",
            "prompt": CONTACT_PROMPT_WA,
            "prompt_web": CONTACT_PROMPT_WEB,
        }
    ]
    for key in keys:
        if key == CONTACT_STEP_KEY:
            continue
        if key == "industry_addon":
            prompt = str(addon_question or "").strip()
            if not prompt:
                continue
            steps.append({"key": key, "prompt": prompt, "kind": "text", "label": "Industry question"})
            continue
        bank = _BANK_BY_KEY.get(key)
        if bank:
            steps.append(
                {
                    "key": bank["key"],
                    "prompt": bank["prompt"],
                    "kind": "text",
                    "label": bank["label"],
                }
            )

    # Legacy fallback if somehow empty after contact
    if len(steps) == 1:
        for q in UNIVERSAL_QUESTIONS:
            if q["key"] in {"name", "company"}:
                continue
            steps.append({"key": q["key"], "prompt": q["prompt"], "kind": "text"})

    gift_on = bool(free_gift_enabled)
    gift_text = str(free_gift_text or "").strip() or DEFAULT_FREE_GIFT_TEXT
    mode = str(contact_capture or "offer_both").strip().lower()
    if mode not in {"offer_both", "manual_only", "card_only"}:
        mode = "offer_both"
    steps[0]["prompt"] = contact_prompt_for_mode(mode, channel="whatsapp")
    steps[0]["prompt_web"] = contact_prompt_for_mode(mode, channel="web")
    return {
        "steps": steps,
        "version": 2,
        "contact_capture": mode,
        "selected_question_keys": [s["key"] for s in steps if s["key"] != CONTACT_STEP_KEY],
        "thank_you_message": str(thank_you_message or "").strip() or DEFAULT_THANK_YOU,
        "free_gift_enabled": gift_on,
        "free_gift_text": gift_text if gift_on else "",
    }


def parse_question_config(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return list(default_question_config()["steps"])
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return list(default_question_config()["steps"])
    steps = data.get("steps") if isinstance(data, dict) else None
    if not isinstance(steps, list) or not steps:
        return list(default_question_config()["steps"])
    out: list[dict[str, Any]] = []
    for step in steps[:12]:
        if not isinstance(step, dict):
            continue
        key = str(step.get("key") or "").strip()
        prompt = str(step.get("prompt") or "").strip()
        if key and prompt:
            item: dict[str, Any] = {
                "key": key,
                "prompt": prompt,
                "kind": str(step.get("kind") or "text"),
            }
            if step.get("prompt_web"):
                item["prompt_web"] = str(step.get("prompt_web"))
            if step.get("label"):
                item["label"] = str(step.get("label"))
            out.append(item)
    return out or list(default_question_config()["steps"])


def parse_contact_capture(raw: str | None) -> str:
    if not raw:
        return "offer_both"
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return "offer_both"
    if not isinstance(data, dict):
        return "offer_both"
    mode = str(data.get("contact_capture") or "offer_both").strip().lower()
    return mode if mode in {"offer_both", "manual_only", "card_only"} else "offer_both"


def parse_closing_config(raw: str | None) -> dict[str, Any]:
    """Thank-you + optional free-gift settings stored alongside question steps."""
    if not raw:
        return {
            "thank_you_message": DEFAULT_THANK_YOU,
            "free_gift_enabled": False,
            "free_gift_text": DEFAULT_FREE_GIFT_TEXT,
        }
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    gift_on = bool(data.get("free_gift_enabled"))
    gift_text = str(data.get("free_gift_text") or "").strip() or DEFAULT_FREE_GIFT_TEXT
    thank = str(data.get("thank_you_message") or "").strip() or DEFAULT_THANK_YOU
    return {
        "thank_you_message": thank,
        "free_gift_enabled": gift_on,
        "free_gift_text": gift_text,
    }


def build_thank_you_message(raw_config: str | None) -> str:
    closing = parse_closing_config(raw_config)
    thank = str(closing.get("thank_you_message") or DEFAULT_THANK_YOU).strip()
    if closing.get("free_gift_enabled"):
        gift = str(closing.get("free_gift_text") or DEFAULT_FREE_GIFT_TEXT).strip()
        if gift:
            return f"{thank}\n\n{gift}"
    return thank


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(str(text or "").lower()) if len(t) > 2}


def score_asset_match(interest_text: str, *, title: str, description: str | None, keywords: str | None) -> int:
    interest = _tokens(interest_text)
    if not interest:
        return 0
    hay = _tokens(f"{title} {description or ''} {keywords or ''}")
    if not hay:
        return 0
    return len(interest & hay)


def pick_assets_for_interest(
    interest_text: str,
    assets: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """
    Returns (mode, assets):
      - direct: single high-confidence match
      - list: numbered picker candidates
      - full: full catalog (vague)
    """
    if not assets:
        return "none", []
    scored: list[tuple[int, dict[str, Any]]] = []
    for asset in assets:
        score = score_asset_match(
            interest_text,
            title=str(asset.get("title") or ""),
            description=str(asset.get("short_description") or ""),
            keywords=str(asset.get("match_keywords") or ""),
        )
        scored.append((score, asset))
    scored.sort(key=lambda x: (-x[0], int(x[1].get("sort_order") or 100)))
    strong = [a for s, a in scored if s >= 2]
    if len(strong) == 1:
        return "direct", strong
    if len(strong) >= 2:
        return "list", strong[:5]
    defaults = [a for a in assets if a.get("is_default")]
    if defaults and not str(interest_text or "").strip():
        return "direct", defaults[:1]
    return "full", assets[:5]


def format_asset_list_message(assets: list[dict[str, Any]]) -> str:
    lines = ["Which would you like?", ""]
    for idx, asset in enumerate(assets, start=1):
        title = str(asset.get("title") or f"Option {idx}")
        desc = str(asset.get("short_description") or "").strip()
        lines.append(f"{idx}. {title}" + (f" — {desc}" if desc else ""))
    lines.append("")
    lines.append("Reply with the number (1, 2, …) or the product name.")
    return "\n".join(lines)


def resolve_pick_reply(text: str, pending: list[dict[str, Any]]) -> dict[str, Any] | None:
    raw = str(text or "").strip().lower()
    if not raw or not pending:
        return None
    if raw.isdigit():
        n = int(raw)
        if 1 <= n <= len(pending):
            return pending[n - 1]
    for asset in pending:
        title = str(asset.get("title") or "").strip().lower()
        key = str(asset.get("asset_key") or "").strip().lower()
        if title and title in raw:
            return asset
        if key and key in raw:
            return asset
    return None
