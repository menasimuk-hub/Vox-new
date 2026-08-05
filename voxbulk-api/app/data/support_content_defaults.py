"""Insert-missing-only support content defaults keyed to Task2 product groups.

Never overwrite Admin-edited bodies. Optional keys (appointments / recovery / follow_up)
are only seeded when those platform product groups exist.
"""

from __future__ import annotations

from typing import Any

DASH = "https://dashboard.voxbulk.com"
PUBLIC = "https://voxbulk.com"

# Product keys that are only seeded when the platform group row exists.
OPTIONAL_PRODUCT_KEYS = frozenset({"appointments", "recovery", "follow_up"})

# Always considered for seed when present in DEFAULT_PRODUCT_GROUPS / DB.
CORE_PRODUCT_KEYS = frozenset(
    {
        "interview",
        "survey",
        "customer_feedback",
        "expo",
        "smart_card",
        "campaigns",
        "shared",
    }
)


def _faq(
    slug: str,
    question: str,
    answer: str,
    *,
    sort_order: int = 10,
) -> dict[str, Any]:
    return {"slug": slug, "question": question, "answer": answer, "sort_order": sort_order}


DASHBOARD_FAQ_CATEGORIES: list[dict[str, Any]] = [
    {
        "slug": "dash-interview",
        "name": "AI Interview / Recruitment",
        "linked_service": "interview",
        "sort_order": 10,
        "items": [
            _faq(
                "dash-interview-setup",
                "How do I launch my first AI interview campaign?",
                f"Open {DASH}/interviews, create a campaign, upload candidates, generate and approve the script, set the calling window, then launch. Candidates book a slot and Leo dials at the booked time. Public overview: {PUBLIC}/recruitment",
                sort_order=10,
            ),
            _faq(
                "dash-interview-no-call",
                "A candidate booked but the AI never called — what should I check?",
                f"Confirm the calling window is still active, the number is E.164 (+44…), the candidate is not on your opt-out list, and UK dialling hours (Europe/London) allow the call. Escalate via {DASH}/account/support/tickets if the slot was inside the window.",
                sort_order=20,
            ),
            _faq(
                "dash-interview-billing",
                "How is interview usage billed?",
                f"Interview minutes and CV scans draw from your plan / wallet. Check live usage on {DASH}/account/billing and {DASH}/account/usage. For plan changes or invoice issues, open a ticket from {DASH}/account/support/tickets.",
                sort_order=30,
            ),
        ],
    },
    {
        "slug": "dash-survey",
        "name": "WhatsApp Surveys",
        "linked_service": "survey",
        "sort_order": 20,
        "items": [
            _faq(
                "dash-survey-setup",
                "How do I create and send a WhatsApp survey?",
                f"Go to {DASH}/surveys, create or pick a survey type, approve WhatsApp templates if needed, upload recipients, then launch. Product page: {PUBLIC}/surveys",
                sort_order=10,
            ),
            _faq(
                "dash-survey-undelivered",
                "Messages are not delivering — common causes?",
                f"Check template approval status, recipient opt-outs, and that the WhatsApp number/profile is healthy. Review results in {DASH}/surveys. Still stuck? {DASH}/account/support/tickets",
                sort_order=20,
            ),
            _faq(
                "dash-survey-billing",
                "How do WhatsApp survey credits work?",
                f"Conversation and AI voice usage appear under Account → Billing / Usage ({DASH}/account/billing). Escalate billing disputes via {DASH}/account/support/tickets.",
                sort_order=30,
            ),
        ],
    },
    {
        "slug": "dash-feedback",
        "name": "Customer Feedback",
        "linked_service": "customer_feedback",
        "sort_order": 30,
        "items": [
            _faq(
                "dash-feedback-setup",
                "How do I set up Customer Feedback QR codes?",
                f"Open {DASH}/feedback, create a location / QR, customise questions, then print or share the code. Overview: {PUBLIC}/feedback",
                sort_order=10,
            ),
            _faq(
                "dash-feedback-troubleshoot",
                "Scans are not recording — what should I try?",
                f"Confirm the QR is active, questions are published, and you are viewing the correct location in {DASH}/feedback. Contact support at {DASH}/account/support/tickets if scans still do not appear.",
                sort_order=20,
            ),
            _faq(
                "dash-feedback-billing",
                "How is Customer Feedback billed?",
                f"Feedback packs and overage show on {DASH}/account/billing. For invoice questions open {DASH}/account/support/tickets.",
                sort_order=30,
            ),
        ],
    },
    {
        "slug": "dash-expo",
        "name": "VoxBulk Expo",
        "linked_service": "expo",
        "sort_order": 40,
        "items": [
            _faq(
                "dash-expo-setup",
                "How do I run an Expo booth campaign?",
                f"Create a campaign under {DASH}/expo, configure fields and branding, then display the QR/link on the stand. Leads appear under Expo → Leads. Public page: {PUBLIC}/expo",
                sort_order=10,
            ),
            _faq(
                "dash-expo-troubleshoot",
                "Visitors can open the form but leads are missing",
                f"Check the campaign is published, consent fields are valid, and you are looking at the correct event in {DASH}/expo. Escalate via {DASH}/account/support/tickets.",
                sort_order=20,
            ),
            _faq(
                "dash-expo-billing",
                "Where do I manage Expo packages?",
                f"Packages and capacity sit under Account → Expo packages and {DASH}/account/billing. Need a billing change? {DASH}/account/support/tickets",
                sort_order=30,
            ),
        ],
    },
    {
        "slug": "dash-smart-card",
        "name": "Smart Card QR",
        "linked_service": "smart_card",
        "sort_order": 50,
        "items": [
            _faq(
                "dash-smart-card-setup",
                "How do I create a Smart Card QR for a sales rep?",
                f"Open {DASH}/smart-card, add a representative, configure catalogue/questions if needed, then download the QR. Public overview: {PUBLIC}/smart-card",
                sort_order=10,
            ),
            _faq(
                "dash-smart-card-troubleshoot",
                "Prospects scan but no lead appears",
                f"Confirm the representative QR is active and the landing form completes successfully. Review leads in {DASH}/smart-card. Still empty? {DASH}/account/support/tickets",
                sort_order=20,
            ),
            _faq(
                "dash-smart-card-billing",
                "How do Smart Card packages work?",
                f"Manage capacity under Account → Smart Card packages and {DASH}/account/billing. Escalate billing via {DASH}/account/support/tickets.",
                sort_order=30,
            ),
        ],
    },
    {
        "slug": "dash-campaigns",
        "name": "Broadcast campaigns",
        "linked_service": "campaigns",
        "sort_order": 60,
        "items": [
            _faq(
                "dash-campaigns-setup",
                "How do I send a WhatsApp broadcast campaign?",
                f"Use {DASH}/campaigns to pick an approved template, upload contacts with consent, then launch. Monitor delivery in campaign results.",
                sort_order=10,
            ),
            _faq(
                "dash-campaigns-consent",
                "What consent is required before broadcasting?",
                f"Only message contacts who opted in for that purpose. STOP replies are respected automatically. Policy questions: {PUBLIC}/help or {DASH}/account/support/tickets.",
                sort_order=20,
            ),
            _faq(
                "dash-campaigns-billing",
                "How are campaign sends billed?",
                f"Usage appears on {DASH}/account/billing. For overage or invoice help open {DASH}/account/support/tickets.",
                sort_order=30,
            ),
        ],
    },
    {
        "slug": "dash-shared",
        "name": "Account, billing & support",
        "linked_service": "shared",
        "sort_order": 100,
        "items": [
            _faq(
                "dash-shared-billing",
                "Where do I view invoices, wallet and Direct Debit?",
                f"Everything lives under {DASH}/account/billing. Card top-ups, invoices and GoCardless mandates are managed there.",
                sort_order=10,
            ),
            _faq(
                "dash-shared-ticket",
                "How do I contact VoxBulk support?",
                f"Open {DASH}/account/support/tickets to create or reply to an email ticket, or browse docs at {DASH}/account/support/faq and {PUBLIC}/help.",
                sort_order=20,
            ),
            _faq(
                "dash-shared-escalation",
                "When should I escalate a billing or outage issue?",
                f"If wallet credit did not apply, a mandate failed, or a service is down after self-serve checks, raise a ticket at {DASH}/account/support/tickets with the invoice or campaign reference.",
                sort_order=30,
            ),
        ],
    },
    # Optional — only inserted when platform product group exists
    {
        "slug": "dash-appointments",
        "name": "Appointments",
        "linked_service": "appointments",
        "sort_order": 70,
        "optional": True,
        "items": [
            _faq(
                "dash-appointments-setup",
                "How do appointment confirmations work?",
                f"Configure Appointments under {DASH}/appointments so WhatsApp / AI call confirmations follow your booking CRM. Docs: {DASH}/account/support/faq",
                sort_order=10,
            ),
            _faq(
                "dash-appointments-troubleshoot",
                "Confirmations are not sending",
                f"Check integrations and service toggles in Settings, then review {DASH}/appointments. Escalate via {DASH}/account/support/tickets.",
                sort_order=20,
            ),
        ],
    },
    {
        "slug": "dash-recovery",
        "name": "Recovery",
        "linked_service": "recovery",
        "sort_order": 80,
        "optional": True,
        "items": [
            _faq(
                "dash-recovery-setup",
                "What is the Recovery queue for?",
                f"Use {DASH}/recovery for no-show follow-up, emergency reschedule and recall outreach when those modules are enabled for your organisation.",
                sort_order=10,
            ),
            _faq(
                "dash-recovery-troubleshoot",
                "Recovery calls are not dialling",
                f"Confirm the recovery campaign is active and numbers are valid, then check {DASH}/recovery. Support: {DASH}/account/support/tickets",
                sort_order=20,
            ),
        ],
    },
    {
        "slug": "dash-follow-up",
        "name": "Follow-up reminders",
        "linked_service": "follow_up",
        "sort_order": 90,
        "optional": True,
        "items": [
            _faq(
                "dash-follow-up-setup",
                "How do appointment follow-up reminders work?",
                f"Configure sequences under {DASH}/follow-up so WhatsApp reminders go out before appointments. Enable the module in Settings → Services if it is missing.",
                sort_order=10,
            ),
            _faq(
                "dash-follow-up-troubleshoot",
                "Reminders stopped sending",
                f"Check opt-outs, template status and that Follow-up is enabled. Review {DASH}/follow-up or open {DASH}/account/support/tickets.",
                sort_order=20,
            ),
        ],
    },
]

