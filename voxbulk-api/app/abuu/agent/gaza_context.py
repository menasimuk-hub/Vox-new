"""Load local snapshot + cart context for Gaza Agent."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.abuu.agent.session import Session as AgentSession
from app.abuu.market.registry import get_market_agent, marketplace_scope, restaurant_scope
from app.abuu.models.entities import CustomerProfile
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.yallasay_wa_snapshot_service import YallasayWaSnapshotService


def _load_menu_index_from_snapshot(
    db: Session,
    *,
    restaurant_id: str,
    lang: str,
) -> tuple[str | None, list[dict[str, Any]]]:
    row = YallasayWaSnapshotService.get(
        db,
        scope=restaurant_scope(restaurant_id),
        kind="menu",
        lang=lang,
    )
    items: list[dict[str, Any]] = []
    body: str | None = None
    if row is not None:
        body = YallasayWaSnapshotService.get_body(
            db,
            scope=restaurant_scope(restaurant_id),
            kind="menu",
            lang=lang,
        )
        if row.payload_json:
            try:
                payload = json.loads(row.payload_json)
                raw_items = payload.get("items") or []
                if isinstance(raw_items, list):
                    items = [row for row in raw_items if isinstance(row, dict)]
            except json.JSONDecodeError:
                pass
    return body, items


def refresh_menu_item_index(
    db: Session,
    session: AgentSession,
    *,
    restaurant_id: str,
    lang: str,
) -> tuple[str | None, list[dict[str, Any]]]:
    """Sync menu_item_index with snapshot or DB; set dish-pick session flags."""
    body, items = _load_menu_index_from_snapshot(db, restaurant_id=restaurant_id, lang=lang)
    if not items:
        menu_rows = AbuuOrderDraftService.list_menu_items(db, restaurant_id, limit=80)
        items = [
            {
                "index": idx,
                "id": item.id,
                "name_en": item.name_en,
                "name_ar": item.name_ar,
                "price_agorot": int(item.price_agorot or 0),
            }
            for idx, item in enumerate(menu_rows, start=1)
        ]
    session.context["menu_item_index"] = items
    session.context["awaiting_dish_pick"] = True
    session.context["awaiting_restaurant_pick"] = False
    session.context["last_list_type"] = "menu"
    return body, items


def prefetch_gaza_agent_context(
    db: Session,
    session: AgentSession,
    *,
    customer: CustomerProfile,
) -> dict[str, str]:
    market = get_market_agent(db)
    lang = session.language or customer.preferred_language or "ar"
    if lang not in {"ar", "en"}:
        lang = "ar"
    ctx: dict[str, str] = {"market_id": market.id, "agent_name": market.display_name_ar if lang == "ar" else market.display_name_en}

    listing = YallasayWaSnapshotService.get_body(
        db,
        scope=marketplace_scope(market.id),
        kind="restaurant_list",
        lang=lang,
    )
    if listing:
        ctx["restaurant_list"] = listing
        session.context["prefetched_restaurant_list"] = listing

    if session.restaurant_id:
        menu = YallasayWaSnapshotService.get_body(
            db,
            scope=restaurant_scope(session.restaurant_id),
            kind="menu",
            lang=lang,
        )
        if menu:
            ctx["menu"] = menu
            session.context["prefetched_menu"] = menu
        offers = YallasayWaSnapshotService.get_body(
            db,
            scope=restaurant_scope(session.restaurant_id),
            kind="offers",
            lang=lang,
        )
        if offers:
            ctx["offers"] = offers
            session.context["prefetched_offers"] = offers

    if session.restaurant_id:
        refresh_menu_item_index(
            db,
            session,
            restaurant_id=session.restaurant_id,
            lang=lang,
        )

    return ctx
