"""Compile and validate WA Survey flow graphs (P2)."""

from __future__ import annotations

import json
from typing import Any

from app.services.survey_flow_constants import (
    ACTION_SEND_TEXT,
    NODE_TYPE_OUTCOME,
    NODE_TYPE_QUESTION,
    OUTCOME_HAPPY,
    OUTCOME_KEYS,
    OUTCOME_NEUTRAL,
    OUTCOME_UNHAPPY,
)
from app.services.survey_step_bank_service import MIDDLE_STEP_ROLES, normalize_step_role


def _outcome_node_key(outcome_key: str) -> str:
    return f"outcome_{outcome_key}"


def compile_linear_graph(
    *,
    page_roles: list[str],
    questions: list[dict[str, Any]],
    max_question_visits: int,
    closing_body: str,
    flow_definition_id: str | None = None,
    version: int = 1,
    branches: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Build a deterministic graph snapshot from linear page_roles + optional branch overrides.

    branches: optional list of
      {"from_step_role": "rating", "condition": {...}, "to_step_role": "reason" | "outcome_unhappy"}
    """
    middle = [
        normalize_step_role(r)
        for r in page_roles
        if normalize_step_role(r) not in {"start", "completion"}
    ]
    q_by_role: dict[str, dict[str, Any]] = {}
    for q in questions:
        if not isinstance(q, dict):
            continue
        role = normalize_step_role(str(q.get("step_role") or ""))
        if not role:
            idx = len(q_by_role)
            if idx < len(middle):
                role = middle[idx]
        if role:
            q_by_role[role] = {**q, "step_role": role}

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for i, role in enumerate(middle):
        question = q_by_role.get(role) or {
            "step_role": role,
            "text": role.replace("_", " ").title(),
            "reply_type": "text",
            "options": [],
        }
        nodes.append(
            {
                "node_key": role,
                "node_type": NODE_TYPE_QUESTION,
                "step_role": role,
                "question": question,
                "template_id": question.get("template_id"),
                "is_terminal": False,
            }
        )

    for ok in (OUTCOME_HAPPY, OUTCOME_NEUTRAL, OUTCOME_UNHAPPY):
        nk = _outcome_node_key(ok)
        body = closing_body
        if ok == OUTCOME_HAPPY:
            body = closing_body or "Thank you — we appreciate your feedback."
        elif ok == OUTCOME_UNHAPPY:
            body = "We're sorry your experience wasn't better. A team member may follow up soon."
        nodes.append(
            {
                "node_key": nk,
                "node_type": NODE_TYPE_OUTCOME,
                "step_role": None,
                "outcome_key": ok,
                "is_terminal": True,
            }
        )

    branch_edges: list[dict[str, Any]] = []
    if branches:
        for br in branches:
            if not isinstance(br, dict):
                continue
            from_role = normalize_step_role(str(br.get("from_step_role") or ""))
            to_target = str(br.get("to_step_role") or br.get("to_node_key") or "").strip()
            cond = br.get("condition")
            if not from_role or not to_target:
                continue
            to_key = (
                _outcome_node_key(normalize_step_role(to_target.replace("outcome_", "")))
                if to_target.startswith("outcome_") or to_target in OUTCOME_KEYS
                else normalize_step_role(to_target)
            )
            if to_target in OUTCOME_KEYS:
                to_key = _outcome_node_key(to_target)
            branch_edges.append(
                {
                    "from_node_key": from_role,
                    "to_node_key": to_key,
                    "priority": int(br.get("priority") or 10),
                    "rule_key": str(br.get("rule_key") or "branch.custom"),
                    "condition_json": cond,
                }
            )

    for i, role in enumerate(middle):
        custom = [e for e in branch_edges if e["from_node_key"] == role]
        if custom:
            for e in sorted(custom, key=lambda x: x["priority"]):
                edges.append(
                    {
                        **e,
                        "condition_json": e.get("condition_json"),
                    }
                )
            edges.append(
                {
                    "from_node_key": role,
                    "to_node_key": middle[i + 1] if i + 1 < len(middle) else _outcome_node_key(OUTCOME_NEUTRAL),
                    "priority": 500,
                    "rule_key": "linear.default",
                    "condition_json": None,
                }
            )
        else:
            to_key = middle[i + 1] if i + 1 < len(middle) else _outcome_node_key(OUTCOME_NEUTRAL)
            edges.append(
                {
                    "from_node_key": role,
                    "to_node_key": to_key,
                    "priority": 100,
                    "rule_key": "linear.default",
                    "condition_json": None,
                }
            )

    outcomes = []
    for ok in (OUTCOME_HAPPY, OUTCOME_NEUTRAL, OUTCOME_UNHAPPY):
        nk = _outcome_node_key(ok)
        body = closing_body
        if ok == OUTCOME_UNHAPPY:
            body = "We're sorry your experience wasn't better. A team member may follow up soon."
        elif ok == OUTCOME_HAPPY:
            body = closing_body or "Thank you — we appreciate your feedback."
        outcomes.append(
            {
                "outcome_key": ok,
                "node_key": nk,
                "action_type": ACTION_SEND_TEXT,
                "message_body": body,
                "template_id": None,
            }
        )

    entry = middle[0] if middle else _outcome_node_key(OUTCOME_NEUTRAL)
    return {
        "flow_definition_id": flow_definition_id,
        "version": version,
        "entry_node_key": entry,
        "max_question_visits": max_question_visits,
        "fallback_outcome_key": OUTCOME_NEUTRAL,
        "nodes": nodes,
        "edges": edges,
        "outcomes": outcomes,
    }


def snapshot_from_db_rows(
    *,
    flow_id: str,
    version: int,
    entry_node_key: str,
    fallback_outcome_key: str,
    max_question_visits: int,
    nodes: list[Any],
    edges: list[Any],
    outcomes: list[Any],
    questions_by_role: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    qmap = questions_by_role or {}
    snap_nodes: list[dict[str, Any]] = []
    for n in nodes:
        meta = {}
        if n.metadata_json:
            try:
                meta = json.loads(n.metadata_json)
            except Exception:
                meta = {}
        item: dict[str, Any] = {
            "node_key": n.node_key,
            "node_type": n.node_type,
            "step_role": n.step_role,
            "template_id": n.template_id,
            "title": n.title,
            "is_terminal": bool(n.is_terminal),
            "outcome_key": n.outcome_key,
            "metadata": meta,
        }
        if n.node_type == NODE_TYPE_QUESTION and n.step_role:
            item["question"] = qmap.get(n.step_role) or meta.get("question") or {
                "step_role": n.step_role,
                "text": n.title or n.step_role,
                "reply_type": "text",
                "options": [],
            }
        snap_nodes.append(item)

    snap_edges = [
        {
            "from_node_key": e.from_node_key,
            "to_node_key": e.to_node_key,
            "priority": e.priority,
            "rule_key": e.rule_key,
            "condition_json": json.loads(e.condition_json) if e.condition_json else None,
        }
        for e in edges
    ]
    snap_outcomes = [
        {
            "outcome_key": o.outcome_key,
            "node_key": o.node_key,
            "action_type": o.action_type,
            "template_id": o.template_id,
            "message_body": o.message_body,
        }
        for o in outcomes
    ]
    return {
        "flow_definition_id": flow_id,
        "version": version,
        "entry_node_key": entry_node_key,
        "max_question_visits": max_question_visits,
        "fallback_outcome_key": fallback_outcome_key,
        "nodes": snap_nodes,
        "edges": snap_edges,
        "outcomes": snap_outcomes,
    }


def validate_flow_snapshot(snapshot: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    nodes = snapshot.get("nodes") or []
    edges = snapshot.get("edges") or []
    outcomes = snapshot.get("outcomes") or []
    if not nodes:
        errors.append("Flow must have at least one node")
        return errors

    node_map: dict[str, dict[str, Any]] = {}
    question_roles: set[str] = set()
    for n in nodes:
        if not isinstance(n, dict):
            continue
        key = str(n.get("node_key") or "")
        if not key:
            errors.append("Node missing node_key")
            continue
        if key in node_map:
            errors.append(f"Duplicate node_key: {key}")
        node_map[key] = n
        ntype = str(n.get("node_type") or "")
        if ntype == NODE_TYPE_QUESTION:
            role = normalize_step_role(str(n.get("step_role") or ""))
            if not role:
                errors.append(f"Question node {key} missing step_role")
            elif role in question_roles:
                errors.append(f"Duplicate question step_role: {role}")
            elif role not in MIDDLE_STEP_ROLES:
                errors.append(f"Invalid step_role on node {key}: {role}")
            else:
                question_roles.add(role)
        elif ntype == NODE_TYPE_OUTCOME:
            ok = str(n.get("outcome_key") or "")
            if ok not in OUTCOME_KEYS:
                errors.append(f"Outcome node {key} has invalid outcome_key: {ok}")

    entry = str(snapshot.get("entry_node_key") or "")
    if entry not in node_map:
        errors.append(f"entry_node_key not found: {entry}")

    fallback = str(snapshot.get("fallback_outcome_key") or "neutral")
    if fallback not in OUTCOME_KEYS:
        errors.append(f"Invalid fallback_outcome_key: {fallback}")

    edges_by_from: dict[str, list[dict[str, Any]]] = {}
    for e in edges:
        if not isinstance(e, dict):
            continue
        fr = str(e.get("from_node_key") or "")
        to = str(e.get("to_node_key") or "")
        if fr not in node_map:
            errors.append(f"Edge from unknown node: {fr}")
        if to not in node_map:
            errors.append(f"Edge to unknown node: {to}")
        edges_by_from.setdefault(fr, []).append(e)

    for fr, elist in edges_by_from.items():
        node = node_map.get(fr) or {}
        if node.get("node_type") != NODE_TYPE_QUESTION:
            continue
        defaults = [e for e in elist if e.get("condition_json") is None]
        if len(defaults) != 1:
            errors.append(f"Question node {fr} must have exactly one default edge (found {len(defaults)})")

    # Cycle detection (DFS)
    visited: set[str] = set()
    stack: set[str] = set()

    def dfs(key: str) -> bool:
        if key in stack:
            return True
        if key in visited:
            return False
        visited.add(key)
        stack.add(key)
        for e in edges_by_from.get(key, []):
            to = str(e.get("to_node_key") or "")
            if to and dfs(to):
                return True
        stack.remove(key)
        return False

    if entry and dfs(entry):
        errors.append("Flow contains a cycle reachable from entry_node_key")

    outcome_nodes = {str(o.get("node_key")) for o in outcomes if isinstance(o, dict)}
    for o in outcomes:
        if not isinstance(o, dict):
            continue
        ok = str(o.get("outcome_key") or "")
        if ok not in OUTCOME_KEYS:
            errors.append(f"Invalid outcome_key in outcomes: {ok}")
        nk = str(o.get("node_key") or "")
        if nk not in node_map:
            errors.append(f"Outcome mapping references missing node: {nk}")

    for n in nodes:
        if isinstance(n, dict) and n.get("node_type") == NODE_TYPE_OUTCOME:
            nk = str(n.get("node_key") or "")
            if nk not in outcome_nodes:
                errors.append(f"Outcome node {nk} has no survey_flow_outcomes mapping")

    return errors


def index_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    nodes = {str(n["node_key"]): n for n in (snapshot.get("nodes") or []) if isinstance(n, dict) and n.get("node_key")}
    edges_by_from: dict[str, list[dict[str, Any]]] = {}
    for e in snapshot.get("edges") or []:
        if not isinstance(e, dict):
            continue
        fr = str(e.get("from_node_key") or "")
        edges_by_from.setdefault(fr, []).append(e)
    for fr in edges_by_from:
        edges_by_from[fr].sort(key=lambda x: int(x.get("priority") or 100))
    outcomes_by_node = {
        str(o["node_key"]): o for o in (snapshot.get("outcomes") or []) if isinstance(o, dict) and o.get("node_key")
    }
    outcomes_by_key = {
        str(o["outcome_key"]): o for o in (snapshot.get("outcomes") or []) if isinstance(o, dict) and o.get("outcome_key")
    }
    return {
        "nodes": nodes,
        "edges_by_from": edges_by_from,
        "outcomes_by_node": outcomes_by_node,
        "outcomes_by_key": outcomes_by_key,
    }
