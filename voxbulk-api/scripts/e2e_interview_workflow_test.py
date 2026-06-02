#!/usr/bin/env python3
"""
End-to-end interview workflow functional test (run on VPS or locally).

Exercises real HTTP API routes for draft → candidates → payment → launch → booking →
results → stop. Post-call AI scoring has no public HTTP endpoint; use
--simulate-call (default) to complete the call via app services on this server.

IMPORTANT: This script uses HTTP API only — it never opens the app database.
Opening the DB from this script while the API runs (especially on SQLite) can
lock the database and block ALL emails until the script exits.

──────────────────────────────────────────────────────────────────────────────
SETUP (export before running)
──────────────────────────────────────────────────────────────────────────────

  export VOXBULK_API_BASE_URL="https://api.voxbulk.com"   # or http://127.0.0.1:8000
  export VOXBULK_EMAIL="you@company.com"
  export VOXBULK_PASSWORD="your-password"
  # Optional if user belongs to multiple orgs:
  export VOXBULK_ORG_ID="..."

  # Test candidate (must be on Telnyx allowlist for a REAL phone call):
  export VOXBULK_CANDIDATE_NAME="E2E Test Candidate"
  export VOXBULK_CANDIDATE_PHONE="+447700900123"
  export VOXBULK_CANDIDATE_EMAIL="e2e-candidate@example.com"

  # Admin creds for cash-payment approval (can match dashboard user if admin):
  export VOXBULK_ADMIN_EMAIL="$VOXBULK_EMAIL"
  export VOXBULK_ADMIN_PASSWORD="$VOXBULK_PASSWORD"

  # Path to voxbulk-api on VPS (for --simulate-call, default: parent of scripts/):
  export VOXBULK_API_ROOT="/www/voxbulk/voxbulk-api"

──────────────────────────────────────────────────────────────────────────────
RUN (VPS — use python3; `python` is often not installed on Ubuntu)
──────────────────────────────────────────────────────────────────────────────

  cd /www/voxbulk/voxbulk-api

  # Easiest — wrapper picks venv or python3:
  bash scripts/e2e_interview_workflow_test.sh

  # Or directly (activate venv first if you have one):
  source .venv/bin/activate 2>/dev/null || source venv/bin/activate 2>/dev/null || true
  python3 scripts/e2e_interview_workflow_test.py

  # Default: email-safe (WhatsApp invites only — does not hog SMTP while test runs)
  bash scripts/e2e_interview_workflow_test.sh

  # Also send interview emails during the test (invite + confirm + stop):
  python3 scripts/e2e_interview_workflow_test.py --send-test-emails --no-simulate-call

──────────────────────────────────────────────────────────────────────────────
MANUAL BOOKING (skip waiting — pick your own slot)
──────────────────────────────────────────────────────────────────────────────

  After launch, each recipient has a booking_token (recipients API or invite link).

  1) List available 10-minute slots:
     curl -s "https://api.voxbulk.com/public/interview-booking/TOKEN" | jq .available_slots

  2) Confirm a slot (must be one of available_slots):
     curl -s -X POST "https://api.voxbulk.com/public/interview-booking/TOKEN/confirm" \\
       -H "Content-Type: application/json" \\
       -d '{"slot_start_at":"2026-06-02T14:10:00Z"}'

  Or use the dashboard booking page: https://dashboard.voxbulk.com/book/TOKEN

  E2E script — book nearest slot (~1 min wait with 10m grid):
     python3 scripts/e2e_interview_workflow_test.py --slot-minutes-ahead 0

  E2E script — exact slot (no auto-pick):
     python3 scripts/e2e_interview_workflow_test.py --slot-start-at "2026-06-02T14:10:00Z"

  Skip auto-wait before dial (you already passed slot time):
     python3 scripts/e2e_interview_workflow_test.py --wait-for-slot-seconds 0
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, TextIO
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlencode
from urllib.request import Request, urlopen

# ── defaults ─────────────────────────────────────────────────────────────────

DEFAULT_SCRIPT = """QUESTIONS
1. Tell me about your most recent backend project.
2. How do you approach API design and versioning?
3. Describe a time you debugged a production incident.
"""

SIMULATED_TRANSCRIPT = """
Agent: Hello, thanks for joining this screening call.
Candidate: Hi, happy to speak with you about the role.
Agent: Tell me about your most recent backend project.
Candidate: I led a FastAPI and PostgreSQL migration that cut p95 latency by forty percent and improved deployment reliability.
Agent: How do you approach API design and versioning?
Candidate: We document contracts first, version URLs, and maintain backward compatibility for two releases.
Agent: Describe a time you debugged a production incident.
Candidate: We traced a connection-pool exhaustion issue using metrics and fixed it with tighter timeouts and pool sizing.
Agent: Thank you for your time today.
Candidate: Thank you, goodbye.
""".strip()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat() + "Z"


class _Tee(TextIO):
    """Write stdout/stderr to console and log file."""

    def __init__(self, stream: TextIO, log_path: Path) -> None:
        self._stream = stream
        self._log_path = log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = log_path.open("a", encoding="utf-8")
        self._file.write(f"\n\n{'=' * 72}\nE2E run started {_iso(_utc_now())}\n{'=' * 72}\n")
        self._file.flush()

    def write(self, s: str) -> int:
        self._stream.write(s)
        self._file.write(s)
        self._file.flush()
        return len(s)

    def flush(self) -> None:
        self._stream.flush()
        self._file.flush()

    def close(self) -> None:
        self._file.close()


def _token_from_recipient(recipient: dict[str, Any]) -> str:
    tok = str(recipient.get("booking_token") or "").strip()
    if tok:
        return tok
    url = str(recipient.get("booking_url") or "")
    match = re.search(r"/book/([^/?#]+)", url)
    if match:
        return unquote(match.group(1)).strip()
    return ""


def _token_from_activity(activity: dict[str, Any]) -> str:
    url = str(activity.get("booking_url") or "")
    match = re.search(r"/book/([^/?#]+)", url)
    if match:
        return unquote(match.group(1)).strip()
    return ""


def _write_report(
    path: Path,
    *,
    runner: "WorkflowRunner",
    order_id: str | None,
    recipient_id: str | None,
    booked_slot: str | None,
    launch: dict[str, Any] | None,
    detail: dict[str, Any] | None,
) -> None:
    failed = [r for r in runner.results if not r.ok]
    payload = {
        "finished_at": _iso(_utc_now()),
        "base_url": runner.base,
        "order_id": order_id,
        "recipient_id": recipient_id,
        "booked_slot": booked_slot,
        "launch_invites": launch.get("invites") if isinstance(launch, dict) else None,
        "final_score": (detail or {}).get("score") or ((detail or {}).get("analysis") or {}).get("score"),
        "passed": sum(1 for r in runner.results if r.ok),
        "total": len(runner.results),
        "failed_steps": [{"name": r.name, "reason": r.reason} for r in failed],
        "steps": [
            {
                "name": r.name,
                "ok": r.ok,
                "reason": r.reason,
                "status": r.response_status,
                "request": r.request,
                "response": r.response_body,
            }
            for r in runner.results
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"\nReport written → {path}")


@dataclass
class StepResult:
    name: str
    ok: bool
    reason: str = ""
    request: dict[str, Any] = field(default_factory=dict)
    response_status: int | None = None
    response_body: Any = None


class WorkflowRunner:
    def __init__(self, *, base_url: str, verbose: bool = True, email_safe: bool = True) -> None:
        self.base = base_url.rstrip("/")
        self.verbose = verbose
        self.email_safe = email_safe
        self.token: str | None = None
        self.admin_token: str | None = None
        self.org_id: str | None = None
        self.results: list[StepResult] = []

    def invite_channels(self) -> list[str]:
        """WhatsApp-only during tests so SMTP stays free for manual/admin sends."""
        if self.email_safe:
            return ["whatsapp"]
        return ["email", "whatsapp"]

    # ── logging ────────────────────────────────────────────────────────────

    def _print_step(self, step: StepResult) -> None:
        icon = "✅" if step.ok else "❌"
        print(f"\n{'=' * 72}")
        print(f"{icon} {step.name}")
        if step.request:
            print("→ Request:")
            print(json.dumps(step.request, indent=2, default=str)[:4000])
        if step.response_status is not None:
            print(f"← HTTP {step.response_status}")
        if step.response_body is not None:
            body = json.dumps(step.response_body, indent=2, default=str)
            print(f"← Body:\n{body[:6000]}")
        if not step.ok and step.reason:
            print(f"Reason: {step.reason}")
        self.results.append(step)

    def _record(
        self,
        name: str,
        *,
        ok: bool,
        reason: str = "",
        request: dict[str, Any] | None = None,
        status: int | None = None,
        body: Any = None,
        response_body: Any = None,
    ) -> StepResult:
        payload = response_body if response_body is not None else body
        step = StepResult(
            name=name,
            ok=ok,
            reason=reason,
            request=request or {},
            response_status=status,
            response_body=payload,
        )
        self._print_step(step)
        return step

    # ── HTTP helpers ───────────────────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json_body: dict | list | None = None,
        form_body: dict[str, str] | None = None,
        multipart: tuple[str, bytes, str] | None = None,
        timeout: int = 120,
    ) -> tuple[int, Any]:
        url = f"{self.base}{path}"
        headers: dict[str, str] = {"Accept": "application/json"}
        data: bytes | None = None

        if token:
            headers["Authorization"] = f"Bearer {token}"

        if multipart is not None:
            field_name, file_bytes, filename = multipart
            boundary = f"----voxbulk-e2e-{uuid.uuid4().hex}"
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
            parts = [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode(),
                b"Content-Type: text/csv\r\n\r\n",
                file_bytes,
                b"\r\n",
                f"--{boundary}--\r\n".encode(),
            ]
            data = b"".join(parts)
        elif form_body is not None:
            data = urlencode(form_body).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif json_body is not None:
            data = json.dumps(json_body).encode()
            headers["Content-Type"] = "application/json"

        req = Request(url, data=data, headers=headers, method=method.upper())
        try:
            with urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                status = resp.status
        except HTTPError as exc:
            status = exc.code
            raw = exc.read().decode("utf-8", errors="replace")
        except URLError as exc:
            raise RuntimeError(f"Network error for {method} {url}: {exc}") from exc

        if not raw:
            return status, None
        try:
            return status, json.loads(raw)
        except json.JSONDecodeError:
            return status, raw

    def _api(
        self,
        name: str,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json_body: dict | list | None = None,
        form_body: dict[str, str] | None = None,
        multipart: tuple[str, bytes, str] | None = None,
        expect_ok: bool = True,
        check: Callable[[Any], bool] | None = None,
    ) -> Any:
        req_info = {"method": method, "path": path}
        if json_body is not None:
            req_info["json"] = json_body
        if form_body is not None:
            req_info["form"] = {k: ("***" if "password" in k else v) for k, v in form_body.items()}
        if multipart is not None:
            req_info["multipart"] = {"filename": multipart[2], "bytes": len(multipart[1])}

        try:
            status, body = self._request(
                method,
                path,
                token=token or self.token,
                json_body=json_body,
                form_body=form_body,
                multipart=multipart,
            )
        except RuntimeError as exc:
            self._record(name, ok=False, reason=str(exc), request=req_info)
            if expect_ok:
                raise
            return None

        ok = 200 <= status < 300
        reason = ""
        if not ok:
            reason = f"Unexpected HTTP {status}"
        elif check is not None:
            try:
                ok = bool(check(body))
                if not ok:
                    reason = "Response check failed"
            except Exception as exc:
                ok = False
                reason = f"Check error: {exc}"

        self._record(name, ok=ok, reason=reason, request=req_info, status=status, body=body)
        if expect_ok and not ok:
            raise RuntimeError(f"Step failed: {name} — {reason or status}")
        return body

    # ── workflow steps ─────────────────────────────────────────────────────

    def login(self, email: str, password: str, org_id: str | None, *, label: str) -> str:
        form: dict[str, str] = {"username": email, "password": password}
        if org_id:
            form["org_id"] = org_id
        body = self._api(
            f"Authenticate ({label})",
            "POST",
            "/auth/token",
            form_body=form,
            token=None,
            check=lambda b: isinstance(b, dict) and bool(b.get("access_token")),
        )
        token = str(body["access_token"])
        if label == "dashboard":
            self.token = token
            self.org_id = str(body.get("org_id") or org_id or "")
        else:
            self.admin_token = token
        return token

    def step_billing_context(self) -> dict[str, Any]:
        return self._api(
            "Interview billing context",
            "GET",
            "/service-orders/interview/billing-context",
            check=lambda b: isinstance(b, dict),
        )

    def step_create_draft(self) -> str:
        body = self._api(
            "Create interview draft",
            "POST",
            "/service-orders/interview/draft/new",
            check=lambda b: isinstance(b, dict) and bool((b.get("order") or {}).get("id")),
        )
        return str(body["order"]["id"])

    def step_save_draft(self, order_id: str, *, window_start: datetime, window_end: datetime) -> dict[str, Any]:
        payload = {
            "order_id": order_id,
            "title": f"E2E workflow test {_utc_now().strftime('%Y-%m-%d %H:%M')} UTC",
            "role": "E2E Test Engineer",
            "criteria": "Python, APIs, communication, debugging",
            "config": {
                "role": "E2E Test Engineer",
                "criteria": "Python, APIs, communication, debugging",
                "screening_criteria": "Python, APIs, communication, debugging",
                "delivery": "ai_call",
                "script_approved": True,
                "approved_script": DEFAULT_SCRIPT,
                "generated_script_draft": DEFAULT_SCRIPT,
                "system_prompt": "Run a professional phone screening interview.",
                "cv_email_enabled": False,
                "call_workflow": "screening",
            },
            "run_mode": "scheduled",
            "scheduled_start_at": _iso(window_start),
            "scheduled_end_at": _iso(window_end),
        }
        return self._api(
            "Save draft config + calling window",
            "POST",
            "/service-orders/interview/draft",
            json_body=payload,
            check=lambda b: isinstance(b, dict) and bool(b.get("order")),
        )

    def step_upload_candidate(
        self,
        order_id: str,
        *,
        name: str,
        phone: str,
        email: str,
    ) -> dict[str, Any]:
        csv_content = f"name,phone,email\n{name},{phone},{email}\n".encode()
        return self._api(
            "Upload test candidate (CSV intake)",
            "POST",
            f"/service-orders/{order_id}/recipients/intake-contacts",
            multipart=("file", csv_content, "e2e-candidate.csv"),
            check=lambda b: isinstance(b, dict) and int((b.get("summary") or {}).get("ready") or 0) >= 1,
        )

    def step_quote(self, order_id: str) -> dict[str, Any]:
        return self._api(
            "Refresh quote",
            "POST",
            f"/service-orders/{order_id}/quote",
            check=lambda b: isinstance(b, dict),
        )

    def step_pay_and_approve(self, order_id: str, billing: dict[str, Any]) -> None:
        if billing.get("has_active_subscription"):
            self._record(
                "Payment (skipped — active subscription/package)",
                ok=True,
                request={"note": "launch will auto-approve via subscription"},
                body=billing,
            )
            return

        self._api(
            "Submit cash payment",
            "POST",
            f"/service-orders/{order_id}/pay-cash",
            json_body={"note": "E2E workflow test payment"},
        )

        if not self.admin_token:
            self._record(
                "Admin approve payment",
                ok=False,
                reason="No admin token — set VOXBULK_ADMIN_EMAIL / VOXBULK_ADMIN_PASSWORD",
            )
            raise RuntimeError("Admin credentials required for cash payment approval")

        self._api(
            "Admin approve payment",
            "POST",
            f"/admin/platform-services/orders/{order_id}/approve-payment",
            token=self.admin_token,
            json_body={"note": "E2E workflow test auto-approval"},
            check=lambda b: isinstance(b, dict) and b.get("payment_status") == "approved",
        )

    def step_launch(self, order_id: str) -> dict[str, Any]:
        channels = self.invite_channels()
        return self._api(
            "Launch interview (invites + schedule)",
            "POST",
            f"/service-orders/{order_id}/interview/launch",
            json_body={"channels": channels, "resend_invites": True},
            check=lambda b: isinstance(b, dict) and b.get("ok") is not False,
        )

    def step_send_invites(self, order_id: str, *, force: bool = True) -> dict[str, Any]:
        channels = self.invite_channels()
        return self._api(
            "Send booking invites (explicit)",
            "POST",
            f"/service-orders/{order_id}/interview-booking/send-invites",
            json_body={"force_resend": force, "channels": channels},
            check=lambda b: isinstance(b, dict),
        )

    def step_fetch_recipients(self, order_id: str) -> list[dict[str, Any]]:
        body = self._api(
            "List recipients",
            "GET",
            f"/service-orders/{order_id}/recipients",
            check=lambda b: isinstance(b, dict) and isinstance(b.get("recipients"), list),
        )
        return list(body.get("recipients") or [])

    def step_resolve_booking_token(
        self,
        order_id: str,
        *,
        launch_invites: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        recipients = self.step_fetch_recipients(order_id)
        if not recipients:
            raise RuntimeError("No recipients on order")
        recipient = recipients[0]
        recipient_id = str(recipient.get("id") or "")

        token = _token_from_recipient(recipient)
        if token:
            self._record(
                "Resolve booking token",
                ok=True,
                request={"source": "recipients.booking_token"},
                body={"token_prefix": token[:12] + "…", "recipient_id": recipient_id},
            )
            return token, recipient

        # Token is always created server-side on invite dispatch; refresh once before resending.
        time.sleep(2)
        recipients = self.step_fetch_recipients(order_id)
        recipient = recipients[0]
        token = _token_from_recipient(recipient)
        if token:
            self._record(
                "Resolve booking token",
                ok=True,
                request={"source": "recipients after refresh"},
                body={"token_prefix": token[:12] + "…"},
            )
            return token, recipient

        if recipient_id:
            activity = self._api(
                "Activity timeline (booking URL fallback)",
                "GET",
                f"/service-orders/{order_id}/recipients/{recipient_id}/activity",
                check=lambda b: isinstance(b, dict),
            )
            token = _token_from_activity(activity if isinstance(activity, dict) else {})
            if token:
                self._record(
                    "Resolve booking token",
                    ok=True,
                    request={"source": "activity.booking_url"},
                    body={"token_prefix": token[:12] + "…"},
                )
                return token, recipient

        invite = self.step_send_invites(order_id, force=True)
        if isinstance(invite, dict) and invite.get("errors"):
            self._record(
                "Send invites errors (non-fatal for token lookup)",
                ok=bool(invite.get("ok")),
                reason="; ".join((invite.get("errors") or [])[:3]) or "invite dispatch had errors",
                body=invite,
            )
        time.sleep(2)
        recipients = self.step_fetch_recipients(order_id)
        recipient = recipients[0]
        token = _token_from_recipient(recipient)
        if token:
            self._record(
                "Resolve booking token",
                ok=True,
                request={"source": "recipients after send-invites"},
                body={"token_prefix": token[:12] + "…"},
            )
            return token, recipient

        self._record(
            "Resolve booking token",
            ok=False,
            reason="No token on recipient — redeploy API (booking_token field) or check WhatsApp invite errors",
            body=recipient,
        )
        raise RuntimeError("No booking_token on recipient")

    def step_public_booking_page(self, booking_token: str) -> dict[str, Any]:
        return self._api(
            "Public booking page (available slots)",
            "GET",
            f"/public/interview-booking/{booking_token}",
            token=None,
            check=lambda b: isinstance(b, dict) and b.get("booking_closed") is not True,
        )

    def step_confirm_booking(self, booking_token: str, slot_iso: str) -> dict[str, Any]:
        return self._api(
            "Confirm booking slot",
            "POST",
            f"/public/interview-booking/{booking_token}/confirm",
            token=None,
            json_body={"slot_start_at": slot_iso},
            check=lambda b: isinstance(b, dict) and b.get("ok") is not False,
        )

    def step_reschedule_booking(self, booking_token: str, slot_iso: str) -> dict[str, Any]:
        return self._api(
            "Reschedule booking slot",
            "POST",
            f"/public/interview-booking/{booking_token}/reschedule",
            token=None,
            json_body={"slot_start_at": slot_iso},
            check=lambda b: isinstance(b, dict) and b.get("rescheduled") is True,
        )

    def step_wait_for_manual_booking(
        self,
        booking_token: str,
        *,
        timeout_sec: int = 900,
        poll_sec: int = 5,
    ) -> tuple[str, dict[str, Any]]:
        """Poll public booking page until candidate picks a slot."""
        deadline = time.time() + timeout_sec
        last: dict[str, Any] = {}
        booking_url = f"{os.environ.get('BOOKING_APP_ORIGIN', 'http://localhost:5175')}/book/{booking_token}"
        print(f"\n📧 Pick your slot in the email link (or open): {booking_url}\n")
        while time.time() < deadline:
            page = self.step_public_booking_page(booking_token)
            last = page if isinstance(page, dict) else {}
            if last.get("already_booked") and last.get("booked_start_at"):
                slot = str(last["booked_start_at"])
                self._record(
                    "Manual booking detected",
                    ok=True,
                    body={"booked_start_at": slot, "booked_end_at": last.get("booked_end_at")},
                )
                return slot, last
            remaining = int(deadline - time.time())
            if remaining % 30 < poll_sec:
                print(f"… waiting for you to book ({remaining}s left) …")
            time.sleep(poll_sec)
        self._record(
            "Manual booking detected",
            ok=False,
            reason=f"No booking within {timeout_sec}s — open {booking_url}",
            body=last,
        )
        raise RuntimeError(f"Manual booking timeout — open {booking_url}")

        return self._api(
            "Cancel booking slot",
            "POST",
            f"/public/interview-booking/{booking_token}/cancel",
            token=None,
            check=lambda b: isinstance(b, dict) and b.get("cancelled") is True,
        )

    def step_poll_order_running(self, order_id: str, *, timeout_sec: int = 90) -> dict[str, Any]:
        deadline = time.time() + timeout_sec
        last: dict[str, Any] = {}
        while time.time() < deadline:
            status, body = self._request("GET", f"/service-orders/{order_id}", token=self.token)
            if isinstance(body, dict):
                last = body
                if str(body.get("status") or "").lower() == "running":
                    self._record(
                        "Poll until campaign running",
                        ok=True,
                        request={"order_id": order_id, "waited_sec": round(timeout_sec - (deadline - time.time()))},
                        status=status,
                        response_body={"status": body.get("status"), "started_at": body.get("started_at")},
                    )
                    return body
            time.sleep(3)
        self._record(
            "Poll until campaign running",
            ok=False,
            reason=f"Order not running after {timeout_sec}s",
            response_body=last,
        )
        raise RuntimeError("Campaign did not enter running state")

    def step_get_order(self, order_id: str) -> dict[str, Any]:
        return self._api("Get order status", "GET", f"/service-orders/{order_id}")

    def step_wait_for_real_call(
        self,
        order_id: str,
        recipient_id: str,
        *,
        timeout_sec: int,
    ) -> dict[str, Any]:
        deadline = time.time() + timeout_sec
        last: dict[str, Any] = {}
        while time.time() < deadline:
            body = self._api(
                "Poll recipient detail (real call)",
                "GET",
                f"/service-orders/{order_id}/recipients/{recipient_id}/interview-detail",
                expect_ok=True,
            )
            last = body if isinstance(body, dict) else {}
            candidate = last.get("candidate") if isinstance(last.get("candidate"), dict) else {}
            status = str(candidate.get("status") or last.get("status") or "").lower()
            analysis = last.get("analysis") if isinstance(last.get("analysis"), dict) else {}
            score = analysis.get("score") if analysis.get("score") is not None else candidate.get("score")
            has_report = bool(candidate.get("has_interview_report")) or score is not None
            if status in {"completed", "done"} and has_report:
                self._record(
                    "Real call completed + analysis saved",
                    ok=True,
                    response_body={
                        "status": status,
                        "score": score,
                        "has_interview_report": candidate.get("has_interview_report"),
                    },
                )
                return last
            time.sleep(5)
        self._record(
            "Real call completed + analysis saved",
            ok=False,
            reason=f"No completed analysis after {timeout_sec}s — check allowlist, slot time, Telnyx, script_approved",
            response_body=last,
        )
        raise RuntimeError("Timed out waiting for real call")

    def step_interview_results(self, order_id: str) -> dict[str, Any]:
        return self._api(
            "Interview results aggregate",
            "GET",
            f"/service-orders/{order_id}/interview-results",
            check=lambda b: isinstance(b, dict) and isinstance(b.get("candidates"), list),
        )

    def step_recipient_detail(self, order_id: str, recipient_id: str) -> dict[str, Any]:
        return self._api(
            "Recipient interview detail + score",
            "GET",
            f"/service-orders/{order_id}/recipients/{recipient_id}/interview-detail",
            check=lambda b: isinstance(b, dict),
        )

    def step_activity_timeline(self, order_id: str, recipient_id: str) -> dict[str, Any]:
        return self._api(
            "Recipient activity timeline",
            "GET",
            f"/service-orders/{order_id}/recipients/{recipient_id}/activity",
            check=lambda b: isinstance(b, dict),
        )

    def step_stop_campaign(self, order_id: str) -> dict[str, Any]:
        return self._api(
            "Stop interview campaign (closure notifications)",
            "POST",
            f"/service-orders/{order_id}/stop",
            json_body={"reason": "E2E workflow test — intentional stop"},
            check=lambda b: isinstance(b, dict) and str(b.get("status") or "").lower() == "cancelled",
        )

    def step_fetch_report_html(self, order_id: str, recipient_id: str) -> tuple[int, Any]:
        status, body = self._request(
            "GET",
            f"/service-orders/{order_id}/recipients/{recipient_id}/interview-candidate-report.html",
            token=self.token,
        )
        preview = body[:500] if isinstance(body, str) else body
        self._record(
            "Candidate report HTML",
            ok=200 <= status < 300,
            reason="" if 200 <= status < 300 else f"HTTP {status}",
            request={"path": f"/service-orders/{order_id}/recipients/{recipient_id}/interview-candidate-report.html"},
            status=status,
            body={"preview": preview, "bytes": len(body) if isinstance(body, str) else None},
        )
        return status, body

    def step_delete_order(self, order_id: str) -> None:
        self._api("Delete test order (cleanup)", "DELETE", f"/service-orders/{order_id}")

    def summary(self) -> int:
        passed = sum(1 for r in self.results if r.ok)
        failed = [r for r in self.results if not r.ok]
        print(f"\n{'=' * 72}")
        print("SUMMARY")
        print(f"  Passed: {passed}/{len(self.results)}")
        if failed:
            print("  Failed steps:")
            for r in failed:
                print(f"    ❌ {r.name} — {r.reason or 'see body above'}")
            print("\n  Likely fixes:")
            if any("booking_token" in (r.reason or "") for r in failed):
                print("    • Invites/SMTP/Telnyx — check launch response errors and Admin email settings")
            if any("analysis" in r.name.lower() or "score" in r.name.lower() for r in failed):
                print("    • AI provider — verify DeepSeek/OpenAI keys in Admin → Integrations")
            if any("running" in r.name.lower() for r in failed):
                print("    • Scheduler — ensure API process runs interview_call_scheduler_loop; calling window must have started")
            if any("Real call" in r.name for r in failed):
                print("    • Phone — candidate number must be on Telnyx allowlist; book slot in the past window only after slot time")
            if any("Admin approve" in r.name for r in failed):
                print("    • Payment — set VOXBULK_ADMIN_* or use an org with active interview subscription")
        else:
            print("  All steps passed.")
        print(f"{'=' * 72}\n")
        return 0 if not failed else 1


def _pick_booking_slot(page: dict[str, Any], *, minutes_ahead: int = 1, slot_start_at: str = "") -> str:
    slots = [str(s) for s in (page.get("available_slots") or []) if s]
    if not slots:
        raise RuntimeError("No available booking slots — widen calling window or check booking hours")

    if slot_start_at.strip():
        want = slot_start_at.strip()
        if want in slots:
            return want
        try:
            want_dt = datetime.fromisoformat(want.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            raise RuntimeError(f"--slot-start-at is invalid ISO datetime: {want!r}")
        parsed: list[tuple[datetime, str]] = []
        for slot in slots:
            try:
                dt = datetime.fromisoformat(slot.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                continue
            parsed.append((dt, slot))
        if parsed:
            parsed.sort(key=lambda x: x[0])
            for dt, slot in parsed:
                if dt >= want_dt:
                    return slot
            return parsed[-1][1]
        raise RuntimeError(
            f"--slot-start-at {want!r} is not in available_slots — pick one of: {slots[:5]}{'…' if len(slots) > 5 else ''}"
        )

    target = _utc_now() + timedelta(minutes=max(0, minutes_ahead))
    parsed: list[tuple[datetime, str]] = []
    for slot in slots:
        try:
            dt = datetime.fromisoformat(slot.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            continue
        parsed.append((dt, slot))
    if not parsed:
        return slots[0]
    parsed.sort(key=lambda x: x[0])
    for dt, slot in parsed:
        if dt >= target:
            return slot
    return parsed[-1][1]


def _seconds_until_slot(slot_iso: str, *, buffer_seconds: int = 10) -> int:
    try:
        dt = datetime.fromisoformat(slot_iso.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return 0
    wait = int((dt - _utc_now()).total_seconds()) + buffer_seconds
    return max(0, wait)


def main() -> int:
    parser = argparse.ArgumentParser(description="E2E interview workflow test against live API")
    parser.add_argument("--base-url", default=os.environ.get("VOXBULK_API_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--email", default=os.environ.get("VOXBULK_EMAIL", ""))
    parser.add_argument("--password", default=os.environ.get("VOXBULK_PASSWORD", ""))
    parser.add_argument("--org-id", default=os.environ.get("VOXBULK_ORG_ID", ""))
    parser.add_argument("--admin-email", default=os.environ.get("VOXBULK_ADMIN_EMAIL", ""))
    parser.add_argument("--admin-password", default=os.environ.get("VOXBULK_ADMIN_PASSWORD", ""))
    parser.add_argument("--candidate-name", default=os.environ.get("VOXBULK_CANDIDATE_NAME", "E2E Test Candidate"))
    parser.add_argument("--candidate-phone", default=os.environ.get("VOXBULK_CANDIDATE_PHONE", "+447700900123"))
    parser.add_argument("--candidate-email", default=os.environ.get("VOXBULK_CANDIDATE_EMAIL", "e2e-test@example.com"))
    parser.add_argument(
        "--send-test-emails",
        action="store_true",
        help="Send invite/confirm/stop emails during test (default: WhatsApp-only invites so SMTP stays free)",
    )
    parser.add_argument("--wait-for-slot-seconds", type=int, default=-1, help="Sleep before dial (-1 = auto from booked slot)")
    parser.add_argument(
        "--slot-start-at",
        default="",
        help="Book this exact slot (ISO UTC, e.g. 2026-06-02T14:10:00Z) — skips auto-pick",
    )
    parser.add_argument(
        "--slot-minutes-ahead",
        type=int,
        default=1,
        help="Auto-pick first slot at least this many minutes from now (default 1; use 0 for nearest slot)",
    )
    parser.add_argument(
        "--with-cancel-rebook",
        action="store_true",
        help="After first booking: cancel slot, then book a later slot (tests cancel + confirm emails)",
    )
    parser.add_argument(
        "--manual-booking",
        action="store_true",
        help="Send invite email then wait for you to pick a slot on the booking page (no auto-book)",
    )
    parser.add_argument(
        "--manual-booking-timeout",
        type=int,
        default=900,
        help="Seconds to wait for manual booking (default 900)",
    )
    parser.add_argument("--wait-for-real-call-seconds", type=int, default=300)
    parser.add_argument("--skip-stop", action="store_true", help="Skip stop step (default: skip when email-safe)")
    parser.add_argument("--delete-order", action="store_true", help="Delete order after run (default: keep for debugging)")
    parser.add_argument("--log-file", default=os.environ.get("VOXBULK_E2E_LOG", ""), help="Append all output to this log file")
    parser.add_argument("--report-file", default=os.environ.get("VOXBULK_E2E_REPORT", ""), help="Write JSON report path")
    args = parser.parse_args()

    log_path = Path(args.log_file) if args.log_file else None
    if log_path:
        sys.stdout = _Tee(sys.stdout, log_path)  # type: ignore[assignment]
        sys.stderr = _Tee(sys.stderr, log_path)  # type: ignore[assignment]

    if not args.email or not args.password:
        print("ERROR: Set VOXBULK_EMAIL and VOXBULK_PASSWORD (or pass --email / --password)", file=sys.stderr)
        return 2

    admin_email = args.admin_email or args.email
    admin_password = args.admin_password or args.password

    runner = WorkflowRunner(base_url=args.base_url, email_safe=not args.send_test_emails)
    order_id: str | None = None
    recipient_id: str | None = None
    booked_slot: str | None = None
    launch: dict[str, Any] | None = None
    detail: dict[str, Any] | None = None
    keep_order = not args.delete_order
    skip_stop = args.skip_stop or (not args.send_test_emails)

    print(f"Interview E2E test → {args.base_url}")
    print(f"Candidate: {args.candidate_name} <{args.candidate_email}> {args.candidate_phone}")
    print(f"Email mode: {'test sends SMTP emails' if args.send_test_emails else 'email-safe (WhatsApp invites only)'}")
    print(f"Call mode: real Telnyx (--no-simulate-call) | slot +{args.slot_minutes_ahead}m")
    if log_path:
        print(f"Log file: {log_path}")

    try:
        runner.login(args.email, args.password, args.org_id or None, label="dashboard")
        if admin_email != args.email or admin_password != args.password:
            runner.login(admin_email, admin_password, args.org_id or None, label="admin")
        else:
            runner.admin_token = runner.token

        billing = runner.step_billing_context()
        order_id = runner.step_create_draft()

        window_start = _utc_now() - timedelta(minutes=5)
        window_end = _utc_now() + timedelta(hours=4)
        runner.step_save_draft(order_id, window_start=window_start, window_end=window_end)
        intake = runner.step_upload_candidate(
            order_id,
            name=args.candidate_name,
            phone=args.candidate_phone,
            email=args.candidate_email,
        )
        runner.step_quote(order_id)
        runner.step_pay_and_approve(order_id, billing if isinstance(billing, dict) else {})
        launch = runner.step_launch(order_id)
        if isinstance(launch, dict):
            runner._record(
                "Launch response detail",
                ok=True,
                body={
                    "ok": launch.get("ok"),
                    "status": launch.get("status"),
                    "message": launch.get("message"),
                    "invites": launch.get("invites"),
                },
            )
            inv = launch.get("invites") or {}
            if inv.get("errors"):
                runner._record(
                    "Launch invite errors",
                    ok=bool(inv.get("ok")),
                    reason="; ".join((inv.get("errors") or [])[:5]),
                    body=inv,
                )

        booking_token, recipient = runner.step_resolve_booking_token(
            order_id,
            launch_invites=launch.get("invites") if isinstance(launch, dict) else None,
        )
        recipient_id = str(recipient.get("id") or "")

        page = runner.step_public_booking_page(booking_token)
        booking_url = f"{os.environ.get('BOOKING_APP_ORIGIN', 'http://localhost:5175')}/book/{booking_token}"
        print(f"\nBooking link: {booking_url}\n")

        if args.manual_booking:
            booked_slot, page = runner.step_wait_for_manual_booking(
                booking_token,
                timeout_sec=args.manual_booking_timeout,
            )
        else:
            booked_slot = _pick_booking_slot(
                page,
                minutes_ahead=args.slot_minutes_ahead,
                slot_start_at=args.slot_start_at.strip(),
            )
            runner._record(
                "Selected booking slot",
                ok=True,
                body={
                    "slot": booked_slot,
                    "minutes_ahead": args.slot_minutes_ahead,
                    "source": "--slot-start-at" if args.slot_start_at.strip() else "auto",
                },
            )
            confirm = runner.step_confirm_booking(booking_token, booked_slot)
            if args.send_test_emails and isinstance(confirm, dict) and confirm.get("confirmation_email_sent") is False:
                runner._record(
                    "Booking confirmation email",
                    ok=False,
                    reason="confirmation_email_sent=false — check SMTP + interview_booking_confirm template",
                    body=confirm,
                )
            elif isinstance(confirm, dict) and confirm.get("confirmation_email_sent") is False:
                runner._record(
                    "Booking confirmation email",
                    ok=True,
                    reason="skipped check — email-safe mode (SMTP left free for manual sends)",
                    body={"confirmation_email_sent": False},
                )

        if args.with_cancel_rebook and not args.manual_booking:
            cancel = runner.step_cancel_booking(booking_token)
            if args.send_test_emails and isinstance(cancel, dict) and cancel.get("cancellation_email_sent") is False:
                runner._record(
                    "Booking cancellation email",
                    ok=False,
                    reason="cancellation_email_sent=false — check SMTP + interview_booking_cancel template",
                    body=cancel,
                )
            page2 = runner.step_public_booking_page(booking_token)
            rebook_slot = _pick_booking_slot(
                page2,
                minutes_ahead=max(args.slot_minutes_ahead + 2, 3),
                slot_start_at="",
            )
            runner._record(
                "Selected rebook slot",
                ok=True,
                body={"slot": rebook_slot},
            )
            rebook = runner.step_reschedule_booking(booking_token, rebook_slot)
            booked_slot = rebook_slot
            if args.send_test_emails and isinstance(rebook, dict) and rebook.get("confirmation_email_sent") is False:
                runner._record(
                    "Rebook confirmation email",
                    ok=False,
                    reason="confirmation_email_sent=false after rebook",
                    body=rebook,
                )

        runner.step_poll_order_running(order_id, timeout_sec=120)

        wait_sec = args.wait_for_slot_seconds
        if wait_sec < 0 and booked_slot:
            wait_sec = _seconds_until_slot(booked_slot)
        if wait_sec > 0:
            print(f"\n… waiting {wait_sec}s until booked slot (+ buffer) …")
            time.sleep(wait_sec)

        runner.step_wait_for_real_call(
            order_id,
            recipient_id,
            timeout_sec=args.wait_for_real_call_seconds,
        )

        results = runner.step_interview_results(order_id)
        detail = runner.step_recipient_detail(order_id, recipient_id)
        runner.step_activity_timeline(order_id, recipient_id)
        runner.step_fetch_report_html(order_id, recipient_id)

        cand = (detail or {}).get("candidate") if isinstance((detail or {}).get("candidate"), dict) else {}
        score = cand.get("score") or ((detail or {}).get("analysis") or {}).get("score")
        candidates = (results or {}).get("candidates") or []
        runner._record(
            "Verify score persisted in API",
            ok=score is not None or any(c.get("score") is not None for c in candidates),
            reason="" if score is not None else "No score on detail or results — analysis may have failed",
            response_body={"detail_score": score, "results_count": len(candidates)},
        )

        if not skip_stop:
            runner.step_stop_campaign(order_id)
        else:
            runner._record(
                "Stop interview campaign",
                ok=True,
                reason="skipped — email-safe mode (avoid closure emails blocking manual SMTP)",
            )

    except (RuntimeError, Exception) as exc:
        print(f"\nFATAL: {exc}", file=sys.stderr)
        import traceback

        traceback.print_exc()
    finally:
        report_path = Path(args.report_file) if args.report_file else Path(f"/tmp/voxbulk-e2e-report-{_utc_now().strftime('%Y%m%d-%H%M%S')}.json")
        try:
            _write_report(
                report_path,
                runner=runner,
                order_id=order_id,
                recipient_id=recipient_id,
                booked_slot=booked_slot,
                launch=launch if isinstance(launch, dict) else None,
                detail=detail if isinstance(detail, dict) else None,
            )
        except Exception as exc:
            print(f"Could not write report: {exc}", file=sys.stderr)

        if order_id and not keep_order and runner.token:
            failed = any(not r.ok for r in runner.results)
            if failed:
                runner._record(
                    "Delete test order (cleanup)",
                    ok=True,
                    reason=f"Skipped — test had failures; order {order_id} kept for debugging (or delete manually)",
                )
            else:
                try:
                    _, body = runner._request("GET", f"/service-orders/{order_id}", token=runner.token)
                    st = str((body or {}).get("status") or "").lower() if isinstance(body, dict) else ""
                    if st in {"cancelled", "completed", "draft", "quoted", "paid", "scheduled"}:
                        runner.step_delete_order(order_id)
                    else:
                        runner._record(
                            "Delete test order (cleanup)",
                            ok=True,
                            reason=f"Skipped delete — order still {st!r} (use --keep-order to retain)",
                        )
                except Exception as exc:
                    runner._record("Delete test order (cleanup)", ok=False, reason=str(exc))

    return runner.summary()


if __name__ == "__main__":
    raise SystemExit(main())
