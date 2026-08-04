"""Sales / partner commission withdrawal invoices and payout details."""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.sales_rep import SalesCommission, SalesPayoutInvoice, SalesRep
from app.models.user import User
from app.services.sales_rep_service import SalesRepError, SalesRepService

logger = logging.getLogger(__name__)

COMMISSION_TYPE_MONTH2 = "month2"
COMMISSION_TYPE_FIXED = "fixed"
COMMISSION_TYPE_PERCENT = "percent"
VALID_COMMISSION_TYPES = frozenset({COMMISSION_TYPE_MONTH2, COMMISSION_TYPE_FIXED, COMMISSION_TYPE_PERCENT})

PAYOUT_BANK = "bank"
PAYOUT_PAYPAL = "paypal"
VALID_PAYOUT_METHODS = frozenset({PAYOUT_BANK, PAYOUT_PAYPAL})

STATUS_SUBMITTED = "submitted"
STATUS_PAID = "paid"
STATUS_REJECTED = "rejected"


class SalesPayoutService:
    @staticmethod
    def normalize_commission_type(raw: Any) -> str:
        value = str(raw or COMMISSION_TYPE_MONTH2).strip().lower()
        if value not in VALID_COMMISSION_TYPES:
            raise SalesRepError("commission_type must be month2, fixed, or percent.")
        return value

    @staticmethod
    def normalize_fixed_minor(raw: Any) -> int:
        if raw is None or raw == "":
            return 0
        try:
            # Accept pence int, or pounds float/string.
            if isinstance(raw, str) and "." in raw:
                minor = int(round(float(raw) * 100))
            else:
                minor = int(round(float(raw)))
                # Heuristic: values like 250.0 pounds passed as float without scale — treat < 100000 as pence if int-like
                # Callers should pass amount_minor / commission_fixed_minor in pence.
        except (TypeError, ValueError) as exc:
            raise SalesRepError("Fixed commission must be a number (GBP pence).") from exc
        if minor < 0:
            raise SalesRepError("Fixed commission cannot be negative.")
        return minor

    @staticmethod
    def normalize_payout_method(raw: Any) -> str | None:
        if raw is None or str(raw).strip() == "":
            return None
        value = str(raw).strip().lower()
        if value not in VALID_PAYOUT_METHODS:
            raise SalesRepError("payout_method must be bank or paypal.")
        return value

    @staticmethod
    def commission_type_of(rep: SalesRep) -> str:
        value = str(getattr(rep, "commission_type", None) or "").strip().lower()
        if value in VALID_COMMISSION_TYPES:
            return value
        # Legacy fallback by kind.
        if SalesRepService.is_partner_channel(rep):
            return COMMISSION_TYPE_PERCENT
        return COMMISSION_TYPE_MONTH2

    @staticmethod
    def fixed_minor_of(rep: SalesRep) -> int:
        try:
            return max(0, int(getattr(rep, "commission_fixed_minor", 0) or 0))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def payout_dict(rep: SalesRep) -> dict[str, Any]:
        return {
            "payout_method": getattr(rep, "payout_method", None),
            "bank_holder_name": getattr(rep, "bank_holder_name", None),
            "bank_name": getattr(rep, "bank_name", None),
            "bank_sort_code": getattr(rep, "bank_sort_code", None),
            "bank_account_number": getattr(rep, "bank_account_number", None),
            "bank_address": getattr(rep, "bank_address", None),
            "paypal_email": getattr(rep, "paypal_email", None),
        }

    @staticmethod
    def apply_payout_fields(rep: SalesRep, patch: dict[str, Any]) -> None:
        if "payout_method" in patch:
            rep.payout_method = SalesPayoutService.normalize_payout_method(patch.get("payout_method"))
        for key in (
            "bank_holder_name",
            "bank_name",
            "bank_sort_code",
            "bank_account_number",
            "bank_address",
            "paypal_email",
        ):
            if key in patch:
                val = str(patch.get(key) or "").strip()
                setattr(rep, key, val or None)
        method = SalesPayoutService.normalize_payout_method(getattr(rep, "payout_method", None))
        if method == PAYOUT_BANK:
            if not (rep.bank_holder_name and rep.bank_account_number and rep.bank_sort_code and rep.bank_name):
                # Allow partial save from admin create; validate fully on invoice submit.
                pass
        if method == PAYOUT_PAYPAL and "paypal_email" in patch:
            email = str(rep.paypal_email or "").strip().lower()
            if email and "@" not in email:
                raise SalesRepError("PayPal email is invalid.")
            rep.paypal_email = email or None

    @staticmethod
    def assert_payout_ready(rep: SalesRep) -> None:
        method = str(getattr(rep, "payout_method", None) or "").strip().lower()
        if method == PAYOUT_BANK:
            missing = [
                label
                for label, val in (
                    ("account holder / company name", rep.bank_holder_name),
                    ("bank name", rep.bank_name),
                    ("sort code", rep.bank_sort_code),
                    ("account number", rep.bank_account_number),
                )
                if not str(val or "").strip()
            ]
            if missing:
                raise SalesRepError("Complete bank payout details first: " + ", ".join(missing) + ".")
        elif method == PAYOUT_PAYPAL:
            if not str(getattr(rep, "paypal_email", None) or "").strip():
                raise SalesRepError("Add a PayPal email before creating an invoice.")
        else:
            raise SalesRepError("Set a payout method (bank or PayPal) before creating an invoice.")

    @staticmethod
    def payout_snapshot(rep: SalesRep) -> dict[str, Any]:
        return SalesPayoutService.payout_dict(rep)

    @staticmethod
    def payout_method_summary(rep: SalesRep | dict[str, Any]) -> str:
        data = SalesPayoutService.payout_dict(rep) if isinstance(rep, SalesRep) else dict(rep or {})
        method = str(data.get("payout_method") or "").lower()
        if method == PAYOUT_PAYPAL:
            return f"PayPal ({data.get('paypal_email') or '—'})"
        if method == PAYOUT_BANK:
            return (
                f"Bank {data.get('bank_name') or '—'} · "
                f"{data.get('bank_sort_code') or '—'} / {data.get('bank_account_number') or '—'}"
            )
        return "—"

    @staticmethod
    def format_gbp(minor: int) -> str:
        return f"£{int(minor or 0) / 100:,.2f}"

    @staticmethod
    def available_minor(db: Session, *, rep_id: str) -> int:
        rows = (
            db.execute(
                select(SalesCommission).where(
                    SalesCommission.sales_rep_id == str(rep_id),
                    SalesCommission.status == "pending",
                )
            )
            .scalars()
            .all()
        )
        return sum(int(c.amount_minor or 0) for c in rows)

    @staticmethod
    def wallet_totals(db: Session, *, rep_id: str) -> dict[str, int]:
        commissions = (
            db.execute(select(SalesCommission).where(SalesCommission.sales_rep_id == str(rep_id)))
            .scalars()
            .all()
        )
        pending = sum(int(c.amount_minor or 0) for c in commissions if c.status == "pending")
        requested = sum(int(c.amount_minor or 0) for c in commissions if c.status == "requested")
        paid = sum(int(c.amount_minor or 0) for c in commissions if c.status == "paid")
        return {
            "available_minor": pending,
            "requested_minor": requested,
            "paid_minor": paid,
            "total_minor": pending + requested + paid,
        }

    @staticmethod
    def _next_invoice_number(db: Session) -> str:
        stamp = datetime.utcnow().strftime("%Y%m%d")
        for _ in range(12):
            candidate = f"SPI-{stamp}-{secrets.token_hex(2).upper()}"
            exists = db.execute(
                select(SalesPayoutInvoice).where(SalesPayoutInvoice.invoice_number == candidate)
            ).scalar_one_or_none()
            if exists is None:
                return candidate
        return f"SPI-{stamp}-{secrets.token_hex(4).upper()}"

    @staticmethod
    def _reserve_commissions(db: Session, *, rep: SalesRep, invoice: SalesPayoutInvoice, amount_minor: int) -> None:
        remaining = int(amount_minor)
        pending = (
            db.execute(
                select(SalesCommission)
                .where(
                    SalesCommission.sales_rep_id == rep.id,
                    SalesCommission.status == "pending",
                )
                .order_by(SalesCommission.created_at.asc())
            )
            .scalars()
            .all()
        )
        now = datetime.utcnow()
        for row in pending:
            if remaining <= 0:
                break
            row_amount = int(row.amount_minor or 0)
            if row_amount <= 0:
                continue
            if row_amount <= remaining:
                row.status = "requested"
                row.payout_invoice_id = invoice.id
                row.updated_at = now
                remaining -= row_amount
                db.add(row)
            else:
                # Split: reserve part, leave remainder pending.
                leftover = row_amount - remaining
                row.amount_minor = remaining
                row.status = "requested"
                row.payout_invoice_id = invoice.id
                row.updated_at = now
                db.add(row)
                split = SalesCommission(
                    sales_rep_id=row.sales_rep_id,
                    sales_customer_id=row.sales_customer_id,
                    org_id=row.org_id,
                    invoice_id=row.invoice_id,
                    subscription_id=row.subscription_id,
                    amount_minor=leftover,
                    currency=row.currency or "GBP",
                    kind=row.kind,
                    status="pending",
                    note=(row.note or "") + " (split remainder)" if row.note else "Split remainder",
                    created_at=now,
                    updated_at=now,
                )
                db.add(split)
                remaining = 0
        if remaining > 0:
            raise SalesRepError("Not enough available commission for this invoice amount.")

    @staticmethod
    def _release_commissions(db: Session, *, invoice_id: str) -> None:
        rows = (
            db.execute(
                select(SalesCommission).where(SalesCommission.payout_invoice_id == str(invoice_id))
            )
            .scalars()
            .all()
        )
        now = datetime.utcnow()
        for row in rows:
            if row.status == "requested":
                row.status = "pending"
            row.payout_invoice_id = None
            row.updated_at = now
            db.add(row)

    @staticmethod
    def invoice_to_dict(inv: SalesPayoutInvoice, *, include_snapshot: bool = True) -> dict[str, Any]:
        snapshot = None
        if include_snapshot and inv.payout_snapshot_json:
            try:
                snapshot = json.loads(inv.payout_snapshot_json)
            except Exception:  # noqa: BLE001
                snapshot = None
        return {
            "id": inv.id,
            "sales_rep_id": inv.sales_rep_id,
            "invoice_number": inv.invoice_number,
            "amount_minor": int(inv.amount_minor or 0),
            "amount_display": SalesPayoutService.format_gbp(int(inv.amount_minor or 0)),
            "currency": inv.currency or "GBP",
            "status": inv.status,
            "notes": inv.notes,
            "reject_reason": inv.reject_reason,
            "payout_snapshot": snapshot,
            "payout_method_summary": SalesPayoutService.payout_method_summary(snapshot or {}),
            "submitted_at": inv.submitted_at.isoformat() if inv.submitted_at else None,
            "resolved_at": inv.resolved_at.isoformat() if inv.resolved_at else None,
            "resolved_by_admin_id": inv.resolved_by_admin_id,
        }

    @staticmethod
    def list_invoices(db: Session, *, rep_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        q = select(SalesPayoutInvoice).order_by(SalesPayoutInvoice.submitted_at.desc())
        if rep_id:
            q = q.where(SalesPayoutInvoice.sales_rep_id == str(rep_id))
        if status:
            q = q.where(SalesPayoutInvoice.status == str(status))
        return [SalesPayoutService.invoice_to_dict(r) for r in db.execute(q).scalars().all()]

    @staticmethod
    def get_invoice(db: Session, *, invoice_id: str) -> SalesPayoutInvoice | None:
        return db.execute(
            select(SalesPayoutInvoice).where(SalesPayoutInvoice.id == str(invoice_id))
        ).scalar_one_or_none()

    @staticmethod
    def create_invoice(
        db: Session,
        *,
        rep: SalesRep,
        amount_minor: int,
        notes: str | None = None,
    ) -> SalesPayoutInvoice:
        if not rep.is_active:
            raise SalesRepError("This sales account is frozen.")
        try:
            amount = int(amount_minor)
        except (TypeError, ValueError) as exc:
            raise SalesRepError("Invoice amount must be a whole number of pence.") from exc
        if amount <= 0:
            raise SalesRepError("Invoice amount must be greater than zero.")
        available = SalesPayoutService.available_minor(db, rep_id=rep.id)
        if amount > available:
            raise SalesRepError(
                f"Invoice amount ({SalesPayoutService.format_gbp(amount)}) cannot exceed "
                f"available commission ({SalesPayoutService.format_gbp(available)})."
            )
        SalesPayoutService.assert_payout_ready(rep)
        now = datetime.utcnow()
        inv = SalesPayoutInvoice(
            sales_rep_id=rep.id,
            invoice_number=SalesPayoutService._next_invoice_number(db),
            amount_minor=amount,
            currency="GBP",
            status=STATUS_SUBMITTED,
            notes=(str(notes or "").strip() or None),
            payout_snapshot_json=json.dumps(SalesPayoutService.payout_snapshot(rep)),
            submitted_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(inv)
        db.flush()
        SalesPayoutService._reserve_commissions(db, rep=rep, invoice=inv, amount_minor=amount)
        db.commit()
        db.refresh(inv)
        SalesPayoutService._send_email(db, rep=rep, invoice=inv, template_key="sales_payout_invoice_received")
        return inv

    @staticmethod
    def approve_and_pay(
        db: Session,
        *,
        invoice: SalesPayoutInvoice,
        admin_id: str | None = None,
    ) -> SalesPayoutInvoice:
        if invoice.status != STATUS_SUBMITTED:
            raise SalesRepError("Only submitted invoices can be approved and paid.")
        now = datetime.utcnow()
        rows = (
            db.execute(
                select(SalesCommission).where(SalesCommission.payout_invoice_id == invoice.id)
            )
            .scalars()
            .all()
        )
        for row in rows:
            row.status = "paid"
            row.updated_at = now
            db.add(row)
        invoice.status = STATUS_PAID
        invoice.resolved_at = now
        invoice.resolved_by_admin_id = str(admin_id) if admin_id else None
        invoice.updated_at = now
        db.add(invoice)
        db.commit()
        db.refresh(invoice)
        rep = db.get(SalesRep, invoice.sales_rep_id)
        if rep is not None:
            SalesPayoutService._send_email(db, rep=rep, invoice=invoice, template_key="sales_payout_invoice_paid")
        return invoice

    @staticmethod
    def reject_invoice(
        db: Session,
        *,
        invoice: SalesPayoutInvoice,
        admin_id: str | None = None,
        reason: str | None = None,
    ) -> SalesPayoutInvoice:
        if invoice.status != STATUS_SUBMITTED:
            raise SalesRepError("Only submitted invoices can be rejected.")
        SalesPayoutService._release_commissions(db, invoice_id=invoice.id)
        now = datetime.utcnow()
        invoice.status = STATUS_REJECTED
        invoice.reject_reason = (str(reason or "").strip() or None)
        invoice.resolved_at = now
        invoice.resolved_by_admin_id = str(admin_id) if admin_id else None
        invoice.updated_at = now
        db.add(invoice)
        db.commit()
        db.refresh(invoice)
        return invoice

    @staticmethod
    def _send_email(db: Session, *, rep: SalesRep, invoice: SalesPayoutInvoice, template_key: str) -> None:
        try:
            from app.services.email_template_service import EmailTemplateService
            from app.services.platform_sender_email_service import PlatformSenderEmailService
            from app.services.smtp_mailer_service import SmtpMailerService
            from app.services.transactional_email_service import TransactionalEmailService, substitute_placeholders

            user = db.execute(select(User).where(User.id == rep.user_id)).scalar_one_or_none()
            to_email = (user.email if user else "") or ""
            if not to_email:
                return
            snapshot = {}
            if invoice.payout_snapshot_json:
                try:
                    snapshot = json.loads(invoice.payout_snapshot_json)
                except Exception:  # noqa: BLE001
                    snapshot = {}
            variables = {
                "name": rep.name or to_email,
                "company_name": rep.company_name or rep.name or "",
                "invoice_number": invoice.invoice_number,
                "amount": SalesPayoutService.format_gbp(int(invoice.amount_minor or 0)),
                "currency": invoice.currency or "GBP",
                "submitted_at": invoice.submitted_at.strftime("%d %b %Y") if invoice.submitted_at else "",
                "paid_at": invoice.resolved_at.strftime("%d %b %Y") if invoice.resolved_at else "",
                "payout_method_summary": SalesPayoutService.payout_method_summary(snapshot),
                "status": invoice.status,
            }
            EmailTemplateService.ensure_system_templates(db)
            subject_tpl, body_tpl, enabled = TransactionalEmailService.load_template_fields(
                db, template_key=template_key
            )
            if not enabled or not (subject_tpl or "").strip() or not (body_tpl or "").strip():
                return
            subject = substitute_placeholders(subject_tpl, variables)
            body = substitute_placeholders(body_tpl, variables)
            outbound = PlatformSenderEmailService.resolve_outbound(db, "sales") or {}
            SmtpMailerService.send_html(
                db,
                to_addr=to_email,
                subject=subject,
                body=body,
                from_email=outbound.get("from_email"),
                from_name=outbound.get("from_name"),
                smtp_username=outbound.get("smtp_username"),
                smtp_password=outbound.get("smtp_password"),
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to send %s for payout invoice %s", template_key, invoice.id)
