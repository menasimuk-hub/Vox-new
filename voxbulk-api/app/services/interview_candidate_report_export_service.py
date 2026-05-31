"""Export per-candidate interview report as HTML or PDF."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.career_cv_storage_service import resolve_cv_path
from app.services.interview_report_data_service import InterviewCandidateReportService
from app.services.interview_report_template import build_candidate_report_html
from app.services.invoice_pdf_service import render_html_to_pdf_bytes

logger = logging.getLogger(__name__)


def _read_cv_text(recipient: ServiceOrderRecipient) -> str | None:
    text = (recipient.cv_text or "").strip()
    if text:
        return text
    path = resolve_cv_path(recipient.cv_storage_key or "")
    if path is None or not path.is_file():
        return None
    if path.suffix.lower() in {".txt", ".md"}:
        try:
            return path.read_text(encoding="utf-8", errors="replace")[:12000]
        except Exception:
            return None
    return None


def _merge_pdf_bytes(report_pdf: bytes, cv_path: Path) -> bytes:
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        logger.warning("interview_report_pypdf_missing")
        return report_pdf
    if cv_path.suffix.lower() != ".pdf":
        return report_pdf
    try:
        writer = PdfWriter()
        for reader in (PdfReader(__import__("io").BytesIO(report_pdf)), PdfReader(str(cv_path))):
            for page in reader.pages:
                writer.add_page(page)
        out = __import__("io").BytesIO()
        writer.write(out)
        return out.getvalue()
    except Exception as exc:
        logger.warning("interview_report_pdf_merge_failed", extra={"error": str(exc)})
        return report_pdf


class InterviewCandidateReportExportService:
    @staticmethod
    def html(
        db: Session,
        order: ServiceOrder,
        recipient: ServiceOrderRecipient,
        *,
        include_cv: bool = False,
    ) -> str:
        payload = InterviewCandidateReportService.build_payload(db, order, recipient)
        cv_text = _read_cv_text(recipient) if include_cv else None
        return build_candidate_report_html(payload, cv_text=cv_text, for_pdf=False)

    @staticmethod
    def pdf(
        db: Session,
        order: ServiceOrder,
        recipient: ServiceOrderRecipient,
        *,
        include_cv: bool = False,
    ) -> bytes:
        payload = InterviewCandidateReportService.build_payload(db, order, recipient)
        cv_text = _read_cv_text(recipient) if include_cv and not recipient.cv_storage_key else None
        pdf_html = build_candidate_report_html(payload, cv_text=cv_text, for_pdf=True)
        pdf_bytes = render_html_to_pdf_bytes(pdf_html)        if include_cv and recipient.cv_storage_key:
            cv_path = resolve_cv_path(recipient.cv_storage_key)
            if cv_path and cv_path.is_file() and cv_path.suffix.lower() == ".pdf":
                return _merge_pdf_bytes(pdf_bytes, cv_path)
        return pdf_bytes
