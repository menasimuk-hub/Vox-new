"""Expo question bank + hybrid product match helpers."""

from __future__ import annotations

import json
import re
from typing import Any

from app.services.expo.seed_service import UNIVERSAL_QUESTIONS


def default_question_config(*, include_industry_addon: bool = False, addon_question: str | None = None) -> dict[str, Any]:
    steps = [{"key": q["key"], "prompt": q["prompt"], "kind": "text"} for q in UNIVERSAL_QUESTIONS]
    if include_industry_addon and str(addon_question or "").strip():
        # Insert before consent so interest matching still has context
        consent = steps.pop()
        steps.append({"key": "industry_addon", "prompt": str(addon_question).strip(), "kind": "text"})
        steps.append(consent)
    return {"steps": steps, "version": 1}


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
    for step in steps[:5]:
        if not isinstance(step, dict):
            continue
        key = str(step.get("key") or "").strip()
        prompt = str(step.get("prompt") or "").strip()
        if key and prompt:
            out.append({"key": key, "prompt": prompt, "kind": str(step.get("kind") or "text")})
    return out or list(default_question_config()["steps"])


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
    # Vague / weak: prefer defaults then full list
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
