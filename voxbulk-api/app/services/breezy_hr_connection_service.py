"""Breezy HR ATS — PAT connect, positions/candidates, import, result writeback."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.services.crm_connection_service import get_crm_config_raw, save_crm_config_raw

logger = logging.getLogger(__name__)

PROVIDER_KEY = "breezy_hr"
PARTNER_KEY = "breezy"
API_BASE = "https://api.breezy.hr/v3"


def partner_provider_enabled(db: Session) -> bool:
    from sqlalchemy import select

    from app.models.partner import PartnerProvider

    row = db.execute(select(PartnerProvider).where(PartnerProvider.key == PARTNER_KEY)).scalar_one_or_none()
    return bool(row and row.enabled)


def platform_ready(db: Session | None = None) -> bool:
    """Dashboard tile is connectable when Admin → Partners → Breezy is enabled."""
    if db is None:
        return False
    return partner_provider_enabled(db)


def get_breezy_config(db: Session, org_id: str) -> dict[str, Any]:
    return get_crm_config_raw(db, org_id, PROVIDER_KEY)


def breezy_status(db: Session, org_id: str) -> dict[str, Any]:
    cfg = get_breezy_config(db, org_id)
    has_token = bool(str(cfg.get("access_token") or "").strip())
    company_id = str(cfg.get("company_id") or "").strip() or None
    company_name = str(cfg.get("company_name") or "").strip() or None
    return {
        "connected": has_token and bool(company_id),
        "platform_configured": platform_ready(db),
        "account_name": company_name or company_id,
        "company_id": company_id if has_token else None,
        "company_name": company_name if has_token else None,
        "connected_at": cfg.get("connected_at"),
    }


def _auth_header(token: str) -> dict[str, str]:
    raw = str(token or "").strip()
    if not raw:
        raise ValueError("Breezy API token is missing")
    # PATs are sent as-is; session tokens may be bare hex — both work in Authorization.
    return {"Authorization": raw, "Content-Type": "application/json", "Accept": "application/json"}


def _request(
    method: str,
    path: str,
    *,
    token: str,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> httpx.Response:
    url = f"{API_BASE}{path}" if path.startswith("/") else f"{API_BASE}/{path}"
    with httpx.Client(timeout=30.0) as client:
        return client.request(method, url, headers=_auth_header(token), params=params, json=json_body)


def list_companies_for_token(api_token: str) -> list[dict[str, Any]]:
    token = str(api_token or "").strip()
    if not token:
        raise ValueError("Paste your Breezy API token")
    res = _request("GET", "/companies", token=token)
    if res.status_code >= 400:
        raise ValueError(f"Breezy auth failed (HTTP {res.status_code}): {(res.text or '')[:200]}")
    data = res.json()
    rows = data if isinstance(data, list) else data.get("data") if isinstance(data, dict) else []
    out: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        cid = str(row.get("_id") or row.get("id") or "").strip()
        if not cid:
            continue
        out.append({"id": cid, "name": str(row.get("name") or cid).strip() or cid})
    return out


def connect_token(
    db: Session,
    org_id: str,
    *,
    api_token: str,
    company_id: str | None = None,
) -> dict[str, Any]:
    if not platform_ready(db):
        raise ValueError("Breezy HR is not enabled yet. Ask your admin to enable it under Partners → Breezy HR.")
    companies = list_companies_for_token(api_token)
    if not companies:
        raise ValueError("This Breezy token has no companies. Check the token in Breezy → My Settings → API Keys.")
    chosen_id = str(company_id or "").strip()
    if chosen_id:
        match = next((c for c in companies if c["id"] == chosen_id), None)
        if match is None:
            raise ValueError("Selected company is not available for this Breezy token")
    else:
        match = companies[0]
        chosen_id = match["id"]
    cfg = {
        "access_token": str(api_token).strip(),
        "company_id": chosen_id,
        "company_name": match["name"],
        "connected_at": datetime.utcnow().isoformat(),
        "writeback_scorecard": True,
    }
    save_crm_config_raw(db, org_id, PROVIDER_KEY, cfg)
    return breezy_status(db, org_id)


def disconnect(db: Session, org_id: str) -> dict[str, Any]:
    from app.models.organisation import Organisation

    org = db.get(Organisation, org_id)
    if org is None:
        raise ValueError("Organisation not found")
    org.breezy_hr_config_json = None
    db.add(org)
    db.commit()
    return breezy_status(db, org_id)


def _require_connected(db: Session, org_id: str) -> tuple[str, str]:
    cfg = get_breezy_config(db, org_id)
    token = str(cfg.get("access_token") or "").strip()
    company_id = str(cfg.get("company_id") or "").strip()
    if not token or not company_id:
        raise ValueError("Breezy HR is not connected. Connect it in Settings → Integrations → Recruiting.")
    return token, company_id


def list_positions(db: Session, org_id: str, *, state: str | None = "published") -> list[dict[str, Any]]:
    token, company_id = _require_connected(db, org_id)
    params: dict[str, Any] = {}
    if state:
        params["state"] = state
    res = _request("GET", f"/company/{company_id}/positions", token=token, params=params or None)
    if res.status_code >= 400:
        raise ValueError(f"Breezy positions failed (HTTP {res.status_code}): {(res.text or '')[:200]}")
    data = res.json()
    rows = data if isinstance(data, list) else data.get("data") if isinstance(data, dict) else []
    out: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        pid = str(row.get("_id") or row.get("id") or "").strip()
        if not pid:
            continue
        name = str(row.get("name") or row.get("title") or pid).strip() or pid
        out.append(
            {
                "id": pid,
                "name": name,
                "status": str(row.get("state") or row.get("status") or "").strip() or None,
            }
        )
    return out


def _candidate_phone(row: dict[str, Any]) -> str:
    for key in ("phone_number", "phone", "mobile", "cellphone"):
        val = row.get(key)
        if val:
            return str(val).strip()
    meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
    for key in ("phone", "phone_number", "mobile"):
        val = meta.get(key)
        if val:
            return str(val).strip()
    return ""


def _candidate_email(row: dict[str, Any]) -> str:
    for key in ("email_address", "email"):
        val = row.get(key)
        if val:
            return str(val).strip()
    return ""


def _candidate_name(row: dict[str, Any]) -> str:
    name = row.get("name")
    if isinstance(name, dict):
        first = str(name.get("first_name") or name.get("first") or "").strip()
        last = str(name.get("last_name") or name.get("last") or "").strip()
        full = f"{first} {last}".strip()
        if full:
            return full
    if isinstance(name, str) and name.strip():
        return name.strip()
    first = str(row.get("first_name") or "").strip()
    last = str(row.get("last_name") or "").strip()
    return f"{first} {last}".strip() or "Candidate"


def _map_candidate(row: dict[str, Any], *, position_id: str, position_name: str | None = None) -> dict[str, Any] | None:
    cid = str(row.get("_id") or row.get("id") or "").strip()
    if not cid:
        return None
    stage = row.get("stage")
    stage_name = ""
    if isinstance(stage, dict):
        stage_name = str(stage.get("name") or "").strip()
    elif stage:
        stage_name = str(stage).strip()
    phone = _candidate_phone(row)
    return {
        "id": cid,
        "name": _candidate_name(row),
        "email": _candidate_email(row),
        "phone": phone,
        "position_id": position_id,
        "job_title": position_name or "",
        "stage": stage_name or None,
        "phone_missing": not bool(phone),
    }


def list_candidates(
    db: Session,
    org_id: str,
    *,
    position_id: str,
    page: int = 1,
    per_page: int = 50,
) -> list[dict[str, Any]]:
    token, company_id = _require_connected(db, org_id)
    pid = str(position_id or "").strip()
    if not pid:
        raise ValueError("Select a Breezy position first")
    res = _request(
        "GET",
        f"/company/{company_id}/position/{pid}/candidates",
        token=token,
        params={"page": max(page, 1), "page_size": min(max(per_page, 1), 100)},
    )
    if res.status_code >= 400:
        raise ValueError(f"Breezy candidates failed (HTTP {res.status_code}): {(res.text or '')[:200]}")
    data = res.json()
    rows = data if isinstance(data, list) else data.get("data") if isinstance(data, dict) else []
    # Resolve position name once
    position_name = ""
    try:
        pos_res = _request("GET", f"/company/{company_id}/position/{pid}", token=token)
        if pos_res.status_code < 400:
            pos = pos_res.json()
            if isinstance(pos, dict):
                position_name = str(pos.get("name") or pos.get("title") or "").strip()
    except Exception:
        pass
    out: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        mapped = _map_candidate(row, position_id=pid, position_name=position_name)
        if mapped:
            out.append(mapped)
    return out


def get_candidate(
    db: Session,
    org_id: str,
    *,
    position_id: str,
    candidate_id: str,
) -> dict[str, Any] | None:
    token, company_id = _require_connected(db, org_id)
    pid = str(position_id or "").strip()
    cid = str(candidate_id or "").strip()
    if not pid or not cid:
        return None
    res = _request(
        "GET",
        f"/company/{company_id}/position/{pid}/candidate/{cid}",
        token=token,
    )
    if res.status_code >= 400:
        return None
    try:
        row = res.json()
    except Exception:
        return None
    if not isinstance(row, dict):
        return None
    return _map_candidate(row, position_id=pid)


def score_to_breezy(score: int | None, result_status: str | None) -> str:
    """Map VoxBulk outcome to Breezy scorecard enum."""
    status = str(result_status or "").strip().lower()
    if status == "passed":
        if score is not None and score >= 85:
            return "very_good"
        return "good"
    if status == "rejected":
        if score is not None and score < 40:
            return "very_poor"
        return "poor"
    if score is not None:
        if score >= 85:
            return "very_good"
        if score >= 70:
            return "good"
        if score >= 50:
            return "neutral"
        if score >= 35:
            return "poor"
        return "very_poor"
    return "neutral"


def parse_partner_reference(partner_reference_id: str) -> tuple[str | None, str | None]:
    """Expect `position_id:candidate_id` (recommended) or bare candidate id."""
    raw = str(partner_reference_id or "").strip()
    if not raw:
        return None, None
    if ":" in raw:
        left, right = raw.split(":", 1)
        return left.strip() or None, right.strip() or None
    return None, raw


def write_screening_result(
    db: Session,
    *,
    org_id: str,
    position_id: str,
    candidate_id: str,
    score: int | None,
    result_status: str | None,
    report_url: str | None,
) -> dict[str, Any]:
    token, company_id = _require_connected(db, org_id)
    pid = str(position_id or "").strip()
    cid = str(candidate_id or "").strip()
    if not pid or not cid:
        return {"ok": False, "detail": "Breezy position_id and candidate_id are required"}

    note_body = (
        f"VoxBulk AI Voice Screening\n"
        f"Score: {score if score is not None else 'n/a'}\n"
        f"Status: {result_status or 'n/a'}\n"
        f"Report: {report_url or 'n/a'}"
    )
    breezy_score = score_to_breezy(score, result_status)
    stream_ok = False
    scorecard_ok = False

    stream_res = _request(
        "POST",
        f"/company/{company_id}/position/{pid}/candidate/{cid}/stream",
        token=token,
        json_body={"body": note_body, "type": "note"},
    )
    if stream_res.status_code < 400:
        stream_ok = True
    else:
        # Some tenants accept a plain text body field name differently — retry once.
        stream_res2 = _request(
            "POST",
            f"/company/{company_id}/position/{pid}/candidate/{cid}/stream",
            token=token,
            json_body={"text": note_body},
        )
        stream_ok = stream_res2.status_code < 400
        if not stream_ok:
            logger.warning(
                "breezy_stream_note_failed status=%s body=%s",
                stream_res.status_code,
                (stream_res.text or "")[:300],
            )

    cfg = get_breezy_config(db, org_id)
    if cfg.get("writeback_scorecard") is not False:
        sc_res = _request(
            "PUT",
            f"/company/{company_id}/position/{pid}/candidate/{cid}/scorecard",
            token=token,
            json_body={"score": breezy_score, "note": note_body[:500]},
        )
        scorecard_ok = sc_res.status_code < 400
        if not scorecard_ok:
            logger.warning(
                "breezy_scorecard_failed status=%s body=%s",
                sc_res.status_code,
                (sc_res.text or "")[:300],
            )

    # Optional custom attributes for report URL / numeric score
    for attr_name, attr_value in (
        (str(cfg.get("custom_attr_report_url") or "").strip(), report_url),
        (str(cfg.get("custom_attr_score") or "").strip(), str(score) if score is not None else None),
    ):
        if not attr_name or not attr_value:
            continue
        try:
            _request(
                "PUT",
                f"/company/{company_id}/position/{pid}/candidate/{cid}/custom-attribute",
                token=token,
                json_body={"name": attr_name, "value": str(attr_value)},
            )
        except Exception:
            logger.exception("breezy_custom_attr_failed attr=%s", attr_name)

    return {
        "ok": stream_ok or scorecard_ok,
        "stream_note": stream_ok,
        "scorecard": scorecard_ok,
        "breezy_score": breezy_score,
    }


def _loads_recipient_result(recipient: Any) -> dict[str, Any]:
    try:
        raw = getattr(recipient, "result_json", None)
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str) and raw.strip():
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def recipient_breezy_ids(recipient: Any) -> tuple[str, str]:
    data = _loads_recipient_result(recipient)
    return (
        str(data.get("breezy_position_id") or "").strip(),
        str(data.get("breezy_candidate_id") or "").strip(),
    )


def import_candidates_to_order(
    db: Session,
    org_id: str,
    *,
    order_id: str,
    position_id: str,
    candidate_ids: list[str] | None = None,
    import_all_matching: bool = False,
) -> dict[str, Any]:
    """Idempotent import of Breezy candidates into an interview campaign."""
    from sqlalchemy import select

    from app.models.service_order import ServiceOrder, ServiceOrderRecipient
    from app.services.interview_intake_service import (
        _assert_interview_draft,
        _coerce_contact_phone,
        compute_intake_errors,
    )

    order = db.get(ServiceOrder, order_id)
    if order is None or str(order.org_id) != str(org_id):
        raise ValueError("Interview order not found")
    if str(order.service_code or "") != "interview":
        raise ValueError("Order is not an interview campaign")
    _assert_interview_draft(order)

    pid = str(position_id or "").strip()
    if not pid:
        raise ValueError("Select a Breezy position")

    ids = [str(x).strip() for x in (candidate_ids or []) if str(x).strip()]
    listed = list_candidates(db, org_id, position_id=pid, page=1, per_page=100)
    by_id = {str(c["id"]): c for c in listed if c.get("id")}

    missing_ids = [i for i in ids if i not in by_id]
    for mid in missing_ids:
        fetched = get_candidate(db, org_id, position_id=pid, candidate_id=mid)
        if fetched:
            by_id[fetched["id"]] = fetched

    if import_all_matching and not ids:
        selected = list(by_id.values())
    else:
        selected = [by_id[i] for i in ids if i in by_id]
    if not selected:
        raise ValueError("No Breezy candidates selected or matched")

    recipients = list(
        db.execute(select(ServiceOrderRecipient).where(ServiceOrderRecipient.order_id == order.id)).scalars()
    )
    existing_by_breezy: dict[str, ServiceOrderRecipient] = {}
    for r in recipients:
        _, cid = recipient_breezy_ids(r)
        if cid:
            existing_by_breezy[cid] = r

    added = 0
    updated = 0
    skipped = 0
    missing_phone = 0

    cfg: dict[str, Any] = {}
    try:
        cfg = json.loads(order.config_json or "{}")
        if not isinstance(cfg, dict):
            cfg = {}
    except Exception:
        cfg = {}
    cfg["breezy_position_id"] = pid
    order.config_json = json.dumps(cfg, ensure_ascii=False)

    for cand in selected:
        cid = str(cand.get("id") or "").strip()
        if not cid:
            skipped += 1
            continue
        name = str(cand.get("name") or "").strip() or "Candidate"
        phone_raw = str(cand.get("phone") or "").strip() or None
        email = str(cand.get("email") or "").strip() or None
        phone, phone_errors = _coerce_contact_phone(phone_raw)
        if not phone:
            missing_phone += 1

        match = existing_by_breezy.get(cid)
        result_meta = {
            "breezy_candidate_id": cid,
            "breezy_position_id": pid,
            "breezy_stage": str(cand.get("stage") or "").strip() or None,
            "intake_source": "breezy_hr",
        }
        if match:
            if name and (not match.name or match.name == "Unknown"):
                match.name = name
            if phone and not match.phone:
                match.phone = phone
            if email and not match.email:
                match.email = email
            merged = _loads_recipient_result(match)
            merged.update({k: v for k, v in result_meta.items() if v})
            match.result_json = json.dumps(merged, ensure_ascii=False)
            match.intake_source = "breezy_hr"
            match.intake_errors_json = json.dumps(compute_intake_errors(match), ensure_ascii=False)
            db.add(match)
            updated += 1
            continue

        recipient = ServiceOrderRecipient(
            order_id=order.id,
            row_number=len(recipients) + 1,
            name=name,
            phone=phone,
            email=email,
            status="pending",
            cv_quality="missing",
            intake_source="breezy_hr",
            intake_errors_json=json.dumps(phone_errors, ensure_ascii=False),
            result_json=json.dumps({k: v for k, v in result_meta.items() if v}, ensure_ascii=False),
        )
        recipient.intake_errors_json = json.dumps(compute_intake_errors(recipient), ensure_ascii=False)
        db.add(recipient)
        recipients.append(recipient)
        existing_by_breezy[cid] = recipient
        added += 1

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

    return {
        "order_id": order.id,
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "missing_phone": missing_phone,
        "recipient_count": order.recipient_count,
        "breezy_position_id": pid,
    }


def maybe_writeback_interview_result(db: Session, *, order: Any, recipient: Any) -> dict[str, Any] | None:
    """Write Dashboard interview outcome to Breezy when recipient was imported from Breezy."""
    from app.services.partner_service import recommendation_to_status

    position_id, candidate_id = recipient_breezy_ids(recipient)
    if not position_id or not candidate_id:
        return None
    org_id = str(getattr(order, "org_id", "") or "").strip()
    if not org_id:
        return None

    parsed = _loads_recipient_result(recipient)
    analysis = parsed.get("analysis") if isinstance(parsed.get("analysis"), dict) else {}
    score_raw = analysis.get("score") if analysis else parsed.get("score")
    try:
        score = int(score_raw) if score_raw is not None else None
    except Exception:
        score = None
    recommendation = analysis.get("recommendation") if analysis else parsed.get("recommendation")
    result_status = recommendation_to_status(str(recommendation) if recommendation else None, score)
    report_url = f"https://dashboard.voxbulk.com/interview/orders/{order.id}/recipients/{recipient.id}"

    try:
        result = write_screening_result(
            db,
            org_id=org_id,
            position_id=position_id,
            candidate_id=candidate_id,
            score=score,
            result_status=result_status,
            report_url=report_url,
        )
        merged = dict(parsed)
        merged["breezy_writeback"] = {
            "ok": bool(result.get("ok")),
            "at": datetime.utcnow().isoformat(),
            "result_status": result_status,
            "score": score,
            "breezy_score": result.get("breezy_score"),
        }
        recipient.result_json = json.dumps(merged, ensure_ascii=False)
        db.add(recipient)
        db.commit()
        return result
    except Exception:
        logger.exception(
            "breezy_hr_dashboard_writeback_failed order_id=%s recipient_id=%s",
            getattr(order, "id", None),
            getattr(recipient, "id", None),
        )
        return {"ok": False, "detail": "writeback_failed"}
