"""Expo question bank + hybrid product match helpers."""

from __future__ import annotations

import json
import re
from typing import Any

from app.services.expo.seed_service import UNIVERSAL_QUESTIONS

DEFAULT_THANK_YOU = "✅ Thanks so much for stopping by our stand — we'll be in touch soon!"
DEFAULT_FREE_GIFT_TEXT = (
    "🎁 Please collect your free gift from our stand team — thanks for completing the short questionnaire!"
)
POST_COMPLETE_HANDOFF = (
    "💬 Thanks — our team will follow up with you shortly. "
    "If you need anything else, speak with our stand team."
)


def default_free_gift_text(company_name: str | None = None) -> str:
    """Default free-gift closing copy; includes company so multi-stand visitors know which offer it is."""
    name = str(company_name or "").strip()
    if not name:
        return DEFAULT_FREE_GIFT_TEXT
    return (
        f"🎁 Please collect your free gift from {name}'s stand team — "
        "thanks for completing the short questionnaire!"
    )


def thank_you_with_company(company_name: str | None = None) -> str:
    name = str(company_name or "").strip()
    if name:
        return f"✅ Thanks for visiting {name}! We'll be in touch soon."
    return DEFAULT_THANK_YOU


# Fixed contact capture — visitor can send a business-card photo OR type details.
CONTACT_STEP_KEY = "contact"
CONTACT_PROMPT_WA = (
    "👋 Send a photo of your business card, or reply with your full name "
    "(photo skips typing name, company and mobile)."
)
CONTACT_PROMPT_WEB = (
    "👋 Upload a photo of your business card, or enter your name and company "
    "(photo skips typing name, company and mobile)."
)
CONTACT_PROMPT_WA_CARD_ONLY = "📷 Please send a photo of your business card to continue."
CONTACT_PROMPT_WEB_CARD_ONLY = "📷 Please upload a photo of your business card to continue."
CONTACT_PROMPT_WA_MANUAL = "👤 What's your full name?"
CONTACT_PROMPT_WEB_MANUAL = "👤 What's your full name?"
CONTACT_COMPANY_PROMPT = "🏢 Which company or organisation do you represent?"
CONTACT_MOBILE_PROMPT = "📱 What's the best mobile number to reach you on?"


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
        "prompt": "🎯 What are you looking for today at our stand?",
        "label": "What they're looking for",
        "description": "Open interest — used for product matching and lead scoring.",
        "matches_products": True,
    },
    {
        "key": "role",
        "prompt": "👔 Which best describes your role?",
        "label": "Role",
        "description": "Buyer / specifier / influencer — qualifies the lead.",
        "matches_products": False,
    },
    {
        "key": "timeline",
        "prompt": "🗓️ When are you planning to decide or take the next step?",
        "label": "Buying timeline",
        "description": "Used for Hot / Warm / Cold scoring.",
        "matches_products": False,
    },
    {
        "key": "follow_up",
        "prompt": "📞 How should we follow up after the show? (you can pick more than one)",
        "label": "Follow-up preference",
        "description": "Preferred contact channel after the show.",
        "matches_products": False,
    },
    {
        "key": "consent_info",
        "prompt": "📋 Would you like our catalogue and/or price list? Select all that apply.",
        "label": "Catalogue / price list",
        "description": "Shown when the booth has catalogue or price-list files — visitor can download what they want.",
        "matches_products": False,
    },
    # Optional extras (not selected by default)
    {
        "key": "products_wanted",
        "prompt": "📦 Which product or brochure should we send you?",
        "label": "Product request",
        "description": "Visitor names a product — matched to your uploaded files.",
        "matches_products": True,
    },
    {
        "key": "budget",
        "prompt": "💷 Do you have a rough budget in mind for this?",
        "label": "Budget",
        "description": "Optional budget band.",
        "matches_products": False,
    },
    {
        "key": "volume",
        "prompt": "📊 Roughly what volume or quantity are you thinking about?",
        "label": "Volume / quantity",
        "description": "Order size / volume.",
        "matches_products": False,
    },
    {
        "key": "decision_maker",
        "prompt": "✅ Are you the decision-maker for this, or recommending to someone else?",
        "label": "Decision-maker",
        "description": "Buying authority signal.",
        "matches_products": False,
    },
    {
        "key": "sourcing",
        "prompt": "🏢 Are you sourcing for your business, or for events?",
        "label": "Business or events",
        "description": "Useful for hospitality / trade stands.",
        "matches_products": False,
    },
    {
        "key": "need_price_list",
        "prompt": "💰 Would you like our latest price list?",
        "label": "Need price list",
        "description": "Optional — usually covered by automatic product matching after interest.",
        "matches_products": True,
    },
    {
        "key": "need_catalogue",
        "prompt": "📘 Would you like our product catalogue or brochure?",
        "label": "Need catalogue",
        "description": "Optional — usually covered by automatic product matching after interest.",
        "matches_products": True,
    },
]

