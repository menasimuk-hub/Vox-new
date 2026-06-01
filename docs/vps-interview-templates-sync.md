# VPS — Interview templates sync checklist

Run on the VPS after pulling latest code from GitHub.

---

## 1. WhatsApp templates (Telnyx)

Sync from Telnyx after you create/approve templates in the portal:

**Admin UI:** Integrations → Telnyx → **Sync WhatsApp templates**

**Template names (must match exactly):**

| Telnyx template name | Purpose |
|----------------------|---------|
| `interview_email_sent` | Launch notice — “check careers email” |
| `voxbulk_interview_confirm` | Booking confirmed / rescheduled (date + time) |
| `voxbulk_interview_cancel` | Candidate cancelled their slot |
| `voxbulk_interview_job_closed` | Company stopped/deleted the campaign |
| `voxbulk_interview_book` | Legacy URL booking invite (optional) |

Copy-paste bodies for cancel templates: `docs/telnyx-whatsapp-interview-cancel-templates.md`

---

## 2. Email templates (careers@voxbulk.com)

**Template keys in Admin → Email templates:**

| Key | When sent |
|-----|-----------|
| `interview_booking_invite` | After launch — book a slot |
| `interview_booking_confirm` | Slot booked or rescheduled — **includes Add to calendar** |
| `interview_booking_reminder` | 30 min before call — **includes Add to calendar** |
| `interview_booking_cancel` | Candidate cancelled |
| `interview_campaign_cancelled` | Company stopped/deleted job |
| `interview_zoom_invite` | Zoom delivery (if used) |

**Push latest HTML from code (recommended after deploy):**

```bash
cd /path/to/voxbulk-api
source .venv/bin/activate   # or your venv
python scripts/sync_interview_email_templates.py
sudo systemctl restart voxbulk-api   # or your service name
```

Or restart the API once — on first send, `ensure_system_templates` auto-upgrades confirm/reminder bodies if they are missing `{{calendar_links_html}}`.

---

## 3. Environment (production)

```env
BOOKING_APP_ORIGIN=https://book.voxbulk.com
PUBLIC_APP_ORIGIN=https://voxbulk.com
DASHBOARD_APP_ORIGIN=https://dashboard.voxbulk.com
TRUSTED_HOSTS=api.voxbulk.com,localhost,127.0.0.1
```

Calendar `.ics` downloads use: `https://api.voxbulk.com/public/interview-booking/{token}/calendar.ics`

---

## 4. Quick verify

1. Book a test slot → confirm email shows **Google Calendar · Outlook · Apple / .ics**
2. Open `.ics` link → file downloads
3. Cancel via WhatsApp → cancel email + `voxbulk_interview_cancel` WA
4. Stop interview task → `interview_campaign_cancelled` email + `voxbulk_interview_job_closed` WA
