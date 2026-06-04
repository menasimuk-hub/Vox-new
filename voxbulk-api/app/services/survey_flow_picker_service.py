"""Constrained AI picker for WA Survey graph branching (P4)."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from sqlalchemy.orm import Session

from app.models.survey_session import SurveySession, SurveySessionAnswer
from app.models.survey_type import SurveyType
from app.services.providers.openai_service import OpenAIProviderService
from app.services.survey_flow_condition_service import evaluate_condition
from app.services.survey_flow_constants import (
    DECISION_BRANCH_PICKER_INVOKE,
    DECISION_BRANCH_PICKER_RESULT,
    MAX_PICKER_INVOCATIONS_PER_SESSION,
    NODE_TYPE_OUTCOME,
    NODE_TYPE_QUESTION,
    PICKER_AI_ASSISTED,
    PICKER_DETERMINISTIC,
    RULE_AI_PICKER_CHOSEN,
    RULE_AI_PICKER_FALLBACK,
    RULE_AI_PICKER_REQUEST,
    RULE_AI_PICKER_SKIPPED,
    RULE_BRANCH_DEFAULT,
)
from app.services.survey_picker_settings_service import SurveyPickerSettingsService
from app.services.survey_session_service import SurveySessionService
from app.services.survey_step_bank_service import load_step_bank, normalize_step_role

logger = logging.getLogger(__name__)

PICKER_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "chosen_node_key": {"type": "string"},
        "confidence": {"type": "number"},
        "rationale": {"type": "string"},
    },
    "required": ["chosen_node_key", "confidence", "rationale"],
    "additionalProperties": False,
}


def _candidate_descriptor(
    *,
    edge: dict[str, Any],
    node: dict[str, Any] | None,
) -> dict[str, Any]:
    to_key = str(edge.get("to_node_key") or "")
    ntype = str((node or {}).get("node_type") or "")
    if ntype == NODE_TYPE_OUTCOME:
        kind = "outcome"
        step_role = str((node or {}).get("outcome_key") or "")
    else:
        kind = "question"
        step_role = str((node or {}).get("step_role") or to_key)
    return {
        "node_key": to_key,
        "step_role": step_role,
        "kind": kind,
        "edge_rule_key": str(edge.get("rule_key") or RULE_BRANCH_DEFAULT),
        "priority": int(edge.get("priority") or 100),
        "has_condition": edge.get("condition_json") is not None,
    }


class SurveyFlowPickerService:
    @staticmethod
    def patch_snapshot_for_ai_test(snap: dict[str, Any]) -> dict[str, Any]:
        """Mark rating node ai_assisted for internal simulator / sample flows."""
        out = json.loads(json.dumps(snap))
        for node in out.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            if str(node.get("node_key") or "") == "rating":
                node["next_resolution"] = "ai_assisted"
                node["picker_hint"] = (
                    "Choose the most relevant next step from the candidates only. "
                    "Prefer outcome_unhappy for scores 0-2, reason for low-mid detail, yes_no otherwise."
                )
        return out

    @staticmethod
    def build_candidates(
        db: Session,
        *,
        session: SurveySession,
        config: dict[str, Any],
        snap: dict[str, Any],
        idx: dict[str, Any],
        current_node_key: str,
        visit_num: int,
    ) -> list[dict[str, Any]]:
        edges = list(idx.get("edges_by_from", {}).get(current_node_key) or [])
        visited_roles = {
            str(a.step_role)
            for a in SurveySessionService.list_answers(db, session.id)
        }
        mq = int(snap.get("max_question_visits") or session.total_steps or 6)
        visits_exhausted = visit_num >= mq

        bank_roles: set[str] = set()
        st_id = str(session.survey_type_id or config.get("survey_type_id") or "")
        if st_id:
            bank = load_step_bank(
                db,
                survey_type_id=st_id,
                privacy_mode=session.privacy_mode or config.get("privacy_mode"),
            )
            bank_roles = set(bank.get("available_roles") or bank.get("by_role", {}).keys())

        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for edge in sorted(edges, key=lambda e: int(e.get("priority") or 100)):
            to_key = str(edge.get("to_node_key") or "")
            if not to_key or to_key in seen:
                continue
            node = idx["nodes"].get(to_key) or {}
            ntype = str(node.get("node_type") or "")
            if ntype == NODE_TYPE_QUESTION:
                if visits_exhausted:
                    continue
                role = normalize_step_role(str(node.get("step_role") or ""))
                if role in visited_roles:
                    continue
                if bank_roles and role not in bank_roles:
                    continue
            elif ntype != NODE_TYPE_OUTCOME:
                continue
            seen.add(to_key)
            candidates.append(_candidate_descriptor(edge=edge, node=node))
        return candidates

    @staticmethod
    def select_edge_deterministic(
        *,
        edges: list[dict[str, Any]],
        last_answer: SurveySessionAnswer | None,
        answers: list[SurveySessionAnswer],
    ) -> tuple[dict[str, Any] | None, str]:
        matched = None
        for edge in edges:
            cond = edge.get("condition_json")
            if cond is None:
                continue
            if evaluate_condition(cond, last_answer=last_answer, answers=answers):
                matched = edge
                break
        if matched is None:
            defaults = [e for e in edges if e.get("condition_json") is None]
            matched = defaults[0] if defaults else None
        if matched:
            return matched, "deterministic_edge"
        return None, "no_edge"

    @staticmethod
    def _mock_pick(candidates: list[dict[str, Any]], *, last_value: str) -> dict[str, Any]:
        """Simulator-only heuristic when OpenAI is not called."""
        try:
            score = int(float(str(last_value or "").strip()))
        except (TypeError, ValueError):
            score = -1
        keys = {c["node_key"] for c in candidates}
        chosen = None
        if score <= 2 and any(k.startswith("outcome_unhappy") for k in keys):
            chosen = next(k for k in keys if k.startswith("outcome_unhappy"))
        elif "reason" in keys and score <= 6:
            chosen = "reason"
        elif "yes_no" in keys:
            chosen = "yes_no"
        elif candidates:
            chosen = candidates[0]["node_key"]
        return {
            "chosen_node_key": chosen or "",
            "confidence": 0.5,
            "rationale": "simulator_mock_picker",
        }

    @staticmethod
    def invoke_ai_pick(
        db: Session,
        *,
        config: dict[str, Any],
        session: SurveySession,
        current_node: dict[str, Any],
        candidates: list[dict[str, Any]],
        answers: list[SurveySessionAnswer],
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        """Returns (parsed_pick, meta). parsed_pick None on failure."""
        if config.get("simulator_mock_picker"):
            last_val = answers[-1].normalized_value if answers else ""
            parsed = SurveyFlowPickerService._mock_pick(candidates, last_value=last_val or "")
            return parsed, {"api_style": "simulator_mock", "model": "mock"}

        survey_type = db.get(SurveyType, str(session.survey_type_id or "")) if session.survey_type_id else None
        st_slug = survey_type.slug if survey_type else str(config.get("survey_type_slug") or "survey")
        summary = [
            {
                "step_role": a.step_role,
                "normalized_value": a.normalized_value,
            }
            for a in answers[-8:]
        ]
        hint = str(current_node.get("picker_hint") or "").strip()[:500]
        system = (
            "You route a WhatsApp survey. Pick exactly one next_node_key from the candidate list. "
            "Never invent roles or text. Output JSON only."
        )
        user = json.dumps(
            {
                "survey_type": st_slug,
                "privacy_mode": session.privacy_mode or config.get("privacy_mode"),
                "current_node_key": session.current_node_key,
                "picker_hint": hint,
                "answers_summary": summary,
                "candidates": candidates,
            },
            ensure_ascii=False,
        )
        timeout_ms = int(config.get("ai_picker_timeout_ms") or os.getenv("WA_SURVEY_AI_PICKER_TIMEOUT_MS") or 8000)
        t0 = time.monotonic()
        try:
            parsed, meta = OpenAIProviderService.responses_json(
                db,
                system_prompt=system,
                user_prompt=user,
                json_schema=PICKER_JSON_SCHEMA,
                schema_name="wa_survey_flow_picker",
                max_output_tokens=400,
            )
            meta["latency_ms"] = int((time.monotonic() - t0) * 1000)
            meta["timeout_ms"] = timeout_ms
            return parsed, meta
        except Exception as exc:
            logger.warning("[survey-picker] openai_failed session=%s err=%s", session.id, exc)
            return None, {"error": str(exc), "latency_ms": int((time.monotonic() - t0) * 1000)}

    @staticmethod
    def resolve_next_edge(
        db: Session,
        *,
        session: SurveySession,
        config: dict[str, Any],
        snap: dict[str, Any],
        idx: dict[str, Any],
        current_node_key: str,
        current_node: dict[str, Any],
        visit_num: int,
        last_answer: SurveySessionAnswer,
        answers: list[SurveySessionAnswer],
    ) -> tuple[str | None, dict[str, Any]]:
        """
        Choose next node_key after an answer. Returns (to_node_key, picker_debug).
        picker_debug is stored on session decisions / simulator UI.
        """
        edges = list(idx.get("edges_by_from", {}).get(current_node_key) or [])
        debug: dict[str, Any] = {
            "picker_source": PICKER_DETERMINISTIC,
            "picker_called": False,
            "candidates": [],
            "fallback_reason": None,
            "chosen_node_key": None,
            "confidence": None,
            "rationale": None,
            "ai_meta": None,
        }

        candidates = SurveyFlowPickerService.build_candidates(
            db,
            session=session,
            config=config,
            snap=snap,
            idx=idx,
            current_node_key=current_node_key,
            visit_num=visit_num,
        )
        debug["candidates"] = candidates

        if len(candidates) == 1:
            chosen = candidates[0]["node_key"]
            debug["chosen_node_key"] = chosen
            debug["picker_source"] = PICKER_DETERMINISTIC
            debug["fallback_reason"] = "single_candidate"
            SurveySessionService._append_decision(
                db,
                session,
                decision_kind=DECISION_BRANCH_PICKER_RESULT,
                rule_key=RULE_AI_PICKER_SKIPPED,
                from_step=visit_num,
                to_step=visit_num + 1,
                from_role=str(current_node.get("step_role") or ""),
                to_role=chosen,
                reason="Single candidate; AI skipped.",
                context=debug,
                picker=PICKER_DETERMINISTIC,
            )
            return chosen, debug

        if not candidates:
            fallback = str(snap.get("fallback_outcome_key") or "neutral")
            chosen = f"outcome_{fallback}"
            debug["chosen_node_key"] = chosen
            debug["fallback_reason"] = "no_candidates"
            return chosen, debug

        allowed, skip_reason = SurveyPickerSettingsService.can_invoke_picker(
            db,
            config=config,
            session=session,
            current_node=current_node,
        )

        if allowed:
            SurveySessionService._append_decision(
                db,
                session,
                decision_kind=DECISION_BRANCH_PICKER_INVOKE,
                rule_key=RULE_AI_PICKER_REQUEST,
                from_step=visit_num,
                to_step=None,
                from_role=str(current_node.get("step_role") or ""),
                to_role=None,
                reason="AI picker invoked.",
                context={"candidates": candidates},
                picker=PICKER_AI_ASSISTED,
            )
            parsed, ai_meta = SurveyFlowPickerService.invoke_ai_pick(
                db,
                config=config,
                session=session,
                current_node=current_node,
                candidates=candidates,
                answers=answers,
            )
            debug["picker_called"] = True
            debug["ai_meta"] = ai_meta
            valid_keys = {c["node_key"] for c in candidates}
            if parsed and str(parsed.get("chosen_node_key") or "") in valid_keys:
                from datetime import datetime

                session.picker_invocation_count = int(session.picker_invocation_count or 0) + 1
                session.updated_at = datetime.utcnow()
                db.add(session)
                chosen = str(parsed["chosen_node_key"])
                debug["picker_source"] = PICKER_AI_ASSISTED
                debug["chosen_node_key"] = chosen
                debug["confidence"] = parsed.get("confidence")
                debug["rationale"] = parsed.get("rationale")
                SurveySessionService._append_decision(
                    db,
                    session,
                    decision_kind=DECISION_BRANCH_PICKER_RESULT,
                    rule_key=RULE_AI_PICKER_CHOSEN,
                    from_step=visit_num,
                    to_step=visit_num + 1,
                    from_role=str(current_node.get("step_role") or ""),
                    to_role=chosen,
                    reason="AI picker chose next node.",
                    context=debug,
                    picker=PICKER_AI_ASSISTED,
                )
                return chosen, debug
            debug["fallback_reason"] = "invalid_ai_output" if parsed else "ai_call_failed"
        else:
            debug["fallback_reason"] = skip_reason or "picker_not_allowed"

        matched, det_reason = SurveyFlowPickerService.select_edge_deterministic(
            edges=edges,
            last_answer=last_answer,
            answers=answers,
        )
        if matched:
            chosen = str(matched.get("to_node_key") or "")
            debug["picker_source"] = PICKER_DETERMINISTIC
            debug["chosen_node_key"] = chosen
            if not debug.get("fallback_reason"):
                debug["fallback_reason"] = det_reason
            SurveySessionService._append_decision(
                db,
                session,
                decision_kind=DECISION_BRANCH_PICKER_RESULT,
                rule_key=RULE_AI_PICKER_FALLBACK,
                from_step=visit_num,
                to_step=visit_num + 1,
                from_role=str(current_node.get("step_role") or ""),
                to_role=chosen,
                reason="Deterministic fallback after AI skip/failure.",
                context=debug,
                picker=PICKER_DETERMINISTIC,
            )
            return chosen, debug

        fallback = str(snap.get("fallback_outcome_key") or "neutral")
        chosen = f"outcome_{fallback}"
        debug["chosen_node_key"] = chosen
        debug["fallback_reason"] = debug.get("fallback_reason") or "no_edge"
        SurveySessionService._append_decision(
            db,
            session,
            decision_kind=DECISION_BRANCH_PICKER_RESULT,
            rule_key=RULE_AI_PICKER_FALLBACK,
            from_step=visit_num,
            to_step=None,
            from_role=str(current_node.get("step_role") or ""),
            to_role=chosen,
            reason="Fallback outcome — no edge matched.",
            context=debug,
            picker=PICKER_DETERMINISTIC,
        )
        return chosen, debug

    @staticmethod
    def latest_picker_debug(db: Session, session_id: str) -> dict[str, Any] | None:
        for row in reversed(SurveySessionService.list_decisions(db, session_id)):
            if row.decision_kind not in (DECISION_BRANCH_PICKER_INVOKE, DECISION_BRANCH_PICKER_RESULT):
                continue
            try:
                ctx = json.loads(row.context_json or "{}")
            except Exception:
                ctx = {}
            if isinstance(ctx, dict):
                ctx["decision_kind"] = row.decision_kind
                ctx["rule_key"] = row.rule_key
                ctx["picker"] = row.picker
                return ctx
        return None
