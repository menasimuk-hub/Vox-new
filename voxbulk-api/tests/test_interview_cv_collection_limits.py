"""Tests for per-campaign CV collection limits and config validation."""

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.org_usage_period import OrgUsagePeriod
from app.models.plan import Plan
from app.models.service_order import ServiceOrder
from app.models.subscription import Subscription
from app.models.user import User
from app.services.interview_cv_collection_service import (
    CvCollectionConfigError,
    compute_cv_collection_limits,
    cv_collection_at_capacity,
    is_cv_email_active_campaign,
    validate_and_apply_cv_config,
)
from app.services.platform_catalog_service import ServiceOrderService


@pytest.fixture()
def db_session():
    from app.core.database import Base, get_engine, get_sessionmaker
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def _seed_org_with_plan(db: Session, *, cv_scans_included: int = 10) -> tuple[Organisation, User, Plan]:
    org = Organisation(name="Limits Org")
    user = User(email=f"lim-{uuid.uuid4().hex[:8]}@test.com", password_hash="x", is_active=True)
    plan = Plan(
        code="starter",
        name="Starter",
        price_gbp_pence=9900,
        interval="monthly",
        cv_scans_included=cv_scans_included,
    )
    db.add(org)
    db.add(user)
    db.add(plan)
    db.flush()
    db.add(
        Subscription(
            org_id=org.id,
            plan_id=plan.id,
            status="active",
            payment_provider="gocardless",
        )
    )
    now = datetime.utcnow()
    db.add(
        OrgUsagePeriod(
            org_id=org.id,
            period_start=now,
            period_end=now + timedelta(days=30),
            status="active",
            plan_code=plan.code,
            cv_scans_included=cv_scans_included,
            cv_scans_used=0,
        )
    )
    db.commit()
    return org, user, plan


def _interview_order(
    db: Session,
    *,
    org: Organisation,
    user: User,
    enabled: bool = True,
    max_cvs: int | None = 5,
    closed: bool = False,
) -> ServiceOrder:
    now = datetime.utcnow()
    cfg: dict = {
        "cv_email_enabled": enabled,
        "cv_collection_start_at": (now - timedelta(hours=1)).isoformat(),
        "cv_email_start_at": (now - timedelta(hours=1)).isoformat(),
        "cv_auto_close_on_limit": True,
    }
    if max_cvs is not None:
        cfg["cv_max_count"] = max_cvs
    if closed:
        cfg["cv_collection_closed_early_at"] = now.isoformat()
    order = ServiceOrderService.create_order(
        db,
        org_id=org.id,
        user_id=user.id,
        service_code="interview",
        title="Role",
        config=cfg,
    )
    db.commit()
    db.refresh(order)
    return order


def test_active_campaign_reserves_max_allocation(db_session: Session):
    org, user, _plan = _seed_org_with_plan(db_session, cv_scans_included=20)
    _interview_order(db_session, org=org, user=user, max_cvs=8)
    current = _interview_order(db_session, org=org, user=user, max_cvs=3)

    limits = compute_cv_collection_limits(db_session, org.id, exclude_order_id=current.id)
    assert limits["reserved_across_active"] == 8
    assert limits["plan_balance_remaining"] == 20
    assert limits["default_max_cvs"] == 12
    assert limits["available_for_order"] == 12


def test_closed_campaign_returns_allocation(db_session: Session):
    org, user, _plan = _seed_org_with_plan(db_session, cv_scans_included=20)
    _interview_order(db_session, org=org, user=user, max_cvs=8, closed=True)

    limits = compute_cv_collection_limits(db_session, org.id)
    assert limits["reserved_across_active"] == 0
    assert limits["default_max_cvs"] == 20


def test_validate_applies_safe_defaults(db_session: Session):
    org, user, _plan = _seed_org_with_plan(db_session, cv_scans_included=15)
    order = _interview_order(db_session, org=org, user=user, enabled=False, max_cvs=None)

    cfg = validate_and_apply_cv_config(
        db_session,
        org.id,
        order,
        {"cv_email_enabled": True},
        previous_cfg={"cv_email_enabled": False},
    )
    assert cfg["cv_auto_close_on_limit"] is True
    assert cfg["cv_max_count"] == 15
    assert cfg.get("cv_min_ats_score") == 40
    assert cfg["cv_collection_start_at"]


def test_validate_requires_overage_acknowledgement(db_session: Session):
    org, user, _plan = _seed_org_with_plan(db_session, cv_scans_included=5)
    _interview_order(db_session, org=org, user=user, max_cvs=4)
    order = _interview_order(db_session, org=org, user=user, max_cvs=1)

    with pytest.raises(CvCollectionConfigError, match="remaining plan allowance"):
        validate_and_apply_cv_config(
            db_session,
            org.id,
            order,
            {"cv_max_count": 3, "cv_email_enabled": True},
            previous_cfg=_loads(order),
        )


