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

Per exhibition (`service_kind=expo`, interval `one_time`):

| Package | GB price | Scoring | Post-show follow-up | Post-event survey | AI summary |
|---|---|---|---|---|---|
| Expo Starter (`expo_starter_gb`) | £49 | No | No | No | No |
| Expo Pro (`expo_pro_gb`) | £99 | Yes | Yes | No | No |
| Expo Premium (`expo_premium_gb`) | £149 | Yes | Yes | Yes | Yes |

Also seeded for `eu` / `us` / `ca` / `au` zones. Checkout is not wired yet — packages are assignable/visible.

## Messaging

Visitor opens WhatsApp first (QR) → **24h session window** → questions and PDF links sent as **session text** (no Meta HSM for live Q&A). Product delivery uses hybrid match-or-list against booth assets.

## Deploy

```bash
cd /www/voxbulk   # or your repo root
git pull origin main
./deploy-vps.sh
```

Migration `0180_expo_foundation` applies on deploy. Boot seed creates industries + packages.
