"""Canonical public / SEO marketing FAQs for the VoxBulk frontpage and Help centre."""

from __future__ import annotations

# Demo support-ticket FAQs seeded for the dashboard — remove from public SEO.
DEMO_SUPPORT_FAQ_QUESTIONS = frozenset(
    {
        "How do I create a support ticket?",
        "Where can I manage my package?",
        "Where can I see invoices?",
        "Can I change my plan?",
        "What files can I upload to tickets?",
    }
)

# Legacy single-category alias (used by older callers).
MARKETING_FAQ_CATEGORY = ("Product", "product", 10)

# (question, answer, slug, sort_order, featured)
GETTING_STARTED_FAQS: list[tuple[str, str, str, int, bool]] = [
    (
        "What exactly does VoxBulk do?",
        "VoxBulk is a UK-built AI platform for WhatsApp surveys, QR customer feedback, "
        "AI phone interviews, and voice agents. Automate conversations, collect multilingual "
        "responses, and act from live dashboards.",
        "what-exactly-does-voxbulk-do",
        10,
        True,
    ),
    (
        "How do I create a VoxBulk account?",
        "Click Get Started on voxbulk.com, sign up with email or Google, then complete the short "
        "onboarding wizard — company details, country, and the products you want to use "
        "(surveys, feedback, AI interviews).",
        "how-do-i-create-a-voxbulk-account",
        20,
        True,
    ),
    (
        "How long does setup take?",
        "Most teams are live within a few days. We connect messaging, scheduling, and your "
        "workflows, configure your surveys or interview scripts, and run test conversations "
        "before going live.",
        "how-long-does-setup-take",
        30,
        False,
    ),
    (
        "Can I invite my team?",
        "Yes. Invite teammates from your organisation settings. Roles include owner, manager, "
        "accountant and member — each with role-based access to billing, campaigns and reports.",
        "can-i-invite-my-team",
        40,
        False,
    ),
    (
        "Do I need technical skills?",
        "No. VoxBulk is built for recruiters, ops and marketing teams. Surveys, interview scripts "
        "and campaigns are point-and-click. API and marketplace partners are available when you "
        "need deeper integrations.",
        "do-i-need-technical-skills",
        50,
        False,
    ),
]

BILLING_FAQS: list[tuple[str, str, str, int, bool]] = [
    (
        "Is there a contract or commitment?",
        "No long-term contract. Monthly subscription, cancel anytime with 30 days' notice. "
        "Enterprise customers can opt for annual terms with custom pricing.",
        "is-there-a-contract-or-commitment",
        10,
        True,
    ),
    (
        "How does interview screening pricing work?",
        "Partner and marketplace screening is usage-based: £1.50 connection fee + £0.35 per minute. "
        "A typical completed screen is about £7–£9. Dashboard wallet and subscription plans cover "
        "WhatsApp surveys, feedback and AI calling depending on your package.",
        "how-does-interview-screening-pricing-work",
        20,
        True,
    ),
    (
        "Can I switch plans anytime?",
        "Yes. Upgrade or change plan from Billing in the dashboard. Changes apply from your next "
        "billing cycle. Contact support@voxbulk.com for enterprise volume pricing.",
        "can-i-switch-plans-anytime",
        30,
        False,
    ),
    (
        "Which currencies do you support?",
        "GBP, USD, AUD and CAD. Your billing currency is set from organisation country and can be "
        "confirmed during onboarding.",
        "which-currencies-do-you-support",
        40,
        False,
    ),
    (
        "Are there setup fees?",
        "Standard self-serve plans have no setup fees. Fully custom survey or interview flows may "
        "include a one-off configuration fee depending on complexity — we confirm this before work starts.",
        "are-there-setup-fees",
        50,
        False,
    ),
]

