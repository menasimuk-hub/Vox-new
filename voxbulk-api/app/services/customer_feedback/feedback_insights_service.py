"""LLM-generated themes and action recommendations for Customer Feedback results."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackResultsInsightsCache
from app.models.organisation import Organisation
from app.services.agents.base import AgentMessage
from app.services.providers.openai_service import OpenAIProviderService
from app.services.survey_action_recommendations import (
    _parse_recommendations_json,
    fallback_action_recommendations,
)

logger = logging.getLogger(__name__)

_THEMES_META = """You analyse anonymous customer feedback survey results from QR WhatsApp surveys.
Return ONLY valid JSON:
{"themes":[{"label":"Short theme title","sentiment":"positive"|"negative"|"mixed","weight":number}]}

Rules:
- Provide 3 to 5 themes ranked by weight (weights should sum to roughly 100)
- Base themes on question breakdowns and open comment excerpts only
- British English
- Do not mention individual phone numbers or names"""

_RECOMMENDATIONS_META = """You write practical business improvement recommendations from anonymous QR feedback results.
Return ONLY valid JSON:
{"recommendations":[{"title":"Short action headline","text":"One clear sentence.","impact":"High"|"Medium"|"Low"}]}

Rules:
- Provide 3 to 5 recommendations
- Base every item on the survey data provided
- Do NOT mention phone calls to individual customers by name — org staff will follow up separately
- British English"""


def _location_cache_key(location_id: str | None) -> str:
    return str(location_id or "").strip() or "__all__"


def _fingerprint(summary: dict[str, Any], aggregates: list[dict[str, Any]], comment_count: int) -> str:
    payload = {
        "completed": summary.get("completed_sessions"),
        "responses": summary.get("responses"),
        "comments": comment_count,
        "aggregates": aggregates[:8],
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _resolve_llm_provider(db: Session) -> str:
    from app.services.provider_settings import ProviderSettingsService

    for name in ("deepseek", "deepinfra", "openai"):
        cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider=name)
        if enabled and isinstance(cfg, dict) and str(cfg.get("api_key") or "").strip():
            return name
    return "deepseek"


def _complete_json(db: Session, *, system_prompt: str, user_block: str) -> str:
    provider = _resolve_llm_provider(db)
    try:
        result = OpenAIProviderService.complete(
            db,
            system_prompt=system_prompt,
            messages=[AgentMessage(role="user", content=user_block)],
            max_tokens=900,
            temperature=0.3,
            provider=provider,
        )
        return str(result.assistant_text or "")
    except Exception as exc:
        logger.warning("feedback_insights_llm_failed provider=%s err=%s", provider, str(exc)[:200])
        raise


def _parse_themes(raw: str) -> list[dict[str, Any]]:
    text = str(raw or "").strip()
    if not text:
        return []
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return []
        data = json.loads(text[start : end + 1])
    rows = data.get("themes") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or "").strip()
        if not label:
            continue
        weight = row.get("weight") or row.get("value") or 0
        try:
            value = int(round(float(weight)))
        except (TypeError, ValueError):
            value = 0
        sentiment = str(row.get("sentiment") or "mixed").strip().lower()
        if sentiment not in {"positive", "negative", "mixed"}:
            sentiment = "mixed"
        out.append({"label": label, "value": max(0, value), "sentiment": sentiment})
    total = sum(t["value"] for t in out) or 1
    for item in out:
        if item["value"] <= 0:
            item["value"] = max(1, round(100 / len(out)))
    if total > 0 and total != 100:
        for item in out:
            item["value"] = round(item["value"] / total * 100)
    return out[:5]


def _fallback_themes(aggregates: list[dict[str, Any]], open_comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    themes: list[dict[str, Any]] = []
    for block in aggregates[:3]:
        question = str(block.get("question") or "").strip()
        breakdown = block.get("breakdown") or []
        if not question or not breakdown:
            continue
        poor = next((g for g in breakdown if g.get("key") == "poor"), None)
        excellent = next((g for g in breakdown if g.get("key") == "excellent"), None)
        if poor and int(poor.get("pct") or 0) >= 20:
            themes.append({"label": f"{question[:40]} concerns", "value": int(poor.get("pct") or 20), "sentiment": "negative"})
        elif excellent and int(excellent.get("pct") or 0) >= 50:
            themes.append({"label": f"Strong {question[:30]}", "value": int(excellent.get("pct") or 50), "sentiment": "positive"})
    if not themes and open_comments:
        themes.append({"label": "Open feedback comments", "value": 100, "sentiment": "mixed"})
    return themes[:5]


def _generate_themes(
    db: Session,
    *,
    org_name: str,
    summary: dict[str, Any],
    aggregates: list[dict[str, Any]],
    open_comments: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    excerpts = [str(c.get("text") or "")[:200] for c in open_comments[:20] if c.get("text")]
    payload = {
        "organisation": org_name,
        "summary": summary,
        "questions": aggregates[:10],
        "open_comment_excerpts": excerpts,
    }
    try:
        raw = _complete_json(
            db,
            system_prompt=_THEMES_META,
            user_block=json.dumps(payload, ensure_ascii=False, indent=2),
        )
        parsed = _parse_themes(raw)
        if parsed:
            return parsed, _resolve_llm_provider(db)
    except Exception:
        pass
    return _fallback_themes(aggregates, open_comments), "fallback"


def _generate_recommendations(
    db: Session,
    *,
    org_name: str,
    summary: dict[str, Any],
    aggregates: list[dict[str, Any]],
    themes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    summary_for_fallback = {
        "completed_count": summary.get("completed_sessions"),
        "nps_label": "Unhappy" if int(summary.get("unhappy_count") or 0) >= 3 else "",
        "unhappy_count": summary.get("unhappy_count"),
    }
    payload = {
        "organisation": org_name,
        "summary": summary,
        "themes": themes,
        "questions_and_answers": aggregates,
        "unhappy_respondent_count": summary.get("unhappy_count"),
    }
    try:
        raw = _complete_json(
            db,
            system_prompt=_RECOMMENDATIONS_META,
            user_block=json.dumps(payload, ensure_ascii=False, indent=2),
        )
        parsed = _parse_recommendations_json(raw)
        if parsed:
            recs = [{"title": r["title"], "text": r["text"], "impact": "High"} for r in parsed[:5]]
            return recs, _resolve_llm_provider(db)
    except Exception:
        pass
    fallback = fallback_action_recommendations(summary=summary_for_fallback, aggregates=aggregates)
    return [{"title": r["title"], "text": r["text"], "impact": "Medium"} for r in fallback[:5]], "fallback"


class FeedbackInsightsService:
    @staticmethod
    def get_or_generate(
        db: Session,
        org_id: str,
        *,
        location_id: str | None,
        summary: dict[str, Any],
        aggregates: list[dict[str, Any]],
        open_comments: list[dict[str, Any]],
        force: bool = False,
    ) -> dict[str, Any]:
        completed = int(summary.get("completed_sessions") or 0)
        if completed < 3:
            return {
                "themes": [],
                "recommendations": [],
                "generated_at": None,
                "source": "insufficient_data",
            }

        fp = _fingerprint(summary, aggregates, len(open_comments))
        cache_key = _location_cache_key(location_id)
        cached = db.execute(
            select(FeedbackResultsInsightsCache).where(
                FeedbackResultsInsightsCache.org_id == org_id,
                FeedbackResultsInsightsCache.location_key == cache_key,
            )
        ).scalar_one_or_none()

        if cached and cached.fingerprint == fp and not force:
            try:
                themes = json.loads(cached.themes_json or "[]")
                recs = json.loads(cached.recommendations_json or "[]")
            except json.JSONDecodeError:
                themes, recs = [], []
            return {
                "themes": themes if isinstance(themes, list) else [],
                "recommendations": recs if isinstance(recs, list) else [],
                "generated_at": cached.updated_at.isoformat() if cached.updated_at else None,
                "source": cached.source or "cache",
            }

        org = db.get(Organisation, org_id)
        org_name = org.name if org else "Organisation"
        themes, theme_source = _generate_themes(
            db,
            org_name=org_name,
            summary=summary,
            aggregates=aggregates,
            open_comments=open_comments,
        )
        recs, rec_source = _generate_recommendations(
            db,
            org_name=org_name,
            summary=summary,
            aggregates=aggregates,
            themes=themes,
        )
        source = theme_source if theme_source == rec_source else f"{theme_source}+{rec_source}"
        if source.startswith("fallback"):
            source = "fallback"

        now = datetime.utcnow()
        if cached:
            cached.fingerprint = fp
            cached.themes_json = json.dumps(themes, ensure_ascii=False)
            cached.recommendations_json = json.dumps(recs, ensure_ascii=False)
            cached.source = source
            cached.updated_at = now
            db.add(cached)
        else:
            db.add(
                FeedbackResultsInsightsCache(
                    org_id=org_id,
                    location_key=cache_key,
                    fingerprint=fp,
                    themes_json=json.dumps(themes, ensure_ascii=False),
                    recommendations_json=json.dumps(recs, ensure_ascii=False),
                    source=source,
                    updated_at=now,
                    created_at=now,
                )
            )
        db.commit()

        return {
            "themes": themes,
            "recommendations": recs,
            "generated_at": now.isoformat(),
            "source": source,
        }
