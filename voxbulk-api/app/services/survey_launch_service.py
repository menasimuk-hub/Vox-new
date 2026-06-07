"""Survey launch orchestration after entitlement / payment checks."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder
from app.services.platform_catalog_service import ServiceOrderService
from app.services.survey_launch_eligibility_service import (
    SurveyLaunchEligibilityError,
    SurveyLaunchEligibilityService,
)

logger = logging.getLogger(__name__)


class SurveyLaunchService:
    @staticmethod
    def launch(
        db: Session,
        order: ServiceOrder,
        org: Organisation,
        *,
        run_now: bool = True,
    ) -> dict[str, Any]:
        if order.service_code != "survey":
            raise ValueError("Launch is only for survey orders")

        from app.services.interview_campaign_service import ensure_campaign_id

        order = ensure_campaign_id(db, order)

        eligibility = SurveyLaunchEligibilityService.assert_can_launch(db, order, org)

        if order.payment_status != "approved":
            order = SurveyLaunchEligibilityService.approve_if_covered(db, order, org)

        if order.payment_status != "approved":
            raise SurveyLaunchEligibilityError("Payment must be approved before launch")

        SurveyLaunchEligibilityService.consume_launch_allowance(db, order, org)

        if run_now:
            order.run_mode = "manual"
            order.updated_at = datetime.utcnow()
            db.add(order)
            db.commit()
            db.refresh(order)
            order = ServiceOrderService.start_order(db, order)
        else:
            if not order.scheduled_start_at:
                raise ValueError("Set a schedule date before scheduling launch")
            order.run_mode = "scheduled"
            order.updated_at = datetime.utcnow()
            db.add(order)
            db.commit()
            db.refresh(order)
            order = ServiceOrderService.schedule_order(db, order)

        logger.info(
            "survey_launch_complete order_id=%s org_id=%s mode=%s status=%s eligibility_mode=%s",
            order.id,
            org.id,
            "now" if run_now else "scheduled",
            order.status,
            eligibility.get("mode"),
        )
        return {
            "ok": True,
            "order_id": order.id,
            "campaign_id": order.campaign_id,
            "status": order.status,
            "payment_status": order.payment_status,
            "eligibility_mode": eligibility.get("mode"),
            "message": "Survey launched." if run_now else "Survey scheduled.",
        }
