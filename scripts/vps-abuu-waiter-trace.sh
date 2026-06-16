#!/usr/bin/env bash
# Tail Abuu waiter pipeline trace lines on VPS.
set -euo pipefail

API_LOG="${VOX_API_LOG:-/tmp/voxbulk-api.log}"

if [[ ! -f "$API_LOG" ]]; then
  echo "Log not found: $API_LOG" >&2
  echo "Set VOX_API_LOG or start API via ./vox.sh restart" >&2
  exit 1
fi

echo "Tailing abuu_waiter_trace from $API_LOG (Ctrl+C to stop)"
tail -f "$API_LOG" | grep --line-buffered abuu_waiter_trace
