#!/usr/bin/env python3
"""List interview orders for a dashboard user — phone vs web sessions. READ ONLY.

Run on the VPS:

  cd /www/voxbulk/voxbulk-api
  source .venv/bin/activate
  python3 scripts/diagnose_user_interviews.py --email zaghlolno@gmail.com
"""

from __future__ import annotations

import argparse
import json
import os
import sys

API_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, API_ROOT)
os.chdir(API_ROOT)


def _loads(raw: str | None) -> dict:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _session_kind(result: dict) -> str:
    ch = str(result.get("channel") or "").lower()
    tr = str(result.get("transport") or "").lower()
    if tr == "webrtc" or ch == "meeting":
        return "web_meeting"
    if result.get("call_control_id") or ch in {"ai_call", "phone", "call"}:
        return "phone_call"
    if result.get("duration_seconds"):
        return "session_unknown"
    return "no_session"


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose interview orders for a user email")
    parser.add_argument("--email", required=True, help="Dashboard user email")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    from sqlalchemy import or_, select

    from app.core.database import get_sessionmaker
    from app.models.membership import OrganisationMembership
    from app.models.organisation import Organisation
    from app.models.service_order import ServiceOrder, ServiceOrderRecipient
    from app.models.user import User

    email = str(args.email or "").strip().lower()
    with get_sessionmaker()() as db:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is None:
            print(f"User not found: {email}")
            return 1

        memberships = db.execute(
            select(OrganisationMembership).where(OrganisationMembership.user_id == user.id)
        ).scalars().all()
        org_ids = {m.org_id for m in memberships}
        org_names = {}
        for oid in org_ids:
            org = db.get(Organisation, oid)
            org_names[oid] = org.name if org else oid

        print("=== User ===")
        print(f"  email     {user.email}")
        print(f"  id        {user.id}")
        print(f"  orgs      {', '.join(org_names.get(o, o) for o in sorted(org_ids)) or '—'}")

        scope = [ServiceOrder.user_id == user.id]
        if org_ids:
            scope.append(ServiceOrder.org_id.in_(list(org_ids)))
        stmt = (
            select(ServiceOrder)
            .where(ServiceOrder.service_code == "interview")
            .where(or_(*scope))
            .order_by(ServiceOrder.created_at.desc())
            .limit(max(1, int(args.limit)))
        )
        orders = list(db.execute(stmt).scalars())

        print(f"\n=== Interview orders ({len(orders)}) ===")
        if not orders:
            print("  No interview service_orders for this user/org.")
            print("  Note: Admin → Agents → Test WebRTC does NOT create an order.")
            return 0

        web_orders = 0
        for order in orders:
            cfg = _loads(order.config_json)
            delivery = str(cfg.get("delivery") or "ai_call").lower()
            recs = db.execute(
                select(ServiceOrderRecipient).where(ServiceOrderRecipient.order_id == order.id)
            ).scalars().all()
            kinds = {"web_meeting": 0, "phone_call": 0, "no_session": 0, "session_unknown": 0}
            for r in recs:
                kinds[_session_kind(_loads(r.result_json))] += 1
            has_web = kinds["web_meeting"] > 0 or delivery == "ai_meeting"
            if has_web:
                web_orders += 1
            print(f"\n  --- {order.campaign_id or order.reference_id or order.id[:8]} ---")
            print(f"  order_id        {order.id}")
            print(f"  org             {org_names.get(order.org_id, order.org_id)}")
            print(f"  status          {order.status} / payment {order.payment_status}")
            print(f"  config.delivery {delivery}")
            print(f"  quote           {order.quote_total_pence}p")
            print(f"  recipients      {len(recs)}")
            print(
                f"  sessions        web={kinds['web_meeting']} phone={kinds['phone_call']} "
                f"none={kinds['no_session']} other={kinds['session_unknown']}"
            )
            print(f"  admin_url       /operations/orders/{order.campaign_id or order.id}")

        print(f"\n=== Summary ===")
        print(f"  Total interview orders: {len(orders)}")
        print(f"  With any web/meeting session: {web_orders}")
        print(
            "\n  There is NO separate 'web interview orders' list in admin. "
            "All interviews are under Operations → Interviews (Finished tab when completed). "
            "Web shows as recipient channel=meeting / transport=webrtc on the order Calls & costs tab."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
