"""Merge CSV + CV uploads into interview draft recipient lists."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.interview_cv_parse_service import ParsedCv, name_from_filename, name_similarity, parse_uploaded_cv_files
from app.services.platform_catalog_service import ServiceOrderService

MATCH_THRESHOLD = 0.82


def _loads_json(raw: str | None) -> Any:
    try:
        return json.loads(raw or "")
    except Exception:
        return None


def _dumps_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


def compute_intake_errors(recipient: ServiceOrderRecipient) -> list[str]:
    errors: list[str] = []
    stored = _loads_json(recipient.intake_errors_json)
    if isinstance(stored, list):
        errors.extend(str(x) for x in stored if x)
    if not str(recipient.name or "").strip():
        errors.append("Name missing")
    if not str(recipient.phone or "").strip():
        errors.append("Phone missing — click to add")
    quality = str(recipient.cv_quality or "missing")
    if quality == "low_quality":
        errors.append("CV low-quality — generic questions only")
    elif quality == "corrupt":
        errors.append("CV unreadable")
    elif quality == "missing" and str(recipient.intake_source or "") != "csv":
        errors.append("CV missing")
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for err in errors:
        key = err.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(err)
    return out


def recipient_intake_dict(recipient: ServiceOrderRecipient) -> dict[str, Any]:
    base = ServiceOrderService.recipient_to_dict(recipient)
    parsed = _loads_json(recipient.cv_parsed_json) or {}
    errors = compute_intake_errors(recipient)
    ready = bool(str(recipient.name or "").strip() and str(recipient.phone or "").strip())
    base.update(
        {
            "cv_quality": recipient.cv_quality or "missing",
            "cv_filename": recipient.cv_filename,
            "intake_source": recipient.intake_source,
            "intake_errors": errors,
            "intake_ready": ready,
            "cv_skills": parsed.get("skills") or [],
            "cv_job_titles": parsed.get("job_titles") or [],
        }
    )
    return base


def _assert_interview_draft(order: ServiceOrder) -> None:
    if order.service_code != "interview":
        raise ValueError("Only interview orders support CV intake")
    if order.payment_status == "approved":
        raise ValueError("Cannot change candidates after payment is approved")
    if order.status in {"running", "completed", "cancelled"}:
        raise ValueError("Cannot change candidates while campaign is active or finished")


def ensure_interview_draft_order(
    db: Session,
    *,
    org_id: str,
    user_id: str,
    title: str = "Interview draft",
    role: str = "",
    criteria: str = "",
) -> ServiceOrder:
    rows = list(
        db.execute(
            select(ServiceOrder)
            .where(
                ServiceOrder.org_id == org_id,
                ServiceOrder.service_code == "interview",
                ServiceOrder.status == "draft",
                ServiceOrder.payment_status == "unpaid",
            )
            .order_by(ServiceOrder.updated_at.desc())
            .limit(1)
        ).scalars()
    )
    if rows:
        order = rows[0]
        config = _loads_json(order.config_json) or {}
        changed = False
        if role and not config.get("role"):
            config["role"] = role
            changed = True
        if criteria and not config.get("criteria"):
            config["criteria"] = criteria
            changed = True
        if changed:
            order.config_json = _dumps_json(config)
            order.updated_at = datetime.utcnow()
            db.add(order)
            db.commit()
            db.refresh(order)
        return order
    config: dict[str, Any] = {}
    if role:
        config["role"] = role
    if criteria:
        config["criteria"] = criteria
    return ServiceOrderService.create_order(
        db,
        org_id=org_id,
        user_id=user_id,
        service_code="interview",
        title=title.strip() or "Interview draft",
        config=config,
    )


def _apply_parsed_cv(recipient: ServiceOrderRecipient, parsed: ParsedCv, *, merge: bool) -> None:
    recipient.cv_filename = parsed.filename
    recipient.cv_text = parsed.text or None
    recipient.cv_quality = parsed.quality
    recipient.cv_parsed_json = _dumps_json(parsed.to_dict())
    recipient.intake_errors_json = _dumps_json(parsed.errors)
    if parsed.name and (not recipient.name or merge):
        recipient.name = parsed.name
    if parsed.phone and (not recipient.phone or merge):
        recipient.phone = parsed.phone
    if parsed.email and (not recipient.email or merge):
        recipient.email = parsed.email
    if recipient.intake_source == "csv":
        recipient.intake_source = "merged"
    elif not recipient.intake_source:
        recipient.intake_source = "cv"


def _find_match(recipients: list[ServiceOrderRecipient], parsed: ParsedCv) -> ServiceOrderRecipient | None:
    if not parsed.name:
        return None
    best: ServiceOrderRecipient | None = None
    best_score = 0.0
    for r in recipients:
        score = name_similarity(r.name, parsed.name)
        if score > best_score:
            best_score = score
            best = r
    if best and best_score >= MATCH_THRESHOLD:
        return best
    return None


def intake_contacts_csv(db: Session, order: ServiceOrder, rows: list[dict[str, str | None]]) -> ServiceOrder:
    _assert_interview_draft(order)
    db.execute(delete(ServiceOrderRecipient).where(ServiceOrderRecipient.order_id == order.id))
    added = 0
    for i, row in enumerate(rows, start=1):
        name = str(row.get("name") or "").strip()
        phone = str(row.get("phone") or "").strip() or None
        email = str(row.get("email") or "").strip() or None
        if not name and not phone:
            continue
        recipient = ServiceOrderRecipient(
            order_id=order.id,
            row_number=i,
            name=name or "Unknown",
            phone=phone,
            email=email,
            status="pending",
            cv_quality="missing",
            intake_source="csv",
            intake_errors_json=_dumps_json([] if phone else ["Phone missing — click to add"]),
        )
        db.add(recipient)
        added += 1
    order.recipient_count = added
    order.updated_at = datetime.utcnow()
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def parse_contacts_csv_relaxed_from_bytes(content: bytes, filename: str) -> list[dict[str, str | None]]:
    """Like parse_recipient_file but phone is optional during intake."""
    name = str(filename or "").lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        import io

        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
        if not header_row:
            return []
        headers = [ServiceOrderService._norm_header(x) for x in header_row]
        out: list[dict[str, str | None]] = []
        for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            data = {
                headers[i]: (str(row[i]).strip() if i < len(row) and row[i] is not None else "")
                for i in range(len(headers))
            }
            name_val = data.get("name") or data.get("fullname") or data.get("contactname") or ""
            phone_val = data.get("phone") or data.get("mobile") or data.get("telephone") or data.get("phonenumber") or ""
            email_val = data.get("email") or data.get("emailaddress") or ""
            if not name_val and not phone_val:
                continue
            out.append({"name": name_val or None, "phone": phone_val or None, "email": email_val or None})
        return out
    import csv
    import io

    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV must include a header row: name, phone, email")
    out = []
    for raw in reader:
        data = {ServiceOrderService._norm_header(k): str(v or "").strip() for k, v in raw.items()}
        name_val = data.get("name") or data.get("fullname") or data.get("contactname") or ""
        phone_val = data.get("phone") or data.get("mobile") or data.get("telephone") or data.get("phonenumber") or ""
        email_val = data.get("email") or data.get("emailaddress") or ""
        if not name_val and not phone_val:
            continue
        out.append({"name": name_val or None, "phone": phone_val or None, "email": email_val or None})
    return out


def intake_cv_files(db: Session, order: ServiceOrder, files: list[tuple[str, bytes]]) -> dict[str, Any]:
    _assert_interview_draft(order)
    parsed_list = parse_uploaded_cv_files(files)
    recipients = list(db.execute(select(ServiceOrderRecipient).where(ServiceOrderRecipient.order_id == order.id)).scalars())
    unmatched: list[dict[str, Any]] = []
    created = 0

    for parsed in parsed_list:
        match = _find_match(recipients, parsed)
        if match:
            _apply_parsed_cv(match, parsed, merge=True)
            db.add(match)
            continue

        display_name = (parsed.name or name_from_filename(parsed.filename)).strip()
        if not display_name:
            unmatched.append({"filename": parsed.filename, "errors": parsed.errors or ["Could not identify candidate name"]})
            continue

        recipient = ServiceOrderRecipient(
            order_id=order.id,
            row_number=len(recipients) + created + 1,
            name=display_name,
            phone=parsed.phone or None,
            email=parsed.email or None,
            status="pending",
            cv_quality=parsed.quality,
            cv_filename=parsed.filename,
            cv_text=parsed.text or None,
            cv_parsed_json=_dumps_json(parsed.to_dict()),
            intake_errors_json=_dumps_json(parsed.errors),
            intake_source="cv",
        )
        db.add(recipient)
        recipients.append(recipient)
        created += 1

    db.flush()

    recipients = list(
        db.execute(
            select(ServiceOrderRecipient)
            .where(ServiceOrderRecipient.order_id == order.id)
            .order_by(ServiceOrderRecipient.row_number)
        ).scalars()
    )
    for i, r in enumerate(recipients, start=1):
        r.row_number = i
        db.add(r)

    order.recipient_count = len(recipients)
    order.updated_at = datetime.utcnow()
    db.add(order)
    db.commit()
    db.refresh(order)

    final_recipients = list(
        db.execute(
            select(ServiceOrderRecipient)
            .where(ServiceOrderRecipient.order_id == order.id)
            .order_by(ServiceOrderRecipient.row_number)
        ).scalars()
    )
    recipient_payload = [recipient_intake_dict(r) for r in final_recipients]
    return {
        "order_id": order.id,
        "parsed_count": len(parsed_list),
        "recipient_count": len(final_recipients),
        "unmatched_files": unmatched,
        "recipients": recipient_payload,
        "summary": intake_summary(recipient_payload),
    }


def list_intake_recipients(db: Session, order: ServiceOrder) -> list[dict[str, Any]]:
    rows = list(
        db.execute(
            select(ServiceOrderRecipient)
            .where(ServiceOrderRecipient.order_id == order.id)
            .order_by(ServiceOrderRecipient.row_number)
        ).scalars()
    )
    return [recipient_intake_dict(r) for r in rows]


def update_intake_recipient(
    db: Session,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    payload: dict[str, Any],
) -> ServiceOrderRecipient:
    _assert_interview_draft(order)
    if recipient.order_id != order.id:
        raise ValueError("Recipient does not belong to this order")
    if "name" in payload:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("Name is required")
        recipient.name = name
    if "phone" in payload:
        phone = str(payload.get("phone") or "").strip()
        recipient.phone = phone or None
    if "email" in payload:
        email = str(payload.get("email") or "").strip()
        recipient.email = email or None
    recipient.intake_errors_json = _dumps_json(
        [e for e in compute_intake_errors(recipient) if "Phone missing" not in e]
        + ([] if recipient.phone else ["Phone missing — click to add"])
    )
    order.updated_at = datetime.utcnow()
    db.add(recipient)
    db.add(order)
    db.commit()
    db.refresh(recipient)
    return recipient


def delete_intake_recipient(db: Session, order: ServiceOrder, recipient: ServiceOrderRecipient) -> ServiceOrder:
    _assert_interview_draft(order)
    if recipient.order_id != order.id:
        raise ValueError("Recipient does not belong to this order")
    db.delete(recipient)
    remaining = list(
        db.execute(
            select(ServiceOrderRecipient)
            .where(ServiceOrderRecipient.order_id == order.id)
            .order_by(ServiceOrderRecipient.row_number)
        ).scalars()
    )
    for i, r in enumerate(remaining, start=1):
        r.row_number = i
        db.add(r)
    order.recipient_count = len(remaining)
    order.updated_at = datetime.utcnow()
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def intake_summary(recipients: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(recipients),
        "ready": sum(1 for r in recipients if r.get("intake_ready")),
        "missing_phone": sum(1 for r in recipients if any("phone missing" in str(e).lower() for e in (r.get("intake_errors") or []))),
        "cv_good": sum(1 for r in recipients if r.get("cv_quality") == "good"),
        "cv_low_quality": sum(1 for r in recipients if r.get("cv_quality") == "low_quality"),
        "cv_missing": sum(1 for r in recipients if r.get("cv_quality") == "missing"),
    }
