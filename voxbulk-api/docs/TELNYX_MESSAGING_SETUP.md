# Telnyx SMS + WhatsApp setup (VOXBULK)

This guide covers Telnyx portal setup, Meta WhatsApp Business connection, VOXBULK admin configuration, and how to test with your real mobile number.

## What VOXBULK exposes

| Purpose | URL |
|---------|-----|
| Inbound SMS + WhatsApp | `POST https://YOUR-PUBLIC-HOST/telnyx/webhooks/messages` |
| Voice call control | `POST https://YOUR-PUBLIC-HOST/telnyx/webhooks/voice` |
| Call status | `POST https://YOUR-PUBLIC-HOST/telnyx/webhooks/status` |

For local dev, run `ngrok http 8000` and use the ngrok **https** URL as your webhook base (no path suffix).

---

## Part 1 — Telnyx portal (SMS)

### 1. API key
1. [Telnyx Portal](https://portal.telnyx.com/) → **API Keys** → Create key.
2. Copy the full secret (`KEY…`, ~58 characters).

### 2. Buy / assign a number
1. **Numbers** → buy or port a number with **SMS** capability (e.g. UK +44).
2. Note the E.164 number (e.g. `+442046203055`).

### 3. Messaging profile
1. **Messaging** → **Messaging Profiles** → **Add profile**.
2. Set **Webhook URL** to:
   ```
   https://YOUR-PUBLIC-HOST/telnyx/webhooks/messages
   ```
3. Enable events: `message.received`, `message.sent`, `message.finalized`.
4. Copy the **Messaging Profile ID** (UUID).

### 4. Assign number to profile
1. Open your number → **Messaging** tab.
2. Assign the **Messaging Profile** you created.

### 5. Voice (if not done already)
1. **Call Control** → create an application / connection.
2. Set voice webhook to `https://YOUR-PUBLIC-HOST/telnyx/webhooks/voice`.
3. Assign the same number to Call Control for outbound voice.

---

## Part 2 — VOXBULK admin

1. Open **Admin → Integrations → Telnyx**.
2. Fill in:
   - **API key**
   - **Connection ID** (Call Control)
   - **Default outbound number** (your Telnyx number)
   - **Webhook base URL** (ngrok or production host, e.g. `https://abc123.ngrok-free.app`)
   - **Messaging profile ID**
   - **SMS from number** (same Telnyx number)
   - **Messaging webhook URL** (auto-computed after save — copy to Telnyx profile)
   - **Default messaging org ID** (optional — org UUID for inbound logs; otherwise first org is used)
3. Click **Save Telnyx**.
4. Click **Test connection** — should return API key OK.
5. Enter **your mobile** in E.164 (`+447…`) and click **Test SMS**.
6. Click **Refresh inbound** after Meta or anyone texts your Telnyx number — messages appear in the list.

---

## Part 3 — Meta WhatsApp Business via Telnyx

Meta verification SMS (and later WhatsApp traffic) flows through Telnyx once connected.

### In Meta Business Manager
1. [business.facebook.com](https://business.facebook.com/) → create or open your Business account.
2. **WhatsApp Manager** → add a phone number for WhatsApp Business.
3. When Meta asks to verify the number, choose **SMS verification** to your mobile **or** verify via the Telnyx number if Meta sends to that line.

### In Telnyx
1. **Messaging** → **WhatsApp** (or **Channels** → WhatsApp).
2. **Connect Meta Business** — follow OAuth to link your Meta Business account.
3. Complete WhatsApp Business profile (display name, category, description).
4. Once approved, Telnyx shows your **WhatsApp-enabled number**.
5. Ensure that number uses the same **Messaging Profile** with webhook `…/telnyx/webhooks/messages`.

### In VOXBULK
1. Set **WhatsApp from number** to the Telnyx WhatsApp number (E.164, e.g. `+442046203055`).
2. Save → **Test WhatsApp** to your personal mobile (must have opted in / 24h window rules apply for production templates).

> **Note:** Outside the 24-hour customer care window, WhatsApp requires **approved message templates**. Use free-form text only for testing inside an open session or with Meta’s test numbers.

---

## Part 4 — Testing checklist

### SMS (your real mobile)
- [ ] ngrok running → webhook base saved in admin
- [ ] Messaging profile webhook = `…/telnyx/webhooks/messages`
- [ ] Number assigned to messaging profile
- [ ] Admin **Test SMS** → SMS arrives on your phone
- [ ] Reply to the Telnyx number → **Refresh inbound** shows your reply

### Meta verification SMS
- [ ] Start WhatsApp number setup in Meta
- [ ] When Meta sends verification SMS, either:
  - it goes to **your mobile** (manual entry in Meta), or
  - it arrives on the **Telnyx number** → appears in **Refresh inbound**
- [ ] Enter the code in Meta to finish verification

### WhatsApp
- [ ] Meta Business linked in Telnyx
- [ ] WhatsApp from number saved in VOXBULK admin
- [ ] **Test WhatsApp** from admin (or `POST /whatsapp/send` from tenant API)
- [ ] Inbound WhatsApp → same `/telnyx/webhooks/messages` endpoint

### API smoke tests (optional)
```bash
# Probe webhook (should return ok: true)
curl https://YOUR-HOST/telnyx/webhooks/messages

# Admin test SMS (requires admin JWT)
curl -X POST https://YOUR-HOST/admin/integrations/telnyx/test-sms \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to_number":"+447700900123","body":"VOXBULK test"}'
```

---

## Part 5 — Deploy to VPS

After pushing code:
```bash
cd /www/voxbulk && git pull origin main
systemctl restart voxbulk-api
cd admin.voxbulk.com/adim-web && npm run build
rsync -a --exclude='.user.ini' dist/ /www/wwwroot/admin.voxbulk.com/
```

Set production webhook base to `https://api.voxbulk.com` (or your API host) — **not** ngrok.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Test SMS 502 / not_configured | Set messaging profile ID + SMS from number; save Telnyx settings |
| Inbound empty | Check messaging profile webhook URL; open ngrok/API logs; verify number on profile |
| Meta code not visible | Click **Refresh inbound**; confirm webhook reaches public URL |
| WhatsApp test fails | Complete Meta + Telnyx WA link; number must be WA-enabled; check 24h window / templates |
| 404 on webhook | Redeploy API; URL must end with `/telnyx/webhooks/messages` |

Twilio has been **removed** from VOXBULK — all SMS, WhatsApp, and voice recovery use **Telnyx only**.
