from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.services.agents.base import AgentMessage
from app.services.providers.openai_service import OpenAIProviderService

logger = logging.getLogger(__name__)

_SURVEY_ACTIONS_META = """You write practical business improvement recommendations from anonymous survey results.
Return ONLY valid JSON:
{"recommendations":[{"title":"Short action headline","text":"One clear sentence explaining what to improve and why, based on the survey data."}]}

Rules:
- Provide 3 to 5 recommendations
- Each title is an action the business can take (examples: "Improve phone support", "Add more appointment slots", "Fix online booking flow")
- Base every item on the survey questions, answer breakdown, satisfaction score, or recurring themes
- Do NOT mention phone calls, transcripts, recordings, or individual respondents
- Do NOT describe the survey process — only business improvements suggested by the findings
"""


def _parse_recommendations_json(raw: str) -> list[dict[str, str]]:
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
    rows = data.get("recommendations") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return []
    out: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or row.get("headline") or "").strip()
        body = str(row.get("text") or row.get("detail") or row.get("description") or "").strip()
        if title and body:
            out.append({"title": title, "text": body})
        elif body:
            out.append({"title": body.split(".")[0][:80], "text": body})
    return out[:5]


def fallback_action_recommendations(
    *,
    summary: dict[str, Any],
    aggregates: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Deterministic business actions from aggregated answers when AI is unavailable."""
    recs: list[dict[str, str]] = []
    completed = max(1, int(summary.get("completed_count") or 1))

    if summary.get("nps_label") == "Unhappy":
        recs.append(
            {
                "title": "Improve overall customer experience",
                "text": "Overall satisfaction is below target — review service quality across booking, visits, and follow-up.",
            }
        )

    for block in aggregates:
        question = str(block.get("question") or "").strip()
        responses = block.get("responses") or []
        if not question or not responses:
            continue
        total = max(1, int(block.get("total") or 1))
        q_lower = question.lower()

        if any(k in q_lower for k in ("improve", "better", "change", "could we")):
            for row in responses:
                answer = str(row.get("answer") or "").strip()
                count = int(row.get("count") or 0)
                if not answer or count <= 0:
                    continue
                if answer.lower() in {"nothing", "none", "n/a", "no", "na"}:
                    continue
                pct = round((count / total) * 100)
                recs.append(
                    {
                        "title": f"Improve {answer.lower()}",
                        "text": f"{pct}% of responses ({count} people) asked for better {answer.lower()}.",
                    }
                )
                break

        if "wait" in q_lower:
            for row in responses:
                answer = str(row.get("answer") or "").lower()
                count = int(row.get("count") or 0)
                if count <= 0:
                    continue
                if any(w in answer for w in ("long", "slow", "too long", "poor")):
                    pct = round((count / total) * 100)
                    recs.append(
                        {
                            "title": "Reduce wait times",
                            "text": f"{pct}% of respondents ({count}) reported wait times as {row.get('answer')}.",
                        }
                    )
                    break

        if any(k in q_lower for k in ("recommend", "likely")):
            low = [r for r in responses if str(r.get("answer") or "").isdigit() and int(r["answer"]) <= 6]
            low_count = sum(int(r.get("count") or 0) for r in low)
            if low_count >= max(2, completed // 4):
                recs.append(
                    {
                        "title": "Strengthen customer loyalty",
                        "text": f"{low_count} respondents gave low recommendation scores — focus on the issues driving dissatisfaction.",
                    }
                )

    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for rec in recs:
        key = rec["title"].lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(rec)

    if not deduped and completed:
        deduped.append(
            {
                "title": "Review survey themes with your team",
                "text": "Use the answer summary below to agree priority improvements for your service.",
            }
        )
    return deduped[:5]


def generate_ai_action_recommendations(
    db: Session,
    *,
    goal: str,
    org_name: str,
    summary: dict[str, Any],
    aggregates: list[dict[str, Any]],
    negative_feedback: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    if int(summary.get("completed_count") or 0) <= 0:
        return []

    payload = {
        "organisation": org_name or "Unknown",
        "survey_goal": goal or "Customer feedback",
        "completed_responses": summary.get("completed_count"),
        "response_rate_pct": summary.get("response_rate_pct"),
        "satisfaction_out_of_5": summary.get("average_satisfaction_5"),
        "loyalty_score_out_of_100": summary.get("nps_score"),
        "loyalty_label": summary.get("nps_label"),
        "sentiment": summary.get("sentiment_counts"),
        "top_themes": summary.get("top_issues"),
        "questions_and_answers": aggregates,
        "negative_feedback_excerpts": negative_feedback or [],
        "unhappy_respondent_count": summary.get("unhappy_count"),
    }
    user_block = json.dumps(payload, ensure_ascii=False, indent=2)

    try:
        result = OpenAIProviderService.complete(
            db,
            system_prompt=_SURVEY_ACTIONS_META,
            messages=[AgentMessage(role="user", content=user_block)],
            max_tokens=900,
            temperature=0.3,
            provider="deepseek",
        )
        parsed = _parse_recommendations_json(str(result.assistant_text or ""))
        if parsed:
            return parsed
    except Exception as exc:
        logger.warning("survey_action_recommendations_ai_failed: %s", str(exc)[:300])

    return fallback_action_recommendations(summary=summary, aggregates=aggregates)
