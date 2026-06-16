"""Arabic-first clarification prompts for ambiguous voice interpretation."""

from __future__ import annotations


def category_clarification(categories: list[str], *, lang: str = "ar") -> str:
    if lang == "en":
        if "chicken" in categories and "fish" in categories:
            return "Did you mean chicken or fish?"
        return "Could you clarify what you'd like?"
    if "chicken" in categories and "fish" in categories:
        return "تقصد دجاج ولا سمك؟"
    if "drinks" in categories and len(categories) > 1:
        return "تقصد مشروبات ولا أكلة؟"
    return "ممكن توضّح شو بدك بالضبط؟"


def item_clarification(name_a: str, name_b: str, *, lang: str = "ar") -> str:
    if lang == "en":
        return f"Did you mean {name_a} or {name_b}?"
    return f"تقصد {name_a} ولا {name_b}؟"


def allergy_clarification(allergen_hint: str | None = None, *, lang: str = "ar") -> str:
    if lang == "en":
        if allergen_hint:
            return f"Do you have an allergy to {allergen_hint}?"
        return "Do you have any food allergies I should know about?"
    if allergen_hint:
        return f"هل عندك حساسية من {allergen_hint}؟"
    return "هل عندك حساسية من أي مكوّن؟"
