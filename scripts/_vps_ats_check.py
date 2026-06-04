"""Check VPS ATS status — run locally, SSH to server."""
from __future__ import annotations

import sys

import paramiko

HOST = "161.97.159.253"
USER = "root"
PASSWORD = sys.argv[1] if len(sys.argv) > 1 else ""


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 120) -> str:
    print(f"\n=== {cmd} ===")
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if out.strip():
        print(out.rstrip())
    if err.strip():
        print("STDERR:", err.rstrip())
    return out


def main() -> int:
    if not PASSWORD:
        print("Usage: python _vps_ats_check.py <password>", file=sys.stderr)
        return 2

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30, look_for_keys=False, allow_agent=False)

    run(client, "cd /www/voxbulk && git log -1 --oneline && git rev-parse HEAD")
    run(client, "curl -s -o /dev/null -w 'API health: %{http_code}\\n' http://127.0.0.1:8000/health")
    run(client, "grep -E 'DEEPSEEK|deepseek|OPENAI_API' /www/voxbulk/voxbulk-api/.env 2>/dev/null | sed 's/=.*/=***/' || echo 'no .env grep'")
    run(
        client,
        "tail -100 /tmp/voxbulk-api.log 2>/dev/null | grep -i ats || tail -30 /tmp/voxbulk-api.log 2>/dev/null || echo 'no api log'",
    )
    run(
        client,
        r"""cd /www/voxbulk/voxbulk-api && source .venv/bin/activate && python <<'PY'
from sqlalchemy import select, func
from app.core.database import get_sessionmaker
from app.models.service_order import ServiceOrder, ServiceOrderRecipient

db = get_sessionmaker()()
pending = db.scalar(
    select(func.count()).select_from(ServiceOrderRecipient).where(
        ServiceOrderRecipient.ats_status.in_(["pending", "analyzing"])
    )
)
failed = db.scalar(
    select(func.count()).select_from(ServiceOrderRecipient).where(
        ServiceOrderRecipient.ats_status == "failed"
    )
)
complete = db.scalar(
    select(func.count()).select_from(ServiceOrderRecipient).where(
        ServiceOrderRecipient.ats_status == "complete"
    )
)
print(f"ATS rows: pending/analyzing={pending} complete={complete} failed={failed}")
rows = list(
    db.execute(
        select(ServiceOrderRecipient)
        .where(ServiceOrderRecipient.ats_status.in_(["pending", "analyzing", "failed"]))
        .order_by(ServiceOrderRecipient.updated_at.desc())
        .limit(5)
    ).scalars()
)
for r in rows:
    order = db.get(ServiceOrder, r.order_id)
    print(f"  {r.id[:8]} status={r.ats_status} score={r.ats_score} err={r.ats_error!r} order={order.title if order else '?'}")
PY""",
    )
    run(client, "grep -n 'background_process_ats\\|process_inline' /www/voxbulk/voxbulk-api/app/services/interview_ats_billing_service.py 2>/dev/null | head -5 || echo 'OLD CODE - no background_process'")
    run(client, "grep -n 'background_process_ats' /www/voxbulk/voxbulk-api/app/routers/service_orders.py 2>/dev/null | head -3 || echo 'OLD ROUTER'")

    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
