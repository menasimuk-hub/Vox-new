"""Invite dispatch detection for launch/stop email workflows."""

from __future__ import annotations

import json
from datetime import datetime

from app.services.interview_booking_service import campaign_invites_were_sent


def test_campaign_invites_were_sent_from_dispatch_counts():
    order = type("O", (), {})()
    order.config_json = json.dumps(
        {
            "last_invite_dispatch": {
                "ok": True,
                "email_sent": 0,
                "whatsapp_sent": 2,
            }
        }
    )
    assert campaign_invites_were_sent(order) is True


def test_campaign_invites_were_sent_false_when_dispatch_failed():
    order = type("O", (), {})()
    order.config_json = json.dumps(
        {
            "booking_invites_sent_at": datetime.utcnow().isoformat(),
            "last_invite_dispatch": {"ok": False, "errors": ["smtp down"]},
        }
    )
    assert campaign_invites_were_sent(order) is False
