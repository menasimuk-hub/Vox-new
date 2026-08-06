from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AssistantHighlightType = Literal[
    "",
    "invoice",
    "service_order",
    "ticket",
    "feedback_location",
    "survey_result",
    "interview_result",
    "wallet_transaction",
    "usage",
]

AssistantNextActionKind = Literal["navigate", "confirm", "open_panel"]
AssistantUiCommandKind = Literal["navigate", "highlight", "scroll_to", "open_panel"]


class AssistantHistoryItem(BaseModel):
    role: str = "user"
    text: str = ""


class AssistantContextIn(BaseModel):
    order_id: str | None = None
    invoice_id: str | None = None
    ticket_id: str | None = None
    location_id: str | None = None
    service_code: str | None = None
    organisation_id: str | None = None
    current_route: str | None = None
    enabled_services: list[str] = Field(default_factory=list)
    recent_history: list[AssistantHistoryItem] = Field(default_factory=list)


class AssistantChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[AssistantHistoryItem] = Field(default_factory=list)
    context: AssistantContextIn = Field(default_factory=AssistantContextIn)
    conversation_id: str | None = None


class AssistantConfirmIn(BaseModel):
    # Full signed pending-action token (uuid + HMAC payload); not just the short public id.
    action_id: str = Field(min_length=8, max_length=8192)
    confirmed: bool = True


class AssistantNextAction(BaseModel):
    id: str
    label: str
    kind: AssistantNextActionKind = "navigate"
    route: str | None = None
    action_id: str | None = None


class AssistantUiCommand(BaseModel):
    id: str
    kind: AssistantUiCommandKind = "navigate"
    route: str | None = None
    label: str
    highlight_type: AssistantHighlightType = ""
    highlight_id: str | None = None
    highlight_label: str | None = None


class AssistantPendingAction(BaseModel):
    action_id: str
    action_type: str
    summary: str
    required_fields: list[str] = Field(default_factory=list)
    preview: dict[str, Any] = Field(default_factory=dict)


class AssistantChatOut(BaseModel):
    ok: bool = True
    primary_message: str
    highlight_type: AssistantHighlightType = ""
    highlight_id: str | None = None
    highlight_label: str | None = None
    next_actions: list[AssistantNextAction] = Field(default_factory=list)
    ui_commands: list[AssistantUiCommand] = Field(default_factory=list)
    blocking_reason: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.85)
    intent: str | None = None
    pending_action: AssistantPendingAction | None = None
    policy_refused: bool = False
    error_occurred: bool = False
    support_report_token: str | None = None
    suggested_prompts: list[str] = Field(default_factory=list)
    source_type: str | None = None
    sources: list[dict[str, Any]] = Field(default_factory=list)
    conversation_id: str | None = None
    message_id: str | None = None


class AssistantReportSupportIn(BaseModel):
    support_report_token: str = Field(min_length=8, max_length=8192)


class AssistantReportSupportOut(BaseModel):
    ok: bool = True
    message: str
    ticket_ref: str | None = None
    already_reported: bool = False


class AssistantConversationOut(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class AssistantMessageOut(BaseModel):
    id: str
    role: str
    content: str
    source_type: str | None = None
    sources: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str


class AssistantFeedbackIn(BaseModel):
    rating: str = Field(pattern="^(up|down)$")


class AssistantInsightsOut(BaseModel):
    total_questions: int
    kb_hits: int
    general_ai: int
    thumbs_up: int
    thumbs_down: int
    avg_latency_ms: float


class AssistantSuggestionOut(BaseModel):
    id: str
    question: str
    sample_answer: str
    org_id: str | None
    user_id: str | None
    status: str
    created_at: str


class AssistantSuggestionStatusIn(BaseModel):
    status: str = Field(pattern="^(accepted|rejected)$")
