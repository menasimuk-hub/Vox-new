"""Dashboard route catalog — single source of truth for assistant navigation and prompts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DashboardCatalogEntry:
    id: str
    title: str
    route: str
    description: str
    service_key: str | None = None
    example_questions: tuple[str, ...] = ()
    read_tools: tuple[str, ...] = ()


CATALOG: tuple[DashboardCatalogEntry, ...] = (
    DashboardCatalogEntry("home", "Dashboard home", "/", "Overview KPIs and quick links to your modules."),
    DashboardCatalogEntry("interviews", "Interviews", "/interviews", "Saved AI phone screening campaigns.", "interviews", ("List my interviews",), ("list_service_orders",)),
    DashboardCatalogEntry("interviews_new", "Create interview", "/interviews/new", "Wizard to create a new AI phone interview campaign.", "interviews", ("Create an interview",), ()),
    DashboardCatalogEntry("interview_results", "Interview results", "/interviews/results", "Candidate completion stats.", "interviews", ("Interview results",), ("interview_results",)),
    DashboardCatalogEntry("interview_reports", "Interview reports", "/interviews/reports", "Performance reports and exports.", "interviews", ("Interview reports",), ()),
    DashboardCatalogEntry("surveys", "Surveys", "/surveys", "Saved AI call and WhatsApp survey campaigns.", "surveys", ("List my surveys",), ("list_service_orders",)),
    DashboardCatalogEntry("surveys_new", "Create survey", "/surveys/new", "Wizard for phone or WhatsApp outbound surveys.", "surveys", ("Create a survey",), ()),
    DashboardCatalogEntry("survey_results", "Survey results", "/surveys/results", "NPS, response rates, and completion summaries.", "surveys", ("Survey results", "Show NPS"), ("survey_results",)),
    DashboardCatalogEntry("survey_reports", "Survey reports", "/surveys/reports", "Campaign performance reports.", "surveys", ("Survey reports",), ()),
    DashboardCatalogEntry("feedback", "Customer feedback", "/feedback", "QR-triggered WhatsApp feedback locations.", "feedback", ("Customer feedback",), ("feedback_locations",)),
    DashboardCatalogEntry("feedback_new", "Create QR feedback", "/feedback/new", "Add a new QR feedback location.", "feedback", ("Create feedback location",), ()),
    DashboardCatalogEntry("feedback_results", "Feedback results", "/feedback/results", "Responses from QR feedback locations.", "feedback", ("Feedback results",), ("feedback_results",)),
    DashboardCatalogEntry("campaigns", "Campaign templates", "/campaigns", "WhatsApp broadcast template library.", "campaigns", ("My campaign templates",), ()),
    DashboardCatalogEntry("campaigns_new", "Create campaign template", "/campaigns/new", "Design a Meta-approved broadcast template.", "campaigns", ("Create campaign template",), ()),
    DashboardCatalogEntry("campaigns_send", "Send campaign", "/campaigns/send", "Send a broadcast to an audience.", "campaigns", ("Send broadcast",), ()),
    DashboardCatalogEntry("recovery", "Recovery", "/recovery", "Missed-appointment recovery queue.", "recovery", ("Recovery queue",), ()),
    DashboardCatalogEntry("recovery_noshow", "No-show follow-up", "/recovery/no-show", "AI calling for missed appointments.", "recovery", ("No-show follow up",), ()),
    DashboardCatalogEntry("recovery_emergency", "Emergency reschedule", "/recovery/emergency", "Mass cancel and rebook workflows.", "recovery", ("Emergency reschedule",), ()),
    DashboardCatalogEntry("recovery_recall", "Recall campaigns", "/recovery/recall", "Dental recall outreach.", "recovery", ("Recall campaigns",), ()),
    DashboardCatalogEntry("recovery_offers", "Offer campaigns", "/recovery/offers", "Promotional fill outreach.", "recovery", ("Offer campaigns",), ()),
    DashboardCatalogEntry("followup", "Follow up", "/follow-up", "WhatsApp appointment reminder sequences.", "followup", ("Follow up reminders",), ()),
    DashboardCatalogEntry("settings_profile", "Profile settings", "/settings/profile", "Company name, logo, and contact details.", None, ("Update company profile",), ()),
    DashboardCatalogEntry("settings_services", "Services", "/settings/services", "Turn dashboard modules on or off in the sidebar.", None, ("Change my services",), ()),
    DashboardCatalogEntry("settings_integrations", "Integrations", "/settings/integrations", "HubSpot, scheduling, and messaging integrations.", None, ("Integrations",), ()),
    DashboardCatalogEntry("settings_team", "Team members", "/settings/team", "Invite colleagues and manage roles.", None, ("Invite team member",), ()),
    DashboardCatalogEntry("settings_optout", "Opt-out list", "/settings/opt-out", "Do-not-contact numbers.", None, ("Opt out list",), ()),
    DashboardCatalogEntry("settings_audit", "Audit log", "/settings/audit", "Compliance and activity audit trail.", None, ("Audit log",), ()),
    DashboardCatalogEntry("account_packages", "Packages & pricing", "/account/packages", "Plans, bundles, and subscription options.", None, ("My plan", "Pricing"), ("billing_subscription",)),
    DashboardCatalogEntry("account_feedback_packages", "Feedback plans", "/account/feedback/packages", "QR feedback subscription packages.", "feedback", ("Feedback subscription",), ("feedback_subscription",)),
    DashboardCatalogEntry("account_billing", "Billing", "/account/billing", "Wallet, invoices, and subscription.", None, ("Show my billing", "Why is my wallet low?"), ("billing_access", "wallet")),
    DashboardCatalogEntry("account_usage", "Usage", "/account/usage", "Plan allowance and campaign usage breakdown.", None, ("What's my usage?",), ("usage_summary", "usage_breakdown")),
    DashboardCatalogEntry("account_support", "Support", "/account/support", "Help hub — FAQ, tickets, and assistant.", None, ("Get support",), ()),
    DashboardCatalogEntry("account_support_faq", "FAQ", "/account/support/faq", "Documentation and FAQs.", None, ("FAQ",), ()),
    DashboardCatalogEntry("account_support_tickets", "Support tickets", "/account/support/tickets", "Your email support conversations.", None, ("My support tickets",), ("list_tickets",)),
)


def catalog_for_prompt(*, enabled_services: list[str] | None = None) -> list[DashboardCatalogEntry]:
    enabled = {str(s).strip().lower() for s in (enabled_services or []) if str(s).strip()}
    if not enabled:
        return list(CATALOG)
    return [e for e in CATALOG if e.service_key is None or e.service_key in enabled]


def catalog_prompt_block(*, enabled_services: list[str] | None = None) -> str:
    lines = ["Dashboard pages (read-only — direct users here):"]
    for entry in catalog_for_prompt(enabled_services=enabled_services):
        ex = "; ".join(entry.example_questions[:2])
        suffix = f" Examples: {ex}." if ex else ""
        lines.append(f"- {entry.title} ({entry.route}): {entry.description}{suffix}")
    return "\n".join(lines)


def example_questions_for_user(*, enabled_services: list[str] | None = None, limit: int = 6) -> list[str]:
    seen: list[str] = []
    for entry in catalog_for_prompt(enabled_services=enabled_services):
        for q in entry.example_questions:
            if q not in seen:
                seen.append(q)
            if len(seen) >= limit:
                return seen
    return seen
