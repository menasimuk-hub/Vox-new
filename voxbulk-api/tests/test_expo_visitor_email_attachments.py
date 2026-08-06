"""Expo visitor catalogue email must attach requested files."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.expo.expo_email_service import ExpoEmailService, _email_attachments


def test_email_attachments_reads_stored_pdf(tmp_path: Path, monkeypatch):
    root = tmp_path / "data" / "expo-assets" / "org1"
    root.mkdir(parents=True)
    pdf = root / "solar.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    import app.services.expo.asset_storage_service as store

    monkeypatch.setattr(store, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(store, "EXPO_ASSETS_ROOT", tmp_path / "data" / "expo-assets")

    assets = [
        {
            "id": "a1",
            "title": "300W Solar Panel",
            "storage_path": "data/expo-assets/org1/solar.pdf",
            "original_filename": "solar.pdf",
        }
    ]
    atts = _email_attachments(assets)
    assert len(atts) == 1
    assert atts[0]["filename"] == "solar.pdf"
    assert atts[0]["content"].startswith(b"%PDF")
    assert atts[0]["maintype"] == "application"
    assert atts[0]["subtype"] == "pdf"


def test_send_visitor_catalogue_passes_attachments(monkeypatch):
    booth = MagicMock()
    booth.company_display_name = "Acme"
    booth.name = "Stand 1"
    booth.notify_mobile = None
    booth.company_website = None
    booth.visitor_contact_email = "stand@acme.test"
    booth.representative_contacts_json = None
    booth.offer_config_json = None

    lead = MagicMock()
    lead.id = "lead-1"
    lead.visitor_email = "visitor@example.com"
    lead.name = "Sam"
    lead.offer_interested = False

    assets = [{"id": "a1", "title": "Spec", "url": "https://api.example/x", "storage_path": "data/expo-assets/o/a.pdf"}]
    fake_atts = [{"filename": "a.pdf", "content": b"x", "maintype": "application", "subtype": "pdf"}]

    monkeypatch.setattr(
        "app.services.expo.expo_email_service._email_attachments",
        lambda _assets: fake_atts,
    )
    monkeypatch.setattr(
        ExpoEmailService,
        "_smtp_from",
        staticmethod(lambda _db: {"from_email": "from@x", "from_name": "X", "smtp_username": None, "smtp_password": None}),
    )

    captured = {}

    def _send(**kwargs):
        captured.update(kwargs)
        return True, None

    with patch(
        "app.services.expo.expo_email_service.TransactionalEmailService.send_templated_optional",
        side_effect=lambda *a, **k: _send(**k),
    ):
        ok = ExpoEmailService.send_visitor_catalogue(MagicMock(), booth=booth, lead=lead, assets=assets)

    assert ok is True
    assert captured.get("attachments") == fake_atts
    assert captured.get("to_email") == "visitor@example.com"
