# Smart Card QR

Independent VoxBulk service for representative digital cards (QR → WhatsApp / web leads).

## Enable

1. Admin → Onboarding → Services → allow **Smart Card QR** for the org  
2. Dashboard → Settings → Services → turn **Smart Card QR** on  
3. Create mailbox **`smartqr@voxbulk.com`** on aaPanel and configure Admin → Smart Card mailbox SMTP (API: `GET/PUT /admin/smart-card/mailbox`)

## Packages

- Default: **$5 / seat / month, billed yearly** ($60 / seat / year) — Admin editable via Pricing Packages (`service_kind=smart_card`)  
- Checkout: Dashboard → Packages → choose seat quantity → Stripe/Airwallex (`POST /smart-card/billing/checkout` + `/complete`)  
- Preview: **15** free QR tests, then stop until paid  
- Expiry: Celery beat `smart-card-renewal-reminders-daily` (30d / 14d / 7d / 1d); public + dashboard expired page with Renew

## Channels

- Web: `https://voxbulk.com/smart-card/{qr_token}`  
- WhatsApp: Telnyx inbound routes Smart Card tokens/sessions (after Expo, before Feedback)  
- SMTP From: `smartqr@voxbulk.com` (dedicated mailbox settings)

## APIs

| Prefix | Audience |
|--------|----------|
| `/smart-card` | Dashboard (company, catalogue, reps, leads, change-requests, seat billing) |
| `/public/smart-card/{token}` | Visitor landing + web session + card OCR |
| `/admin/smart-card` | Questions, mailbox, seed, overview |

## Deploy

```bash
cd /www/voxbulk
git pull origin main
./deploy-vps.sh
```
