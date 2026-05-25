import io
import uuid
import zipfile

import pytest
from docx import Document
from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder
from app.models.user import User
from app.services.interview_intake_service import intake_cv_files, intake_mixed_files
from app.services.platform_catalog_service import ServiceOrderService


def _docx_bytes(name_line: str) -> bytes:
    doc = Document()
    doc.add_paragraph(name_line)
    doc.add_paragraph("Email: alex@example.com")
    doc.add_paragraph("Phone: +44 7700 900123")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _zip_with_docx(files: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for fname, data in files:
            zf.writestr(fname, data)
    return buf.getvalue()


@pytest.fixture()
def db_session():
    from app.core.database import Base, get_engine, get_sessionmaker
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def interview_order(db_session: Session):
    org = Organisation(name="Test Org")
    user = User(email=f"intake-{uuid.uuid4().hex[:8]}@test.com", password_hash="x", is_active=True)
    db_session.add(org)
    db_session.add(user)
    db_session.flush()
    order = ServiceOrderService.create_order(
        db_session,
        org_id=org.id,
        user_id=user.id,
        service_code="interview",
        title="Interview draft",
        config={},
    )
    return order


def test_intake_cv_zip_creates_recipient_rows(db_session: Session, interview_order: ServiceOrder):
    zip_bytes = _zip_with_docx(
        [
            ("jane_doe_cv.docx", _docx_bytes("Jane Doe")),
            ("john_smith.docx", _docx_bytes("John Smith")),
        ]
    )
    result = intake_cv_files(db_session, interview_order, [("cvs.zip", zip_bytes)])
    assert result["parsed_count"] == 2
    assert result["recipient_count"] == 2
    assert len(result["recipients"]) == 2
    names = {r["name"] for r in result["recipients"]}
    assert "Jane Doe" in names or "jane doe".title() in names
    assert result["summary"]["total"] == 2


def test_intake_mixed_zip_and_csv(db_session: Session, interview_order: ServiceOrder):
    import csv
    import io

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["name", "phone", "email"])
    writer.writerow(["Alice Example", "+447700900111", "alice@example.com"])
    csv_bytes = buf.getvalue().encode("utf-8")
    zip_bytes = _zip_with_docx([("bob_cv.docx", _docx_bytes("Bob Example"))])
    result = intake_mixed_files(
        db_session,
        interview_order,
        [("list.csv", csv_bytes), ("cvs.zip", zip_bytes)],
    )
    assert result["recipient_count"] >= 2
    assert len(result["recipients"]) >= 2
