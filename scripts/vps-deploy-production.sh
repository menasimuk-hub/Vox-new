#!/usr/bin/env bash
# Production deploy from main — fixes git sync when local HEAD != feat branch.
# Run on VPS from repo root: bash scripts/vps-deploy-production.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export VOX_GIT_BRANCH=main
export VOX_HARD_RESET=1

echo "[vps-deploy-production] Syncing origin/main and deploying …"
exec ./deploy-vps.sh
