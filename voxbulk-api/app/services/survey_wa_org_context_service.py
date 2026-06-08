"""Resolve survey organisation / company display name for WA template variables."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.services.survey_wa_template_pack_service import resolve_wa_survey_company_name

logger = logging.getLogger(__name__)

_NEUTRAL_ORG_NAMES = frozenset(
    {
        "",
        "your business",
        "your organisation",
        "your organization",
        "company",
        "business",
        "the hiring team",
        "voxbulk",
        "retover",
    }
)


def _clean_org_candidate(raw: Any) -> str | None:
    val = str(raw or "").strip()
    if not val or val.lower() in _NEUTRAL_ORG_NAMES:
        return None
    return val


def resolve_survey_organisation_name(db: Session, *, org_id: str, config: dict[str, Any] | None) -> str:
    """Prefer explicit survey config, then tenant AI identity / org profile."""
    cfg = config if isinstance(config, dict) else {}
    for key in ("organisation_name", "clinic_name", "client_name", "business_name"):
        candidate = _clean_org_candidate(cfg.get(key))
        if candidate:
            return candidate

    resolved = resolve_wa_survey_company_name(db, org_id=org_id)
    if resolved:
        return resolved

    from app.models.organisation import Organisation

    org = db.get(Organisation, org_id)
    candidate = _clean_org_candidate(org.name if org else None)
    if candidate:
        return candidate

    logger.warning(
        "survey_org_name_missing org_id=%s — no company name in config or tenant profile; using fallback",
        org_id,
    )
    return "Your business"
