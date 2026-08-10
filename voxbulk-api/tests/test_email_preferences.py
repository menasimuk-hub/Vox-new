"""Email notification preferences — catalog, gating, footer inject."""

from __future__ import annotations

from app.data.brand_email_layout import inject_email_preferences_footer, wrap_brand_email
from app.services.email_preference_service import EmailPreferenceService, EMAIL_PREF_KEYS


def test_wrap_brand_email_includes_manage_preferences_link():
    html = wrap_brand_email(title="Test", inner_html="<p>Hello</p>")
    assert "Manage Email Preferences" in html
    assert "settings/profile#email-notifications" in html


def test_inject_email_preferences_footer_once():
    body = "<html><body><p>Hi</p></body></html>"
    once = inject_email_preferences_footer(body)
    assert once.count("Manage Email Preferences") == 1
    twice = inject_email_preferences_footer(once)
    assert twice.count("Manage Email Preferences") == 1


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
