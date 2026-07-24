# Zoho Marketplace — submit checklist (VoxBulk AI Voice Screening)

Use this after the extension ZIP is ready. Zoho reviews the listing; approval time is controlled by Zoho.

## 1. Vendor account

- [ ] Create / sign in to [Zoho Marketplace vendor](https://marketplace.zoho.com/) (partner / vendor console)
- [ ] Organisation legal name, support email, website: `https://voxbulk.com`
- [ ] Privacy policy URL ready (use your live privacy page on voxbulk.com)

## 2. Extension artifact

- [ ] Build ZIP: `zoho-recruit-extension/dist/VoxBulk-Zoho-Recruit-Widget.zip`  
  Contents: `plugin-manifest.json` + `app/` (widget.html, js, css, img)
- [ ] Confirm hosted widget loads: https://dashboard.voxbulk.com/zoho-recruit-widget/
- [ ] Confirm Partner API health: `POST https://api.voxbulk.com/partner/v1/screenings` with sandbox key returns a screening link

## 3. OAuth / API (VoxBulk side — already configured in Admin)

| Item | Value |
|------|--------|
| OAuth redirect | `https://api.voxbulk.com/partner/v1/oauth/zoho/callback` |
| Partner inbound | `https://api.voxbulk.com/partner/v1/screenings` |
| Partner name header | `zoho` |
| Recruit scopes (dashboard Connect) | `ZohoRecruit.modules.ALL ZohoRecruit.users.ALL` |
| Data centres | Per-org at Connect time (EU / UK / US / CA / …) |

- [ ] Admin → Partners → Zoho: Enabled, Client ID/Secret saved, sandbox or live key generated
- [ ] Mapped org has Dashboard → Integrations → Recruiting → Zoho Recruit connected (for writeback demos)

## 4. Listing content (paste into Zoho Marketplace form)

**Name:** VoxBulk AI Voice Screening  

**Short description:** AI phone screening for Zoho Recruit candidates (English & Arabic). Open VoxBulk from the Candidate record; import lists, run ATS and AI interviews in Dashboard; scores write back to Zoho Notes.  

**Long description (draft):**  
VoxBulk runs AI voice interviews for your candidates. Install the extension, open a Candidate, jump to VoxBulk Dashboard to create a campaign, import your Zoho list, approve AI questions, optionally collect CVs by email and run ATS, then launch AI calls. Scores and status write back to the same Zoho Candidate. Works across Zoho data centres. Organisations connect Recruit OAuth from the VoxBulk dashboard.

**Category:** Recruiting / ATS / HR  

**Support:** support email / https://voxbulk.com (or dashboard Support)  

**Screenshots to capture:**  
1. Candidate page with VoxBulk panel  
2. Launch screening success + booking link  
3. VoxBulk dashboard Recruiting Connect  
4. Score/note on Zoho Candidate after completion  

## 5. Submit steps (Zoho console)

1. Open Zoho Marketplace vendor console → submit / publish extension for **Zoho Recruit**
2. Upload the ZIP (or register external widget URL if the form asks for hosting)
3. Fill listing fields from section 4
4. Declare permissions / data use (Candidate fields: id, name, phone, email; screening results written back)
5. Submit for Zoho review
6. Track review status in the vendor console until **Approved / Published**

Official references:

- Widgets overview: https://www.zoho.com/recruit/developer-console/widgets/
- Widget usage / hosting: https://www.zoho.com/recruit/developer-console/widgets/usage.html
- Marketplace: https://marketplace.zoho.com/

## 6. After approval — customer experience

1. Customer opens Zoho Recruit → Marketplace → Install **VoxBulk AI Voice Screening**
2. Admin generates Partner API key (or you provision) and customer pastes it once in the extension config / widget
3. Customer connects Recruit on VoxBulk dashboard (data centre) for writeback
4. Open Candidate → Launch screening

## 7. Fallback while pending review

Dashboard Launch remains live:  
https://dashboard.voxbulk.com → Settings → Integrations → Recruiting → Zoho Recruit → Launch screening