CANNED_CATEGORIES: list[dict[str, Any]] = [
    {
        "slug": "canned-interview",
        "name": "Interview / Recruitment",
        "linked_service": "interview",
        "description": "Replies for AI interview campaigns.",
        "replies": [
            {
                "seed_key": "canned-interview-setup",
                "title": "Interview — getting started",
                "question": "How do I start with AI interviews?",
                "answer": f"Thanks for getting in touch. To launch interviews: open {DASH}/interviews → create a campaign → upload candidates → approve the script → set the calling window → launch. More detail: {DASH}/account/support/faq and {PUBLIC}/recruitment",
            },
            {
                "seed_key": "canned-interview-escalate",
                "title": "Interview — escalation",
                "question": "Interview billing or outage",
                "answer": f"Sorry you hit this. Please reply with the campaign name/ID and roughly when it happened. Meanwhile check usage on {DASH}/account/billing. We'll investigate and update this ticket.",
            },
        ],
    },
    {
        "slug": "canned-survey",
        "name": "WhatsApp Surveys",
        "linked_service": "survey",
        "description": "Replies for WhatsApp survey campaigns.",
        "replies": [
            {
                "seed_key": "canned-survey-setup",
                "title": "Survey — getting started",
                "question": "How do WhatsApp surveys work?",
                "answer": f"Create and launch surveys from {DASH}/surveys. Templates must be approved before high-volume sends. Guides: {DASH}/account/support/faq · {PUBLIC}/surveys",
            },
            {
                "seed_key": "canned-survey-undelivered",
                "title": "Survey — delivery issues",
                "question": "Messages not delivering",
                "answer": f"Please share the survey/order reference. Common causes: template not approved, recipient opt-out, or profile health. You can also review results in {DASH}/surveys while we check our side.",
            },
        ],
    },
    {
        "slug": "canned-feedback",
        "name": "Customer Feedback",
        "linked_service": "customer_feedback",
        "description": "Replies for QR customer feedback.",
        "replies": [
            {
                "seed_key": "canned-feedback-setup",
                "title": "Feedback — setup",
                "question": "How do I set up feedback QR?",
                "answer": f"Manage locations and QR codes under {DASH}/feedback. Public overview: {PUBLIC}/feedback. Docs: {DASH}/account/support/faq",
            },
            {
                "seed_key": "canned-feedback-escalate",
                "title": "Feedback — escalation",
                "question": "Scans missing / billing",
                "answer": f"Thanks — please send the location name and approximate scan times. Check {DASH}/feedback meanwhile. Billing questions: {DASH}/account/billing.",
            },
        ],
    },
    {
        "slug": "canned-expo",
        "name": "Expo",
        "linked_service": "expo",
        "description": "Replies for Expo booth lead capture.",
        "replies": [
            {
                "seed_key": "canned-expo-setup",
                "title": "Expo — setup",
                "question": "How do I run Expo?",
                "answer": f"Create the event under {DASH}/expo, publish the QR/link for the stand, then review leads in Expo → Leads. Overview: {PUBLIC}/expo",
            },
            {
                "seed_key": "canned-expo-escalate",
                "title": "Expo — escalation",
                "question": "Leads missing",
                "answer": f"Please share the Expo campaign name and when visitors submitted. Confirm the campaign is published in {DASH}/expo — we'll dig in from there.",
            },
        ],
    },
    {
        "slug": "canned-smart-card",
        "name": "Smart Card",
        "linked_service": "smart_card",
        "description": "Replies for Smart Card QR.",
        "replies": [
            {
                "seed_key": "canned-smart-card-setup",
                "title": "Smart Card — setup",
                "question": "How do Smart Cards work?",
                "answer": f"Add representatives and download QRs from {DASH}/smart-card. Overview: {PUBLIC}/smart-card · FAQ: {DASH}/account/support/faq",
            },
            {
                "seed_key": "canned-smart-card-escalate",
                "title": "Smart Card — escalation",
                "question": "Leads / packages",
                "answer": f"Please share the representative name and when the scan happened. Manage packages under Account → Smart Card packages; billing is on {DASH}/account/billing.",
            },
        ],
    },
    {
        "slug": "canned-campaigns",
        "name": "Campaigns",
        "linked_service": "campaigns",
        "description": "Replies for broadcast campaigns.",
        "replies": [
            {
                "seed_key": "canned-campaigns-setup",
                "title": "Campaigns — setup",
                "question": "How do broadcasts work?",
                "answer": f"Launch approved template broadcasts from {DASH}/campaigns with consented contacts. Docs: {DASH}/account/support/faq",
            },
            {
                "seed_key": "canned-campaigns-escalate",
                "title": "Campaigns — escalation",
                "question": "Delivery / billing",
                "answer": f"Please share the campaign ID and send window. Check delivery in {DASH}/campaigns and usage on {DASH}/account/billing while we investigate.",
            },
        ],
    },
    {
        "slug": "canned-shared",
        "name": "Account & billing",
        "linked_service": "shared",
        "description": "Shared account, billing and escalation replies.",
        "replies": [
            {
                "seed_key": "canned-shared-billing",
                "title": "Billing overview",
                "question": "Where is billing?",
                "answer": f"Invoices, wallet top-ups and Direct Debit are under {DASH}/account/billing. If something looks wrong, reply on this ticket with the invoice number.",
            },
            {
                "seed_key": "canned-shared-help",
                "title": "Help centre pointers",
                "question": "Where is documentation?",
                "answer": f"Dashboard docs: {DASH}/account/support/faq · Public help: {PUBLIC}/help · Contact form: {PUBLIC}/contact",
            },
        ],
    },
    {
        "slug": "canned-appointments",
        "name": "Appointments",
        "linked_service": "appointments",
        "optional": True,
        "description": "Appointment confirmation support.",
        "replies": [
            {
                "seed_key": "canned-appointments-setup",
                "title": "Appointments — setup",
                "question": "Appointments help",
                "answer": f"Configure confirmation workflows under {DASH}/appointments. If something is missing from the sidebar, enable it in Settings → Services.",
            },
        ],
    },
    {
        "slug": "canned-recovery",
        "name": "Recovery",
        "linked_service": "recovery",
        "optional": True,
        "description": "Missed-appointment recovery support.",
        "replies": [
            {
                "seed_key": "canned-recovery-setup",
                "title": "Recovery — setup",
                "question": "Recovery help",
                "answer": f"Use {DASH}/recovery for no-show and recall workflows when the module is enabled. Share the campaign name if you need us to investigate.",
            },
        ],
    },
    {
        "slug": "canned-follow-up",
        "name": "Follow-up",
        "linked_service": "follow_up",
        "optional": True,
        "description": "Appointment reminder follow-up support.",
        "replies": [
            {
                "seed_key": "canned-follow-up-setup",
                "title": "Follow-up — setup",
                "question": "Follow-up help",
                "answer": f"Reminder sequences are managed at {DASH}/follow-up. Confirm the module is enabled, then share the sequence name if reminders stopped.",
            },
        ],
    },
]

