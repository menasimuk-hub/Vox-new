from app.core.database import get_sessionmaker
from app.data.brand_email_layout import inject_brand_tagline, wrap_brand_email
from app.data.weekly_digest_email_default import WEEKLY_DIGEST_BODY
from app.services.brand_assets import BRAND_TAGLINE
from app.services.email_template_service import EMAIL_TEMPLATE_KEYS, EmailTemplateService


def test_wrap_brand_email_includes_tagline():
    html = wrap_brand_email(title="Test", inner_html="<p>Hello</p>")
    assert BRAND_TAGLINE in html


def test_inject_brand_tagline_inserts_once():
    base = '<a href="#"><img alt="VOXBULK" /></a><p>Body</p>'
    patched = inject_brand_tagline(base)
    assert patched is not None
    assert patched.count(BRAND_TAGLINE) == 1
    assert inject_brand_tagline(patched) is None


def test_weekly_digest_default_is_company_neutral():
    assert "{{organisation_name}}" in WEEKLY_DIGEST_BODY
    assert "Recovery queue" not in WEEKLY_DIGEST_BODY
    assert "interviews_recommended_percent" not in WEEKLY_DIGEST_BODY
    assert BRAND_TAGLINE in WEEKLY_DIGEST_BODY


def test_ensure_system_templates_includes_sales_offer():
    with get_sessionmaker()() as db:
        EmailTemplateService.ensure_system_templates(db)
        row = EmailTemplateService.get(db, key="sales_offer")
        assert row is not None
        assert row.template_key == "sales_offer"
        assert "{{first_name}}" in (row.body or "")
        assert 'alt="VOXBULK"' in (row.body or "")
        assert BRAND_TAGLINE in (row.body or "")
        assert "sales_offer" in EMAIL_TEMPLATE_KEYS

        digest = EmailTemplateService.get(db, key="weekly_digest")
        assert digest is not None
        assert "{{organisation_name}}" in (digest.body or "")
        assert "Recovery queue" not in (digest.body or "")
