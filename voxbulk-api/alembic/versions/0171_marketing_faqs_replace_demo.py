"""0171 — Replace demo support FAQs with marketing frontpage FAQs.

Revision ID: 0171_marketing_faqs_replace_demo
Revises: 0170_seo_marketing_pages
"""

from __future__ import annotations

from alembic import op

revision = "0171_marketing_faqs_replace_demo"
down_revision = "0170_seo_marketing_pages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Data-only: run ensure via SQLAlchemy session after schema is current.
    # Import inside upgrade so Alembic env path resolves app package.
    from sqlalchemy.orm import Session

    from app.services.faq_service import FAQService

    bind = op.get_bind()
    with Session(bind=bind) as db:
        FAQService.ensure_marketing_faqs(db)


def downgrade() -> None:
    # Non-destructive: leave marketing FAQs in place.
    pass
