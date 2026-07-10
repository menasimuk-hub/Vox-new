# VoxBulk Client Dashboard — Q&A and Troubleshooting Guide

Welcome to the official, developer-verified User Guide and FAQ for the **VoxBulk Client Dashboard**. This guide is designed entirely for platform clients, business owners, and support agents using the client-facing portal. It details what each menu item is for, how to use it, what problems you might face, and how billing operates.

---

## 📖 Table of Contents
1. [Dashboard Overview (Home)](#1-dashboard-overview-home)
2. [AI Interview campaigns (Automated Candidate Screening)](#2-ai-interview-campaigns-automated-candidate-screening)
3. [WhatsApp (WA) Surveys (Interactive Chat Campaigns)](#3-whatsapp-wa-surveys-interactive-chat-campaigns)
4. [WhatsApp (WA) Calling Surveys (AI phone voice polls)](#4-whatsapp-wa-calling-surveys-ai-phone-voice-polls)
5. [Customer Feedback (QR-code Local Branch Loops)](#5-customer-feedback-qr-code-local-branch-loops)
6. [Account Billing, Packages, Wallet, and Quotas](#6-account-billing-packages-wallet-and-quotas)
7. [Support Tickets and Live Assistant Diagnostics](#7-support-tickets-and-live-assistant-diagnostics)

---

## 1. Dashboard Overview (Home)

### 💡 What is it for and why?
* **Route:** `/`
* **Purpose:** The Dashboard Overview serves as your central command center. It gives you an instant, high-level snapshot of your active communication channels, recent outreach campaigns, candidate evaluations, and current system engagement.
* **Why use it:** Rather than digging into individual sections, use the Overview to monitor:
  * Running AI interview slots.
  * Active survey voice-calls and completed response counts.
  * Live QR code scan activity.
  * A summary of recently processed campaign statistics.

---

## 2. AI Interview campaigns (Automated Candidate Screening)

### 💡 What is it for and why?
* **Route:** `/interviews`
* **Purpose:** High-volume candidate pre-screening using interactive, professional voice AI ("Leo").
* **Why use it:** Recruiting manually takes hours of calling and coordination. The AI Interview service automates CV screening and phone interviews. Candidates book their preferred slots, the Voice AI conducts a structured phone call, and the dashboard aggregates traits and scores to deliver structured hire recommendations.

### ⚙️ How to use it step-by-step
1. **Upload Candidates:** Navigate to `/interviews/new`. Upload candidate CV documents manually (PDF/Docx) or receive them automatically via job board integrations.
2. **Review ATS Scoring:** The dashboard runs an automated parser to extract qualifications, scoring applicants against the target role.
3. **Approve Interview Script:** Approve the structured script preview. Questions 1–2 are personalized CV templates which the AI adjusts for each candidate; questions 3+ are matching criteria questions standard across all applicants.
4. **Set Calling Window:** Define the date and time ranges when the Voice AI is permitted to dial.
5. **Launch Campaign:** Candidates are notified via email and WhatsApp with a booking link (`/book/{token}`).
6. **Self-Serve Scheduling:** Candidates pick an open 4-minute slot on your scheduling calendar.
7. **The Phone Screening:** At the selected slot time, Voice AI "Leo" dials the candidate, asks the criteria questions, and transcribes the conversation.
8. **View Scorecard:** Go to `/interviews/results` to listen to actual audio recordings, review transcript text, check specific trait evaluations, and view fit recommendations.

### ❓ What problems you may have & what to do/what not to do

* **Problem: The candidate is scheduled, but the AI hasn't called them.**
  * **What to do:** 
    1. Verify that your calling window is currently active and has not expired.
    2. Check the UK local time (`Europe/London`). Calls do not dial outside standard business hours (09:00 - 17:30 UK time) unless you have enabled "Relaxed Hours" mode.
    3. Ensure the candidate's phone number is verified, has the correct E.164 country code (e.g., `+44...`), and is not listed in your Opt-Out list.
  * **What NOT to do:** Do not schedule candidate slots within 30 minutes of the closing window limit, as the scheduler requires setup buffer time.

* **Problem: Candidates receive slots that are too early or late.**
  * **What to do:** The booking grid strictly standardizes time slots based on UK timezone rules. Check that your scheduled start and end limits in Step 4 match your target recruitment timeline.
  * **What NOT to do:** Do not leave your booking window wide open over weekends or holidays unless your HR staff is actively tracking incoming scores.

---

## 3. WhatsApp (WA) Surveys (Interactive Chat Campaigns)

### 💡 What is it for and why?
* **Route:** `/surveys` (Channel: WhatsApp)
* **Purpose:** Conduct conversational patient or customer surveys directly inside WhatsApp chat.
* **Why use it:** Traditional email surveys get low response rates. WhatsApp surveys achieve high response rates by asking approved questions step-by-step in a comfortable, linear, or graph-based flow.

### ⚙️ How to use it step-by-step
1. **Upload Contact List:** Navigate to `/surveys/new` and select the **WhatsApp** channel. Upload your CSV recipient list.
2. **Build Your Question Flow:** Choose a preset campaign template (e.g., patient satisfaction) or define a structured flow using Linear (fixed sequence) or Graph (branching logic based on answers) mode.
3. **Review Approved Templates:** Verify that your selected questions match approved templates. Custom edits must go through Meta's automated approval process first.
4. **Launch and Monitor:** Launch the campaign. The system dispatches the initial WhatsApp message and handles recipient responses automatically.
5. **View Results:** Go to `/surveys/results` to inspect reply transcripts, view NPS indicators, and extract answers.

### ❓ What problems you may have & what to do/what not to do

* **Problem: Sent surveys are failing or showing "undelivered".**
  * **What to do:** Check if your virtual sender number has active credits. Ensure your templates are marked as "approved/live" in the system before triggering them.
  * **What NOT to do:** Do not edit template text mid-campaign. WhatsApp requires exact, pre-approved spacing and variable placeholders; custom additions can cause deliveries to be blocked.

* **Problem: A recipient cannot receive any further messages.**
  * **What to do:** The user may have opted out. If a test handset gets blocked with network rule restrictions, send **UNSTOP** on WhatsApp to your sender virtual number to lift the automatic opt-out block.
  * **What NOT to do:** Do not repeatedly trigger campaigns to numbers that have replied **STOP** or opted out, as this can lead to your WhatsApp Business number being suspended.

---

## 4. WhatsApp (WA) Calling Surveys (AI phone voice polls)

### 💡 What is it for and why?
* **Route:** `/surveys` (Channel: AI phone call)
* **Purpose:** Reach customer or patient lists quickly via automated, verbal AI surveys.
* **Why use it:** Great for senior cohorts or urgent notifications (like recall outreach). The AI dials the list, reads questions aloud, interprets spoken answers, and compiles results instantly.

### ⚙️ How to use it step-by-step
1. **Create Campaign:** Navigate to `/surveys/new` and select **AI phone call**.
2. **Import Numbers:** Upload your recipient list CSV with valid phone numbers.
3. **Select Script and Window:** Choose a pre-defined survey script. Define your Calling Window to set boundaries on when dialing is permitted.
4. **Launch Call Outbound:** The system automatically manages dialing lines, connects to recipients, presents your questions, transcribes voice replies, and saves structured summaries in your dashboard reports.

### ❓ What problems you may have & what to do/what not to do

* **Problem: Calls are getting declined or disconnected immediately.**
  * **What to do:** Verify your calling hours. The system enforces strict compliance, automatically blocking automated calls outside of standard UK hours (09:00 to 17:30 UK local time) unless the "Relaxed Hours" mode is enabled.
  * **What NOT to do:** Do not upload landline or mobile numbers with missing country codes, as the telephony network cannot route them.

* **Problem: Captured answers are cut off or inaccurate.**
  * **What to do:** Tell recipients beforehand or keep questions simple (Yes/No or 1-10 scores). Voice recognition works best with clear, short answers.
  * **What NOT to do:** Do not use long, complex open-ended questions on phone polls. Use WhatsApp surveys instead for lengthy textual feedback.

---

## 5. Customer Feedback (QR-code Local Branch Loops)

### 💡 What is it for and why?
* **Route:** `/feedback`
* **Purpose:** Capture instant, location-specific patient or guest reviews via physical QR codes placed inside your venues.
* **Why use it:** Collecting feedback at the point of experience yields the most accurate reviews. Guests scan a QR code at your checkout or reception, opening WhatsApp instantly. They complete a conversational, topic-based review in their native language (English or Arabic supported) in seconds.

### ⚙️ How to use it step-by-step
1. **Create Branch Locations:** Navigate to `/feedback/new` and specify your branch locations.
2. **Select Evaluation Topics:** Choose your industry (e.g., Dental, Retail) and toggle up to 6 key areas you want rated (e.g., cleanliness, wait time, staff).
3. **Print QR Material:** Download the unique high-resolution QR codes generated for each branch and print them.
4. **Position in Venues:** Place printed QR sheets prominently at your waiting area, reception desk, or exits.
5. **The Guest Flow:** Guests scan the QR, triggering an automated WhatsApp survey. The system translates questions to Arabic automatically for Arabic country codes, saving everything as English on your dashboard.
6. **Track Branch Scores:** View branch-by-branch satisfaction levels, specific topic reviews, and marketing opt-ins on `/feedback/results`.

### ❓ What problems you may have & what to do/what not to do

* **Problem: Scanning the QR code displays "invalid location code".**
  * **What to do:** Check your printed QR. The pre-filled WhatsApp message must end with the static 6-character reference suffix (e.g., `acme-marylebone-a3f2b1`). If this code is missing or altered, the system cannot link the chat to your branch.
  * **What NOT to do:** Do not add emojis or custom text to the QR link's default message payload, as this can break the tracking reference parser on some devices.

* **Problem: I want to change the survey questions. Do I need to reprint the physical QR codes?**
  * **What to do:** No! Simply edit the branch's topics or closing questions on the dashboard. The changes sync instantly, while the physical QR and its reference suffix remain unchanged.
  * **What NOT to do:** Do not delete a branch location to reset its configuration; use the **Edit Survey** option to change topics. Deleting a branch permanently breaks any printed QR materials linked to it.

---

## 6. Account Billing, Packages, Wallet, and Quotas

### 💡 What is it for and why?
* **Routes:** `/account/billing`, `/account/usage`, `/account/packages`
* **Purpose:** Manage your billing status, subscription allowances, and prepaid wallet.
* **Why use it:** VoxBulk is a pay-for-usage platform. Monitoring quotas prevents campaign blocks and keeps your integrations running smoothly.

### ⚙️ How Billing Works
* **Monthly Packages:** Standard subscription plans (Starter, Practice, Group) are billed monthly via GoCardless Direct Debit. These packages provide a monthly quota of Calls, WhatsApp sends, and SMS.
* **Prepaid Wallet:** Your wallet handles campaign setup costs and overage charges. You can top up using credit or debit cards via Stripe or Airwallex (minimum top-up is £5).
* **Overage Charges:** Once your monthly package allowances are fully consumed, extra usage is billed per-minute or per-message directly from your prepaid wallet balance.
* **Campaign Reconciliation:** If you launch a survey for 100 people but only 80 are messaged, the unused balance is refunded back to your prepaid wallet automatically.

### ❓ What problems you may have & what to do/what not to do

* **Problem: The "Launch" button is disabled on my campaigns.**
  * **What to do:** 
    1. Navigate to `/account/billing` and check your wallet balance and outstanding invoices.
    2. Ensure you have an active Direct Debit mandate configured.
    3. Check if your outstanding balance has exceeded your credit limit. If so, pay pending invoices to restore campaign access.
  * **What NOT to do:** Do not delete your active GoCardless mandate while campaigns are running, as this will trigger an immediate launch freeze on your account.

* **Problem: I just signed up for Direct Debit, but my campaign is still blocked.**
  * **What to do:** Direct Debit networks (Bacs, ACH, PAD) require **3 to 7 business days** to clear first-payment verification. Your account status will show `pending_first_payment` during this time.
  * **What NOT to do:** Do not delay urgent outreach while waiting for bank clearing. Top up your prepaid wallet via Stripe for immediate campaign access.

---

## 7. Support Tickets and Live Assistant Diagnostics

### 💡 What is it for and why?
* **Route:** `/account/support/tickets`
* **Purpose:** Solve platform issues quickly through in-app live chat and structured support ticket tracking.
* **Why use it:** If you run into campaign issues or billing questions, our Live Assistant can guide you. If you need engineering intervention, creating a support ticket automatically packages diagnostic logs so our team can resolve your issue quickly.

### ⚙️ How to use it step-by-step
1. **Engage Live Chat:** Click the support bubble on the bottom right.
2. **Ask Questions:** Ask questions about billing, campaign results, usage limits, or menu navigation.
3. **Submit Ticket:** If the assistant cannot solve your issue, confirm the prompt to **Send ticket to support**.
4. **Diagnostic Attachments:** The system automatically bundles your active route, enabled services, subscription tier, and error logs, sending them directly to engineers.
5. **Track Updates:** Review, update, or close your submitted issues on `/account/support/tickets`.

### ❓ What problems you may have & what to do/what not to do

* **Problem: The chat assistant keeps telling me "Policy Refused".**
  * **What to do:** The in-app chat assistant is **Read-Only** for safety. It can answer questions and navigate you to menus, but it cannot process refunds, edit templates, or delete active campaigns. You must perform those actions manually on their respective pages.
  * **What NOT to do:** Do not ask the assistant to make billing edits or campaign changes. Instead, navigate to `/account/billing` or `/surveys` to perform those updates yourself.
