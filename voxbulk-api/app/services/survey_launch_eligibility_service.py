"""Survey launch entitlement checks — shared by API, UI, and start/schedule validation.

Billing model:
- Promo credits cover a launch entirely when sufficient.
- Subscription customers: plan allowance first; extras collected by GoCardless Direct Debit.
- PAYG customers: wallet balance only (top up via Stripe/Airwallex); launch blocks when short.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder
from app.services.billing_access_service import BillingAccessService
from app.services.billing_currency import money_display, resolve_org_currency
from app.services.launch_billing_service import LaunchBillingError, LaunchBillingService
from app.services.org_service_credit_service import OrgServiceCreditError, OrgServiceCreditService
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_billing_context import org_survey_billing_context
from app.services.usage_wallet_service import UsageWalletService

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
        billable_recipient_count = recipient_count
        estimated_usage = SurveyLaunchEligibilityService.estimated_whatsapp_units(order, channel=channel)
        billing = org_survey_billing_context(db, org)
        currency = resolve_org_currency(db, org)

        base: dict[str, Any] = {
            "order_id": order.id,
            "campaign_name": order.title,
            "survey_channel": channel,
            "recipient_count": recipient_count,
            "estimated_whatsapp_usage": estimated_usage,
            "payment_status": order.payment_status,
            "order_status": order.status,
            "billing": billing,
            "currency": currency,
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
            "wallet_balance_minor": 0,
            "wallet_balance_display": None,
            "wallet_charge_minor": 0,
            "dd_charge_minor": 0,
            "wallet_shortfall_minor": 0,
        }

        if channel == "ai_call":
            from app.services.telnyx_phone_allowlist_service import TelnyxPhoneAllowlistService

            allowlist_stats = TelnyxPhoneAllowlistService.dialable_recipient_counts(db, order)
            base["phone_allowlist"] = allowlist_stats
            billable_recipient_count = max(0, int(allowlist_stats.get("dialable") or 0))
            blocked = max(0, int(allowlist_stats.get("blocked") or 0))
            if billable_recipient_count <= 0 and int(allowlist_stats.get("total") or 0) > 0:
                return SurveyLaunchEligibilityService._set_block(
                    base,
                    code="phone_allowlist_blocked",
                    reason="None of your contacts match the AI call allowlist. Update phone numbers to allowed prefixes or remove blocked rows.",
                    summary="No dialable contacts — fix allowlist numbers before launch.",
                )
            if blocked > 0:
                base["phone_allowlist_warning"] = (
                    f"{blocked} number{'s' if blocked != 1 else ''} will not be called — not on the Telnyx allowlist."
                )

        from app.services.billing_access_service import BillingAccessService

        payg_wallet_launch = not bool(billing.get("can_launch_and_invoice"))
        if not payg_wallet_launch:
            sub = BillingAccessService.get_subscription(db, org.id)
            if sub is not None:
                from app.services.subscription_cancellation_service import (
                    CANCELLATION_CANCELLED,
                    SubscriptionCancellationService,
                )

                cancel_status = str(sub.cancellation_status or "none").strip().lower()
                if (
                    cancel_status == CANCELLATION_CANCELLED
                    or SubscriptionCancellationService.effective_status(sub) == "cancelled"
                ):
                    payg_wallet_launch = True

        access_block = BillingAccessService.launch_block_reason(
            db,
            org,
            payg_wallet_launch=payg_wallet_launch,
        )
        if access_block:
            return SurveyLaunchEligibilityService._set_block(
                base,
                code="billing_access_blocked",
                reason=access_block,
                summary=access_block,
            )

        if recipient_count <= 0:
            return SurveyLaunchEligibilityService._set_block(
                base,
                code="no_recipients",
                reason="Upload at least one contact before launch.",
                summary="No recipients on this survey yet.",
            )

        if channel == "ai_call" and billable_recipient_count <= 0:
            return SurveyLaunchEligibilityService._set_block(
                base,
                code="phone_allowlist_blocked",
                reason="No contacts on the AI call allowlist.",
                summary="No dialable contacts.",
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
                db, order, org, base, billing, recipient_count, wa_remaining
            )

        return SurveyLaunchEligibilityService._compute_phone(
            db, order, org, base, billing, billable_recipient_count, config
        )

    @staticmethod
    def _phone_survey_setup_error(db: Session, order: ServiceOrder, config: dict[str, Any]) -> str | None:
        from app.services.script_moderation_service import script_moderation_blocks_launch

        moderation_block = script_moderation_blocks_launch(config)
        if moderation_block:
            return moderation_block
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
    def _apply_estimate(base: dict[str, Any], est: dict[str, Any]) -> dict[str, Any]:
        """Map a LaunchBillingService estimate onto the eligibility payload."""
        currency = str(est.get("currency") or "GBP")
        total = int(est.get("total_minor") or 0)
        base.update(
            {
                "currency": currency,
                "pricing_source": "voxbulk_plan_prices",
                "amount_due_pence": total,
                "amount_due_display": est.get("total_display"),
                "estimated_cost_minor": int(est.get("estimated_cost_minor") or total),
                "estimated_cost_display": est.get("estimated_cost_display") or est.get("total_display"),
                "required_wallet_minor": int(est.get("required_wallet_minor") or est.get("wallet_charge_minor") or 0),
                "required_wallet_display": est.get("required_wallet_display"),
                "wallet_buffer_percent": int(est.get("wallet_buffer_percent") or 100),
                "top_up_minor": int(est.get("top_up_minor") or est.get("wallet_shortfall_minor") or 0),
                "top_up_display": est.get("top_up_display"),
                "extra_cost_pence": total,
                "extra_cost_display": est.get("total_display"),
                "quote_total_pence": total,
                "quote_total_display": est.get("total_display"),
                "wallet_balance_minor": int(est.get("wallet_balance_minor") or 0),
                "wallet_balance_display": est.get("wallet_balance_display"),
                "wallet_charge_minor": int(est.get("wallet_charge_minor") or 0),
                "dd_charge_minor": int(est.get("dd_charge_minor") or 0),
                "wallet_shortfall_minor": int(est.get("wallet_shortfall_minor") or 0),
                "launch_billing": est,
            }
        )
        return base

    @staticmethod
    def _enforce_value_pool_soft_cap(
        db: Session,
        org: Organisation,
        billing: dict[str, Any],
        est: dict[str, Any],
        base: dict[str, Any],
    ) -> dict[str, Any]:
        value_pool = billing.get("value_pool") or {}
        if not value_pool.get("value_pool_active") or not billing.get("can_launch_and_invoice"):
            return base
        from app.services.package_value_pool_service import PackageValuePoolService
        from app.services.usage_wallet_service import UsageWalletService

        row = UsageWalletService.get_current(db, org.id)
        burn = int(est.get("catalog_cost_minor") or est.get("estimated_cost_minor") or 0)
        cap = PackageValuePoolService.check_soft_cap(
            row,
            burn,
            wa_unit_minor=int(value_pool.get("wa_unit_minor") or 0),
            per_min_minor=int(value_pool.get("per_min_minor") or 0),
        )
        if not cap.get("allowed"):
            blocked = SurveyLaunchEligibilityService._set_block(
                base,
                code="package_soft_cap_exceeded",
                reason=str(cap.get("reason") or "Package allowance exceeded 110% grace."),
                summary="Blocked — upgrade your plan or top up your wallet.",
            )
            blocked["launch_action"] = "topup_required"
            return blocked
        if cap.get("in_grace"):
            base["soft_cap_grace"] = True
        return base

    @staticmethod
    def _compute_whatsapp(
        db: Session,
        order: ServiceOrder,
        org: Organisation,
        base: dict[str, Any],
        billing: dict[str, Any],
        recipient_count: int,
        wa_remaining: int,
    ) -> dict[str, Any]:
        can_invoice = bool(billing.get("can_launch_and_invoice"))
        est = LaunchBillingService.estimate_whatsapp_launch(
            db,
            org,
            recipient_count=recipient_count,
            wa_remaining=wa_remaining,
            has_subscription=can_invoice,
        )
        covered = int(est.get("units_covered_by_allowance") or 0)
        extra = int(est.get("units_billable") or 0)
        currency = str(est.get("currency") or "GBP")
        rate_display = str(est.get("unit_rate_display") or "")

        base = SurveyLaunchEligibilityService._apply_estimate(base, est)
        soft = SurveyLaunchEligibilityService._enforce_value_pool_soft_cap(db, org, billing, est, base)
        if soft.get("block_reason_code") == "package_soft_cap_exceeded":
            return soft
        base = soft
        base.update(
            {
                "covered_by_allowance": covered,
                "covered_recipients": covered,
                "extra_recipients": extra,
                "shortfall_units": extra,
                "wa_survey_extra_pence": int(est.get("unit_rate_minor") or 0),
                "wa_survey_extra_display": rate_display,
                "remaining_whatsapp_after_launch": max(0, wa_remaining - covered),
            }
        )

        method = str(est.get("payment_method") or "")
        included = int(billing.get("whatsapp_included") or 0)

        if method == "allowance":
            pkg_remaining = int(billing.get("package_remaining") or wa_remaining)
            if billing.get("shared_package_pool"):
                pkg_display = billing.get("package_remaining_display") or f"{pkg_remaining} units"
                summary_text = (
                    f"Package remaining: {pkg_display}. "
                    f"This launch uses {recipient_count} recipient{'s' if recipient_count != 1 else ''} "
                    f"({max(0, pkg_remaining - covered)} package units remaining after launch). "
                    f"Approximate capacity estimates are for guidance only."
                )
            else:
                summary_text = (
                    f"Plan includes: {included} WA survey recipients/month. "
                    f"This launch uses {recipient_count} recipient{'s' if recipient_count != 1 else ''} "
                    f"({max(0, wa_remaining - covered)} remaining after launch)."
                )
            base.update(
                {
                    "can_launch": True,
                    "payment_required": False,
                    "mode": "subscription_whatsapp" if can_invoice else "included",
                    "launch_action": "launch",
                    "amount_due_display": money_display(0, currency),
                    "summary": summary_text,
                }
            )
        elif method == "direct_debit":
            if BillingAccessService.pending_first_payment_blocks_dd(db, org.id):
                blocked = SurveyLaunchEligibilityService._set_block(
                    base,
                    code="pending_first_payment",
                    reason="Your first Direct Debit payment is still pending. Top up your wallet or wait for confirmation before launching with Direct Debit.",
                    summary="First payment pending — Direct Debit launches are blocked.",
                )
                blocked["mode"] = "pending_first_payment"
                return blocked
            base.update(
                {
                    "can_launch": True,
                    "payment_required": False,
                    "mode": "subscription_overage",
                    "launch_action": "launch",
                    "summary": (
                        f"Plan includes: {included} WA survey recipients/month. "
                        f"This launch: {covered} included, {extra} extra. "
                        f"Extra recipients: {rate_display} each — {est.get('total_display')} "
                        f"collected by Direct Debit at launch."
                    ),
                }
            )
        elif method == "wallet":
            hold = est.get("wallet_charge_display") or est.get("total_display")
            est_cost = est.get("estimated_cost_display") or est.get("total_display")
            payg_hold = int(est.get("wallet_buffer_percent") or 100) > 100
            if payg_hold:
                summary = (
                    f"Pay as you go: {extra} recipient{'s' if extra != 1 else ''} × {rate_display} "
                    f"= {est_cost}. 125% hold ({hold}) debited at launch; unused hold refunded after."
                )
            elif billing.get("shared_package_pool"):
                summary = (
                    f"Package allowance exhausted — {extra} recipient{'s' if extra != 1 else ''} × {rate_display} "
                    f"= {est.get('total_display')} charged to your wallet at launch "
                    f"({est.get('wallet_balance_display')} available)."
                )
            else:
                summary = (
                    f"Pay as you go: {extra} recipient{'s' if extra != 1 else ''} × {rate_display} "
                    f"= {est.get('total_display')} — charged to your wallet at launch "
                    f"({est.get('wallet_balance_display')} available)."
                )
            base.update(
                {
                    "can_launch": True,
                    "payment_required": False,
                    "mode": "wallet",
                    "launch_action": "launch",
                    "summary": summary,
                }
            )
        else:
            base.update({"mode": "wallet_insufficient"})
            blocked = SurveyLaunchEligibilityService._set_block(
                base,
                code="wallet_insufficient",
                reason=str(est.get("block_reason") or "Wallet balance is insufficient for this launch."),
            )
            blocked["launch_action"] = "topup_required"
            return blocked
        logger.info(
            "survey_launch_billing_done order_id=%s success=true launch_action=launch mode=%s method=%s total=%s",
            order.id, base["mode"], method, est.get("total_minor"),
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
        can_invoice = bool(billing.get("can_launch_and_invoice"))
        duration = (
            config.get("estimated_duration_min")
            or config.get("expected_duration_minutes")
            or config.get("duration_min")
        )
        try:
            duration_min = max(1, int(duration)) if duration else 12
        except (TypeError, ValueError):
            duration_min = 12
        est = LaunchBillingService.estimate_phone_launch(
            db,
            org,
            recipient_count=recipient_count,
            duration_min=duration_min,
            calls_remaining_min=int(billing.get("calls_remaining") or 0),
            has_subscription=can_invoice,
        )
        covered_minutes = int(est.get("units_covered_by_allowance") or 0)
        extra_minutes = int(est.get("units_billable") or 0)
        estimated_minutes = int(est.get("units_total") or 0)
        calls_included = int(billing.get("calls_included") or 0)
        remaining_after = max(0, int(billing.get("calls_remaining") or 0) - covered_minutes)
        per_call_display = str(est.get("per_call_display") or "")

        base = SurveyLaunchEligibilityService._apply_estimate(base, est)
        soft = SurveyLaunchEligibilityService._enforce_value_pool_soft_cap(db, org, billing, est, base)
        if soft.get("block_reason_code") == "package_soft_cap_exceeded":
            return soft
        base = soft
        base.update(
            {
                "estimated_call_minutes": estimated_minutes,
                "covered_call_minutes": covered_minutes,
                "extra_call_minutes": extra_minutes,
                "remaining_call_minutes_after_launch": remaining_after,
            }
        )

        method = str(est.get("payment_method") or "")
        if method == "allowance":
            if billing.get("shared_package_pool"):
                pkg_display = billing.get("package_remaining_display") or f"{int(billing.get('package_remaining') or 0)} units"
                summary = (
                    f"Package remaining: {pkg_display}. "
                    f"This launch uses {estimated_minutes} minute{'s' if estimated_minutes != 1 else ''} "
                    f"({remaining_after} package units remaining after launch)."
                )
            else:
                summary = (
                    f"Plan includes {calls_included} call minutes/month. "
                    f"This launch uses {estimated_minutes} minute{'s' if estimated_minutes != 1 else ''} "
                    f"({remaining_after} remaining after launch)."
                )
            base.update(
                {
                    "can_launch": True,
                    "payment_required": False,
                    "mode": "subscription_phone_included",
                    "launch_action": "launch",
                    "summary": summary,
                }
            )
        elif method == "direct_debit":
            from app.services.billing_access_service import BillingAccessService

            if BillingAccessService.pending_first_payment_blocks_dd(db, org.id):
                blocked = SurveyLaunchEligibilityService._set_block(
                    base,
                    code="pending_first_payment",
                    reason="Your first Direct Debit payment is still pending. Top up your wallet or wait for confirmation before launching with Direct Debit.",
                    summary="First payment pending — Direct Debit launches are blocked.",
                )
                blocked["mode"] = "pending_first_payment"
                return blocked
            base.update(
                {
                    "can_launch": True,
                    "payment_required": False,
                    "mode": "subscription_phone_overage",
                    "launch_action": "launch",
                    "summary": (
                        f"Plan includes {calls_included} call minutes/month. "
                        f"This launch: {covered_minutes} included, {extra_minutes} extra minute{'s' if extra_minutes != 1 else ''} "
                        f"({est.get('total_display')} collected by Direct Debit at launch)."
                    ),
                }
            )
        elif method == "wallet":
            hold = est.get("wallet_charge_display") or est.get("total_display")
            est_cost = est.get("estimated_cost_display") or est.get("total_display")
            payg_hold = int(est.get("wallet_buffer_percent") or 100) > 100
            hold_line = (
                f" Estimated {est_cost} — 125% hold ({hold}) debited at launch; unused hold refunded after."
                if payg_hold
                else f" {est.get('total_display')} charged to your wallet at launch"
            )
            base.update(
                {
                    "can_launch": True,
                    "payment_required": False,
                    "mode": "wallet",
                    "launch_action": "launch",
                    "summary": (
                        f"AI phone survey: pay as you go —{hold_line} "
                        f"({est.get('wallet_balance_display')} available)."
                    ),
                }
            )
        else:
            base.update({"mode": "wallet_insufficient"})
            blocked = SurveyLaunchEligibilityService._set_block(
                base,
                code="wallet_insufficient",
                reason=str(est.get("block_reason") or "Wallet balance is insufficient for this launch."),
            )
            blocked["launch_action"] = "topup_required"
            return blocked
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
    def approve_if_covered(db: Session, order: ServiceOrder, org: Organisation) -> ServiceOrder:
        """Charge the launch (allowance/wallet/Direct Debit) and approve the order payment."""
        if order.payment_status == "approved":
            return order

        eligibility = SurveyLaunchEligibilityService.compute(db, order, org)
        mode = str(eligibility.get("mode") or "")

        if mode == "promo_credits":
            try:
                return OrgServiceCreditService.apply_to_order(db, order, org)
            except OrgServiceCreditError as e:
                raise SurveyLaunchEligibilityError(str(e)) from e

        if mode in {"already_paid", "included"} and order.payment_status == "approved":
            return order

        breakdown = eligibility.get("launch_billing")
        if not eligibility.get("can_launch") or not isinstance(breakdown, dict):
            raise SurveyLaunchEligibilityError(
                str(eligibility.get("block_reason") or eligibility.get("summary") or "Payment required before launch")
            )

        config = SurveyLaunchEligibilityService._order_config(order)
        config["launch_allowance_units"] = SurveyLaunchEligibilityService.estimated_whatsapp_units(
            order,
            channel=PlatformCatalogService.resolve_survey_channel(config),
        )
        order.config_json = json.dumps(config, ensure_ascii=False)
        db.add(order)

        try:
            LaunchBillingService.charge_launch(db, order, org, breakdown)
        except LaunchBillingError as e:
            raise SurveyLaunchEligibilityError(str(e)) from e
        db.refresh(order)
        return order

    @staticmethod
    def consume_launch_allowance(db: Session, order: ServiceOrder, org: Organisation) -> None:
        """Reserve WA allowance at launch; actual usage is recorded once at campaign settlement."""
        config = SurveyLaunchEligibilityService._order_config(order)
        channel = PlatformCatalogService.resolve_survey_channel(config)
        if channel != "whatsapp":
            return
        units = int(config.get("launch_allowance_units") or 0)
        if units <= 0:
            units = SurveyLaunchEligibilityService.estimated_whatsapp_units(order, channel=channel)
        if units <= 0:
            return

        import json

        from app.services.campaign_billing_settlement_service import CampaignBillingSettlementService

        snapshot = CampaignBillingSettlementService._load_snapshot(order)
        deferred = str(snapshot.get("billing_phase") or "") in {"held", "pending_settlement"}
        if deferred:
            row = UsageWalletService.get_current(db, org.id)
            wa_remaining = 0
            wa_used = 0
            wa_included = 0
            if row is not None:
                wa_remaining = max(0, int(row.whatsapp_included or 0) - int(row.whatsapp_used or 0))
                wa_used = int(row.whatsapp_used or 0)
                wa_included = int(row.whatsapp_included or 0)
            snapshot["allowance_units_reserved_at_launch"] = units
            snapshot["wa_remaining_at_launch"] = wa_remaining
            snapshot["wa_used_at_launch"] = wa_used
            snapshot["wa_included_at_launch"] = wa_included
            order.launch_billing_json = json.dumps(snapshot, ensure_ascii=False)
            db.add(order)
            db.commit()
            logger.info(
                "survey_launch_whatsapp_reserved order_id=%s org_id=%s units=%s deferred=true",
                order.id,
                org.id,
                units,
            )
            return

        UsageWalletService.record_whatsapp_usage(db, org_id=org.id, units=units, commit=True)
        logger.info(
            "survey_launch_whatsapp_usage order_id=%s org_id=%s units=%s deferred=false",
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
