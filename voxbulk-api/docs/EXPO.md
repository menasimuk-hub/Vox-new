# VoxBulk Expo

WhatsApp exhibition lead capture (sibling product to Customer Feedback).

## Enable / roles

| Layer | Who |
|---|---|
| Admin grant | Admin → Onboarding services → **VoxBulk Expo** (`allowed_services.expo`) |
| Org toggle | Dashboard → Settings → Services → **VoxBulk Expo** (`enabled_services.expo`) |
| Campaign use (create/delete booths, view own leads) | `owner`, `manager`, `member` |
| Billing / packages page | `owner`, `manager`, `accountant` |
| Accountant | Billing-only UI — Account → Expo packages (no campaign sidebar) |

Members only see booths they created (same campaign-owner filter as Feedback).

## Price list (seeded)

Per exhibition (`service_kind=expo`, interval `one_time`) — duration packages:

| Package | Days active | GB price | Scoring |
|---|---|---|---|
| Expo 1 Day (`expo_day1_gb`) | 1 | £49 | Yes |
| Expo 3 Days (`expo_day3_gb`) | 3 | £99 (featured) | Yes |
| Expo 7 Days (`expo_day7_gb`) | 7 | £149 | Yes |

Also seeded for `eu` / `us` / `ca` / `au` zones. Legacy Starter/Pro/Premium codes are deactivated on seed. Checkout is not wired yet — selecting a package activates the booth for N days from activation (`expires_at`).

## Messaging

Visitor opens WhatsApp first (QR) → **24h session window** → questions and PDF links sent as
**plain session text from the server** (Meta Cloud API or Telnyx `type=text`). **No Meta HSM
templates** are used for live booth Q&A.

Contact capture (fixed): business-card photo **or** name / company (web also asks for mobile).
Photo skips typed contact fields. Exhibitors then select extra qualifying questions from a bank.

Product files: PDF, image, or Excel — delivered as absolute `https://api.voxbulk.com/public/expo/assets/...`
links (or the visitor’s external URL). Hybrid match-or-list against booth assets.

Inbound is wired on **both** Meta and Telnyx WhatsApp webhooks (Expo before Customer Feedback).

**Session isolation (shared WA line):** one visitor phone may only have one **active** Expo
session. Scanning a new booth QR (or starting web again) **supersedes** any prior active
session for that phone, so Stand A questions / price lists never continue after Stand B.

**Business card photo:** visitor sends an image on WhatsApp → OpenAI vision OCR extracts
name / company / email / phone → reply “Got your details…” → skips typed name/company/mobile.

## Deploy

```bash
cd /www/voxbulk   # or your repo root
git pull origin main
./deploy-vps.sh
```

Migration `0180_expo_foundation` applies on deploy. Boot seed creates industries + packages.

## Closing message

After the questionnaire completes, Expo always sends a **thank-you** message.

Optional wizard toggle: **Offer a free gift after the questionnaire**. When enabled, the thank-you is followed by the exhibitor’s gift instructions (e.g. “Please collect your free gift from our stand team…”).
