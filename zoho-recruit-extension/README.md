# VoxBulk Zoho Recruit widget

Embed AI Voice Screening inside Zoho Recruit (Candidate detail / custom button).

## Install (your Zoho — no Marketplace wait)

### External host (fastest)

1. Zoho Recruit → Setup → Widgets → Add widget  
2. Hosting: External  
3. URL: https://dashboard.voxbulk.com/zoho-recruit-widget/  
4. Attach to Candidates detail or a Custom Button  
5. Open Candidate → widget → paste Partner API key → Launch  

### Internal ZIP

Upload `dist/VoxBulk-Zoho-Recruit-Widget.zip` in Zoho Developer Console (Internal hosting).

Or rebuild:

```bash
cd zoho-recruit-extension
npm install -g zoho-extension-toolkit
zet validate
zet pack
```

## API key

Admin → Partners → Zoho → API keys.

## Writeback

Admin Mapped org must have Dashboard → Integrations → Recruiting → Zoho Recruit connected.

## Deluge fallback

See `deluge/launch_screening.dg` for a Candidate custom button without a widget UI.

## Marketplace

Same widget; public listing needs Zoho Marketplace submission + review.
