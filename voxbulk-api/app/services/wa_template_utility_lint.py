"""Meta WhatsApp UTILITY template compliance lint (English + Arabic)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

_UTILITY_CONTEXT_PHRASES = (
    "recent visit",
    "recent interaction",
    "recent experience",
    "recent service",
    "recent engagement",
    "recent order",
    "recent transaction",
    "recent appointment",
    "recent stay",
    "recent delivery",
    "following your",
    "after your recent",
    "during your visit today",
    "during your visit",
    "for today's visit",
    "today's visit",
    "your visit today",
    "your order today",
    "your stay with us",
    "your recent",
    "during your appointment",
    "after your appointment",
    "after dining with us",
    "after shopping with us",
    "thank you for dining",
    "thank you for shopping",
    "thank you for visiting",
    "your interview",
    "your booking",
    "your booked slot",
    "interview for",
    "application for",
    "check your inbox",
    "position at",
)

# English promotional / marketing signals (Meta auto-reclassifies as MARKETING)
_EN_FORBIDDEN_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bsale\b", "promotional keyword: sale"),
    (r"\bdiscount", "promotional keyword: discount"),
    (r"\boffer\b", "promotional keyword: offer"),
    (r"\bgift\b", "promotional keyword: gift"),
    (r"\breward", "promotional keyword: reward"),
    (r"\bpromotion", "promotional keyword: promotion"),
    (r"\bnew\b", "promotional keyword: new"),
    (r"\bloyalty\b", "loyalty programme language"),
    (r"\brecommend\b.*\bfriend", "refer-a-friend wording"),
    (r"\brecommend\b.*\bfamily", "refer-a-friend wording"),
    (r"\brefer a friend\b", "refer-a-friend wording"),
    (r"\bjoin the club\b", "marketing CTA"),
    (r"\bshop now\b", "marketing CTA"),
    (r"\bsee deals\b", "marketing CTA"),
    (r"\bwe would love to see you again\b", "return-intent marketing tone"),
    (r"\bvisit us again\b", "return-intent marketing tone"),
    (r"\bstay with us again\b", "return-intent marketing tone"),
    (r"\bchoose us again\b", "return-intent marketing tone"),
    (r"\bdine with us again\b", "return-intent marketing tone"),
    (r"\bwould you recommend\b", "recommend-to-others survey"),
    (r"\breferral likelihood\b", "referral survey"),
    (r"\brenewal intent\b", "renewal intent survey"),
    (r"\breturn intent\b", "return intent survey"),
    (r"\brepeat purchase intent\b", "repeat purchase intent"),
    (r"\brepeat use intent\b", "repeat use intent"),
    (r"\bwe hope you enjoyed\b", "vague brand survey without transaction anchor"),
    (r"\bwe hope you left feeling great\b", "vague brand survey"),
    (r"\bwe hope you had a great\b", "vague brand survey"),
    (r"https?://", "URL / link in body"),
    (r"\bfacebook\b|\binstagram\b|\btwitter\b|\btiktok\b", "social media reference"),
)

# Arabic marketing signals
_AR_FORBIDDEN_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"خصم", "Arabic: discount"),
    (r"عرض", "Arabic: offer/promotion"),
    (r"عروض", "Arabic: promotions"),
    (r"هدية", "Arabic: gift"),
    (r"مكاف", "Arabic: reward"),
    (r"ترويج", "Arabic: promotion"),
    (r"ولاء", "Arabic: loyalty"),
    (r"برنامج\s+ولاء", "Arabic: loyalty programme"),
    (r"توص", "Arabic: recommend (partial)"),
    (r"صديق", "Arabic: friend (referral context risk)"),
    (r"انضم", "Arabic: join (CTA risk)"),
    (r"تسوق\s+الآن", "Arabic: shop now"),
    (r"http", "URL in body"),
)

_ALLOWED_CATEGORIES = frozenset({"utility", "UTILITY"})


@dataclass
class UtilityLintIssue:
    code: str
    message: str
    field: str = "body"


@dataclass
class UtilityLintResult:
    ok: bool
    issues: list[UtilityLintIssue] = field(default_factory=list)

    def add(self, code: str, message: str, *, field: str = "body") -> None:
        self.issues.append(UtilityLintIssue(code=code, message=message, field=field))
        self.ok = False


def _normalize_lang(language: str | None) -> str:
    raw = str(language or "en").strip().lower().replace("-", "_")
    if raw in {"ar", "arabic"}:
        return "ar"
    return "en"


def _mentions_recent_interaction(text: str) -> bool:
    lower = str(text or "").lower()
    return any(phrase in lower for phrase in _UTILITY_CONTEXT_PHRASES)


def _check_patterns(text: str, patterns: Iterable[tuple[str, str]], result: UtilityLintResult, *, field: str) -> None:
    for pattern, label in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE | re.UNICODE):
            result.add("forbidden_pattern", label, field=field)


def lint_utility_body(
    body: str,
    *,
    language: str | None = None,
    require_transaction_anchor: bool = True,
    allow_variables: bool = False,
) -> UtilityLintResult:
    result = UtilityLintResult(ok=True)
    text = str(body or "").strip()
    if not text:
        result.add("empty_body", "BODY text is empty")
        return result

    lang = _normalize_lang(language)
    patterns = _AR_FORBIDDEN_PATTERNS if lang == "ar" else _EN_FORBIDDEN_PATTERNS
    _check_patterns(text, patterns, result, field="body")

    if require_transaction_anchor and lang == "en" and not _mentions_recent_interaction(text):
        result.add("missing_transaction_anchor", "BODY must tie to a specific recent transaction or visit")

    if not allow_variables and "{{" in text:
        result.add("variables_in_body", "Utility feedback templates should not use {{1}} variables in BODY")

    return result


def lint_utility_buttons(buttons: list[str], *, language: str | None = None) -> UtilityLintResult:
    result = UtilityLintResult(ok=True)
    lang = _normalize_lang(language)
    patterns = _AR_FORBIDDEN_PATTERNS if lang == "ar" else _EN_FORBIDDEN_PATTERNS
    marketing_ctas = (
        (r"\bshop now\b", "marketing CTA on button"),
        (r"\bsee deals\b", "marketing CTA on button"),
        (r"\bjoin\b", "marketing CTA on button"),
    )
    all_patterns = list(patterns) + list(marketing_ctas)
    for idx, label in enumerate(buttons or []):
        text = str(label or "").strip()
        if not text:
            result.add("empty_button", f"Button {idx + 1} is empty", field=f"button_{idx + 1}")
            continue
        if len(text) > 20:
            result.add("button_too_long", f"Button {idx + 1} exceeds 20 characters", field=f"button_{idx + 1}")
        _check_patterns(text, all_patterns, result, field=f"button_{idx + 1}")
    return result


def lint_utility_template(
    *,
    body: str,
    buttons: list[str] | None = None,
    language: str | None = None,
    meta_category: str | None = None,
    template_key: str | None = None,
    require_transaction_anchor: bool = True,
    allow_variables: bool = False,
) -> UtilityLintResult:
    """Lint BODY, buttons, and category for Meta UTILITY compliance."""
    if template_key and str(template_key).strip().lower() == "marketing_opt_in":
        return UtilityLintResult(ok=True)

    merged = UtilityLintResult(ok=True)
    for part in (
        lint_utility_body(
            body,
            language=language,
            require_transaction_anchor=require_transaction_anchor,
            allow_variables=allow_variables,
        ),
        lint_utility_buttons(list(buttons or []), language=language),
    ):
        if not part.ok:
            merged.ok = False
            merged.issues.extend(part.issues)

    cat = str(meta_category or "utility").strip().lower()
    if cat and cat not in _ALLOWED_CATEGORIES:
        merged.add("wrong_category", f"meta_category must be utility, got {meta_category!r}", field="category")

    return merged


def assert_utility_template(**kwargs: Any) -> UtilityLintResult:
    """Lint and raise ValueError if not compliant (for push gates)."""
    result = lint_utility_template(**kwargs)
    if not result.ok:
        msgs = "; ".join(f"{issue.field}: {issue.message}" for issue in result.issues)
        raise ValueError(f"Utility lint failed: {msgs}")
    return result


def merge_lint_results(*results: UtilityLintResult) -> UtilityLintResult:
    merged = UtilityLintResult(ok=True)
    for result in results:
        if not result.ok:
            merged.ok = False
            merged.issues.extend(result.issues)
    return merged
