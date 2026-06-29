#!/usr/bin/env python3
"""Inspect SMTP transport + last invite send for an interview (no send)."""

from __future__ import annotations

import argparse
import json
import os
import sys

API_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, API_ROOT)
os.chdir(API_ROOT)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign_id", nargs="?", default="VB-CMP-9442F012")
    args = parser.parse_args()

    from sqlalchemy import select

    from app.core.database import get_sessionmaker
    from app.models.service_order import ServiceOrder, ServiceOrderRecipient
    from app.services.career_email_service import careers_from_address, interview_email_delivery_status
    from app.services.email_template_service import EmailTemplateService
    from app.services.smtp_settings_service import SmtpSettingsService

    with get_sessionmaker()() as db:
        row = SmtpSettingsService.get_row(db)
        configured, missing = SmtpSettingsService.compute_status(row)
        fn, fe = careers_from_address(db)
        print("=== SMTP transport (Admin → Email) ===")
        print(f"  host:        {row.smtp_host}")
        print(f"  port:        {row.smtp_port}")
        print(f"  username:    {row.smtp_username}")
        print(f"  use_tls:     {row.use_tls}  use_ssl: {row.use_ssl}")
        print(f"  is_enabled:  {row.is_enabled}")
        print(f"  configured:  {configured}  missing: {missing}")
        print(f"  admin_from:  {row.from_email}")
        print(f"  careers_from:{fn} <{fe}>")
        print(f"  can_send:    {interview_email_delivery_status(db)}")

        order = db.execute(
            select(ServiceOrder).where(ServiceOrder.campaign_id == args.campaign_id.upper())
        ).scalar_one_or_none()
        if not order:
            print(f"Order not found: {args.campaign_id}")
            return 1
        recipient = db.execute(
            select(ServiceOrderRecipient).where(ServiceOrderRecipient.order_id == order.id)
        ).scalar_one_or_none()
        merged = json.loads(recipient.result_json or "{}") if recipient else {}
        print("\n=== Last invite record ===")
        print(f"  to:          {recipient.email if recipient else '?'}")
        print(f"  invite_sent_to: {merged.get('invite_sent_to')}")
        print(f"  sent_at:     {merged.get('invite_email_sent_at')}")
        print(f"  failed:      {merged.get('invite_email_failed')}")
        print(f"  booking_url: {merged.get('booking_url')}")

        subj, body, enabled = EmailTemplateService.get_send_content(db, key="interview_booking_invite")
        print("\n=== Template interview_booking_invite ===")
        print(f"  enabled:     {enabled}")
        print(f"  subject:     {(subj or '')[:120]}")
        print(f"  body_len:    {len(body or '')}")

        cfg = json.loads(order.config_json or "{}")
        dispatch = cfg.get("last_invite_dispatch") or {}
        print("\n=== Verdict ===")
        if dispatch.get("email_sent"):
            print(
                "  API accepted SMTP send (email_sent=1). If inbox is empty, this is a DELIVERY issue:\n"
                "    • Check Gmail spam/promotions for careers@voxbulk.com\n"
                "    • Verify SMTP host can send AS careers@voxbulk.com (SPF/DKIM on voxbulk.com)\n"
                "    • Check mail server queue/logs for bounces to skipdaq@gmail.com\n"
                "    • Run: python3 scripts/send_interview_invite_email_test.py --to skipdaq@gmail.com"
            )
        else:
            print("  API did not record a successful email send — workflow issue, not delivery.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
