"""Auto-reject CVs below a minimum ATS score before AI screening."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.interview_cv_email_service import _loads_config
from app.services.interview_cv_parse_service import ParsedCv

DEFAULT_MIN_ATS_SCORE = 40

AUTO_REPLY_EXCLUDED_SUBJECT = "Your CV could not be processed"
AUTO_REPLY_EXCLUDED_BODY = (
    "Thank you for your interest. Based on our initial review of your CV, we are unable to progress "
    "your application for this role at this time.\n\n"
    "Your CV was not stored for this campaign."
)


def cv_min_ats_score_from_config(cfg: dict[str, Any]) -> int:
    raw = cfg.get("cv_min_ats_score")
    if raw is None:
        return DEFAULT_MIN_ATS_SCORE
    try:
        return max(0, min(100, int(raw)))
    except (TypeError, ValueError):
        return DEFAULT_MIN_ATS_SCORE


def cv_exclusion_keywords_from_config(cfg: dict[str, Any]) -> list[str]:
    raw = cfg.get("cv_exclusion_keywords")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        keyword = str(item or "").strip()
        if not keyword:
            continue
        key = keyword.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(keyword[:120])
    return out[:50]


def normalize_exclusion_keywords(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.replace("\n", ",").split(",")]
        return cv_exclusion_keywords_from_config({"cv_exclusion_keywords": parts})
    if isinstance(raw, list):
        return cv_exclusion_keywords_from_config({"cv_exclusion_keywords": raw})
    return []


def cv_text_for_exclusion_check(
    *,
    parsed: ParsedCv,
    filename: str,
    body_text: str = "",
    sender_email: str | None = None,
) -> str:
    chunks = [
        parsed.text or "",
        parsed.name or "",
        parsed.email or "",
        sender_email or "",
        filename or "",
        body_text or "",
    ]
    skills = getattr(parsed, "skills", None) or []
    if isinstance(skills, list):
        chunks.extend(str(s) for s in skills)
    titles = getattr(parsed, "job_titles", None) or []
    if isinstance(titles, list):
        chunks.extend(str(t) for t in titles)
    return "\n".join(str(c) for c in chunks if str(c).strip())


def match_exclusion_keyword(text: str, keywords: list[str]) -> str | None:
    haystack = str(text or "").lower()
    if not haystack:
        return None
    for keyword in keywords:
        if keyword.lower() in haystack:
            return keyword
    return None


def check_cv_exclusion(
    order: ServiceOrder,
    *,
    parsed: ParsedCv,
    filename: str,
    body_text: str = "",
    sender_email: str | None = None,
) -> str | None:
    cfg = _loads_config(order)
    keywords = cv_exclusion_keywords_from_config(cfg)
    if not keywords:
        return None
    blob = cv_text_for_exclusion_check(
        parsed=parsed,
        filename=filename,
        body_text=body_text,
        sender_email=sender_email,
    )
    return match_exclusion_keyword(blob, keywords)


def is_auto_excluded_recipient(recipient: ServiceOrderRecipient) -> bool:
    try:
        parsed = json.loads(recipient.result_json or "{}")
        if not isinstance(parsed, dict):
            return False
    except Exception:
        return False
    return bool(
        parsed.get("auto_excluded_at")
        or parsed.get("cv_exclusion_keyword")
        or parsed.get("cv_ats_reject")
    )


def cv_accepted_recipient_count(db: Session, order: ServiceOrder) -> int:
    rows = (
        db.execute(select(ServiceOrderRecipient).where(ServiceOrderRecipient.order_id == order.id))
        .scalars()
        .all()
    )
    return sum(1 for row in rows if not is_auto_excluded_recipient(row))


def record_excluded_cv_for_order(
    db: Session,
    order: ServiceOrder,
    *,
    parsed: ParsedCv,
    filename: str,
    matched_keyword: str,
    sender_email: str | None = None,
) -> ServiceOrderRecipient:
    now = datetime.utcnow()
    display_name = (parsed.name or "Candidate").strip() or "Candidate"
    result = {
        "auto_excluded_at": now.isoformat(),
        "cv_exclusion_keyword": matched_keyword,
        "exclusion_label": f"Auto-excluded · matched: {matched_keyword}",
        "sender_email": sender_email,
    }
    recipient = ServiceOrderRecipient(
        order_id=order.id,
        row_number=0,
        name=display_name,
        phone=parsed.phone or None,
        email=parsed.email or sender_email or None,
        status="excluded",
        cv_quality=parsed.quality,
        cv_filename=filename,
        cv_text=None,
        cv_parsed_json=json.dumps(parsed.to_dict(), ensure_ascii=False),
        intake_source="email",
        intake_errors_json=json.dumps(["Auto-excluded before screening"], ensure_ascii=False),
        result_json=json.dumps(result, ensure_ascii=False),
    )
    db.add(recipient)
    db.flush()
    recipients = list(
        db.execute(select(ServiceOrderRecipient).where(ServiceOrderRecipient.order_id == order.id)).scalars()
    )
    for i, row in enumerate(recipients, start=1):
        row.row_number = i
        db.add(row)
    order.updated_at = now
    db.add(order)
    db.commit()
    db.refresh(recipient)
    return recipient


def mark_recipient_ats_rejected(
    db: Session,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    *,
    min_score: int,
    actual_score: int,
) -> ServiceOrderRecipient:
    now = datetime.utcnow()
    try:
        result = json.loads(recipient.result_json or "{}")
        if not isinstance(result, dict):
            result = {}
    except Exception:
        result = {}
    result.update(
        {
            "auto_excluded_at": now.isoformat(),
            "cv_ats_reject": True,
            "cv_min_ats_score": min_score,
            "cv_ats_score": actual_score,
            "exclusion_label": f"Auto-excluded · ATS score {actual_score}% (below {min_score}%)",
        }
    )
    recipient.status = "excluded"
    recipient.result_json = json.dumps(result, ensure_ascii=False)
    order.updated_at = now
    db.add(recipient)
    db.add(order)
    db.commit()
    db.refresh(recipient)
    return recipient


def maybe_reject_recipient_by_ats_threshold(
    db: Session,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
) -> bool:
    """Mark recipient excluded when ATS score is below campaign threshold. Returns True if rejected."""
    if is_auto_excluded_recipient(recipient):
        return True
    if str(recipient.ats_status or "").lower() != "complete" or recipient.ats_score is None:
        return False
    min_score = cv_min_ats_score_from_config(_loads_config(order))
    actual_score = int(recipient.ats_score)
    if actual_score >= min_score:
        return False
    mark_recipient_ats_rejected(
        db,
        order,
        recipient,
        min_score=min_score,
        actual_score=actual_score,
    )
    return True


def should_reject_by_ats_score(order: ServiceOrder, recipient: ServiceOrderRecipient) -> bool:
    if is_auto_excluded_recipient(recipient):
        return True
    if str(recipient.ats_status or "").lower() != "complete" or recipient.ats_score is None:
        return False
    min_score = cv_min_ats_score_from_config(_loads_config(order))
    return int(recipient.ats_score) < min_score


def _recipient_result_dict(recipient: ServiceOrderRecipient) -> dict[str, Any]:
    try:
        data = json.loads(recipient.result_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def is_ats_threshold_excluded(recipient: ServiceOrderRecipient) -> bool:
    return bool(_recipient_result_dict(recipient).get("cv_ats_reject"))


def screening_eligible_recipient(order: ServiceOrder, recipient: ServiceOrderRecipient) -> bool:
    if is_auto_excluded_recipient(recipient):
        return False
    if str(recipient.ats_status or "").lower() != "complete" or recipient.ats_score is None:
        return False
    min_score = cv_min_ats_score_from_config(_loads_config(order))
    return int(recipient.ats_score) >= min_score


def apply_ats_threshold_to_order(
    db: Session,
    order: ServiceOrder,
    *,
    min_score: int | None = None,
) -> dict[str, Any]:
    """Re-evaluate all scored CVs against the campaign ATS cutoff (reject below, restore above)."""
    cfg = _loads_config(order)
    if min_score is not None:
        cfg["cv_min_ats_score"] = max(0, min(100, int(min_score)))
        order.config_json = json.dumps(cfg, ensure_ascii=False)
        db.add(order)

    threshold = cv_min_ats_score_from_config(cfg)
    rows = list(
        db.execute(select(ServiceOrderRecipient).where(ServiceOrderRecipient.order_id == order.id)).scalars()
    )
    rejected = 0
    restored = 0
    now = datetime.utcnow()

    for recipient in rows:
        parsed = _recipient_result_dict(recipient)
        if parsed.get("cv_exclusion_keyword") and not parsed.get("cv_ats_reject"):
            continue
        if str(recipient.ats_status or "").lower() != "complete" or recipient.ats_score is None:
            continue

        score = int(recipient.ats_score)
        if score >= threshold:
            if parsed.get("cv_ats_reject"):
                for key in (
                    "auto_excluded_at",
                    "cv_ats_reject",
                    "cv_min_ats_score",
                    "cv_ats_score",
                    "exclusion_label",
                ):
                    parsed.pop(key, None)
                recipient.result_json = json.dumps(parsed, ensure_ascii=False)
                if str(recipient.status or "").lower() == "excluded":
                    recipient.status = "pending"
                db.add(recipient)
                restored += 1
        elif not parsed.get("cv_ats_reject"):
            mark_recipient_ats_rejected(
                db,
                order,
                recipient,
                min_score=threshold,
                actual_score=score,
            )
            rejected += 1
        else:
            mark_recipient_ats_rejected(
                db,
                order,
                recipient,
                min_score=threshold,
                actual_score=score,
            )

    order.updated_at = now
    db.add(order)
    db.commit()
    db.refresh(order)

    eligible_count = sum(
        1
        for row in db.execute(select(ServiceOrderRecipient).where(ServiceOrderRecipient.order_id == order.id))
        .scalars()
        if screening_eligible_recipient(order, row)
    )
    return {
        "ok": True,
        "min_ats_score": threshold,
        "rejected_count": rejected,
        "restored_count": restored,
        "eligible_count": eligible_count,
        "total_scored": sum(
            1
            for row in rows
            if str(row.ats_status or "").lower() == "complete" and row.ats_score is not None
        ),
    }
