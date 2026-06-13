from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.dependencies import CurrentPrincipal
from app.models.organisation import Organisation
from app.schemas.assistant import AssistantChatIn, AssistantChatOut, AssistantContextIn, AssistantPendingAction
from app.services.assistant.allowlists import customer_may_mutate
from app.services.assistant.billing_context import billing_note_for_intent, fetch_billing_access
from app.services.assistant.highlights import build_out, confirm_action, nav_action, plan_subscription_dict
from app.services.assistant.intent import IntentMatch, classify_intent
from app.services.assistant.pending_actions import issue_pending_action, verify_pending_action
from app.services.assistant.policy_gate import check_policy
from app.services.assistant.safe_tools import (
    INVOICE_FALLBACK_HINT,
    INVOICE_READ_ERROR,
    is_greeting,
    run_tool,
    usage_summary_fragment,
    user_display_name,
)
from app.services.assistant.tools import AssistantTools
from app.services.gocardless_service import BillingService
from app.services.platform_catalog_service import PlatformCatalogService as ServiceOrderService
from app.services.support_ticket_service import SupportTicketService

logger = logging.getLogger(__name__)


class AssistantOrchestrator:
    @staticmethod
    def handle_chat(
        db: Session,
        *,
        principal: CurrentPrincipal,
        payload: AssistantChatIn,
        is_admin: bool = False,
    ) -> AssistantChatOut:
        policy = check_policy(payload.message)
        if not policy.allowed:
            return build_out(
                primary_message=policy.reason or "That request is not permitted.",
                confidence=1.0,
                intent="policy_refused",
                policy_refused=True,
                blocking_reason=policy.reason,
            )

        intent_match = classify_intent(payload.message, is_admin=is_admin)
        org = AssistantTools.get_org(db, principal.org_id)
        if org is None:
            return build_out(primary_message="Organisation not found.", confidence=1.0, blocking_reason="org_not_found")

        handler = _HANDLERS.get(intent_match.intent, _handle_general)
        try:
            return handler(
                db,
                principal=principal,
                org=org,
                message=payload.message,
                intent=intent_match,
                context=payload.context,
                is_admin=is_admin,
            )
        except Exception:
            logger.exception("assistant handler failed intent=%s org=%s", intent_match.intent, principal.org_id)
            return _handler_error_response(
                db,
                principal=principal,
                org=org,
                message=payload.message,
                intent=intent_match,
            )

    @staticmethod
    def handle_confirm(
        db: Session,
        *,
        principal: CurrentPrincipal,
        action_id: str,
        confirmed: bool,
    ) -> AssistantChatOut:
        if not confirmed:
            return build_out(primary_message="Action cancelled. No changes were made.", confidence=1.0, intent="cancelled")

        body = verify_pending_action(action_id, org_id=principal.org_id, user_id=principal.user_id)
        if body is None:
            return build_out(
                primary_message="This confirmation link has expired or is invalid. Please start again.",
                confidence=1.0,
                blocking_reason="invalid_action_token",
            )

        action_type = str(body.get("action_type") or "")
        data = body.get("payload") or {}
        if action_type == "create_support_ticket" and customer_may_mutate(action_type):
            try:
                ticket = SupportTicketService.create_ticket(
                    db,
                    org_id=principal.org_id,
                    user_id=principal.user_id,
                    category=str(data.get("category") or "technical"),
                    subject=str(data.get("subject") or "Support request"),
                    message=str(data.get("message") or ""),
                )
            except ValueError as e:
                return build_out(primary_message=str(e), confidence=0.9, blocking_reason=str(e))
            ref = getattr(ticket, "public_ref", None) or str(ticket.id)
            return build_out(
                primary_message=f"Support ticket {ref} has been created. Our team will respond soon.",
                confidence=1.0,
                intent="create_ticket",
                highlight_type="ticket",
                highlight_id=str(ticket.id),
                highlight_label=str(ticket.subject)[:80],
                next_actions=[nav_action("view_ticket", "View ticket", "/account/support/tickets")],
            )

        return build_out(primary_message="Unknown action type.", confidence=0.5, blocking_reason="unknown_action")


