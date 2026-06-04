"""Order config helpers for WA Survey flow_engine (P2)."""

from __future__ import annotations

import json
from typing import Any

from app.services.survey_flow_constants import FLOW_ENGINE_GRAPH, FLOW_ENGINE_LINEAR


def parse_config_json(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def flow_engine(config: dict[str, Any]) -> str:
    return str(config.get("flow_engine") or FLOW_ENGINE_LINEAR).strip().lower()


def is_graph_flow(config: dict[str, Any]) -> bool:
    if flow_engine(config) != FLOW_ENGINE_GRAPH:
        return False
    snap = config.get("flow_snapshot")
    if isinstance(snap, dict) and snap.get("nodes"):
        return True
    raw = config.get("flow_snapshot_json")
    if raw:
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            return isinstance(data, dict) and bool(data.get("nodes"))
        except Exception:
            return False
    return False


def get_flow_snapshot(config: dict[str, Any]) -> dict[str, Any] | None:
    snap = config.get("flow_snapshot")
    if isinstance(snap, dict):
        return snap
    raw = config.get("flow_snapshot_json")
    if not raw:
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def attach_flow_to_config(config: dict[str, Any], *, snapshot: dict[str, Any], flow_definition_id: str | None) -> dict[str, Any]:
    out = dict(config)
    out["flow_engine"] = FLOW_ENGINE_GRAPH
    out["flow_definition_id"] = flow_definition_id
    out["flow_snapshot"] = snapshot
    out["flow_snapshot_json"] = json.dumps(snapshot, ensure_ascii=False)
    return out


def is_simulator_dry_run(config: dict[str, Any]) -> bool:
    return bool(config.get("simulator_dry_run"))


def is_simulator_live_test(config: dict[str, Any]) -> bool:
    return bool(config.get("simulator_live_test"))


def is_simulator_order(config: dict[str, Any]) -> bool:
    return is_simulator_dry_run(config) or is_simulator_live_test(config)


def max_question_visits(config: dict[str, Any], *, survey_type_max_length: int = 6) -> int:
    snap = get_flow_snapshot(config)
    if snap and snap.get("max_question_visits"):
        try:
            return int(snap["max_question_visits"])
        except (TypeError, ValueError):
            pass
    pc = config.get("page_count")
    if pc is not None:
        try:
            return int(pc)
        except (TypeError, ValueError):
            pass
    return survey_type_max_length
