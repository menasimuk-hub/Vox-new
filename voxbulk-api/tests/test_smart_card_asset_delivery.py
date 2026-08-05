"""Smart Card catalogue delivery — asset lookup, public URLs, lead tracking, email attachments."""

import uuid
from pathlib import Path

import pytest

from app.core.database import get_sessionmaker
from app.models.organisation import Organisation
from app.models.smart_card import (
    SmartCardAsset,
    SmartCardCategory,
    SmartCardLead,
    SmartCardProduct,
    SmartCardRepresentative,
)
from app.services.smart_card.asset_delivery_service import (
    asset_filename,
    build_delivery_rows,
    email_attachments,
    load_assets_for_products,
    mark_lead_asset_opened,
    mark_lead_assets_sent,
    supports_document_send,
)
from app.services.smart_card.asset_storage_service import SMART_CARD_ASSETS_ROOT


@pytest.fixture()
def db():
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def _seed_catalogue(db) -> tuple[SmartCardRepresentative, list[SmartCardProduct], list[SmartCardAsset]]:
    org = Organisation(name=f"Asset Org {uuid.uuid4().hex[:6]}")
    db.add(org)
    db.flush()
    rep = SmartCardRepresentative(
        org_id=org.id,
        name="Dana Rep",
        email=f"rep-{uuid.uuid4().hex[:6]}@test.local",
        qr_token=f"org-assets-{uuid.uuid4().hex[:16]}",
        status="active",
    )
    category = SmartCardCategory(org_id=org.id, name="Machines", sort_order=10)
    db.add_all([rep, category])
    db.flush()

    products = []
    for i in range(2):
        product = SmartCardProduct(
            org_id=org.id,
            category_id=category.id,
            name=f"Product {i + 1}",
            sort_order=10 * (i + 1),
        )
        db.add(product)
        db.flush()
        products.append(product)

    assets = [
        SmartCardAsset(
            org_id=org.id,
            product_id=products[0].id,
            category_id=category.id,
            title="Product 1 spec sheet",
            kind="pdf",
            purpose="product",
            storage_path="data/smart-card-assets/demo/product-1.pdf",
            original_filename="product-1.pdf",
            sort_order=10,
        ),
        SmartCardAsset(
            org_id=org.id,
            product_id=products[1].id,
            category_id=category.id,
            title="Product 2 brochure",
            kind="pdf",
            purpose="product",
            external_url="https://cdn.example.com/product-2.pdf",
            sort_order=20,
        ),
        SmartCardAsset(
            org_id=org.id,
            product_id=None,
            category_id=category.id,
            title="Machines catalogue",
            kind="pdf",
            purpose="catalogue",
            storage_path="data/smart-card-assets/demo/catalogue.pdf",
            sort_order=30,
        ),
    ]
    db.add_all(assets)
    db.commit()
    return rep, products, assets


def test_selected_product_pulls_its_asset_and_the_category_catalogue(db):
    rep, products, _ = _seed_catalogue(db)

    rows = load_assets_for_products(db, org_id=rep.org_id, product_ids=[products[0].id])

    titles = [r["title"] for r in rows]
    assert "Product 1 spec sheet" in titles
    assert "Machines catalogue" in titles
    assert "Product 2 brochure" not in titles


def test_no_products_selected_delivers_nothing(db):
    rep, _, _ = _seed_catalogue(db)

    assert load_assets_for_products(db, org_id=rep.org_id, product_ids=[]) == []
    assert load_assets_for_products(db, org_id=rep.org_id, product_ids=["", None]) == []


def test_products_from_another_org_are_never_delivered(db):
    rep, products, _ = _seed_catalogue(db)
    other_org = Organisation(name=f"Other Org {uuid.uuid4().hex[:6]}")
    db.add(other_org)
    db.commit()

    assert load_assets_for_products(db, org_id=other_org.id, product_ids=[products[0].id]) == []


def test_delivery_rows_build_absolute_tracked_urls(db):
    rep, products, _ = _seed_catalogue(db)

    rows = build_delivery_rows(
        db,
        org_id=rep.org_id,
        qr_token=rep.qr_token,
        lead_id="lead-123",
        product_ids=[products[0].id],
    )

    stored = next(r for r in rows if r["title"] == "Product 1 spec sheet")
    assert stored["url"].startswith("http")
    assert f"/public/smart-card/{rep.qr_token}/assets/{stored['id']}" in stored["url"]
    assert stored["url"].endswith("lead_id=lead-123")
    assert stored["filename"] == "product-1.pdf"


