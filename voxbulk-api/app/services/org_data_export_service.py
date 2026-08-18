"""Organisation DSAR / portability ZIP — profile, team, consent, audit, campaign metadata."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.organisation_ai_config import OrganisationComplianceConfig
from app.models.organisation_invite import OrganisationInvite
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.user import User
from app.schemas.data_export import DataExportManifest
from app.services.email_preference_service import EmailPreferenceService
from app.services.org_audit_service import OrgAuditService
from app.services.org_opt_out_service import OrgOptOutService
from app.services.org_rbac import OrgRbacService
from app.services.org_team_service import OrgTeamService

EXPORT_VERSION = "1"
MAX_ORDERS = 2000
MAX_RECIPIENTS = 10000
MAX_AUDIT = 500

_README = """VOXBULK organisation data export
=================================

This ZIP is a copy of data this organisation holds in VoxBulk (UK GDPR portability / DSAR helper).

Included
- organisation.json — public profile and billing balances (no integration secrets)
- memberships.json — team members (email, role, status)
- pending_invites.json — outstanding invites (no invite tokens)
- consent.json — WhatsApp opt-outs, org compliance defaults, email preference toggles
- audit_summary.json — recent organisation activity log
- campaigns.json — survey / interview order metadata and recipient contact fields

Not included
- Passwords, MFA secrets, or decrypted API credentials
- CRM / ATS stored config JSON
- Full survey answers, interview recordings, transcripts, CVs, or report payloads
- Third-party media that is not stored as metadata in VoxBulk