_DEFAULT_SELECTED_KEYS = ("interest", "role", "timeline", "follow_up", "consent_info")
_BANK_BY_KEY = {q["key"]: q for q in SELECTABLE_QUESTION_BANK}

# Topic emoji for WA/web prompts — applied at send time so existing booths get them too.
QUESTION_TOPIC_EMOJI: dict[str, str] = {
    "contact": "👋",
    "interest": "🎯",
    "role": "👔",
    "timeline": "🗓️",
    "follow_up": "📞",
    "consent_info": "📋",
    "products_wanted": "📦",
    "budget": "💷",
    "volume": "📊",
    "decision_maker": "✅",
    "sourcing": "🏢",
    "need_price_list": "💰",
    "need_catalogue": "📘",
    "industry_addon": "✨",
    "name": "👤",
    "company": "🏢",
}


def with_topic_emoji(key: str, prompt: str) -> str:
    """Prefix a professional topic emoji when the prompt does not already start with one."""
    clean = str(prompt or "").strip()
    if not clean:
        return clean
    emoji = QUESTION_TOPIC_EMOJI.get(str(key or "").strip())
    if not emoji:
        return clean
    if clean.startswith(emoji):
        return clean
    # Already has any known topic emoji / common leading symbol
    known = set(QUESTION_TOPIC_EMOJI.values()) | {"📷", "🎁", "💬", "✅", "👋", "📱"}
    for mark in known:
        if clean.startswith(mark):
            return clean
    # Generic emoji / symbol at start (skip double-prefix)
    first = clean[0]
    if ord(first) > 0x24FF or first in "✨⭐✓✔":
        return clean
    return f"{emoji} {clean}"


# Closed-choice UI for Expo web (CF-style buttons). Open keys stay text+voice.
WEB_CHOICE_OPTIONS: dict[str, list[dict[str, str]]] = {
    "role": [
        {"value": "Buyer", "label": "🛒 Buyer / purchasing"},
        {"value": "Specifier", "label": "🔧 Specifier / technical"},
        {"value": "Influencer", "label": "💡 Influencer / recommender"},
        {"value": "Other", "label": "👤 Other"},
    ],
    "timeline": [
        {"value": "This week", "label": "⚡ This week"},
        {"value": "This month", "label": "📅 This month"},
        {"value": "This quarter", "label": "🗓️ This quarter"},
        {"value": "Later", "label": "⏳ Later"},
        {"value": "Just exploring", "label": "👀 Just exploring"},
    ],
    "follow_up": [
        {"value": "WhatsApp", "label": "💬 WhatsApp"},
        {"value": "Email", "label": "✉️ Email"},
        {"value": "Call", "label": "📞 Call"},
    ],
    "consent_info": [
        {"value": "Yes", "label": "✅ Yes, please"},
        {"value": "No", "label": "🙅 No thanks"},
    ],
    "need_price_list": [
        {"value": "Yes", "label": "✅ Yes"},
        {"value": "No", "label": "🙅 No"},
    ],
    "need_catalogue": [
        {"value": "Yes", "label": "✅ Yes"},
        {"value": "No", "label": "🙅 No"},
    ],
    "sourcing": [
        {"value": "Business", "label": "🏢 For my business"},
        {"value": "Events", "label": "🎉 For events"},
    ],
    "decision_maker": [
        {"value": "Decision-maker", "label": "✅ I'm the decision-maker"},
        {"value": "Recommending", "label": "🤝 Recommending to someone else"},
    ],
}

WEB_VOICE_KEYS = frozenset(
    {
        "interest",
        "products_wanted",
        "budget",
        "volume",
        "industry_addon",
    }
)

# Multi-select on Expo web (visitor can pick several options).
WEB_MULTI_CHOICE_KEYS = frozenset({"follow_up"})


def web_ui_for_question_key(key: str) -> dict[str, Any]:
    """Return input type + options for Expo public web questions."""
    k = str(key or "").strip()
    opts = WEB_CHOICE_OPTIONS.get(k)
    if opts:
        input_kind = "multi_choice" if k in WEB_MULTI_CHOICE_KEYS else "choice"
        return {"input": input_kind, "options": list(opts), "allow_voice": False}
    if k == CONTACT_STEP_KEY:
        return {"input": "contact", "options": [], "allow_voice": False}
    return {"input": "text", "options": [], "allow_voice": k in WEB_VOICE_KEYS or k not in WEB_CHOICE_OPTIONS}


