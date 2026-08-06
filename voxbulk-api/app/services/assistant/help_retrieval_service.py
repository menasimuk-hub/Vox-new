"""Retrieve relevant help chunks for assistant RAG queries."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.models.assistant_help import AssistantHelpChunk
from app.models.faq import FAQItem
from app.models.support_kb import SupportKbArticle

logger = logging.getLogger(__name__)

SERVICE_KEY_MAP = {
    "interviews": "interview",
    "surveys": "survey",
    "feedback": "customer_feedback",
    "expo": "expo",
    "smartCard": "smart_card",
    "campaigns": "campaigns",
    "feedbackCampaigns": "customer_feedback",
}


def _normalize_service_keys(enabled_services: list[str] | None) -> list[str]:
    if not enabled_services:
        return []
    normalized: list[str] = []
    for svc in enabled_services:
        mapped = SERVICE_KEY_MAP.get(svc, svc)
        if mapped and mapped not in normalized:
            normalized.append(mapped)
    return normalized


def _fulltext_search_mysql(db: Session, question: str, service_keys: list[str], limit: int) -> list[AssistantHelpChunk]:
    search_terms = re.sub(r"[^\w\s\-]", " ", question or "").strip()
    if not search_terms:
        return []
    # Prefer ORM FULLTEXT via ILIKE fallback path when binding IN lists is awkward;
    # use parameterized query with explicit OR for service keys.
    if service_keys:
        key_clauses = " OR ".join(f"service_key = :sk{i}" for i in range(len(service_keys)))
        vis_sql = f"(service_key IS NULL OR service_key = '' OR {key_clauses})"
        params: dict[str, Any] = {f"sk{i}": k for i, k in enumerate(service_keys)}
    else:
        vis_sql = "(service_key IS NULL OR service_key = '')"
        params = {}
    params.update({"q": search_terms, "lim": int(limit)})
    sql = text(
        f"""
        SELECT id FROM assistant_help_chunks
        WHERE is_active = 1
          AND {vis_sql}
          AND MATCH(title, body) AGAINST(:q IN NATURAL LANGUAGE MODE)
        ORDER BY MATCH(title, body) AGAINST(:q IN NATURAL LANGUAGE MODE) DESC
        LIMIT :lim
        """
    )
    try:
        rows = db.execute(sql, params).fetchall()
    except Exception as e:
        logger.warning("fulltext_search_mysql failed: %s", e)
        return []
    ids = [str(r[0]) for r in rows]
    if not ids:
        return []
    chunks = list(db.execute(select(AssistantHelpChunk).where(AssistantHelpChunk.id.in_(ids))).scalars().all())
    by_id = {c.id: c for c in chunks}
    return [by_id[i] for i in ids if i in by_id]


def _fallback_ilike_search(db: Session, question: str, service_keys: list[str], limit: int) -> list[AssistantHelpChunk]:
    terms = [t.strip().lower() for t in re.split(r"\s+", question or "") if len(t.strip()) > 2]
    if not terms:
        return []
    query = select(AssistantHelpChunk).where(AssistantHelpChunk.is_active.is_(True))
    if service_keys:
        query = query.where(
            or_(
                AssistantHelpChunk.service_key.is_(None),
                AssistantHelpChunk.service_key == "",
                AssistantHelpChunk.service_key.in_(service_keys),
            )
        )
    else:
        query = query.where(
            or_(AssistantHelpChunk.service_key.is_(None), AssistantHelpChunk.service_key == "")
        )
    term_filters = []
    for term in terms[:6]:
        term_filters.append(AssistantHelpChunk.title.ilike(f"%{term}%"))
        term_filters.append(AssistantHelpChunk.body.ilike(f"%{term}%"))
    if term_filters:
        query = query.where(or_(*term_filters))
    rows = list(db.execute(query.limit(limit * 3)).scalars().all())

    def score(chunk: AssistantHelpChunk) -> int:
        blob = f"{chunk.title}\n{chunk.body}".lower()
        return sum(1 for t in terms if t in blob)

    ranked = sorted(rows, key=score, reverse=True)
    return [c for c in ranked if score(c) > 0][:limit]


def increment_usage_count(db: Session, kind: str, source_id: str) -> None:
    chunk = db.execute(
        select(AssistantHelpChunk).where(
            AssistantHelpChunk.source_kind == kind,
            AssistantHelpChunk.source_id == source_id,
        )
    ).scalar_one_or_none()
    if chunk:
        chunk.usage_count = int(chunk.usage_count or 0) + 1
        db.add(chunk)

    if kind == "faq":
        faq_id_str = source_id.replace("faq-", "")
        try:
            faq = db.get(FAQItem, int(faq_id_str))
            if faq is not None:
                faq.usage_count = int(getattr(faq, "usage_count", 0) or 0) + 1
                db.add(faq)
        except ValueError:
            pass
    if kind == "kb":
        kb_id_str = source_id.replace("kb-", "")
        try:
            kb = db.get(SupportKbArticle, int(kb_id_str))
            if kb is not None:
                kb.usage_count = int(getattr(kb, "usage_count", 0) or 0) + 1
                db.add(kb)
        except ValueError:
            pass
    db.commit()


# Back-compat alias used by orchestrator
_increment_usage_count = increment_usage_count


def retrieve(
    db: Session,
    question: str,
    enabled_services: list[str] | None = None,
    limit: int = 5,
    min_score: float = 0.0,
) -> list[dict[str, Any]]:
    """Return top N help hits: id, kind, title, snippet, url, source_id, score."""
    from app.services.assistant.help_chunk_sync_service import ensure_builtin_chunks

    try:
        ensure_builtin_chunks(db)
    except Exception:
        logger.debug("ensure_builtin_chunks skipped", exc_info=True)

    service_keys = _normalize_service_keys(enabled_services)
    bind = db.get_bind()
    dialect = bind.dialect.name
    chunks: list[AssistantHelpChunk] = []
    if dialect == "mysql":
        chunks = _fulltext_search_mysql(db, question, service_keys, limit)
    if not chunks:
        chunks = _fallback_ilike_search(db, question, service_keys, limit)

    results: list[dict[str, Any]] = []
    for chunk in chunks:
        snippet = chunk.body[:300] + ("..." if len(chunk.body) > 300 else "")
        url = "/account/support/faq"
        if chunk.source_kind == "faq":
            url = f"/account/support/faq#{chunk.source_id}"
        elif chunk.source_kind == "kb":
            url = "/account/support/faq"
        elif chunk.route_hints_json:
            try:
                routes = json.loads(chunk.route_hints_json)
                if isinstance(routes, list) and routes:
                    url = str(routes[0])
            except Exception:
                pass
        results.append(
            {
                "id": chunk.id,
                "kind": chunk.source_kind,
                "title": chunk.title,
                "snippet": snippet,
                "url": url,
                "source_id": chunk.source_id,
                "score": 1.0,
            }
        )
    _ = min_score
    return results[:limit]
