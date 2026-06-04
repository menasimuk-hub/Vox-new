"""Deploy latest to VPS and trigger deferred ATS retry."""
from __future__ import annotations

import sys

import paramiko

HOST = "161.97.159.253"
USER = "root"
PASSWORD = sys.argv[1] if len(sys.argv) > 1 else ""


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 900) -> int:
    print(f"\n>>> {cmd[:100]}")
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if out.strip():
        print(out.rstrip())
    if err.strip():
        print(err.rstrip())
    return stdout.channel.recv_exit_status()


def main() -> int:
    if not PASSWORD:
        return 2
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30, look_for_keys=False, allow_agent=False)

    code = run(client, "cd /www/voxbulk && git fetch origin main && git pull --ff-only origin main")
    if code != 0:
        print("git pull failed", file=sys.stderr)
        client.close()
        return code

    code = run(client, "cd /www/voxbulk && chmod +x deploy-vps.sh vox.sh && ./deploy-vps.sh", timeout=900)
    if code != 0:
        print("deploy failed", file=sys.stderr)

    run(
        client,
        r"""cd /www/voxbulk/voxbulk-api && source .venv/bin/activate && python <<'PY'
from app.core.database import get_sessionmaker
from app.services.interview_email_ats_service import retry_deferred_email_ats
from app.services.interview_ats_service import process_pending_ats_scans

db = get_sessionmaker()()
deferred = retry_deferred_email_ats(db, limit=30)
pending = process_pending_ats_scans(db, limit=8)
print(f"retry_deferred={deferred} process_pending={pending}")
PY""",
    )
    run(client, "cd /www/voxbulk && ./vox.sh status | head -12")
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
