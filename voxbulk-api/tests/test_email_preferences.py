"""Email notification preferences — catalog, gating, footer inject."""

from __future__ import annotations

from app.data.brand_email_layout import inject_email_preferences_footer, wrap_brand_email
from app.services.brand_assets import BRAND_COLORS
from app.services.email_preference_service import EmailPreferenceService, EMAIL_PREF_KEYS


def test_wrap_brand_email_includes_manage_preferences_link():
    html = wrap_brand_email(title="Test", inner_html="<p>Hello</p>")
    assert "Manage Email Preferences" in html
    assert "settings/profile#email-notifications" in html
    # In main body cell, not only in bottom Sent-by strip
    assert 'padding:28px;' in html
    body_idx = html.find("Manage Email Preferences")
    footer_idx = html.find("border-top:1px solid")
    assert body_idx > 0 and footer_idx > 0
    assert body_idx < footer_idx


def test_wrap_places_prefs_under_contact_line():
    html = wrap_brand_email(
        title="Billing",
        inner_html=(
            "<p>Hi,</p>"
            '<p style="font-size:13px;color:#6b6560;">'
            "Questions about this decision? Contact us at "
            '<a href="mailto:billing@voxbulk.com" style="color:#1a2d5c;">billing@voxbulk.com</a>.'
            "</p>"
        ),
        footer="Sent by VOXBULK Billing · billing@voxbulk.com",
    )
    contact_at = html.find("Questions about this decision?")
    prefs_at = html.find("Manage Email Preferences")
    footer_at = html.find("Sent by VOXBULK Billing")
    assert contact_at < prefs_at < footer_at
    assert f'color:{BRAND_COLORS["ink_muted"]}' in html[prefs_at - 120 : prefs_at]


def test_inject_email_preferences_footer_once():
    body = "<html><body><p>Hi</p></body></html>"
    once = inject_email_preferences_footer(body)
    assert once.count("Manage Email Preferences") == 1
    twice = inject_email_preferences_footer(once)
    assert twice.count("Manage Email Preferences") == 1


def test_inject_relocates_bottom_footer_prefs():
    """Remove primary-colored bottom inject and place muted link in body."""
    body = (
        '<td style="padding:28px;"><p>Hi</p>'
        '<p style="font-size:13px;color:#6b6560;">Questions about this decision? '
        "Contact us at billing@voxbulk.com</p></td>"
        '<td style="padding:16px 28px 24px;border-top:1px solid #e5e0d8;">'
        "Sent by VOXBULK"
        '<p style="margin:16px 0 0;"><a href="https://x" style="color:#1a2d5c;">'
        "Manage Email Preferences</a></p></td>"
    )
    out = inject_email_preferences_footer(body)
    assert out.count("Manage Email Preferences") == 1
    contact_at = out.find("Questions about this decision?")
    prefs_at = out.find("Manage Email Preferences")
    border_at = out.find("border-top:1px solid")
    assert contact_at < prefs_at < border_at


def test_inject_upgrades_legacy_email_preferences_label():
    body = '<p><a href="https://dashboard.voxbulk.com/settings/team">Email preferences</a></p>'
    out = inject_email_preferences_footer(body)
    assert "Manage Email Preferences" in out
    assert "Email preferences" not in out
    assert out.count("Manage Email Preferences") == 1


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
