def test_public_legal_page(app_client):
    from app.core.database import get_sessionmaker
    from app.services.legal_page_service import LegalPageService

    with get_sessionmaker()() as db:
        LegalPageService.ensure_defaults(db)
        LegalPageService.update_page(
            db,
            "terms",
            title="Terms & Conditions",
            meta_description="Test terms",
            body="<p>Hello legal world</p>",
            is_published=True,
        )

    r = app_client.get("/legal-pages/terms")
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Terms & Conditions"
    assert "Hello legal world" in body["body"]


def test_admin_legal_pages_list_requires_auth(app_client):
    r = app_client.get("/admin/legal-pages")
    assert r.status_code == 401