RECRUITMENT_FAQS: list[tuple[str, str, str, int, bool]] = [
    (
        "How do AI voice interviews actually work?",
        "Candidates receive a scheduled invite, join at their slot, and complete a natural "
        "phone conversation with our AI interviewer. The AI asks tailored questions, listens, "
        "follows up, and produces a scored, summarised report.",
        "how-do-ai-voice-interviews-work",
        10,
        True,
    ),
    (
        "Which languages and accents are supported?",
        "AI voice interviews and calling surveys support English (GB, Irish, Australian, "
        "American, Scottish and Canadian dialects) and Arabic (Egyptian and Saudi dialects). "
        "WhatsApp surveys and voice-note transcription work across 50+ languages, with "
        "responses translated to English in your dashboard.",
        "which-languages-and-accents-are-supported",
        20,
        True,
    ),
    (
        "Can I customise the interview questions?",
        "Yes. Use role-based templates or write your own screening questions and scoring criteria "
        "per campaign. Criteria appear in the AI brief so every candidate is assessed the same way.",
        "can-i-customise-the-interview-questions",
        30,
        False,
    ),
    (
        "Can candidates opt out of speaking to AI?",
        "Yes. The AI announces itself at the start of every interaction, and candidates can "
        "request a human follow-up at any time.",
        "can-candidates-opt-out-of-speaking-to-ai",
        40,
        False,
    ),
    (
        "Does it integrate with my ATS?",
        "Yes. Zoho Recruit is available via Marketplace / Partner API. We also support API push "
        "into other ATS/HRIS systems. Custom connectors are available on Enterprise.",
        "does-it-integrate-with-my-ats",
        50,
        False,
    ),
]

WHATSAPP_SURVEY_FAQS: list[tuple[str, str, str, int, bool]] = [
    (
        "Can I use VoxBulk just for surveys or feedback?",
        "Yes. WhatsApp surveys and QR customer feedback are available as standalone products. "
        "Collect replies (including voice notes), translate them, and deliver actionable "
        "reports — named or anonymous.",
        "can-i-use-voxbulk-just-for-surveys-or-feedback",
        10,
        True,
    ),
    (
        "Why WhatsApp instead of email?",
        "WhatsApp reaches people where they already reply — far higher open and response rates "
        "than email survey links. Customers can answer with text or voice notes in their language.",
        "why-whatsapp-instead-of-email",
        20,
        True,
    ),
    (
        "Can customers reply in any language?",
        "Yes. Customers speak or type in 50+ languages and voice notes — you read everything "
        "auto-translated to English in your dashboard.",
        "can-customers-reply-in-any-language",
        30,
        False,
    ),
    (
        "How do I create a survey?",
        "Choose an industry template or build your own questions, upload contacts, and launch. "
        "QR customer feedback works the same way for in-venue or post-visit capture.",
        "how-do-i-create-a-survey",
        40,
        False,
    ),
    (
        "Is WhatsApp Business required?",
        "We send via the WhatsApp Business API on VoxBulk-managed numbers (or your connected "
        "profile where enabled). You do not need to build your own Meta app to get started.",
        "is-whatsapp-business-required",
        50,
        False,
    ),
]

AI_CALLING_FAQS: list[tuple[str, str, str, int, bool]] = [
    (
        "How natural does the AI sound?",
        "VoxBulk uses modern neural voices for English and Arabic dialects. Most respondents "
        "experience a clear, natural conversation. Sample calls are available on request.",
        "how-natural-does-the-ai-sound",
        10,
        True,
    ),
    (
        "Can the AI handle interruptions?",
        "Yes. Real-time turn-taking and interruption handling are built in so conversations "
        "feel natural rather than rigid IVR scripts.",
        "can-the-ai-handle-interruptions",
        20,
        False,
    ),
    (
        "What happens after a call?",
        "Every call is transcribed, scored where configured, and pushed to your dashboard "
        "(and ATS/CRM via API or marketplace webhook) shortly after hang-up.",
        "what-happens-after-a-call",
        30,
        True,
    ),
]

