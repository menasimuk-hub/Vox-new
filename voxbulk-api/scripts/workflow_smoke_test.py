#!/usr/bin/env python3
"""
VoxBulk workflow smoke — API routes, email readiness, UI pages, and optional live auth.

Run on VPS after deploy:
  cd /www/voxbulk/voxbulk-api
  .venv/bin/python3 scripts/workflow_smoke_test.py

Optional credentials (dashboard user):
  export VOXBULK_API_BASE_URL="https://api.voxbulk.com"
  export VOXBULK_EMAIL="you@company.com"
  export VOXBULK_PASSWORD="your-password"
  .venv/bin/python3 scripts/workflow_smoke_test.py --check-auth

Optional live registration + welcome email attempt:
  .venv/bin/python3 scripts/workflow_smoke_test.py --test-register
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parent

PASS = 0
FAIL = 0
WARN = 0


def pass_(msg: str) -> None:
    global PASS
    PASS += 1
    print(f"PASS  {msg}")


def fail(msg: str) -> None:
    global FAIL
    FAIL += 1
    print(f"FAIL  {msg}")


def warn(msg: str) -> None:
    global WARN
    WARN += 1
    print(f"WARN  {msg}")


def section(title: str) -> None:
    print(f"\n--- {title} ---")


@dataclass
class HttpResult:
    ok: bool
    status: int | None = None
    body: str = ""
    error: str = ""


def http_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout: int = 20,
) -> HttpResult:
    data = None
    hdrs = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    req = Request(url, data=data, headers=hdrs, method=method.upper())
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return HttpResult(ok=200 <= resp.status < 400, status=resp.status, body=raw)
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return HttpResult(ok=False, status=exc.code, body=raw, error=str(exc))
    except URLError as exc:
        return HttpResult(ok=False, error=str(exc.reason or exc))


def load_settings():
    if str(API_ROOT) not in sys.path:
        sys.path.insert(0, str(API_ROOT))
    from app.core.config import get_settings

    return get_settings()


def api_base_url() -> str:
    env = os.environ.get("VOXBULK_API_BASE_URL", "").strip().rstrip("/")
    if env:
        return env
    settings = load_settings()
    return "http://127.0.0.1:8000"


def api_headers() -> dict[str, str]:
    return {"Host": "api.voxbulk.com", "Accept": "application/json"}


def check_git() -> None:
    section("git")
    try:
        log = subprocess.check_output(["git", "log", "-1", "--oneline"], cwd=REPO_ROOT, text=True).strip()
        pass_(f"git revision: {log}")
    except Exception as exc:
        warn(f"git log unavailable: {exc}")


def check_api_health(base: str) -> None:
    section("API health")
    res = http_request("GET", f"{base}/health/build", headers=api_headers())
    if not res.ok:
        res = http_request("GET", f"{base}/health/build")
    if res.ok:
        pass_("GET /health/build reachable")
        try:
            data = json.loads(res.body)
            if data.get("deploy_ok"):
                pass_("deploy_ok true")
            else:
                warn("deploy_ok not true — restart API after deploy")
        except json.JSONDecodeError:
            warn("/health/build returned non-JSON")
    else:
        fail(f"/health/build not reachable ({res.status or res.error})")


def check_openapi_routes(base: str) -> None:
    section("API route registry")
    required = [
        ("post", "/auth/register"),
        ("post", "/auth/token"),
        ("post", "/auth/forgot-password"),
        ("post", "/auth/accept-invite"),
        ("get", "/organisations/me"),
        ("get", "/billing/wallet"),
        ("get", "/health/build"),
    ]
    res = http_request("GET", f"{base}/openapi.json", headers=api_headers())
    if not res.ok:
        fail(f"GET /openapi.json failed ({res.status or res.error})")
        return
    try:
        spec = json.loads(res.body)
    except json.JSONDecodeError:
        fail("openapi.json is not valid JSON")
        return
    paths = spec.get("paths") or {}
    for method, path in required:
        node = paths.get(path) or {}
        if method in node:
            pass_(f"{method.upper()} {path} registered")
        else:
            fail(f"{method.upper()} {path} missing from OpenAPI")


def check_auth_public(base: str) -> None:
    section("Auth public endpoints")
    fp = http_request(
        "POST",
        f"{base}/auth/forgot-password",
        headers=api_headers(),
        body={"email": "workflow-smoke@example.com"},
    )
    if fp.ok:
        pass_("POST /auth/forgot-password returns success envelope")
    else:
        fail(f"POST /auth/forgot-password failed ({fp.status})")

    bad = http_request(
        "POST",
        f"{base}/auth/token",
        headers=api_headers(),
        body={"username": "missing-user@example.com", "password": "wrong-password-xyz"},
    )
    if bad.status in (400, 401, 422):
        pass_("POST /auth/token rejects bad credentials")
    else:
        warn(f"POST /auth/token unexpected status for bad creds: {bad.status}")


def check_email_readiness() -> None:
    section("Welcome email readiness")
    if str(API_ROOT) not in sys.path:
        sys.path.insert(0, str(API_ROOT))
    from app.core.database import get_sessionmaker
    from app.services.smtp_settings_service import SmtpSettingsService
    from app.services.transactional_email_service import TransactionalEmailService

    with get_sessionmaker()() as db:
        smtp = SmtpSettingsService.get_row(db)
        configured, missing = SmtpSettingsService.compute_status(smtp)
        if configured:
            pass_("SMTP row complete")
        else:
            fail(f"SMTP incomplete: {', '.join(missing)}")
        if smtp.is_enabled:
            pass_("SMTP enabled")
        else:
            fail("SMTP disabled — welcome emails will not send")

        for key in ("new_user", "forgot_password"):
            subject, body, enabled = TransactionalEmailService.load_template_fields(db, template_key=key)
            if enabled:
                pass_(f"email template '{key}' enabled")
            else:
                fail(f"email template '{key}' disabled")
            if str(subject).strip() and str(body).strip():
                pass_(f"email template '{key}' has subject + body")
            else:
                fail(f"email template '{key}' empty subject/body")
            if key == "new_user":
                if "dashboard" in str(body).lower() or "{{dashboard_url}}" in str(body):
                    pass_("new_user template references dashboard link")
                else:
                    warn("new_user template missing dashboard_url placeholder")

        settings = load_settings()
        if str(settings.env).lower() in {"production", "prod"}:
            for key in ("new_user", "forgot_password", "interview_booking_invite"):
                try:
                    _, body, _ = TransactionalEmailService.load_template_fields(db, template_key=key)
                except Exception:
                    continue
                if "localhost" in str(body).lower() or "127.0.0.1" in str(body):
                    fail(f"template '{key}' contains localhost URL in production")


def check_ui_pages() -> None:
    section("UI pages (HTTP)")
    settings = load_settings()
    pages = [
        ("public signin", f"{settings.public_app_origin.rstrip('/')}/signin"),
        ("public onboarding", f"{settings.public_app_origin.rstrip('/')}/onboarding"),
        ("dashboard home", f"{settings.dashboard_app_origin.rstrip('/')}/"),
        ("dashboard billing", f"{settings.dashboard_app_origin.rstrip('/')}/account/billing"),
        ("dashboard interviews", f"{settings.dashboard_app_origin.rstrip('/')}/interviews"),
        ("dashboard surveys", f"{settings.dashboard_app_origin.rstrip('/')}/surveys"),
        ("dashboard feedback", f"{settings.dashboard_app_origin.rstrip('/')}/feedback"),
        ("admin home", os.environ.get("VOX_ADMIN_ORIGIN", "https://admin.voxbulk.com").rstrip("/") + "/"),
        ("admin organisations", os.environ.get("VOX_ADMIN_ORIGIN", "https://admin.voxbulk.com").rstrip("/") + "/organisations"),
        ("admin billing", os.environ.get("VOX_ADMIN_ORIGIN", "https://admin.voxbulk.com").rstrip("/") + "/billing/subscriptions"),
    ]
    wwwroot_dash = Path(os.environ.get("VOX_DASH_DIST", "/www/wwwroot/dashboard.voxbulk.com"))
    wwwroot_admin = Path(os.environ.get("VOX_ADMIN_DIST", "/www/wwwroot/admin.voxbulk.com"))
    if wwwroot_dash.joinpath("index.html").is_file():
        pass_(f"dashboard wwwroot index present: {wwwroot_dash}")
    else:
        warn(f"dashboard wwwroot missing index.html ({wwwroot_dash})")
    if wwwroot_admin.joinpath("index.html").is_file():
        pass_(f"admin wwwroot index present: {wwwroot_admin}")
    else:
        warn(f"admin wwwroot missing index.html ({wwwroot_admin})")

    for label, url in pages:
        res = http_request("GET", url, headers={"Accept": "text/html"})
        if res.ok and ("<html" in res.body.lower() or "<!doctype" in res.body.lower()):
            pass_(f"{label} loads HTML ({url})")
        elif res.ok:
            warn(f"{label} returned {res.status} but no HTML shell ({url})")
        else:
            fail(f"{label} unreachable ({url}) — {res.status or res.error}")


def check_dashboard_route_files() -> None:
    section("Dashboard route files on disk")
    routes_dir = REPO_ROOT / "dashboard.voxbulk.com/dashboard-web/src/routes"
    expected = [
        "_app.account.billing.tsx",
        "_app.account.feedback.packages.tsx",
        "_app.interviews.index.tsx",
        "_app.surveys.index.tsx",
        "_app.feedback.index.tsx",
        "book.$token.tsx",
    ]
    if not routes_dir.is_dir():
        warn(f"dashboard routes dir missing: {routes_dir}")
        return
    for name in expected:
        if (routes_dir / name).is_file():
            pass_(f"route file present: {name}")
        else:
            fail(f"route file missing: {name}")


def check_auth_flow(base: str) -> None:
    section("Authenticated API smoke")
    email = os.environ.get("VOXBULK_EMAIL", "").strip()
    password = os.environ.get("VOXBULK_PASSWORD", "").strip()
    if not email or not password:
        warn("VOXBULK_EMAIL/PASSWORD not set — skipping authenticated checks")
        return

    tok = http_request(
        "POST",
        f"{base}/auth/token",
        headers=api_headers(),
        body={"username": email, "password": password},
    )
    if not tok.ok:
        fail(f"auth/token failed for {email} ({tok.status})")
        return
    try:
        token_data = json.loads(tok.body)
    except json.JSONDecodeError:
        fail("auth/token returned non-JSON")
        return
    access = str(token_data.get("access_token") or "").strip()
    if not access:
        fail("auth/token missing access_token")
        return
    pass_("dashboard login token issued")

    auth_hdrs = {**api_headers(), "Authorization": f"Bearer {access}"}
    for label, path in (
        ("organisations/me", "/organisations/me"),
        ("billing wallet", "/billing/wallet"),
        ("service orders", "/service-orders"),
    ):
        res = http_request("GET", f"{base}{path}", headers=auth_hdrs)
        if res.ok:
            pass_(f"GET {path} OK for {email}")
        else:
            fail(f"GET {path} failed ({res.status}) for {email}")


def check_register_welcome(base: str) -> None:
    section("Live register (welcome email uses SMTP above)")
    token = uuid.uuid4().hex[:10]
    email = f"workflow-smoke-{token}@anonymized.voxbulk.invalid"
    org_name = f"Workflow Smoke {token}"
    password = f"Smoke{token}!"

    res = http_request(
        "POST",
        f"{base}/auth/register",
        headers=api_headers(),
        body={
            "email": email,
            "password": password,
            "organisation_name": org_name,
        },
    )
    if not res.ok:
        fail(f"POST /auth/register failed ({res.status}): {res.body[:200]}")
        return
    try:
        data = json.loads(res.body)
    except json.JSONDecodeError:
        fail("POST /auth/register returned non-JSON")
        return
    if str(data.get("access_token") or "").strip():
        pass_(f"POST /auth/register created test user {email}")
        warn("dispose test user with purge_user_billing_and_accounts.py if needed")
    else:
        fail("POST /auth/register missing access_token")


def main() -> int:
    global PASS, FAIL, WARN
    parser = argparse.ArgumentParser(description="VoxBulk workflow smoke test")
    parser.add_argument("--check-auth", action="store_true", help="Run authenticated API checks (needs env creds)")
    parser.add_argument("--test-register", action="store_true", help="Create disposable user and verify welcome hook")
    args = parser.parse_args()

    base = api_base_url()
    print("=== VoxBulk workflow smoke ===")
    print(f"api: {base}")
    print(f"time: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")

    check_git()
    check_api_health(base)
    check_openapi_routes(base)
    check_auth_public(base)
    check_email_readiness()
    check_ui_pages()
    check_dashboard_route_files()
    if args.check_auth:
        check_auth_flow(base)
    if args.test_register:
        check_register_welcome(base)

    print(f"\n=== SUMMARY ===")
    print(f"PASS={PASS} FAIL={FAIL} WARN={WARN}")
    if FAIL:
        print("OVERALL: FAIL")
        return 1
    if WARN:
        print("OVERALL: PASS (review WARN lines)")
    else:
        print("OVERALL: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