def _handler_error_response(
    db: Session,
    *,
    principal: CurrentPrincipal,
    org: Organisation,
    message: str,
    intent: IntentMatch,
) -> AssistantChatOut:
    name = user_display_name(db, principal)
    if intent.intent == "wallet_low":
        try:
            return _handle_wallet_low(
                db,
                principal=principal,
                org=org,
                message=message,
                intent=intent,
                context=AssistantContextIn(),
                is_admin=False,
            )
        except Exception:
            logger.exception("assistant wallet_low recovery failed org=%s", principal.org_id)

    return build_out(
        primary_message=(
            f"Sorry {name}, I couldn't load that just now. "
            "Open Billing or Usage for the latest figures, or try your question again."
        ),
        confidence=0.4,
        intent=intent.intent,
        blocking_reason="temporary_data_error",
        next_actions=[
            nav_action("billing", "Open billing", "/account/billing"),
            nav_action("usage", "View usage", "/account/usage"),
        ],
    )


def _resolve_order_id(context: AssistantContextIn, message: str, orders: list[dict[str, Any]]) -> str | None:
    if context.order_id:
        return context.order_id
    uuid_match = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", message, re.I)
    if uuid_match:
        return uuid_match.group(0)
    if orders:
        return str(orders[0].get("id") or "") or None
    return None


def _handle_wallet_low(db, *, principal, org, message, intent, context, is_admin) -> AssistantChatOut:
    analysis = AssistantTools.wallet_low_analysis(db, org)
    wallet = analysis.get("wallet") or {}
    balance = wallet.get("wallet_balance_display") or wallet.get("wallet_balance_gbp") or "£0.00"
    h_type, h_id, h_label, explanation = AssistantTools.pick_charge_explanation(analysis)
    invoice_failed = bool(analysis.get("invoice_lookup_failed"))

    parts = [f"Your wallet balance is {balance}."]
    if invoice_failed:
        parts.append(INVOICE_READ_ERROR)
        parts.append(INVOICE_FALLBACK_HINT)
    if explanation:
        parts.append(explanation)

    usage_line = usage_summary_fragment(analysis.get("usage"))
    if usage_line:
        parts.append(usage_line)

    msg = " ".join(parts)
    actions = [
        nav_action("billing", "Open billing", "/account/billing"),
        nav_action("usage", "View usage", "/account/usage"),
    ]
    if h_type == "invoice" and h_id and not invoice_failed:
        actions.insert(0, nav_action("invoice", "View invoice", f"/account/billing?pay={h_id}"))
    elif h_type == "service_order" and h_id:
        actions.insert(0, nav_action("order", "View campaign", f"/surveys/{h_id}"))
    elif h_type == "wallet_transaction" and h_id:
        actions.insert(0, nav_action("wallet", "View wallet activity", "/account/billing"))

    blocking = INVOICE_READ_ERROR if invoice_failed else None
    return build_out(
        primary_message=msg,
        confidence=0.92 if not invoice_failed else 0.75,
        intent=intent.intent,
        highlight_type=h_type if h_id or h_type == "usage" else "",
        highlight_id=h_id or None,
        highlight_label=h_label,
        next_actions=actions,
        blocking_reason=blocking,
    )


