#!/usr/bin/env bash
# Run on VPS: bash scripts/e2e_interview_workflow_test.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY=""
for candidate in "$ROOT/.venv/bin/python3" "$ROOT/venv/bin/python3" "$(command -v python3)"; do
  if [[ -n "$candidate" && -x "$candidate" ]]; then
    PY="$candidate"
    break
  fi
done

if [[ -z "$PY" ]]; then
  echo "ERROR: python3 not found. Install: apt install python3" >&2
  exit 1
fi

echo "Using: $PY"
exec "$PY" "$ROOT/scripts/e2e_interview_workflow_test.py" "$@"
