"""0156 — feedback_wa_templates.meta_template_name (stored CFS template name)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0156_feedback_meta_template_name"
down_revision = "0155_custom_org_profiles"
branch_labels = None
depends_on = None

_TABLE = "feedback_wa_templates"
_COLUMN = "meta_template_name"
_INDEX = "ix_feedback_wa_templates_meta_template_name"


def _has_column(bind) -> bool:
    insp = sa.inspect(bind)
    return _COLUMN in {c["name"] for c in insp.get_columns(_TABLE)}


def _has_index(bind) -> bool:
    insp = sa.inspect(bind)
    return _INDEX in {i["name"] for i in insp.get_indexes(_TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind):
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(length=512), nullable=True))
    if not _has_index(bind):
        op.create_index(_INDEX, _TABLE, [_COLUMN])


def downgrade() -> None:
    bind = op.get_bind()
    if _has_index(bind):
        op.drop_index(_INDEX, table_name=_TABLE)
    if _has_column(bind):
        op.drop_column(_TABLE, _COLUMN)