def test_validate_logs_pending_overage_when_acknowledged(db_session: Session):
    org, user, _plan = _seed_org_with_plan(db_session, cv_scans_included=5)
    order = _interview_order(db_session, org=org, user=user, max_cvs=2)

    cfg = validate_and_apply_cv_config(
        db_session,
        org.id,
        order,
        {"cv_max_count": 10, "cv_email_enabled": True, "cv_overage_acknowledged": True},
        previous_cfg=_loads(order),
    )
    pending = cfg.get("cv_overage_pending") or {}
    assert pending.get("extra_count") == 5
    assert pending.get("total_pence", 0) > 0


def test_at_capacity_ignores_auto_excluded(db_session: Session):
    org, user, _plan = _seed_org_with_plan(db_session)
    order = _interview_order(db_session, org=org, user=user, max_cvs=2)
    order.recipient_count = 3
    db_session.add(order)
    db_session.commit()

    from app.models.service_order import ServiceOrderRecipient
    from datetime import datetime
    import json

    excluded = ServiceOrderRecipient(
        order_id=order.id,
        row_number=1,
        name="Excluded",
        status="excluded",
        result_json=json.dumps(
            {"auto_excluded_at": datetime.utcnow().isoformat(), "cv_exclusion_keyword": "agency"},
            ensure_ascii=False,
        ),
    )
    db_session.add(excluded)
    db_session.commit()

    assert cv_collection_at_capacity(db_session, order) is False

    accepted = ServiceOrderRecipient(
        order_id=order.id,
        row_number=2,
        name="One",
        status="pending",
        result_json="{}",
    )
    accepted2 = ServiceOrderRecipient(
        order_id=order.id,
        row_number=3,
        name="Two",
        status="pending",
        result_json="{}",
    )
    db_session.add(accepted)
    db_session.add(accepted2)
    db_session.commit()
    assert cv_collection_at_capacity(db_session, order) is True


def test_plan_balance_uses_subscription_not_stale_usage_row(db_session: Session):
    org, user, plan = _seed_org_with_plan(db_session, cv_scans_included=0)
    plan.cv_scans_included = 50
    db_session.add(plan)
    row = db_session.execute(select(OrgUsagePeriod).where(OrgUsagePeriod.org_id == org.id)).scalars().first()
    if row is not None:
        row.cv_scans_included = 0
        row.cv_scans_used = 5
        db_session.add(row)
    db_session.commit()

    limits = compute_cv_collection_limits(db_session, org.id)
    assert limits["plan_balance_remaining"] == 45
    assert limits["default_max_cvs"] == 45


def test_exclusion_keyword_match():
    from app.services.interview_cv_exclusion_service import match_exclusion_keyword

    assert match_exclusion_keyword("Worked at Acme Agency for 5 years", ["agency"]) == "agency"
    assert match_exclusion_keyword("Software engineer", ["agency"]) is None


def test_min_ats_score_saved_without_cv_email(db_session: Session):
    org, user, _plan = _seed_org_with_plan(db_session, cv_scans_included=15)
    order = _interview_order(db_session, org=org, user=user, enabled=False, max_cvs=None)

    cfg = validate_and_apply_cv_config(
        db_session,
        org.id,
        order,
        {"cv_min_ats_score": 55},
        previous_cfg=_loads(order),
    )
    assert cfg["cv_min_ats_score"] == 55
    assert cfg.get("cv_email_enabled") is not True


def test_apply_ats_threshold_to_scored_recipients(db_session: Session):
    from app.services.interview_cv_exclusion_service import apply_ats_threshold_to_order

    org, user, _plan = _seed_org_with_plan(db_session, cv_scans_included=15)
    order = _interview_order(db_session, org=org, user=user, enabled=False, max_cvs=None)
    cfg = validate_and_apply_cv_config(
        db_session,
        org.id,
        order,
        {"cv_min_ats_score": 70},
        previous_cfg=_loads(order),
    )
    order.config_json = __import__("json").dumps(cfg)
    db_session.add(order)
    db_session.commit()

    from app.models.service_order import ServiceOrderRecipient

    high = ServiceOrderRecipient(
        order_id=order.id,
        row_number=1,
        name="Strong",
        status="pending",
        ats_status="complete",
        ats_score=85,
        result_json="{}",
    )
    low = ServiceOrderRecipient(
        order_id=order.id,
        row_number=2,
        name="Weak",
        status="pending",
        ats_status="complete",
        ats_score=55,
        result_json="{}",
    )
    db_session.add_all([high, low])
    db_session.commit()

    result = apply_ats_threshold_to_order(db_session, order, min_score=70)
    assert result["eligible_count"] == 1
    assert result["rejected_count"] == 1

    db_session.refresh(high)
    db_session.refresh(low)
    assert high.status == "pending"
    assert low.status == "excluded"


def test_inactive_when_email_disabled(db_session: Session):
    org, user, _plan = _seed_org_with_plan(db_session)
    order = _interview_order(db_session, org=org, user=user, enabled=False)
    assert is_cv_email_active_campaign(order) is False


def _loads(order: ServiceOrder) -> dict:
    import json

    try:
        data = json.loads(order.config_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}