KB_CATEGORIES: list[dict[str, Any]] = [
    {
        "slug": "kb-interview",
        "name": "Interview / Recruitment",
        "linked_service": "interview",
        "description": "Help centre articles for AI interviews.",
        "sort_order": 10,
        "articles": [
            {
                "slug": "kb-interview-setup",
                "title": "Set up an AI interview campaign",
                "body": f"## Setup\n1. Open {DASH}/interviews\n2. Create a campaign and upload CVs\n3. Generate, edit and approve the script\n4. Set the calling window and launch\n\nPublic overview: {PUBLIC}/recruitment\nDashboard FAQ: {DASH}/account/support/faq",
            },
            {
                "slug": "kb-interview-troubleshoot",
                "title": "Interview troubleshooting & escalation",
                "body": f"## Common checks\n- Calling window still active\n- Valid E.164 numbers\n- Not on opt-out list\n- UK dialling hours\n\nBilling: {DASH}/account/billing\nEscalate: {DASH}/account/support/tickets",
            },
        ],
    },
    {
        "slug": "kb-survey",
        "name": "WhatsApp Surveys",
        "linked_service": "survey",
        "description": "Help centre articles for WhatsApp surveys.",
        "sort_order": 20,
        "articles": [
            {
                "slug": "kb-survey-setup",
                "title": "Launch a WhatsApp survey",
                "body": f"## Setup\n1. {DASH}/surveys → create / select survey\n2. Ensure WhatsApp templates are approved\n3. Upload recipients and launch\n\n{PUBLIC}/surveys · {DASH}/account/support/faq",
            },
            {
                "slug": "kb-survey-troubleshoot",
                "title": "Survey delivery troubleshooting",
                "body": f"Check template status, opt-outs and results in {DASH}/surveys. Billing on {DASH}/account/billing. Tickets: {DASH}/account/support/tickets",
            },
        ],
    },
    {
        "slug": "kb-feedback",
        "name": "Customer Feedback",
        "linked_service": "customer_feedback",
        "description": "Help centre articles for customer feedback.",
        "sort_order": 30,
        "articles": [
            {
                "slug": "kb-feedback-setup",
                "title": "Customer Feedback QR setup",
                "body": f"Create locations and print QR codes from {DASH}/feedback. Overview: {PUBLIC}/feedback",
            },
            {
                "slug": "kb-feedback-troubleshoot",
                "title": "Feedback scans & billing",
                "body": f"If scans are missing, confirm the QR is active in {DASH}/feedback. Billing: {DASH}/account/billing · Support: {DASH}/account/support/tickets",
            },
        ],
    },
    {
        "slug": "kb-expo",
        "name": "Expo",
        "linked_service": "expo",
        "description": "Help centre articles for Expo.",
        "sort_order": 40,
        "articles": [
            {
                "slug": "kb-expo-setup",
                "title": "Run an Expo booth campaign",
                "body": f"Create and publish under {DASH}/expo. Public page: {PUBLIC}/expo",
            },
            {
                "slug": "kb-expo-troubleshoot",
                "title": "Expo leads & packages",
                "body": f"Review leads in {DASH}/expo. Packages and billing: {DASH}/account/billing. Escalate: {DASH}/account/support/tickets",
            },
        ],
    },
    {
        "slug": "kb-smart-card",
        "name": "Smart Card",
        "linked_service": "smart_card",
        "description": "Help centre articles for Smart Card QR.",
        "sort_order": 50,
        "articles": [
            {
                "slug": "kb-smart-card-setup",
                "title": "Create Smart Card QRs",
                "body": f"Manage representatives at {DASH}/smart-card. Overview: {PUBLIC}/smart-card",
            },
            {
                "slug": "kb-smart-card-troubleshoot",
                "title": "Smart Card leads & billing",
                "body": f"Check leads in {DASH}/smart-card. Billing: {DASH}/account/billing · Tickets: {DASH}/account/support/tickets",
            },
        ],
    },
    {
        "slug": "kb-campaigns",
        "name": "Campaigns",
        "linked_service": "campaigns",
        "description": "Help centre articles for broadcasts.",
        "sort_order": 60,
        "articles": [
            {
                "slug": "kb-campaigns-setup",
                "title": "Send a broadcast campaign",
                "body": f"Use approved templates from {DASH}/campaigns with consented contacts only.",
            },
            {
                "slug": "kb-campaigns-troubleshoot",
                "title": "Campaign delivery & billing",
                "body": f"Monitor results in {DASH}/campaigns. Usage: {DASH}/account/billing. Help: {PUBLIC}/help",
            },
        ],
    },
    {
        "slug": "kb-shared",
        "name": "Account & support",
        "linked_service": "shared",
        "description": "Shared account and support articles.",
        "sort_order": 100,
        "articles": [
            {
                "slug": "kb-shared-billing",
                "title": "Billing, wallet and Direct Debit",
                "body": f"Manage invoices and payments at {DASH}/account/billing. Need help? {DASH}/account/support/tickets or {PUBLIC}/contact",
            },
            {
                "slug": "kb-shared-support",
                "title": "How to get support",
                "body": f"Docs: {DASH}/account/support/faq · Tickets: {DASH}/account/support/tickets · Public help: {PUBLIC}/help",
            },
        ],
    },
    {
        "slug": "kb-appointments",
        "name": "Appointments",
        "linked_service": "appointments",
        "optional": True,
        "sort_order": 70,
        "description": "Appointment confirmation help.",
        "articles": [
            {
                "slug": "kb-appointments-setup",
                "title": "Appointment confirmations",
                "body": f"Configure workflows under {DASH}/appointments. Escalate issues via {DASH}/account/support/tickets.",
            },
        ],
    },
    {
        "slug": "kb-recovery",
        "name": "Recovery",
        "linked_service": "recovery",
        "optional": True,
        "sort_order": 80,
        "description": "Recovery queue help.",
        "articles": [
            {
                "slug": "kb-recovery-setup",
                "title": "Using the Recovery queue",
                "body": f"No-show and recall tools live under {DASH}/recovery when enabled for your organisation.",
            },
        ],
    },
    {
        "slug": "kb-follow-up",
        "name": "Follow-up",
        "linked_service": "follow_up",
        "optional": True,
        "sort_order": 90,
        "description": "Follow-up reminder help.",
        "articles": [
            {
                "slug": "kb-follow-up-setup",
                "title": "Appointment follow-up reminders",
                "body": f"Manage reminder sequences at {DASH}/follow-up.",
            },
        ],
    },
]

