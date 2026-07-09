"""Canonical WAS naming for WA Survey WhatsApp templates."""

from __future__ import annotations

import re

META_NAME_MAX = 128
_EMPLOYEE_SLUG = "employee_survey"


def topic_slug(name: str, *, max_len: int = 48) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(name or "").strip().lower())
    return s.strip("_")[:max_len] or "topic"


def industry_was_prefix(industry_slug: str) -> str:
    slug = str(industry_slug or "").strip().lower()
    if slug == _EMPLOYEE_SLUG:
        return "employee"
    return slug


def _lang_suffix(language: str | None) -> str:
    lang = str(language or "en_GB").strip().lower().replace("-", "_")
    if lang.startswith("ar"):
        return "ar"
    return "en"


def _fit_name(prefix: str, topic: str, seq: int, lang: str) -> str:
    suffix = f"_{seq:03d}_{lang}"
    budget = META_NAME_MAX - len(prefix) - len(suffix)
    topic_part = topic_slug(topic, max_len=max(budget, 8))
    return f"{prefix}{topic_part}{suffix}"[:META_NAME_MAX]


def was_industry_topic_name(
    industry_slug: str,
    topic_name: str,
    *,
    seq: int = 1,
    language: str | None = None,
) -> str:
    prefix = f"was_{industry_was_prefix(industry_slug)}_"
    lang = _lang_suffix(language)
    return _fit_name(prefix, topic_name, seq, lang)


def was_system_template_name(
    kind: str,
    *,
    privacy_mode: str | None = None,
    seq: int = 1,
    language: str | None = None,
) -> str:
    from app.services.wa_template_privacy import PRIVACY_MODE_ON, normalize_privacy_mode

    kind = str(kind or "").strip().lower()
    lang = _lang_suffix(language)
    if kind == "welcome":
        variant = "anonymous" if normalize_privacy_mode(privacy_mode) == PRIVACY_MODE_ON else "named"
        topic = f"welcome_{variant}"
    elif kind == "final_feedback":
        topic = "closing"
    elif kind in ("thank_you", "tell_us_more"):
        topic = kind
    else:
        topic = topic_slug(kind)
    prefix = "was_system_"
    return _fit_name(prefix, topic, seq, lang)


def lang_suffix(language: str | None) -> str:
    return _lang_suffix(language)


def is_was_survey_name(name: str | None) -> bool:
    return str(name or "").strip().lower().startswith("was_")


_WAS_SEQ_SUFFIX_RE = re.compile(r"^(.+_)(\d{3})_(en|ar)$", re.I)


def suggest_next_was_seq_name(
    current_name: str,
    *,
    used_names: set[str] | None = None,
) -> str | None:
    """Bump was_* _00N_en|ar to the next free sequence (e.g. _002_ -> _003_)."""
    base = str(current_name or "").strip().lower()
    if not base.startswith("was_"):
        return None
    match = _WAS_SEQ_SUFFIX_RE.match(base)
    if not match:
        return None
    prefix, seq, lang = match.group(1), int(match.group(2)), match.group(3)
    used = {str(n or "").strip().lower() for n in (used_names or set()) if str(n or "").strip()}
    for next_seq in range(seq + 1, 100):
        candidate = f"{prefix}{next_seq:03d}_{lang}"
        if candidate.lower() not in used:
            return candidate
    return None
