"""Code-written Utility WA template content: emoji + buttons + neutral wording."""

from __future__ import annotations

import json
import re
from typing import Any

# Leading emoji required on every Utility template body.
DEFAULT_EMOJI = "📋"
RATING_BUTTONS = ["Excellent", "Good", "Poor"]
YES_NO_BUTTONS = ["Yes", "No"]
THANKS_BUTTONS = ["Done"]

PROMO_WORDS = re.compile(
    r"\b(sale|discount|offer|gift|reward|promotion|promo|loyalty|deal|shop now|see deals|"
    r"join the club|refer a friend|free trial|upgrade|upsell)\b",
    re.I,
)


def has_leading_emoji(text: str | None) -> bool:
    body = str(text or "").strip()
    if not body:
        return False
    # First non-space char is outside BMP basic latin / common punctuation → treat as emoji/symbol.
    ch = body[0]
    return ord(ch) > 127 or ch in {"✅", "📋", "⭐", "🙏", "💬", "📝", "👍", "👋", "🔔"}


def ensure_leading_emoji(text: str | None, *, emoji: str = DEFAULT_EMOJI) -> str:
    body = str(text or "").strip()
    if not body:
        return f"{emoji} How was your recent visit with us?"
    if has_leading_emoji(body):
        return body
    return f"{emoji} {body}"


def extract_buttons_from_components(components: list[dict[str, Any]] | None) -> list[str]:
    labels: list[str] = []
    for comp in components or []:
        if not isinstance(comp, dict):
            continue
        if str(comp.get("type") or "").upper() != "BUTTONS":
            continue
        for btn in comp.get("buttons") or []:
            if not isinstance(btn, dict):
                continue
            if str(btn.get("type") or "").upper() not in {"QUICK_REPLY", "QUICK-REPLY", ""}:
                # Prefer quick reply; still accept label if present.
                pass
            label = str(btn.get("text") or btn.get("title") or "").strip()
            if label:
                labels.append(label[:25])
    return labels


def default_buttons_for_key(template_key: str | None, *, name: str | None = None) -> list[str]:
    key = str(template_key or name or "").strip().lower()
    if any(token in key for token in ("thank", "done", "confirm_book", "booked")):
        return list(THANKS_BUTTONS)
    if any(token in key for token in ("recommend", "would_", "return_intent", "yes_no", "opt_in")):
        return list(YES_NO_BUTTONS)
    return list(RATING_BUTTONS)


def utility_body_for_topic(topic_name: str | None, *, emoji: str = DEFAULT_EMOJI) -> str:
    topic = str(topic_name or "your recent visit").strip() or "your recent visit"
    # Neutral, event-tied Utility wording (Meta guidelines).
    return f"{emoji} How was {topic.lower()} for your recent visit with us? Reply with one option below."


def is_promo_wording(text: str | None) -> bool:
    return bool(PROMO_WORDS.search(str(text or "")))


def build_utility_components(
    *,
    body: str,
    buttons: list[str],
    example_values: list[str] | None = None,
) -> list[dict[str, Any]]:
    body_text = ensure_leading_emoji(body)
    # Meta requires examples when body has {{n}} variables.
    vars_in_body = re.findall(r"\{\{(\d+)\}\}", body_text)
    examples = list(example_values or [])
    if vars_in_body and not examples:
        examples = ["your recent visit" for _ in vars_in_body]
    body_comp: dict[str, Any] = {"type": "BODY", "text": body_text}
    if examples:
        body_comp["example"] = {"body_text": [examples]}
    comps: list[dict[str, Any]] = [body_comp]
    labels = [str(b).strip()[:25] for b in buttons if str(b).strip()]
    if not labels:
        labels = list(RATING_BUTTONS)
    comps.append(
        {
            "type": "BUTTONS",
            "buttons": [{"type": "QUICK_REPLY", "text": label} for label in labels[:3]],
        }
    )
    return comps


def components_have_buttons(components: list[dict[str, Any]] | None) -> bool:
    return bool(extract_buttons_from_components(components))


def parse_components_json(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []
