from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.billing_settings import BillingSettings

_ALLOCATE_ATTEMPTS = 8


class BillingSettingsService:
    @staticmethod
    def get(db: Session) -> BillingSettings:
        row = db.get(BillingSettings, 1)
        if row is None:
            row = BillingSettings(id=1, updated_at=datetime.utcnow())
            db.add(row)
            db.commit()
            db.refresh(row)
        return row

    @staticmethod
    def to_dict(row: BillingSettings) -> dict[str, Any]:
        return {
            "company_name": row.company_name,
            "company_address": row.company_address,
            "company_email": row.company_email,
            "company_phone": row.company_phone,
            "vat_number": row.vat_number,
            "vat_enabled": bool(row.vat_enabled),
            "invoice_prefix": row.invoice_prefix,
            "invoice_next_number": int(row.invoice_next_number or 1),
            "invoice_due_days": int(row.invoice_due_days or 7),
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def update(db: Session, payload: dict[str, Any]) -> BillingSettings:
        row = BillingSettingsService.get(db)
        for key in ("company_name", "company_address", "company_email", "company_phone", "vat_number"):
            if key in payload:
                value = str(payload[key] or "").strip()
                setattr(row, key, value or None if key != "company_name" else (value or row.company_name))
        if "vat_enabled" in payload:
            row.vat_enabled = bool(payload["vat_enabled"])
        if "invoice_prefix" in payload and str(payload["invoice_prefix"] or "").strip():
            prefix = str(payload["invoice_prefix"]).strip().upper()[:16].rstrip("-")
            row.invoice_prefix = prefix or "INV"
        if "invoice_next_number" in payload and payload["invoice_next_number"] is not None:
            nxt = int(payload["invoice_next_number"])
            if nxt < 1:
                raise ValueError("invoice_next_number must be 1 or greater")
            row.invoice_next_number = nxt
        if "invoice_due_days" in payload and payload["invoice_due_days"] is not None:
            days = int(payload["invoice_due_days"])
            if days < 0:
                raise ValueError("invoice_due_days must be 0 or greater")
            row.invoice_due_days = days
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def _lock_settings(db: Session) -> BillingSettings:
        from sqlalchemy import select

        row = db.execute(select(BillingSettings).where(BillingSettings.id == 1).with_for_update()).scalar_one_or_none()
        if row is None:
            BillingSettingsService.get(db)
            row = db.execute(select(BillingSettings).where(BillingSettings.id == 1).with_for_update()).scalar_one()
        return row

    @staticmethod
    def allocate_invoice_number(db: Session) -> str:
        """Allocate the next sequential invoice number, e.g. INV-2026-000123."""
        from sqlalchemy import select

        from app.models.billing_invoice import BillingInvoice

        last_error: BaseException | None = None
        for _ in range(_ALLOCATE_ATTEMPTS):
            row = BillingSettingsService._lock_settings(db)
            seq = int(row.invoice_next_number or 1)
            year = datetime.utcnow().year
            number = f"{row.invoice_prefix or 'INV'}-{year}-{seq:06d}"
            taken = db.execute(
                select(BillingInvoice.id).where(BillingInvoice.invoice_number == number).limit(1)
            ).first()
            row.invoice_next_number = seq + 1
            row.updated_at = datetime.utcnow()
            db.add(row)
            try:
                with db.begin_nested():
                    db.flush()
            except IntegrityError as exc:
                last_error = exc
                continue
            if taken:
                continue
            return number
        raise RuntimeError("Could not allocate a unique invoice number") from last_error

    @staticmethod
    def allocate_credit_note_number(db: Session) -> str:
        from sqlalchemy import select

        from app.models.credit_note import CreditNote

        last_error: BaseException | None = None
        for _ in range(_ALLOCATE_ATTEMPTS):
            row = BillingSettingsService._lock_settings(db)
            seq = int(getattr(row, "credit_note_next_number", None) or 1)
            year = datetime.utcnow().year
            number = f"CN-{year}-{seq:06d}"
            taken = db.execute(
                select(CreditNote.id).where(CreditNote.credit_note_number == number).limit(1)
            ).first()
            row.credit_note_next_number = seq + 1
            row.updated_at = datetime.utcnow()
            db.add(row)
            try:
                with db.begin_nested():
                    db.flush()
            except IntegrityError as exc:
                last_error = exc
                continue
            if taken:
                continue
            return number
        raise RuntimeError("Could not allocate a unique credit note number") from last_error
