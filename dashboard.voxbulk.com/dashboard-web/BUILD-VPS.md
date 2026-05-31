# Deploy new dashboard to VPS (static wwwroot)

The **new UI** builds to `dist/client/` (not `dist/`).

## On VPS — every update

```bash
cd /www/voxbulk
git pull origin main

cd dashboard.voxbulk.com/dashboard-web
npm install
npm run build

# IMPORTANT: rsync dist/client/  (with trailing slash) — NOT dist/
sudo rsync -a --delete --exclude='.user.ini' dist/client/ /www/wwwroot/dashboard.voxbulk.com/
```

Hard-refresh browser: **Ctrl+Shift+R**.

## How to know it worked

View page source on https://dashboard.voxbulk.com/

- **NEW theme:** `styles-Bwln9hXe.css`, `index-Bjm_kGr3.js`, title `Dashboard — VoxBulk`
- **OLD theme (wrong):** `tabler-icons`, title `VoxBulk — App Dashboard`

## Wrong command (do not use)

```bash
# WRONG — copies empty client/ + server/ folders, no index.html at root
rsync dist/ /www/wwwroot/dashboard.voxbulk.com/
```
