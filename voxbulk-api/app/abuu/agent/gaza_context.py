"""Load local snapshot + cart context for Gaza Agent."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.abuu.agent.session import Session as AgentSession
from app.abuu.market.registry import get_market_agent, marketplace_scope, restaurant_scope
from app.abuu.models.entities import CustomerProfile
from app.abuu.services.yallasay_wa_snapshot_service import YallasayWaSnapshotService


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

    row = YallasayWaSnapshotService.get(
        db,
        scope=restaurant_scope(session.restaurant_id),
        kind="menu",
        lang=lang,
    ) if session.restaurant_id else None
    if row and row.payload_json:
        try:
            session.context["menu_item_index"] = json.loads(row.payload_json).get("items") or []
        except json.JSONDecodeError:
            pass

    return ctx
