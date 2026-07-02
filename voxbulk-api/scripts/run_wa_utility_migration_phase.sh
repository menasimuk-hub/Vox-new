#!/usr/bin/env bash
# Run one WA UTILITY migration phase on VPS.
# Prerequisite: Admin → Integrations → Telnyx → WhatsApp WABA ID = 1033532842963987
# Usage:
#   bash scripts/run_wa_utility_migration_phase.sh survey 1 --dry-run
#   bash scripts/run_wa_utility_migration_phase.sh feedback 1 --rewrite-only --translate-ar
#   bash scripts/run_wa_utility_migration_phase.sh feedback 1 --push --languages en,ar
#   bash scripts/run_wa_utility_migration_phase.sh interview --push

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source .venv/bin/activate

python scripts/verify_wa_utility_waba.py || exit 1

PRODUCT="${1:?product required: survey|feedback|interview}"
shift || true

if [[ "$PRODUCT" == "interview" ]]; then
  exec python scripts/migrate_wa_templates_utility.py --product interview --sync-remote "$@"
fi

PHASE="${1:?phase number required for survey/feedback}"
shift || true
exec python scripts/migrate_wa_templates_utility.py --product "$PRODUCT" --phase "$PHASE" --sync-remote "$@"
