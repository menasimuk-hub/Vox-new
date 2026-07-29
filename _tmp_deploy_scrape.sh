#!/bin/bash
cd /www/voxbulk || exit 1
git pull origin main
# Reload API workers (prefer systemd)
if systemctl is-active --quiet voxbulk-api 2>/dev/null; then
  sudo -n systemctl reload voxbulk-api 2>/dev/null || sudo -n systemctl restart voxbulk-api 2>/dev/null || ./vox.sh restart
else
  ./vox.sh restart
fi
sleep 4
python3 /tmp/_tmp_health.py
cd /www/voxbulk/voxbulk-api
source .venv/bin/activate
PYTHONPATH=. python -u /tmp/_tmp_inline_scrape.py
