"""Survey launch entitlement checks — shared by API, UI, and start/schedule validation."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder
from app.services.org_service_credit_service import OrgServiceCreditError, OrgServiceCreditService
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_billing_context import org_survey_billing_context
from app.services.usage_wallet_service import UsageWalletService
from app.services.voxbulk_pricing_service import VoxbulkPricingService

logger = logging.getLogger(__name__)

_LAUNCH_ELIGIBILITY_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_LAUNCH_ELIGIBILITY_CACHE_TTL_SEC = 5.0


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
    def _wa_launch_quote(
        db: Session,
        *,
        org_id: str,
        recipient_count: int,
        wa_remaining: int,
        has_subscription_package: bool,
    ) -> dict[str, Any]:
        rates = VoxbulkPricingService.resolve_rates_for_org(db, org_id)
        quote = VoxbulkPricingService.quote_wa_survey_launch(
            recipient_count=recipient_count,
            wa_remaining=wa_remaining,
            wa_survey_extra_pence=int(rates["wa_survey_extra_pence"]),
            has_subscription=has_subscription_package,
        )
        quote["wa_survey_extra_display"] = VoxbulkPricingService.money_display(int(rates["wa_survey_extra_pence"]))
        return quote

    @staticmethod
    def _phone_launch_quote(
        db: Session,
        *,
        org_id: str,
        recipient_count: int,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        duration = config.get("estimated_duration_min") or config.get("duration_min")
        return VoxbulkPricingService.quote_phone_survey_launch(
            db,
            org_id=org_id,
            recipient_count=recipient_count,
            duration_min=int(duration) if duration else None,
        )

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

        usage = UsageWalletService.get_current(db, org.id)
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
            "covered_recipients": 0,
            "extra_recipients": 0,
            "covered_by_promo_credits": 0,
            "shortfall_units": 0,
            "wa_survey_extra_pence": None,
            "wa_survey_extra_display": None,
            "extra_cost_pence": 0,
            "extra_cost_display": None,
            "amount_due_pence": 0,
            "amount_due_display": None,
            "quote_total_pence": int(order.quote_total_pence or 0),
            "quote_total_display": None,
            "remaining_whatsapp_after_launch": billing["whatsapp_remaining"],
            "remaining_promo_credits_after_launch": billing["survey_credits"],
            "package_label": billing.get("plan_name"),
            "launch_action": "blocked",
            "pricing_source": None,
        }

        if recipient_count <= 0:
            return SurveyLaunchEligibilityService._set_block(
                base,
                code="no_recipients",
                reason="Upload at least one contact before launch.",
                summary="No recipients on this survey yet.",
            )

        if channel == "ai_call":
            setup_error = SurveyLaunchEligibilityService._phone_survey_setup_error(db, order, config)
            if setup_error:
                return SurveyLaunchEligibilityService._set_block(
                    base,
                    code="phone_survey_setup_incomplete",
                    reason=setup_error,
                    summary=setup_error,
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

        if channel == "whatsapp":
            return SurveyLaunchEligibilityService._compute_whatsapp(
                db, order, org, base, billing, recipient_count, estimated_usage, wa_remaining
            )

        return SurveyLaunchEligibilityService._compute_phone(
            db, order, org, base, billing, recipient_count, config
        )

    @staticmethod
    def _phone_survey_setup_error(db: Session, order: ServiceOrder, config: dict[str, Any]) -> str | None:
        if not config.get("script_approved") and not str(config.get("approved_script") or "").strip():
            return "Approve your survey script before launch."
        if not order.scheduled_start_at or not order.scheduled_end_at:
            return "Set calling start and end date/time before launch."
        try:
            if order.scheduled_end_at <= order.scheduled_start_at:
                return "Calling end must be after calling start."
        except TypeError:
            return "Set a valid calling window before launch."
        from app.services.survey_voice_agent_service import resolve_survey_agent_for_order

        agent = resolve_survey_agent_for_order(db, order, config)
        if agent is None or not str(agent.telnyx_assistant_id or "").strip():
            return "Select a survey voice agent with a Telnyx assistant configured."
        return None

    @staticmethod
    def _compute_whatsapp(
        db: Session,
        order: ServiceOrder,
        org: Organisation,
        base: dict[str, Any],
        billing: dict[str, Any],
        recipient_count: int,
        estimated_usage: int,
        wa_remaining: int,
    ) -> dict[str, Any]:
        can_invoice = bool(billing.get("can_launch_and_invoice"))
        quote = SurveyLaunchEligibilityService._wa_launch_quote(
            db,
            org_id=org.id,
            recipient_count=recipient_count,
            wa_remaining=wa_remaining,
            has_subscription_package=can_invoice,
        )
        covered = int(quote.get("covered_recipients") or 0)
        extra = int(quote.get("extra_recipients") or 0)
        extra_pence = int(quote.get("extra_cost_pence") or 0)
        payg_total = int(quote.get("total_pence") or 0)
        extra_display = str(quote.get("extra_cost_display") or VoxbulkPricingService.money_display(extra_pence))
        extra_rate_display = str(quote.get("wa_survey_extra_display") or "")

        base.update(
            {
                "covered_by_allowance": covered,
                "covered_recipients": covered,
                "extra_recipients": extra,
                "shortfall_units": extra,
                "wa_survey_extra_pence": quote.get("wa_survey_extra_pence"),
                "wa_survey_extra_display": extra_rate_display,
                "extra_cost_pence": extra_pence,
                "extra_cost_display": extra_display,
                "pricing_source": quote.get("pricing_source"),
                "remaining_whatsapp_after_launch": max(0, wa_remaining - covered),
            }
        )

        if can_invoice and wa_remaining >= estimated_usage > 0:
            base.update(
                {
                    "can_launch": True,
                    "payment_required": False,
                    "mode": "subscription_whatsapp",
                    "launch_action": "launch",
                    "amount_due_pence": 0,
                    "amount_due_display": "£0.00",
                    "summary": (
                        f"Plan includes: {billing.get('whatsapp_included', 0)} WA survey recipients/month. "
                        f"This launch uses {recipient_count} recipient{'s' if recipient_count != 1 else ''} "
                        f"({wa_remaining} remaining after launch)."
                    ),
                }
            )
            logger.info(
                "survey_launch_billing_done order_id=%s success=true launch_action=launch mode=subscription_whatsapp",
                order.id,
            )
            return base

        if can_invoice:
            extra_rate = extra_rate_display or VoxbulkPricingService.money_display(int(quote.get("wa_survey_extra_pence") or 49))
            if extra > 0:
                summary = (
                    f"Plan includes: {billing.get('whatsapp_included', 0)} WA survey recipients/month. "
                    f"This launch: {covered} included, {extra} extra. "
                    f"Extra recipients: {extra_rate} each after allowance is used "
                    f"({extra_display} invoiced on your next bill)."
                )
            else:
                summary = (
                    f"Plan includes: {billing.get('whatsapp_included', 0)} WA survey recipients/month. "
                    "Interview WhatsApp: included."
                )
            base.update(
                {
                    "can_launch": True,
                    "payment_required": False,
                    "mode": "subscription_overage" if extra > 0 else "subscription_whatsapp",
                    "launch_action": "launch",
                    "amount_due_pence": extra_pence,
                    "amount_due_display": extra_display if extra > 0 else "£0.00",
                    "summary": summary,
                }
            )
            logger.info(
                "survey_launch_billing_done order_id=%s success=true launch_action=launch mode=%s extra=%s",
                order.id,
                base["mode"],
                extra,
            )
            return base

        amount_display = str(quote.get("total_gbp") or VoxbulkPricingService.money_display(payg_total))
        summary = (
            f"Extra recipients: {extra_rate_display or '£0.49'} each after allowance is used. "
            f"Pay & launch: {recipient_count} recipient{'s' if recipient_count != 1 else ''} × "
            f"{extra_rate_display or '£0.49'} = {amount_display}."
        )
        base.update(
            {
                "can_launch": False,
                "payment_required": True,
                "mode": "payg",
                "launch_action": "pay_and_launch",
                "amount_due_pence": payg_total,
                "amount_due_display": amount_display,
                "quote_total_pence": payg_total,
                "quote_total_display": amount_display,
                "summary": summary,
            }
        )
        logger.info(
            "survey_launch_billing_done order_id=%s success=false launch_action=pay_and_launch mode=payg amount_due=%s",
            order.id,
            payg_total,
        )
        return base

    @staticmethod
    def _compute_phone(
        db: Session,
        order: ServiceOrder,
        org: Organisation,
        base: dict[str, Any],
        billing: dict[str, Any],
        recipient_count: int,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        quote = SurveyLaunchEligibilityService._phone_launch_quote(
            db,
            org_id=org.id,
            recipient_count=recipient_count,
            config=config,
        )
        total = int(quote.get("total_pence") or 0)
        amount_display = str(quote.get("total_gbp") or VoxbulkPricingService.money_display(total))
        per_call_display = str(quote.get("per_call_display") or "")
        duration_min = int(quote.get("duration_minutes") or 1)
        estimated_minutes = max(1, duration_min * recipient_count)
        calls_remaining = int(billing.get("calls_remaining") or 0)
        calls_included = int(billing.get("calls_included") or 0)
        can_invoice = bool(billing.get("can_launch_and_invoice"))
        covered_minutes = min(calls_remaining, estimated_minutes) if can_invoice and calls_included > 0 else 0
        extra_minutes = max(0, estimated_minutes - covered_minutes)
        remaining_after = max(0, calls_remaining - covered_minutes)

        base.update(
            {
                "estimated_call_minutes": estimated_minutes,
                "covered_call_minutes": covered_minutes,
                "extra_call_minutes": extra_minutes,
                "remaining_call_minutes_after_launch": remaining_after,
                "pricing_source": quote.get("pricing_source"),
            }
        )

        if can_invoice and calls_included > 0 and extra_minutes <= 0:
            base.update(
                {
                    "can_launch": True,
                    "payment_required": False,
                    "mode": "subscription_phone_included",
                    "launch_action": "launch",
                    "amount_due_pence": 0,
                    "amount_due_display": "£0.00",
                    "summary": (
                        f"Plan includes {calls_included} call minutes/month. "
                        f"This launch uses {estimated_minutes} minute{'s' if estimated_minutes != 1 else ''} "
                        f"({remaining_after} remaining after launch)."
                    ),
                }
            )
            return base

        if can_invoice and calls_included > 0 and extra_minutes > 0:
            base.update(
                {
                    "can_launch": True,
                    "payment_required": False,
                    "mode": "subscription_phone_overage",
                    "launch_action": "launch",
                    "amount_due_pence": total,
                    "amount_due_display": amount_display,
                    "summary": (
                        f"Plan includes {calls_included} call minutes/month. "
                        f"This launch: {covered_minutes} included, {extra_minutes} extra minute{'s' if extra_minutes != 1 else ''} "
                        f"({amount_display} invoiced on your next bill)."
                    ),
                }
            )
            return base

        if can_invoice and total <= 0:
            base.update(
                {
                    "can_launch": True,
                    "payment_required": False,
                    "mode": "subscription_phone",
                    "launch_action": "launch",
                    "amount_due_pence": 0,
                    "amount_due_display": "£0.00",
                    "summary": (
                        f"AI phone survey: billed by connection + minutes "
                        f"({per_call_display}/call × {recipient_count})."
                    ),
                }
            )
            return base

        if can_invoice:
            base.update(
                {
                    "can_launch": True,
                    "payment_required": False,
                    "mode": "subscription_phone",
                    "launch_action": "launch",
                    "amount_due_pence": total,
                    "amount_due_display": amount_display,
                    "summary": (
                        f"AI phone survey: billed by connection + minutes "
                        f"({per_call_display}/call × {recipient_count} = {amount_display} on your next bill)."
                    ),
                }
            )
            return base

        base.update(
            {
                "can_launch": False,
                "payment_required": True,
                "mode": "payg",
                "launch_action": "pay_and_launch",
                "amount_due_pence": total,
                "amount_due_display": amount_display,
                "quote_total_pence": total,
                "quote_total_display": amount_display,
                "summary": (
                    f"AI phone survey: pay as you go — {amount_display} "
                    f"({per_call_display}/call × {recipient_count})."
                ),
            }
        )
        return base

    @staticmethod
    def compute_cached(
        db: Session,
        order: ServiceOrder,
        org: Organisation,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        """Return eligibility with short TTL cache to absorb duplicate frontend polls."""
        cache_key = (
            f"{order.id}:{org.id}:{int(order.recipient_count or 0)}:"
            f"{int(order.updated_at.timestamp()) if order.updated_at else 0}"
        )
        now = time.time()
        if not force:
            cached = _LAUNCH_ELIGIBILITY_CACHE.get(cache_key)
            if cached and cached[0] > now:
                logger.info(
                    "survey_launch_eligibility_cache_hit order_id=%s org_id=%s",
                    order.id,
                    org.id,
                )
                return dict(cached[1])

        result = SurveyLaunchEligibilityService.compute(db, order, org)
        _LAUNCH_ELIGIBILITY_CACHE[cache_key] = (now + _LAUNCH_ELIGIBILITY_CACHE_TTL_SEC, dict(result))
        return result

    @staticmethod
    def prepare_order_payment_quote(db: Session, order: ServiceOrder, org: Organisation) -> ServiceOrder:
        """Align order quote with payable PAYG amount before GoCardless."""
        eligibility = SurveyLaunchEligibilityService.compute(db, order, org)
        if not eligibility.get("payment_required"):
            return order
        amount_pence = int(eligibility.get("amount_due_pence") or 0)
        if amount_pence <= 0:
            raise SurveyLaunchEligibilityError("Nothing to pay for this launch")

        config = SurveyLaunchEligibilityService._order_config(order)
        channel = PlatformCatalogService.resolve_survey_channel(config)
        if channel == "whatsapp":
            quote = SurveyLaunchEligibilityService._wa_launch_quote(
                db,
                org_id=org.id,
                recipient_count=max(0, int(order.recipient_count or 0)),
                wa_remaining=0,
                has_subscription_package=False,
            )
        else:
            quote = SurveyLaunchEligibilityService._phone_launch_quote(
                db,
                org_id=org.id,
                recipient_count=max(0, int(order.recipient_count or 0)),
                config=config,
            )

        order.quote_total_pence = int(quote.get("total_pence") or amount_pence)
        order.quote_breakdown_json = json.dumps(quote, ensure_ascii=False)
        order.status = "quoted"
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

        if mode in {
            "subscription_whatsapp",
            "subscription_overage",
            "subscription_phone",
            "subscription_phone_included",
            "subscription_phone_overage",
        }:
            from datetime import datetime

            plan_name = str(eligibility.get("package_label") or "package").strip() or "package"
            config = SurveyLaunchEligibilityService._order_config(order)
            config["launch_allowance_units"] = SurveyLaunchEligibilityService.estimated_whatsapp_units(
                order,
                channel=PlatformCatalogService.resolve_survey_channel(config),
            )
            order.config_json = json.dumps(config, ensure_ascii=False)
            order.payment_method = "subscription_whatsapp" if "whatsapp" in mode else "subscription"
            order.payment_status = "approved"
            order.status = "paid"
            extra = int(eligibility.get("extra_recipients") or 0)
            covered = int(eligibility.get("covered_recipients") or eligibility.get("covered_by_allowance") or 0)
            if extra > 0:
                order.payment_note = (
                    f"Covered by {plan_name} ({covered} recipients); "
                    f"{extra} extra invoiced at launch"
                )
            else:
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
        if units <= 0:
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
