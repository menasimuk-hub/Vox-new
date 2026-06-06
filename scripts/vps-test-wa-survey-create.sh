#!/usr/bin/env bash
# Open the Create Survey wizard pre-filled for VPS testing (Hospitality & food + WhatsApp).
#
# Usage:
#   ./scripts/vps-test-wa-survey-create.sh
#   DASHBOARD_URL=https://dashboard.voxbulk.com ./scripts/vps-test-wa-survey-create.sh
#
# Query params:
#   channel=whatsapp          — skip channel picker
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
echo "Deploy reminder (API + dashboard):"
echo "  VOX_GIT_BRANCH=feat/wa-survey-template-library ./deploy-vps.sh"

if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "${FULL_URL}" >/dev/null 2>&1 || true
elif command -v open >/dev/null 2>&1; then
  open "${FULL_URL}" || true
fi
