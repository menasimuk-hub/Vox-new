"""Seed expansion: 15 restaurants in one city + 4 drivers."""

from __future__ import annotations

from alembic import op
from sqlalchemy.orm import Session

revision = "0005_abuu_seed_city"
down_revision = "0004_abuu_phase6_ops"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.abuu.services.seed_service import AbuuSeedService

    bind = op.get_bind()
    db = Session(bind=bind)
    try:
        AbuuSeedService.seed_city_expansion(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def downgrade() -> None:
    pass
