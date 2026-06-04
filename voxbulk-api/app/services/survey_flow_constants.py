"""Constants for WA Survey flow graph (P2)."""

from __future__ import annotations

FLOW_ENGINE_LINEAR = "linear"
FLOW_ENGINE_GRAPH = "graph"

FLOW_MODE_LINEAR = "linear"
FLOW_MODE_GRAPH = "graph"

FLOW_STATUS_DRAFT = "draft"
FLOW_STATUS_PUBLISHED = "published"
FLOW_STATUS_ARCHIVED = "archived"

NODE_TYPE_QUESTION = "question"
NODE_TYPE_OUTCOME = "outcome"

OUTCOME_HAPPY = "happy"
OUTCOME_NEUTRAL = "neutral"
OUTCOME_UNHAPPY = "unhappy"
OUTCOME_KEYS: frozenset[str] = frozenset({OUTCOME_HAPPY, OUTCOME_NEUTRAL, OUTCOME_UNHAPPY})

ACTION_SEND_TEXT = "send_text"
ACTION_SEND_TEMPLATE = "send_template"

DECISION_BRANCH_EVALUATE = "branch_evaluate"
DECISION_BRANCH_TAKE = "branch_take"
DECISION_OUTCOME_REACHED = "outcome_reached"
DECISION_OUTCOME_ACTION = "outcome_action"

RULE_BRANCH_DEFAULT = "branch.default"
RULE_GRAPH_START = "graph.start"
RULE_GRAPH_SEND = "graph.send_question"
RULE_GRAPH_COMPLETE = "graph.complete"