SECURITY_FAQS: list[tuple[str, str, str, int, bool]] = [
    (
        "How is my data kept secure?",
        "VoxBulk is a multi-tenant platform with strict tenant isolation — each organisation's "
        "data is kept separate. Passwords use encrypted storage, integration secrets are "
        "encrypted at rest, and role-based access controls ensure only authorised team members "
        "see what they need. Production runs on secured infrastructure in UK and EU data centres.",
        "how-is-my-data-kept-secure",
        10,
        True,
    ),
    (
        "Is VoxBulk GDPR compliant?",
        "Yes. Data is encrypted in transit and at rest, hosted in UK/EU data centres, and every "
        "customer accepts our Data Processing Agreement at signup. Read it at voxbulk.com/dpa "
        "(PDF available) or see voxbulk.com/gdpr.",
        "is-voxbulk-gdpr-compliant",
        20,
        True,
    ),
    (
        "Do you train AI on my data?",
        "No. Customer recordings, transcripts and survey replies are not used to train foundation "
        "models. Call recordings and full transcripts are kept 30 days by default; other operational "
        "data on our servers 90 days. Contact Data.Pro@voxbulk.com for deletion requests.",
        "do-you-train-ai-on-my-data",
        30,
        False,
    ),
    (
        "Where is my data stored?",
        "Production data is stored in UK and EU data centres. We do not move customer data outside "
        "the UK/EU without written agreement.",
        "where-is-my-data-stored",
        40,
        False,
    ),
    (
        "How long do you keep call recordings?",
        "Call recordings and full transcripts are retained for 30 days by default, then deleted or "
        "made inaccessible. Structured scores, survey answers and message logs on our servers are "
        "kept for 90 days by default. See voxbulk.com/privacy and voxbulk.com/dpa.",
        "how-long-do-you-keep-call-recordings",
        50,
        True,
    ),
]

ACCOUNT_FAQS: list[tuple[str, str, str, int, bool]] = [
    (
        "What integrations are supported?",
        "Booking providers such as Calendly, Cal.com, Google Calendar and Microsoft 365 Bookings; "
        "CRM options including HubSpot; Zoho Recruit for AI voice candidate screening; plus API "
        "access to push results into your ATS or HRIS. Connect them from Dashboard → Settings → "
        "Integrations.",
        "what-integrations-are-supported",
        10,
        True,
    ),
    (
        "How do I reset my password?",
        "On the sign-in page choose Forgot password. You will receive a reset link by email. "
        "If you use Google or another social login, reset through that provider.",
        "how-do-i-reset-my-password",
        20,
        False,
    ),
    (
        "Can I have multiple workspaces?",
        "Agencies and multi-brand companies can run separate organisations. Contact "
        "support@voxbulk.com to enable multi-org billing or linked workspaces.",
        "can-i-have-multiple-workspaces",
        30,
        False,
    ),
    (
        "How do I delete my account?",
        "Email support@voxbulk.com from your account email. We delete organisation data within "
        "30 days where legally allowed and confirm in writing. See voxbulk.com/privacy.",
        "how-do-i-delete-my-account",
        40,
        False,
    ),
]

TROUBLESHOOTING_FAQS: list[tuple[str, str, str, int, bool]] = [
    (
        "Candidates aren't receiving interview links",
        "Confirm the phone number includes the correct country code and is reachable. Check "
        "campaign delivery status in the dashboard. For WhatsApp invites, the number must be "
        "WhatsApp-enabled.",
        "candidates-arent-receiving-interview-links",
        10,
        True,
    ),
    (
        "My dashboard isn't loading",
        "Try a hard refresh (Ctrl/Cmd + Shift + R) or another browser. Clear cached site data "
        "if needed. If the issue continues, email support@voxbulk.com with your org name and "
        "a screenshot.",
        "my-dashboard-isnt-loading",
        20,
        False,
    ),
    (
        "AI call ended unexpectedly",
        "This often means a poor connection on the candidate's side. Failed or incomplete calls "
        "can be retried from the campaign. Check recipient status and call logs in the order view.",
        "ai-call-ended-unexpectedly",
        30,
        False,
    ),
]