def _handle_billing_overview(db, *, principal, org, message, intent, context, is_admin) -> AssistantChatOut:
    access, access_failed = run_tool("billing_access", lambda: AssistantTools.billing_access(db, org), default={})
    sub = BillingService.get_subscription(db, principal.org_id)
    plan = BillingService.resolve_active_plan(db, principal.org_id)
    sub_data = plan_subscription_dict(sub, plan)
    invoices, invoice_failed = run_tool("invoices", lambda: AssistantTools.invoices(db, principal.org_id, limit=5), default=[])
    outstanding = [i for i in invoices if str(i.get("status") or "").lower() not in {"paid", "void", "cancelled", "refunded"}]
    wallet_data, _ = run_tool("usage_summary", lambda: AssistantTools.usage_summary(db, org), default={})
    wallet = (wallet_data or {}).get("wallet") or {}
    balance = wallet.get("wallet_balance_display") or "£0.00"
    next_label = access.get("next_action_label") or access.get("next_action")
    plan_name = (sub_data.get("plan") or {}).get("name") or "No active plan"
    msg = f"Plan: {plan_name}. Wallet: {balance}."
    if outstanding and not invoice_failed:
        msg += f" You have {len(outstanding)} outstanding invoice(s)."
    elif invoice_failed:
        msg += f" {INVOICE_READ_ERROR} {INVOICE_FALLBACK_HINT}"
    if next_label and not access_failed:
        msg += f" Next step: {next_label}."
    highlight_id = str(outstanding[0].get("id")) if outstanding and not invoice_failed else None
    highlight_label = str(outstanding[0].get("invoice_number") or "Billing") if outstanding and not invoice_failed else "Billing overview"
    blocking = INVOICE_READ_ERROR if invoice_failed else (str(access.get("block_reason") or "") or None)
    return build_out(
        primary_message=msg,
        confidence=0.88 if not invoice_failed else 0.72,
        intent=intent.intent,
        highlight_type="invoice" if highlight_id else "usage",
        highlight_id=highlight_id,
        highlight_label=highlight_label,
        next_actions=[
            nav_action("billing", "Open billing", "/account/billing"),
            nav_action("usage", "View usage", "/account/usage"),
            *( [nav_action("pay", "Pay invoice", f"/account/billing?pay={highlight_id}")] if highlight_id else [] ),
        ],
        blocking_reason=blocking,
    )


def _handle_usage_summary(db, *, principal, org, message, intent, context, is_admin) -> AssistantChatOut:
    data = AssistantTools.usage_summary(db, org)
    monitor = data.get("billing_monitor") or {}
    status = monitor.get("status") or {}
    commercial = monitor.get("commercial") or {}
    remaining = commercial.get("package_remaining_display") or ""
    usage = data.get("usage") or {}
    calls = usage.get("calls") or {}
    wa = usage.get("whatsapp") or {}
    parts = []
    if calls:
        parts.append(f"AI calls: {calls.get('used', 0)}/{calls.get('included', 0)} min")
    if wa:
        parts.append(f"WA surveys: {wa.get('used', 0)}/{wa.get('included', 0)} recipients")
    if remaining:
        parts.append(f"Package remaining: {remaining}")
    msg = ". ".join(parts) if parts else "Usage data is not available for this period yet."
    return build_out(
        primary_message=msg,
        confidence=0.86,
        intent=intent.intent,
        highlight_type="usage",
        highlight_label="Usage summary",
        next_actions=[nav_action("usage", "View usage details", "/account/usage")],
        blocking_reason=status.get("next_action_label"),
    )


def _handle_launch_check(db, *, principal, org, message, intent, context, is_admin) -> AssistantChatOut:
    service_code = context.service_code or intent.service_code or "survey"
    orders = AssistantTools.list_service_orders(db, principal.org_id, service_code=service_code, limit=10)
    order_id = _resolve_order_id(context, message, orders)
    if not order_id:
        return build_out(
            primary_message="I need a campaign to check. Open Surveys or Interviews and try again with a campaign selected.",
            confidence=0.7,
            intent=intent.intent,
            next_actions=[nav_action("surveys", "View surveys", "/surveys"), nav_action("interviews", "View interviews", "/interviews")],
        )
    order_row = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order_row is None:
        return build_out(primary_message="Campaign not found.", confidence=0.9, blocking_reason="order_not_found")
    access = AssistantTools.billing_access(db, org)
    elig = AssistantTools.launch_eligibility(db, org, order_row)
    can = bool(elig.get("can_launch") or elig.get("launch_action") == "ready")
    block = elig.get("block_reason") or elig.get("summary") or access.get("next_action_label")
    title = order_row.title or "Campaign"
    if can:
        msg = f"✅ “{title}” looks ready to launch! Confirm recipients and payment, then launch from the campaign page 🚀"
    else:
        msg = f"⏳ “{title}” isn't ready to launch yet. {block or 'Check billing and campaign setup.'}"
    route = f"/surveys/new?order_id={order_id}" if service_code == "survey" else f"/interviews/{order_id}"
    return build_out(
        primary_message=msg,
        confidence=0.9,
        intent=intent.intent,
        highlight_type="service_order",
        highlight_id=order_id,
        highlight_label=title[:80],
        next_actions=[nav_action("open_order", "Open campaign", route)],
        blocking_reason=None if can else str(block or ""),
    )


