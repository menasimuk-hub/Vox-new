"""Restaurant order line unavailable + customer WhatsApp substitution."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abuu.models.entities import (
    AbuuConversationSession,
    CustomerOrder,
    CustomerOrderItem,
    CustomerProfile,
    RestaurantMenuCategory,
    RestaurantMenuItem,
)
from app.abuu.services.notification_service import AbuuNotificationService
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.order_service import AbuuOrderService
from app.abuu.services.reply_service import (
    item_unavailable_message,
    order_substitution_updated_message,
    substitution_prompt_message,
)


class AbuuOrderSubstitutionService:
    @staticmethod
    def refresh_substitution_pending(db: Session, order: CustomerOrder) -> None:
        db.flush()
        pending = db.execute(
            select(CustomerOrderItem.id).where(
                CustomerOrderItem.order_id == order.id,
                CustomerOrderItem.unavailable.is_(True),
                CustomerOrderItem.substitution_status == "pending_customer",
            )
        ).first()
        order.substitution_pending = pending is not None
        order.updated_at = datetime.utcnow()
        db.add(order)

    @staticmethod
    def mark_line_unavailable(
        db: Session,
        *,
        order: CustomerOrder,
        line_id: str,
        restaurant_id: str,
    ) -> CustomerOrderItem:
        if order.restaurant_id != restaurant_id:
            raise ValueError("Order not found")
        if order.status not in {"sent_to_restaurant", "preparing"}:
            raise ValueError("Order cannot be modified from current status")

        line = db.get(CustomerOrderItem, line_id)
        if line is None or line.order_id != order.id:
            raise ValueError("Order item not found")
        if line.unavailable and line.substitution_status == "pending_customer":
            return line

        line.unavailable = True
        line.unavailable_at = datetime.utcnow()
        line.substitution_status = "pending_customer"
        db.add(line)
        AbuuOrderSubstitutionService.refresh_substitution_pending(db, order)
        AbuuOrderService.append_event(
            db,
            order.id,
            "item_unavailable",
            {"order_item_id": line.id, "menu_item_id": line.menu_item_id},
        )
        return line

    @staticmethod
    def undo_line_unavailable(
        db: Session,
        *,
        order: CustomerOrder,
        line_id: str,
        restaurant_id: str,
    ) -> CustomerOrderItem:
        if order.restaurant_id != restaurant_id:
            raise ValueError("Order not found")
        line = db.get(CustomerOrderItem, line_id)
        if line is None or line.order_id != order.id:
            raise ValueError("Order item not found")
        if line.substitution_status == "resolved":
            raise ValueError("Substitution already resolved")

        line.unavailable = False
        line.unavailable_at = None
        line.substitution_status = None
        db.add(line)
        AbuuOrderSubstitutionService.refresh_substitution_pending(db, order)
        return line

    @staticmethod
    def setup_substitution_session(db: Session, *, phone: str, order_id: str, pending_line_id: str) -> None:
        context = {"pending_substitution_line_id": pending_line_id}
        AbuuOrderDraftService.upsert_session(
            db,
            phone=phone,
            step="awaiting_substitution",
            context=context,
            active_order_id=order_id,
        )

    @staticmethod
    def find_menu_item_for_text(db: Session, restaurant_id: str, text: str) -> RestaurantMenuItem | None:
        normalized = (text or "").strip().lower()
        if not normalized:
            return None

        rows = db.execute(
            select(RestaurantMenuItem)
            .join(RestaurantMenuCategory, RestaurantMenuItem.category_id == RestaurantMenuCategory.id)
            .where(
                RestaurantMenuCategory.restaurant_id == restaurant_id,
                RestaurantMenuCategory.is_deleted.is_(False),
                RestaurantMenuItem.is_deleted.is_(False),
                RestaurantMenuItem.is_available.is_(True),
            )
        ).scalars().all()

        best: RestaurantMenuItem | None = None
        best_len = 0
        for item in rows:
            for name in (item.name_en or "", item.name_ar or ""):
                n = name.strip().lower()
                if not n:
                    continue
                if n in normalized or normalized in n:
                    if len(n) > best_len:
                        best = item
                        best_len = len(n)
        return best

    @staticmethod
    def parse_quantity(text: str) -> int:
        m = re.search(r"(\d+)", text or "")
        if m:
            return max(1, min(10, int(m.group(1))))
        return 1

    @staticmethod
    def handle_customer_reply(
        db: Session,
        *,
        session: AbuuConversationSession,
        order: CustomerOrder,
        customer: CustomerProfile,
        text: str,
        lang: str,
    ) -> dict[str, Any]:
        context = {}
        if session.context_json:
            try:
                context = json.loads(session.context_json)
            except json.JSONDecodeError:
                context = {}

        pending_line_id = context.get("pending_substitution_line_id")
        if not pending_line_id:
            pending = db.execute(
                select(CustomerOrderItem).where(
                    CustomerOrderItem.order_id == order.id,
                    CustomerOrderItem.unavailable.is_(True),
                    CustomerOrderItem.substitution_status == "pending_customer",
                )
            ).scalars().first()
            pending_line_id = pending.id if pending else None

        if not pending_line_id:
            AbuuOrderDraftService.upsert_session(db, phone=customer.phone, step="idle", context={})
            order.substitution_pending = False
            db.add(order)
            return {"handled": True, "action": "substitution_already_resolved"}

        line = db.get(CustomerOrderItem, pending_line_id)
        if line is None or line.order_id != order.id:
            raise ValueError("Pending substitution line not found")

        replacement = AbuuOrderSubstitutionService.find_menu_item_for_text(db, order.restaurant_id, text)
        if replacement is None:
            return {
                "handled": False,
                "action": "substitution_unmatched",
                "reply": substitution_prompt_message(
                    line.name_ar if lang == "ar" else line.name_en or "item",
                    lang,
                ),
            }

        qty = AbuuOrderSubstitutionService.parse_quantity(text)
        order.total_agorot = max(0, int(order.total_agorot or 0) - int(line.line_total_agorot or 0))
        line.substitution_status = "resolved"
        db.add(line)
        db.delete(line)

        AbuuOrderDraftService.add_item(db, order, replacement, quantity=qty)
        AbuuOrderSubstitutionService.refresh_substitution_pending(db, order)

        AbuuOrderService.append_event(
            db,
            order.id,
            "substitution_applied",
            {
                "removed_line_id": pending_line_id,
                "replacement_menu_item_id": replacement.id,
                "quantity": qty,
            },
        )

        AbuuNotificationService.create_if_absent(
            db,
            target_type="restaurant",
            target_id=order.restaurant_id,
            order_id=order.id,
            kind="substitution_resolved",
            title="تم تحديث الطلب",
            body=f"Customer replaced unavailable item — order {order.id[:8]}",
            payload={"order_id": order.id},
        )

        if order.substitution_pending:
            next_pending = db.execute(
                select(CustomerOrderItem).where(
                    CustomerOrderItem.order_id == order.id,
                    CustomerOrderItem.substitution_status == "pending_customer",
                )
            ).scalars().first()
            if next_pending:
                context["pending_substitution_line_id"] = next_pending.id
                AbuuOrderDraftService.upsert_session(
                    db,
                    phone=customer.phone,
                    step="awaiting_substitution",
                    context=context,
                    active_order_id=order.id,
                )
            else:
                AbuuOrderDraftService.upsert_session(db, phone=customer.phone, step="idle", context={})
        else:
            AbuuOrderDraftService.upsert_session(db, phone=customer.phone, step="idle", context={})

        reply = order_substitution_updated_message(order, replacement, qty, lang)
        return {"handled": True, "action": "substitution_applied", "reply": reply}
