"""Merge CSV + CV uploads into interview draft recipient lists."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.interview_cv_parse_service import ParsedCv, name_from_filename, name_similarity, parse_uploaded_cv_files
from app.services.platform_catalog_service import ServiceOrderService

MATCH_THRESHOLD = 0.82


def _norm_phone(value: str | None) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _norm_email(value: str | None) -> str:
    return str(value or "").strip().lower()


def _norm_name(value: str | None) -> str:
    return str(value or "").strip().lower()


def find_duplicate_recipient(
    recipients: list[ServiceOrderRecipient],
    *,
    name: str | None,
    phone: str | None,
    email: str | None,
) -> ServiceOrderRecipient | None:
    """Match a prior row for the same person (not phone-only — avoids merging ZIP batch CVs)."""
    np = _norm_phone(phone)
    ne = _norm_email(email)
    nn = _norm_name(name)
    for r in recipients:
        if nn and len(nn) >= 2 and _norm_name(r.name) == nn:
            return r
        if ne and _norm_email(r.email) == ne:
            return r
        if np and _norm_phone(r.phone) == np:
            if nn and r.name and name_similarity(r.name, name) >= MATCH_THRESHOLD:
                return r
            if ne and _norm_email(r.email) == ne:
                return r
    return None


def _remove_recipient(db: Session, recipient: ServiceOrderRecipient, recipients: list[ServiceOrderRecipient]) -> None:
    from sqlalchemy import inspect

    from app.services.career_cv_storage_service import delete_cv_file

    delete_cv_file(recipient.cv_storage_key)
    state = inspect(recipient)
    if state.persistent:
        db.delete(recipient)
    if recipient in recipients:
        recipients.remove(recipient)


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


def recipient_intake_dict(recipient: ServiceOrderRecipient, *, position: str = "") -> dict[str, Any]:
    base = ServiceOrderService.recipient_to_dict(recipient)
    parsed = _loads_json(recipient.cv_parsed_json) or {}
    errors = compute_intake_errors(recipient)
    ready = bool(str(recipient.name or "").strip() and str(recipient.phone or "").strip())
    from app.services.interview_ats_service import ats_display_for_recipient

    base.update(
        {
            "cv_quality": recipient.cv_quality or "missing",
            "cv_filename": recipient.cv_filename,
            "intake_source": recipient.intake_source,
            "intake_errors": errors,
            "intake_ready": ready,
            "cv_skills": parsed.get("skills") or [],
            "cv_job_titles": parsed.get("job_titles") or [],
            "has_cv_file": bool(recipient.cv_storage_key or (recipient.cv_text or "").strip()),
        }
    )
    base.update(ats_display_for_recipient(recipient, position=position))
    from app.services.interview_activity_service import InterviewActivityService

    base["activity_status"] = InterviewActivityService.activity_status(recipient)
    phone_raw = str(recipient.phone or "").strip()
    if phone_raw:
        from sqlalchemy.orm import object_session

        from app.services.telnyx_phone_allowlist_service import TelnyxPhoneAllowlistService

        db = object_session(recipient)
        phone_check = (
            TelnyxPhoneAllowlistService.validate_phone_db(db, phone_raw)
            if db is not None
            else TelnyxPhoneAllowlistService.validate_phone(phone_raw)
        )
        base["phone_call_allowed"] = bool(phone_check.get("allowed"))
        base["phone_call_block_reason"] = phone_check.get("reason")
        base["phone_country"] = phone_check.get("country")
        base["phone_line_type"] = phone_check.get("line_type")
        if phone_check.get("normalized"):
            base["phone_normalized"] = phone_check.get("normalized")
    else:
        base["phone_call_allowed"] = False
        base["phone_call_block_reason"] = "Phone number is required"
    return base


def _assert_interview_draft(order: ServiceOrder) -> None:
    if order.service_code != "interview":
        raise ValueError("Only interview orders support CV intake")
    if order.payment_status == "approved":
        raise ValueError("Cannot change candidates after payment is approved")
    if order.status in {"running", "completed", "cancelled"}:
        raise ValueError("Cannot change candidates while campaign is active or finished")


def get_latest_interview_draft(db: Session, *, org_id: str) -> ServiceOrder | None:
    purge_empty_interview_drafts(db, org_id=org_id)
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
    return rows[0] if rows else None


def _interview_draft_has_meaningful_config(cfg: dict[str, Any]) -> bool:
    meaningful = [
        cfg.get("role"),
        cfg.get("position"),
        cfg.get("criteria"),
        cfg.get("screening_criteria"),
        cfg.get("approved_script"),
        cfg.get("generated_script_draft"),
        cfg.get("agent_id"),
        cfg.get("title"),
    ]
    if any(str(v or "").strip() for v in meaningful):
        return True
    if cfg.get("script_approved") or cfg.get("cv_email_enabled"):
        return True
    if str(cfg.get("scheduled_start") or "").strip() or str(cfg.get("scheduled_end") or "").strip():
        return True
    if str(cfg.get("calling_start") or "").strip() or str(cfg.get("calling_end") or "").strip():
        return True
    delivery = str(cfg.get("delivery") or "").strip().lower()
    if delivery and delivery not in {"ai_call", ""}:
        return True
    duration = cfg.get("expected_duration_minutes")
    if duration is not None and str(duration).strip() not in {"", "0"}:
        return True
    return False


def is_empty_interview_draft(order: ServiceOrder, *, recipient_count: int) -> bool:
    if order.status != "draft" or order.payment_status != "unpaid":
        return False
    if recipient_count > 0:
        return False
    if int(order.recipient_count or 0) > 0:
        return False
    cfg = _loads_json(order.config_json) or {}
    if _interview_draft_has_meaningful_config(cfg):
        return False
    title = str(order.title or "").strip().lower()
    return title in {"", "interview draft", "interview", "untitled interview"}


def purge_empty_interview_drafts(db: Session, *, org_id: str, keep_order_id: str | None = None) -> int:
    from sqlalchemy import func

    rows = list(
        db.execute(
            select(ServiceOrder)
            .where(
                ServiceOrder.org_id == org_id,
                ServiceOrder.service_code == "interview",
                ServiceOrder.status == "draft",
                ServiceOrder.payment_status == "unpaid",
            )
        ).scalars()
    )
    deleted = 0
    for order in rows:
        if keep_order_id and order.id == keep_order_id:
            continue
        count = db.execute(
            select(func.count())
            .select_from(ServiceOrderRecipient)
            .where(ServiceOrderRecipient.order_id == order.id)
        ).scalar_one()
        if is_empty_interview_draft(order, recipient_count=int(count or 0)):
            ServiceOrderService.delete_order(db, order)
            deleted += 1
    return deleted


def ensure_interview_draft_order(
    db: Session,
    *,
    org_id: str,
    user_id: str,
    title: str = "Interview draft",
    role: str = "",
    criteria: str = "",
) -> ServiceOrder:
    purge_empty_interview_drafts(db, org_id=org_id)
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
        from app.services.interview_reference_service import ensure_order_reference_id

        return ensure_order_reference_id(db, order)
    config: dict[str, Any] = {}
    if role:
        config["role"] = role
    if criteria:
        config["criteria"] = criteria
    order = ServiceOrderService.create_order(
        db,
        org_id=org_id,
        user_id=user_id,
        service_code="interview",
        title=title.strip() or "Interview draft",
        config=config,
    )
    from app.services.interview_reference_service import ensure_order_reference_id

    return ensure_order_reference_id(db, order)


def create_new_interview_draft(
    db: Session,
    *,
    org_id: str,
    user_id: str,
) -> ServiceOrder:
    """Always create a fresh draft (new reference ID) without touching existing drafts."""
    purge_empty_interview_drafts(db, org_id=org_id)
    order = ServiceOrderService.create_order(
        db,
        org_id=org_id,
        user_id=user_id,
        service_code="interview",
        title="Interview draft",
        config={},
    )
    from app.services.interview_reference_service import ensure_order_reference_id

    order = ensure_order_reference_id(db, order)
    purge_empty_interview_drafts(db, org_id=org_id, keep_order_id=order.id)
    return order


def abandon_empty_interview_draft(db: Session, *, org_id: str, order_id: str) -> bool:
    """Delete a draft interview order when it has no saved content."""
    order = ServiceOrderService.get_order(db, order_id, org_id=org_id)
    if order is None or order.service_code != "interview":
        return False
    from sqlalchemy import func

    count = db.execute(
        select(func.count())
        .select_from(ServiceOrderRecipient)
        .where(ServiceOrderRecipient.order_id == order.id)
    ).scalar_one()
    if not is_empty_interview_draft(order, recipient_count=int(count or 0)):
        return False
    ServiceOrderService.delete_order(db, order)
    return True


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


CONTACT_EXTENSIONS = (".csv", ".xlsx", ".xls")
CV_EXTENSIONS = (".pdf", ".docx", ".doc", ".zip", ".txt")


def classify_intake_filename(filename: str) -> str:
    lower = str(filename or "").lower().replace("\\", "/")
    base = lower.rsplit("/", 1)[-1]
    for ext in CONTACT_EXTENSIONS:
        if base.endswith(ext):
            return "contact"
    for ext in CV_EXTENSIONS:
        if base.endswith(ext):
            return "cv"
    return "unknown"


def _find_match_for_contact(recipients: list[ServiceOrderRecipient], row: dict[str, str | None]) -> ServiceOrderRecipient | None:
    phone = str(row.get("phone") or "").strip()
    name = str(row.get("name") or "").strip()
    if phone:
        norm_phone = re.sub(r"\D", "", phone)
        for r in recipients:
            if norm_phone and norm_phone == re.sub(r"\D", "", str(r.phone or "")):
                return r
    if name:
        best: ServiceOrderRecipient | None = None
        best_score = 0.0
        for r in recipients:
            score = name_similarity(r.name, name)
            if score > best_score:
                best_score = score
                best = r
        if best and best_score >= MATCH_THRESHOLD:
            return best
    return None


def intake_contacts_merge(db: Session, order: ServiceOrder, rows: list[dict[str, str | None]]) -> ServiceOrder:
    _assert_interview_draft(order)
    recipients = list(db.execute(select(ServiceOrderRecipient).where(ServiceOrderRecipient.order_id == order.id)).scalars())
    for row in rows:
        name = str(row.get("name") or "").strip()
        phone = str(row.get("phone") or "").strip() or None
        email = str(row.get("email") or "").strip() or None
        if not name and not phone:
            continue
        match = _find_match_for_contact(recipients, row)
        if match:
            if name and (not match.name or match.name == "Unknown"):
                match.name = name
            if phone and not match.phone:
                match.phone = phone
            if email and not match.email:
                match.email = email
            if match.intake_source == "cv":
                match.intake_source = "merged"
            db.add(match)
            continue
        recipient = ServiceOrderRecipient(
            order_id=order.id,
            row_number=len(recipients) + 1,
            name=name or "Unknown",
            phone=phone,
            email=email,
            status="pending",
            cv_quality="missing",
            intake_source="csv",
            intake_errors_json=_dumps_json([] if phone else ["Phone missing — click to add"]),
        )
        db.add(recipient)
        recipients.append(recipient)
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
    return order


def intake_mixed_files(db: Session, order: ServiceOrder, files: list[tuple[str, bytes]]) -> dict[str, Any]:
    _assert_interview_draft(order)
    if not files:
        raise ValueError("Upload at least one file")

    contact_files: list[tuple[str, bytes]] = []
    cv_files: list[tuple[str, bytes]] = []
    rejected: list[dict[str, str]] = []

    for filename, content in files:
        kind = classify_intake_filename(filename)
        if kind == "contact":
            contact_files.append((filename, content))
        elif kind == "cv":
            cv_files.append((filename, content))
        else:
            rejected.append({"filename": filename, "reason": "Unsupported file type — use Excel, CSV, PDF, DOCX, TXT, or ZIP"})

    contact_rows: list[dict[str, str | None]] = []
    for filename, content in contact_files:
        try:
            rows = parse_contacts_csv_relaxed_from_bytes(content, filename)
            contact_rows.extend(rows)
        except ValueError as e:
            rejected.append({"filename": filename, "reason": str(e)})

    existing = list(db.execute(select(ServiceOrderRecipient).where(ServiceOrderRecipient.order_id == order.id)).scalars())
    contacts_added = 0
    if contact_rows:
        if existing:
            order = intake_contacts_merge(db, order, contact_rows)
        else:
            order = intake_contacts_csv(db, order, contact_rows)
        contacts_added = len(contact_rows)

    cv_result: dict[str, Any] = {
        "parsed_count": 0,
        "unmatched_files": [],
    }
    if cv_files:
        cv_result = intake_cv_files(db, order, cv_files)
        order = ServiceOrderService.get_order(db, order.id) or order

    final_recipients = list(
        db.execute(
            select(ServiceOrderRecipient)
            .where(ServiceOrderRecipient.order_id == order.id)
            .order_by(ServiceOrderRecipient.row_number)
        ).scalars()
    )
    recipient_payload = [recipient_intake_dict(r) for r in final_recipients]
    for u in cv_result.get("unmatched_files") or []:
        rejected.append({"filename": u.get("filename", ""), "reason": "; ".join(u.get("errors") or [])})

    if not final_recipients and not contact_files and not cv_files:
        raise ValueError("No supported files in upload")
    if not final_recipients and rejected and not contact_rows and not cv_files:
        raise ValueError(rejected[0].get("reason") or "Could not process upload")

    return {
        "order_id": order.id,
        "contact_files": len(contact_files),
        "contact_rows": contacts_added,
        "parsed_count": cv_result.get("parsed_count", 0),
        "recipient_count": len(final_recipients),
        "rejected_files": rejected,
        "recipients": recipient_payload,
        "summary": intake_summary(recipient_payload),
    }


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


def intake_email_cv_for_order(
    db: Session,
    order: ServiceOrder,
    *,
    parsed: ParsedCv,
    storage_key: str,
    sender_email: str | None = None,
) -> ServiceOrder:
    _assert_interview_draft(order)
    recipients = list(db.execute(select(ServiceOrderRecipient).where(ServiceOrderRecipient.order_id == order.id)).scalars())
    email_val = parsed.email or sender_email
    dup = find_duplicate_recipient(recipients, name=parsed.name, phone=parsed.phone, email=email_val)
    if dup and parsed.name and dup.name and name_similarity(dup.name, parsed.name) >= MATCH_THRESHOLD:
        _apply_parsed_cv(dup, parsed, merge=True)
        dup.cv_storage_key = storage_key
        dup.intake_source = "email"
        db.add(dup)
        db.flush()
        recipients = list(
            db.execute(select(ServiceOrderRecipient).where(ServiceOrderRecipient.order_id == order.id)).scalars()
        )
        for i, r in enumerate(recipients, start=1):
            r.row_number = i
            db.add(r)
        order.recipient_count = len(recipients)
        order.updated_at = datetime.utcnow()
        db.add(order)
        db.commit()
        db.refresh(order)
        return order

    display_name = (parsed.name or name_from_filename(parsed.filename)).strip() or "Unknown"
    recipient = ServiceOrderRecipient(
        order_id=order.id,
        row_number=len(recipients) + 1,
        name=display_name,
        phone=parsed.phone or None,
        email=email_val or None,
        status="pending",
        cv_quality=parsed.quality,
        cv_filename=parsed.filename,
        cv_text=parsed.text or None,
        cv_parsed_json=_dumps_json(parsed.to_dict()),
        intake_errors_json=_dumps_json(parsed.errors),
        intake_source="email",
        cv_storage_key=storage_key,
    )
    db.add(recipient)
    recipients.append(recipient)
    db.flush()
    for i, r in enumerate(recipients, start=1):
        r.row_number = i
        db.add(r)
    order.recipient_count = len(recipients)
    order.updated_at = datetime.utcnow()
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def _cv_bytes_by_filename(files: list[tuple[str, bytes]]) -> dict[str, bytes]:
    """Map each CV filename to raw bytes (including DOCX/PDF inside ZIP archives)."""
    from app.services.interview_cv_parse_service import iter_cv_files_from_zip

    out: dict[str, bytes] = {}
    for filename, content in files:
        if str(filename or "").lower().endswith(".zip"):
            try:
                for inner_name, inner_bytes in iter_cv_files_from_zip(content):
                    out[inner_name] = inner_bytes
            except Exception:
                continue
        else:
            out[str(filename or "upload")] = content
    return out


def intake_cv_files(db: Session, order: ServiceOrder, files: list[tuple[str, bytes]]) -> dict[str, Any]:
    _assert_interview_draft(order)
    parsed_list = parse_uploaded_cv_files(files)
    bytes_by_name = _cv_bytes_by_filename(files)
    recipients = list(db.execute(select(ServiceOrderRecipient).where(ServiceOrderRecipient.order_id == order.id)).scalars())
    unmatched: list[dict[str, Any]] = []
    created = 0

    for parsed in parsed_list:
        raw_bytes = bytes_by_name.get(parsed.filename)
        raw_file = (parsed.filename, raw_bytes) if raw_bytes is not None else None
        dup = find_duplicate_recipient(recipients, name=parsed.name, phone=parsed.phone, email=parsed.email)
        if dup and parsed.name and dup.name and name_similarity(dup.name, parsed.name) >= MATCH_THRESHOLD:
            _apply_parsed_cv(dup, parsed, merge=True)
            if raw_file:
                from app.services.career_cv_storage_service import delete_cv_file, save_cv_bytes, storage_key_for

                delete_cv_file(dup.cv_storage_key)
                key = storage_key_for(org_id=order.org_id, order_id=order.id, filename=parsed.filename)
                save_cv_bytes(storage_key=key, content=raw_file[1])
                dup.cv_storage_key = key
            db.add(dup)
            continue

        match = _find_match(recipients, parsed)
        if match:
            if raw_file:
                from app.services.career_cv_storage_service import delete_cv_file, save_cv_bytes, storage_key_for

                delete_cv_file(match.cv_storage_key)
                key = storage_key_for(org_id=order.org_id, order_id=order.id, filename=parsed.filename)
                save_cv_bytes(storage_key=key, content=raw_file[1])
                match.cv_storage_key = key
            _apply_parsed_cv(match, parsed, merge=True)
            if match.intake_source in {None, "csv"}:
                match.intake_source = "merged"
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
        if raw_file:
            from app.services.career_cv_storage_service import save_cv_bytes, storage_key_for

            key = storage_key_for(org_id=order.org_id, order_id=order.id, filename=parsed.filename)
            save_cv_bytes(storage_key=key, content=raw_file[1])
            recipient.cv_storage_key = key
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
    from app.services.interview_ats_service import _order_job_context

    role, _ = _order_job_context(order)
    recipient_payload = [recipient_intake_dict(r, position=role) for r in final_recipients]
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
    from app.services.interview_ats_service import _order_job_context

    role, _ = _order_job_context(order)
    return [recipient_intake_dict(r, position=role) for r in rows]


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
    from app.services.career_cv_storage_service import delete_cv_file

    delete_cv_file(recipient.cv_storage_key)
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