def _handle_survey_results(db, *, principal, org, message, intent, context, is_admin) -> AssistantChatOut:
    orders = AssistantTools.list_service_orders(db, principal.org_id, service_code="survey", limit=15)
    order_id = _resolve_order_id(context, message, [o for o in orders if str(o.get("status") or "").lower() in {"completed", "running", "paused", "stopped"}] or orders)
    if not order_id:
        return build_out(
            primary_message="No survey campaign found. Create or finish a survey first.",
            confidence=0.75,
            intent=intent.intent,
            next_actions=[nav_action("surveys", "View surveys", "/surveys")],
        )
    order_row = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order_row is None:
        return build_out(primary_message="Survey not found.", confidence=0.9)
    try:
        results = AssistantTools.survey_results(db, order_row)
    except Exception:
        logger.exception("assistant survey_results failed order=%s", order_id)
        return build_out(
            primary_message="I'm having trouble loading survey results right now. Open the results page directly.",
            confidence=0.7,
            intent=intent.intent,
            highlight_type="service_order",
            highlight_id=order_id,
            highlight_label=(order_row.title or "Survey")[:80],
            blocking_reason="temporary_data_error",
            next_actions=[
                nav_action("results", "View results", "/surveys/results"),
                nav_action("order", "Open campaign", f"/surveys/new?order_id={order_id}"),
            ],
        )
    summary = results.get("summary") or {}
    completed = summary.get("completed_count") or results.get("completed_count") or 0
    total = summary.get("total_recipients") or results.get("total_recipients") or 0
    rate = summary.get("response_rate_percent") or results.get("response_rate") or 0
    title = order_row.title or "Survey"
    msg = f"“{title}”: {completed}/{total} responses ({rate}% response rate)."
    return build_out(
        primary_message=msg,
        confidence=0.88,
        intent=intent.intent,
        highlight_type="survey_result",
        highlight_id=order_id,
        highlight_label=title[:80],
        next_actions=[
            nav_action("results", "View results", "/surveys/results"),
            nav_action("order", "Open campaign", f"/surveys/new?order_id={order_id}"),
        ],
    )


def _handle_interview_results(db, *, principal, org, message, intent, context, is_admin) -> AssistantChatOut:
    orders = AssistantTools.list_service_orders(db, principal.org_id, service_code="interview", limit=15)
    order_id = _resolve_order_id(context, message, orders)
    if not order_id:
        return build_out(primary_message="No interview campaign found.", confidence=0.75, intent=intent.intent, next_actions=[nav_action("interviews", "View interviews", "/interviews")])
    order_row = ServiceOrderService.get_order(db, order_id, org_id=principal.org_id)
    if order_row is None:
        return build_out(primary_message="Interview not found.", confidence=0.9)
    results = AssistantTools.interview_results(db, order_row)
    title = results.get("title") or "Interview"
    msg = f"“{title}”: {results.get('completed_count', 0)}/{results.get('recipient_count', 0)} candidates interviewed."
    return build_out(
        primary_message=msg,
        confidence=0.88,
        intent=intent.intent,
        highlight_type="interview_result",
        highlight_id=order_id,
        highlight_label=title[:80],
        next_actions=[nav_action("results", "View results", f"/interviews/results/{order_id}")],
    )


def _handle_feedback_overview(db, *, principal, org, message, intent, context, is_admin) -> AssistantChatOut:
    locations = AssistantTools.feedback_locations(db, principal.org_id)
    loc_id = context.location_id
    results = AssistantTools.feedback_results(db, principal.org_id, location_id=loc_id)
    total_responses = int((results.get("summary") or {}).get("responses") or len(results.get("rows") or []))
    loc_count = len(locations)
    msg = f"Customer Feedback: {loc_count} location(s), {total_responses} recent response(s). This is separate from outbound WA Survey campaigns."
    h_id = loc_id or (str(locations[0].get("id")) if locations else None)
    h_label = str(locations[0].get("name") if locations else "Feedback results")
    return build_out(
        primary_message=msg,
        confidence=0.87,
        intent=intent.intent,
        highlight_type="feedback_location" if h_id else "",
        highlight_id=h_id,
        highlight_label=str(h_label)[:80] if h_id else None,
        next_actions=[
            nav_action("feedback", "View feedback", "/feedback/results"),
            nav_action("new_loc", "Add location", "/feedback/new"),
        ],
    )


