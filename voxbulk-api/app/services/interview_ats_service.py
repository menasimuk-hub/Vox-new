"""DeepSeek ATS scoring for interview CV intake (upload + email)."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.agents.base import AgentMessage
from app.services.providers.openai_service import OpenAIProviderService

logger = logging.getLogger(__name__)

ATS_VERSION = "1"
MAX_CV_CHARS = 12_000
MAX_JOB_CHARS = 4_000
_BATCH_SIZE = 8

_ATS_SYSTEM = """You are an ATS (Applicant Tracking System) scorer for recruitment.
Evaluate how well the candidate CV matches the job description.
Consider: CV relevance, skills match, experience relevance, keyword match.
Return ONLY valid JSON with a single field: {"ats_score": <integer 0-100>}
No markdown, no explanation, no other keys."""

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_cv_text(text: str) -> str:
    raw = str(text or "")
    raw = _CONTROL_CHARS.sub(" ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw[:MAX_CV_CHARS]


def _order_job_context(order: ServiceOrder) -> tuple[str, str]:
    try:
        cfg = json.loads(order.config_json or "{}")
        if not isinstance(cfg, dict):
            cfg = {}
    except Exception:
        cfg = {}
    role = str(cfg.get("role") or order.title or "Role").strip()
    criteria = str(cfg.get("criteria") or cfg.get("screening_criteria") or "").strip()
    job = "\n".join(x for x in [f"Position: {role}", f"Requirements:\n{criteria}"] if x).strip()
    return role, job[:MAX_JOB_CHARS]


def compute_ats_input_hash(*, cv_text: str, job_description: str) -> str:
    payload = f"{ATS_VERSION}|{job_description}|{cv_text}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _parse_ats_score(raw: str) -> int | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "ats_score" in data:
            score = int(data["ats_score"])
            return max(0, min(100, score))
    except Exception:
        pass
    match = re.search(r'"ats_score"\s*:\s*(\d{1,3})', text)
    if match:
        return max(0, min(100, int(match.group(1))))
    match = re.search(r"\b(\d{1,3})\s*%?\b", text)
    if match:
        return max(0, min(100, int(match.group(1))))
    return None


def score_cv_with_deepseek(db: Session, *, cv_text: str, job_description: str) -> int:
    clean_cv = sanitize_cv_text(cv_text)
    if len(clean_cv) < 80:
        raise ValueError("CV text is too short for ATS scoring")
    job = str(job_description or "").strip() or "General role"
    user = f"Job description:\n{job}\n\nCandidate CV:\n{clean_cv}"
    result = OpenAIProviderService.complete(
        db,
        system_prompt=_ATS_SYSTEM,
        messages=[AgentMessage(role="user", content=user)],
        max_tokens=64,
        temperature=0.1,
        provider="deepseek",
    )
    score = _parse_ats_score(str(result.assistant_text or ""))
    if score is None:
        raise ValueError("DeepSeek did not return a valid ATS score")
    return score


def queue_ats_for_recipient(db: Session, recipient: ServiceOrderRecipient, *, order: ServiceOrder | None = None) -> None:
    cv_text = sanitize_cv_text(recipient.cv_text or "")
    if len(cv_text) < 80:
        return
    order = order or db.get(ServiceOrder, recipient.order_id)
    if order is None or order.service_code != "interview":
        return
    _, job = _order_job_context(order)
    content_hash = compute_ats_input_hash(cv_text=cv_text, job_description=job)
    if recipient.ats_status == "complete" and recipient.ats_hash == content_hash:
        return
    recipient.ats_hash = content_hash
    recipient.ats_score = None
    recipient.ats_error = None
    recipient.ats_status = "pending"
    db.add(recipient)


def queue_ats_for_order(db: Session, order: ServiceOrder, *, recipient_ids: list[str] | None = None) -> int:
    if order.service_code != "interview":
        return 0
    rows = list(
        db.execute(
            select(ServiceOrderRecipient).where(ServiceOrderRecipient.order_id == order.id)
        ).scalars()
    )
    queued = 0
    for row in rows:
        if recipient_ids and row.id not in recipient_ids:
            continue
        before = row.ats_status
        queue_ats_for_recipient(db, row, order=order)
        if row.ats_status == "pending" and before != "pending":
            queued += 1
        elif row.ats_status == "pending":
            queued += 1
    if queued:
        db.commit()
    return queued


def process_one_ats_recipient(db: Session, recipient: ServiceOrderRecipient) -> bool:
    if str(recipient.ats_status or "") not in {"pending", "analyzing"}:
        return False
    order = db.get(ServiceOrder, recipient.order_id)
    if order is None:
        return False
    cv_text = sanitize_cv_text(recipient.cv_text or "")
    if len(cv_text) < 80:
        recipient.ats_status = "failed"
        recipient.ats_error = "CV text missing or too short"
        db.add(recipient)
        db.commit()
        return True
    role, job = _order_job_context(order)
    content_hash = compute_ats_input_hash(cv_text=cv_text, job_description=job)
    if recipient.ats_status == "complete" and recipient.ats_hash == content_hash and recipient.ats_score is not None:
        return False
    recipient.ats_status = "analyzing"
    recipient.ats_error = None
    db.add(recipient)
    db.commit()
    try:
        score = score_cv_with_deepseek(db, cv_text=cv_text, job_description=job)
        recipient.ats_score = score
        recipient.ats_status = "complete"
        recipient.ats_hash = content_hash
        recipient.ats_error = None
    except Exception as exc:
        logger.exception("interview_ats_score_failed recipient_id=%s", recipient.id)
        recipient.ats_status = "failed"
        recipient.ats_error = str(exc)[:500]
    db.add(recipient)
    db.commit()
    return True


def process_pending_ats_scans(db: Session, *, limit: int = _BATCH_SIZE) -> int:
    rows = list(
        db.execute(
            select(ServiceOrderRecipient)
            .where(ServiceOrderRecipient.ats_status.in_(["pending", "analyzing"]))
            .order_by(ServiceOrderRecipient.created_at.asc())
            .limit(limit)
        ).scalars()
    )
    processed = 0
    for row in rows:
        if process_one_ats_recipient(db, row):
            processed += 1
    return processed


def ats_display_for_recipient(recipient: ServiceOrderRecipient, *, position: str = "") -> dict[str, Any]:
    status = str(recipient.ats_status or "").strip().lower()
    score = recipient.ats_score
    label = "—"
    if status in {"pending", "analyzing"}:
        label = "Analyzing..."
    elif status == "complete" and score is not None:
        label = f"{int(score)}%"
    elif status == "failed":
        label = "Failed"
    return {
        "ats_score": score,
        "ats_status": status or None,
        "ats_label": label,
        "position": position,
    }
