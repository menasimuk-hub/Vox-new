"""Seed four bilingual restaurants with full menus."""

from __future__ import annotations

from alembic import op
from sqlalchemy.orm import Session

revision = "0003_abuu_seed_restaurants"
down_revision = "0002_abuu_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.abuu.services.seed_service import AbuuSeedService

    bind = op.get_bind()
    db = Session(bind=bind)
    try:
        AbuuSeedService.seed_restaurants_if_empty(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        __import__("sqlalchemy").text(
            "DELETE FROM abuu_menu_items; DELETE FROM abuu_menu_categories; DELETE FROM abuu_restaurants;"
        )
    )
