"""Interview Excel contacts template download."""
from __future__ import annotations

from app.services.interview_intake_service import parse_contacts_csv_relaxed_from_bytes
from app.services.platform_catalog_service import ServiceOrderService


def test_interview_recipient_template_xlsx_preserves_arabic_and_phones():
    raw = ServiceOrderService.recipient_template_xlsx(for_interview=True)
    assert raw[:2] == b"PK"
    rows = parse_contacts_csv_relaxed_from_bytes(raw, "voxbulk-interview-contacts-template.xlsx")
    assert len(rows) >= 3
    names = {r["name"] for r in rows}
    assert "قصي" in names
    assert "Sarah Ahmed" in names
    phones = {r["phone"] for r in rows}
    assert "+447700900123" in phones
    assert "+447954823445" in phones
    assert "07700900555" in phones
    # Phones must not be scientific notation
    for r in rows:
        assert "E+" not in str(r["phone"] or "").upper()
        assert "e+" not in str(r["phone"] or "")