CUSTOMER_FEEDBACK_FAQS: list[tuple[str, str, str, int, bool]] = [
    (
        "How does QR customer feedback work?",
        "Print or display a unique QR code per location. Customers scan, open WhatsApp, and leave "
        "star ratings, text or voice notes — no app download required. Results appear live in your "
        "dashboard with translation where needed.",
        "how-does-qr-customer-feedback-work",
        10,
        True,
    ),
    (
        "Can customers leave voice notes on feedback?",
        "Yes. Voice notes are transcribed and translated so your team can read them in English in "
        "the dashboard. Full voice content follows our 30-day retention default.",
        "can-customers-leave-voice-notes-on-feedback",
        20,
        True,
    ),
    (
        "Can I compare feedback across locations?",
        "Yes. Use Compare locations in the dashboard to see scores and themes side by side for "
        "branches or sites.",
        "can-i-compare-feedback-across-locations",
        30,
        False,
    ),
    (
        "What happens when someone leaves a poor score?",
        "You can configure alerts so your team is notified quickly and can follow up. Poor scores "
        "still appear in reports like any other response.",
        "what-happens-when-someone-leaves-a-poor-score",
        40,
        False,
    ),
]

INTEGRATIONS_FAQS: list[tuple[str, str, str, int, bool]] = [
    (
        "How do I connect a booking calendar?",
        "In the dashboard open Settings → Integrations → Booking providers. Choose Calendly, "
        "Cal.com, Google Calendar or Microsoft 365 Calendar, click Connect, complete the provider "
        "login, then select your event type or Bookings page. Only one booking provider is active "
        "per organisation at a time.",
        "how-do-i-connect-a-booking-calendar",
        10,
        True,
    ),
    (
        "How do interview booking links work?",
        "After you connect a booking provider, send invites from your interview campaign. "
        "Candidates receive a link to book a slot on your calendar. VoxBulk sends the invite emails; "
        "your booking provider holds the availability.",
        "how-do-interview-booking-links-work",
        20,
        True,
    ),
    (
        "How do I connect HubSpot or another CRM?",
        "Open Settings → Integrations → CRM. Connect HubSpot with the Connect button and approve "
        "access. Use Test connection to confirm tokens and scopes. Additional CRM connectors roll "
        "out as they become Live for your account.",
        "how-do-i-connect-hubspot-or-another-crm",
        30,
        False,
    ),
    (
        "Why don't I see a booking or CRM provider?",
        "Providers appear only when VoxBulk has enabled them for organisations (and Live, or "
        "Testing if you are on the tester list). Ask support@voxbulk.com if you expect a provider "
        "that is missing.",
        "why-dont-i-see-a-booking-or-crm-provider",
        40,
        False,
    ),
]

EXPO_FAQS: list[tuple[str, str, str, int, bool]] = [
    (
        "What is VoxBulk Expo?",
        "Expo helps you capture leads at events with a branded QR or link experience, then follow "
        "up from your dashboard. It is available when Expo is enabled on your organisation.",
        "what-is-voxbulk-expo",
        10,
        True,
    ),
    (
        "How do I create an Expo campaign?",
        "From the dashboard open Expo → New, set your event details and capture fields, then "
        "publish your QR or link for the stand. Leads appear under Expo → Leads.",
        "how-do-i-create-an-expo-campaign",
        20,
        True,
    ),
]

CAMPAIGNS_FAQS: list[tuple[str, str, str, int, bool]] = [
    (
        "What are broadcast campaigns?",
        "Broadcast campaigns send approved WhatsApp template messages to a contact list for "
        "announcements or offers. They are separate from conversational surveys. Your organisation "
        "must have Campaigns enabled and approved templates.",
        "what-are-broadcast-campaigns",
        10,
        True,
    ),
    (
        "Do I need consent for WhatsApp campaigns?",
        "Yes. You must have a lawful basis under UK GDPR and PECR (usually consent for marketing). "
        "Recipients can opt out with STOP. Transactional messages have different rules — configure "
        "purpose correctly before send.",
        "do-i-need-consent-for-whatsapp-campaigns",
        20,
        True,
    ),
]

ZOHO_FAQ_CATEGORY = ("Zoho Recruit", "zoho-recruit", 90)

