# Smart Card QR

Independent VoxBulk service for representative digital cards (QR → WhatsApp / web leads).

## Enable

1. Admin → Onboarding → Services → allow **Smart Card QR** for the org  
   - Grant also **auto-enables** the module for the customer (sidebar visible after refresh).
2. Dashboard → Settings → Services → toggle **Smart Card QR** (show/hide) if needed  
3. Create mailbox **`smartqr@voxbulk.com`** on aaPanel and configure Admin → WA Templates → Smart Card QR (SMTP + optional IMAP)

## Admin pricing & products

- Pricing → Packages: section **Smart Card QR** (`service_kind=smart_card`) — yearly seat unit price  
- Products hub: lists Core, Feedback, Expo, Smart Card, Campaigns; green dot = active; active sorted first  
- Deep link: `/pricing/packages?service=smart_card`

## Packages (customer)

- Default: **$5 / seat / month, billed yearly** ($60 / seat / year) — Admin-editable  
- Checkout: seat quantity × yearly unit (`POST /smart-card/billing/checkout` + `/complete`)  
- Preview: **15** free QR tests  
- Expiry: Celery renewal reminders 30d / 14d / 7d / 1d  
- Account → Packages tabs include Expo + Smart Card CTAs

## Channels

- Web: `https://voxbulk.com/smart-card/{qr_token}`  
- WhatsApp: Telnyx inbound (token/session); voice notes transcribed; hot-lead WA to rep mobile  
- Mail: From `smartqr@voxbulk.com`; IMAP sync → support tickets (`category=smart_card`)

## Customer wizard

- Sidebar: **Create Smart Card QR** · **Saved QR codes** · **Lead results** · **Packages & pricing**
- Setup wizard (`/smart-card/new`): company profile (editable) + first salesman → optional products → required questions (scan/fill + bank) → optional offer → preview QR → seat pricing table + quantity → activate
- Add QR (`/smart-card/qrs/new`): representative-only wizard with product assign
- Edit QR: colours, PNG download, product assign
- Seed: Admin seed copies full Expo question bank into Smart Card templates (insert-missing)
- Ops: `/operations/smart-card-insights` — scans, leads, seat `period_end`

## Catalogue

- Categories / products / PDFs via URL **or file upload** (`POST /smart-card/catalogue/assets/upload`)

## Admin content

- Industries + questions CRUD (WA Templates → Smart Card QR)  
- Mailbox: Test send / Test receive / Sync now  

## APIs

| Prefix | Audience |
|--------|----------|
| `/smart-card` | Dashboard |
| `/public/smart-card/{token}` | Visitor landing + web session |
| `/admin/smart-card` | Questions, industries, mailbox, seed, overview |

## Deploy

```bash
cd /www/voxbulk
git pull origin main
./deploy-vps.sh
```
