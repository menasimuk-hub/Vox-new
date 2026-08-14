"""Smart Card trial + seat resize billing."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.services.smart_card.billing_service import (
    DEFAULT_SMART_CARD_TRIAL_DAYS,
    SmartCardBillingError,
    SmartCardBillingService,
)


def test_resolve_trial_days_defaults_to_30():
    plan = Plan(id=str(uuid.uuid4()), code="sc_seat", name="Seats", trial_days_default=0)
    db = MagicMock()
    # No pending promo
    from unittest.mock import patch

    with patch(
        "app.services.smart_card.billing_service.PromoDiscountService.peek_amount",
        return_value={"trial_days": 0, "discount_applied": False},
    ):
        assert SmartCardBillingService.resolve_trial_days(db, org_id="org", plan=plan) == DEFAULT_SMART_CARD_TRIAL_DAYS


def test_resolve_trial_days_uses_plan_default():
    plan = Plan(id=str(uuid.uuid4()), code="sc_seat", name="Seats", trial_days_default=45)
    db = MagicMock()
    from unittest.mock import patch

    with patch(
        "app.services.smart_card.billing_service.PromoDiscountService.peek_amount",
        return_value={"trial_days": 0, "discount_applied": False},
    ):
        assert SmartCardBillingService.resolve_trial_days(db, org_id="org", plan=plan) == 45


def test_resolve_trial_days_prefers_promo():
    plan = Plan(id=str(uuid.uuid4()), code="sc_seat", name="Seats", trial_days_default=30)
    db = MagicMock()
    from unittest.mock import patch

    with patch(
        "app.services.smart_card.billing_service.PromoDiscountService.peek_amount",
        return_value={"trial_days": 14, "discount_applied": True},
    ):
        assert SmartCardBillingService.resolve_trial_days(db, org_id="org", plan=plan) == 14


def test_normalize_seats_bounds():
    assert SmartCardBillingService._normalize_seats(3) == 3
    try:
        SmartCardBillingService._normalize_seats(0)
        assert False, "expected error"
    except SmartCardBillingError:
        pass
    try:
        SmartCardBillingService._normalize_seats(501)
        assert False, "expected error"
    except SmartCardBillingError:
        pass
