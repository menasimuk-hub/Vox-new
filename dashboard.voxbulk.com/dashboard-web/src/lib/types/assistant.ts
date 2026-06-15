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
export type AssistantUiCommandKind = "navigate" | "highlight" | "scroll_to" | "open_panel";

export type AssistantNextAction = {
  id: string;
  label: string;
  kind: AssistantNextActionKind;
  route?: string | null;
  action_id?: string | null;
};

export type AssistantUiCommand = {
  id: string;
  kind: AssistantUiCommandKind;
  route?: string | null;
  label: string;
  highlight_type?: AssistantHighlightType;
  highlight_id?: string | null;
  highlight_label?: string | null;
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
  ui_commands?: AssistantUiCommand[];
  blocking_reason?: string | null;
  confidence: number;
  intent?: string | null;
  pending_action?: AssistantPendingAction | null;
  policy_refused?: boolean;
  error_occurred?: boolean;
  support_report_token?: string | null;
};

export type AssistantReportSupportResponse = {
  ok: boolean;
  message: string;
  ticket_ref?: string | null;
  already_reported?: boolean;
};

export type AssistantHighlight = {
  type: AssistantHighlightType;
  id: string;
  label?: string | null;
} | null;
