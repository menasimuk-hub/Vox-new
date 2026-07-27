"""AI Team / Apify reply knowledge-base matching."""

from __future__ import annotations

from app.services.ai_team_reply_kb import build_reply_kb_context, detect_issue_tags


def test_gmail_paywall_matches_free_email_playbook():
    tags = detect_issue_tags(
        from_email="alex@gmail.com",
        inbound_subject='Re: Test company, turn your "London excel show" scans into leads',
        inbound_body="i can't login and can't see offer it show me i have to pay , please advice",
    )
    assert tags[0] == "free_personal_email"
    assert "paywall_or_cant_see_offer" in tags
    assert "cant_login" in tags

    kb = build_reply_kb_context(
        from_email="alex@gmail.com",
        inbound_subject="Re: London excel show",
        inbound_body="i can't login and have to pay",
    )
    assert kb["from_is_free_email"] is True
    assert "company / work email" in kb["prompt_block"].lower() or "company email" in kb["prompt_block"].lower()
    assert "expired" in kb["prompt_block"].lower()  # hard rule forbids inventing expired trial
    assert "EXPO3DAYS" in kb["prompt_block"]
    assert "signin?promo=EXPO3DAYS" in kb["signup_url"]


def test_company_email_interest_is_not_free_mailbox():
    tags = detect_issue_tags(
        from_email="ops@acme-events.com",
        inbound_subject="Re: VoxBulk",
        inbound_body="Interesting — can we book a short demo next week?",
    )
    assert "free_personal_email" not in tags
    assert tags[0] == "wants_demo_or_info"

    kb = build_reply_kb_context(
        from_email="ops@acme-events.com",
        inbound_body="Interested in a demo",
    )
    assert kb["from_is_free_email"] is False
