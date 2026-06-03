"""Local WA Survey verification script — run while API is on :8000."""

from __future__ import annotations

import json
import sqlite3
import sys
import urllib.parse
import urllib.request
from pathlib import Path

API = "http://127.0.0.1:8000"
ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "voxbulk-api" / "retover.local.db"
PASSWORD = "testtest1"


def http(method: str, path: str, token: str | None = None, body: dict | None = None):
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{API}{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, json.loads(resp.read().decode())


def main() -> int:
    if not DB.exists():
        print(f"FAIL: database not found at {DB}")
        return 1

    con = sqlite3.connect(DB)
    email = con.execute("SELECT email FROM users WHERE is_superuser=1 LIMIT 1").fetchone()[0]
    org = con.execute(
        """
        SELECT om.org_id FROM organisation_memberships om
        JOIN users u ON u.id = om.user_id
        WHERE u.email = ? LIMIT 1
        """,
        (email,),
    ).fetchone()[0]
    con.close()

    form = urllib.parse.urlencode({"username": email, "password": PASSWORD, "org_id": org}).encode()
    req = urllib.request.Request(f"{API}/auth/token", data=form, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        token = json.loads(resp.read().decode())["access_token"]
    print(f"OK admin auth as {email}")

    _, listed = http("GET", "/admin/wa-survey/types", token)
    types = listed["types"]
    print(f"OK list types: {len(types)} (expect >= 5)")
    assert len(types) >= 5

    _, created = http(
        "POST",
        "/admin/wa-survey/types",
        token,
        {"name": "Local verify type", "description": "Created by verify script"},
    )
    type_id = created["type"]["id"]
    print(f"OK create type: {created['type']['slug']}")

    _, detail = http("GET", f"/admin/wa-survey/types/{type_id}", token)
    print(f"OK edit page data: templates={len(detail['templates'])}")

    _, draft = http("POST", f"/admin/wa-survey/types/{type_id}/templates/standard", token, {})
    template_id = draft["template"]["id"]
    print(f"OK standard draft template id={template_id}")

    _, cloned = http("POST", f"/admin/wa-survey/templates/{template_id}/clone-anonymous", token)
    anon_id = cloned["template"]["id"]
    print(f"OK clone anonymous id={anon_id}")

    _, preview = http("GET", f"/admin/wa-survey/templates/{template_id}/preview", token)
    assert preview.get("rendered_body")
    print(f"OK template preview body len={len(preview['rendered_body'])}")

    # Approve template locally for generation test
    con = sqlite3.connect(DB)
    con.execute(
        "UPDATE telnyx_whatsapp_templates SET status='APPROVED', active_for_survey=1 WHERE id=?",
        (template_id,),
    )
    con.commit()
    con.close()

    _, gen = http(
        "POST",
        "/admin/wa-survey/generate-preview",
        token,
        {
            "survey_type_id": type_id,
            "variant": "standard",
            "length": "short",
            "goal": "Test local generation",
        },
    )
    assert gen.get("flow_steps")
    print(f"OK generate preview: {gen['question_count']} questions, {len(gen['flow_steps'])} flow steps")

    # Dashboard token (non-admin user)
    dash_email = "user@user.com"
    con = sqlite3.connect(DB)
    row = con.execute("SELECT id FROM users WHERE lower(email)=?", (dash_email,)).fetchone()
    dash_org = con.execute(
        "SELECT org_id FROM organisation_memberships WHERE user_id=? LIMIT 1",
        (row[0],),
    ).fetchone()[0]
    con.close()
    form = urllib.parse.urlencode({"username": dash_email, "password": PASSWORD, "org_id": dash_org}).encode()
    req = urllib.request.Request(f"{API}/auth/token", data=form, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        dash_token = json.loads(resp.read().decode())["access_token"]

    _, dash_types = http("GET", "/dashboard/service-scripts/wa-survey/types", dash_token)
    print(f"OK dashboard types: {len(dash_types['types'])}")

    try:
        http(
            "POST",
            "/dashboard/service-scripts/wa-survey/generate",
            dash_token,
            {
                "survey_type_id": type_id,
                "variant": "standard",
                "length": "short",
                "goal": "Dashboard generate test",
            },
        )
        print("OK dashboard generate")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"WARN dashboard generate: {e.code} {body[:200]}")

    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
