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
DEFAULT_OPEN_FEEDBACK = (
    "📝 Please share anything else you'd like us to know about your recent experience with us. "
    "Anything at all — big or small, we're listening. 😊 "
    "🗣️ Write it down or record a voice note, in your own language — whatever's easiest for you!"
)
DEFAULT_COMPANY_CARD = "Here's how to reach us:"
OPEN_FEEDBACK_KEY = "open_feedback"


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
CONTACT_EMAIL_PROMPT = (
    "📧 What's the best email for catalogues and follow-up? "
    "(Reply skip if you'd rather not share one.)"
)
EMAIL_SKIP_WORDS = frozenset(
    {"skip", "pass", "n/a", "na", "none", "no", "nope", "nah", "-", "—", "prefer not", "no thanks"}
)


def contact_prompt_for_mode(mode: str, *, channel: str = "whatsapp", db: Any | None = None) -> str:
    m = str(mode or "offer_both").strip().lower()
    web = str(channel or "").lower() == "web"
    if m == "card_only":
        fb = CONTACT_PROMPT_WEB_CARD_ONLY if web else CONTACT_PROMPT_WA_CARD_ONLY
        return get_template_prompt(db, "contact_card_only", fb)
    if m == "manual_only":
        fb = CONTACT_PROMPT_WEB_MANUAL if web else CONTACT_PROMPT_WA_MANUAL
        return get_template_prompt(db, "contact_manual", fb)
    fb = CONTACT_PROMPT_WEB if web else CONTACT_PROMPT_WA
    return get_template_prompt(db, "contact_web" if web else "contact", fb)

