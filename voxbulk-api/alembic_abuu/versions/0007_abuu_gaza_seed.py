"""Gaza Strip seed relocation for Abuu production."""

from __future__ import annotations

from alembic import op
from sqlalchemy.orm import Session

revision = "0007_abuu_gaza_seed"
down_revision = "0006_abuu_phase7_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.abuu.services.seed_service import AbuuSeedService

    bind = op.get_bind()
    db = Session(bind=bind)
    try:
        AbuuSeedService.seed_gaza_relocation(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def downgrade() -> None:
    pass
