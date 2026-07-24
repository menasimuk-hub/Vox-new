# VoxBulk AI Voice Screening — Zoho Recruit Marketplace extension

Installable Zoho Recruit app. After Zoho Marketplace approval, customers **Install** VoxBulk and launch AI screening from a Candidate page.

## Backend (already live)

| Step | System |
|------|--------|
| Create screening | `POST https://api.voxbulk.com/partner/v1/screenings` |
| Headers | `X-API-Key`, `X-Partner-Name: zoho` |
| Org Connect / Launch (fallback) | Dashboard → Integrations → Recruiting |
| Score writeback | Zoho Candidate note/fields via OAuth on the VoxBulk org |

## Package layout

```
zoho-recruit-extension/
  plugin-manifest.json   # ZET / Marketplace widget locations
  app/widget.html        # Candidate UI
  app/js/widget.js
  app/css/widget.css
  app/img/logo.svg
  dist/*.zip             # Upload / submit artifact
  MARKETPLACE_SUBMIT.md  # Submit checklist for Zoho
```

Hosted twin (external URL for widget hosting):

`https://dashboard.voxbulk.com/zoho-recruit-widget/`

## Pack ZIP

```bash
cd zoho-recruit-extension
npm install -g zoho-extension-toolkit
zet validate
zet pack
```

Or zip `app/` + `plugin-manifest.json` into `dist/VoxBulk-Zoho-Recruit-Widget.zip`.

## Admin

Admin → Partners → Zoho → **Zoho app** tab = Marketplace submit / install notes only.