def _handle_create_ticket(db, *, principal, org, message, intent, context, is_admin) -> AssistantChatOut:
    category = "invoices" if re.search(r"\b(invoice|bill|payment|refund)\b", message, re.I) else "technical"
    if re.search(r"\b(sales|demo|pricing|plan)\b", message, re.I):
        category = "pre-sale"
    subject = message[:200] if len(message) <= 200 else message[:197] + "..."
    token = issue_pending_action(
        org_id=principal.org_id,
        user_id=principal.user_id,
        action_type="create_support_ticket",
        payload={"category": category, "subject": subject, "message": message},
    )
    pending = AssistantPendingAction(
        action_id=token.split(":", 1)[0],
        action_type="create_support_ticket",
        summary=f"Create support ticket: {subject[:60]}",
        preview={"category": category, "subject": subject},
    )
    return build_out(
        primary_message="🎫 I can create a support ticket with your message. Please confirm to proceed.",
        confidence=0.84,
        intent=intent.intent,
        pending_action=pending,
        next_actions=[confirm_action("confirm_ticket", "Confirm create ticket", token)],
    )


def _handle_create_template(db, *, principal, org, message, intent, context, is_admin) -> AssistantChatOut:
    name = user_display_name(db, principal)
    msg = (
        f"Hey {name}! ✨ Let's build your custom WhatsApp template:\n\n"
        "1️⃣ Open Create Survey and pick the WhatsApp channel\n"
        "2️⃣ In Step 3, choose Custom template for each survey type\n"
        "3️⃣ Write your welcome, questions, and thank-you messages\n"
        "4️⃣ Save your draft — Meta approval comes before launch 🚀\n\n"
        "Designing templates is free; launching uses your package or wallet when you're ready."
    )
    blocking, _suffix = billing_note_for_intent(fetch_billing_access(db, org), intent.intent)
    return build_out(
        primary_message=msg,
        confidence=0.9,
        intent=intent.intent,
        highlight_type="service_order",
        highlight_label="Custom WA template",
        next_actions=[
            nav_action("wizard", "Open template wizard", "/surveys/new?channel=whatsapp"),
            nav_action("surveys", "View surveys", "/surveys"),
        ],
        blocking_reason=blocking,
    )


def _handle_create_survey(db, *, principal, org, message, intent, context, is_admin) -> AssistantChatOut:
    channel = "whatsapp" if re.search(r"\b(whatsapp|wa)\b", message, re.I) else "ai_call" if re.search(r"\b(phone|call)\b", message, re.I) else None
    if not channel:
        return build_out(
            primary_message="To create a survey, choose WhatsApp or phone channel first. AI Survey is outbound; Customer Feedback (QR) is a separate product.",
            confidence=0.82,
            intent=intent.intent,
            next_actions=[
                nav_action("wa", "WhatsApp survey", "/surveys/new?channel=whatsapp"),
                nav_action("phone", "Phone survey", "/surveys/new?channel=phone"),
            ],
        )
    return build_out(
        primary_message=f"Open the survey wizard to create a new {'WhatsApp' if channel == 'whatsapp' else 'phone'} survey. I will not launch until you confirm on the campaign page.",
        confidence=0.85,
        intent=intent.intent,
        next_actions=[nav_action("wizard", "Create survey", f"/surveys/new?channel={channel}")],
    )


def _handle_create_feedback(db, *, principal, org, message, intent, context, is_admin) -> AssistantChatOut:
    return build_out(
        primary_message="Customer Feedback uses QR-triggered inbound WhatsApp — separate from outbound surveys. Ensure your feedback subscription is active, then add a location.",
        confidence=0.85,
        intent=intent.intent,
        next_actions=[
            nav_action("feedback_pkgs", "Feedback packages", "/account/feedback/packages"),
            nav_action("new_loc", "Add location", "/feedback/new"),
        ],
    )


