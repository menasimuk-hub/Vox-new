#!/usr/bin/env python3
"""Audit system email templates for branding, placeholders, and footer consistency."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data.system_email_defaults import SYSTEM_EMAIL_DEFAULTS  # noqa: E402
from app.services.brand_assets import BRAND_TAGLINE  # noqa: E402
from app.services.transactional_email_service import EMAIL_TEST_VARIABLES  # noqa: E402

_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

BILLING_KEYS = {
    "new_invoice",
    "invoice_document",
    "payment_failed",
    "payment_receipt",
    "billing_cancellation_requested",
    "billing_cancellation_reversed",
    "billing_wallet_credit_issued",
    "billing_bank_refund_approved",
    "billing_refund_request_rejected",
    "billing_subscription_ended",
    "billing_renewal_reminder",
    "billing_pending_invoice_reminder",
    "billing_payment_action_required",
}


def main() -> int:
    issues: list[str] = []
    for key, defaults in sorted(SYSTEM_EMAIL_DEFAULTS.items()):
        body = str(defaults.get("body") or "")
        subject = str(defaults.get("subject") or "")
        if not body.strip():
            issues.append(f"{key}: empty default body")
            continue
        if "wrap_brand_email" not in body and key not in {"invoice_document"}:
            if "<!DOCTYPE html><html><body" in body and key != "invoice_document":
                issues.append(f"{key}: off-brand raw HTML (missing wrap_brand_email in source)")
        if key != "invoice_document" and BRAND_TAGLINE not in body and "wrap_brand_email" in body:
            issues.append(f"{key}: branded wrapper should inherit tagline via wrap_brand_email()")
        placeholders = set(_PLACEHOLDER.findall(subject + body))
        missing = sorted(p for p in placeholders if p not in EMAIL_TEST_VARIABLES)
        if missing:
            issues.append(f"{key}: placeholders missing from EMAIL_TEST_VARIABLES: {', '.join(missing)}")
        footer = "billing@voxbulk.com" if key in BILLING_KEYS else "careers@voxbulk.com"
        if footer not in body and key != "invoice_document":
            issues.append(f"{key}: expected footer hint '{footer}' in default body")

    print("VOXBULK email template audit")
    print(f"Templates checked: {len(SYSTEM_EMAIL_DEFAULTS)}")
    if not issues:
        print("OK — no issues found.")
        return 0
    print(f"Issues: {len(issues)}")
    for line in issues:
        print(f"  - {line}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
