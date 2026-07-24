# VoxBulk AI Voice Screening — Zoho Recruit Marketplace extension

Installable Zoho Recruit app. After Zoho Marketplace approval, customers **Install** VoxBulk and launch AI screening from a Candidate page.

Installable Zoho Recruit app. After Zoho Marketplace approval, customers **Install** VoxBulk and open the Candidate widget to jump into the VoxBulk Dashboard hybrid workflow (import list → AI interview → writeback).

## Hybrid flow (recommended)

| Step | Where |
|------|--------|
| Connect OAuth | Dashboard → Integrations → Recruiting |
| Create campaign + AI questions | Dashboard → Interviews → New |
| Import Zoho candidates | Interview wizard Step 2 |
| Email CV + ATS | Dashboard (careers@ + Run ATS) |
| AI calls + billing | VoxBulk wallet |
| Score writeback | Zoho Candidate Notes (automatic) |

## Backend

| Step | System |
|------|--------|
| Import list | `POST /service-orders/zoho-recruit/candidates/import-to-order` |
| Org Connect | Dashboard OAuth |
| Score writeback | Notes on Candidate via OAuth |

The Marketplace widget is **thin**: shows Candidate context + **Open VoxBulk** deep link (not a one-question launcher).


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
