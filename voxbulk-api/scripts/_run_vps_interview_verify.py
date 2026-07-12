"""Upload and run interview EN/AR verify on VPS."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import paramiko

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOST = "198.244.178.240"
USER = "qusay"
PASSWORD = "Just4test12!@"

REMOTE = Path(__file__).with_name("_remote_interview_workflow_verify.py")


def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30, look_for_keys=False, allow_agent=False)
    sftp = client.open_sftp()
    sftp.put(str(REMOTE), "/tmp/vox_interview_workflow_verify.py")
    sftp.close()
    cmd = (
        "cd /www/voxbulk/voxbulk-api; "
        "source .venv/bin/activate; "
        "PYTHONPATH=. python /tmp/vox_interview_workflow_verify.py"
    )
    _, stdout, stderr = client.exec_command(cmd, timeout=180, get_pty=True)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    print(out)
    if err.strip():
        print("STDERR:", err)
    client.close()
    try:
        data = json.loads(out[out.find("{") : out.rfind("}") + 1])
    except Exception:
        return 1
    print("OVERALL", "PASS" if data.get("ok") else "FAIL")
    for c in data.get("checks", []):
        print(("PASS" if c["pass"] else "FAIL"), "-", c["name"], c.get("detail") or "")
    return 0 if data.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
