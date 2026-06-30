#!/usr/bin/env bash
# Seed demo data for a salesman workspace (run on the VPS, inside the repo root).
#
# Usage:
#   ./seed-sales-demo.sh salesman1@voxbulk.com
#   ./seed-sales-demo.sh salesman1@voxbulk.com --reset
#
# It (1) ensures the 'sales ai survey' demo agent exists, then (2) seeds the
# salesman's workspace with interviews, surveys, campaigns, and feedback QR data.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
API_DIR="$ROOT/voxbulk-api"

EMAIL="${1:-}"
if [ -z "$EMAIL" ]; then
  echo "Usage: ./seed-sales-demo.sh <salesman-email> [--reset]" >&2
  exit 1
fi
shift || true

cd "$API_DIR"
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Ensuring 'sales ai survey' demo agent..."
python scripts/seed_sales_ai_survey_agent.py

echo "==> Seeding demo data for $EMAIL ..."
python -m scripts.seed_sales_demo --email "$EMAIL" "$@"

echo "Done."