def _handle_product_compare(db, *, principal, org, message, intent, context, is_admin) -> AssistantChatOut:
    return build_out(
        primary_message=(
            "AI Survey sends outbound phone/WhatsApp campaigns to a contact list (ServiceOrder). "
            "Customer Feedback collects inbound QR-triggered WhatsApp at physical locations — separate billing and data. "
            "AI Interview screens candidates via phone interviews. Which product do you need?"
        ),
        confidence=0.95,
        intent=intent.intent,
    )


def _handle_list_surveys(db, *, principal, org, message, intent, context, is_admin) -> AssistantChatOut:
    orders = AssistantTools.list_service_orders(db, principal.org_id, service_code="survey", limit=10)
    if not orders:
        return build_out(primary_message="You have no survey campaigns yet.", confidence=0.8, intent=intent.intent, next_actions=[nav_action("new", "Create survey", "/surveys/new")])
    live = [o for o in orders if o.get("is_live") or str(o.get("status") or "").lower() in {"running", "paused", "draft", "quoted"}]
    first = (live or orders)[0]
    title = first.get("title") or "Survey"
    msg = f"You have {len(orders)} survey campaign(s). Latest: “{title}” ({first.get('status_label') or first.get('status')})."
    return build_out(
        primary_message=msg,
        confidence=0.82,
        intent=intent.intent,
        highlight_type="service_order",
        highlight_id=str(first.get("id")),
        highlight_label=title[:80],
        next_actions=[nav_action("surveys", "View all surveys", "/surveys")],
    )


def _handle_list_interviews(db, *, principal, org, message, intent, context, is_admin) -> AssistantChatOut:
    orders = AssistantTools.list_service_orders(db, principal.org_id, service_code="interview", limit=10)
    if not orders:
        return build_out(primary_message="You have no interview campaigns yet.", confidence=0.8, intent=intent.intent, next_actions=[nav_action("new", "Create interview", "/interviews/new")])
    first = orders[0]
    title = first.get("title") or "Interview"
    msg = f"You have {len(orders)} interview campaign(s). Latest: “{title}”."
    return build_out(
        primary_message=msg,
        confidence=0.82,
        intent=intent.intent,
        highlight_type="service_order",
        highlight_id=str(first.get("id")),
        highlight_label=title[:80],
        next_actions=[nav_action("interviews", "View interviews", "/interviews")],
    )


def _handle_general(db, *, principal, org, message, intent, context, is_admin) -> AssistantChatOut:
    name = user_display_name(db, principal)

    if is_greeting(message):
        return build_out(
            primary_message=(
                f"Hi {name}! 👋 I'm your VoxBulk assistant. "
                "Ask about your wallet, usage, campaigns, customer feedback, or support."
            ),
            confidence=0.9,
            intent="greeting",
            next_actions=[
                nav_action("billing", "Open billing", "/account/billing"),
                nav_action("usage", "View usage", "/account/usage"),
            ],
        )

    return build_out(
        primary_message=(
            f"Hi {name}! 🤔 I didn't quite match that. "
            "Try “Why is my wallet low?”, “Can I launch?”, or “Show survey results”."
        ),
        confidence=0.45,
        intent=intent.intent,
        next_actions=[
            nav_action("billing", "Open billing", "/account/billing"),
            nav_action("usage", "View usage", "/account/usage"),
        ],
    )


_HANDLERS = {
    "wallet_low": _handle_wallet_low,
    "billing_overview": _handle_billing_overview,
    "usage_summary": _handle_usage_summary,
    "launch_check": _handle_launch_check,
    "survey_results": _handle_survey_results,
    "interview_results": _handle_interview_results,
    "feedback_overview": _handle_feedback_overview,
    "create_ticket": _handle_create_ticket,
    "create_template": _handle_create_template,
    "create_survey": _handle_create_survey,
    "create_feedback": _handle_create_feedback,
    "product_compare": _handle_product_compare,
    "list_surveys": _handle_list_surveys,
    "list_interviews": _handle_list_interviews,
    "general_help": _handle_general,
    "unknown": _handle_general,
}
