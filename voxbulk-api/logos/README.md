# VOXBULK brand assets (API source of truth)

Place logo files here. The API serves them at `/public/brand/{name}`.

| File (any one format) | URL |
|---|---|
| `logo-black.png` or `.svg` | `https://api.voxbulk.com/public/brand/logo-black` |
| `logo-white.png` or `.svg` | `https://api.voxbulk.com/public/brand/logo-white` |
| `icon-black.png` or `.svg` | `https://api.voxbulk.com/public/brand/icon-black` |
| `icon-white.png` or `.svg` | `https://api.voxbulk.com/public/brand/icon-white` |
| `favicon.ico` or `.png` | `https://api.voxbulk.com/public/brand/favicon` |
| `calendar/calendar-google.png` | `https://api.voxbulk.com/public/brand/calendar-google` |
| `calendar/calendar-outlook.png` | `https://api.voxbulk.com/public/brand/calendar-outlook` |
| `calendar/calendar-apple.png` | `https://api.voxbulk.com/public/brand/calendar-apple` |
| `ya.jpg` | `https://api.voxbulk.com/public/brand/ya` |

**PNG is preferred for email** (Outlook blocks SVG and many external icon CDNs). SVG is fine for web/PDF.

After adding files on the VPS:

```bash
ls -la voxbulk-api/logos/
curl -s https://api.voxbulk.com/public/brand | jq .
./vox.sh restart
```

Frontends copy from here via `scripts/sync-brand-assets.mjs` on `npm run build`.
