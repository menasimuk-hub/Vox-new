"""Deep VPS ATS diagnostic."""
from __future__ import annotations

import sys

import paramiko

HOST = "161.97.159.253"
USER = "root"
PASSWORD = sys.argv[1] if len(sys.argv) > 1 else ""


def run(client: paramiko.SSHClient, cmd: str) -> None:
    print(f"\n=== {cmd[:100]} ===")
    _, stdout, stderr = client.exec_command(cmd, timeout=120, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if out.strip():
        print(out.rstrip())
    if err.strip():
        print("STDERR:", err.rstrip())


def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30, look_for_keys=False, allow_agent=False)

    run(
        client,
        r"""grep -i 'ats/run\|interview_ats\|ats_score_failed\|402\|Payment' /tmp/voxbulk-api.log | tail -30""",
    )
    run(
        client,
        r"""cd /www/voxbulk/voxbulk-api && source .venv/bin/activate && python <<'PY'
import json
from sqlalchemy import select
from app.core.database import get_sessionmaker
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.providers.provider_settings_service import ProviderSettingsService

db = get_sessionmaker()()
view = ProviderSettingsService.get_platform_config_admin_view(db, provider="deepseek")
print("DeepSeek provider view keys:", {k: ("***" if "key" in k.lower() or "secret" in k.lower() else v) for k, v in (view or {}).items() if k in ("enabled", "configured", "has_api_key", "status", "provider", "model")}})

order_id = "ce29dd06-0175-4264-952b-89646b346594"
order = db.get(ServiceOrder, order_id)
if not order:
    print("Order not found")
else:
    cfg = json.loads(order.config_json or "{}")
    print("Order:", order.title, "status=", order.status)
    print("  role:", (cfg.get("role") or cfg.get("position") or "")[:80])
    print("  criteria len:", len(str(cfg.get("criteria") or cfg.get("screening_criteria") or "")))
    print("  approved_script len:", len(str(cfg.get("approved_script") or "")))
    print("  ats_manual_run_at:", cfg.get("ats_manual_run_at"))
    print("  ats_skipped:", cfg.get("ats_skipped"))
    recips = list(db.execute(select(ServiceOrderRecipient).where(ServiceOrderRecipient.order_id == order_id)).scalars())
    print(f"  recipients={len(recips)}")
    for r in recips[:12]:
        parsed = {}
        try:
            parsed = json.loads(r.result_json or "{}")
        except Exception:
            pass
        cv_len = len(r.cv_text or "")
        print(f"    {r.name[:20]:20} ats={r.ats_status} score={r.ats_score} cv_chars={cv_len} deferred={parsed.get('email_ats_pending_at')}")
PY""",
    )
    run(client, "curl -s -H 'Host: api.voxbulk.com' http://127.0.0.1:8000/health")
    run(client, "cd /www/voxbulk && ./vox.sh status 2>&1 | head -25")

    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
