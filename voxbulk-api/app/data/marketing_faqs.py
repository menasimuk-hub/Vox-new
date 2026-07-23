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
MARKETING_FAQS: list[tuple[str, str, str, int, bool]] = [
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
        "How long does setup take?",
        "Most teams are live within a few days. We connect messaging, scheduling, and your "
        "workflows, configure your surveys or interview scripts, and run test conversations "
        "before going live.",
        "how-long-does-setup-take",
        20,
        False,
    ),
    (
        "How do AI voice interviews actually work?",
        "Candidates receive a scheduled invite, join at their slot, and complete a natural "
        "phone conversation with our AI interviewer. The AI asks tailored questions, listens, "
        "follows up, and produces a scored, summarised report.",
        "how-do-ai-voice-interviews-work",
        30,
        False,
    ),
    (
        "Can I use VoxBulk just for surveys or feedback?",
        "Yes. WhatsApp surveys and QR customer feedback are available as standalone products. "
        "Collect replies (including voice notes), translate them, and deliver actionable "
        "reports — named or anonymous.",
        "can-i-use-voxbulk-just-for-surveys-or-feedback",
        40,
        False,
    ),
    (
        "Which languages and accents are supported?",
        "AI voice interviews and calling surveys support English (GB, Irish, Australian, "
        "American, Scottish and Canadian dialects) and Arabic (Egyptian and Saudi dialects). "
        "WhatsApp surveys and voice-note transcription work across 50+ languages, with "
        "responses translated to English in your dashboard.",
        "which-languages-and-accents-are-supported",
        50,
        False,
    ),
    (
        "How is my data kept secure?",
        "VoxBulk is a multi-tenant platform with strict tenant isolation — each organisation's "
        "data is kept separate. Passwords use encrypted storage, integration secrets are "
        "encrypted at rest, and role-based access controls ensure only authorised team members "
        "see what they need. Production runs on secured infrastructure in UK and EU data centres.",
        "how-is-my-data-kept-secure",
        60,
        False,
    ),
    (
        "Is VoxBulk GDPR compliant?",
        "Yes. All data stays within UK/EU data centres, calls and messages are encrypted in "
        "transit and at rest, and we sign a Data Processing Agreement with every customer. "
        "See voxbulk.com/gdpr for our GDPR overview.",
        "is-voxbulk-gdpr-compliant",
        70,
        False,
    ),
    (
        "What integrations are supported?",
        "Cronofy and Calendly for scheduling, WhatsApp for surveys and feedback, Zoho Recruit "
        "for AI voice candidate screening (Marketplace listing), plus API access to push results "
        "into your ATS or HRIS. Custom integrations are available on Enterprise.",
        "what-integrations-are-supported",
        80,
        False,
    ),
    (
        "Can candidates opt out of speaking to AI?",
        "Yes. The AI announces itself at the start of every interaction, and candidates can "
        "request a human follow-up at any time.",
        "can-candidates-opt-out-of-speaking-to-ai",
        90,
        False,
    ),
    (
        "Is there a contract or commitment?",
        "No long-term contract. Monthly subscription, cancel anytime with 30 days' notice. "
        "Enterprise customers can opt for annual terms with custom pricing.",
        "is-there-a-contract-or-commitment",
        100,
        False,
    ),
]

ZOHO_FAQ_CATEGORY = ("Zoho Recruit", "zoho-recruit", 20)

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

# ((name, slug, sort_order), faqs)
MARKETING_FAQ_GROUPS: list[tuple[tuple[str, str, int], list[tuple[str, str, str, int, bool]]]] = [
    (MARKETING_FAQ_CATEGORY, MARKETING_FAQS),
    (ZOHO_FAQ_CATEGORY, ZOHO_FAQS),
]
