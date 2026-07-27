"""Knowledge base for Apify / AI Team outbound reply drafts.

Injected into DeepSeek prompts so replies match real VoxBulk signup / trial rules
instead of inventing billing or “expired trial” explanations.
"""

from __future__ import annotations

from typing import Any

from app.services.expo.company_email import extract_email_domain, is_company_email, is_free_email_domain

DEFAULT_SIGNUP_URL = "https://voxbulk.com/signin?promo=EXPO3DAYS"
DEFAULT_PROMO_CODE = "EXPO3DAYS"

# Product truth for outreach replies (Expo / Apify campaigns).
PRODUCT_FACTS = """
## Product (VoxBulk Expo outreach)
- VoxBulk: B2B customer feedback (WhatsApp + voice) for events / expo teams.
- Outreach offer: free 3-day Expo trial with promo code (default EXPO3DAYS) — no card when eligible.
- Signup: https://voxbulk.com/signin?promo=EXPO3DAYS (or the campaign’s trial/signup link).
- The free trial is granted only when the customer registers with a company / work email.
- Free personal mailboxes (Gmail, Outlook.com, Hotmail, Yahoo, iCloud, Proton, etc.) do NOT get the silent Expo trial.
- If they sign up with Gmail/Yahoo/etc., the product correctly asks them to pay / choose a paid plan — that is not a bug and not an “expired trial”.
- One free Expo trial per company email domain (first company that claims the domain).
- Do NOT invent pricing, SLAs, contracts, or “your trial expired”. Prefer short clear steps.
""".strip()

PLAYBOOKS: dict[str, dict[str, Any]] = {
    "free_personal_email": {
        "title": "Free / personal email (Gmail, Outlook, Yahoo, …)",
        "when": "From-address is a free consumer domain, OR they say they signed up with Gmail/personal email and see paywall / can’t access offer.",
        "must_do": [
            "Explain politely that the free Expo trial needs a company / work email (not Gmail/Hotmail/Yahoo/iCloud).",
            "Tell them to register again with their work email (e.g. name@theircompany.com).",
            "Give the signup link with promo code.",
            "Do NOT say their trial expired, account is locked for payment failure, or that they must pay first to unlock the offer.",
            "Do NOT ask them for “which email they signed up with” as the main next step if we already know they wrote from Gmail — lead with the company-email fix.",
        ],
        "sample_angle": (
            "Thanks for trying — the free Expo trial only activates on a company email. "
            "Please sign up again with your work email (not Gmail), using the promo link, and you’ll get the 3 free days with no card."
        ),
    },
    "paywall_or_cant_see_offer": {
        "title": "Sees payment / can’t see free offer",
        "when": "Message mentions pay, payment, upgrade, buy, price wall, can’t see offer, no free trial, forced checkout.",
        "must_do": [
            "Most common cause for outreach leads: they used a free personal email → advise company email re-registration.",
            "Second cause: their company domain already used the one free Expo trial → explain one trial per company domain; offer a short call / alternative help.",
            "Third: wrong/missing promo link → resend signup URL with EXPO3DAYS (or campaign promo).",
            "Never invent that their trial “expired” unless they clearly had a company-email trial that ended.",
        ],
    },
    "cant_login": {
        "title": "Can’t log in",
        "when": "Message mentions login, sign in, password, access denied, can’t enter account.",
        "must_do": [
            "If From is free email: treat as free_personal_email first (wrong account type for the offer).",
            "Otherwise: ask them to confirm they use the same work email they registered with; suggest password reset on the sign-in page.",
            "Offer to help once they confirm the work email used at signup.",
        ],
    },
    "wants_demo_or_info": {
        "title": "Interested / wants demo or more info",
        "when": "Positive interest, questions about product, asking for a call or overview.",
        "must_do": [
            "Thank them, give a one-line what VoxBulk does, offer the free trial link (company email) or a short call.",
            "Keep it short; one clear next step.",
        ],
    },
    "unsubscribe_or_stop": {
        "title": "Unsubscribe / stop emailing",
        "when": "Stop, unsubscribe, remove me, not interested.",
        "must_do": [
            "Acknowledge politely, confirm they will not be emailed again, no sales pitch.",
        ],
    },
    "general": {
        "title": "General reply",
        "when": "No stronger playbook matched.",
        "must_do": [
            "Acknowledge their message, answer helpfully, one simple next step.",
            "If unsure about billing/trial eligibility, ask one clarifying question — prefer company vs personal email if pay/access is involved.",
        ],
    },
}


