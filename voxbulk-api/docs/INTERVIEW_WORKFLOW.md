# AI interview workflow (email + WhatsApp + call + report)

All times shown to candidates are **UK time (Europe/London)**. Slots are stored in UTC with a `Z` suffix in the API.

## Simple flow

```mermaid
flowchart TD
    A[Employer: create campaign + launch] --> B[Invite email + optional WhatsApp]
    B --> C[Candidate opens booking link]
    C --> D{Books a slot?}
    D -->|Yes| E[Confirmation email + optional WhatsApp]
    D -->|No| F[Reminder ~30 min before window ends]
    E --> G[At booked slot time]
    G --> H[AI phone call — Telnyx + Leo assistant]
    H --> I[Transcript + AI score + report]
    D -->|Cancel| J[Cancel email + slot freed]
    J --> C
    E -->|Reschedule| C
    A -->|Stop campaign| K[Cancel emails to booked candidates]
```

## Step detail

| Step | Channel | What happens |
|------|---------|----------------|
| 1. Launch | Dashboard | Campaign `running`; invite sent |
| 2. Invite | **Email** (SMTP careers@) | Link to `/book/{token}` — book interview |
| 2b. Invite | **WhatsApp** (optional) | Same booking link if number is WA-enabled |
| 3. Book | Public booking page | Candidate picks **4-minute** slot (config: `INTERVIEW_SLOT_MINUTES`) |
| 4. Confirm | **Email** | Booking time in UK; add-to-calendar: Google, Outlook, Apple (.ics) |
| 4b. Confirm | **WhatsApp** (optional) | Confirmation template with reschedule/cancel |
| 5. Reminder | Email / WA | ~30 minutes before call (if configured) |
| 6. Call | Phone | Scheduler dials at slot; AI assistant speaks |
| 7. Results | Dashboard | Transcript, score, recommendation, recording |

## Candidate status (backend)

| Status | Meaning |
|--------|---------|
| `pending` / `sent` | Invited, not called yet |
| `scheduled` | Slot booked — eligible for dial at slot time |
| `calling` | On the phone now |
| `completed` | Call finished — report when analysis runs |

## Configuration (VPS)

In `voxbulk-api/.env` on the server:

```env
INTERVIEW_SLOT_MINUTES=4
INTERVIEW_RELAX_HOURS=1
BOOKING_APP_ORIGIN=https://dashboard.voxbulk.com
```

`INTERVIEW_RELAX_HOURS=1` (temporary): 4-minute slots for the full campaign window, no 9:00–17:30 booking cap, and AI calls allowed outside org calling hours. Remove in production.

Restart API after changing env.

## Telnyx

- Interview agent must use a **valid** Telnyx assistant ID (e.g. `Leo- Interview` in portal).
- Stored on agent row `telnyx_assistant_id` in Admin → Agents.

## Before pushing to GitHub

1. Run tests: `pytest tests/test_interview_booking_slots.py tests/test_interview_calendar_service.py -q`
2. On VPS: set `INTERVIEW_SLOT_MINUTES=4`, deploy, restart API
3. Send one test confirmation email and check calendar icons in Outlook + Apple Mail
