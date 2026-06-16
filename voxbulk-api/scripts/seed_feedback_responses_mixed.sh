#!/usr/bin/env bash
# Run Customer Feedback response seed using the API virtualenv.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/seed_feedback_responses_mixed.py" "$@"