def _norm(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def detect_issue_tags(*, from_email: str, inbound_subject: str = "", inbound_body: str = "") -> list[str]:
    """Return ordered playbook tags (most specific first)."""
    blob = _norm(f"{inbound_subject}\n{inbound_body}")
    tags: list[str] = []

    free_from = bool(from_email) and not is_company_email(from_email)
    mentions_free_mail = any(
        w in blob
        for w in (
            "gmail",
            "googlemail",
            "hotmail",
            "outlook.com",
            "yahoo",
            "icloud",
            "personal email",
            "personal mail",
            "free email",
        )
    )
    paywall = any(
        w in blob
        for w in (
            "pay",
            "payment",
            "upgrade",
            "subscribe",
            "pricing",
            "price",
            "buy",
            "checkout",
            "credit card",
            "card required",
            "have to pay",
            "must pay",
            "can't see offer",
            "cant see offer",
            "cannot see offer",
            "no free",
            "not free",
            "offer",
            "trial",
        )
    )
    login = any(
        w in blob
        for w in (
            "login",
            "log in",
            "sign in",
            "signin",
            "password",
            "can't access",
            "cant access",
            "cannot access",
            "can't login",
            "cant login",
            "unable to login",
            "unable to log in",
        )
    )
    stop = any(
        w in blob
        for w in ("unsubscribe", "stop email", "stop mailing", "remove me", "not interested", "do not contact")
    )
    interest = any(
        w in blob
        for w in ("demo", "call", "meeting", "interested", "tell me more", "how does", "pricing?")
    )

    if free_from or mentions_free_mail:
        tags.append("free_personal_email")
    if paywall:
        tags.append("paywall_or_cant_see_offer")
    if login:
        tags.append("cant_login")
    if stop:
        tags.append("unsubscribe_or_stop")
    if interest and "unsubscribe_or_stop" not in tags:
        tags.append("wants_demo_or_info")
    if not tags:
        tags.append("general")

    # Dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        if t not in seen and t in PLAYBOOKS:
            seen.add(t)
            out.append(t)
    return out


def build_reply_kb_context(
    *,
    from_email: str,
    inbound_subject: str = "",
    inbound_body: str = "",
    promo_code: str | None = None,
    signup_url: str | None = None,
) -> dict[str, Any]:
    """Build prompt context + matched playbooks for generate_reply_draft."""
    code = (promo_code or DEFAULT_PROMO_CODE).strip() or DEFAULT_PROMO_CODE
    url = (signup_url or "").strip() or f"https://voxbulk.com/signin?promo={code}"
    domain = extract_email_domain(from_email)
    free_from = bool(from_email) and is_free_email_domain(domain)
    tags = detect_issue_tags(
        from_email=from_email,
        inbound_subject=inbound_subject,
        inbound_body=inbound_body,
    )

    lines: list[str] = [
        PRODUCT_FACTS,
        "",
        f"## This conversation",
        f"- Customer From email: {from_email or '(unknown)'}",
        f"- Email domain: {domain or '(unknown)'}",
        f"- From is free/personal mailbox: {'YES — treat as free_personal_email' if free_from else 'No (looks like company email)'}",
        f"- Promo code to share: {code}",
        f"- Signup / trial URL to share: {url}",
        "",
        "## Matched playbooks (follow these in order — do not invent other root causes)",
    ]
    for tag in tags:
        pb = PLAYBOOKS[tag]
        lines.append(f"### {pb['title']} (`{tag}`)")
        lines.append(f"When: {pb['when']}")
        lines.append("Must do:")
        for step in pb["must_do"]:
            lines.append(f"- {step}")
        sample = pb.get("sample_angle")
        if sample:
            lines.append(f"Sample angle: {sample}")
        lines.append("")

    lines.extend(
        [
            "## Hard rules",
            "- If From is a free/personal email AND they mention pay / login / offer / trial: "
            "the correct advice is company/work email registration — not expired trial, not “send me your signup email first” as the only help.",
            "- Never claim their free trial expired unless they clearly had a company-email trial that ended.",
            "- Never invent prices or that they must pay to unlock the Expo outreach offer.",
            "- Keep the reply short (under ~180 words), plain text, polite.",
            "- End with the signature provided by the system (do not invent a different name).",
        ]
    )

    return {
        "tags": tags,
        "from_is_free_email": free_from,
        "domain": domain,
        "promo_code": code,
        "signup_url": url,
        "prompt_block": "\n".join(lines).strip(),
    }
