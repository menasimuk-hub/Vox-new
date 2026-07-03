#!/usr/bin/env bash
# OpenAI 4-phase WA UTILITY migration (VPS).
#
# Prerequisite:
#   Admin → Integrations → Telnyx → WhatsApp WABA ID = 1033532842963987
#   Admin → Integrations → OpenAI configured
#
# Usage:
#   bash scripts/run_wa_utility_migration_phase.sh 0          # seed DB from MD
#   bash scripts/run_wa_utility_migration_phase.sh 1 --dry-run
#   bash scripts/run_wa_utility_migration_phase.sh 1 --save --push --dedup
#   bash scripts/run_wa_utility_migration_phase.sh 4 --save --push --translate-ar --dedup

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source .venv/bin/activate

PHASE="${1:?phase 0-4 required (0=seed only)}"
shift || true

if [[ "$PHASE" == "0" ]]; then
  python scripts/verify_wa_utility_waba.py || true
  python scripts/seed_utility_templates_to_db.py --all
  python scripts/audit_wa_template_db.py --json
  exit 0
fi

python scripts/verify_wa_utility_waba.py
PROGRESS_LOG="/tmp/wa-phase${PHASE}.progress.log"
echo "Live log: tail -f ${PROGRESS_LOG}"
python scripts/migrate_wa_templates_utility.py --phase "$PHASE" --audit "$@" 2>&1 | tee -a "${PROGRESS_LOG}"
exit "${PIPESTATUS[0]}"