Recordings and full results stay with the original campaign screens unless already stored here.
"""


def _json_default(obj: Any) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, default=_json_default, indent=2, ensure_ascii=False).encode("utf-8")


class OrgDataExportService:
    @staticmethod
    def _org_profile(org: Organisation) -> dict[str, Any]:
        return {
            "id": org.id,
            "name": org.name,
            "created_at": org.created_at,
            "is_suspended": bool(org.is_suspended),
            "onboarding_state": org.onboarding_state,
            "address_line1": org.address_line1,
            "address_line2": org.address_line2,
            "city": org.city,
            "county_state": org.county_state,
            "postcode": org.postcode,
            "country": org.country,
            "country_code": org.country_code,
            "contact_name": org.contact_name,
            "contact_email": org.contact_email,
            "contact_phone": org.contact_phone,
            "website": org.website,
            "billing_currency": org.billing_currency,
            "survey_credits_balance": org.survey_credits_balance,
            "interview_credits_balance": org.interview_credits_balance,
            "feedback_credits_balance": org.feedback_credits_balance,
            "wallet_balance_pence": org.wallet_balance_pence,
            "deletion_status": org.deletion_status,
            "deletion_requested_at": org.deletion_requested_at,
            "logo_present": bool(org.logo_storage_key),
        }

    @staticmethod
    def _pending_invites(db: Session, org_id: str) -> list[dict[str, Any]]:
        now = datetime.utcnow()
        rows = list(
            db.execute(
                select(OrganisationInvite)
                .where(
                    OrganisationInvite.org_id == org_id,
                    OrganisationInvite.consumed_at.is_(None),
                )
                .order_by(OrganisationInvite.created_at.desc())
                .limit(200)
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": i.id,
                "email": i.email,
                "role": i.role or "member",
                "created_at": i.created_at,
                "expires_at": i.expires_at,
                "is_expired": bool(i.expires_at and i.expires_at < now),
            }
            for i in rows
        ]

    @staticmethod
    def _campaigns(db: Session, org_id: str) -> dict[str, Any]:
        orders = list(
            db.execute(
                select(ServiceOrder)
                .where(ServiceOrder.org_id == org_id)
                .order_by(ServiceOrder.created_at.desc())
                .limit(MAX_ORDERS)
            )
            .scalars()
            .all()
        )
        order_ids = [o.id for o in orders]
        recipients: list[ServiceOrderRecipient] = []
        if order_ids:
            recipients = list(
                db.execute(
                    select(ServiceOrderRecipient)
                    .where(ServiceOrderRecipient.order_id.in_(order_ids))
                    .order_by(ServiceOrderRecipient.created_at.asc())
                    .limit(MAX_RECIPIENTS)
                )
                .scalars()
                .all()
            )
        by_order: dict[str, list[dict[str, Any]]] = {oid: [] for oid in order_ids}
        for rec in recipients:
            bucket = by_order.get(rec.order_id)
            if bucket is None:
                continue
            bucket.append(
                {
                    "id": rec.id,
                    "row_number": rec.row_number,
                    "name": rec.name,
                    "phone": rec.phone,
                    "email": rec.email,
                    "status": rec.status,
                    "created_at": rec.created_at,
                    "has_cv_on_file": bool(rec.cv_storage_key or rec.cv_filename),
                    "has_result_payload": bool(rec.result_json),
                }
            )
        campaigns = []
        for order in orders:
            campaigns.append(
                {
                    "id": order.id,
                    "service_code": order.service_code,
                    "title": order.title,
                    "reference_id": order.reference_id,
                    "campaign_id": order.campaign_id,
                    "status": order.status,
                    "payment_status": order.payment_status,
                    "recipient_count": order.recipient_count,
                    "run_mode": order.run_mode,
                    "created_at": order.created_at,
                    "started_at": order.started_at,
                    "completed_at": order.completed_at,
                    "has_report_payload": bool(order.report_json),
                    "recipients": by_order.get(order.id) or [],
                }
            )
        return {
            "truncated_orders": len(orders) >= MAX_ORDERS,
            "truncated_recipients": len(recipients) >= MAX_RECIPIENTS,
            "campaigns": campaigns,
        }

    @staticmethod
    def _compliance_defaults(db: Session, org_id: str) -> dict[str, Any]:
        row = db.execute(
            select(OrganisationComplianceConfig).where(OrganisationComplianceConfig.org_id == org_id)
        ).scalar_one_or_none()
        if row is None:
            return {}
        return {
            "privacy_notice_url": row.privacy_notice_url,
            "contact_email": row.contact_email,
            "dpo_email": row.dpo_email,
            "opt_out_enabled": bool(row.opt_out_enabled),
            "lawful_basis_default": row.lawful_basis_default,
            "special_category_data_present_default": bool(row.special_category_data_present_default),
            "article9_condition_default": row.article9_condition_default,
            "privacy_intro_text_default": row.privacy_intro_text_default,
            "collect_minimal_data_default": bool(row.collect_minimal_data_default),
            "retention_days_messages": row.retention_days_messages,
            "retention_days_responses": row.retention_days_responses,
            "retention_days_recordings": row.retention_days_recordings,
            "retention_days_transcripts": row.retention_days_transcripts,
        }

    @staticmethod
    def _consent(db: Session, *, org_id: str, members: list[dict[str, Any]]) -> dict[str, Any]:
        prefs = []
        for mem in members:
            uid = str(mem.get("user_id") or "")
            if not uid:
                continue
            prefs.append(
                {
                    "user_id": uid,
                    "email": mem.get("email"),
                    "preferences": EmailPreferenceService.get_prefs(db, uid),
                }
            )
        return {
            "opt_outs": OrgOptOutService.list_opt_outs(db, org_id),
            "org_compliance_defaults": OrgDataExportService._compliance_defaults(db, org_id),
            "email_preferences": prefs,
        }

    @staticmethod
    def build_zip(db: Session, *, org_id: str, actor_user_id: str) -> tuple[bytes, str]:
        OrgRbacService.assert_can_export_org_data(db, org_id=org_id, user_id=actor_user_id)
        org = db.get(Organisation, org_id)
        if org is None:
            raise ValueError("Organisation not found")

        members = OrgTeamService.list_members(db, org_id)
        generated_at = datetime.utcnow()
        files = [
            "README.txt",
            "manifest.json",
            "organisation.json",
            "memberships.json",
            "pending_invites.json",
            "consent.json",
            "audit_summary.json",
            "campaigns.json",
        ]
        manifest = DataExportManifest(
            export_version=EXPORT_VERSION,
            generated_at=generated_at,
            org_id=org_id,
            requested_by_user_id=actor_user_id,
            files=files,
            notes=[
                "Integration credentials and campaign result payloads are omitted.",
                "Invite tokens are omitted.",
            ],
        )
        payload = {
            "README.txt": _README.encode("utf-8"),
            "manifest.json": _json_bytes(manifest.model_dump()),
            "organisation.json": _json_bytes(OrgDataExportService._org_profile(org)),
            "memberships.json": _json_bytes(members),
            "pending_invites.json": _json_bytes(OrgDataExportService._pending_invites(db, org_id)),
            "consent.json": _json_bytes(OrgDataExportService._consent(db, org_id=org_id, members=members)),
            "audit_summary.json": _json_bytes(OrgAuditService.list_events(db, org_id, limit=MAX_AUDIT)),
            "campaigns.json": _json_bytes(OrgDataExportService._campaigns(db, org_id)),
        }

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name, content in payload.items():
                zf.writestr(name, content)
        blob = buf.getvalue()

        actor = db.get(User, actor_user_id)
        OrgAuditService.record_for_user(
            db,
            org_id=org_id,
            user=actor,
            action="data.export_downloaded",
            detail=f"ZIP {len(blob)} bytes",
        )
        stamp = generated_at.strftime("%Y%m%d")
        filename = f"voxbulk-org-export-{stamp}.zip"
        return blob, filename
