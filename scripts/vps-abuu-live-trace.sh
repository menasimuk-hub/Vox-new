#!/usr/bin/env bash
# Pretty-print Abuu WhatsApp live trace from API log (JSON or plain text).
set -euo pipefail

API_LOG="${VOX_API_LOG:-/tmp/voxbulk-api.log}"
HISTORY=0
FOLLOW=1

usage() {
  cat <<'EOF'
Usage: vps-abuu-live-trace.sh [--history N] [--log PATH]

  (default)     tail -f API log and pretty-print Abuu trace lines
  --history N   print last N matching lines (no follow)
  --log PATH    override log file (default: /tmp/voxbulk-api.log)

Env: VOX_API_LOG
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --history)
      HISTORY="${2:-50}"
      FOLLOW=0
      shift 2
      ;;
    --log)
      API_LOG="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ ! -f "$API_LOG" ]]; then
  echo "Log not found: $API_LOG" >&2
  echo "Start API: ./vox.sh restart" >&2
  exit 1
fi

format_abuu_trace() {
  python3 - "$@" <<'PY'
import json
import re
import sys

MARKERS = (
    "abuu_live_trace",
    "abuu_wa_trace",
    "abuu_smart_pipeline",
    "abuu_waiter_trace",
    "abuu_wa_inbound_handler_failed",
)

EVENT_LABELS = {
    "boot": "BOOT",
    "route": "ROUTE",
    "in": "IN",
    "search": "SEARCH",
    "think": "THINK",
    "out": "OUT",
    "skip": "SKIP",
}


def short_ts(raw: str) -> str:
    if not raw:
        return "??:??:??"
    if "T" in raw and len(raw) >= 19:
        return raw[11:19]
    return raw[:8]


def pick_fields(text: str) -> str:
    pairs = re.findall(r'(\w+)=(?:"([^"]*)"|(\S+))', text)
    if not pairs:
        return text.strip()
    out = []
    for key, quoted, bare in pairs:
        val = quoted if quoted else bare
        out.append(f"{key}={val}")
    return " ".join(out)


def format_message(msg: str, ts: str) -> str | None:
    if not any(marker in msg for marker in MARKERS):
        return None
    stamp = f"[{short_ts(ts)}]"

    if "abuu_live_trace" in msg:
        m = re.search(r"abuu_live_trace\s+(\w+)\s+(.*)", msg)
        if m:
            event, rest = m.group(1), m.group(2).strip()
            label = EVENT_LABELS.get(event, event.upper())
            return f"{stamp} {label:<6} {pick_fields(rest) or rest}"
        return f"{stamp} TRACE  {msg}"

    if "abuu_wa_trace IN" in msg:
        return f"{stamp} WA_IN  {msg.split('abuu_wa_trace IN', 1)[-1].strip()}"
    if "abuu_wa_trace OUT" in msg:
        return f"{stamp} WA_OUT {msg.split('abuu_wa_trace OUT', 1)[-1].strip()}"
    if "abuu_wa_inbound_handler_failed" in msg:
        return f"{stamp} ERROR  {msg}"
    if "abuu_smart_pipeline" in msg:
        return f"{stamp} SMART  {msg.split('abuu_smart_pipeline', 1)[-1].strip()}"
    if "abuu_waiter_trace" in msg:
        return f"{stamp} WAITER {msg.split('abuu_waiter_trace', 1)[-1].strip()}"
    return f"{stamp} ABUU   {msg}"


def handle_line(line: str) -> None:
    line = line.rstrip("\n")
    if not line.strip():
        return
    ts = ""
    msg = line
    try:
        obj = json.loads(line)
        ts = str(obj.get("timestamp") or "")
        msg = str(obj.get("message") or line)
    except json.JSONDecodeError:
        pass
    formatted = format_message(msg, ts)
    if formatted:
        print(formatted, flush=True)


for raw in sys.stdin:
    handle_line(raw)
PY
}

if [[ "$FOLLOW" -eq 1 ]]; then
  echo "Live Abuu trace from $API_LOG (Ctrl+C to stop)"
  echo "Send a WhatsApp message to YallaSay while this runs."
  echo "---"
  tail -f "$API_LOG" | format_abuu_trace
else
  echo "Last $HISTORY Abuu trace lines from $API_LOG"
  echo "---"
  grep -E 'abuu_live_trace|abuu_wa_trace|abuu_smart_pipeline|abuu_waiter_trace|abuu_wa_inbound_handler_failed' "$API_LOG" 2>/dev/null | tail -n "$HISTORY" | format_abuu_trace || true
fi
