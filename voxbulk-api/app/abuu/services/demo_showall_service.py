"""Internal demo listing payloads for /showall portal pages."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.abuu.models.entities import Restaurant, RestaurantMenuCategory, RestaurantMenuItem
from app.abuu.services.yallasay_demo_seed_service import (
    DEMO_DRIVERS,
    DEMO_RESTAURANTS,
    YallasayDemoSeedService,
)
from app.core.config import get_settings


def demo_showall_enabled() -> bool:
    return bool(get_settings().abuu_demo_showall_enabled)


class DemoShowallService:
    @staticmethod
    def restaurant_portal_base() -> str:
        return "https://restaurant.yallasay.com"

    @staticmethod
    def driver_portal_base() -> str:
        return "https://driver.yallasay.com"

    @staticmethod
    def list_restaurants(db: Session) -> dict:
        rows: list[dict] = []
        for spec in DEMO_RESTAURANTS:
            restaurant = db.get(Restaurant, spec["id"])
            menu_items = DemoShowallService._menu_item_count(db, spec["id"])
            new_orders = YallasayDemoSeedService.count_new_orders(db, spec["id"])
            rows.append(
                {
                    "id": spec["id"],
                    "name_en": spec["name_en"],
                    "name_ar": spec["name_ar"],
                    "login_email": spec["email"],
                    "status": restaurant.status if restaurant else "missing",
                    "is_available": bool(restaurant.is_available) if restaurant else False,
                    "new_orders_count": new_orders,
                    "menu_items_count": menu_items,
                    "login_url": f"{DemoShowallService.restaurant_portal_base()}/login?email={spec['email']}",
                }
            )
        return {"restaurants": rows, "count": len(rows)}

    @staticmethod
    def list_drivers(db: Session) -> dict:
        from app.abuu.models.entities import Driver

        rows: list[dict] = []
        for spec in DEMO_DRIVERS:
            driver = db.get(Driver, spec["id"])
            counts = YallasayDemoSeedService.driver_assignment_counts(db, spec["id"])
            rows.append(
                {
                    "id": spec["id"],
                    "name": spec["name"],
                    "phone": spec["phone"],
                    "login_email": spec["email"],
                    "status": driver.status if driver else "missing",
                    "is_available": bool(driver.is_available) if driver else False,
                    "queued_orders_count": counts["queued_orders"],
                    "active_orders_count": counts["active_orders"],
                    "assignment_by_status": counts["by_status"],
                    "login_url": f"{DemoShowallService.driver_portal_base()}/login?email={spec['email']}",
                }
            )
        return {"drivers": rows, "count": len(rows)}

    @staticmethod
    def _menu_item_count(db: Session, restaurant_id: str) -> int:
        category_ids = db.execute(
            select(RestaurantMenuCategory.id).where(
                RestaurantMenuCategory.restaurant_id == restaurant_id,
                RestaurantMenuCategory.is_deleted.is_(False),
            )
        ).scalars().all()
        if not category_ids:
            return 0
        return int(
            db.execute(
                select(func.count())
                .select_from(RestaurantMenuItem)
                .where(
                    RestaurantMenuItem.category_id.in_(category_ids),
                    RestaurantMenuItem.is_deleted.is_(False),
                )
            ).scalar_one()
            or 0
        )
