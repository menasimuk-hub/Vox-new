"""Expo org-level catalogue library (Add catalogues page)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.expo import ExpoLibraryAsset, ExpoLibraryCategory, ExpoLibraryProduct


class ExpoLibraryCatalogueError(ValueError):
    pass


class ExpoLibraryCatalogueService:
    @staticmethod
    def create_category(db: Session, *, org_id: str, payload: dict[str, Any]) -> ExpoLibraryCategory:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ExpoLibraryCatalogueError("Category name is required")
        row = ExpoLibraryCategory(
            org_id=org_id,
            name=name[:128],
            accent_color=str(payload.get("accent_color") or payload.get("color") or "sky")[:32],
            is_frozen=bool(payload.get("is_frozen") or payload.get("frozen")),
            sort_order=int(payload.get("sort_order") or 100),
        )
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def update_category(db: Session, *, org_id: str, category_id: str, payload: dict[str, Any]) -> ExpoLibraryCategory:
        row = db.execute(
            select(ExpoLibraryCategory).where(
                ExpoLibraryCategory.id == category_id,
                ExpoLibraryCategory.org_id == org_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise ExpoLibraryCatalogueError("Category not found")
        if "name" in payload:
            name = str(payload.get("name") or "").strip()
            if not name:
                raise ExpoLibraryCatalogueError("Category name is required")
            row.name = name[:128]
        if "accent_color" in payload or "color" in payload:
            row.accent_color = str(payload.get("accent_color") or payload.get("color") or row.accent_color)[:32]
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
        products = list(
            db.execute(
                select(ExpoLibraryProduct).where(
                    ExpoLibraryProduct.category_id == category_id,
                    ExpoLibraryProduct.org_id == org_id,
                )
            )
            .scalars()
            .all()
        )
        for p in products:
            ExpoLibraryCatalogueService.delete_product(db, org_id=org_id, product_id=p.id)
        db.execute(
            delete(ExpoLibraryAsset).where(
                ExpoLibraryAsset.category_id == category_id,
                ExpoLibraryAsset.org_id == org_id,
            )
        )
        db.execute(
            delete(ExpoLibraryCategory).where(
                ExpoLibraryCategory.id == category_id,
                ExpoLibraryCategory.org_id == org_id,
            )
        )
        db.flush()

    @staticmethod
    def create_product(db: Session, *, org_id: str, payload: dict[str, Any]) -> ExpoLibraryProduct:
        cat_id = str(payload.get("category_id") or "").strip()
        name = str(payload.get("name") or "").strip()
        if not cat_id or not name:
            raise ExpoLibraryCatalogueError("category_id and name are required")
        cat = db.execute(
            select(ExpoLibraryCategory).where(
                ExpoLibraryCategory.id == cat_id,
                ExpoLibraryCategory.org_id == org_id,
            )
        ).scalar_one_or_none()
        if cat is None:
            raise ExpoLibraryCatalogueError("Category not found")
        row = ExpoLibraryProduct(
            org_id=org_id,
            category_id=cat_id,
            name=name[:255],
            short_description=(str(payload.get("short_description") or payload.get("description") or "").strip() or None),
            is_frozen=bool(payload.get("is_frozen") or payload.get("frozen")),
            sort_order=int(payload.get("sort_order") or 100),
        )
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def update_product(db: Session, *, org_id: str, product_id: str, payload: dict[str, Any]) -> ExpoLibraryProduct:
        row = db.execute(
            select(ExpoLibraryProduct).where(
                ExpoLibraryProduct.id == product_id,
                ExpoLibraryProduct.org_id == org_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise ExpoLibraryCatalogueError("Product not found")
        if "name" in payload:
            name = str(payload.get("name") or "").strip()
            if not name:
                raise ExpoLibraryCatalogueError("Product name is required")
            row.name = name[:255]
        if "short_description" in payload or "description" in payload:
            row.short_description = (
                str(payload.get("short_description") or payload.get("description") or "").strip() or None
            )
        if "is_frozen" in payload or "frozen" in payload:
            row.is_frozen = bool(payload.get("is_frozen") if "is_frozen" in payload else payload.get("frozen"))
        if "category_id" in payload:
            cat_id = str(payload.get("category_id") or "").strip()
            cat = db.execute(
                select(ExpoLibraryCategory).where(
                    ExpoLibraryCategory.id == cat_id,
                    ExpoLibraryCategory.org_id == org_id,
                )
            ).scalar_one_or_none()
            if cat is None:
                raise ExpoLibraryCatalogueError("Category not found")
            row.category_id = cat_id
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def delete_product(db: Session, *, org_id: str, product_id: str) -> None:
        db.execute(
            delete(ExpoLibraryAsset).where(
                ExpoLibraryAsset.product_id == product_id,
                ExpoLibraryAsset.org_id == org_id,
            )
        )
        db.execute(
            delete(ExpoLibraryProduct).where(
                ExpoLibraryProduct.id == product_id,
                ExpoLibraryProduct.org_id == org_id,
            )
        )
        db.flush()

    @staticmethod
    def create_asset(db: Session, *, org_id: str, payload: dict[str, Any]) -> ExpoLibraryAsset:
        title = str(payload.get("title") or payload.get("original_filename") or "File").strip()
        if not title:
            raise ExpoLibraryCatalogueError("Asset title is required")
        product_id = str(payload.get("product_id") or "").strip() or None
        category_id = str(payload.get("category_id") or "").strip() or None
        if not product_id and not category_id:
            raise ExpoLibraryCatalogueError("product_id or category_id is required")
        size = payload.get("file_size_bytes")
        try:
            size_i = int(size) if size is not None else None
        except (TypeError, ValueError):
            size_i = None
        row = ExpoLibraryAsset(
            org_id=org_id,
            product_id=product_id,
            category_id=category_id,
            title=title[:255],
            kind=str(payload.get("kind") or "pdf")[:16],
            purpose=str(payload.get("purpose") or "catalogue")[:32],
            storage_path=(str(payload.get("storage_path") or "").strip() or None),
            external_url=(str(payload.get("external_url") or "").strip() or None),
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
            delete(ExpoLibraryAsset).where(
                ExpoLibraryAsset.id == asset_id,
                ExpoLibraryAsset.org_id == org_id,
            )
        )
        db.flush()

    @staticmethod
    def serialize_category(c: ExpoLibraryCategory) -> dict[str, Any]:
        return {
            "id": c.id,
            "name": c.name,
            "accent_color": c.accent_color or "sky",
            "color": c.accent_color or "sky",
            "is_frozen": bool(c.is_frozen),
            "frozen": bool(c.is_frozen),
            "sort_order": c.sort_order,
        }

    @staticmethod
    def serialize_product(p: ExpoLibraryProduct) -> dict[str, Any]:
        return {
            "id": p.id,
            "category_id": p.category_id,
            "name": p.name,
            "short_description": p.short_description,
            "description": p.short_description,
            "is_frozen": bool(p.is_frozen),
            "frozen": bool(p.is_frozen),
            "sort_order": p.sort_order,
        }

    @staticmethod
    def serialize_asset(a: ExpoLibraryAsset) -> dict[str, Any]:
        return {
            "id": a.id,
            "product_id": a.product_id,
            "category_id": a.category_id,
            "title": a.title,
            "kind": a.kind,
            "purpose": a.purpose,
            "external_url": a.external_url,
            "storage_path": a.storage_path,
            "original_filename": a.original_filename,
            "file_size_bytes": a.file_size_bytes,
            "sort_order": a.sort_order,
        }

    @staticmethod
    def tree(db: Session, org_id: str) -> list[dict[str, Any]]:
        cats = list(
            db.execute(
                select(ExpoLibraryCategory)
                .where(ExpoLibraryCategory.org_id == org_id)
                .order_by(ExpoLibraryCategory.sort_order.asc(), ExpoLibraryCategory.name.asc())
            )
            .scalars()
            .all()
        )
        products = list(
            db.execute(
                select(ExpoLibraryProduct)
                .where(ExpoLibraryProduct.org_id == org_id)
                .order_by(ExpoLibraryProduct.sort_order.asc(), ExpoLibraryProduct.name.asc())
            )
            .scalars()
            .all()
        )
        assets = list(
            db.execute(
                select(ExpoLibraryAsset)
                .where(ExpoLibraryAsset.org_id == org_id)
                .order_by(ExpoLibraryAsset.sort_order.asc(), ExpoLibraryAsset.title.asc())
            )
            .scalars()
            .all()
        )
        by_cat: dict[str, list[ExpoLibraryProduct]] = {}
        for p in products:
            by_cat.setdefault(p.category_id, []).append(p)
        assets_by_product: dict[str, list[ExpoLibraryAsset]] = {}
        for a in assets:
            if a.product_id:
                assets_by_product.setdefault(a.product_id, []).append(a)
        out = []
        for c in cats:
            out.append(
                {
                    **ExpoLibraryCatalogueService.serialize_category(c),
                    "products": [
                        {
                            **ExpoLibraryCatalogueService.serialize_product(p),
                            "assets": [
                                ExpoLibraryCatalogueService.serialize_asset(a)
                                for a in assets_by_product.get(p.id, [])
                            ],
                        }
                        for p in by_cat.get(c.id, [])
                    ],
                }
            )
        return out
