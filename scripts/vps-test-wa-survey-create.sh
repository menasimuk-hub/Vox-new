#!/usr/bin/env bash
# Print (and optionally open) the Create Survey wizard URL for VPS testing.
#
# Usage — run from repo root (/www/voxbulk on VPS):
#   ./scripts/vps-test-wa-survey-create.sh
#   DASHBOARD_URL=https://dashboard.voxbulk.com ./scripts/vps-test-wa-survey-create.sh
#
# On a headless VPS there is no browser — copy the URL and open it on your laptop.
# Set OPEN_BROWSER=1 only on a machine with a desktop (Mac/Linux with DISPLAY).
#
# Query params:
#   channel=whatsapp               — skip channel picker
#   industry_slug=hospitality_food — auto-select Hospitality & food in Step 1

set -euo pipefail

DASHBOARD_URL="${DASHBOARD_URL:-https://dashboard.voxbulk.com}"
TEST_PATH="/surveys/new?channel=whatsapp&industry_slug=hospitality_food"
FULL_URL="${DASHBOARD_URL%/}${TEST_PATH}"

echo "WA survey create test URL:"
echo "  ${FULL_URL}"
echo
echo "Steps:"
echo "  1. Log in to the dashboard if prompted"
echo "  2. Step 1 should show Hospitality & food selected (hotel + food icons)"
echo "  3. Pick 1–4 survey types in Step 2"
echo "  4. Pick welcome, middle templates, thank-you in Step 3 — errors show in red box"
echo
echo "Deploy first (API + dashboard — script does NOT deploy):"
echo "  VOX_GIT_BRANCH=feat/wa-survey-template-library ./deploy-vps.sh"
echo
echo "Icon / error UI only appear after dashboard deploy (not vps-sync-dashboard alone)."
echo "On VPS: copy the URL above into Chrome on your PC — do not expect xdg-open to work here."

if [[ "${OPEN_BROWSER:-0}" == "1" ]] && [[ -n "${DISPLAY:-}" ]]; then
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "${FULL_URL}" >/dev/null 2>&1 || true
  elif command -v open >/dev/null 2>&1; then
    open "${FULL_URL}" || true
  fi
fi
