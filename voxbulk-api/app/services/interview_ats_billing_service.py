"""Paid ATS scoring for interview CV intake."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.interview_ats_service import queue_ats_for_order, sanitize_cv_text
from app.services.platform_catalog_service import PlatformCatalogService

ATS_SERVICE_CODE = "interview_ats"
DEFAULT_ATS_UNIT_PENCE = 50


class InterviewAtsBillingError(ValueError):
    pass


def ats_unit_price_pence(db: Session) -> int:
    svc = PlatformCatalogService.get_service_by_code(db, ATS_SERVICE_CODE)
    if svc is None:
        return DEFAULT_ATS_UNIT_PENCE
    rules = PlatformCatalogService.list_rules_for_service(db, svc.id, active_only=True)
    for rule in rules:
        if int(rule.unit_price_pence or 0) > 0:
            return int(rule.unit_price_pence)
        if int(rule.overage_unit_price_pence or 0) > 0:
            return int(rule.overage_unit_price_pence)
    return DEFAULT_ATS_UNIT_PENCE


def _order_config(order: ServiceOrder) -> dict[str, Any]:
    try:
        data = json.loads(order.config_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_order_config(db: Session, order: ServiceOrder, cfg: dict[str, Any]) -> ServiceOrder:
    order.config_json = json.dumps(cfg, ensure_ascii=False)
    order.updated_at = datetime.utcnow()
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def ats_wallet_pence(order: ServiceOrder) -> int:
    cfg = _order_config(order)
    return max(0, int(cfg.get("ats_wallet_pence") or 0))


def recipients_needing_ats(
    order: ServiceOrder,
    recipients: list[ServiceOrderRecipient],
    *,
    force: bool = False,
) -> list[ServiceOrderRecipient]:
    out: list[ServiceOrderRecipient] = []
    for row in recipients:
        cv_text = sanitize_cv_text(row.cv_text or "")
        if len(cv_text) < 80:
            continue
        status = str(row.ats_status or "").strip().lower()
        if not force and status in {"pending", "analyzing", "complete"}:
            continue
        out.append(row)
    return out


def quote_ats_run(db: Session, order: ServiceOrder, *, force: bool = False) -> dict[str, Any]:
    if order.service_code != "interview":
        raise InterviewAtsBillingError("Not an interview order")
    recipients = list(
        db.execute(
            select(ServiceOrderRecipient)
            .where(ServiceOrderRecipient.order_id == order.id)
            .order_by(ServiceOrderRecipient.row_number.asc())
        ).scalars()
    )
    pending = recipients_needing_ats(order, recipients, force=force)
    unit = ats_unit_price_pence(db)
    total = unit * len(pending)
    wallet = ats_wallet_pence(order)
    return {
        "candidate_count": len(pending),
        "unit_price_pence": unit,
        "unit_price_gbp": f"£{unit / 100:.2f}",
        "total_pence": total,
        "total_gbp": f"£{total / 100:.2f}",
        "wallet_pence": wallet,
        "wallet_gbp": f"£{wallet / 100:.2f}",
        "requires_payment": total > wallet,
        "recipient_ids": [r.id for r in pending],
    }


def assert_script_ready_for_ats(order: ServiceOrder) -> None:
    cfg = _order_config(order)
    criteria = str(cfg.get("criteria") or cfg.get("screening_criteria") or "").strip()
    role = str(cfg.get("role") or cfg.get("position") or order.title or "").strip()
    if not role:
        raise InterviewAtsBillingError("Enter the position / role before running ATS")
    if not criteria:
        raise InterviewAtsBillingError("Add screening criteria before running ATS")
    script = str(cfg.get("approved_script") or cfg.get("generated_script_draft") or "").strip()
    if not script:
        raise InterviewAtsBillingError("Generate and save the AI script before running ATS")


def deposit_ats_wallet(db: Session, order: ServiceOrder, *, amount_pence: int) -> ServiceOrder:
    amount = max(0, int(amount_pence or 0))
    if amount <= 0:
        raise InterviewAtsBillingError("Deposit amount must be positive")
    cfg = _order_config(order)
    cfg["ats_wallet_pence"] = ats_wallet_pence(order) + amount
    ledger = cfg.get("ats_wallet_ledger")
    if not isinstance(ledger, list):
        ledger = []
    ledger.append({"amount_pence": amount, "at": datetime.utcnow().isoformat(), "kind": "deposit"})
    cfg["ats_wallet_ledger"] = ledger[-50:]
    return _save_order_config(db, order, cfg)


def charge_and_queue_ats(
    db: Session,
    order: ServiceOrder,
    org: Organisation,
    *,
    confirm_charge: bool = False,
    recipient_ids: list[str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    assert_script_ready_for_ats(order)
    quote = quote_ats_run(db, order, force=force)
    count = int(quote["candidate_count"] or 0)
    if count <= 0:
        return {"ok": True, "queued": 0, "message": "No CVs need ATS scoring", **quote}

    total = int(quote["total_pence"] or 0)
    wallet = ats_wallet_pence(order)
    if total > wallet and not confirm_charge:
        raise InterviewAtsBillingError(
            f"ATS costs {quote['total_gbp']} ({count} × {quote['unit_price_gbp']}). "
            "Confirm payment to continue."
        )

    cfg = _order_config(order)
    if total > wallet:
        cfg["ats_pending_charge_pence"] = total
        cfg["ats_last_charge_at"] = datetime.utcnow().isoformat()
        cfg["ats_last_charge_count"] = count
    elif total > 0:
        cfg["ats_wallet_pence"] = wallet - total
        ledger = cfg.get("ats_wallet_ledger")
        if not isinstance(ledger, list):
            ledger = []
        ledger.append({"amount_pence": -total, "at": datetime.utcnow().isoformat(), "kind": "ats_run"})
        cfg["ats_wallet_ledger"] = ledger[-50:]

    order = _save_order_config(db, order, cfg)
    queued = queue_ats_for_order(db, order, recipient_ids=recipient_ids or quote.get("recipient_ids"))
    return {"ok": True, "queued": queued, "charged_pence": total, **quote}
