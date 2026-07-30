# Smart Card QR

Independent VoxBulk service for representative digital cards (QR → WhatsApp / web leads).

## Enable

1. Admin → Onboarding → Services → allow **Smart Card QR** for the org  
2. Dashboard → Settings → Services → turn **Smart Card QR** on  
3. Create mailbox **`smartqr@voxbulk.com`** on aaPanel and configure Admin → Smart Card mailbox SMTP (API: `GET/PUT /admin/smart-card/mailbox`)

## Packages

- Default: **$5 / seat / month, billed yearly** ($60 / seat / year) — Admin editable via Pricing Packages (`service_kind=smart_card`)  
- Preview: **15** free QR tests, then stop until paid  
- Expiry: renewal reminders 30d / 14d / 7d / 1d (worker TBD); public + dashboard expired page with Renew

## APIs

| Prefix | Audience |
|--------|----------|
| `/smart-card` | Dashboard |
| `/public/smart-card/{token}` | Visitor landing status |
| `/admin/smart-card` | Questions, mailbox, seed, overview |

## Deploy

```bash
cd /www/voxbulk
git pull origin main
./deploy-vps.sh
```
