"""Tests for assistant help RAG: retrieval, feedback, conversation privacy."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.database import get_sessionmaker
from app.models.assistant_help import AssistantHelpChunk
from app.services.assistant import conversation_service, help_chunk_sync_service, help_retrieval_service


def _db() -> Session:
    return get_sessionmaker()()


def test_builtin_chunks_sync():
    db = _db()
    try:
        result = help_chunk_sync_service.ensure_builtin_chunks(db)
        assert result["created"] + result["updated"] > 0
        chunk = db.query(AssistantHelpChunk).filter(AssistantHelpChunk.source_kind == "builtin").first()
        assert chunk is not None
        assert chunk.title
        assert chunk.body
    finally:
        db.close()


def test_retrieval_visibility_filter():
    db = _db()
    try:
        help_chunk_sync_service.ensure_builtin_chunks(db)
        results_no_service = help_retrieval_service.retrieve(
            db, question="billing", enabled_services=None, limit=10
        )
        for r in results_no_service:
            chunk = db.query(AssistantHelpChunk).filter(AssistantHelpChunk.id == r["id"]).first()
            assert chunk is not None
            assert chunk.service_key is None or chunk.service_key == ""

        results_with_services = help_retrieval_service.retrieve(
            db, question="survey", enabled_services=["surveys", "interviews"], limit=10
        )
        assert len(results_with_services) > 0
    finally:
        db.close()


def test_retrieve_hits_relevant_content():
    db = _db()
    try:
        help_chunk_sync_service.ensure_builtin_chunks(db)
        results = help_retrieval_service.retrieve(
            db, question="How do I view my billing invoices?", enabled_services=None, limit=5
        )
        assert len(results) > 0
        assert any("billing" in r["title"].lower() or "invoice" in r["title"].lower() for r in results)
    finally:
        db.close()


def test_no_hit_general_query():
    db = _db()
    try:
        help_chunk_sync_service.ensure_builtin_chunks(db)
        results = help_retrieval_service.retrieve(
            db, question="xyz nonsense query 12345", enabled_services=None, limit=5
        )
        assert isinstance(results, list)
    finally:
        db.close()


def test_private_conversation_404_for_other_user():
    db = _db()
    try:
        org_id = "org-123"
        user_a = "user-a"
        user_b = "user-b"
        conv = conversation_service.create_conversation(db, org_id, user_a, title="User A conv")
        assert conversation_service.get_conversation(db, conv.id, user_a) is not None
        assert conversation_service.get_conversation(db, conv.id, user_b) is None
    finally:
        db.close()


def test_feedback_increments_counters():
    db = _db()
    try:
        help_chunk_sync_service.ensure_builtin_chunks(db)
        chunk = db.query(AssistantHelpChunk).filter(AssistantHelpChunk.source_kind == "builtin").first()
        assert chunk is not None
        initial_helpful = chunk.helpful_count
        initial_unhelpful = chunk.unhelpful_count
        conv = conversation_service.create_conversation(db, "org-456", "user-123", title="Test")
        msg = conversation_service.append_message(
            db,
            conv.id,
            "assistant",
            "Test answer",
            source_type="knowledge_base",
            sources=[
                {
                    "id": chunk.id,
                    "kind": chunk.source_kind,
                    "source_id": chunk.source_id,
                    "title": chunk.title,
                    "url": "/",
                }
            ],
        )
        conversation_service.add_feedback(db, msg.id, "user-123", "up")
        db.refresh(chunk)
        assert chunk.helpful_count == initial_helpful + 1
        conversation_service.add_feedback(db, msg.id, "user-123", "down")
        db.refresh(chunk)
        assert chunk.helpful_count == initial_helpful
        assert chunk.unhelpful_count == initial_unhelpful + 1
    finally:
        db.close()


def test_conversation_list_and_delete():
    db = _db()
    try:
        org_id = "org-789"
        user_id = "user-789"
        conv1 = conversation_service.create_conversation(db, org_id, user_id, title="First")
        conversation_service.create_conversation(db, org_id, user_id, title="Second")
        convs = conversation_service.list_conversations(db, org_id, user_id, limit=10)
        assert len(convs) >= 2
        assert conversation_service.delete_conversation(db, conv1.id, user_id) is True
        assert conversation_service.get_conversation(db, conv1.id, user_id) is None
    finally:
        db.close()


def test_insights_summary_shape():
    db = _db()
    try:
        data = conversation_service.insights_summary(db)
        assert set(data.keys()) >= {
            "total_questions",
            "kb_hits",
            "general_ai",
            "thumbs_up",
            "thumbs_down",
            "avg_latency_ms",
        }
    finally:
        db.close()
