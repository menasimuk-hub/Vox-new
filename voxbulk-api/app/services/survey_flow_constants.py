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

NEXT_RESOLUTION_DETERMINISTIC = "deterministic"
NEXT_RESOLUTION_AI_ASSISTED = "ai_assisted"

PICKER_DETERMINISTIC = "deterministic"
PICKER_AI_ASSISTED = "ai_assisted"

DECISION_BRANCH_PICKER_INVOKE = "branch_picker_invoke"
DECISION_BRANCH_PICKER_RESULT = "branch_picker_result"

RULE_AI_PICKER_REQUEST = "ai_picker.request"
RULE_AI_PICKER_CHOSEN = "ai_picker.chosen"
RULE_AI_PICKER_FALLBACK = "ai_picker.fallback"
RULE_AI_PICKER_SKIPPED = "ai_picker.skipped"

MAX_PICKER_INVOCATIONS_PER_SESSION = 3
