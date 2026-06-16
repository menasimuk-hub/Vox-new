#!/usr/bin/env python3
"""
Simulate inbound Yallasay WhatsApp and print route + log + DB trace.

Run on VPS:
  cd /www/voxbulk/voxbulk-api
  .venv/bin/python3 scripts/yallasay_e2e_trace.py

Or via wrapper:
  bash scripts/vps-yallasay-e2e-trace.sh
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

LOG_MARKERS = (
    "yallasay_inbound_to_inferred",
    "yallasay_inbound_route",
    "yallasay_inbound_handler_failed",
    "abuu_wa_trace",
    "abuu_wa_reply_failed",
    "telnyx_message_http_error",
    "abuu_agent_deepseek",
)

DEFAULT_FROM = "+447700900123"
DEFAULT_TEXT = "Yallasay"


def _line(label: str, detail: str = "") -> None:
    text = f"{label:<10} {detail}".rstrip()
    print(text, flush=True)


def _fetch_health(base_url: str) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/health/abuu-runtime"
    try:
        with urlopen(url, timeout=8) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"status": "error", "detail": str(exc)}


def _log_line_count(log_path: Path) -> int:
    if not log_path.is_file():
        return 0
    try:
        with log_path.open("rb") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0


def _read_new_log_lines(log_path: Path, start_line: int) -> list[str]:
    if not log_path.is_file():
        return []
    try:
        with log_path.open("r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return []
    return [ln.rstrip("\n") for ln in lines[start_line:] if ln.strip()]


def _extract_log_message(line: str) -> tuple[str, str]:
    ts = ""
    msg = line
    try:
        obj = json.loads(line)
        ts = str(obj.get("timestamp") or "")
        msg = str(obj.get("message") or line)
    except json.JSONDecodeError:
        pass
    return ts, msg


def _short_ts(raw: str) -> str:
    if raw and "T" in raw and len(raw) >= 19:
        return raw[11:19]
    return raw[:8] if raw else "??:??:??"


def _format_trace_line(ts: str, msg: str) -> str | None:
    if not any(marker in msg for marker in LOG_MARKERS):
        return None
    stamp = f"[{_short_ts(ts)}]"
    if "yallasay_inbound_to_inferred" in msg:
        return f"{stamp} INFER  {msg.split('yallasay_inbound_to_inferred', 1)[-1].strip()}"
    if "yallasay_inbound_route" in msg:
        return f"{stamp} ROUTE  {msg.split('yallasay_inbound_route', 1)[-1].strip()}"
    if "abuu_wa_trace IN" in msg:
        return f"{stamp} WA_IN  {msg.split('abuu_wa_trace IN', 1)[-1].strip()}"
    if "abuu_wa_trace OUT" in msg:
        return f"{stamp} WA_OUT {msg.split('abuu_wa_trace OUT', 1)[-1].strip()}"
    if "telnyx_message_http_error" in msg:
        return f"{stamp} TELNYX {msg.split('telnyx_message_http_error', 1)[-1].strip()}"
    if "abuu_wa_reply_failed" in msg or "yallasay_inbound_handler_failed" in msg:
        return f"{stamp} ERROR  {msg}"
    return f"{stamp} LOG    {msg}"


def _parse_out_ok(log_lines: list[str]) -> bool | None:
    for line in reversed(log_lines):
        _, msg = _extract_log_message(line)
        if "abuu_wa_trace OUT" not in msg:
            continue
        m = re.search(r"ok=(True|False)", msg)
        if m:
            return m.group(1) == "True"
    return None


def _resolve_org_id(db) -> str:
    from sqlalchemy import select

    from app.models.organisation import Organisation
    from app.services.provider_settings import ProviderSettingsService

    cfg, _enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
    config = cfg if isinstance(cfg, dict) else {}
    org_id = str(config.get("messaging_org_id") or config.get("default_messaging_org_id") or "").strip()
    if org_id:
        return org_id
    fallback = db.execute(select(Organisation.id).order_by(Organisation.created_at.asc()).limit(1)).scalar_one_or_none()
    return str(fallback or "")


def _build_payload(
    *,
    message_id: str,
    from_phone: str,
    to_phone: str | None,
    text: str,
    messaging_profile_id: str | None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": message_id,
        "direction": "inbound",
        "type": "WHATSAPP",
        "from": {"phone_number": from_phone},
        "body": {"type": "text", "text": {"body": text}},
        "status": "received",
    }
    if to_phone:
        record["to"] = [{"phone_number": to_phone}]
    if messaging_profile_id:
        record["messaging_profile_id"] = messaging_profile_id
    return {
        "data": {
            "event_type": "message.received",
            "payload": record,
        }
    }


def run_preflight(db, *, api_base: str) -> dict[str, Any]:
    from app.abuu.agent.agent import _deepseek_platform_ready
    from app.services.yallasay_telnyx_line import get_yallasay_line_config, get_yallasay_whatsapp_e164

    health = _fetch_health(api_base)
    yalla = get_yallasay_whatsapp_e164(db)
    line = get_yallasay_line_config(db)
    profile = str(line.get("whatsapp_messaging_profile_id") or "").strip()
    deepseek = _deepseek_platform_ready(db)

    info = {
        "health": health,
        "yallasay": yalla,
        "profile": profile or None,
        "deepseek": deepseek,
        "agent_mode": bool(health.get("agent_mode")),
        "abuu_enabled": bool(health.get("abuu_enabled")),
    }

    git_sha = str(health.get("git_sha") or "")
    _line("PREFLIGHT", f"yallasay={yalla or '(NOT SET)'} profile={profile or '(NOT SET)'} agent={info['agent_mode']} deepseek={deepseek} git_sha={git_sha or '?'}")

    blockers: list[str] = []
    if not yalla:
        blockers.append("Yallasay WhatsApp number not configured (sms_from_2 / whatsapp_from_2)")
    if health.get("status") != "ok":
        blockers.append(f"API health check failed: {health.get('detail') or health}")
    if not info["abuu_enabled"]:
        blockers.append("ABUU_ENABLED is false in running API")
    if not profile:
        _line("WARN", "yallasay_wa_profile_id missing — inbound routing may work but OUT may fail (Apply Telnyx setup)")
    if not deepseek:
        _line("WARN", "DeepSeek not configured — agent reply may fail")

    info["blockers"] = blockers
    return info


def query_whatsapp_logs(db, *, message_id: str, from_phone: str, since: datetime) -> dict[str, Any]:
    from sqlalchemy import select

    from app.models.whatsapp_log import WhatsAppLog

    inbound = db.execute(
        select(WhatsAppLog).where(WhatsAppLog.external_message_id == message_id)
    ).scalar_one_or_none()

    outbound = db.execute(
        select(WhatsAppLog)
        .where(
            WhatsAppLog.direction == "outbound",
            WhatsAppLog.to_number == from_phone,
            WhatsAppLog.created_at >= since,
        )
        .order_by(WhatsAppLog.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    return {
        "inbound": inbound,
        "outbound": outbound,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulate Yallasay WhatsApp inbound and print E2E trace")
    parser.add_argument("--text", default=DEFAULT_TEXT, help="Inbound message text")
    parser.add_argument("--from", dest="from_phone", default=DEFAULT_FROM, help="Simulated customer E.164")
    parser.add_argument("--omit-to", action="store_true", help="Omit Telnyx `to` field; use messaging_profile_id")
    parser.add_argument("--message-id", default="", help="Override external message id")
    parser.add_argument("--preflight", action="store_true", help="Config checks only; do not simulate")
    parser.add_argument("--api-base", default=os.environ.get("VOXBULK_API_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--log", default=os.environ.get("VOX_API_LOG", "/tmp/voxbulk-api.log"))
    args = parser.parse_args()

    log_path = Path(args.log)
    api_base = str(args.api_base).strip()

    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        preflight = run_preflight(db, api_base=api_base)
        if preflight["blockers"]:
            for item in preflight["blockers"]:
                _line("FAIL", item)
            return 1

        if args.preflight:
            _line("OK", "preflight passed")
            return 0

        from app.services.yallasay_telnyx_line import get_yallasay_line_config, get_yallasay_whatsapp_e164
        from app.services.telnyx_inbound_messaging_service import TelnyxInboundMessagingService

        yalla_to = get_yallasay_whatsapp_e164(db)
        line = get_yallasay_line_config(db)
        profile_id = str(line.get("whatsapp_messaging_profile_id") or "").strip() or None
        org_id = _resolve_org_id(db)
        if not org_id:
            _line("FAIL", "No organisation in database for webhook org_id")
            return 1

        message_id = str(args.message_id or "").strip() or f"vps-probe-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        from_phone = str(args.from_phone).strip()
        text = str(args.text).strip() or DEFAULT_TEXT

        payload = _build_payload(
            message_id=message_id,
            from_phone=from_phone,
            to_phone=None if args.omit_to else yalla_to,
            text=text,
            messaging_profile_id=profile_id if args.omit_to else None,
        )

        mode = "omit-to" if args.omit_to else "with-to"
        _line("SIMULATE", f"text={text!r} from={from_phone} to={yalla_to if not args.omit_to else '(omitted)'} mode={mode} message_id={message_id} org_id={org_id}")

        log_start = _log_line_count(log_path)
        started_at = datetime.now(timezone.utc).replace(tzinfo=None)

        result = TelnyxInboundMessagingService.handle_webhook(db, payload, header_org_id=org_id)

        time.sleep(0.5)

        abuu = result.get("abuu") if isinstance(result.get("abuu"), dict) else {}
        _line(
            "ROUTE",
            f"yallasay_line={result.get('yallasay_line')} abuu_handled={abuu.get('handled')} reason={abuu.get('reason')} log_id={result.get('log_id')}",
        )
        print("RESULT " + json.dumps(result, default=str)[:2000], flush=True)

        new_lines = _read_new_log_lines(log_path, log_start)
        _line("LOG", f"--- {len(new_lines)} new log line(s) from {log_path} ---")
        for raw in new_lines:
            ts, msg = _extract_log_message(raw)
            formatted = _format_trace_line(ts, msg)
            if formatted:
                print(formatted, flush=True)

        logs = query_whatsapp_logs(db, message_id=message_id, from_phone=from_phone, since=started_at - timedelta(seconds=5))
        inbound = logs["inbound"]
        outbound = logs["outbound"]
        if inbound:
            _line("DB", f"inbound id={inbound.id} to={inbound.to_number or '—'} from={inbound.from_number or '—'} status={inbound.status}")
        else:
            _line("DB", "inbound row not found")
        if outbound:
            _line("DB", f"outbound id={outbound.id} to={outbound.to_number or '—'} status={outbound.status} external_id={outbound.external_message_id or '—'}")
        else:
            _line("DB", "no outbound row yet (Telnyx send may have failed or not logged)")

        if not result.get("yallasay_line"):
            _line("EXIT", "2 — not routed to Yallasay line")
            return 2

        if not abuu.get("handled"):
            _line("EXIT", "2 — Yallasay routed but Abuu did not handle")
            return 2

        out_ok = _parse_out_ok(new_lines)
        if out_ok is False:
            _line("EXIT", "3 — Abuu handled but outbound failed (check profile / Telnyx)")
            return 3
        if out_ok is True:
            _line("EXIT", "0 — route + Abuu + outbound OK")
            return 0

        if outbound and str(outbound.status or "").lower() not in {"failed", "error"}:
            _line("EXIT", "0 — route + Abuu OK (outbound queued)")
            return 0

        _line("EXIT", "3 — Abuu handled but no successful outbound trace")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
