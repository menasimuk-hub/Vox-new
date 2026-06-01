# Telnyx WhatsApp — Interview cancel templates (copy-paste)

Create these in **Telnyx → Messaging → WhatsApp → Templates**. Names must match exactly. Category: **Utility** (recommended for booking lifecycle messages).

After Meta approves, run **Admin → Integrations → Telnyx → Sync WhatsApp templates** so VoxBulk can send them.

---

## Template 1 — `voxbulk_interview_cancel` (candidate self-cancel)

Sent when a candidate cancels their booked slot via WhatsApp quick reply or the booking page.

| Field | Value |
|-------|--------|
| **Name** | `voxbulk_interview_cancel` |
| **Category** | Utility |
| **Language** | English (US) `en_US` |

**Body** — copy all:

```
Hi {{1}} 👋

Your *{{2}}* interview at *{{3}}* on {{4}} at {{5}} has been cancelled ❌

You will not receive any further messages about this role.

Thank you.
```

**Sample variables:**

| Variable | Sample |
|----------|--------|
| `{{1}}` | Alex |
| `{{2}}` | Senior Dental Hygienist |
| `{{3}}` | Smile Dental Group |
| `{{4}}` | Mon 9 Jun 2026 |
| `{{5}}` | 10:30 AM |

**Buttons:** none (informational only)

**Email pairing:** `interview_booking_cancel` (careers@voxbulk.com) sends at the same time.

---

## Template 2 — `voxbulk_interview_job_closed` (employer closed campaign)

Sent to all active candidates when the company **stops**, **cancels**, or **deletes** the interview task.

| Field | Value |
|-------|--------|
| **Name** | `voxbulk_interview_job_closed` |
| **Category** | Utility |
| **Language** | English (US) `en_US` |

**Body** — copy all:

```
Hi {{1}} 👋

The *{{2}}* role at *{{3}}* is no longer available — this interview campaign has ended 🛑

You will not receive any further messages about this job.

Thank you for your interest.
```

**Sample variables:**

| Variable | Sample |
|----------|--------|
| `{{1}}` | Alex |
| `{{2}}` | Senior Dental Hygienist |
| `{{3}}` | Smile Dental Group |

**Buttons:** none

**Email pairing:** `interview_campaign_cancelled` (careers@voxbulk.com)

---

## Existing template — `voxbulk_interview_confirm` (reschedule / new booking)

When a candidate **reschedules** and picks a new slot on the booking page, VoxBulk already sends:

- **Email:** `interview_booking_confirm`
- **WhatsApp:** `voxbulk_interview_confirm` with Reschedule / Cancel quick-reply buttons

No new template needed for reschedule — only the confirmation template is re-sent with the new date/time.

---

## Booking link blocking (automatic)

The public booking page returns `booking_closed: true` when:

| Scenario | Block message |
|----------|----------------|
| Candidate cancelled via WA / web | No further messages about this job |
| Company stopped / cancelled task | Campaign ended |
| Calling window end date passed | Booking window has ended |
| Order completed | Interviews closed |
| Interview already completed (AI call done) | Booking no longer available |
