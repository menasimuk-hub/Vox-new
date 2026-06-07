"""Survey launch entitlement checks — shared by API, UI, and start/schedule validation."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder
from app.services.org_service_credit_service import OrgServiceCreditError, OrgServiceCreditService
from app.services.platform_catalog_service import PlatformCatalogService, ServiceOrderService
from app.services.survey_billing_context import org_survey_billing_context
from app.services.usage_wallet_service import UsageWalletService

logger = logging.getLogger(__name__)


class SurveyLaunchEligibilityError(ValueError):
    pass


class SurveyLaunchEligibilityService:
    @staticmethod
    def _order_config(order: ServiceOrder) -> dict[str, Any]:
        try:
            data = json.loads(order.config_json or "{}")
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def estimated_whatsapp_units(order: ServiceOrder, *, channel: str | None = None) -> int:
        ch = channel or PlatformCatalogService.resolve_survey_channel(SurveyLaunchEligibilityService._order_config(order))
        if ch != "whatsapp":
            return 0
        return max(0, int(order.recipient_count or 0))

    @staticmethod
    def _quote_for_recipients(
        db: Session,
        order: ServiceOrder,
        *,
        recipient_count: int,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        count = max(int(recipient_count or 0), 0)
        if count <= 0:
            return {"total_pence": 0, "total_gbp": "£0.00", "lines": [], "recipient_count": 0}
        options = dict(config)
        options["org_id"] = order.org_id
        return PlatformCatalogService.calculate_quote(
            db,
            service_code="survey",
            recipient_count=count,
            options=options,
        )

    @staticmethod
    def _ensure_order_quote(db: Session, order: ServiceOrder) -> ServiceOrder:
        if order.quote_total_pence and order.quote_total_pence > 0 and order.status == "quoted":
            return order
        return ServiceOrderService.quote_order(db, order)

    @staticmethod
    def _attach_launch_pricing(
        quote: dict[str, Any],
        *,
        recipient_count: int,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Split quote into send estimate vs minimum charge for launch UI."""
        lines = list(quote.get("lines") or [])
        setup_fee = sum(int(line.get("amount_pence") or 0) for line in lines if line.get("kind") == "setup")
        bundle_line = next((line for line in lines if line.get("kind") == "bundle"), None)
        overage_line = next((line for line in lines if line.get("kind") == "overage"), None)
        count = max(int(recipient_count or 0), 0)
        estimated_send = 0
        minimum_charge = 0
        pricing_source = "quote_total"

        if overage_line:
            estimated_send = int(overage_line.get("amount_pence") or 0)
            pricing_source = "overage_units"
        elif bundle_line:
            bundle_size = max(int(bundle_line.get("bundle_size") or bundle_line.get("contacts_included") or 0), 1)
            bundle_price = int(bundle_line.get("amount_pence") or 0)
            minimum_charge = bundle_price
            if count > 0 and bundle_size > 0:
                estimated_send = int(round(bundle_price * count / bundle_size))
            pricing_source = "bundle_prorated"
        else:
            per_person = sum(
                int(line.get("amount_pence") or 0)
                for line in lines
                if line.get("kind") in {"per_person", "unit", "send"}
            )
            if per_person > 0:
                estimated_send = per_person
                pricing_source = "per_person"

        amount_due = int(quote.get("total_pence") or 0)
        if estimated_send <= 0 and amount_due > 0 and count > 0:
            estimated_send = amount_due - setup_fee if amount_due > setup_fee else amount_due

        return {
            **quote,
            "estimated_send_cost_pence": max(0, estimated_send),
            "estimated_send_cost_display": PlatformCatalogService._money(max(0, estimated_send)),
            "minimum_charge_pence": max(0, minimum_charge),
            "minimum_charge_display": PlatformCatalogService._money(max(0, minimum_charge)) if minimum_charge > 0 else None,
            "setup_fee_pence": setup_fee,
            "setup_fee_display": PlatformCatalogService._money(setup_fee) if setup_fee > 0 else None,
            "package_id": str(quote.get("selected_package_id") or config.get("package_id") or "") or None,
            "pricing_lines": lines,
            "pricing_source": pricing_source,
        }

    @staticmethod
    def _quote_payable_launch(
        db: Session,
        order: ServiceOrder,
        *,
        recipient_count: int,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        count = max(int(recipient_count or 0), 0)
        quote = SurveyLaunchEligibilityService._quote_for_recipients(
            db,
            order,
            recipient_count=count,
            config=config,
        )
        enriched = SurveyLaunchEligibilityService._attach_launch_pricing(
            quote,
            recipient_count=count,
            config=config,
        )
        logger.info(
            "survey_launch_pricing order_id=%s recipients=%s package_id=%s estimated_send=%s minimum=%s amount_due=%s source=%s",
            order.id,
            count,
            enriched.get("package_id"),
            enriched.get("estimated_send_cost_pence"),
            enriched.get("minimum_charge_pence"),
            enriched.get("total_pence"),
            enriched.get("pricing_source"),
        )
        return enriched

    @staticmethod
    def _set_block(base: dict[str, Any], *, code: str, reason: str, summary: str | None = None) -> dict[str, Any]:
        base["block_reason_code"] = code
        base["block_reason"] = reason
        base["summary"] = summary or reason
        base["launch_action"] = "blocked"
        logger.info(
            "survey_launch_billing_blocked order_id=%s code=%s reason=%s",
            base.get("order_id"),
            code,
            reason,
        )
        return base

    @staticmethod
    def compute(db: Session, order: ServiceOrder, org: Organisation) -> dict[str, Any]:
        if order.service_code != "survey":
            raise SurveyLaunchEligibilityError("Launch eligibility is only for survey orders")

        logger.info("survey_launch_billing_start order_id=%s org_id=%s", order.id, org.id)

        config = SurveyLaunchEligibilityService._order_config(order)
        channel = PlatformCatalogService.resolve_survey_channel(config)
        recipient_count = max(0, int(order.recipient_count or 0))
        estimated_usage = SurveyLaunchEligibilityService.estimated_whatsapp_units(order, channel=channel)
        billing = org_survey_billing_context(db, org)
        package_id = str(config.get("package_id") or "").strip() or None

        usage = UsageWalletService.get_current(db, org.id)
        logger.info(
            "survey_launch_package_lookup order_id=%s package_id=%s channel=%s",
            order.id,
            package_id,
            channel,
        )
        logger.info(
            "survey_launch_wallet_lookup order_id=%s org_id=%s wallet_status=%s wa_included=%s wa_used=%s",
            order.id,
            org.id,
            getattr(usage, "status", None) if usage else None,
            billing.get("whatsapp_included"),
            billing.get("whatsapp_used"),
        )
        logger.info(
            "survey_launch_allowance_result order_id=%s wa_remaining=%s has_allowance=%s survey_credits=%s",
            order.id,
            billing.get("whatsapp_remaining"),
            billing.get("has_whatsapp_allowance"),
            billing.get("survey_credits"),
        )
        logger.info(
            "survey_launch_usage_count order_id=%s recipient_count=%s estimated_whatsapp_usage=%s",
            order.id,
            recipient_count,
            estimated_usage,
        )

        base: dict[str, Any] = {
            "order_id": order.id,
            "campaign_name": order.title,
            "survey_channel": channel,
            "recipient_count": recipient_count,
            "estimated_whatsapp_usage": estimated_usage,
            "payment_status": order.payment_status,
            "order_status": order.status,
            "billing": billing,
            "can_launch": False,
            "payment_required": True,
            "mode": "blocked",
            "block_reason": None,
            "block_reason_code": None,
            "summary": "",
            "covered_by_allowance": 0,
            "covered_by_promo_credits": 0,
            "shortfall_units": 0,
            "amount_due_pence": 0,
            "amount_due_display": None,
            "quote_total_pence": int(order.quote_total_pence or 0),
            "quote_total_display": None,
            "remaining_whatsapp_after_launch": billing["whatsapp_remaining"],
            "remaining_promo_credits_after_launch": billing["survey_credits"],
            "package_label": billing.get("plan_name"),
            "launch_action": "blocked",
        }

        if recipient_count <= 0:
            return SurveyLaunchEligibilityService._set_block(
                base,
                code="no_recipients",
                reason="Upload at least one contact before launch.",
                summary="No recipients on this survey yet.",
            )

        if order.payment_status == "approved":
            base.update(
                {
                    "can_launch": True,
                    "payment_required": False,
                    "mode": "already_paid",
                    "launch_action": "launch",
                    "summary": "Payment is approved — you can launch this campaign.",
                }
            )
            logger.info(
                "survey_launch_billing_done order_id=%s success=true launch_action=launch mode=already_paid",
                order.id,
            )
            return base

        wa_remaining = int(billing["whatsapp_remaining"] or 0)
        survey_credits = int(billing["survey_credits"] or 0)

        if OrgServiceCreditService.can_cover(org, service_code="survey", recipient_count=recipient_count):
            base.update(
                {
                    "can_launch": True,
                    "payment_required": False,
                    "mode": "promo_credits",
                    "launch_action": "launch",
                    "covered_by_promo_credits": recipient_count,
                    "remaining_promo_credits_after_launch": survey_credits - recipient_count,
                    "summary": (
                        f"This campaign is covered by your survey promo credits "
                        f"({survey_credits} available · this launch uses {recipient_count})."
                    ),
                }
            )
            logger.info(
                "survey_launch_billing_done order_id=%s success=true launch_action=launch mode=promo_credits",
                order.id,
            )
            return base

        if channel == "whatsapp" and billing.get("has_whatsapp_allowance") and wa_remaining >= estimated_usage > 0:
            base.update(
                {
                    "can_launch": True,
                    "payment_required": False,
                    "mode": "subscription_whatsapp",
                    "launch_action": "launch",
                    "covered_by_allowance": estimated_usage,
                    "remaining_whatsapp_after_launch": wa_remaining - estimated_usage,
                    "summary": (
                        "This campaign is covered by your package. "
                        f"Remaining WhatsApp allowance: {wa_remaining}. "
                        f"Estimated usage for this launch: {estimated_usage}."
                    ),
                }
            )
            logger.info(
                "survey_launch_billing_done order_id=%s success=true launch_action=launch mode=subscription_whatsapp",
                order.id,
            )
            return base

        shortfall_units = 0
        covered_by_allowance = 0
        if channel == "whatsapp" and billing.get("has_whatsapp_allowance") and wa_remaining > 0:
            covered_by_allowance = min(wa_remaining, estimated_usage)
            shortfall_units = max(0, estimated_usage - covered_by_allowance)

        payable_recipients = recipient_count if shortfall_units <= 0 else shortfall_units
        try:
            amount_quote = SurveyLaunchEligibilityService._quote_payable_launch(
                db,
                order,
                recipient_count=payable_recipients,
                config=config,
            )
        except ValueError as e:
            msg = str(e)
            code = "package_not_found" if "package" in msg.lower() else "quote_failed"
            return SurveyLaunchEligibilityService._set_block(base, code=code, reason=msg)

        amount_pence = int(amount_quote.get("total_pence") or 0)
        amount_display = str(amount_quote.get("total_gbp") or PlatformCatalogService._money(amount_pence))

        if amount_pence <= 0 and not billing["payg_allowed"]:
            return SurveyLaunchEligibilityService._set_block(
                base,
                code="package_not_found",
                reason="Package not found.",
            )

        if amount_pence <= 0:
            base.update(
                {
                    "can_launch": True,
                    "payment_required": False,
                    "mode": "included",
                    "launch_action": "launch",
                    "amount_due_pence": 0,
                    "amount_due_display": "£0.00",
                    "summary": "This launch is included — no payment required.",
                }
            )
            logger.info(
                "survey_launch_billing_done order_id=%s success=true launch_action=launch mode=included",
                order.id,
            )
            return base

        if not billing["payg_allowed"]:
            return SurveyLaunchEligibilityService._set_block(
                base,
                code="package_not_found",
                reason="Package not found.",
                summary="No active package found for WhatsApp launch.",
            )

        if shortfall_units > 0:
            summary = (
                "Your package covers part of this launch. "
                f"Remaining WhatsApp allowance: {wa_remaining}. "
                f"Covered by package: {covered_by_allowance}. "
                f"Additional WhatsApp usage required: {shortfall_units}. "
                f"Amount due: {amount_display}."
            )
            mode = "partial_allowance"
        elif billing["has_active_subscription"]:
            summary = (
                f"Your package allowance does not cover this launch. "
                f"Estimated usage: {estimated_usage or recipient_count}. "
                f"Amount due: {amount_display}."
            )
            mode = "payg"
        else:
            summary = (
                "No active package found for WhatsApp launch. "
                f"Pay-as-you-go amount due: {amount_display}."
                if channel == "whatsapp"
                else f"Pay-as-you-go amount due: {amount_display}."
            )
            mode = "payg"

        allowance_exhausted = (
            channel == "whatsapp"
            and billing.get("has_whatsapp_allowance")
            and wa_remaining <= 0
            and estimated_usage > 0
        )
        block_reason_code = None
        block_reason = None
        if allowance_exhausted:
            wa_included = int(billing.get("whatsapp_included") or 0)
            wa_used = int(billing.get("whatsapp_used") or 0)
            block_reason_code = "whatsapp_usage_limit"
            block_reason = (
                f"Your WhatsApp allowance has been fully used. "
                f"Included: {wa_included}, used: {wa_used}, remaining: 0. "
                f"This launch would require additional billing of {amount_display}."
            )
            summary = block_reason
            logger.info(
                "survey_launch_blocked order_id=%s code=whatsapp_usage_limit wa_remaining=%s amount_due=%s recipient_count=%s",
                order.id,
                wa_remaining,
                amount_pence,
                recipient_count,
            )
        else:
            logger.info(
                "survey_launch_billing_done order_id=%s success=false launch_action=pay_and_launch mode=%s amount_due=%s",
                order.id,
                mode,
                amount_pence,
            )

        base.update(
            {
                "can_launch": False,
                "payment_required": True,
                "mode": mode,
                "launch_action": "pay_and_launch",
                "block_reason_code": block_reason_code,
                "block_reason": block_reason,
                "allowance_exhausted": allowance_exhausted,
                "covered_by_allowance": covered_by_allowance,
                "shortfall_units": shortfall_units or (estimated_usage if channel == "whatsapp" else recipient_count),
                "amount_due_pence": amount_pence,
                "amount_due_display": amount_display,
                "estimated_send_cost_pence": amount_quote.get("estimated_send_cost_pence"),
                "estimated_send_cost_display": amount_quote.get("estimated_send_cost_display"),
                "minimum_charge_pence": amount_quote.get("minimum_charge_pence"),
                "minimum_charge_display": amount_quote.get("minimum_charge_display"),
                "setup_fee_pence": amount_quote.get("setup_fee_pence"),
                "setup_fee_display": amount_quote.get("setup_fee_display"),
                "package_id": amount_quote.get("package_id"),
                "pricing_lines": amount_quote.get("pricing_lines") or [],
                "pricing_source": amount_quote.get("pricing_source"),
                "quote_total_pence": amount_pence,
                "quote_total_display": amount_display,
                "remaining_whatsapp_after_launch": max(0, wa_remaining - covered_by_allowance),
                "summary": summary,
            }
        )
        return base

    @staticmethod
    def prepare_order_payment_quote(db: Session, order: ServiceOrder, org: Organisation) -> ServiceOrder:
        """Align order quote with payable shortfall/full payg amount before GoCardless."""
        eligibility = SurveyLaunchEligibilityService.compute(db, order, org)
        if not eligibility.get("payment_required"):
            return order
        amount_pence = int(eligibility.get("amount_due_pence") or 0)
        if amount_pence <= 0:
            raise SurveyLaunchEligibilityError("Nothing to pay for this launch")
        shortfall = int(eligibility.get("shortfall_units") or 0)
        config = SurveyLaunchEligibilityService._order_config(order)
        if shortfall > 0:
            quote = SurveyLaunchEligibilityService._quote_for_recipients(
                db, order, recipient_count=shortfall, config=config
            )
        else:
            order = SurveyLaunchEligibilityService._ensure_order_quote(db, order)
            quote = json.loads(order.quote_breakdown_json or "{}") if order.quote_breakdown_json else {}
            quote["total_pence"] = int(order.quote_total_pence or 0)
        order.quote_total_pence = int(quote.get("total_pence") or amount_pence)
        order.quote_breakdown_json = json.dumps(quote, ensure_ascii=False)
        order.status = "quoted"
        covered = int(eligibility.get("covered_by_allowance") or 0)
        if covered > 0:
            config = SurveyLaunchEligibilityService._order_config(order)
            config["launch_allowance_units"] = covered
            order.config_json = json.dumps(config, ensure_ascii=False)
        db.add(order)
        db.commit()
        db.refresh(order)
        return order

    @staticmethod
    def approve_if_covered(db: Session, order: ServiceOrder, org: Organisation) -> ServiceOrder:
        if order.payment_status == "approved":
            return order

        eligibility = SurveyLaunchEligibilityService.compute(db, order, org)
        mode = str(eligibility.get("mode") or "")

        if mode == "promo_credits":
            try:
                return OrgServiceCreditService.apply_to_order(db, order, org)
            except OrgServiceCreditError as e:
                raise SurveyLaunchEligibilityError(str(e)) from e

        if mode == "subscription_whatsapp":
            from datetime import datetime

            plan_name = str(eligibility.get("package_label") or "package").strip() or "package"
            covered = int(eligibility.get("covered_by_allowance") or eligibility.get("estimated_whatsapp_usage") or 0)
            config = SurveyLaunchEligibilityService._order_config(order)
            if covered > 0:
                config["launch_allowance_units"] = covered
                order.config_json = json.dumps(config, ensure_ascii=False)
            order.payment_method = "subscription_whatsapp"
            order.payment_status = "approved"
            order.status = "paid"
            order.payment_note = f"Covered by {plan_name} WhatsApp allowance"
            order.updated_at = datetime.utcnow()
            db.add(order)
            db.commit()
            db.refresh(order)
            return order

        if mode in {"already_paid", "included"}:
            return order

        raise SurveyLaunchEligibilityError(
            str(eligibility.get("block_reason") or eligibility.get("summary") or "Payment required before launch")
        )

    @staticmethod
    def consume_launch_allowance(db: Session, order: ServiceOrder, org: Organisation) -> None:
        config = SurveyLaunchEligibilityService._order_config(order)
        channel = PlatformCatalogService.resolve_survey_channel(config)
        if channel != "whatsapp":
            return
        units = int(config.get("launch_allowance_units") or 0)
        if units <= 0 and str(order.payment_method or "") == "subscription_whatsapp":
            units = SurveyLaunchEligibilityService.estimated_whatsapp_units(order, channel=channel)
        if units > 0:
            UsageWalletService.record_whatsapp_usage(db, org_id=org.id, units=units, commit=True)
            logger.info(
                "survey_launch_whatsapp_usage order_id=%s org_id=%s units=%s",
                order.id,
                org.id,
                units,
            )

    @staticmethod
    def assert_can_launch(db: Session, order: ServiceOrder, org: Organisation) -> dict[str, Any]:
        eligibility = SurveyLaunchEligibilityService.compute(db, order, org)
        if order.payment_status != "approved" and not eligibility.get("can_launch"):
            raise SurveyLaunchEligibilityError(
                str(eligibility.get("block_reason") or eligibility.get("summary") or "Cannot launch this survey")
            )
        return eligibility
