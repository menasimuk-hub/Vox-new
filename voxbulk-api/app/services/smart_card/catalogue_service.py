"""Smart Card QR catalogue — categories, products, PDF assets."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.smart_card import SmartCardAsset, SmartCardCategory, SmartCardProduct


class SmartCardCatalogueError(ValueError):
    pass


class SmartCardCatalogueService:
    @staticmethod
    def list_categories(db: Session, org_id: str) -> list[SmartCardCategory]:
        return list(
            db.execute(
                select(SmartCardCategory)
                .where(SmartCardCategory.org_id == org_id)
                .order_by(SmartCardCategory.sort_order.asc(), SmartCardCategory.name.asc())
            )
            .scalars()
            .all()
        )

    @staticmethod
    def create_category(db: Session, *, org_id: str, name: str, sort_order: int = 100, **extra: Any) -> SmartCardCategory:
        name = str(name or "").strip()
        if not name:
            raise SmartCardCatalogueError("Category name is required")
        row = SmartCardCategory(
            org_id=org_id,
            name=name[:128],
            accent_color=str(extra.get("accent_color") or extra.get("color") or "sky")[:32],
            is_frozen=bool(extra.get("is_frozen") or extra.get("frozen")),
            sort_order=int(sort_order or 100),
        )
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def update_category(db: Session, *, org_id: str, category_id: str, payload: dict[str, Any]) -> SmartCardCategory:
        row = db.execute(
            select(SmartCardCategory).where(
                SmartCardCategory.id == category_id,
                SmartCardCategory.org_id == org_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise SmartCardCatalogueError("Category not found")
        if "name" in payload:
            name = str(payload.get("name") or "").strip()
            if not name:
                raise SmartCardCatalogueError("Category name is required")
            row.name = name[:128]
        if "accent_color" in payload or "color" in payload:
            row.accent_color = str(payload.get("accent_color") or payload.get("color") or row.accent_color or "sky")[:32]
        if "is_frozen" in payload or "frozen" in payload:
            row.is_frozen = bool(payload.get("is_frozen") if "is_frozen" in payload else payload.get("frozen"))
        if "sort_order" in payload:
            try:
                row.sort_order = int(payload.get("sort_order"))
            except (TypeError, ValueError):
                pass
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def delete_category(db: Session, *, org_id: str, category_id: str) -> None:
        products = (
            db.execute(
                select(SmartCardProduct).where(
                    SmartCardProduct.category_id == category_id,
                    SmartCardProduct.org_id == org_id,
                )
            )
            .scalars()
            .all()
        )
        for p in products:
            SmartCardCatalogueService.delete_product(db, org_id=org_id, product_id=p.id)
        db.execute(
            delete(SmartCardCategory).where(
                SmartCardCategory.id == category_id,
                SmartCardCategory.org_id == org_id,
            )
        )
        db.flush()

    @staticmethod
    def list_products(db: Session, org_id: str, *, category_id: str | None = None) -> list[SmartCardProduct]:
        stmt = select(SmartCardProduct).where(SmartCardProduct.org_id == org_id)
        if category_id:
            stmt = stmt.where(SmartCardProduct.category_id == category_id)
        stmt = stmt.order_by(SmartCardProduct.sort_order.asc(), SmartCardProduct.name.asc())
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def create_product(db: Session, *, org_id: str, payload: dict[str, Any]) -> SmartCardProduct:
        cat_id = str(payload.get("category_id") or "").strip()
        name = str(payload.get("name") or "").strip()
        if not cat_id or not name:
            raise SmartCardCatalogueError("category_id and name are required")
        cat = db.execute(
            select(SmartCardCategory).where(
                SmartCardCategory.id == cat_id,
                SmartCardCategory.org_id == org_id,
            )
        ).scalar_one_or_none()
        if cat is None:
            raise SmartCardCatalogueError("Category not found")
        row = SmartCardProduct(
            org_id=org_id,
            category_id=cat_id,
            name=name[:255],
            short_description=(str(payload.get("short_description") or payload.get("description") or "").strip() or None),
            match_keywords=(str(payload.get("match_keywords") or "").strip() or None),
            is_frozen=bool(payload.get("is_frozen") or payload.get("frozen")),
            sort_order=int(payload.get("sort_order") or 100),
        )
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def update_product(db: Session, *, org_id: str, product_id: str, payload: dict[str, Any]) -> SmartCardProduct:
        row = db.execute(
            select(SmartCardProduct).where(
                SmartCardProduct.id == product_id,
                SmartCardProduct.org_id == org_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise SmartCardCatalogueError("Product not found")
        if "name" in payload:
            name = str(payload.get("name") or "").strip()
            if not name:
                raise SmartCardCatalogueError("Product name is required")
            row.name = name[:255]
        if "short_description" in payload or "description" in payload:
            row.short_description = (
                str(payload.get("short_description") or payload.get("description") or "").strip() or None
            )
        for key in ("match_keywords",):
            if key in payload:
                setattr(row, key, (str(payload.get(key) or "").strip() or None))
        if "is_frozen" in payload or "frozen" in payload:
            row.is_frozen = bool(payload.get("is_frozen") if "is_frozen" in payload else payload.get("frozen"))
        if "sort_order" in payload:
            try:
                row.sort_order = int(payload.get("sort_order"))
            except (TypeError, ValueError):
                pass
        if "category_id" in payload:
            cat_id = str(payload.get("category_id") or "").strip()
            cat = db.execute(
                select(SmartCardCategory).where(
                    SmartCardCategory.id == cat_id,
                    SmartCardCategory.org_id == org_id,
                )
            ).scalar_one_or_none()
            if cat is None:
                raise SmartCardCatalogueError("Category not found")
            row.category_id = cat_id
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def delete_product(db: Session, *, org_id: str, product_id: str) -> None:
        db.execute(
            delete(SmartCardAsset).where(
                SmartCardAsset.product_id == product_id,
                SmartCardAsset.org_id == org_id,
            )
        )
        from app.models.smart_card import SmartCardRepresentativeProduct

        db.execute(
            delete(SmartCardRepresentativeProduct).where(
                SmartCardRepresentativeProduct.product_id == product_id,
                SmartCardRepresentativeProduct.org_id == org_id,
            )
        )
        db.execute(
            delete(SmartCardProduct).where(
                SmartCardProduct.id == product_id,
                SmartCardProduct.org_id == org_id,
            )
        )
        db.flush()

    @staticmethod
    def list_assets(
        db: Session,
        org_id: str,
        *,
        product_id: str | None = None,
        category_id: str | None = None,
    ) -> list[SmartCardAsset]:
        stmt = select(SmartCardAsset).where(SmartCardAsset.org_id == org_id)
        if product_id:
            stmt = stmt.where(SmartCardAsset.product_id == product_id)
        if category_id:
            stmt = stmt.where(SmartCardAsset.category_id == category_id)
        stmt = stmt.order_by(SmartCardAsset.sort_order.asc(), SmartCardAsset.title.asc())
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def create_asset(db: Session, *, org_id: str, payload: dict[str, Any]) -> SmartCardAsset:
        title = str(payload.get("title") or "").strip()
        if not title:
            raise SmartCardCatalogueError("Asset title is required")
        product_id = str(payload.get("product_id") or "").strip() or None
        category_id = str(payload.get("category_id") or "").strip() or None
        if not product_id and not category_id:
            raise SmartCardCatalogueError("product_id or category_id is required")
        try:
            size_i = int(payload["file_size_bytes"]) if payload.get("file_size_bytes") is not None else None
        except (TypeError, ValueError):
            size_i = None
        row = SmartCardAsset(
            org_id=org_id,
            product_id=product_id,
            category_id=category_id,
            title=title[:255],
            kind=str(payload.get("kind") or "pdf")[:16],
            purpose=str(payload.get("purpose") or "catalogue")[:32],
            storage_path=(str(payload.get("storage_path") or "").strip() or None),
            external_url=(str(payload.get("external_url") or "").strip() or None),
            match_keywords=(str(payload.get("match_keywords") or "").strip() or None),
            original_filename=(str(payload.get("original_filename") or "").strip() or None),
            file_size_bytes=size_i,
            sort_order=int(payload.get("sort_order") or 100),
        )
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def delete_asset(db: Session, *, org_id: str, asset_id: str) -> None:
        db.execute(
            delete(SmartCardAsset).where(
                SmartCardAsset.id == asset_id,
                SmartCardAsset.org_id == org_id,
            )
        )
        db.flush()

    @staticmethod
    def serialize_category(c: SmartCardCategory) -> dict[str, Any]:
        return {
            "id": c.id,
            "name": c.name,
            "accent_color": getattr(c, "accent_color", None) or "sky",
            "color": getattr(c, "accent_color", None) or "sky",
            "is_frozen": bool(getattr(c, "is_frozen", False)),
            "frozen": bool(getattr(c, "is_frozen", False)),
            "sort_order": c.sort_order,
        }

    @staticmethod
    def serialize_product(p: SmartCardProduct) -> dict[str, Any]:
        return {
            "id": p.id,
            "category_id": p.category_id,
            "name": p.name,
            "short_description": p.short_description,
            "description": p.short_description,
            "match_keywords": p.match_keywords,
            "is_frozen": bool(getattr(p, "is_frozen", False)),
            "frozen": bool(getattr(p, "is_frozen", False)),
            "sort_order": p.sort_order,
        }

    @staticmethod
    def serialize_asset(a: SmartCardAsset) -> dict[str, Any]:
        return {
            "id": a.id,
            "product_id": a.product_id,
            "category_id": a.category_id,
            "title": a.title,
            "kind": a.kind,
            "purpose": a.purpose,
            "external_url": a.external_url,
            "storage_path": a.storage_path,
            "match_keywords": a.match_keywords,
            "original_filename": getattr(a, "original_filename", None),
            "file_size_bytes": getattr(a, "file_size_bytes", None),
            "sort_order": a.sort_order,
        }

    @staticmethod
    def tree(db: Session, org_id: str) -> list[dict[str, Any]]:
        cats = SmartCardCatalogueService.list_categories(db, org_id)
        products = SmartCardCatalogueService.list_products(db, org_id)
        assets = SmartCardCatalogueService.list_assets(db, org_id)
        by_cat: dict[str, list[SmartCardProduct]] = {}
        for p in products:
            by_cat.setdefault(p.category_id, []).append(p)
        assets_by_product: dict[str, list[SmartCardAsset]] = {}
        assets_by_cat: dict[str, list[SmartCardAsset]] = {}
        for a in assets:
            if a.product_id:
                assets_by_product.setdefault(a.product_id, []).append(a)
            if a.category_id:
                assets_by_cat.setdefault(a.category_id, []).append(a)
        out = []
        for c in cats:
            out.append(
                {
                    **SmartCardCatalogueService.serialize_category(c),
                    "assets": [SmartCardCatalogueService.serialize_asset(a) for a in assets_by_cat.get(c.id, [])],
                    "products": [
                        {
                            **SmartCardCatalogueService.serialize_product(p),
                            "assets": [
                                SmartCardCatalogueService.serialize_asset(a)
                                for a in assets_by_product.get(p.id, [])
                            ],
                        }
                        for p in by_cat.get(c.id, [])
                    ],
                }
            )
        return out
