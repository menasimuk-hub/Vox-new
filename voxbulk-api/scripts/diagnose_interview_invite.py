#!/usr/bin/env python3
"""Explain why an interview's invitation email did or did not send — READ ONLY.

Sends nothing, changes nothing. Run on the VPS where the API/DB lives:

  cd /www/voxbulk/voxbulk-api
  source .venv/bin/activate
  python3 scripts/diagnose_interview_invite.py VB-CMP-808CF4F5

Accepts a dashboard campaign id (VB-CMP-...), an interview reference id
(VB-INT-...), or the internal ServiceOrder UUID.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

API_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, API_ROOT)
os.chdir(API_ROOT)


def _loads(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _resolve_order(db, ref: str):
    from sqlalchemy import select

    from app.models.service_order import ServiceOrder

    key = str(ref or "").strip()
    if not key:
        return None
    order = db.get(ServiceOrder, key)
    if order is not None:
        return order
    upper = key.upper()
    return db.execute(
        select(ServiceOrder).where(
            (ServiceOrder.campaign_id == upper) | (ServiceOrder.reference_id == upper)
        ).limit(1)
    ).scalar_one_or_none()


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose interview invitation email (read only)")
    parser.add_argument("order_ref", help="VB-CMP-… campaign id, VB-INT-… reference, or order UUID")
    args = parser.parse_args()

    from app.core.database import get_sessionmaker
    from app.services.career_email_service import careers_from_address, interview_email_delivery_status
    from app.services.interview_booking_service import _recipient_outreach_email
    from app.services.smtp_settings_service import SmtpSettingsService

    verdicts: list[str] = []

    with get_sessionmaker()() as db:
        order = _resolve_order(db, args.order_ref)
        if order is None:
            print(f"Order not found: {args.order_ref}")
            print("Use the dashboard campaign id (VB-CMP-...), the VB-INT-... reference, or the order UUID.")
            return 1

        cfg = _loads(order.config_json)
        delivery = str(cfg.get("delivery") or cfg.get("delivery_mode") or "ai_call").strip().lower()
        dispatch = cfg.get("last_invite_dispatch") if isinstance(cfg.get("last_invite_dispatch"), dict) else {}

        print("=== Order ===")
        print(f"  id              {order.id}")
        print(f"  campaign_id     {order.campaign_id}")
        print(f"  reference_id    {order.reference_id}")
        print(f"  service_code    {order.service_code}")
        print(f"  status          {order.status}")
        print(f"  payment_status  {order.payment_status}")
        print(f"  delivery        {delivery}")
        print(f"  scheduled_start {order.scheduled_start_at}")
        print(f"  scheduled_end   {order.scheduled_end_at}")
        print(f"  recipient_count {order.recipient_count}")

        print("\n=== Launch / dispatch flags ===")
        print(f"  launch_requested_at    {cfg.get('launch_requested_at')}")
        print(f"  booking_invites_sent_at{'':1}{cfg.get('booking_invites_sent_at')}")
        if dispatch:
            print(f"  last_invite_dispatch.ok           {dispatch.get('ok')}")
            print(f"  last_invite_dispatch.email_sent   {dispatch.get('email_sent')}")
            print(f"  last_invite_dispatch.whatsapp_sent{'':1}{dispatch.get('whatsapp_sent')}")
            print(f"  last_invite_dispatch.skipped      {dispatch.get('skipped_locked')}")
            for err in (dispatch.get("errors") or [])[:20]:
                print(f"      dispatch error: {err}")
        else:
            print("  last_invite_dispatch   <none — send_invites never ran for this order>")

        print("\n=== SMTP / email delivery ===")
        email_status = interview_email_delivery_status(db)
        smtp_row = SmtpSettingsService.get_row(db)
        _, careers_from = careers_from_address(db)
        print(f"  can_send_email      {email_status.get('can_send_email')}")
        print(f"  interview_from      {email_status.get('interview_from_email')}")
        print(f"  smtp_host           {smtp_row.host}")
        print(f"  smtp_port           {smtp_row.port}")
        print(f"  smtp_username       {smtp_row.username}")
        print(f"  admin_smtp_from     {smtp_row.from_email}")
        missing = email_status.get("smtp_missing_fields") or []
        if missing:
            print(f"  smtp_missing_fields {', '.join(str(m) for m in missing)}")
        admin_from = str(smtp_row.from_email or "").strip().lower()
        if admin_from and careers_from and admin_from != careers_from:
            print(
                f"  NOTE: Interview mail uses From={careers_from} but Admin SMTP default From is {admin_from}. "
                "Gmail may spam or drop mail if SPF/DKIM for voxbulk.com does not authorize this SMTP host."
            )

        print("\n=== Recipients ===")
        from app.services.platform_catalog_service import ServiceOrderService

        recipients = ServiceOrderService.get_recipients(db, order.id)
        if not recipients:
            print("  <no candidates on this order>")
        pending_with_email = 0
        for r in recipients:
            merged = _loads(r.result_json)
            outreach = _recipient_outreach_email(r)
            sent_at = merged.get("invite_email_sent_at")
            failed = merged.get("invite_email_failed")
            wa_at = merged.get("invite_wa_sent_at")
            if outreach and not sent_at:
                pending_with_email += 1
            print(
                f"  - {r.name or r.id}: email={outreach or '∅'} phone={r.phone or '∅'} "
                f"status={r.status} invite_email_sent_at={sent_at or '∅'} "
                f"invite_email_failed={failed or '∅'} invite_wa_sent_at={wa_at or '∅'}"
            )

        # ---- verdict ----
        if order.service_code != "interview":
            verdicts.append(f"This is a '{order.service_code}' order, not an interview — the interview invite workflow does not apply.")
        if order.payment_status != "approved":
            verdicts.append(
                f"payment_status='{order.payment_status}' (not 'approved') — invites only send at launch AFTER payment. "
                "Creating/saving a draft sends nothing."
            )
        if not order.scheduled_start_at or not order.scheduled_end_at:
            verdicts.append("Calling window not set (scheduled_start/end empty) — launch refuses to send invites until it is set.")
        if not email_status.get("can_send_email"):
            verdicts.append("SMTP is not enabled/complete (can_send_email=false) — the email channel is skipped at launch. Enable SMTP in Admin → Email.")
        if not recipients:
            verdicts.append("No candidates on the order — nothing to invite.")
        elif all(not _recipient_outreach_email(r) for r in recipients):
            verdicts.append("No candidate has an email address — invite emails cannot be addressed (add email or re-upload CV with contact details).")
        if dispatch and dispatch.get("ok") is False:
            verdicts.append("Last launch dispatch reported ok=false — see the dispatch errors above for the precise reason.")
        if not dispatch and not cfg.get("booking_invites_sent_at"):
            verdicts.append("send_invites has never run for this order — it was never launched (or launch errored before sending).")
        if pending_with_email and email_status.get("can_send_email") and order.payment_status == "approved":
            verdicts.append(
                f"{pending_with_email} candidate(s) have an email but no recorded invite — the scheduler auto-ensure "
                "(this fix) will send the invitation on its next tick."
            )

        email_sent_n = int(dispatch.get("email_sent") or 0) if dispatch else 0

        print("\n=== Verdict ===")
        if verdicts:
            for v in verdicts:
                print(f"  • {v}")
        if email_sent_n > 0 and order.payment_status == "approved":
            print("  • WORKFLOW OK: API handed the invite to SMTP (email_sent=%d, invite_email_sent_at set)." % email_sent_n)
            print("    If skipdaq@gmail.com (or the candidate inbox) is empty, this is DELIVERY — not a missing launch:")
            print("      1. Gmail → Spam / Promotions / All Mail — search: from:careers@voxbulk.com")
            print("      2. Admin → Email: SMTP host must be allowed to send AS careers@voxbulk.com (SPF + DKIM on voxbulk.com)")
            print("      3. On VPS: grep career_email_sent voxbulk-api/logs/*.log | tail -5")
            print("      4. Test same path: python3 scripts/send_interview_invite_email_test.py --to skipdaq@gmail.com")
        elif not verdicts:
            print("  No blocking condition detected — invites appear to have been sent (check recipient flags above and spam folder).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
