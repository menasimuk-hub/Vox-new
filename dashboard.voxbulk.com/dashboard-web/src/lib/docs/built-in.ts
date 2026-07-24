import {
  LayoutDashboard,
  PhoneCall,
  MessageSquare,
  PhoneOutgoing,
  QrCode,
  Wallet,
  LifeBuoy,
  Settings as SettingsIcon,
  type LucideIcon,
} from "lucide-react";

export type DocsArticle = {
  id: string;
  title: string;
  /** Optional sub-section label shown above the article (e.g. "How to use", "Troubleshooting") */
  group?: string;
  /** Optional dashboard route(s) this article is about — rendered as a chip under the title */
  routes?: string[];
  /** Plain text or simple markdown-ish lines; rendered with whitespace preserved */
  body: string;
};

export type DocsCategory = {
  id: string;
  name: string;
  shortName?: string;
  description: string;
  Icon: LucideIcon;
  articles: DocsArticle[];
};

export const BUILT_IN_DOCS: DocsCategory[] = [
  {
    id: "overview",
    name: "Dashboard overview",
    shortName: "Overview",
    description: "What the home page shows and how to use it.",
    Icon: LayoutDashboard,
    articles: [
      {
        id: "overview-purpose",
        group: "What is it for",
        title: "Why the Overview page exists",
        routes: ["/"],
        body: "The Dashboard Overview is your central command centre. It gives you an instant, high-level snapshot of:\n\n• Running AI interview slots\n• Active survey voice-calls and completed response counts\n• Live QR code scan activity\n• A summary of recently processed campaign statistics\n\nUse it to monitor everything at a glance instead of opening each module.",
      },
      {
        id: "overview-tips",
        group: "Tips",
        title: "What the KPI cards mean",
        body: "• AI interview calls live — candidates currently on the phone with Leo.\n• AI survey calls live — outbound survey calls in progress.\n• Calls attempted vs completed — completion rate for the current period.\n• Total scans — QR code scans (Customer Feedback) for the period.\n\nClick any KPI to jump to its detailed page.",
      },
    ],
  },
  {
    id: "interviews",
    name: "AI Interview campaigns",
    shortName: "AI Interview",
    description: "Automated CV screening + Voice AI phone interviews.",
    Icon: PhoneCall,
    articles: [
      {
        id: "interviews-purpose",
        group: "What is it for",
        title: "What AI Interview campaigns do",
        routes: ["/interviews"],
        body: "High-volume candidate pre-screening using interactive, professional voice AI (\"Leo\").\n\nRecruiting manually takes hours of calling and coordination. The AI Interview service automates CV screening and phone interviews. Candidates book their preferred slots, the Voice AI conducts a structured phone call, and the dashboard aggregates traits and scores to deliver structured hire recommendations.",
      },
      {
        id: "interviews-how-to",
        group: "How to use",
        title: "Step-by-step: launch your first interview campaign",
        body: "1. Upload candidates — go to /interviews/new and upload CVs (PDF/Docx) or pull from a job board integration.\n2. Review ATS scoring — the parser extracts qualifications and scores applicants against the target role.\n3. Approve interview script — questions 1–2 are personalised CV templates; questions 3+ are your standard criteria.\n4. Set calling window — choose the date/time range when the Voice AI may dial.\n5. Launch — candidates receive an email + WhatsApp invite with a booking link.\n6. Self-serve booking — candidates pick an open 4-minute slot.\n7. Phone screening — at the slot time, Leo dials and conducts the interview.\n8. View scorecard — /interviews/results gives you audio, transcript, trait scores and fit recommendation.",
      },
      {
        id: "interviews-script-generate",
        group: "How to use",
        title: "How the AI generates the interview script",
        body: "When you create or edit an interview campaign, the system drafts the script for you based on:\n\n• The job title and role you entered\n• The criteria, must-haves and deal-breakers you typed in the brief\n• The CVs uploaded so far (questions 1–2 are personalised per candidate from their CV)\n\nWhat you see in the preview:\n• Questions 1–2 — CV templates. The AI replaces them on each call with questions tailored to that candidate's CV.\n• Questions 3+ — the same for every candidate, drawn from your criteria.\n\nThe opening line and legal disclosure are added automatically and aren't shown in the editor — they're handled by your AI agent for compliance.\n\nClick Generate / Re-generate at any time before approving to redraft. The estimated call duration (e.g. ~4 min per call) updates with each draft.",
      },
      {
        id: "interviews-script-edit",
        group: "How to use",
        title: "Can I edit the AI script and use my own questions?",
        body: "Yes. The script editor is fully editable before you approve.\n\nHow to customise:\n1. Click Generate to get the AI draft.\n2. Edit any question text directly — rewrite, reorder, add or remove.\n3. Keep questions short and conversational (the AI reads them aloud over the phone).\n4. Click Approve script to lock the version that will be used on calls.\n\nGood practice:\n• Aim for 3–6 questions total. More than that and call length / drop-off climbs.\n• Don't add multi-part questions in one line — split them so the AI can score answers cleanly.\n• Keep candidate-personalised wording (e.g. \"Tell me about X on your CV\") only in slots 1–2 — the AI handles personalisation there.\n\nYou can re-approve a new version any time before launch.",
      },
      {
        id: "interviews-no-call",
        group: "Troubleshooting",
        title: "Problem: the candidate booked but the AI never called",
        body: "Do:\n• Verify your calling window is active and hasn't expired.\n• Check UK local time (Europe/London). Calls don't dial outside 09:00–17:30 UK unless Relaxed Hours is enabled.\n• Make sure the candidate's phone is a valid E.164 number (e.g. +44…) and not on your Opt-Out list.\n\nDon't:\n• Don't schedule slots within 30 minutes of your closing window — the scheduler needs buffer time.",
      },
      {
        id: "interviews-slots-off",
        group: "Troubleshooting",
        title: "Problem: candidates see slots that look too early or too late",
        body: "Do:\n• The booking grid is anchored to UK time. Check the start and end limits in Step 4 match your target recruitment timeline.\n\nDon't:\n• Don't leave the booking window wide open over weekends or holidays unless your HR staff is actively monitoring incoming scores.",
      },
      {
        id: "interviews-script-not-approved",
        group: "Troubleshooting",
        title: "Problem: why is my script not approved?",
        body: "When you click Approve script, the text is scanned by VoxBulk's content review before going live. Here are the exact reasons it can stay un-approved, in order:\n\n1) Script text is empty\n  • There must be a generated or pasted draft. Click Generate, or paste your own questions, then try Approve again.\n  • You'll also see the wizard hint: \"Generate or paste a script, then approve it\".\n\n2) You edited the script after it was approved\n  • Any edit resets the review status to not_scanned and unticks Approved. This is by design — every change has to be re-reviewed.\n  • Fix: click Approve script again to re-submit the edited version.\n\n3) The content review flagged the text\n  Status becomes pending_admin_review and a red banner appears: \"Script blocked: <reason>\". The review flags these categories:\n  • racism — racist, discriminatory or hateful content targeting protected groups\n  • offensive — harassment, slurs, threats, extreme insults, or gratuitously abusive language\n  • sexual — sexual, explicit or adult content\n  • political — partisan campaigning, inflammatory political messaging, or election advocacy\n  Fix: edit the questions to remove the flagged content, then click Approve again. If you believe it was a false positive, leave it and wait for the VoxBulk team to review — they can manually approve.\n\n4) Your script was rejected after review\n  Status becomes rejected with a reason. Edit the text and click Approve again.\n\n5) Content review is temporarily unavailable\n  If the AI safety check itself errors out, the script stays un-approved and the banner says: \"Content review is temporarily unavailable\". Try again in a few minutes.\n\nWhat NOT to do:\n• Don't try to bypass the banner by launching — Launch stays disabled until your script status shows Approved.\n• Don't paste binary or emoji-heavy text into questions — the AI reads them aloud and they break the voice flow.\n• Don't keep editing the script after launch for already-called candidates — edits only apply to candidates not yet called.",
      },
      {
        id: "interviews-script-roles",
        group: "Troubleshooting",
        title: "Question: who in my team is allowed to approve a script?",
        body: "Approve script and Launch follow your VoxBulk role permissions:\n\n• Owner — full access. Can create, edit, approve and launch.\n• Manager — full access. Same as Owner for campaigns and settings.\n• Member — can create, edit, approve and launch campaigns. Cannot see Billing or manage the team.\n• Accountant — billing only. Cannot see Interviews or Surveys in the sidebar at all.\n\nIf a teammate can't see Interviews:\n• Check Settings → Team and confirm their role is owner, manager or member. Accountant is intentionally billing-only.\n\nIf they can see Interviews but the Approve button does nothing:\n• That's a script-content issue (see \"why is my script not approved?\") — it's not a role issue.\n\nNeed to change someone's role: Owner or Manager → /settings/team → edit role.",
      },
      {
        id: "interviews-script-after-launch",
        group: "Troubleshooting",
        title: "Question: can I change the script after launch?",
        body: "Yes — open the live campaign on /interviews/{id}.\n\n• Edits to the script and calling window apply to candidates not yet called.\n• Candidates already booked keep their slot.\n• Candidates already called and completed are unchanged (their reports stay as they were scored).\n\nIf you change the criteria significantly, re-generate the script and approve again — that becomes the new version used for any candidate dialed from that point on.",
      },
    ],
  },
  {
    id: "wa-survey",
    name: "WhatsApp Surveys",
    shortName: "WA Survey",
    description: "Conversational chat-based surveys on WhatsApp.",
    Icon: MessageSquare,
    articles: [
      {
        id: "wa-survey-purpose",
        group: "What is it for",
        title: "Why use WhatsApp Surveys",
        routes: ["/surveys"],
        body: "Channel: WhatsApp.\n\nConduct conversational patient or customer surveys directly inside WhatsApp chat.\n\nTraditional email surveys get low response rates. WhatsApp surveys reach people where they already chat and ask approved questions step-by-step, in either a fixed linear order or a branching graph based on their answers.",
      },
      {
        id: "wa-survey-how-to",
        group: "How to use",
        title: "Step-by-step: launch a WhatsApp survey",
        body: "1. Upload contact list — go to /surveys/new, pick the WhatsApp channel, upload your CSV.\n2. Build your question flow — pick a preset template, or define a structured flow (Linear = fixed order, Graph = branches based on answers).\n3. Review approved templates — questions must match Meta-approved templates. Custom edits need re-approval.\n4. Launch and monitor — the system sends the first message and handles replies automatically.\n5. View results — /surveys/results shows reply transcripts, NPS indicators and extracted answers.",
      },
      {
        id: "wa-survey-undelivered",
        group: "Troubleshooting",
        title: "Problem: messages show as undelivered",
        body: "Do:\n• Check your sender number has active credits.\n• Make sure the template is marked approved / live before launching.\n\nDon't:\n• Don't edit template text mid-campaign. WhatsApp requires the exact approved wording — even small changes can block delivery.",
      },
      {
        id: "wa-survey-blocked",
        group: "Troubleshooting",
        title: "Problem: a recipient stopped receiving messages",
        body: "Do:\n• The user probably opted out. For a test handset, send UNSTOP on WhatsApp to your sender number to lift the block.\n\nDon't:\n• Don't keep messaging numbers that replied STOP — that can get your WhatsApp Business number suspended.",
      },
      {
        id: "wa-survey-template-not-approved",
        group: "Troubleshooting",
        title: "Problem: my WhatsApp template isn't approved yet",
        body: "Do:\n• WhatsApp templates need Meta approval before they can be sent. New or edited templates show as draft / pending until Meta reviews them (usually minutes, sometimes hours).\n• While you wait, pick a different template that's already approved — Launch shows you which templates are live.\n• If a template comes back rejected, edit it to remove URLs / promo wording / unsupported placeholders and resubmit.\n\nDon't:\n• Don't edit an approved template's wording mid-campaign — even small text changes reset it to pending and pause delivery.\n• Don't try to launch with a template still in draft — Launch will be disabled.",
      },
      {
        id: "wa-survey-script-moderation",
        group: "Troubleshooting",
        title: "Problem: why is my WhatsApp survey script not approved?",
        body: "WhatsApp survey scripts go through the same content review as interviews. They can stay un-approved for these reasons:\n\n1) Empty script — generate or paste questions first.\n2) Edited after approval — any change resets the status; click Approve again.\n3) Content review flagged the text as racism / offensive / sexual / political. Edit and re-approve, or wait for the VoxBulk team to review.\n4) Your script was rejected after review — edit and re-approve.\n5) Content review temporarily unavailable — try again in a few minutes.\n\nAdditionally for WhatsApp surveys:\n• The selected message template must already be Meta-approved (see \"My WhatsApp template isn't approved yet\").\n• Custom templates submitted to Meta can take minutes to hours to approve.",
      },
    ],
  },
  {
    id: "wa-calling",
    name: "WhatsApp Calling Surveys",
    shortName: "WA Calling",
    description: "AI phone voice polls (outbound calls).",
    Icon: PhoneOutgoing,
    articles: [
      {
        id: "wa-calling-purpose",
        group: "What is it for",
        title: "Why use AI Calling Surveys",
        routes: ["/surveys"],
        body: "Channel: AI phone call.\n\nReach customer or patient lists quickly via automated voice AI surveys.\n\nIdeal for senior cohorts or urgent outreach (recall, reminders). The AI dials the list, reads questions aloud, interprets spoken answers and compiles results instantly in your dashboard.",
      },
      {
        id: "wa-calling-how-to",
        group: "How to use",
        title: "Step-by-step: launch a calling survey",
        body: "1. Create campaign — /surveys/new, pick the AI phone call channel.\n2. Import numbers — upload a CSV with valid E.164 phone numbers.\n3. Select script and window — choose a pre-defined survey script and set the calling window.\n4. Launch — the system dials, reads questions, transcribes voice answers and saves structured summaries to your reports.",
      },
      {
        id: "wa-calling-declined",
        group: "Troubleshooting",
        title: "Problem: calls get declined or disconnected immediately",
        body: "Do:\n• Verify your calling hours. Automated calls outside 09:00–17:30 UK time are blocked unless Relaxed Hours is enabled.\n\nDon't:\n• Don't upload numbers without a country code — the network can't route them.",
      },
      {
        id: "wa-calling-bad-answers",
        group: "Troubleshooting",
        title: "Problem: captured answers are cut off or inaccurate",
        body: "Do:\n• Keep questions short and simple (Yes/No, 1–10). Voice recognition works best with brief answers.\n• Mention upfront that the call is an AI survey, so people answer clearly.\n\nDon't:\n• Don't use long open-ended questions on phone polls. Use WhatsApp Surveys for lengthy text feedback instead.",
      },
    ],
  },
  {
    id: "feedback",
    name: "Customer Feedback (QR)",
    shortName: "Feedback",
    description: "QR-code surveys at physical branches + multi-location comparison.",
    Icon: QrCode,
    articles: [
      {
        id: "feedback-purpose",
        group: "What is it for",
        title: "Why use Customer Feedback QR",
        routes: ["/feedback"],
        body: "Capture instant, location-specific reviews via physical QR codes placed inside your venues.\n\nFeedback at the point of experience is the most accurate. Guests scan a QR code, WhatsApp opens with a pre-filled message, and they complete a short topic-based review in their own language (English / Arabic supported).",
      },
      {
        id: "feedback-how-to",
        group: "How to use",
        title: "Step-by-step: launch QR feedback at a branch",
        body: "1. Create branch locations — /feedback/new and add each branch.\n2. Select topics — choose your industry and toggle up to 6 areas to rate (e.g. cleanliness, wait time, staff).\n3. Print QR material — download the unique QR images for each branch and print them.\n4. Position in venues — reception, waiting area, exits.\n5. Guest flow — scanning the QR triggers a WhatsApp survey; replies are stored in English on your dashboard.\n6. Track scores — /feedback/results shows branch-by-branch satisfaction and topic breakdowns.",
      },
      {
        id: "feedback-invalid-code",
        group: "Troubleshooting",
        title: "Problem: scanning the QR says invalid location code",
        body: "Do:\n• The pre-filled WhatsApp message must end with the 6-character reference suffix (e.g. acme-marylebone-a3f2b1). If it's missing, the system can't link the chat to your branch.\n• Reprint from /feedback if the printed copy was hand-edited.\n\nDon't:\n• Don't add emojis or extra text to the QR's pre-filled message — some devices break the suffix parser.",
      },
      {
        id: "feedback-change-questions",
        group: "Troubleshooting",
        title: "Question: do I need to reprint QRs to change topics?",
        body: "Do:\n• No — go to /feedback, open the branch, click Edit survey. Topic and closing changes sync instantly. The printed QR and its reference suffix stay valid.\n\nDon't:\n• Don't delete a branch to reset its config. That permanently breaks any QRs already printed for it.",
      },
      {
        id: "feedback-compare-purpose",
        group: "Compare locations",
        title: "What Compare locations is for",
        routes: ["/feedback/compare"],
        body: "Side-by-side comparison of satisfaction, NPS, response rates and per-topic scores across multiple branches.\n\nOnly available on multi-location Customer Feedback plans (Pro / Business). On Starter (single location), you won't see this menu item — upgrade on /account/feedback/packages to unlock it.",
      },
      {
        id: "feedback-compare-how-to",
        group: "Compare locations",
        title: "Step-by-step: compare branches",
        body: "1. Open /feedback/compare.\n2. Tick the branches you want to include (up to 8 colour-coded series).\n3. Compare:\n  • Satisfaction trends over time\n  • Response and recommend rates\n  • Sentiment split (happy / neutral / unhappy)\n  • Per-question average scores\n4. Spot outliers and drill into a branch by clicking through to its results.",
      },
    ],
  },
  {
    id: "settings",
    name: "Settings (profile, team, integrations)",
    shortName: "Settings",
    description: "Organisation profile, team, opt-out list, audit, integrations.",
    Icon: SettingsIcon,
    articles: [
      {
        id: "settings-profile",
        group: "What is it for",
        title: "Profile settings — organisation details and logo",
        routes: ["/settings/profile"],
        body: "Edit your organisation's display name, country, contact details, brand logo (shown in the sidebar) and request account deletion.\n\nWho can edit: Owner and Manager. Member and Accountant can view only.",
      },
      {
        id: "settings-services",
        group: "What is it for",
        title: "Services — show or hide modules in your sidebar",
        routes: ["/settings/services"],
        body: "Toggle which services appear in your sidebar and Dashboard Overview (Interviews, Surveys, Customer Feedback).\n\n• Off = hidden from sidebar; turn back on here anytime.\n• To remove a module from your plan entirely, contact your VoxBulk account manager — these toggles are visibility only.\n\nOnly modules your plan includes show up here.",
      },
      {
        id: "settings-integrations",
        group: "What is it for",
        title: "Integrations — booking providers and CRM",
        routes: ["/settings/integrations"],
        body: "Connect the external tools VoxBulk uses to schedule human interviews and to sync candidates to your CRM. The page is split into two tabs:\n\n• Booking providers — Calendly, Cal.com, Google Calendar, Microsoft 365 Calendar, HubSpot Meetings. Only one booking provider can be active per organisation at any time.\n• CRM — HubSpot (Pipedrive and Zoho are coming in a future release).\n\nEvery tile shows live status: Connected, Not connected, Error or Unavailable. Click a tile to open the side sheet with Connect, Test connection and Disconnect buttons.\n\nOnly providers that your VoxBulk admin has both configured and marked as visible to organisations appear in the list — if you can't see a provider, ask admin to enable it for you.",
      },
      {
        id: "settings-integrations-test",
        group: "Booking providers",
        title: "Test connection — what the deep health check actually does",
        routes: ["/settings/integrations"],
        body: "The Test connection button in the provider sheet runs three checks before reporting OK:\n\n1. Token check — confirms your stored access token is still valid (we call the provider's `/me` or `/account-info` endpoint).\n2. Scope check — confirms the right permissions are present (for example `Calendars.ReadWrite` for Microsoft 365, `crm.objects.contacts.read` for HubSpot).\n3. Sample resource — actually loads one real resource (your first event type, calendar, meeting link, or contact). This catches the case where the token is valid but the selected event type was deleted.\n\nIf any check fails you see a red banner with which check failed and why. Common fixes: disconnect and reconnect (re-grants scopes), or re-select the event type / Bookings page in the provider sheet.",
      },
      {
        id: "settings-integrations-microsoft",
        group: "Booking providers",
        title: "Microsoft 365 Calendar — connect Outlook Bookings",
        routes: ["/settings/integrations"],
        body: "Microsoft 365 Calendar uses a multi-tenant Microsoft Entra app, so any work or school account can authorise VoxBulk:\n\n1. Open Settings → Integrations → Booking providers, click the Microsoft 365 Calendar tile.\n2. Click Connect Microsoft 365 Calendar and sign in with the Microsoft account that owns the Bookings page.\n3. Back in the sheet, paste your Microsoft Bookings public page URL (something like outlook.office365.com/owa/calendar/.../bookings/ or book.ms/your-page).\n4. Click Save Bookings page.\n\nFrom that point, when you send interview booking links from campaign Results, each candidate gets an email with your Bookings URL. Microsoft does not send those emails for you — VoxBulk handles delivery.\n\nNot seeing the tile? Microsoft 365 Calendar may still be in soft-launch — your admin needs to flip 'Visible to organisations' on in Admin → Integrations → Microsoft 365 Calendar.",
      },
      {
        id: "settings-integrations-soft-launch",
        group: "Booking providers",
        title: "Why a provider may be hidden from your list",
        routes: ["/settings/integrations"],
        body: "Every customer-facing integration (Booking, CRM, Recruiting) has:\n\n• Enable — platform credentials are configured and usable.\n• Release: Testing | Live — Testing shows the tile (and its linked FAQs) only to emails on the Admin Test group list. Live shows them to every organisation.\n\nA provider only appears on your Integrations page when it is enabled and either Live, or Testing and your login email is a tester. If you expect a provider and do not see it, ask your admin.",
      },
      {
        id: "settings-team",
        group: "What is it for",
        title: "Team members — invite teammates and assign roles",
        routes: ["/settings/team"],
        body: "Invite teammates by email. Choose a role:\n• Manager — full dashboard access (campaigns, billing, team).\n• Member — campaigns only; no billing or team management.\n• Accountant — billing only; cannot launch campaigns.\n• Owner — your role; only Owner can transfer the seat to someone else.\n\nThe invitee receives an email with a sign-in link. You can also copy the invite link to share manually. Revoke pending invites or remove an active member from this page.\n\nWho can manage the team: Owner and Manager only.",
      },
      {
        id: "settings-opt-out",
        group: "What is it for",
        title: "Opt-out list — numbers we'll never message or call",
        routes: ["/settings/opt-out"],
        body: "A central Do-Not-Contact list. Any phone here is permanently excluded from every campaign, survey or reminder.\n\nNumbers are added in two ways:\n• Manually here (add by E.164, e.g. +447700900123).\n• Automatically when a recipient opts out on a call or replies STOP on WhatsApp.\n\nRemove a number by clicking Remove on its row.",
      },
      {
        id: "settings-audit",
        group: "What is it for",
        title: "Audit log — who did what, when",
        routes: ["/settings/audit"],
        body: "Compliance-grade activity log. Records every team invite, opt-out change, logo update, settings change and account-deletion event with who, when, and details.\n\nWho can view: Owner and Manager.",
      },
    ],
  },
  {
    id: "billing",
    name: "Billing, packages, wallet & payments",
    shortName: "Billing & payments",
    description: "Plans, top-ups, invoices, Stripe, Airwallex and GoCardless Direct Debit.",
    Icon: Wallet,
    articles: [
      {
        id: "billing-purpose",
        group: "Overview",
        title: "How VoxBulk billing works at a glance",
        routes: ["/account/billing", "/account/usage", "/account/packages"],
        body: "• Monthly packages — Starter, Practice, Group plans, billed monthly via GoCardless Direct Debit. Each plan includes a monthly quota of calls, WhatsApp sends and SMS.\n• Prepaid wallet — covers campaign setup costs and overage. Top up with Stripe or Airwallex (min £5 / equivalent).\n• Overage — once a monthly allowance is consumed, extra usage is billed per-minute / per-message from your wallet.\n• Reconciliation — if a campaign of 100 only sends 80, the unused balance is refunded to your wallet automatically.",
      },
      {
        id: "billing-rails",
        group: "Overview",
        title: "Three payment rails — when each one is used",
        body: "VoxBulk uses three payment providers, each for a different job:\n\n• Stripe — one-off card payments (wallet top-ups and single invoice payments).\n• Airwallex — alternative one-off card processor; same flows as Stripe. Your account uses one of them or both.\n• GoCardless — Direct Debit for recurring subscriptions and DD-backed launches.\n\nYou'll see whichever providers are enabled on your account in the top-up and invoice dialogs.",
      },
      {
        id: "account-plan-tabs",
        group: "Packages & plans",
        title: "Packages & pricing — Core and Customer Feedback",
        routes: ["/account/packages"],
        body: "Two separate product tabs because they bill differently:\n• Core platform — AI interviews + WA / AI-call surveys. Subscription + top-up.\n• Customer Feedback — QR-driven inbound WhatsApp. Subscription only (Starter / Pro / Business by location count).\n\nSubscribing to Customer Feedback does not include Core, and vice versa — they're separate products.",
      },
      {
        id: "account-plan-change",
        group: "Packages & plans",
        title: "Changing plans mid-cycle",
        routes: ["/account/packages"],
        body: "On /account/packages click the new plan's Subscribe / Change button:\n• Upgrade — takes effect immediately. You're charged a pro-rated amount for the remainder of the current cycle via Direct Debit, and the bigger allowance starts now.\n• Downgrade — schedules at the next billing anchor (no refund for unused allowance on the current cycle). The pending plan is shown on the Billing page until it takes effect.\n• Cancellation — schedules at the end of the current cycle. Re-subscribe any time before then to undo it.",
      },
      {
        id: "account-wallet-topup",
        group: "Wallet & top-up",
        title: "How to top up your wallet",
        routes: ["/account/billing", "/account/packages"],
        body: "1. Click Top up on the Billing page or open the Wallet card on Packages.\n2. Choose an amount (minimum £5 / $5 equivalent).\n3. Pay with card via Stripe or Airwallex (whichever is enabled on your account).\n4. The amount appears in your wallet instantly on a successful charge.\n\nUse cases for the wallet:\n• PAYG accounts — every launch is paid from the wallet.\n• Subscribers — covers overage when monthly allowances run out, and one-off pay-per-use items (CV scans, ad-hoc calls).",
      },
      {
        id: "account-usage-breakdown",
        group: "Wallet & top-up",
        title: "Usage page — where every charge comes from",
        routes: ["/account/usage"],
        body: "Line-by-line breakdown of usage across every campaign in the current billing period:\n• Service (interview / survey / feedback)\n• Channel (call / WhatsApp / SMS)\n• Status of the campaign\n• Usage units + cost\n• Billing source — allowance, wallet, or DD\n\nClick a row to jump to the campaign that produced the charge. Filter by service or status to investigate spikes.",
      },
      {
        id: "billing-usage-warnings",
        group: "Wallet & top-up",
        title: "Usage warnings at 80% and 100%",
        routes: ["/account/usage"],
        body: "We send automatic emails when your plan reaches 80% and 100% of its monthly allowance, so you can top up or upgrade before overage kicks in.\n\nSee live counters on /account/usage.",
      },
      {
        id: "stripe-purpose",
        group: "Stripe — card payments",
        title: "What Stripe is used for in VoxBulk",
        body: "Stripe powers two card payment flows in your dashboard:\n\n1) Wallet top-up — /account/billing → Top up, or /account/packages → Wallet card.\n   Pre-load credit on your account that any service (interviews, surveys, CV scans) draws from.\n\n2) One-off invoice payment — Pay button on any open invoice on /account/billing.\n   Settle a single invoice with a card instead of waiting for the next Direct Debit collection.\n\nStripe is one of two card processors VoxBulk supports — the other is Airwallex. Whichever is enabled for your account shows up as a payment button. If neither is configured, you'll see \"Card payments are not configured yet. Contact support to top up your wallet.\"\n\nFor recurring monthly subscriptions, VoxBulk uses GoCardless Direct Debit (not Stripe). Stripe is for one-off card payments only.",
      },
      {
        id: "stripe-currencies",
        group: "Stripe — card payments",
        title: "Which currencies and cards are supported",
        body: "Currency:\n• Stripe charges in your organisation's billing currency — GBP, USD, CAD or AUD — set on /settings/profile (your country drives this).\n• You can't pay an invoice in a different currency from the one it was issued in.\n\nCards:\n• Visa, Mastercard, American Express, and any other card brand your enabled Stripe account supports.\n• 3D Secure (SCA) is handled automatically — if your bank requires the extra step, Stripe shows the challenge inline; no redirect away from the dashboard.\n• Apple Pay and Google Pay are intentionally disabled. Pay by entering the card details directly.",
      },
      {
        id: "stripe-topup-flow",
        group: "Stripe — card payments",
        title: "Step-by-step: top up your wallet with Stripe",
        body: "1. Open the Top up wallet dialog from /account/billing or /account/packages.\n2. Enter an amount (minimum £5 or local equivalent; the dialog refuses smaller amounts).\n3. Optionally pick a suggested amount chip if you want a bonus credit pack.\n4. Click \"Pay {amount} with Stripe\".\n5. The Stripe Payment Element loads inline. Enter your card details (and complete 3D Secure if your bank prompts you).\n6. Click Pay. On success you'll see \"Wallet topped up — {new balance}\" and the dialog closes.\n7. If Stripe needs a moment to settle, you'll see \"Payment is still processing\" — your wallet credits as soon as the bank confirms.",
      },
      {
        id: "stripe-invoice-flow",
        group: "Stripe — card payments",
        title: "Step-by-step: pay an open invoice by card",
        body: "1. Go to /account/billing. Open invoices show a Pay button next to them.\n2. Click Pay on the invoice you want to settle.\n3. The Invoice payment dialog offers the available methods — typically: Pay from wallet (if balance covers it), Pay by card (Stripe / Airwallex), or DD collection (if your mandate is active).\n4. Click Pay by card (Stripe).\n5. Enter card details in the inline form and submit.\n6. On success the invoice flips to paid and disappears from the open list. The receipt PDF becomes downloadable from the same row.",
      },
      {
        id: "stripe-min-amount",
        group: "Stripe — card payments",
        title: "Minimum top-up and bonus packs",
        body: "• Minimum top-up: £5 / $5 / CA$5 / A$5 (set by Stripe's own minimum charge floor; the dialog enforces it).\n• Suggested amount chips on the top-up dialog can offer bonus credit (e.g. \"Top up £100 — get £110\"). Bonus credit is applied to the wallet at the same moment as your payment clears.\n• You can type any custom amount above the minimum — bonuses only apply to the suggested packs.",
      },
      {
        id: "stripe-failed",
        group: "Stripe — troubleshooting",
        title: "Problem: my Stripe payment failed",
        body: "When Stripe returns an error, the dashboard shows the exact reason from your bank — for example:\n• \"Your card was declined.\" — your bank rejected the charge. Common causes: insufficient funds, card limits, fraud rules. Try a different card or call your bank.\n• \"Your card's security code is incorrect.\" — re-check the CVC.\n• \"Authentication required\" — 3D Secure was needed but cancelled or failed. Try the payment again and complete the bank's challenge.\n• \"This card has expired.\" — use a different card or have a new one issued.\n\nWhat to do:\n• Try the same card again — temporary declines (e.g. a one-off fraud check) often clear on retry.\n• If it keeps failing, switch to a different card.\n• If you see \"Stripe is not configured\", contact support to enable card payments — this is a configuration we manage for you.\n\nWhat NOT to do:\n• Don't keep retrying the same card more than 3–4 times. Repeated declines can trigger your bank's fraud lock.",
      },
      {
        id: "stripe-still-processing",
        group: "Stripe — troubleshooting",
        title: "Problem: I see \"Payment is still processing\" — where's my credit?",
        body: "This appears when Stripe accepted your card but hasn't finalised the charge yet (this is normal for some 3D Secure flows and some bank rails).\n\nWhat to do:\n• Wait a few minutes. The wallet credits automatically as soon as Stripe's webhook confirms settlement — you don't need to do anything.\n• Refresh /account/billing after 1–2 minutes to see the new wallet balance.\n• If it's been more than 30 minutes and the wallet still hasn't credited, open a support ticket — the assistant attaches your Stripe payment intent ID automatically.\n\nWhat NOT to do:\n• Don't pay again. The first payment is still queued — paying twice will charge you twice.",
      },
      {
        id: "stripe-duplicate",
        group: "Stripe — troubleshooting",
        title: "Problem: I think Stripe charged me twice",
        body: "VoxBulk has duplicate protection at the payment-intent level — even if you click Pay twice quickly, only one charge succeeds and your wallet credits once.\n\nIf your card statement does show two charges:\n• Open /account/billing → Wallet history. Each successful top-up is listed as a separate row. If there's only one, the second card-statement entry is almost always a temporary authorisation hold from your bank and will fall off in 1–7 days.\n• If two rows show in Wallet history, open a support ticket — we'll refund one and email confirmation.",
      },
      {
        id: "stripe-no-card-option",
        group: "Stripe — troubleshooting",
        title: "Problem: I don't see a Pay-by-card / Stripe option",
        body: "If the top-up dialog or invoice payment dialog doesn't list Stripe:\n• \"Card payments are not configured yet\" — contact support to switch them on.\n• Only Airwallex is shown — your account is set to use Airwallex; the flow is essentially the same (enter card details inline, click pay).\n• The Pay button on an invoice is greyed out — the invoice may already be paid, voided, or in dispute. Refresh the page; check the status badge on the row.",
      },
      {
        id: "stripe-refunds",
        group: "Stripe — troubleshooting",
        title: "Question: can I get a refund of a Stripe top-up?",
        body: "Wallet top-ups are non-refundable by default — the credit sits in your wallet until you use it, so there's no \"expiry\" risk.\n\nWhen we do refund:\n• Duplicate charge (see \"charged me twice\" above) — refunded automatically once you raise a ticket.\n• You stop using VoxBulk and want unused wallet credit back — contact support; refunds are returned to the original Stripe card and may take 5–10 business days to land.\n• You were billed for a service you genuinely didn't use because of a platform fault — support refunds the wallet credit, you then withdraw to card.\n\nFor invoice payments, refunds depend on the invoice — disputed invoices that are resolved in your favour are refunded to the original card.",
      },
      {
        id: "aw-purpose",
        group: "Airwallex — card payments",
        title: "What Airwallex is used for in VoxBulk",
        body: "Airwallex is the alternative card processor to Stripe — used for the same two flows:\n\n1) Wallet top-up — /account/billing → Top up, or /account/packages → Wallet card.\n2) One-off invoice payment — Pay button on any open invoice.\n\nYour account is configured to use one of: Stripe only, Airwallex only, or both. Whichever are enabled appear as Pay-with-… buttons in the top-up and invoice dialogs. Functionally they behave the same — pick whichever your business prefers.",
      },
      {
        id: "aw-currencies",
        group: "Airwallex — card payments",
        title: "Which currencies and cards are supported (Airwallex)",
        body: "Currency:\n• Airwallex charges in your organisation's billing currency (GBP / USD / CAD / AUD / EUR depending on your country).\n• Airwallex is particularly strong for non-UK currencies — useful if your bank doesn't play well with Stripe's local rails.\n\nCards:\n• Visa, Mastercard, American Express, JCB, Diners, UnionPay, and other brands supported by your Airwallex merchant account.\n• 3D Secure (SCA) is enforced inline via the Airwallex drop-in element.\n• Apple Pay / Google Pay availability follows what's configured on the Airwallex merchant side.",
      },
      {
        id: "aw-topup-flow",
        group: "Airwallex — card payments",
        title: "Step-by-step: top up with Airwallex",
        body: "1. Open the Top up wallet dialog from /account/billing or /account/packages.\n2. Enter an amount (minimum £5 / $5 / equivalent).\n3. Click \"Pay {amount} with Airwallex\".\n4. The Airwallex drop-in element loads inline. Enter card details (and complete 3D Secure if your bank prompts).\n5. On success the dialog closes with \"Wallet topped up — {new balance}\".\n6. If the dialog says \"Payment is still processing\", the credit appears automatically as soon as Airwallex confirms — no further action needed.",
      },
      {
        id: "aw-invoice-flow",
        group: "Airwallex — card payments",
        title: "Step-by-step: pay an invoice by Airwallex",
        body: "1. /account/billing → click Pay on an open invoice.\n2. In the payment method picker, choose Pay by card (Airwallex).\n3. Enter card details in the drop-in form.\n4. On success the invoice is marked paid; the receipt PDF appears on the same row.",
      },
      {
        id: "aw-failed",
        group: "Airwallex — troubleshooting",
        title: "Problem: my Airwallex payment failed",
        body: "Airwallex returns the same kinds of errors as Stripe — they're surfaced as a toast: \"Payment failed: <reason>\".\n\nCommon causes:\n• Card declined by bank — try a different card or contact your bank.\n• 3D Secure cancelled — re-try and complete the bank's challenge.\n• Currency mismatch — your card's currency doesn't match the invoice/wallet currency. Use a multi-currency card or contact support to adjust.\n• \"Airwallex SDK failed to load\" — usually a corporate firewall blocking checkout.airwallex.com. Try another network.\n\nWhat NOT to do:\n• Don't retry more than 3–4 times on the same card; you'll trigger your bank's fraud lock.",
      },
      {
        id: "aw-no-option",
        group: "Airwallex — troubleshooting",
        title: "Problem: I don't see an Airwallex option",
        body: "If the top-up or invoice payment dialog only shows Stripe (or no card options at all):\n• Airwallex isn't enabled on your account — contact support to switch it on.\n• You may already have Stripe and don't need Airwallex; they're interchangeable for card payments.\n\nFunctionally, every wallet top-up / invoice flow works the same with either provider — choose whichever your business prefers.",
      },
      {
        id: "gc-purpose",
        group: "GoCardless — Direct Debit",
        title: "What GoCardless is used for in VoxBulk",
        body: "GoCardless powers all Direct Debit (DD) flows in your dashboard:\n\n1) Monthly subscription billing — Core platform (Starter / Practice / Group) and Customer Feedback plans (Starter / Pro / Business). Plan fees are collected every month from your bank account.\n\n2) Mandate setup and updates — when you subscribe, you authorise a one-time mandate via your bank. The mandate is reused for all future collections, no card data ever stored.\n\n3) Per-order DD payment — for subscribers, launching an interview / survey campaign that exceeds your monthly allowance pulls the overage directly via DD using your mandate.\n\nGoCardless is for recurring + DD-backed payments. For one-off card payments use Stripe or Airwallex.",
      },
      {
        id: "gc-schemes",
        group: "GoCardless — Direct Debit",
        title: "Which countries and bank schemes are supported",
        body: "GoCardless routes payments through local bank rails based on your country:\n\n• UK — Bacs (3 business days to clear first payment)\n• EU / EEA — SEPA (2 business days first payment)\n• US — ACH (3–4 business days first payment)\n• Canada — PAD (3–4 business days first payment)\n• Australia / New Zealand — BECS (3 business days first payment)\n\nYour country (set on /settings/profile) controls which scheme is offered at checkout. Customer Feedback plans only enable a country once your account manager has confirmed GC supports it for your billing currency.",
      },
      {
        id: "gc-subscribe-flow",
        group: "GoCardless — Direct Debit",
        title: "Step-by-step: subscribe to a plan with GoCardless",
        body: "1. Open /account/packages and pick a plan (Core platform or Customer Feedback).\n2. Click Subscribe. You're redirected to the GoCardless hosted checkout page (this leaves the VoxBulk dashboard for a moment — that's expected).\n3. On the GC page, enter your bank account details and confirm the mandate.\n4. GC redirects you back to the dashboard and your subscription becomes active.\n5. If your scheme requires first-payment verification (Bacs / ACH / PAD / BECS), the dashboard shows status pending_first_payment for 3–7 business days. During this window you can still use the wallet to launch campaigns; DD-backed launches wait until first payment clears.",
      },
      {
        id: "gc-mandate-update",
        group: "GoCardless — Direct Debit",
        title: "Step-by-step: update or replace your DD mandate",
        body: "1. Open /account/billing. If your mandate needs attention (cancelled, expired, or you want to switch banks), the next-invoice card shows an Update mandate button.\n2. Click it — you're redirected to GoCardless to authorise the new mandate.\n3. After confirming, you return to the dashboard with the new mandate active.\n4. Future DD collections use the new mandate automatically.\n\nIf you cancelled accidentally, the old mandate stays untouched and the dashboard will tell you the update was cancelled.",
      },
      {
        id: "gc-vs-card",
        group: "GoCardless — Direct Debit",
        title: "When to use GoCardless vs card (Stripe / Airwallex)",
        body: "Use GoCardless DD when:\n• You're committing to a monthly subscription (always required for Core / Feedback plans).\n• You want VoxBulk to pull recurring fees automatically without card-expiry headaches.\n\nUse Stripe or Airwallex card when:\n• You need credit instantly (wallet top-up settles in seconds; DD takes days).\n• You want to settle a single overdue invoice without waiting for the next DD retry.\n• You don't have a UK / EU / US / CA / AU bank account that GC supports.\n\nMany customers use both: GoCardless for the monthly subscription, card top-ups for ad-hoc credit between cycles.",
      },
      {
        id: "gc-pending-first",
        group: "GoCardless — troubleshooting",
        title: "Problem: I just subscribed but campaign launches are blocked",
        body: "This is the first-payment hold. Bacs / ACH / PAD / BECS require 3–7 business days to verify the first DD collection before VoxBulk will accept DD-backed launches.\n\nWhat to do:\n• For urgent outreach, top up your wallet (Stripe / Airwallex) and launch from wallet — wallet launches are NOT blocked during the hold.\n• Wait for the hold to clear; your status changes from pending_first_payment to active automatically.\n• You can see the current status on /account/billing → Subscription card.\n\nWhat NOT to do:\n• Don't cancel and re-subscribe — the 3–7 day clock restarts each time.",
      },
      {
        id: "gc-mandate-cancelled",
        group: "GoCardless — troubleshooting",
        title: "Problem: my mandate was cancelled — what happens now?",
        body: "If your mandate is cancelled (by you in GC's emails, by your bank, or by GC for inactivity), VoxBulk freezes all DD-backed launches and emails you + your account admin.\n\nWhat to do:\n1. Open /account/billing.\n2. Click Update mandate on the Next invoice card — this opens a fresh GoCardless checkout.\n3. Confirm a new mandate; status returns to active.\n4. Any past-due invoice retries automatically on the new mandate.\n\nMeanwhile, your wallet still works — you can keep launching campaigns paid from wallet credit while you set up the new mandate.",
      },
      {
        id: "gc-failed-dd",
        group: "GoCardless — troubleshooting",
        title: "Problem: a DD payment failed",
        body: "Failed DD collections (insufficient funds, bank rejected, account closed) are automatically retried by VoxBulk:\n• Up to 3 retries over roughly 7 days, spaced out so your bank can resolve the issue.\n• If all 3 retries fail, your account moves to past_due and all DD-backed launches stop.\n• Wallet launches still work during past_due.\n\nWhat to do:\n• Top up your bank balance or fix the bank issue, then wait for the next retry.\n• Or settle the open invoice manually on /account/billing — click Pay → pay by Stripe / Airwallex card to clear past_due immediately.\n\nWhat NOT to do:\n• Don't cancel the mandate — re-creating it restarts the first-payment hold. Just leave it and let the retries run.",
      },
      {
        id: "gc-pop-up-blocked",
        group: "GoCardless — troubleshooting",
        title: "Problem: the GoCardless checkout never opens / returns an error",
        body: "Do:\n• Allow redirects to the gocardless.com domain in your browser. Some corporate firewalls block it — try a personal network or another browser.\n• If you see \"GoCardless did not return a checkout URL\", the integration isn't set up for your country / currency. Contact support — your account manager needs to enable the right scheme.\n• If your session expired during the GC step, click Subscribe again to start fresh.\n\nDon't:\n• Don't refresh the GC page mid-checkout — restart the flow from /account/packages instead.",
      },
      {
        id: "billing-launch-blocked",
        group: "Troubleshooting — launches & invoices",
        title: "Problem: the Launch button is disabled",
        body: "Do:\n1. Open /account/billing and check wallet balance and outstanding invoices.\n2. Make sure your Direct Debit mandate is active.\n3. If outstanding invoices exceed your credit limit, settle them — launches resume automatically.\n\nDon't:\n• Don't delete your active GoCardless mandate while campaigns are running — it triggers an immediate launch freeze.",
      },
      {
        id: "billing-pending-first-payment",
        group: "Troubleshooting — launches & invoices",
        title: "Problem: just signed up for Direct Debit but launch still blocked",
        body: "Do:\n• Direct Debit (Bacs, ACH, PAD, BECS) takes 3–7 business days for first-payment verification. Status shows pending_first_payment during this window.\n• For urgent outreach, top up your wallet via Stripe / Airwallex for immediate access — wallet launches aren't blocked during first-payment hold.\n\nDon't:\n• Don't cancel and re-create the mandate — the clock restarts.",
      },
    ],
  },
  {
    id: "support",
    name: "Support & live assistant",
    shortName: "Support",
    description: "Live chat, tickets and the in-app assistant.",
    Icon: LifeBuoy,
    articles: [
      {
        id: "support-purpose",
        group: "What is it for",
        title: "How to get help inside the dashboard",
        routes: ["/account/support/tickets"],
        body: "The support hub gives you three ways to get help:\n• Documentation & FAQ (this page)\n• Live chat — VoxBulk AI assistant in the bottom-right bubble\n• Email / ticket support — track replies and status in /account/support/tickets",
      },
      {
        id: "support-how-to",
        group: "How to use",
        title: "Step-by-step: open a support ticket",
        body: "1. Click the support bubble (bottom-right).\n2. Ask your question — billing, results, usage, navigation.\n3. If the assistant can't solve it, confirm Send ticket to support.\n4. Your active route, enabled services, plan tier and recent error logs are attached automatically.\n5. Track replies and status on /account/support/tickets.",
      },
      {
        id: "support-policy-refused",
        group: "Troubleshooting",
        title: "Problem: assistant says Policy refused",
        body: "Do:\n• The in-app assistant is read-only for safety. It can answer questions and link you to the right page, but it can't process refunds, edit templates, or delete campaigns on your behalf.\n• Follow the link it suggests and make the change yourself on the relevant page (/account/billing, /surveys, etc.).\n\nDon't:\n• Don't ask the assistant to make billing edits or campaign changes — it will always refuse and link you to the right screen.",
      },
    ],
  },
];
