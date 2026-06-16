from __future__ import annotations

import pytest

from app.abuu.agent.prefetch import prefetch_offers
from app.abuu.agent.session import Session as AgentSession
from app.abuu.services.offer_service import best_offer_match, rank_offers_by_query
from app.abuu.services.seed_service import AbuuSeedService


@pytest.fixture
def abuu_seeded(app_client):
    from app.abuu.services.agent_settings_seed import seed_agent_settings
    from app.core.abuu_database import get_abuu_sessionmaker

    with get_abuu_sessionmaker()() as db:
        AbuuSeedService.seed_restaurants_if_empty(db)
        AbuuSeedService.seed_offers_if_empty(db)
        seed_agent_settings(db)
        db.commit()
        yield db


def test_rank_offers_bahr_family_query_prefers_fish_offer(abuu_seeded):
    db = abuu_seeded
    ranked = rank_offers_by_query(db, "عرض البحر العائلي", limit=5)
    assert ranked
    top = ranked[0]
    assert top.offer.id == "abuu-offer-fish-1"
    assert "سمك" in (top.offer.title_ar or "")


def test_rank_offers_chicken_family_query_prefers_chicken_offer(abuu_seeded):
    db = abuu_seeded
    ranked = rank_offers_by_query(db, "عرض عائلي دجاج", limit=5)
    assert ranked
    top = ranked[0]
    assert top.offer.id == "abuu-offer-chicken-1"
    assert "دجاج" in (top.offer.title_ar or "")


def test_best_offer_match_sets_fish_for_bahr_query(abuu_seeded):
    db = abuu_seeded
    match = best_offer_match(db, "بدي عرض البحر العائلي", lang="ar")
    assert match is not None
    assert match.offer.id == "abuu-offer-fish-1"
    assert match.score >= 5.0


def test_prefetch_offers_sets_matched_hint_for_approximate_name(abuu_seeded):
    db = abuu_seeded
    session = AgentSession(customer_wa_number="+972509990099", language="ar")
    listing = prefetch_offers(db, session, query="عرض البحر العائلي")

    assert session.context.get("matched_offer_id") == "abuu-offer-fish-1"
    hint = session.context.get("matched_offer_hint")
    assert isinstance(hint, str)
    assert "سمك" in hint
    assert hint in listing