HELP_LINKS: list[dict[str, Any]] = [
    {"seed_key": "hl-dash-faq", "title": "Dashboard FAQ", "url": f"{DASH}/account/support/faq", "category": "Support", "linked_service": "shared", "sort_order": 10, "description": "In-app documentation & FAQ"},
    {"seed_key": "hl-dash-tickets", "title": "Support tickets", "url": f"{DASH}/account/support/tickets", "category": "Support", "linked_service": "shared", "sort_order": 20, "description": "Email support inbox"},
    {"seed_key": "hl-public-help", "title": "Public help centre", "url": f"{PUBLIC}/help", "category": "Support", "linked_service": "shared", "sort_order": 30, "description": "voxbulk.com/help"},
    {"seed_key": "hl-contact", "title": "Contact VoxBulk", "url": f"{PUBLIC}/contact", "category": "Support", "linked_service": "shared", "sort_order": 40, "description": "Public contact form"},
    {"seed_key": "hl-billing", "title": "Account billing", "url": f"{DASH}/account/billing", "category": "Billing", "linked_service": "shared", "sort_order": 50, "description": "Invoices, wallet, Direct Debit"},
    {"seed_key": "hl-interview", "title": "AI Interviews", "url": f"{DASH}/interviews", "category": "Products", "linked_service": "interview", "sort_order": 60, "description": "Interview campaigns"},
    {"seed_key": "hl-recruitment-public", "title": "Recruitment product page", "url": f"{PUBLIC}/recruitment", "category": "Products", "linked_service": "interview", "sort_order": 65, "description": "Public recruitment page"},
    {"seed_key": "hl-survey", "title": "WhatsApp Surveys", "url": f"{DASH}/surveys", "category": "Products", "linked_service": "survey", "sort_order": 70, "description": "Survey workspace"},
    {"seed_key": "hl-survey-public", "title": "Surveys product page", "url": f"{PUBLIC}/surveys", "category": "Products", "linked_service": "survey", "sort_order": 75, "description": "Public surveys page"},
    {"seed_key": "hl-feedback", "title": "Customer Feedback", "url": f"{DASH}/feedback", "category": "Products", "linked_service": "customer_feedback", "sort_order": 80, "description": "Feedback QR workspace"},
    {"seed_key": "hl-feedback-public", "title": "Feedback product page", "url": f"{PUBLIC}/feedback", "category": "Products", "linked_service": "customer_feedback", "sort_order": 85, "description": "Public feedback page"},
    {"seed_key": "hl-expo", "title": "Expo", "url": f"{DASH}/expo", "category": "Products", "linked_service": "expo", "sort_order": 90, "description": "Expo campaigns"},
    {"seed_key": "hl-expo-public", "title": "Expo product page", "url": f"{PUBLIC}/expo", "category": "Products", "linked_service": "expo", "sort_order": 95, "description": "Public Expo page"},
    {"seed_key": "hl-smart-card", "title": "Smart Card", "url": f"{DASH}/smart-card", "category": "Products", "linked_service": "smart_card", "sort_order": 100, "description": "Smart Card workspace"},
    {"seed_key": "hl-smart-card-public", "title": "Smart Card product page", "url": f"{PUBLIC}/smart-card", "category": "Products", "linked_service": "smart_card", "sort_order": 105, "description": "Public Smart Card page"},
    {"seed_key": "hl-campaigns", "title": "Campaigns", "url": f"{DASH}/campaigns", "category": "Products", "linked_service": "campaigns", "sort_order": 110, "description": "Broadcast campaigns"},
    {"seed_key": "hl-appointments", "title": "Appointments", "url": f"{DASH}/appointments", "category": "Products", "linked_service": "appointments", "optional": True, "sort_order": 120, "description": "Appointment confirmations"},
    {"seed_key": "hl-recovery", "title": "Recovery", "url": f"{DASH}/recovery", "category": "Products", "linked_service": "recovery", "optional": True, "sort_order": 130, "description": "Recovery queue"},
    {"seed_key": "hl-follow-up", "title": "Follow-up", "url": f"{DASH}/follow-up", "category": "Products", "linked_service": "follow_up", "optional": True, "sort_order": 140, "description": "Follow-up reminders"},
]