ZOHO_FAQS: list[tuple[str, str, str, int, bool]] = [
    (
        "What is VoxBulk AI Voice Screening for Zoho Recruit?",
        "VoxBulk AI Voice Screening is an API integration for Zoho Recruit that runs AI phone "
        "interviews in English and Arabic. Recruiters send candidate details; VoxBulk calls the "
        "candidate and returns a score (0–100), status (passed / review / rejected), call duration, "
        "and a report link. Full setup guide: https://voxbulk.com/help/zoho-recruit",
        "zoho-recruit-what-is-voxbulk-ai-voice-screening",
        10,
        True,
    ),
    (
        "How do I connect Zoho Recruit to VoxBulk?",
        "Create a VoxBulk account, open the Zoho Recruit Marketplace listing for VoxBulk AI Voice "
        "Screening (or install via the vendor redirect), connect your Recruit organisation with "
        "the API credentials shown in VoxBulk Admin → Partners → Zoho, then send a test candidate. "
        "Step-by-step: https://voxbulk.com/help/zoho-recruit",
        "zoho-recruit-how-to-connect",
        20,
        True,
    ),
    (
        "What personal data does the Zoho Recruit integration store?",
        "Candidate name, phone, email (if provided), job title, screening questions and answers, "
        "language preference, call recordings/transcripts, AI score and status, report URL, and "
        "ATS reference IDs. VoxBulk processes this as a processor for your organisation under UK "
        "GDPR. See https://voxbulk.com/privacy",
        "zoho-recruit-personal-data",
        30,
        False,
    ),
    (
        "How much does Zoho Recruit AI screening cost?",
        "Usage-based pricing: £1.50 connection fee + £0.35 per minute. A typical completed screen "
        "is about £7–£9. There is no upfront install fee. Zoho Marketplace may apply its platform "
        "commission on billed usage where applicable.",
        "zoho-recruit-pricing",
        40,
        False,
    ),
    (
        "Does VoxBulk support Arabic screening for Zoho Recruit?",
        "Yes. Preferred language can be English (en) or Arabic (ar). Dual-language AI voice "
        "screening is designed for UK and Middle East hiring teams using Zoho Recruit.",
        "zoho-recruit-arabic-english",
        50,
        False,
    ),
    (
        "Where can I get help for the Zoho Recruit integration?",
        "Read the public help guide at https://voxbulk.com/help/zoho-recruit or email "
        "support@voxbulk.com. For privacy questions contact Data.Pro@voxbulk.com.",
        "zoho-recruit-support",
        60,
        False,
    ),
]

# Keep Product alias pointing at getting-started content for older callers.
MARKETING_FAQS = GETTING_STARTED_FAQS

# ((name, slug, sort_order), faqs)
MARKETING_FAQ_GROUPS: list[tuple[tuple[str, str, int], list[tuple[str, str, str, int, bool]]]] = [
    (("Getting started", "getting-started", 10), GETTING_STARTED_FAQS),
    (("Billing & pricing", "billing", 20), BILLING_FAQS),
    (("AI Recruitment", "recruitment", 30), RECRUITMENT_FAQS),
    (("WhatsApp Surveys", "whatsapp-surveys", 40), WHATSAPP_SURVEY_FAQS),
    (("Customer Feedback", "customer-feedback", 45), CUSTOMER_FEEDBACK_FAQS),
    (("AI Calling", "ai-calling", 50), AI_CALLING_FAQS),
    (("Integrations", "integrations", 55), INTEGRATIONS_FAQS),
    (("Expo", "expo", 58), EXPO_FAQS),
    (("Campaigns", "campaigns", 59), CAMPAIGNS_FAQS),
    (("Security & privacy", "security", 60), SECURITY_FAQS),
    (("Account & settings", "account", 70), ACCOUNT_FAQS),
    (("Troubleshooting", "troubleshooting", 80), TROUBLESHOOTING_FAQS),
    (ZOHO_FAQ_CATEGORY, ZOHO_FAQS),
]
