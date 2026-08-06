"""Manage private assistant conversations, messages, and feedback."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.assistant_help import (
    AssistantConversation,
    AssistantFaqSuggestion,
    AssistantHelpChunk,
    AssistantMessage,
    AssistantMessageFeedback,
)
from app.models.faq import FAQItem
from app.models.support_kb import SupportKbArticle

logger = logging.getLogger(__name__)


def create_conversation(db: Session, org_id: str, user_id: str, title: str = "New conversation") -> AssistantConversation:
    """Create a new private conversation."""
    conversation = AssistantConversation(
        id=str(uuid.uuid4()),
        org_id=org_id,
        user_id=user_id,
        title=title,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def get_conversation(db: Session, conversation_id: str, user_id: str) -> AssistantConversation | None:
    """Get conversation (private check: must be user's own)."""
    return db.query(AssistantConversation).filter(
        AssistantConversation.id == conversation_id,
        AssistantConversation.user_id == user_id,
    ).first()


def list_conversations(db: Session, org_id: str, user_id: str, limit: int = 50) -> list[AssistantConversation]:
    """List user's conversations (most recent first)."""
    return db.query(AssistantConversation).filter(
        AssistantConversation.org_id == org_id,
        AssistantConversation.user_id == user_id,
    ).order_by(AssistantConversation.updated_at.desc()).limit(limit).all()


def delete_conversation(db: Session, conversation_id: str, user_id: str) -> bool:
    """Delete conversation (cascade deletes messages and feedback)."""
    conversation = get_conversation(db, conversation_id, user_id)
    if not conversation:
        return False
    db.delete(conversation)
    db.commit()
    return True


def append_message(
    db: Session,
    conversation_id: str,
    role: str,
    content: str,
    source_type: str | None = None,
    sources: list[dict[str, Any]] | None = None,
) -> AssistantMessage:
    """Append message to conversation."""
    sources_json = json.dumps(sources) if sources else None
    message = AssistantMessage(
        id=str(uuid.uuid4()),
        conversation_id=conversation_id,
        role=role,
        content=content,
        source_type=source_type,
        sources_json=sources_json,
    )
    db.add(message)
    
    # Update conversation updated_at
    conversation = db.query(AssistantConversation).filter(
        AssistantConversation.id == conversation_id
    ).first()
    if conversation:
        conversation.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(message)
    return message


def get_messages(db: Session, conversation_id: str, limit: int = 100) -> list[AssistantMessage]:
    """Get messages in conversation (oldest first)."""
    return db.query(AssistantMessage).filter(
        AssistantMessage.conversation_id == conversation_id
    ).order_by(AssistantMessage.created_at.asc()).limit(limit).all()


def add_feedback(
    db: Session,
    message_id: str,
    user_id: str,
    rating: str,
) -> AssistantMessageFeedback:
    """
    Add or update thumbs up/down feedback.
    Increments helpful_count or unhelpful_count on cited sources.
    Creates FAQ suggestion on thumbs down.
    """
    # Check existing feedback
    existing = db.query(AssistantMessageFeedback).filter(
        AssistantMessageFeedback.message_id == message_id,
        AssistantMessageFeedback.user_id == user_id,
    ).first()
    
    if existing:
        old_rating = existing.rating
        existing.rating = rating
        feedback = existing
    else:
        feedback = AssistantMessageFeedback(
            id=str(uuid.uuid4()),
            message_id=message_id,
            user_id=user_id,
            rating=rating,
        )
        db.add(feedback)
        old_rating = None
    
    db.commit()
    
    # Update counters on sources
    message = db.query(AssistantMessage).filter(
        AssistantMessage.id == message_id
    ).first()
    
    if message and message.sources_json:
        try:
            sources = json.loads(message.sources_json)
            if isinstance(sources, list):
                for src in sources:
                    _update_source_counters(db, src, old_rating, rating)
        except Exception:
            logger.warning("Failed to update source counters", exc_info=True)
    
    # Create FAQ suggestion on thumbs down
    if rating == "down" and message:
        _create_faq_suggestion(db, message, user_id)
    
    db.refresh(feedback)
    return feedback


def _update_source_counters(db: Session, source: dict, old_rating: str | None, new_rating: str) -> None:
    """Update helpful/unhelpful counters on source (help_chunk, FAQ, KB)."""
    kind = source.get("kind")
    source_id = source.get("source_id")
    if not kind or not source_id:
        return
    
    # Decrement old rating
    if old_rating == "up":
        _decrement_helpful(db, kind, source_id)
    elif old_rating == "down":
        _decrement_unhelpful(db, kind, source_id)
    
    # Increment new rating
    if new_rating == "up":
        _increment_helpful(db, kind, source_id)
    elif new_rating == "down":
        _increment_unhelpful(db, kind, source_id)


def _increment_helpful(db: Session, kind: str, source_id: str) -> None:
    """Increment helpful_count on source."""
    if kind == "builtin" or kind == "faq" or kind == "kb":
        chunk = db.query(AssistantHelpChunk).filter(
            AssistantHelpChunk.source_kind == kind,
            AssistantHelpChunk.source_id == source_id,
        ).first()
        if chunk:
            chunk.helpful_count += 1
    
    if kind == "faq":
        faq_id_str = source_id.replace("faq-", "")
        try:
            faq_id = int(faq_id_str)
            faq = db.query(FAQItem).filter(FAQItem.id == faq_id).first()
            if faq:
                faq.helpful_count += 1
        except ValueError:
            pass
    
    if kind == "kb":
        kb_id_str = source_id.replace("kb-", "")
        try:
            kb_id = int(kb_id_str)
            kb = db.query(SupportKbArticle).filter(SupportKbArticle.id == kb_id).first()
            if kb:
                kb.helpful_count += 1
        except ValueError:
            pass
    
    db.commit()


def _increment_unhelpful(db: Session, kind: str, source_id: str) -> None:
    """Increment unhelpful_count on source."""
    if kind == "builtin" or kind == "faq" or kind == "kb":
        chunk = db.query(AssistantHelpChunk).filter(
            AssistantHelpChunk.source_kind == kind,
            AssistantHelpChunk.source_id == source_id,
        ).first()
        if chunk:
            chunk.unhelpful_count += 1
    
    if kind == "faq":
        faq_id_str = source_id.replace("faq-", "")
        try:
            faq_id = int(faq_id_str)
            faq = db.query(FAQItem).filter(FAQItem.id == faq_id).first()
            if faq:
                faq.unhelpful_count += 1
        except ValueError:
            pass
    
    if kind == "kb":
        kb_id_str = source_id.replace("kb-", "")
        try:
            kb_id = int(kb_id_str)
            kb = db.query(SupportKbArticle).filter(SupportKbArticle.id == kb_id).first()
            if kb:
                kb.unhelpful_count += 1
        except ValueError:
            pass
    
    db.commit()


def _decrement_helpful(db: Session, kind: str, source_id: str) -> None:
    """Decrement helpful_count on source (when user changes from up to down)."""
    if kind == "builtin" or kind == "faq" or kind == "kb":
        chunk = db.query(AssistantHelpChunk).filter(
            AssistantHelpChunk.source_kind == kind,
            AssistantHelpChunk.source_id == source_id,
        ).first()
        if chunk and chunk.helpful_count > 0:
            chunk.helpful_count -= 1
    
    if kind == "faq":
        faq_id_str = source_id.replace("faq-", "")
        try:
            faq_id = int(faq_id_str)
            faq = db.query(FAQItem).filter(FAQItem.id == faq_id).first()
            if faq and faq.helpful_count > 0:
                faq.helpful_count -= 1
        except ValueError:
            pass
    
    if kind == "kb":
        kb_id_str = source_id.replace("kb-", "")
        try:
            kb_id = int(kb_id_str)
            kb = db.query(SupportKbArticle).filter(SupportKbArticle.id == kb_id).first()
            if kb and kb.helpful_count > 0:
                kb.helpful_count -= 1
        except ValueError:
            pass
    
    db.commit()


def _decrement_unhelpful(db: Session, kind: str, source_id: str) -> None:
    """Decrement unhelpful_count on source (when user changes from down to up)."""
    if kind == "builtin" or kind == "faq" or kind == "kb":
        chunk = db.query(AssistantHelpChunk).filter(
            AssistantHelpChunk.source_kind == kind,
            AssistantHelpChunk.source_id == source_id,
        ).first()
        if chunk and chunk.unhelpful_count > 0:
            chunk.unhelpful_count -= 1
    
    if kind == "faq":
        faq_id_str = source_id.replace("faq-", "")
        try:
            faq_id = int(faq_id_str)
            faq = db.query(FAQItem).filter(FAQItem.id == faq_id).first()
            if faq and faq.unhelpful_count > 0:
                faq.unhelpful_count -= 1
        except ValueError:
            pass
    
    if kind == "kb":
        kb_id_str = source_id.replace("kb-", "")
        try:
            kb_id = int(kb_id_str)
            kb = db.query(SupportKbArticle).filter(SupportKbArticle.id == kb_id).first()
            if kb and kb.unhelpful_count > 0:
                kb.unhelpful_count -= 1
        except ValueError:
            pass
    
    db.commit()


def _create_faq_suggestion(db: Session, message: AssistantMessage, user_id: str) -> None:
    """Create FAQ suggestion from thumbs-down message."""
    conversation = db.query(AssistantConversation).filter(
        AssistantConversation.id == message.conversation_id
    ).first()
    
    if not conversation:
        return
    
    # Find user question (previous message in conversation)
    prev_messages = db.query(AssistantMessage).filter(
        AssistantMessage.conversation_id == message.conversation_id,
        AssistantMessage.role == "user",
        AssistantMessage.created_at < message.created_at,
    ).order_by(AssistantMessage.created_at.desc()).limit(1).all()
    
    question = prev_messages[0].content if prev_messages else "User question not found"
    
    suggestion = AssistantFaqSuggestion(
        id=str(uuid.uuid4()),
        question=question[:2000],
        sample_answer=message.content[:2000],
        org_id=conversation.org_id,
        user_id=user_id,
        status="pending",
    )
    db.add(suggestion)
    db.commit()


def list_suggestions(db: Session, status: str | None = None, limit: int = 100) -> list[AssistantFaqSuggestion]:
    """List FAQ suggestions (admin)."""
    query = db.query(AssistantFaqSuggestion)
    if status:
        query = query.filter(AssistantFaqSuggestion.status == status)
    return query.order_by(AssistantFaqSuggestion.created_at.desc()).limit(limit).all()


def update_suggestion_status(db: Session, suggestion_id: str, status: str) -> AssistantFaqSuggestion | None:
    """Update suggestion status (admin)."""
    suggestion = db.query(AssistantFaqSuggestion).filter(
        AssistantFaqSuggestion.id == suggestion_id
    ).first()
    if not suggestion:
        return None
    suggestion.status = status
    suggestion.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(suggestion)
    return suggestion


def set_suggestion_status(db: Session, suggestion_id: str, status: str) -> AssistantFaqSuggestion | None:
    return update_suggestion_status(db, suggestion_id, status)


def record_feedback(
    db: Session,
    *,
    message_id: str,
    user_id: str,
    org_id: str,
    rating: str,
) -> dict[str, Any]:
    """Validate ownership then record thumbs feedback."""
    message = db.query(AssistantMessage).filter(AssistantMessage.id == message_id).first()
    if message is None:
        raise ValueError("Message not found")
    conversation = db.query(AssistantConversation).filter(
        AssistantConversation.id == message.conversation_id,
        AssistantConversation.user_id == user_id,
        AssistantConversation.org_id == org_id,
    ).first()
    if conversation is None:
        raise ValueError("Message not found")
    feedback = add_feedback(db, message_id, user_id, rating)
    return {"ok": True, "rating": feedback.rating, "message_id": message_id}


def insights_summary(db: Session) -> dict[str, Any]:
    """Aggregate Ask AI metrics for Admin insights."""
    from sqlalchemy import func

    from app.models.assistant_help import AssistantMessageFeedback

    total_questions = (
        db.query(func.count(AssistantMessage.id))
        .filter(AssistantMessage.role == "user")
        .scalar()
        or 0
    )
    kb_hits = (
        db.query(func.count(AssistantMessage.id))
        .filter(AssistantMessage.role == "assistant", AssistantMessage.source_type == "knowledge_base")
        .scalar()
        or 0
    )
    general_ai = (
        db.query(func.count(AssistantMessage.id))
        .filter(AssistantMessage.role == "assistant", AssistantMessage.source_type == "general_ai")
        .scalar()
        or 0
    )
    thumbs_up = (
        db.query(func.count(AssistantMessageFeedback.id))
        .filter(AssistantMessageFeedback.rating == "up")
        .scalar()
        or 0
    )
    thumbs_down = (
        db.query(func.count(AssistantMessageFeedback.id))
        .filter(AssistantMessageFeedback.rating == "down")
        .scalar()
        or 0
    )
    return {
        "total_questions": int(total_questions),
        "kb_hits": int(kb_hits),
        "general_ai": int(general_ai),
        "thumbs_up": int(thumbs_up),
        "thumbs_down": int(thumbs_down),
        "avg_latency_ms": 0.0,
    }


def enqueue_faq_suggestion(
    db: Session,
    *,
    question: str,
    sample_answer: str,
    org_id: str | None,
    user_id: str | None,
) -> AssistantFaqSuggestion:
    suggestion = AssistantFaqSuggestion(
        id=str(uuid.uuid4()),
        question=(question or "")[:2000],
        sample_answer=(sample_answer or "")[:2000],
        org_id=org_id,
        user_id=user_id,
        status="pending",
    )
    db.add(suggestion)
    db.commit()
    db.refresh(suggestion)
    return suggestion
