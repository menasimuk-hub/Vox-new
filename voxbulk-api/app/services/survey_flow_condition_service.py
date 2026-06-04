"""Evaluate deterministic branch conditions for WA Survey flow graph (P2)."""

from __future__ import annotations

import json
from typing import Any

from app.models.survey_session import SurveySessionAnswer


def _cast_value(raw: str, cast: str | None) -> Any:
    text = str(raw or "").strip()
    if not cast:
        return text
    key = str(cast).strip().lower()
    if key == "int":
        try:
            return int(float(text))
        except (TypeError, ValueError):
            return None
    if key == "float":
        try:
            return float(text)
        except (TypeError, ValueError):
            return None
    if key == "lower":
        return text.lower()
    return text


def _resolve_source(source: str, *, last_answer: SurveySessionAnswer | None, answers: list[SurveySessionAnswer]) -> Any:
    src = str(source or "").strip()
    if src == "last_answer.normalized_value":
        return last_answer.normalized_value if last_answer else None
    if src == "last_answer.raw_value":
        return last_answer.raw_value if last_answer else None
    if src == "last_answer.step_role":
        return last_answer.step_role if last_answer else None
    if src.startswith("answers_by_role."):
        role = src.split(".", 1)[1]
        for row in reversed(answers):
            if row.step_role == role:
                return row.normalized_value
        return None
    return None


def _compare(op: str, left: Any, right: Any) -> bool:
    if op == "eq":
        return left == right
    if op == "neq":
        return left != right
    if op == "in":
        if not isinstance(right, list):
            return False
        return left in right
    if left is None or right is None:
        return False
    try:
        if op == "lte":
            return left <= right
        if op == "lt":
            return left < right
        if op == "gte":
            return left >= right
        if op == "gt":
            return left > right
    except TypeError:
        return False
    return False


def evaluate_condition(
    condition: dict[str, Any] | None,
    *,
    last_answer: SurveySessionAnswer | None,
    answers: list[SurveySessionAnswer],
) -> bool:
    if not condition:
        return True
    op = str(condition.get("op") or "").strip().lower()
    if op == "always":
        return True
    if op in {"and", "or"}:
        parts = condition.get("conditions") or []
        if not isinstance(parts, list) or not parts:
            return False
        results = [
            evaluate_condition(p, last_answer=last_answer, answers=answers)
            for p in parts
            if isinstance(p, dict)
        ]
        if not results:
            return False
        return all(results) if op == "and" else any(results)
    source = str(condition.get("source") or "").strip()
    left = _resolve_source(source, last_answer=last_answer, answers=answers)
    cast = condition.get("cast")
    if cast:
        left = _cast_value(str(left) if left is not None else "", cast)
    right = condition.get("value")
    if cast and right is not None:
        right = _cast_value(str(right), cast)
    return _compare(op, left, right)


def parse_condition_json(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        return None
