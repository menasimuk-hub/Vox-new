#!/usr/bin/env bash
# Tail Abuu waiter / SmartPipeline trace lines on VPS (delegates to live trace script).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "$ROOT/scripts/vps-abuu-live-trace.sh" "$@"
