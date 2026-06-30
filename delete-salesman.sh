#!/usr/bin/env bash
# Completely delete a salesman and ALL their data (demo data included). IRREVERSIBLE.
#
# Usage (on the VPS, in the repo root):
#   ./delete-salesman.sh salesman02@voxbulk.com          # dry run — shows what would be deleted
#   ./delete-salesman.sh salesman02@voxbulk.com --yes    # actually delete everything
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
API_DIR="$ROOT/voxbulk-api"

EMAIL="${1:-}"
if [ -z "$EMAIL" ]; then
  echo "Usage: ./delete-salesman.sh <salesman-email> [--yes]" >&2
  exit 1
fi
shift || true

cd "$API_DIR"
# shellcheck disable=SC1091
source .venv/bin/activate

python -m scripts.delete_salesman --email "$EMAIL" "$@"
