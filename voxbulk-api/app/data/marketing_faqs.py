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
        "Yes. All data stays within UK/EU data centres, calls and messages are encrypted in "
        "transit and at rest, and we sign a Data Processing Agreement with every customer. "
        "See voxbulk.com/gdpr for our GDPR overview.",
        "is-voxbulk-gdpr-compliant",
        20,
        True,
    ),
    (
        "Do you train AI on my data?",
        "No. Customer recordings, transcripts and survey replies are not used to train foundation "
        "models. Your organisation controls retention and can request deletion.",
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
]

ACCOUNT_FAQS: list[tuple[str, str, str, int, bool]] = [
    (
        "What integrations are supported?",
        "Cronofy and Calendly for scheduling, WhatsApp for surveys and feedback, Zoho Recruit "
        "for AI voice candidate screening (Marketplace listing), plus API access to push results "
        "into your ATS or HRIS. Custom integrations are available on Enterprise.",
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
    (("AI Calling", "ai-calling", 50), AI_CALLING_FAQS),
    (("Security & privacy", "security", 60), SECURITY_FAQS),
    (("Account & settings", "account", 70), ACCOUNT_FAQS),
    (("Troubleshooting", "troubleshooting", 80), TROUBLESHOOTING_FAQS),
    (ZOHO_FAQ_CATEGORY, ZOHO_FAQS),
]
