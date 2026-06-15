"""Static intent → read-only tool registry for the dashboard AI assistant."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.dependencies import CurrentPrincipal
from app.models.organisation import Organisation
from app.schemas.assistant import AssistantContextIn, AssistantUiCommand
from app.services.assistant.allowlists import CUSTOMER_READ_TOOLS
from app.services.assistant.safe_tools import run_tool
from app.services.assistant.tools import AssistantTools
from app.services.platform_catalog_service import PlatformCatalogService as ServiceOrderService

_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


@dataclass
class ToolResult:
    ok: bool
    data: Any = None
    error_code: str | None = None
    error_detail: str | None = None
    endpoint_label: str = ""
    params_sent: dict[str, Any] = field(default_factory=dict)
    navigation_only: bool = False


@dataclass(frozen=True)
class AssistantIntentSpec:
    intent: str
    tool_name: str | None
    endpoint_label: str
    dashboard_section: str
    description: str
    example_phrases: tuple[str, ...]
    param_keys: tuple[str, ...] = ()


def _resolve_order_id(context: AssistantContextIn, message: str, orders: list[dict[str, Any]]) -> str | None:
    if context.order_id:
        return context.order_id
    match = _UUID_RE.search(message or "")
    if match:
        return match.group(0)
    if orders:
        return str(orders[0].get("id") or "") or None
    return None


def _nav_commands(*pairs: tuple[str, str, str | None]) -> list[AssistantUiCommand]:
    out: list[AssistantUiCommand] = []
    for cmd_id, label, route in pairs:
        out.append(AssistantUiCommand(id=cmd_id, kind="navigate", route=route, label=label))
    return out


def _highlight_command(
    *,
    cmd_id: str,
    label: str,
    highlight_type: str,
    highlight_id: str,
    highlight_label: str | None = None,
    route: str | None = None,
) -> AssistantUiCommand:
    return AssistantUiCommand(
        id=cmd_id,
        kind="scroll_to",
        route=route,
        label=label,
        highlight_type=highlight_type or "",
        highlight_id=highlight_id,
        highlight_label=highlight_label,
    )


INTENT_REGISTRY: dict[str, AssistantIntentSpec] = {
    "wallet_low": AssistantIntentSpec(
        intent="wallet_low",
        tool_name="wallet",
        endpoint_label="GET in-process wallet_low_analysis",
        dashboard_section="Account → Billing",
        description="Explain wallet balance and recent debits",
        example_phrases=("Why is my wallet low?", "Where did my balance go?"),
    ),
    "billing_overview": AssistantIntentSpec(
        intent="billing_overview",
        tool_name="billing_access",
        endpoint_label="GET in-process billing_access",
        dashboard_section="Account → Billing",
        description="Subscription, invoices, and payment status",
        example_phrases=("Show my billing", "Do I owe anything?", "Invoice status"),
    ),
    "usage_summary": AssistantIntentSpec(
        intent="usage_summary",
        tool_name="usage_summary",
        endpoint_label="GET in-process usage_summary",
        dashboard_section="Account → Usage",
        description="Plan allowance and usage meters",
        example_phrases=("What's my usage?", "How many minutes left?", "Quota remaining"),
    ),
    "launch_check": AssistantIntentSpec(
        intent="launch_check",
        tool_name="launch_eligibility",
        endpoint_label="GET in-process launch_eligibility",
        dashboard_section="Surveys / Interviews",
        description="Check if a campaign can launch",
        example_phrases=("Can I launch?", "Ready to start campaign"),
        param_keys=("order_id",),
    ),
    "survey_results": AssistantIntentSpec(
        intent="survey_results",
        tool_name="survey_results",
        endpoint_label="GET in-process survey_results",
        dashboard_section="Surveys → Results",
        description="Survey completion and NPS summary",
        example_phrases=("Survey results", "Show NPS", "Response rate"),
        param_keys=("order_id",),
    ),
    "interview_results": AssistantIntentSpec(
        intent="interview_results",
        tool_name="interview_results",
        endpoint_label="GET in-process interview_results",
        dashboard_section="Interviews → Results",
        description="Interview campaign completion stats",
        example_phrases=("Interview results", "Candidate completion"),
        param_keys=("order_id",),
    ),
    "feedback_overview": AssistantIntentSpec(
        intent="feedback_overview",
        tool_name="feedback_locations",
        endpoint_label="GET in-process feedback_locations",
        dashboard_section="Feedback",
        description="QR feedback locations and scans",
        example_phrases=("Customer feedback", "QR locations"),
    ),
    "list_surveys": AssistantIntentSpec(
        intent="list_surveys",
        tool_name="list_service_orders",
        endpoint_label="GET in-process list_service_orders(survey)",
        dashboard_section="Surveys",
        description="List survey campaigns",
        example_phrases=("My surveys", "List campaigns"),
    ),
    "list_interviews": AssistantIntentSpec(
        intent="list_interviews",
        tool_name="list_service_orders",
        endpoint_label="GET in-process list_service_orders(interview)",
        dashboard_section="Interviews",
        description="List interview campaigns",
        example_phrases=("My interviews", "List interviews"),
    ),
    "list_tickets": AssistantIntentSpec(
        intent="list_tickets",
        tool_name="list_tickets",
        endpoint_label="GET in-process list_tickets",
        dashboard_section="Account → Support",
        description="Support ticket history",
        example_phrases=("My support tickets", "Open tickets"),
    ),
    "invoice_detail": AssistantIntentSpec(
        intent="invoice_detail",
        tool_name="invoice_detail",
        endpoint_label="GET in-process invoice_detail",
        dashboard_section="Account → Billing",
        description="Explain a specific invoice",
        example_phrases=("Explain this invoice", "Invoice breakdown"),
        param_keys=("invoice_id",),
    ),
    "create_survey": AssistantIntentSpec(
        intent="create_survey",
        tool_name=None,
        endpoint_label="NAV /surveys/new",
        dashboard_section="Surveys",
        description="Navigate to create a new survey",
        example_phrases=("Create survey", "New campaign"),
    ),
    "create_interview": AssistantIntentSpec(
        intent="create_interview",
        tool_name=None,
        endpoint_label="NAV /interviews/new",
        dashboard_section="Interviews",
        description="Navigate to create a new interview",
        example_phrases=("Create interview", "New interview"),
    ),
    "create_feedback": AssistantIntentSpec(
        intent="create_feedback",
        tool_name=None,
        endpoint_label="NAV /feedback/new",
        dashboard_section="Feedback",
        description="Navigate to create feedback location",
        example_phrases=("Create feedback location", "New QR location"),
    ),
    "create_template": AssistantIntentSpec(
        intent="create_template",
        tool_name=None,
        endpoint_label="NAV /surveys/new?channel=whatsapp",
        dashboard_section="Surveys → WhatsApp",
        description="Navigate to WhatsApp survey template setup",
        example_phrases=("Custom WhatsApp template", "Create template"),
    ),
    "product_compare": AssistantIntentSpec(
        intent="product_compare",
        tool_name=None,
        endpoint_label="NAV (informational)",
        dashboard_section="Product",
        description="Compare survey vs feedback vs interview",
        example_phrases=("Survey vs feedback", "What's the difference"),
    ),
    "general_help": AssistantIntentSpec(
        intent="general_help",
        tool_name=None,
        endpoint_label="NAV (informational)",
        dashboard_section="Dashboard",
        description="General product guidance",
        example_phrases=("What can you do?", "Help"),
    ),
    "open_settings": AssistantIntentSpec(
        intent="open_settings",
        tool_name=None,
        endpoint_label="NAV /settings/profile",
        dashboard_section="Settings",
        description="Open account settings",
        example_phrases=("Account settings", "Open settings", "Profile settings"),
    ),
}


def registry_intent_names() -> list[str]:
    return sorted(INTENT_REGISTRY.keys())


def default_ui_commands_for_intent(
    intent: str,
    *,
    data: Any = None,
    params: dict[str, Any] | None = None,
) -> list[AssistantUiCommand]:
    params = params or {}
    if intent == "billing_overview":
        inv_id = None
        if isinstance(data, dict):
            invoices = data.get("outstanding_invoices") or data.get("invoices") or []
            if invoices and isinstance(invoices[0], dict):
                inv_id = str(invoices[0].get("id") or "")
        cmds = _nav_commands(("billing", "Open billing", "/account/billing"))
        if inv_id:
            cmds.insert(0, _highlight_command(cmd_id="invoice", label="View invoice", highlight_type="invoice", highlight_id=inv_id, route="/account/billing"))
        return cmds
    if intent == "usage_summary":
        return _nav_commands(("usage", "View usage", "/account/usage"))
    if intent == "wallet_low":
        cmds = _nav_commands(("billing", "Open billing", "/account/billing"), ("usage", "View usage", "/account/usage"))
        if isinstance(data, dict):
            analysis = data
            h_type, h_id, h_label, _ = AssistantTools.pick_charge_explanation(analysis)
            if h_id and h_type:
                cmds.insert(0, _highlight_command(cmd_id="charge", label="View item", highlight_type=h_type, highlight_id=h_id, highlight_label=h_label, route="/account/billing"))
        return cmds
    if intent in {"list_surveys", "survey_results"}:
        order_id = str(params.get("order_id") or "")
        if isinstance(data, dict) and not order_id:
            order_id = str(data.get("order_id") or data.get("id") or "")
        cmds = [_nav_commands(("surveys", "View surveys", "/surveys"))[0]]
        if order_id:
            cmds.insert(0, _highlight_command(cmd_id="survey", label="Open survey", highlight_type="service_order", highlight_id=order_id, route=f"/surveys/new?order_id={order_id}"))
        return cmds
    if intent in {"list_interviews", "interview_results"}:
        order_id = str(params.get("order_id") or "")
        if isinstance(data, dict) and not order_id:
            order_id = str(data.get("order_id") or "")
        cmds = [_nav_commands(("interviews", "View interviews", "/interviews"))[0]]
        if order_id:
            cmds.insert(0, _highlight_command(cmd_id="interview", label="Open interview", highlight_type="service_order", highlight_id=order_id, route=f"/interviews/{order_id}"))
        return cmds
    if intent == "feedback_overview":
        return _nav_commands(("feedback", "View feedback", "/feedback"))
    if intent == "list_tickets":
        return _nav_commands(("tickets", "View tickets", "/account/support/tickets"))
    if intent == "create_survey":
        return _nav_commands(("create_survey", "Create survey", "/surveys/new"))
    if intent == "create_interview":
        return _nav_commands(("create_interview", "Create interview", "/interviews/new"))
    if intent == "create_feedback":
        return _nav_commands(("create_feedback", "Create feedback", "/feedback/new"))
    if intent == "create_template":
        return _nav_commands(("create_template", "Create WA survey", "/surveys/new?channel=whatsapp"))
    if intent == "open_settings":
        return _nav_commands(("settings", "Account settings", "/settings/profile"))
    if intent == "launch_check":
        order_id = str(params.get("order_id") or "")
        route = f"/surveys/new?order_id={order_id}" if order_id else "/surveys"
        cmds = [AssistantUiCommand(id="launch", kind="navigate", route=route, label="Open campaign")]
        if order_id:
            cmds.insert(0, _highlight_command(cmd_id="order", label="Campaign", highlight_type="service_order", highlight_id=order_id, route=route))
        return cmds
    return _nav_commands(("home", "Dashboard home", "/"))


def _truncate_json(data: Any, *, max_chars: int = 6000) -> str:
    try:
        raw = json.dumps(data, ensure_ascii=False, default=str)
    except Exception:
        raw = str(data)
    if len(raw) <= max_chars:
        return raw
    return raw[: max_chars - 20] + "…(truncated)"


def execute_intent(
    db: Session,
    *,
    intent: str,
    params: dict[str, Any],
    principal: CurrentPrincipal,
    org: Organisation,
    context: AssistantContextIn,
    message: str,
) -> ToolResult:
    spec = INTENT_REGISTRY.get(intent)
    if spec is None:
        return ToolResult(ok=False, error_code="unknown_intent", error_detail=f"Unknown intent: {intent}", endpoint_label="none")

    if spec.tool_name is None:
        return ToolResult(ok=True, data={"intent": intent}, endpoint_label=spec.endpoint_label, navigation_only=True)

    if spec.tool_name not in CUSTOMER_READ_TOOLS:
        return ToolResult(
            ok=False,
            error_code="tool_not_allowed",
            error_detail=f"Tool {spec.tool_name} is not allowlisted",
            endpoint_label=spec.endpoint_label,
            params_sent=params,
        )

    sent = dict(params or {})
    try:
        if intent == "wallet_low":
            data, failed = run_tool(spec.tool_name, lambda: AssistantTools.wallet_low_analysis(db, org))
        elif intent == "billing_overview":
            data, failed = run_tool(spec.tool_name, lambda: AssistantTools.billing_access(db, org))
        elif intent == "usage_summary":
            data, failed = run_tool(spec.tool_name, lambda: AssistantTools.usage_summary(db, org))
        elif intent == "list_surveys":
            data, failed = run_tool(spec.tool_name, lambda: AssistantTools.list_service_orders(db, principal.org_id, service_code="survey", limit=20))
        elif intent == "list_interviews":
            data, failed = run_tool(spec.tool_name, lambda: AssistantTools.list_service_orders(db, principal.org_id, service_code="interview", limit=20))
        elif intent == "list_tickets":
            data, failed = run_tool(
                spec.tool_name,
                lambda: AssistantTools.list_tickets(db, principal.org_id, principal.user_id, limit=20),
            )
        elif intent == "feedback_overview":
            data, failed = run_tool(spec.tool_name, lambda: AssistantTools.feedback_locations(db, principal.org_id))
        elif intent == "invoice_detail":
            invoice_id = str(sent.get("invoice_id") or context.invoice_id or "")
            if not invoice_id:
                match = _UUID_RE.search(message or "")
                invoice_id = match.group(0) if match else ""
            sent["invoice_id"] = invoice_id
            data, failed = run_tool(
                spec.tool_name,
                lambda: AssistantTools.invoice_detail(db, principal.org_id, invoice_id) if invoice_id else None,
            )
        elif intent in {"survey_results", "interview_results", "launch_check"}:
            service_code = "survey" if intent != "interview_results" else "interview"
            orders, o_fail = run_tool(
                "list_service_orders",
                lambda: AssistantTools.list_service_orders(db, principal.org_id, service_code=service_code, limit=15),
                default=[],
            )
            order_id = str(sent.get("order_id") or _resolve_order_id(context, message, orders or []) or "")
            sent["order_id"] = order_id
            if not order_id:
                return ToolResult(ok=False, error_code="missing_order_id", error_detail="No campaign found", endpoint_label=spec.endpoint_label, params_sent=sent)
            order_row = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
            if order_row is None:
                return ToolResult(ok=False, error_code="order_not_found", error_detail="Campaign not found", endpoint_label=spec.endpoint_label, params_sent=sent)
            if intent == "launch_check":
                data, failed = run_tool(spec.tool_name, lambda: AssistantTools.launch_eligibility(db, org, order_row))
            elif intent == "survey_results":
                data, failed = run_tool(spec.tool_name, lambda: AssistantTools.survey_results(db, order_row))
            else:
                data, failed = run_tool(spec.tool_name, lambda: AssistantTools.interview_results(db, order_row))
        else:
            return ToolResult(ok=False, error_code="not_implemented", error_detail=intent, endpoint_label=spec.endpoint_label, params_sent=sent)

        if failed or data is None:
            return ToolResult(
                ok=False,
                error_code="tool_failed",
                error_detail="Tool execution failed",
                endpoint_label=spec.endpoint_label,
                params_sent=sent,
            )
        return ToolResult(ok=True, data=data, endpoint_label=spec.endpoint_label, params_sent=sent)
    except Exception as exc:
        return ToolResult(
            ok=False,
            error_code="exception",
            error_detail=str(exc)[:500],
            endpoint_label=spec.endpoint_label,
            params_sent=sent,
        )


def tool_data_for_prompt(result: ToolResult) -> str:
    if result.navigation_only:
        return json.dumps({"navigation_only": True, "intent": result.params_sent.get("intent")})
    if not result.ok:
        return json.dumps({"error": result.error_code})
    return _truncate_json(result.data)
