"""Paid ATS scoring for interview CV intake."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.platform_service import PlatformService
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.interview_ats_service import process_pending_ats_scans, queue_ats_for_order, sanitize_cv_text
from app.services.platform_catalog_service import PlatformCatalogService

logger = logging.getLogger(__name__)

ATS_SERVICE_CODE = "interview_ats"
DEFAULT_ATS_UNIT_PENCE = 50


class InterviewAtsBillingError(ValueError):
    pass


def ats_unit_price_pence(db: Session) -> int:
    """Read ATS unit price from VoxBulk global/org pricing."""
    try:
        from app.services.voxbulk_pricing_service import VoxbulkPricingService

        settings = VoxbulkPricingService.get_settings(db)
        fee = int(settings.ats_cv_scan_fee_pence or 0)
        return fee if fee > 0 else DEFAULT_ATS_UNIT_PENCE
    except Exception:
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
        if status in {"pending", "analyzing"}:
            continue
        if not force and status == "complete" and row.ats_score is not None:
            continue
        out.append(row)
    return out


def quote_ats_run(
    db: Session,
    order: ServiceOrder,
    *,
    force: bool = False,
    recipient_ids: list[str] | None = None,
) -> dict[str, Any]:
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
    if recipient_ids:
        allowed = {str(rid).strip() for rid in recipient_ids if str(rid).strip()}
        pending = [row for row in pending if row.id in allowed]
    already_scored = sum(
        1
        for row in recipients
        if str(row.ats_status or "").strip().lower() == "complete" and row.ats_score is not None
    )
    unit = ats_unit_price_pence(db)
    total = unit * len(pending)
    wallet = ats_wallet_pence(order)
    return {
        "candidate_count": len(pending),
        "already_scored_count": already_scored if not force else 0,
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


def assert_email_cv_ats_ready(order: ServiceOrder) -> None:
    cfg = _order_config(order)
    criteria = str(cfg.get("criteria") or cfg.get("screening_criteria") or "").strip()
    role = str(cfg.get("role") or cfg.get("position") or order.title or "").strip()
    if not role:
        raise InterviewAtsBillingError("Enter the position / role before ATS can run on emailed CVs")
    if not criteria:
        raise InterviewAtsBillingError("Add screening criteria before ATS can run on emailed CVs")


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


def _ats_charges_list(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    raw = cfg.get("ats_charges")
    return [row for row in raw if isinstance(row, dict)] if isinstance(raw, list) else []


def record_ats_charge(
    db: Session,
    order: ServiceOrder,
    org: Organisation,
    recipient: ServiceOrderRecipient,
    *,
    source: str,
    created_by_user_id: str | None = None,
) -> dict[str, Any]:
    """Charge one ATS scan (manual or auto): plan allowance first, then org wallet."""
    cfg = _order_config(order)
    charges = _ats_charges_list(cfg)
    if any(str(row.get("recipient_id") or "") == recipient.id for row in charges):
        return {"ok": True, "skipped": True, "reason": "already_charged"}

    unit = ats_unit_price_pence(db)
    wallet_tx_id: str | None = None
    billing_kind = "wallet"
    billable_pence = unit

    from app.services.usage_wallet_service import UsageWalletService
    from app.services.wallet_service import InsufficientWalletBalance, WalletService

    row = UsageWalletService.get_current(db, org.id)
    included = int(getattr(row, "cv_scans_included", 0) or 0) if row else 0
    used = int(getattr(row, "cv_scans_used", 0) or 0) if row else 0
    if row is not None and included > 0 and used < included:
        UsageWalletService.record_cv_scan_usage(db, org_id=org.id, units=1, commit=False)
        billing_kind = "plan_included"
        billable_pence = 0
    else:
        tx = WalletService.debit(
            db,
            org,
            amount_minor=unit,
            kind="ats_debit",
            description=f"ATS CV screening — {recipient.name or 'Candidate'}"[:500],
            order_id=order.id,
            created_by_user_id=created_by_user_id,
            metadata={"recipient_id": recipient.id, "source": source},
            commit=False,
        )
        wallet_tx_id = tx.id
        UsageWalletService.record_cv_scan_usage(db, org_id=org.id, units=1, commit=False)

    charges.append(
        {
            "recipient_id": recipient.id,
            "source": str(source or "manual").strip().lower()[:16],
            "catalog_unit_pence": unit,
            "amount_pence": billable_pence,
            "billing_kind": billing_kind,
            "wallet_tx_id": wallet_tx_id,
            "at": datetime.utcnow().isoformat(),
        }
    )
    cfg["ats_charges"] = charges[-500:]
    cfg["ats_last_charge_at"] = datetime.utcnow().isoformat()
    cfg["ats_last_charge_count"] = len(charges)
    cfg["ats_last_unit_pence"] = unit
    _save_order_config(db, order, cfg)
    return {
        "ok": True,
        "catalog_unit_pence": unit,
        "amount_pence": billable_pence,
        "billing_kind": billing_kind,
        "wallet_tx_id": wallet_tx_id,
    }


def charge_and_queue_ats(
    db: Session,
    order: ServiceOrder,
    org: Organisation,
    *,
    confirm_charge: bool = False,
    recipient_ids: list[str] | None = None,
    force: bool = False,
    require_script: bool = True,
    process_inline: bool = False,
) -> dict[str, Any]:
    if require_script:
        assert_script_ready_for_ats(order)
    else:
        assert_email_cv_ats_ready(order)
    quote = quote_ats_run(db, order, force=force, recipient_ids=recipient_ids)
    count = int(quote["candidate_count"] or 0)
    cfg = _order_config(order)
    if count <= 0:
        order = _save_order_config(db, order, cfg)
        return {"ok": True, "queued": 0, "message": "No CVs need ATS scoring", **quote}

    ids = [str(rid).strip() for rid in (recipient_ids or quote.get("recipient_ids") or []) if str(rid).strip()]
    pending_recipients = list(
        db.execute(
            select(ServiceOrderRecipient).where(
                ServiceOrderRecipient.order_id == order.id,
                ServiceOrderRecipient.id.in_(ids),
            )
        ).scalars()
    ) if ids else []

    if require_script:
        cfg["ats_manual_run_at"] = datetime.utcnow().isoformat()
        _save_order_config(db, order, cfg)

    unit = int(quote["unit_price_pence"] or 0)
    from app.services.usage_wallet_service import UsageWalletService
    from app.services.wallet_service import InsufficientWalletBalance, WalletService

    usage_row = UsageWalletService.get_current(db, org.id)
    included = int(getattr(usage_row, "cv_scans_included", 0) or 0) if usage_row else 0
    used = int(getattr(usage_row, "cv_scans_used", 0) or 0) if usage_row else 0
    plan_remaining = max(0, included - used)
    wallet_units = max(0, count - plan_remaining)
    wallet_needed = wallet_units * unit
    if wallet_needed > 0 and WalletService.balance_minor(org) < wallet_needed and not confirm_charge:
        raise InterviewAtsBillingError(
            f"ATS costs {quote['total_gbp']} ({count} × {quote['unit_price_gbp']}). "
            "Confirm payment to continue."
        )

    charged_pence = 0
    for recipient in pending_recipients:
        try:
            result = record_ats_charge(
                db,
                order,
                org,
                recipient,
                source="manual",
            )
            charged_pence += int(result.get("amount_pence") or 0)
        except InsufficientWalletBalance as exc:
            raise InterviewAtsBillingError(str(exc)) from exc
    db.refresh(order)

    queued = queue_ats_for_order(db, order, recipient_ids=ids or None, force=force)
    processed = 0
    if queued > 0 and process_inline:
        processed = process_pending_ats_scans(db, limit=max(1, min(int(queued), 8)))

    accepted = 0
    if process_inline and ids and org is not None:
        from app.services.interview_cv_exclusion_service import maybe_reject_recipient_by_ats_threshold

        recipients = list(
            db.execute(
                select(ServiceOrderRecipient).where(
                    ServiceOrderRecipient.order_id == order.id,
                    ServiceOrderRecipient.id.in_(ids),
                )
            ).scalars()
        )
        for recipient in recipients:
            db.refresh(recipient)
            if maybe_reject_recipient_by_ats_threshold(db, order, recipient):
                continue
            accepted += 1

    db.commit()
    return {"ok": True, "queued": queued, "processed": processed, "accepted": accepted, "charged_pence": charged_pence, **quote}


def background_process_ats_scans(*, limit: int = 8) -> None:
    """Process queued ATS rows after HTTP response so UI can show Analyzing."""
    from app.core.database import get_sessionmaker

    db = get_sessionmaker()()
    try:
        process_pending_ats_scans(db, limit=max(1, min(int(limit), 8)))
    except Exception:
        logger.exception("background_process_ats_scans_failed")
    finally:
        db.close()
