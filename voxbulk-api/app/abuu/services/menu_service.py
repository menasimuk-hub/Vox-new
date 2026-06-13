"""Menu CRUD helpers for admin and restaurant portals."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abuu.models.entities import RestaurantMenuCategory, RestaurantMenuItem
from app.abuu.services.abuu_menu_photo_storage_service import delete_photo_file


class AbuuMenuService:
    @staticmethod
    def list_categories(db: Session, restaurant_id: str) -> list[RestaurantMenuCategory]:
        return list(
            db.execute(
                select(RestaurantMenuCategory)
                .where(
                    RestaurantMenuCategory.restaurant_id == restaurant_id,
                    RestaurantMenuCategory.is_deleted.is_(False),
                )
                .order_by(RestaurantMenuCategory.sort_order.asc())
            ).scalars().all()
        )

    @staticmethod
    def create_category(
        db: Session,
        *,
        restaurant_id: str,
        name_en: str,
        name_ar: str,
        sort_order: int = 100,
        is_available: bool = True,
        parent_category_id: str | None = None,
    ) -> RestaurantMenuCategory:
        row = RestaurantMenuCategory(
            restaurant_id=restaurant_id,
            parent_category_id=parent_category_id,
            name_en=name_en.strip(),
            name_ar=name_ar.strip(),
            sort_order=sort_order,
            is_available=is_available,
        )
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def patch_category(db: Session, row: RestaurantMenuCategory, payload: dict) -> RestaurantMenuCategory:
        for key in ("name_en", "name_ar"):
            if key in payload:
                setattr(row, key, str(payload[key]).strip())
        if "sort_order" in payload:
            row.sort_order = int(payload["sort_order"])
        if "is_available" in payload:
            row.is_available = bool(payload["is_available"])
        if "parent_category_id" in payload:
            row.parent_category_id = payload["parent_category_id"]
        row.updated_at = datetime.utcnow()
        db.add(row)
        return row

    @staticmethod
    def delete_category(db: Session, row: RestaurantMenuCategory) -> None:
        row.is_deleted = True
        row.deleted_at = datetime.utcnow()
        db.add(row)

    @staticmethod
    def create_item(
        db: Session,
        *,
        category_id: str,
        name_en: str,
        name_ar: str,
        item_type: str = "meat",
        price_agorot: int = 0,
        description_en: str | None = None,
        description_ar: str | None = None,
        parent_menu_item_id: str | None = None,
        is_available: bool = True,
    ) -> RestaurantMenuItem:
        row = RestaurantMenuItem(
            category_id=category_id,
            name_en=name_en.strip(),
            name_ar=name_ar.strip(),
            description_en=description_en,
            description_ar=description_ar,
            item_type=item_type,
            price_agorot=price_agorot,
            parent_menu_item_id=parent_menu_item_id,
            is_available=is_available,
        )
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def patch_item(db: Session, row: RestaurantMenuItem, payload: dict) -> RestaurantMenuItem:
        for key in ("name_en", "name_ar", "description_en", "description_ar", "item_type"):
            if key in payload:
                val = payload[key]
                setattr(row, key, str(val).strip() if val is not None and key in ("name_en", "name_ar", "item_type") else val)
        if "price_agorot" in payload:
            row.price_agorot = int(payload["price_agorot"])
        if "is_available" in payload:
            row.is_available = bool(payload["is_available"])
        if "parent_menu_item_id" in payload:
            row.parent_menu_item_id = payload["parent_menu_item_id"]
        if "category_id" in payload:
            row.category_id = str(payload["category_id"])
        row.updated_at = datetime.utcnow()
        db.add(row)
        return row

    @staticmethod
    def delete_item(db: Session, row: RestaurantMenuItem) -> None:
        if row.photo_storage_key:
            delete_photo_file(row.photo_storage_key)
        row.is_deleted = True
        row.deleted_at = datetime.utcnow()
        db.add(row)

    @staticmethod
    def nested_menu(db: Session, restaurant_id: str) -> list[dict]:
        from app.abuu.services.serializers import menu_category_to_dict, menu_item_to_dict

        categories = AbuuMenuService.list_categories(db, restaurant_id)
        items_by_cat: dict[str, list] = {}
        for cat in categories:
            items = list(
                db.execute(
                    select(RestaurantMenuItem).where(
                        RestaurantMenuItem.category_id == cat.id,
                        RestaurantMenuItem.is_deleted.is_(False),
                    )
                ).scalars().all()
            )
            items_by_cat[cat.id] = [menu_item_to_dict(i) for i in items]

        top_level = [c for c in categories if not c.parent_category_id]
        out = []
        for cat in top_level:
            node = {**menu_category_to_dict(cat), "items": items_by_cat.get(cat.id, []), "subcategories": []}
            for sub in categories:
                if sub.parent_category_id == cat.id:
                    node["subcategories"].append(
                        {**menu_category_to_dict(sub), "items": items_by_cat.get(sub.id, [])}
                    )
            out.append(node)
        return out
