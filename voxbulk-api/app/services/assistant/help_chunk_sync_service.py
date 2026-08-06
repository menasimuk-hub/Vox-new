"""Sync builtin help, FAQ, and KB articles into assistant_help_chunks for RAG."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.data.assistant_builtin_help import BUILTIN_HELP_ARTICLES
from app.models.assistant_help import AssistantHelpChunk
from app.models.faq import FAQItem
from app.models.support_kb import SupportKbArticle

logger = logging.getLogger(__name__)


def ensure_builtin_chunks(db: Session) -> dict[str, int]:
    """Ensure builtin help articles are synced into help_chunks (insert or update)."""
    created = 0
    updated = 0
    for article in BUILTIN_HELP_ARTICLES:
        source_id = article["source_id"]
        existing = db.query(AssistantHelpChunk).filter(
            AssistantHelpChunk.source_kind == "builtin",
            AssistantHelpChunk.source_id == source_id,
        ).first()
        
        route_hints = json.dumps(article["routes"]) if article["routes"] else None
        
        if existing:
            existing.title = article["title"]
            existing.body = article["body"]
            existing.service_key = article["service_key"]
            existing.category_id = article["category_id"]
            existing.route_hints_json = route_hints
            existing.is_active = True
            existing.updated_at = datetime.utcnow()
            updated += 1
        else:
            chunk = AssistantHelpChunk(
                id=str(uuid.uuid4()),
                source_kind="builtin",
                source_id=source_id,
                category_id=article["category_id"],
                service_key=article["service_key"],
                title=article["title"],
                body=article["body"],
                route_hints_json=route_hints,
                is_active=True,
            )
            db.add(chunk)
            created += 1
    
    db.commit()
    return {"created": created, "updated": updated}


def sync_faq_and_kb_chunks(db: Session) -> dict[str, int]:
    """Sync published dashboard FAQ items and KB articles into help_chunks."""
    faq_synced = 0
    kb_synced = 0
    active_faq_ids: set[str] = set()
    active_kb_ids: set[str] = set()

    faq_items = db.query(FAQItem).filter(
        FAQItem.surface == "dashboard",
        FAQItem.is_published == True,  # noqa: E712
    ).all()

    for faq in faq_items:
        source_id = f"faq-{faq.id}"
        active_faq_ids.add(source_id)
        existing = db.query(AssistantHelpChunk).filter(
            AssistantHelpChunk.source_kind == "faq",
            AssistantHelpChunk.source_id == source_id,
        ).first()

        category = str(faq.category_id) if faq.category_id else None
        service_key = faq.linked_service or None
        title = faq.question[:500]
        body = faq.answer

        if existing:
            existing.title = title
            existing.body = body
            existing.category_id = category
            existing.service_key = service_key
            existing.is_active = True
            existing.updated_at = datetime.utcnow()
        else:
            chunk = AssistantHelpChunk(
                id=str(uuid.uuid4()),
                source_kind="faq",
                source_id=source_id,
                category_id=category,
                service_key=service_key,
                title=title,
                body=body,
                is_active=True,
            )
            db.add(chunk)
        faq_synced += 1

    kb_articles = db.query(SupportKbArticle).filter(
        SupportKbArticle.state == "published",
    ).all()

    for kb in kb_articles:
        source_id = f"kb-{kb.id}"
        active_kb_ids.add(source_id)
        existing = db.query(AssistantHelpChunk).filter(
            AssistantHelpChunk.source_kind == "kb",
            AssistantHelpChunk.source_id == source_id,
        ).first()

        category = str(kb.category_id) if kb.category_id else None
        service_key = kb.linked_service or None
        title = kb.title
        body = kb.body

        if existing:
            existing.title = title
            existing.body = body
            existing.category_id = category
            existing.service_key = service_key
            existing.is_active = True
            existing.updated_at = datetime.utcnow()
        else:
            chunk = AssistantHelpChunk(
                id=str(uuid.uuid4()),
                source_kind="kb",
                source_id=source_id,
                category_id=category,
                service_key=service_key,
                title=title,
                body=body,
                is_active=True,
            )
            db.add(chunk)
        kb_synced += 1

    # Deactivate unpublished / removed FAQ & KB chunks
    for stale in db.query(AssistantHelpChunk).filter(AssistantHelpChunk.source_kind == "faq").all():
        if stale.source_id not in active_faq_ids and stale.is_active:
            stale.is_active = False
            stale.updated_at = datetime.utcnow()
    for stale in db.query(AssistantHelpChunk).filter(AssistantHelpChunk.source_kind == "kb").all():
        if stale.source_id not in active_kb_ids and stale.is_active:
            stale.is_active = False
            stale.updated_at = datetime.utcnow()

    db.commit()
    return {"faq": faq_synced, "kb": kb_synced}


def rebuild_all(db: Session) -> dict[str, int | dict]:
    """Full rebuild: builtin + FAQ + KB."""
    builtin_result = ensure_builtin_chunks(db)
    sync_result = sync_faq_and_kb_chunks(db)
    return {
        "builtin": builtin_result,
        "faq": sync_result["faq"],
        "kb": sync_result["kb"],
    }
