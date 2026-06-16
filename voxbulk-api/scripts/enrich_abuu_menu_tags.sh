#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python scripts/enrich_abuu_menu_tags.py "$@"