def test_external_asset_without_lead_keeps_its_own_url(db):
    rep, products, _ = _seed_catalogue(db)

    rows = build_delivery_rows(
        db,
        org_id=rep.org_id,
        qr_token=rep.qr_token,
        lead_id=None,
        product_ids=[products[1].id],
    )

    external = next(r for r in rows if r["title"] == "Product 2 brochure")
    assert external["url"] == "https://cdn.example.com/product-2.pdf"


def test_external_asset_with_lead_is_proxied_for_open_tracking(db):
    rep, products, _ = _seed_catalogue(db)

    rows = build_delivery_rows(
        db,
        org_id=rep.org_id,
        qr_token=rep.qr_token,
        lead_id="lead-9",
        product_ids=[products[1].id],
    )

    external = next(r for r in rows if r["title"] == "Product 2 brochure")
    assert "/public/smart-card/" in external["url"]


def test_asset_filename_falls_back_to_title_and_suffix():
    assert asset_filename({"title": "Spec", "storage_path": "a/b/x.pdf"}) == "Spec.pdf"
    assert asset_filename({"original_filename": "deep/path/real name.pdf"}) == "real name.pdf"


def test_supports_document_send_recognises_files_and_kinds():
    assert supports_document_send({"storage_path": "a/b.pdf"}) is True
    assert supports_document_send({"kind": "spreadsheet"}) is True
    assert supports_document_send({"kind": "video", "storage_path": "a/b.mp4"}) is False


def test_lead_records_sent_assets_without_duplicates(db):
    rep, products, _ = _seed_catalogue(db)
    lead = SmartCardLead(org_id=rep.org_id, representative_id=rep.id, name="Ana")
    db.add(lead)
    db.flush()
    rows = build_delivery_rows(
        db, org_id=rep.org_id, qr_token=rep.qr_token, lead_id=lead.id, product_ids=[products[0].id]
    )

    mark_lead_assets_sent(db, lead=lead, assets=rows)
    mark_lead_assets_sent(db, lead=lead, assets=rows)
    db.commit()

    import json

    payload = json.loads(lead.assets_sent_json)
    assert len(payload["assets"]) == len(rows)
    assert all(item["sent_at"] for item in payload["assets"])


def test_marking_an_open_is_recorded_once(db):
    rep, _, assets = _seed_catalogue(db)
    lead = SmartCardLead(org_id=rep.org_id, representative_id=rep.id, name="Ana")
    db.add(lead)
    db.flush()

    assert mark_lead_asset_opened(db, lead=lead, asset_id=assets[0].id) is True
    assert mark_lead_asset_opened(db, lead=lead, asset_id=assets[0].id) is False
    db.commit()

    import json

    assert len(json.loads(lead.assets_sent_json)["assets_opened"]) == 1


def test_email_attachments_read_stored_files_and_skip_external(db, tmp_path):
    rep, products, _ = _seed_catalogue(db)
    stored = SMART_CARD_ASSETS_ROOT / "demo" / "product-1.pdf"
    stored.parent.mkdir(parents=True, exist_ok=True)
    stored.write_bytes(b"%PDF-1.4 fake")
    try:
        rows = build_delivery_rows(
            db,
            org_id=rep.org_id,
            qr_token=rep.qr_token,
            lead_id=None,
            product_ids=[products[0].id, products[1].id],
        )
        attachments = email_attachments(rows)
    finally:
        stored.unlink(missing_ok=True)

    names = [a["filename"] for a in attachments]
    assert "product-1.pdf" in names
    assert all(a["content"] for a in attachments)
    assert all(a["maintype"] == "application" and a["subtype"] == "pdf" for a in attachments)
    # The external brochure has no local file, so it stays link-only.
    assert not any("brochure" in str(n).lower() for n in names)


def test_email_attachments_ignore_paths_outside_the_asset_root(db):
    rows = [{"id": "x", "storage_path": "../../etc/passwd", "filename": "passwd"}]

    assert email_attachments(rows) == []


def test_missing_file_does_not_raise(db):
    rows = [{"id": "x", "storage_path": str(Path("data/smart-card-assets/nope.pdf")), "filename": "n.pdf"}]

    assert email_attachments(rows) == []
