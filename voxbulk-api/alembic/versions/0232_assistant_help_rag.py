"""Add assistant help RAG tables and counters.

Revision ID: 0232_assistant_help_rag
Revises: 0231_support_content_product_keys
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0232_assistant_help_rag"
down_revision = "0231_support_content_product_keys"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def _index_exists(table: str, index_name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return any(idx["name"] == index_name for idx in insp.get_indexes(table))


def _create_fulltext_index_mysql(table: str, index_name: str, *columns: str) -> None:
    """Create MySQL FULLTEXT index, skip on SQLite."""
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect != "mysql":
        return
    if _index_exists(table, index_name):
        return
    try:
        cols = ", ".join(columns)
        op.execute(sa.text(f"CREATE FULLTEXT INDEX {index_name} ON {table}({cols})"))
    except Exception:
        pass


def upgrade() -> None:
    # assistant_help_chunks
    if not _table_exists("assistant_help_chunks"):
        op.create_table(
            "assistant_help_chunks",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("source_kind", sa.String(32), nullable=False, index=True),
            sa.Column("source_id", sa.String(64), nullable=False, index=True),
            sa.Column("category_id", sa.String(64), nullable=True, index=True),
            sa.Column("service_key", sa.String(64), nullable=True, index=True),
            sa.Column("title", sa.Text, nullable=False),
            sa.Column("body", sa.Text, nullable=False),
            sa.Column("route_hints_json", sa.Text, nullable=True),
            sa.Column("is_active", sa.Boolean, nullable=False, default=True, index=True),
            sa.Column("usage_count", sa.Integer, nullable=False, default=0),
            sa.Column("helpful_count", sa.Integer, nullable=False, default=0),
            sa.Column("unhelpful_count", sa.Integer, nullable=False, default=0),
            sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
            sa.UniqueConstraint("source_kind", "source_id", name="uq_help_chunk_source"),
        )
    _create_fulltext_index_mysql("assistant_help_chunks", "ft_help_chunk_title_body", "title", "body")

    # assistant_conversations
    if not _table_exists("assistant_conversations"):
        op.create_table(
            "assistant_conversations",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("org_id", sa.String(36), nullable=False, index=True),
            sa.Column("user_id", sa.String(36), nullable=False, index=True),
            sa.Column("title", sa.String(500), nullable=False, default="New conversation"),
            sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now(), index=True),
            sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    # assistant_messages
    if not _table_exists("assistant_messages"):
        op.create_table(
            "assistant_messages",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("conversation_id", sa.String(36), sa.ForeignKey("assistant_conversations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("role", sa.String(20), nullable=False),
            sa.Column("content", sa.Text, nullable=False),
            sa.Column("source_type", sa.String(32), nullable=True, index=True),
            sa.Column("sources_json", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now(), index=True),
        )

    # assistant_message_feedback
    if not _table_exists("assistant_message_feedback"):
        op.create_table(
            "assistant_message_feedback",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("message_id", sa.String(36), sa.ForeignKey("assistant_messages.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("user_id", sa.String(36), nullable=False, index=True),
            sa.Column("rating", sa.String(10), nullable=False),
            sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("message_id", "user_id", name="uq_message_feedback_user"),
        )

    # assistant_faq_suggestions
    if not _table_exists("assistant_faq_suggestions"):
        op.create_table(
            "assistant_faq_suggestions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("question", sa.Text, nullable=False),
            sa.Column("sample_answer", sa.Text, nullable=False),
            sa.Column("org_id", sa.String(36), nullable=True, index=True),
            sa.Column("user_id", sa.String(36), nullable=True, index=True),
            sa.Column("status", sa.String(20), nullable=False, default="pending", index=True),
            sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now(), index=True),
            sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        )

    # assistant_chat_metrics_daily
    if not _table_exists("assistant_chat_metrics_daily"):
        op.create_table(
            "assistant_chat_metrics_daily",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("day", sa.Date, nullable=False, index=True, unique=True),
            sa.Column("questions", sa.Integer, nullable=False, default=0),
            sa.Column("kb_hits", sa.Integer, nullable=False, default=0),
            sa.Column("general_ai", sa.Integer, nullable=False, default=0),
            sa.Column("thumbs_up", sa.Integer, nullable=False, default=0),
            sa.Column("thumbs_down", sa.Integer, nullable=False, default=0),
            sa.Column("latency_ms_sum", sa.Integer, nullable=False, default=0),
            sa.Column("latency_ms_count", sa.Integer, nullable=False, default=0),
        )

    # Add counters to faq_items
    if not _column_exists("faq_items", "usage_count"):
        op.add_column("faq_items", sa.Column("usage_count", sa.Integer, nullable=False, server_default="0"))
    if not _column_exists("faq_items", "helpful_count"):
        op.add_column("faq_items", sa.Column("helpful_count", sa.Integer, nullable=False, server_default="0"))
    if not _column_exists("faq_items", "unhelpful_count"):
        op.add_column("faq_items", sa.Column("unhelpful_count", sa.Integer, nullable=False, server_default="0"))
    _create_fulltext_index_mysql("faq_items", "ft_faq_question_answer", "question", "answer")

    # Add counters to support_kb_articles
    if not _column_exists("support_kb_articles", "usage_count"):
        op.add_column("support_kb_articles", sa.Column("usage_count", sa.Integer, nullable=False, server_default="0"))
    if not _column_exists("support_kb_articles", "helpful_count"):
        op.add_column("support_kb_articles", sa.Column("helpful_count", sa.Integer, nullable=False, server_default="0"))
    if not _column_exists("support_kb_articles", "unhelpful_count"):
        op.add_column("support_kb_articles", sa.Column("unhelpful_count", sa.Integer, nullable=False, server_default="0"))
    _create_fulltext_index_mysql("support_kb_articles", "ft_kb_title_body", "title", "body")


def downgrade() -> None:
    # Drop counters from support_kb_articles
    if _column_exists("support_kb_articles", "unhelpful_count"):
        op.drop_column("support_kb_articles", "unhelpful_count")
    if _column_exists("support_kb_articles", "helpful_count"):
        op.drop_column("support_kb_articles", "helpful_count")
    if _column_exists("support_kb_articles", "usage_count"):
        op.drop_column("support_kb_articles", "usage_count")

    # Drop counters from faq_items
    if _column_exists("faq_items", "unhelpful_count"):
        op.drop_column("faq_items", "unhelpful_count")
    if _column_exists("faq_items", "helpful_count"):
        op.drop_column("faq_items", "helpful_count")
    if _column_exists("faq_items", "usage_count"):
        op.drop_column("faq_items", "usage_count")

    # Drop tables
    if _table_exists("assistant_chat_metrics_daily"):
        op.drop_table("assistant_chat_metrics_daily")
    if _table_exists("assistant_faq_suggestions"):
        op.drop_table("assistant_faq_suggestions")
    if _table_exists("assistant_message_feedback"):
        op.drop_table("assistant_message_feedback")
    if _table_exists("assistant_messages"):
        op.drop_table("assistant_messages")
    if _table_exists("assistant_conversations"):
        op.drop_table("assistant_conversations")
    if _table_exists("assistant_help_chunks"):
        op.drop_table("assistant_help_chunks")