# Extra qualifying questions exhibitors can toggle on (in addition to fixed contact).
# Keys with matches_products=True help route Step 4 product PDFs (price list / catalogue).
SELECTABLE_QUESTION_BANK: list[dict[str, Any]] = [
    {
        "key": "interest",
        "prompt": "What are you looking for at our stand today? Type a short answer, or tap the mic and tell us in your own words.",
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
    {
        "key": "offer_interest",
        "prompt": "🎁 Are you interested in our special trade-show offer? (Yes / No)",
        "label": "Trade-show offer",
        "description": "Shown when you add an optional expo offer — claim link is emailed if they say yes.",
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

_DEFAULT_SELECTED_KEYS = (
    "interest",
    "role",
    "timeline",
    "decision_maker",
    "budget",
    "volume",
    "follow_up",
    "consent_info",
)
_BANK_BY_KEY = {q["key"]: q for q in SELECTABLE_QUESTION_BANK}

# Topic emoji for WA/web prompts — applied at send time so existing booths get them too.
QUESTION_TOPIC_EMOJI: dict[str, str] = {
    "contact": "👋",
    "interest": "🎯",
    "role": "👔",
    "timeline": "🗓️",
    "follow_up": "📞",
    "consent_info": "📋",
    "offer_interest": "🎁",
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
    "open_feedback": "📝",
    "thank_you": "✅",
    "post_complete_handoff": "💬",
    "contact_company": "🏢",
    "contact_mobile": "📱",
    "contact_email": "📧",
    "contact_confirm": "✅",
}

# System session strings editable in Admin → Qualifying questions (not exhibitor toggles).
SYSTEM_SESSION_TEMPLATES: list[dict[str, Any]] = [
    {
        "key": "contact",
        "prompt": CONTACT_PROMPT_WA,
        "label": "Contact (WhatsApp)",
        "description": "Business card or type details — WhatsApp.",
        "sort_order": 900,
    },
    {
        "key": "contact_web",
        "prompt": CONTACT_PROMPT_WEB,
        "label": "Contact (Web)",
        "description": "Business card or type details — web.",
        "sort_order": 901,
    },
    {
        "key": "contact_card_only",
        "prompt": CONTACT_PROMPT_WA_CARD_ONLY,
        "label": "Contact card-only",
        "description": "Card photo required.",
        "sort_order": 902,
    },
    {
        "key": "contact_manual",
        "prompt": CONTACT_PROMPT_WA_MANUAL,
        "label": "Contact name (manual)",
        "description": "Ask for full name when typing.",
        "sort_order": 903,
    },
    {
        "key": "contact_company",
        "prompt": CONTACT_COMPANY_PROMPT,
        "label": "Contact company",
        "description": "Ask for company name.",
        "sort_order": 904,
    },
    {
        "key": "contact_mobile",
        "prompt": CONTACT_MOBILE_PROMPT,
        "label": "Contact mobile",
        "description": "Ask for mobile number.",
        "sort_order": 905,
    },
    {
        "key": "contact_email",
        "prompt": CONTACT_EMAIL_PROMPT,
        "label": "Contact email (WhatsApp)",
        "description": "Ask for visitor email so catalogues can be emailed. Skip allowed.",
        "sort_order": 906,
    },
    {
        "key": "contact_confirm",
        "prompt": "✅ Please check your details and continue.",
        "label": "Contact confirm",
        "description": "Confirm OCR / typed details.",
        "sort_order": 907,
    },
    {
        "key": OPEN_FEEDBACK_KEY,
        "prompt": DEFAULT_OPEN_FEEDBACK,
        "label": "Anything else (voice/text)",
        "description": "Final open feedback before company card and thank-you.",
        "sort_order": 950,
    },
    {
        "key": "thank_you",
        "prompt": DEFAULT_THANK_YOU,
        "label": "Thank you",
        "description": "Closing thank-you message.",
        "sort_order": 960,
    },
    {
        "key": "company_card",
        "prompt": DEFAULT_COMPANY_CARD,
        "label": "Company card intro",
        "description": "Intro before representative contact details.",
        "sort_order": 970,
    },
    {
        "key": "post_complete_handoff",
        "prompt": POST_COMPLETE_HANDOFF,
        "label": "Post-complete handoff",
        "description": "Sent after thank-you on WhatsApp.",
        "sort_order": 980,
    },
]

SYSTEM_TEMPLATE_KEYS = frozenset(q["key"] for q in SYSTEM_SESSION_TEMPLATES)


def get_template_prompt(db: Any | None, key: str, fallback: str) -> str:
    """Resolve Admin-edited ExpoQuestionTemplate prompt; insert-missing seed owns defaults."""
    clean_key = str(key or "").strip()
    if not clean_key:
        return str(fallback or "").strip()
    if db is None:
        return with_topic_emoji(clean_key, str(fallback or "").strip())
    try:
        from sqlalchemy import select

        from app.models.expo import ExpoQuestionTemplate

        row = db.execute(
            select(ExpoQuestionTemplate).where(ExpoQuestionTemplate.question_key == clean_key)
        ).scalar_one_or_none()
        if row is not None and str(row.prompt or "").strip():
            return with_topic_emoji(clean_key, str(row.prompt).strip())
    except Exception:
        pass
    return with_topic_emoji(clean_key, str(fallback or "").strip())


def build_company_card_text(
    *,
    intro: str,
    company_name: str | None,
    website: str | None,
    reps: list[dict[str, Any]],
    logo_url: str | None = None,
) -> str:
    # logo_url kept for callers; WA no longer attaches a separate logo document.
    _ = logo_url
    name = str(company_name or "").strip() or "Our team"
    raw_intro = str(intro or DEFAULT_COMPANY_CARD).strip() or DEFAULT_COMPANY_CARD
    # Keep the heading plain (Admin may still have an old emoji-prefixed template).
    raw_intro = re.sub(r"^[📇🏢\s]+", "", raw_intro).strip() or DEFAULT_COMPANY_CARD

    lines = [
        raw_intro,
        f"Company: {name}",
    ]
    if website:
        lines.append(f"Website: {website}")

    if reps:
        for rep in reps[:5]:
            if not isinstance(rep, dict):
                continue
            rname = str(rep.get("name") or "").strip()
            email = str(rep.get("email") or "").strip()
            mobile = str(rep.get("mobile") or "").strip()
            tel = str(rep.get("telephone") or "").strip()
            if not rname and not email and not mobile and not tel:
                continue
            lines.append(f"Contacts: {rname or 'Contact'}")
            if email:
                lines.append(f"✉️ {email}")
            if mobile:
                lines.append(f"📱 {mobile}")
            if tel:
                lines.append(f"☎️ {tel}")
    else:
        lines.append("Contacts: —")

    lines.append("📇 We'll also send a contact card you can save to your phone")
    return "\n".join(lines).strip()


def parse_representative_contacts(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for item in data[:10]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name and not str(item.get("email") or "").strip():
            continue
        out.append(
            {
                "name": name[:128],
                "company_name": str(item.get("company_name") or "").strip()[:128],
                "email": str(item.get("email") or "").strip()[:255],
                "mobile": str(item.get("mobile") or "").strip()[:64],
                "telephone": str(item.get("telephone") or "").strip()[:64],
                "website": str(item.get("website") or "").strip()[:512],
            }
        )
    return out


def build_vcard(
    *,
    company_name: str,
    website: str | None,
    reps: list[dict[str, Any]],
) -> str:
    """Build a multi-contact vCard (VCARD 3.0) for Save to phone."""
    blocks: list[str] = []
    primary = reps[0] if reps else {}
    org = str(company_name or primary.get("company_name") or "Company").strip() or "Company"
    if not reps:
        lines = [
            "BEGIN:VCARD",
            "VERSION:3.0",
            f"FN:{org}",
            f"ORG:{org}",
        ]
        if website:
            lines.append(f"URL:{website}")
        lines.append("END:VCARD")
        return "\n".join(lines) + "\n"
    for rep in reps[:5]:
        name = str(rep.get("name") or org).strip() or org
        co = str(rep.get("company_name") or org).strip() or org
        email = str(rep.get("email") or "").strip()
        mobile = str(rep.get("mobile") or "").strip()
        tel = str(rep.get("telephone") or "").strip()
        url = str(rep.get("website") or website or "").strip()
        lines = [
            "BEGIN:VCARD",
            "VERSION:3.0",
            f"FN:{name}",
            f"ORG:{co}",
        ]
        if email:
            lines.append(f"EMAIL;TYPE=INTERNET:{email}")
        if mobile:
            lines.append(f"TEL;TYPE=CELL:{mobile}")
        if tel:
            lines.append(f"TEL;TYPE=WORK:{tel}")
        if url:
            lines.append(f"URL:{url}")
        lines.append("END:VCARD")
        blocks.append("\n".join(lines))
    return "\n".join(blocks) + "\n"


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
    "offer_interest": [
        {"value": "Yes", "label": "✅ Yes, interested"},
        {"value": "No", "label": "🙅 No thanks"},
    ],
    "budget": [
        {"value": "Under £1k", "label": "💵 Under £1k"},
        {"value": "£1k–£10k", "label": "💷 £1k–£10k"},
        {"value": "£10k–£50k", "label": "💶 £10k–£50k"},
        {"value": "£50k+", "label": "💰 £50k+"},
        {"value": "Not sure", "label": "🤷 Not sure yet"},
    ],
    "volume": [
        {"value": "Sample / 1–10", "label": "1️⃣ Sample / 1–10"},
        {"value": "11–100", "label": "🔟 11–100"},
        {"value": "100–1,000", "label": "📦 100–1,000"},
        {"value": "1,000+", "label": "🏭 1,000+"},
        {"value": "Not sure", "label": "🤷 Not sure yet"},
    ],
}

# Only free-text interest + final open feedback keep the mic; everything else is taps/numbers.
WEB_VOICE_KEYS = frozenset(
    {
        "interest",
        OPEN_FEEDBACK_KEY,
    }
)

# Multi-select on Expo web (visitor can pick several options).
WEB_MULTI_CHOICE_KEYS = frozenset({"follow_up"})

YES_WORDS = frozenset({"yes", "y", "yeah", "yep", "sure", "ok", "okay", "please", "affirmative"})
NO_WORDS = frozenset({"no", "n", "nope", "nah", "negative", "not interested", "no thanks"})

_EMOJI_DIGITS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]

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


def emoji_digit(n: int) -> str:
    if 1 <= n <= len(_EMOJI_DIGITS):
        return _EMOJI_DIGITS[n - 1]
    return f"{n}."


def looks_affirmative(text: str) -> bool:
    lower = str(text or "").strip().lower()
    if not lower:
        return False
    if lower in NO_WORDS:
        return False
    if lower in YES_WORDS:
        return True
    return lower.startswith("yes")


def parse_pick_numbers(text: str, *, option_count: int | None = None) -> list[int]:
    """Extract 1-based option numbers from replies like 1, 1. 1️⃣, 1) or 1,2.

    When ``option_count`` is set and a glued digit run like ``123`` is longer than that
    count (and every digit is a valid index), split into single digits so multi-select
    WhatsApp replies map correctly. ``10`` with ten options still parses as ten.
    """
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

    def _push(n: int) -> None:
        if n < 1 or n in seen:
            return
        seen.add(n)
        found.append(n)

    for match in re.finditer(r"\d+", normalized):
        token = match.group(0)
        try:
            n = int(token)
        except ValueError:
            continue
        max_n = int(option_count or 0)
        if (
            max_n > 0
            and len(token) > 1
            and (n > max_n or len(token) > len(str(max_n)))
            and all(1 <= int(ch) <= max_n for ch in token)
        ):
            for ch in token:
                _push(int(ch))
            continue
        _push(n)
    return found


def remap_choice_reply(
    text: str,
    options: list[dict[str, Any]],
    *,
    multi: bool = False,
) -> str:
    """Map a numbered WhatsApp reply to option value(s); pass text through otherwise."""
    raw = str(text or "").strip()
    if not raw or not options:
        return raw
    lower = raw.lower()
    for opt in options:
        value = str(opt.get("value") or "").strip()
        label = str(opt.get("label") or "").strip()
        if lower == value.lower() or (label and lower == label.lower()):
            return value or raw
    if multi and lower in {"all", "both", "everything", "all of them"}:
        values = [str(o.get("value") or "").strip() for o in options if str(o.get("value") or "").strip()]
        return ", ".join(values) if values else raw
    picks = parse_pick_numbers(raw, option_count=len(options))
    chosen: list[str] = []
    for n in picks:
        if 1 <= n <= len(options):
            value = str(options[n - 1].get("value") or "").strip()
            if value and value not in chosen:
                chosen.append(value)
    if not chosen:
        return raw
    return ", ".join(chosen) if multi or len(chosen) > 1 else chosen[0]


def format_numbered_prompt(
    prompt: str,
    labels: list[str],
    *,
    hint: str = "Reply with the number, e.g. 1",
) -> str:
    """Render a WhatsApp numbered menu under a prompt."""
    lines = [str(prompt or "").strip(), ""]
    for idx, label in enumerate(labels, start=1):
        lines.append(f"{emoji_digit(idx)} {label}")
    lines.append("")
    lines.append(hint)
    return "\n".join(line for line in lines if line is not None).strip()


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
    if key == CONTACT_STEP_KEY or sub in {"awaiting", "company", "mobile", "email", "confirm", "card_retry"}:
        out["question_key"] = CONTACT_STEP_KEY
        if sub == "confirm":
            out["input"] = "contact_confirm"
        elif sub in {"company", "mobile", "email"}:
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
                if str(r.question_key or "") in SYSTEM_TEMPLATE_KEYS and str(r.question_key) != OPEN_FEEDBACK_KEY:
                    continue
                rows.append(
                    {
                        "key": r.question_key,
                        "prompt": r.prompt,
                        "label": r.label,
                        "description": r.description or "",
                        "matches_products": bool(r.matches_products),
                        "id": r.id,
                        "is_system": str(r.question_key or "") in SYSTEM_TEMPLATE_KEYS,
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
    db: Any | None = None,
    include_open_feedback: bool = True,
) -> dict[str, Any]:
    keys = list(selected_question_keys) if selected_question_keys else list(_DEFAULT_SELECTED_KEYS)
    keys = [k for k in keys if k not in SYSTEM_TEMPLATE_KEYS or k == OPEN_FEEDBACK_KEY]
    if include_industry_addon and str(addon_question or "").strip() and "industry_addon" not in keys:
        # Place before consent when present
        if "consent_info" in keys:
            keys.insert(keys.index("consent_info"), "industry_addon")
        else:
            keys.append("industry_addon")
    if include_open_feedback and OPEN_FEEDBACK_KEY not in keys:
        keys.append(OPEN_FEEDBACK_KEY)

    def _prompt_for(key: str, fallback: str) -> str:
        return get_template_prompt(db, key, fallback)

    contact_wa = _prompt_for("contact", CONTACT_PROMPT_WA)
    contact_web = _prompt_for("contact_web", CONTACT_PROMPT_WEB)

    steps: list[dict[str, Any]] = [
        {
            "key": CONTACT_STEP_KEY,
            "kind": "contact",
            "prompt": contact_wa,
            "prompt_web": contact_web,
        }
    ]
    bank_by_key = dict(_BANK_BY_KEY)
    if db is not None:
        for row in list_selectable_questions(db):
            k = str(row.get("key") or "")
            if k and k not in bank_by_key:
                bank_by_key[k] = row
            elif k:
                bank_by_key[k] = {**bank_by_key.get(k, {}), **row}

    for key in keys:
        if key == CONTACT_STEP_KEY:
            continue
        if key == "industry_addon":
            prompt = str(addon_question or "").strip()
            if not prompt:
                continue
            steps.append({"key": key, "prompt": with_topic_emoji(key, prompt), "kind": "text", "label": "Industry question"})
            continue
        if key == OPEN_FEEDBACK_KEY:
            steps.append(
                {
                    "key": OPEN_FEEDBACK_KEY,
                    "prompt": _prompt_for(OPEN_FEEDBACK_KEY, DEFAULT_OPEN_FEEDBACK),
                    "kind": "text",
                    "label": "Anything else",
                }
            )
            continue
        bank = bank_by_key.get(key)
        if bank:
            steps.append(
                {
                    "key": str(bank.get("key") or key),
                    "prompt": _prompt_for(key, str(bank.get("prompt") or "")),
                    "kind": "text",
                    "label": str(bank.get("label") or key),
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
    steps[0]["prompt"] = contact_prompt_for_mode(mode, channel="whatsapp", db=db)
    steps[0]["prompt_web"] = contact_prompt_for_mode(mode, channel="web", db=db)
    thank = str(thank_you_message or "").strip() or _prompt_for("thank_you", DEFAULT_THANK_YOU)
    return {
        "steps": steps,
        "version": 3,
        "contact_capture": mode,
        "selected_question_keys": [s["key"] for s in steps if s["key"] != CONTACT_STEP_KEY],
        "thank_you_message": thank,
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
    for step in steps[:16]:
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


def parse_closing_config(raw: str | None, *, company_name: str | None = None, db: Any | None = None) -> dict[str, Any]:
    """Thank-you + optional free-gift settings stored alongside question steps."""
    fallback_gift = default_free_gift_text(company_name)
    fallback_thank = get_template_prompt(db, "thank_you", DEFAULT_THANK_YOU)
    if not raw:
        return {
            "thank_you_message": fallback_thank,
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
    thank = str(data.get("thank_you_message") or "").strip() or fallback_thank
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
