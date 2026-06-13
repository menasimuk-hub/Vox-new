export type AssistantHighlightType =
  | ""
  | "invoice"
  | "service_order"
  | "ticket"
  | "feedback_location"
  | "survey_result"
  | "interview_result"
  | "wallet_transaction"
  | "usage";

export type AssistantNextActionKind = "navigate" | "confirm" | "open_panel";

export type AssistantNextAction = {
  id: string;
  label: string;
  kind: AssistantNextActionKind;
  route?: string | null;
  action_id?: string | null;
};

export type AssistantPendingAction = {
  action_id: string;
  action_type: string;
  summary: string;
  required_fields?: string[];
  preview?: Record<string, unknown>;
};

export type AssistantChatResponse = {
  ok: boolean;
  primary_message: string;
  highlight_type: AssistantHighlightType;
  highlight_id?: string | null;
  highlight_label?: string | null;
  next_actions: AssistantNextAction[];
  blocking_reason?: string | null;
  confidence: number;
  intent?: string | null;
  pending_action?: AssistantPendingAction | null;
  policy_refused?: boolean;
};

export type AssistantHighlight = {
  type: AssistantHighlightType;
  id: string;
  label?: string | null;
} | null;