def enrich_step_payload(
    result: dict[str, Any],
    *,
    question_key: str | None = None,
    contact_substep: str | None = None,
    channel: str = "web",
) -> dict[str, Any]:
    """Attach web UI metadata so the public client never desyncs buttons from prompts."""
    out = dict(result or {})
    key = str(question_key or out.get("question_key") or "").strip()
    sub = str(contact_substep or out.get("contact_substep") or "").strip().lower()
    if key:
        out["question_key"] = key
    if sub:
        out["contact_substep"] = sub
    if out.get("done"):
        out.setdefault("input", "done")
        out.setdefault("options", [])
        out.setdefault("allow_voice", False)
        return out
    if out.get("awaiting_pick"):
        out["question_key"] = "product_pick"
        out["input"] = "pick"
        out["options"] = []
        out["allow_voice"] = False
        return out
    if key == CONTACT_STEP_KEY or sub in {"awaiting", "company", "mobile", "confirm", "card_retry"}:
        out["question_key"] = CONTACT_STEP_KEY
        if sub == "confirm":
            out["input"] = "contact_confirm"
        elif sub in {"company", "mobile"}:
            out["input"] = "text"
        else:
            out["input"] = "contact"
        out["options"] = []
        out["allow_voice"] = False
        return out
    ui = web_ui_for_question_key(key)
    out["input"] = ui["input"]
    out["options"] = list(ui["options"])
    out["allow_voice"] = bool(ui["allow_voice"])
    if channel == "web" and key and not out.get("prompt"):
        bank = _BANK_BY_KEY.get(key)
        if bank:
            out["prompt"] = bank["prompt"]
    return out


def upgrade_booth_question_config(raw: str | None) -> str | None:
    """Rewrite legacy booth configs that still use price-list/catalogue Yes/No defaults."""
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    steps = data.get("steps")
    if not isinstance(steps, list):
        return None
    keys = [str(s.get("key") or "") for s in steps if isinstance(s, dict)]
    legacy_markers = {"need_price_list", "need_catalogue"}
    if not (legacy_markers & set(keys)):
        return None
    # Preserve industry addon + closing settings; replace middle with smart defaults.
    has_addon = any(k == "industry_addon" for k in keys)
    addon_prompt = ""
    for s in steps:
        if isinstance(s, dict) and str(s.get("key") or "") == "industry_addon":
            addon_prompt = str(s.get("prompt") or "").strip()
            break
    selected = list(_DEFAULT_SELECTED_KEYS)
    if has_addon and addon_prompt:
        if "consent_info" in selected:
            selected.insert(selected.index("consent_info"), "industry_addon")
        else:
            selected.append("industry_addon")
    upgraded = default_question_config(
        include_industry_addon=bool(addon_prompt),
        addon_question=addon_prompt or None,
        free_gift_enabled=bool(data.get("free_gift_enabled")),
        free_gift_text=str(data.get("free_gift_text") or "") or None,
        thank_you_message=str(data.get("thank_you_message") or "") or None,
        selected_question_keys=selected,
        contact_capture=str(data.get("contact_capture") or "offer_both"),
    )
    return json.dumps(upgraded, ensure_ascii=False)


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
    gift_text = str(free_gift_text or "").strip() or default_free_gift_text()
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


def parse_closing_config(raw: str | None, *, company_name: str | None = None) -> dict[str, Any]:
    """Thank-you + optional free-gift settings stored alongside question steps."""
    fallback_gift = default_free_gift_text(company_name)
    if not raw:
        return {
            "thank_you_message": DEFAULT_THANK_YOU,
            "free_gift_enabled": False,
            "free_gift_text": fallback_gift,
        }
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    gift_on = bool(data.get("free_gift_enabled"))
    gift_text = str(data.get("free_gift_text") or "").strip() or fallback_gift
    thank = str(data.get("thank_you_message") or "").strip() or DEFAULT_THANK_YOU
    return {
        "thank_you_message": thank,
        "free_gift_enabled": gift_on,
        "free_gift_text": gift_text,
    }


def build_thank_you_message(raw_config: str | None, *, company_name: str | None = None) -> str:
    closing = parse_closing_config(raw_config, company_name=company_name)
    thank = str(closing.get("thank_you_message") or DEFAULT_THANK_YOU).strip()
    if closing.get("free_gift_enabled"):
        gift = str(closing.get("free_gift_text") or default_free_gift_text(company_name)).strip()
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
