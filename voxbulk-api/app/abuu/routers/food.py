"""Local food data API — snapshots for Gaza Agent (no LLM)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.abuu.agent.router import _verify_internal_key
from app.abuu.market.registry import get_market_agent, marketplace_scope, restaurant_scope
from app.abuu.services.yallasay_wa_snapshot_service import YallasayWaSnapshotService
from app.core.abuu_database import get_abuu_db

router = APIRouter(prefix="/abuu/food", tags=["abuu-food"])


@router.get("/health")
def food_health(abuu_db: Session = Depends(get_abuu_db)):
    market = get_market_agent(abuu_db)
    row = YallasayWaSnapshotService.get(
        abuu_db,
        scope=marketplace_scope(market.id),
        kind="restaurant_list",
        lang="ar",
    )
    return {
        "ok": True,
        "market_id": market.id,
        "agent": market.display_name_en,
        "snapshot_updated_at": row.updated_at.isoformat() if row else None,
    }


@router.get("/restaurants")
def list_restaurants(
    lang: str = Query(default="ar"),
    abuu_db: Session = Depends(get_abuu_db),
):
    market = get_market_agent(abuu_db)
    body = YallasayWaSnapshotService.get_body(
        abuu_db,
        scope=marketplace_scope(market.id),
        kind="restaurant_list",
        lang=lang if lang in {"ar", "en"} else "ar",
    )
    if not body:
        YallasayWaSnapshotService.rebuild_marketplace(abuu_db)
        abuu_db.commit()
        body = YallasayWaSnapshotService.get_body(
            abuu_db,
            scope=marketplace_scope(market.id),
            kind="restaurant_list",
            lang=lang if lang in {"ar", "en"} else "ar",
        )
    return {"ok": True, "market_id": market.id, "body": body or ""}


@router.get("/restaurants/{restaurant_id}/menu")
def restaurant_menu(
    restaurant_id: str,
    lang: str = Query(default="ar"),
    abuu_db: Session = Depends(get_abuu_db),
):
    body = YallasayWaSnapshotService.get_body(
        abuu_db,
        scope=restaurant_scope(restaurant_id),
        kind="menu",
        lang=lang if lang in {"ar", "en"} else "ar",
    )
    return {"ok": True, "restaurant_id": restaurant_id, "body": body or ""}


@router.get("/restaurants/{restaurant_id}/offers")
def restaurant_offers(
    restaurant_id: str,
    lang: str = Query(default="ar"),
    abuu_db: Session = Depends(get_abuu_db),
):
    body = YallasayWaSnapshotService.get_body(
        abuu_db,
        scope=restaurant_scope(restaurant_id),
        kind="offers",
        lang=lang if lang in {"ar", "en"} else "ar",
    )
    return {"ok": True, "restaurant_id": restaurant_id, "body": body or ""}


@router.post("/rebuild")
def rebuild_all(
    abuu_db: Session = Depends(get_abuu_db),
    _: None = Depends(_verify_internal_key),
):
    market = get_market_agent(abuu_db)
    for rid in market.pilot_restaurant_ids:
        YallasayWaSnapshotService.rebuild_restaurant(abuu_db, rid)
    YallasayWaSnapshotService.rebuild_marketplace(abuu_db)
    abuu_db.commit()
    return {"ok": True, "market_id": market.id, "restaurants": len(market.pilot_restaurant_ids)}


@router.post("/rebuild/{restaurant_id}")
def rebuild_one(
    restaurant_id: str,
    abuu_db: Session = Depends(get_abuu_db),
    _: None = Depends(_verify_internal_key),
):
    YallasayWaSnapshotService.rebuild_restaurant(abuu_db, restaurant_id)
    YallasayWaSnapshotService.rebuild_marketplace(abuu_db)
    abuu_db.commit()
    return {"ok": True, "restaurant_id": restaurant_id}
