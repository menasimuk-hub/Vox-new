#!/usr/bin/env bash
# Abuu voice/STT diagnostic — run ON THE VPS (read-only checks + optional STT test).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_DIR="$ROOT/voxbulk-api"
API_LOG="${VOX_API_LOG:-/tmp/voxbulk-api.log}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

section() { echo -e "\n${GREEN}=== $* ===${NC}"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*" >&2; }

section "Git"
if [[ -d "$ROOT/.git" ]]; then
  git -C "$ROOT" log -1 --oneline 2>/dev/null || warn "git log failed"
  git -C "$ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || true
else
  warn "Not a git repo: $ROOT"
fi

section "API process + log file"
pgrep -af "uvicorn main:app" || warn "no uvicorn process found"
if [[ -f "$API_LOG" ]]; then
  echo "Log: $API_LOG ($(wc -l < "$API_LOG") lines, $(stat -c '%y' "$API_LOG" 2>/dev/null || stat -f '%Sm' "$API_LOG" 2>/dev/null || echo '?'))"
else
  warn "Log missing: $API_LOG"
  PID="$(pgrep -f 'uvicorn main:app' | head -1 || true)"
  if [[ -n "$PID" ]]; then
    echo "Open files for uvicorn pid=$PID:"
    lsof -p "$PID" 2>/dev/null | grep -E '\.log|REG' | tail -10 || true
  fi
fi

section "Recent webhook traffic (last 5)"
if [[ -f "$API_LOG" ]]; then
  grep -E 'TELNYX_WEBHOOK_BUILD_MARKER|\[survey-wa-inbound\] raw_webhook' "$API_LOG" 2>/dev/null | tail -5 || warn "no webhook markers in log"
fi

section "Recent Abuu voice lines (last 15)"
if [[ -f "$API_LOG" ]]; then
  grep -E 'abuu_wa_trace|abuu_voice|voice_interpretation|abuu_stt_|transcription_failed' "$API_LOG" 2>/dev/null | tail -15 || warn "no abuu voice lines — deploy abuu_wa_trace commit and send a voice note"
fi

section "Env flags (from .env, no secrets)"
ENV_FILE="$API_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
  grep -E '^(ABUU_ENABLED|ABUU_VOICE_|ABUU_CONVERSATION|LOG_LEVEL|ABUU_VOICE_NOTE_DIR)=' "$ENV_FILE" 2>/dev/null || true
else
  warn "Missing $ENV_FILE"
fi

section "Python STT + config check"
[[ -d "$API_DIR/.venv" ]] || { warn "Missing $API_DIR/.venv"; exit 1; }
# shellcheck disable=SC1091
source "$API_DIR/.venv/bin/activate"
cd "$API_DIR"

python - <<'PY'
import json
from pathlib import Path

from app.core.config import get_settings
from app.core.database import get_sessionmaker
from app.services.providers.deepinfra_service import DeepInfraProviderService
from app.abuu.services.abuu_voice_service import AbuuVoiceService, _storage_root

s = get_settings()
print("ABUU_ENABLED", s.abuu_enabled)
print("VOICE_INTERPRETATION", s.abuu_voice_interpretation_enabled)
print("CONVERSATION_MODE", getattr(s, "abuu_conversation_mode", "?"))
print("LOG_LEVEL", s.log_level)
root = _storage_root()
print("VOICE_NOTE_DIR", root)
print("VOICE_NOTE_DIR_EXISTS", root.exists())

with get_sessionmaker()() as db:
    print("DEEPINFRA_CONFIGURED", DeepInfraProviderService.is_configured(db))

files = [
    p
    for p in root.glob("**/*")
    if p.is_file() and p.suffix.lower() in {".ogg", ".oga", ".wav", ".mp3", ".m4a"}
]
files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
print("AUDIO_FILE_COUNT", len(files))
audio = files[0] if files else None
print("LATEST_AUDIO", audio)
if audio:
    with get_sessionmaker()() as db:
        text = AbuuVoiceService._transcribe_file(db, audio, language="ar")
    print("STT_RESULT", repr(text))
else:
    print("STT_RESULT", "NO_AUDIO_FILES — send a WhatsApp voice note to Abuu first")

try:
    from app.core.abuu_database import get_abuu_sessionmaker
    from sqlalchemy import text as sql_text

    with get_abuu_sessionmaker()() as adb:
        rows = adb.execute(
            sql_text(
                """
                SELECT created_at, customer_phone, transcript_text, transcript_confidence, payload_json
                FROM abuu_inbound_messages
                WHERE message_type = 'voice'
                ORDER BY created_at DESC
                LIMIT 3
                """
            )
        ).fetchall()
    print("DB_VOICE_ROWS", len(rows))
    for row in rows:
        payload = json.loads(row.payload_json or "{}")
        vi = payload.get("voice_interpretation") or {}
        print("---")
        print("time:", row.created_at)
        print("phone:", row.customer_phone)
        print("transcript_text (STT raw):", row.transcript_text)
        print("confidence:", row.transcript_confidence)
        print("corrected:", vi.get("corrected_transcript"))
except Exception as exc:
    print("DB_VOICE_ROWS_ERROR", exc)
PY

section "Live tail command (run in another terminal while testing)"
echo "tail -f $API_LOG | grep --line-buffered abuu_wa_trace"
echo ""
echo "Or broader:"
echo "tail -f $API_LOG | grep --line-buffered -E 'abuu_wa_trace|TELNYX_WEBHOOK_BUILD_MARKER|abuu_stt_'"
