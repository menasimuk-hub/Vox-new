"""Smart Card QR wizard — preview-draft and catalogue upsert for setup."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.smart_card import SmartCardCategory, SmartCardProduct, SmartCardRepresentative
from app.services.smart_card.catalogue_service import SmartCardCatalogueService
from app.services.smart_card.company_service import SmartCardCompanyService
from app.services.smart_card.representative_service import (
    SmartCardRepError,
    SmartCardRepresentativeService,
)

CONTACT_CAPTURE_MODES = frozenset({"offer_both", "manual_only", "card_only"})
DEFAULT_SELECTED_KEYS = ("interest", "role", "timeline", "follow_up", "consent_info")


class SmartCardSetupError(ValueError):
    pass


def _parse_contact_capture(raw: Any) -> str:
    mode = str(raw or "offer_both").strip().lower()
    return mode if mode in CONTACT_CAPTURE_MODES else "offer_both"


def _build_question_config(payload: dict[str, Any]) -> dict[str, Any]:
    existing = payload.get("question_config")
    if isinstance(existing, dict) and existing.get("selected_keys"):
        selected = [str(k).strip() for k in existing["selected_keys"] if str(k).strip()]
        capture = _parse_contact_capture(existing.get("contact_capture") or payload.get("contact_capture"))
        cfg = dict(existing)
        cfg["selected_keys"] = selected
        cfg["contact_capture"] = capture
        cfg["version"] = int(cfg.get("version") or 1)
        return cfg

    keys = payload.get("selected_keys") or payload.get("selected_question_keys") or list(DEFAULT_SELECTED_KEYS)
    selected = [str(k).strip() for k in keys if str(k).strip() and str(k).strip() != "contact"]
    if not selected:
        raise SmartCardSetupError("Select at least one qualifying question")
    return {
        "version": 1,
        "selected_keys": selected,
        "contact_capture": _parse_contact_capture(payload.get("contact_capture")),
    }


class SmartCardSetupService:
    @staticmethod
    def upsert_catalogue(db: Session, *, org_id: str, categories: list[Any] | None) -> list[dict[str, Any]]:
        """Create categories/products from wizard draft (match by name; skip empty)."""
        if not isinstance(categories, list) or not categories:
            return SmartCardCatalogueService.tree(db, org_id)

        for idx, cat in enumerate(categories):
            if not isinstance(cat, dict):
                continue
            name = str(cat.get("name") or "").strip()
            if not name:
                continue
            existing = db.execute(
                select(SmartCardCategory).where(
                    SmartCardCategory.org_id == org_id,
                    SmartCardCategory.name == name[:128],
                )
            ).scalar_one_or_none()
            if existing is None:
                existing = SmartCardCatalogueService.create_category(
                    db, org_id=org_id, name=name, sort_order=int(cat.get("sort_order") or (idx + 1) * 10)
                )
            products = cat.get("products") or []
            if not isinstance(products, list):
                continue
            for pidx, prod in enumerate(products):
                if not isinstance(prod, dict):
                    continue
                pname = str(prod.get("name") or "").strip()
                if not pname:
                    continue
                prow = db.execute(
                    select(SmartCardProduct).where(
                        SmartCardProduct.org_id == org_id,
                        SmartCardProduct.category_id == existing.id,
                        SmartCardProduct.name == pname[:255],
                    )
                ).scalar_one_or_none()
                if prow is None:
                    SmartCardCatalogueService.create_product(
                        db,
                        org_id=org_id,
                        payload={
                            "category_id": existing.id,
                            "name": pname,
                            "short_description": prod.get("short_description") or prod.get("description"),
                            "match_keywords": prod.get("match_keywords"),
                            "sort_order": int(prod.get("sort_order") or (pidx + 1) * 10),
                        },
                    )
                else:
                    SmartCardCatalogueService.update_product(
                        db,
                        org_id=org_id,
                        product_id=prow.id,
                        payload={
                            "short_description": prod.get("short_description") or prod.get("description"),
                            "match_keywords": prod.get("match_keywords"),
                        },
                    )
        return SmartCardCatalogueService.tree(db, org_id)

    @staticmethod
    def sync_org_profile(db: Session, *, org_id: str, company_name: str, website: str | None) -> None:
        org = db.get(Organisation, org_id)
        if org is None:
            return
        if company_name and not (org.name or "").strip():
            org.name = company_name[:255]
        elif company_name:
            org.name = company_name[:255]
        if website is not None:
            org.website = (str(website).strip() or None)
        db.add(org)

    @staticmethod
    def preview_draft(
        db: Session,
        *,
        org_id: str,
        user_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        company_name = str(payload.get("name") or payload.get("company_name") or "").strip()
        if not company_name:
            raise SmartCardSetupError("Company name is required")

        qcfg = _build_question_config(payload)
        offer = payload.get("offer") if isinstance(payload.get("offer"), dict) else {}
        offer_enabled = bool(payload.get("offer_enabled") or (offer and offer.get("enabled")))
        offer_title = str((offer or {}).get("title") or payload.get("offer_title") or "").strip()
        offer_description = str(
            (offer or {}).get("description") or payload.get("offer_description") or ""
        ).strip()

        company_payload: dict[str, Any] = {
            "name": company_name,
            "website": payload.get("website"),
            "description": payload.get("description"),
            "products_summary": payload.get("products_summary"),
            "contact_email": payload.get("contact_email"),
            "contact_phone": payload.get("contact_phone") or payload.get("notify_mobile"),
            "question_config": qcfg,
        }
        if offer_enabled and (offer_title or offer_description):
            company_payload["pricing_notes"] = "\n".join(
                x for x in [offer_title, offer_description] if x
            )[:4000]
            brand = {
                "offer": {
                    "enabled": True,
                    "title": offer_title,
                    "description": offer_description,
                    "claim_url": str((offer or {}).get("claim_url") or "").strip() or None,
                    "code": str((offer or {}).get("code") or "").strip() or None,
                }
            }
            company_payload["brand_defaults"] = brand
            # Auto-include offer question when offer is on
            if "offer_interest" not in qcfg["selected_keys"]:
                qcfg["selected_keys"] = [*qcfg["selected_keys"], "offer_interest"]
                company_payload["question_config"] = qcfg
        elif "pricing_notes" in payload:
            company_payload["pricing_notes"] = payload.get("pricing_notes")

        company = SmartCardCompanyService.update(db, org_id, company_payload)
        SmartCardSetupService.sync_org_profile(
            db, org_id=org_id, company_name=company_name, website=payload.get("website")
        )

        SmartCardSetupService.upsert_catalogue(db, org_id=org_id, categories=payload.get("categories"))

        rep_payload = payload.get("representative") or payload.get("first_representative")
        if not isinstance(rep_payload, dict):
            reps = payload.get("representatives")
            if isinstance(reps, list) and reps and isinstance(reps[0], dict):
                rep_payload = reps[0]
            else:
                rep_payload = {}

        rep_name = str(rep_payload.get("name") or "").strip()
        if not rep_name:
            raise SmartCardSetupError("First representative name is required for preview")

        existing_reps = (
            db.execute(
                select(SmartCardRepresentative)
                .where(
                    SmartCardRepresentative.org_id == org_id,
                    SmartCardRepresentative.status == "active",
                )
                .order_by(SmartCardRepresentative.created_at.asc())
            )
            .scalars()
            .all()
        )

        body = {
            "name": rep_name,
            "email": rep_payload.get("email"),
            "mobile": rep_payload.get("mobile") or payload.get("notify_mobile"),
            "website": rep_payload.get("website") or payload.get("website"),
            "product_ids": rep_payload.get("product_ids") if isinstance(rep_payload.get("product_ids"), list) else [],
            "qr_fg_color": rep_payload.get("qr_fg_color"),
            "qr_bg_color": rep_payload.get("qr_bg_color"),
            "qr_transparent": rep_payload.get("qr_transparent"),
        }

        try:
            if existing_reps:
                rep = SmartCardRepresentativeService.update(
                    db, org_id=org_id, rep_id=existing_reps[0].id, payload=body
                )
            else:
                rep = SmartCardRepresentativeService.create(
                    db, org_id=org_id, user_id=user_id, payload=body
                )
        except SmartCardRepError as e:
            raise SmartCardSetupError(str(e)) from e

        return {
            "company": SmartCardCompanyService.serialize(company),
            "representative": SmartCardRepresentativeService.serialize(db, rep),
            "catalogue": SmartCardCatalogueService.tree(db, org_id),
        }
