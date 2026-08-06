"""Builtin Help Centre articles for assistant RAG (condensed core docs)."""

from __future__ import annotations

from typing import TypedDict


class BuiltinHelpArticle(TypedDict):
    source_id: str
    title: str
    body: str
    service_key: str | None
    category_id: str
    routes: list[str]


BUILTIN_HELP_ARTICLES: list[BuiltinHelpArticle] = [
    # Overview
    {
        "source_id": "overview-dashboard",
        "title": "VoxBulk Dashboard Overview",
        "body": "The VoxBulk dashboard is your central hub for managing surveys, interviews, customer feedback, and more. Navigate using the left sidebar to access different modules. Each module can be enabled or disabled under Settings → Services.",
        "service_key": None,
        "category_id": "overview",
        "routes": ["/", "/home"],
    },
    {
        "source_id": "overview-billing",
        "title": "Understanding Your Billing",
        "body": "VoxBulk uses a wallet-based system. Your subscription includes monthly allowances (AI call minutes, WhatsApp messages). When you launch campaigns beyond your allowance, the cost is deducted from your wallet. Top up your wallet under Account → Billing. View invoices and payment history there too.",
        "service_key": None,
        "category_id": "billing",
        "routes": ["/account/billing"],
    },
    {
        "source_id": "overview-usage",
        "title": "Tracking Your Usage",
        "body": "View your current period usage under Account → Usage. This shows how many AI call minutes and WhatsApp messages you've used from your subscription allowance, plus any additional charges. Usage resets at the start of each billing cycle.",
        "service_key": None,
        "category_id": "billing",
        "routes": ["/account/usage"],
    },
    # Surveys
    {
        "source_id": "survey-what-is",
        "title": "What is AI Survey?",
        "body": "AI Survey sends outbound WhatsApp or phone surveys to your contact list. Upload recipients (CSV with phone numbers), choose a survey type (e.g. NPS, CSAT), customize questions, and launch. Results appear under Surveys → Results after responses come in.",
        "service_key": "survey",
        "category_id": "surveys",
        "routes": ["/surveys", "/surveys/new"],
    },
    {
        "source_id": "survey-create",
        "title": "Creating a Survey Campaign",
        "body": "Go to Surveys → Create Survey. Choose WhatsApp or Phone channel. Select a survey type (NPS, CSAT, etc.) or create a custom one. Upload your recipient CSV (must include phone number column). Review pricing, then launch. Campaign appears in Surveys list.",
        "service_key": "survey",
        "category_id": "surveys",
        "routes": ["/surveys/new"],
    },
    {
        "source_id": "survey-results",
        "title": "Viewing Survey Results",
        "body": "After launching a survey, view live results under Surveys → Results. Select your campaign to see response rate, scores, and individual answers. Export results as CSV for further analysis. Results update in real-time as responses come in.",
        "service_key": "survey",
        "category_id": "surveys",
        "routes": ["/surveys/results"],
    },
    {
        "source_id": "survey-wa-templates",
        "title": "WhatsApp Survey Templates",
        "body": "WhatsApp surveys use Meta-approved templates. VoxBulk provides pre-built templates for common survey types. For custom templates, design your messages in the survey wizard, then submit for Meta approval. Approval can take 24-48 hours. Once approved, you can launch campaigns using that template.",
        "service_key": "survey",
        "category_id": "surveys",
        "routes": ["/surveys/new?channel=whatsapp"],
    },
    # Interviews
    {
        "source_id": "interview-what-is",
        "title": "What is AI Interview?",
        "body": "AI Interview automates candidate screening via phone. Upload candidates, define interview questions (job role, experience checks, availability), and launch. The AI voice agent calls each candidate, asks questions, and records structured answers. Review transcripts and scores under Interviews → Results.",
        "service_key": "interview",
        "category_id": "interviews",
        "routes": ["/interviews", "/interviews/new"],
    },
    {
        "source_id": "interview-create",
        "title": "Creating an Interview Campaign",
        "body": "Go to Interviews → New Interview. Upload your candidate CSV (phone number + optional name/role). Choose or customize interview questions (job title, years experience, availability slots). Set screening criteria (ATS score). Launch campaign. Interviews are scheduled and conducted automatically.",
        "service_key": "interview",
        "category_id": "interviews",
        "routes": ["/interviews/new"],
    },
    {
        "source_id": "interview-results",
        "title": "Reviewing Interview Results",
        "body": "View interview results under Interviews → Results. Each candidate shows completion status, ATS score, transcript, and structured answers. Filter by score or completion. Export shortlisted candidates as CSV. Integrates with job boards and CRM if configured.",
        "service_key": "interview",
        "category_id": "interviews",
        "routes": ["/interviews/results"],
    },
    # Customer Feedback
    {
        "source_id": "feedback-what-is",
        "title": "What is Customer Feedback?",
        "body": "Customer Feedback is a separate inbound product. Customers scan a QR code at your physical location, triggering a WhatsApp survey. This is different from outbound AI Survey campaigns. You subscribe to a feedback package (per location per month), generate QR codes, and collect responses in real-time.",
        "service_key": "customer_feedback",
        "category_id": "feedback",
        "routes": ["/feedback", "/feedback/new"],
    },
    {
        "source_id": "feedback-setup",
        "title": "Setting Up Customer Feedback Locations",
        "body": "Go to Customer Feedback → Add Location. Name the location (e.g. Store 1), choose the industry survey type, generate QR codes. Print and display QR codes on-site. When customers scan, they receive a WhatsApp feedback survey. Responses appear under Feedback → Results for that location.",
        "service_key": "customer_feedback",
        "category_id": "feedback",
        "routes": ["/feedback/new"],
    },
    {
        "source_id": "feedback-results",
        "title": "Viewing Customer Feedback Results",
        "body": "View feedback responses under Customer Feedback → Results. Filter by location, date, or rating. Export responses as CSV. Set up automated follow-ups or promo campaigns for low/high scores. Billing is per active location per month, not per response.",
        "service_key": "customer_feedback",
        "category_id": "feedback",
        "routes": ["/feedback/results"],
    },
    # Expo
    {
        "source_id": "expo-what-is",
        "title": "What is VoxBulk Expo?",
        "body": "VoxBulk Expo is a digital exhibition booth platform. Create a virtual booth with products, brochures, videos, and voice-enabled info cards. Visitors scan a QR code to explore your booth on their phone, ask questions via voice, and leave contact details. Collect leads and analytics in real-time.",
        "service_key": "expo",
        "category_id": "expo",
        "routes": ["/expo", "/expo/booths"],
    },
        {
        "source_id": "expo-create-booth",
        "title": "Creating an Expo Booth",
        "body": "Go to Expo → New Booth. Add your company logo, brochures (PDF), product images, and booth theme. Configure voice Q&A topics (pricing, features, availability). Generate a booth QR code. Visitors scan it at your exhibition stand or event to explore your booth on their phone. Track leads and engagement under Expo → Leads.",
        "service_key": "expo",
        "category_id": "expo",
        "routes": ["/expo/new"],
    },
    {
        "source_id": "expo-pricing",
        "title": "Expo pricing and when billing starts",
        "body": "Expo booth packages are sold under Account → Packages (Expo plans). Cost depends on the plan length you choose (for example multi-day event packages). Billing typically starts when you purchase/activate the package — not when a visitor first scans — unless Admin has configured a different trial. After purchase, create your booth under Expo → New Booth and download/print the QR code. For exact live prices for your organisation, open Account → Packages or ask Billing support.",
        "service_key": "expo",
        "category_id": "expo",
        "routes": ["/account/packages", "/expo/new"],
    },
    # Smart Card
    {
        "source_id": "smartcard-what-is",
        "title": "What is VoxBulk Smart Card?",
        "body": "VoxBulk Smart Card is a digital business card for sales reps. Each rep gets a personalized QR code linking to a mobile-friendly card showing products, contact details, booking links, and voice-enabled product info. Prospects scan the QR, explore offerings, and leave their contact details. Leads sync to your CRM.",
        "service_key": "smart_card",
        "category_id": "smartcard",
        "routes": ["/smart-card", "/smart-card/company"],
    },
    {
        "source_id": "smartcard-setup",
        "title": "Setting Up Smart Cards",
        "body": "Go to Smart Card → Company Profile to configure your branding and products. Then add sales reps under Smart Card → Representatives. Each rep gets a unique QR code. Print it on business cards or marketing materials. When prospects scan, they see the rep's card and can leave their details or book a call.",
        "service_key": "smart_card",
        "category_id": "smartcard",
        "routes": ["/smart-card/new"],
    },
    # Campaigns (Marketing)
    {
        "source_id": "campaigns-what-is",
        "title": "What are Campaigns?",
        "body": "Campaigns module manages AI-powered outbound sales and marketing sequences (if enabled on your account). This is separate from Surveys. Campaigns can include email sequences, LinkedIn messages, and follow-ups. Configure under Campaigns → New Campaign. This feature requires Campaigns module access.",
        "service_key": "campaigns",
        "category_id": "campaigns",
        "routes": ["/campaigns"],
    },
    # Settings
    {
        "source_id": "settings-profile",
        "title": "Managing Company Profile",
        "body": "Update your company name, logo, and contact details under Settings → Profile. These details appear in emails, surveys, and customer-facing pages. Changes apply across all modules. Your logo is used in email templates and feedback surveys.",
        "service_key": None,
        "category_id": "settings",
        "routes": ["/settings/profile"],
    },
    {
        "source_id": "settings-services",
        "title": "Enabling and Disabling Services",
        "body": "Control which modules appear in your sidebar under Settings → Services. Toggle Surveys, Interviews, Customer Feedback, Expo, Smart Card, and more. Hidden services are not removed from your account—just hidden from the UI. Contact your account manager to permanently add or remove a product from your subscription.",
        "service_key": None,
        "category_id": "settings",
        "routes": ["/settings/services"],
    },
    {
        "source_id": "settings-team",
        "title": "Inviting Team Members",
        "body": "Add colleagues under Settings → Team. Enter their email, choose a role (Owner, Manager, Accountant, Member), and send invite. They receive an email with a signup link. Owners have full access. Managers can launch campaigns. Accountants see billing only. Members have read-only access.",
        "service_key": None,
        "category_id": "settings",
        "routes": ["/settings/team"],
    },
    {
        "source_id": "settings-integrations",
        "title": "Connecting Integrations",
        "body": "VoxBulk integrates with HubSpot, Calendly, Zoho Recruit, and more. Configure under Settings → Integrations. Connect your CRM to sync contacts and leads automatically. Set up scheduling tools to embed booking links in surveys and feedback forms. OAuth connections are secure and can be revoked anytime.",
        "service_key": None,
        "category_id": "settings",
        "routes": ["/settings/integrations"],
    },
    {
        "source_id": "settings-optout",
        "title": "Managing Opt-Out List",
        "body": "Maintain a do-not-contact list under Settings → Opt-out. Add phone numbers or emails manually. These contacts are automatically excluded from all outbound campaigns (surveys, interviews, marketing). Opt-outs are permanent unless you remove them. Respects GDPR and compliance.",
        "service_key": None,
        "category_id": "settings",
        "routes": ["/settings/opt-out"],
    },
    # Billing and Packages
    {
        "source_id": "billing-packages",
        "title": "Choosing a Subscription Plan",
        "body": "View available plans and pricing under Account → Packages. Plans include monthly allowances for AI calls and WhatsApp messages. Upgrade or downgrade anytime. Changes take effect at the next billing cycle. Contact support for custom enterprise plans or add-on services.",
        "service_key": None,
        "category_id": "billing",
        "routes": ["/account/packages"],
    },
    {
        "source_id": "billing-wallet",
        "title": "Topping Up Your Wallet",
        "body": "Your wallet covers campaign overages and on-demand services. When your subscription allowance runs out, costs are deducted from the wallet. Top up under Account → Billing → Add Credit. Minimum top-up £10. Wallet balance never expires. Refunds processed as credit notes.",
        "service_key": None,
        "category_id": "billing",
        "routes": ["/account/billing"],
    },
    {
        "source_id": "billing-invoices",
        "title": "Viewing and Paying Invoices",
        "body": "View all invoices under Account → Billing. Click an invoice to see line items (subscription fees, campaign charges, wallet top-ups). Pay outstanding invoices via Direct Debit or card. Set up auto-pay under Billing → Payment Methods to avoid service interruption.",
        "service_key": None,
        "category_id": "billing",
        "routes": ["/account/billing"],
    },
    # Support
    {
        "source_id": "support-faq",
        "title": "Browsing the FAQ",
        "body": "Find answers to common questions under Account → Support → FAQ. Topics include billing, launching campaigns, troubleshooting, integrations, and compliance. Search by keyword or browse categories. If you can't find an answer, create a support ticket or contact your account manager.",
        "service_key": None,
        "category_id": "support",
        "routes": ["/account/support/faq"],
    },
    {
        "source_id": "support-tickets",
        "title": "Creating a Support Ticket",
        "body": "Raise a support ticket under Account → Support → Tickets. Choose a category (Technical, Billing, Account), describe the issue, and attach screenshots if needed. Our team responds within 4 hours (during business hours). Track ticket status and replies in the same page.",
        "service_key": None,
        "category_id": "support",
        "routes": ["/account/support/tickets"],
    },
    # Common How-Tos
    {
        "source_id": "howto-launch-check",
        "title": "Why Can't I Launch My Campaign?",
        "body": "Common reasons: 1) Insufficient wallet balance. 2) Outstanding invoice. 3) No recipients uploaded. 4) WhatsApp template pending Meta approval. 5) Subscription plan doesn't include this channel. Check the campaign page for specific blockers. Top up wallet or pay invoice under Billing.",
        "service_key": None,
        "category_id": "overview",
        "routes": ["/surveys/new", "/interviews/new"],
    },
    {
        "source_id": "howto-export-results",
        "title": "How Do I Export Results?",
        "body": "Go to the Results page for your campaign (Surveys → Results, Interviews → Results, or Feedback → Results). Select the campaign, click Export or Download CSV. The file includes all responses, scores, and contact details. Use for reports, CRM import, or analysis.",
        "service_key": None,
        "category_id": "overview",
        "routes": ["/surveys/results", "/interviews/results", "/feedback/results"],
    },
    {
        "source_id": "howto-change-plan",
        "title": "How Do I Change My Subscription Plan?",
        "body": "Go to Account → Packages, choose a new plan, and click Upgrade (or Downgrade). Changes take effect at your next billing cycle. If you need immediate changes or custom pricing, contact support or your account manager.",
        "service_key": None,
        "category_id": "billing",
        "routes": ["/account/packages"],
    },
]
