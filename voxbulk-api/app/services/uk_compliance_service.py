"""UK GDPR / PECR / DPA 2018 baseline — validation, merge, privacy text."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organisation_ai_config import OrganisationComplianceConfig
from app.models.service_order import ServiceOrder
from app.services.uk_compliance_constants import (
    ARTICLE9_CONDITIONS,
    DEFAULT_RETENTION_DAYS_MESSAGES,
    DEFAULT_RETENTION_DAYS_RECORDINGS,
    DEFAULT_RETENTION_DAYS_RESPONSES,
    DEFAULT_RETENTION_DAYS_TRANSCRIPTS,
    LAWFUL_BASES,
    MESSAGE_PURPOSES,
)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _default_message_purpose(order: ServiceOrder) -> str:
    if order.service_code == "interview":
        return "interview"
    if order.service_code == "survey":
        return "survey"
    return "transactional"


def _org_compliance_row(db: Session, org_id: str) -> OrganisationComplianceConfig | None:
    return db.execute(
        select(OrganisationComplianceConfig).where(OrganisationComplianceConfig.org_id == org_id)
    ).scalar_one_or_none()


def org_compliance_dict(db: Session, org_id: str) -> dict[str, Any]:
    row = _org_compliance_row(db, org_id)
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


def order_compliance_dict(order: ServiceOrder) -> dict[str, Any]:
    try:
        cfg = json.loads(order.config_json or "{}")
    except Exception:
        cfg = {}
    block = cfg.get("compliance")
    return block if isinstance(block, dict) else {}


def merged_compliance(db: Session, order: ServiceOrder) -> dict[str, Any]:
    org = org_compliance_dict(db, order.org_id)
    order_block = order_compliance_dict(order)
    out: dict[str, Any] = {
        "lawful_basis": order_block.get("lawful_basis") or org.get("lawful_basis_default"),
        "message_purpose": order_block.get("message_purpose") or _default_message_purpose(order),
        "special_category_data_present": order_block.get("special_category_data_present")
        if "special_category_data_present" in order_block
        else org.get("special_category_data_present_default", False),
        "article9_condition": order_block.get("article9_condition") or org.get("article9_condition_default"),
        "privacy_notice_url": order_block.get("privacy_notice_url") or org.get("privacy_notice_url"),
        "contact_email": order_block.get("contact_email") or org.get("contact_email"),
        "dpo_email": order_block.get("dpo_email") or org.get("dpo_email"),
        "privacy_intro_text": order_block.get("privacy_intro_text") or org.get("privacy_intro_text_default"),
        "opt_out_enabled": order_block.get("opt_out_enabled")
        if "opt_out_enabled" in order_block
        else org.get("opt_out_enabled", True),
        "collect_minimal_data": order_block.get("collect_minimal_data")
        if "collect_minimal_data" in order_block
        else org.get("collect_minimal_data_default", True),
        "retention_days_messages": order_block.get("retention_days_messages")
        or org.get("retention_days_messages")
        or DEFAULT_RETENTION_DAYS_MESSAGES,
        "retention_days_responses": order_block.get("retention_days_responses")
        or org.get("retention_days_responses")
        or DEFAULT_RETENTION_DAYS_RESPONSES,
        "retention_days_recordings": order_block.get("retention_days_recordings")
        or org.get("retention_days_recordings")
        or DEFAULT_RETENTION_DAYS_RECORDINGS,
        "retention_days_transcripts": order_block.get("retention_days_transcripts")
        or org.get("retention_days_transcripts")
        or DEFAULT_RETENTION_DAYS_TRANSCRIPTS,
    }
    return out


def validate_compliance_block(block: dict[str, Any], *, for_outbound: bool) -> list[str]:
    errors: list[str] = []
    basis = str(block.get("lawful_basis") or "").strip().lower()
    if not basis:
        errors.append("lawful_basis is required")
    elif basis not in LAWFUL_BASES:
        errors.append(f"lawful_basis must be one of: {', '.join(sorted(LAWFUL_BASES))}")

    purpose = str(block.get("message_purpose") or "").strip().lower()
    if not purpose:
        errors.append("message_purpose is required")
    elif purpose not in MESSAGE_PURPOSES:
        errors.append(f"message_purpose must be one of: {', '.join(sorted(MESSAGE_PURPOSES))}")

    if purpose == "direct_marketing" and basis != "consent":
        errors.append("direct_marketing requires lawful_basis consent (PECR)")

    special = bool(block.get("special_category_data_present"))
    art9 = str(block.get("article9_condition") or "").strip().lower() or None
    if special and not art9:
        errors.append("article9_condition is required when special_category_data_present is true")
    if art9 and art9 not in ARTICLE9_CONDITIONS:
        errors.append(f"article9_condition must be one of: {', '.join(sorted(ARTICLE9_CONDITIONS))}")

    url = str(block.get("privacy_notice_url") or "").strip()
    if not url:
        errors.append("privacy_notice_url is required")
    elif not url.startswith(("http://", "https://")):
        errors.append("privacy_notice_url must be an http(s) URL")

    contact = str(block.get("contact_email") or "").strip()
    if not contact:
        errors.append("contact_email is required")
    elif not _EMAIL_RE.match(contact):
        errors.append("contact_email must be a valid email address")

    dpo = str(block.get("dpo_email") or "").strip()
    if dpo and not _EMAIL_RE.match(dpo):
        errors.append("dpo_email must be a valid email address when set")

    if for_outbound and not bool(block.get("opt_out_enabled", True)):
        errors.append("opt_out_enabled must be true for outbound messaging")

    return errors


class UkComplianceService:
    @staticmethod
    def validate_order_for_launch(db: Session, order: ServiceOrder) -> list[str]:
        block = merged_compliance(db, order)
        return validate_compliance_block(block, for_outbound=True)

    @staticmethod
    def validate_order_for_send(db: Session, order: ServiceOrder) -> list[str]:
        return UkComplianceService.validate_order_for_launch(db, order)

    @staticmethod
    def assert_order_launch_allowed(db: Session, order: ServiceOrder) -> None:
        errors = UkComplianceService.validate_order_for_launch(db, order)
        if errors:
            raise ValueError(
                "UK compliance checks failed before launch: " + "; ".join(errors)
            )

    @staticmethod
    def readiness_summary(db: Session, order: ServiceOrder) -> dict[str, Any]:
        block = merged_compliance(db, order)
        errors = validate_compliance_block(block, for_outbound=True)
        return {
            "ok": len(errors) == 0,
            "errors": errors,
            "compliance": block,
        }

    @staticmethod
    def privacy_footer_text(block: dict[str, Any]) -> str:
        parts: list[str] = []
        intro = str(block.get("privacy_intro_text") or "").strip()
        if intro:
            parts.append(intro)
        url = str(block.get("privacy_notice_url") or "").strip()
        if url:
            parts.append(f"Privacy: {url}")
        contact = str(block.get("contact_email") or "").strip()
        if contact:
            parts.append(f"Contact: {contact}")
        if block.get("opt_out_enabled", True):
            parts.append("Reply STOP to opt out.")
        return " ".join(parts).strip()

    @staticmethod
    def attach_compliance_to_order_config(
        config: dict[str, Any],
        compliance_payload: dict[str, Any],
    ) -> dict[str, Any]:
        cfg = dict(config or {})
        existing = cfg.get("compliance")
        merged = dict(existing) if isinstance(existing, dict) else {}
        merged.update({k: v for k, v in compliance_payload.items() if v is not None})
        cfg["compliance"] = merged
        return cfg

    @staticmethod
    def upsert_org_defaults(db: Session, org_id: str, payload: dict[str, Any]) -> OrganisationComplianceConfig:
        row = _org_compliance_row(db, org_id)
        from datetime import datetime
        import uuid

        now = datetime.utcnow()
        if row is None:
            row = OrganisationComplianceConfig(
                id=str(uuid.uuid4()),
                org_id=org_id,
                created_at=now,
                updated_at=now,
            )
        if "privacy_notice_url" in payload:
            row.privacy_notice_url = str(payload.get("privacy_notice_url") or "").strip() or None
        if "contact_email" in payload:
            row.contact_email = str(payload.get("contact_email") or "").strip() or None
        if "dpo_email" in payload:
            row.dpo_email = str(payload.get("dpo_email") or "").strip() or None
        if "opt_out_enabled" in payload:
            row.opt_out_enabled = bool(payload.get("opt_out_enabled"))
        if "lawful_basis_default" in payload:
            v = str(payload.get("lawful_basis_default") or "").strip().lower() or None
            row.lawful_basis_default = v if v in LAWFUL_BASES else row.lawful_basis_default
        if "special_category_data_present_default" in payload:
            row.special_category_data_present_default = bool(payload.get("special_category_data_present_default"))
        if "article9_condition_default" in payload:
            v = str(payload.get("article9_condition_default") or "").strip().lower() or None
            row.article9_condition_default = v if v in ARTICLE9_CONDITIONS else None
        if "privacy_intro_text_default" in payload:
            row.privacy_intro_text_default = str(payload.get("privacy_intro_text_default") or "").strip() or None
        if "collect_minimal_data_default" in payload:
            row.collect_minimal_data_default = bool(payload.get("collect_minimal_data_default"))
        for key in (
            "retention_days_messages",
            "retention_days_responses",
            "retention_days_recordings",
            "retention_days_transcripts",
        ):
            if key in payload and payload[key] is not None:
                setattr(row, key, max(1, min(3650, int(payload[key]))))
        row.updated_at = now
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
