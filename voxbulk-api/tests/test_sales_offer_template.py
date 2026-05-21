from app.core.database import get_sessionmaker
from app.services.email_template_service import EMAIL_TEMPLATE_KEYS, EmailTemplateService


def test_ensure_system_templates_includes_sales_offer():
    with get_sessionmaker()() as db:
        EmailTemplateService.ensure_system_templates(db)
        row = EmailTemplateService.get(db, key="sales_offer")
        assert row is not None
        assert row.template_key == "sales_offer"
        assert "{{first_name}}" in (row.body or "")
        assert "sales_offer" in EMAIL_TEMPLATE_KEYS
