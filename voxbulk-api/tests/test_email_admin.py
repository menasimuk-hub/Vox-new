from __future__ import annotations

from unittest.mock import patch

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.email_template_service import EMAIL_TEMPLATE_KEYS, EmailTemplateService


def _bootstrap_super(app_client):
    with get_sessionmaker()() as db:
        org = Organisation(name="Email Org")
        db.add(org)
        db.flush()
        admin = User(
            email="emailadmin@example.com",
            password_hash=hash_password("pass123"),
            is_active=True,
            is_superuser=True,
        )
        db.add(admin)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=admin.id))
        db.commit()
        org_id = org.id

    tok = app_client.post(
        "/auth/token",
        data={"username": "emailadmin@example.com", "password": "pass123", "org_id": org_id},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _seed_templates():
    with get_sessionmaker()() as db:
        for key in EMAIL_TEMPLATE_KEYS:
            if EmailTemplateService.get(db, key=key) is None:
                EmailTemplateService.upsert(db, key=key, subject=f"Subject {key}", body=f"Body {key}", is_enabled=True)


def test_email_smtp_requires_superuser(app_client):
    r = app_client.get("/admin/email/smtp")
    assert r.status_code in (401, 403)


def test_email_smtp_roundtrip_masks_password(app_client):
    headers = _bootstrap_super(app_client)

    r0 = app_client.get("/admin/email/smtp", headers=headers)
    assert r0.status_code == 200
    assert "password" not in r0.json()

    payload = {
        "host": "smtp.example.test",
        "port": 587,
        "username": "smtpuser",
        "password": "super-smtp-pass",
        "from_name": "VOXBULK",
        "from_email": "no-reply@example.test",
        "use_tls": True,
        "use_ssl": False,
        "is_enabled": True,
    }
    r1 = app_client.put("/admin/email/smtp", json=payload, headers=headers)
    assert r1.status_code == 200
    j = r1.json()
    assert j["password_set"] is True
    assert j["configured"] is True
    assert "super-smtp-pass" not in str(j)

    r2 = app_client.get("/admin/email/smtp", headers=headers)
    assert r2.status_code == 200
    j2 = r2.json()
    assert j2["host"] == "smtp.example.test"
    assert j2["username"] == "smtpuser"

    allowed = ("host", "port", "username", "from_name", "from_email", "use_tls", "use_ssl", "is_enabled")
    payload_keep = {k: j2[k] for k in allowed if k in j2}
    r3 = app_client.put("/admin/email/smtp", json=payload_keep, headers=headers)
    assert r3.status_code == 200
    assert r3.json()["password_set"] is True


def test_email_templates_crud(app_client):
    headers = _bootstrap_super(app_client)
    _seed_templates()

    r_list = app_client.get("/admin/email/templates", headers=headers)
    assert r_list.status_code == 200
    rows = r_list.json()
    assert isinstance(rows, list)
    keys = sorted([r["template_key"] for r in rows])
    assert keys == sorted(EMAIL_TEMPLATE_KEYS)

    r_bad = app_client.get("/admin/email/templates/unknown_key", headers=headers)
    assert r_bad.status_code == 404

    r_one = app_client.get("/admin/email/templates/new_user", headers=headers)
    assert r_one.status_code == 200

    body = {"subject": "Welcome!", "body": "Hello,\nWorld.", "is_enabled": False}
    r_put = app_client.put("/admin/email/templates/new_user", json=body, headers=headers)
    assert r_put.status_code == 200
    assert r_put.json()["subject"] == "Welcome!"
    assert r_put.json()["is_enabled"] is False


def test_smtp_test_send_validates_config(app_client):
    headers = _bootstrap_super(app_client)
    r = app_client.post("/admin/email/smtp/test", json={"to": "hi@example.com"}, headers=headers)
    assert r.status_code == 400
    assert "incomplete" in r.json()["detail"].lower() or "smtp" in r.json()["detail"].lower()


def test_email_template_send_test_mocked(app_client):
    headers = _bootstrap_super(app_client)
    _seed_templates()

    app_client.put(
        "/admin/email/smtp",
        json={
            "host": "localhost",
            "port": 1025,
            "username": "",
            "from_name": "Test",
            "from_email": "from@example.com",
            "use_tls": False,
            "use_ssl": False,
            "is_enabled": True,
        },
        headers=headers,
    )

    from app.services.smtp_mailer_service import SmtpMailerService

    with patch.object(SmtpMailerService, "send_html") as spy:
        r = app_client.post(
            "/admin/email/templates/general_notification/send-test",
            json={
                "to": "to@example.com",
                "subject": "Hello {{user_name}}",
                "body": "<p>Hi {{user_name}}, {{message}}</p>",
            },
            headers=headers,
        )
    assert r.status_code == 200
    assert r.json().get("ok") is True
    spy.assert_called_once()
    kwargs = spy.call_args.kwargs
    assert kwargs["to_addr"] == "to@example.com"
    assert kwargs["subject"].startswith("[TEST]")
    assert "Alex Demo" in kwargs["body"]


def test_email_template_send_test_uses_saved_when_draft_empty(app_client):
    headers = _bootstrap_super(app_client)
    _seed_templates()

    app_client.put(
        "/admin/email/smtp",
        json={
            "host": "localhost",
            "port": 1025,
            "username": "",
            "from_name": "Test",
            "from_email": "from@example.com",
            "use_tls": False,
            "use_ssl": False,
            "is_enabled": True,
        },
        headers=headers,
    )
    app_client.put(
        "/admin/email/templates/new_user",
        json={"subject": "Welcome saved", "body": "<p>Saved body for {{user_email}}</p>", "is_enabled": False},
        headers=headers,
    )

    from app.services.smtp_mailer_service import SmtpMailerService

    with patch.object(SmtpMailerService, "send_html") as spy:
        r = app_client.post(
            "/admin/email/templates/new_user/send-test",
            json={"to": "welcome@example.com", "subject": "", "body": ""},
            headers=headers,
        )
    assert r.status_code == 200
    kwargs = spy.call_args.kwargs
    assert "Saved body for welcome@example.com" in kwargs["body"]


def test_smtp_test_send_success_mocked(app_client):
    headers = _bootstrap_super(app_client)
    app_client.put(
        "/admin/email/smtp",
        json={
            "host": "localhost",
            "port": 1025,
            "username": "",
            "from_name": "Test",
            "from_email": "from@example.com",
            "use_tls": False,
            "use_ssl": False,
            "is_enabled": True,
        },
        headers=headers,
    )

    from app.services.smtp_mailer_service import SmtpMailerService

    with patch.object(SmtpMailerService, "send_plain") as spy:
        r = app_client.post("/admin/email/smtp/test", json={"to": "to@example.com"}, headers=headers)
    assert r.status_code == 200
    assert r.json().get("ok") is True
    spy.assert_called_once()


def test_send_templated_optional_uses_admin_template_from_db():
    from app.services.smtp_mailer_service import SmtpMailerService
    from app.services.transactional_email_service import TransactionalEmailService

    with get_sessionmaker()() as db:
        EmailTemplateService.upsert(
            db,
            key="new_invoice",
            subject="Admin invoice {{invoice_number}}",
            body="<p>Custom admin invoice for {{amount}}</p>",
            is_enabled=True,
        )
        with patch.object(SmtpMailerService, "send_html") as spy:
            sent, err = TransactionalEmailService.send_templated_optional(
                db,
                template_key="new_invoice",
                to_email="billing@example.com",
                variables={"invoice_number": "INV-9", "amount": "£10.00"},
            )
        assert sent is True
        assert err is None
        kwargs = spy.call_args.kwargs
        assert kwargs["subject"] == "Admin invoice INV-9"
        assert "Custom admin invoice for £10.00" in kwargs["body"]


def test_invoice_document_render_uses_admin_template_from_db():
    from app.models.billing_invoice import BillingInvoice
    from app.services.invoice_service import InvoiceDocumentService

    with get_sessionmaker()() as db:
        org = Organisation(name="PDF Org")
        db.add(org)
        db.flush()
        EmailTemplateService.upsert(
            db,
            key="invoice_document",
            subject="Doc subject",
            body="<html><body><h1>ADMIN-PDF-MARKER {{invoice_number}}</h1></body></html>",
            is_enabled=True,
        )
        invoice = BillingInvoice(
            org_id=org.id,
            provider="gocardless",
            external_invoice_id="pay:test",
            client_email="bill@example.com",
            amount_gbp_pence=1000,
            currency="GBP",
            status="paid",
            invoice_number="INV-ADMIN-1",
        )
        db.add(invoice)
        db.commit()
        db.refresh(invoice)

        html = InvoiceDocumentService.render_html(db, invoice=invoice, org=org)
        assert "ADMIN-PDF-MARKER INV-ADMIN-1" in html


def test_admin_resend_invoice_email_sends_once(app_client):
    from app.models.billing_invoice import BillingInvoice

    headers = _bootstrap_super(app_client)
    with get_sessionmaker()() as db:
        org = db.execute(select(Organisation).order_by(Organisation.created_at.desc())).scalar_one()
        org_id = org.id
        row = BillingInvoice(
            org_id=org_id,
            provider="gocardless",
            external_invoice_id="payment:PM-RESEND-1",
            client_email="resend@example.com",
            amount_gbp_pence=2500,
            currency="GBP",
            status="paid",
            invoice_number="INV-RESEND-1",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        invoice_id = row.id

    with patch(
        "app.services.billing_event_email_service.ProductEmailTriggers.notify_new_invoice",
        return_value=(True, None),
    ) as send_mock:
        r = app_client.post(
            f"/admin/billing/invoices/{invoice_id}/resend-email",
            headers=headers,
        )
    assert r.status_code == 200
    assert r.json()["sent"] is True
    assert send_mock.call_count == 1


def test_issue_from_payment_existing_invoice_does_not_resend_email():
    from app.models.billing_invoice import BillingInvoice
    from app.services.invoice_service import InvoiceService

    with get_sessionmaker()() as db:
        org = Organisation(name="Existing Invoice Org")
        db.add(org)
        db.flush()
        existing = BillingInvoice(
            org_id=org.id,
            provider="gocardless",
            external_invoice_id="payment:PM-EXISTING",
            client_email="existing@example.com",
            amount_gbp_pence=9900,
            currency="GBP",
            status="paid",
            emailed_at=None,
        )
        db.add(existing)
        db.commit()
        db.refresh(existing)

        with patch(
            "app.services.billing_event_email_service.ProductEmailTriggers.notify_new_invoice",
            return_value=(True, None),
        ) as send_mock:
            invoice, created, sent = InvoiceService.issue_from_payment(
                db,
                org_id=org.id,
                client_email="existing@example.com",
                subtotal_pence=9900,
                currency="GBP",
                description="Plan",
                provider="gocardless",
                external_invoice_id="payment:PM-EXISTING",
            )
        assert invoice.id == existing.id
        assert created is False
        assert sent is False
        assert send_mock.call_count == 0
