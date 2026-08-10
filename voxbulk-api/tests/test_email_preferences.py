"""Email notification preferences — catalog, gating, footer inject."""

from __future__ import annotations

from app.data.brand_email_layout import inject_email_preferences_footer, wrap_brand_email
from app.services.brand_assets import BRAND_COLORS
from app.services.email_preference_service import EmailPreferenceService, EMAIL_PREF_KEYS


def test_wrap_places_prefs_under_sent_footer_for_any_product():
    for footer in (
        "Sent via VOXBULK Expo · expo@voxbulk.com",
        "Sent by VOXBULK Billing · billing@voxbulk.com",
        "Sent by VOXBULK Support · support@voxbulk.com",
        "Sent via VOXBULK Smart Card QR · smartqr@voxbulk.com",
    ):
        html = wrap_brand_email(
            title="Test",
            inner_html=(
                "<p>Hi</p>"
                '<p style="font-size:13px;color:#6b6560;">'
                "Questions? Contact "
                '<a href="mailto:support@voxbulk.com">support@voxbulk.com</a>.'
                "</p>"
            ),
            footer=footer,
        )
        sent_at = html.find(footer.split("·")[0].strip())
        prefs_at = html.find("Manage Email Preferences")
        assert sent_at > 0 and prefs_at > sent_at, footer
        prefs_block = html[max(0, prefs_at - 200) : prefs_at + 40]
        assert "font-size:12px" in prefs_block
        assert BRAND_COLORS["ink_muted"] in prefs_block


def test_inject_email_preferences_footer_once():
    body = wrap_brand_email(title="Test", inner_html="<p>Hi</p>", footer="Sent by VOXBULK · careers@voxbulk.com")
    once = inject_email_preferences_footer(body)
    assert once.count("Manage Email Preferences") == 1
    twice = inject_email_preferences_footer(once)
    assert twice.count("Manage Email Preferences") == 1


def test_inject_relocates_mid_body_prefs_into_sent_footer():
    body = (
        '<td style="padding:28px;"><p>Hi</p>'
        '<p style="font-size:13px;color:#6b6560;">Questions? Contact billing@voxbulk.com</p>'
        '<p style="margin:8px 0 0;"><a href="https://x">Manage Email Preferences</a></p>'
        "</td>"
        '<td style="padding:16px 28px 24px;border-top:1px solid #e5e0d8;font-size:12px;color:#6b6560;">'
        "Sent by VOXBULK Billing · billing@voxbulk.com"
        "</td>"
    )
    out = inject_email_preferences_footer(body)
    assert out.count("Manage Email Preferences") == 1
    sent_at = out.find("Sent by VOXBULK Billing")
    prefs_at = out.find("Manage Email Preferences")
    assert sent_at < prefs_at


def test_inject_fallback_under_questions_when_no_sent_footer():
    body = (
        "<html><body><p>Hi</p>"
        '<p style="font-size:13px;color:#6b6560;">Questions? Contact support@voxbulk.com</p>'
        "</body></html>"
    )
    out = inject_email_preferences_footer(body)
    q = out.find("Questions? Contact")
    p = out.find("Manage Email Preferences")
    assert q < p


def test_pref_key_security_always_on():
    assert EmailPreferenceService.pref_key_for_template("forgot_password") is None
    assert EmailPreferenceService.pref_key_for_template("new_user") is None
    assert EmailPreferenceService.pref_key_for_template("interview_scheduling_invite") is None


def test_pref_key_optional_categories():
    assert EmailPreferenceService.pref_key_for_template("weekly_digest") == "weekly_digest"
    assert EmailPreferenceService.pref_key_for_template("sales_offer") == "news_newsletter"
    assert EmailPreferenceService.pref_key_for_template("new_invoice") == "billing"
    assert EmailPreferenceService.pref_key_for_template("usage_warning") == "usage_alerts"


def test_catalog_keys_stable():
    keys = {item["key"] for item in EmailPreferenceService.catalog()}
    assert keys == set(EMAIL_PREF_KEYS)
    assert "news_newsletter" in keys
