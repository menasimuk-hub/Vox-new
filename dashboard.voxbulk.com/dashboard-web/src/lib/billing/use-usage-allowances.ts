import * as React from "react";

import type { AllowanceAlert, AllowanceRow, BillingSnapshot } from "@/lib/billing/allowances";
import {
  corePanelKeys,
  groupAllowancesByProduct,
  pickAllowances,
  PRODUCT_PANEL_META,
} from "@/lib/billing/allowances";
import type { SubscriptionFinanceSummary } from "@/components/billing/subscription-summary-bar";
import { useBillingSubscriptionsSummary, useBillingUsage, useFeedbackSubscription } from "@/lib/queries";
import type { UsageSummary } from "@/lib/types/api";

export function useUsageAllowances() {
  const usageQ = useBillingUsage();
  const feedbackSubQ = useFeedbackSubscription();
  const subsSummaryQ = useBillingSubscriptionsSummary();

  const data = usageQ.data;
  const allowances = (data?.allowances || []) as AllowanceRow[];
  const allowanceAlerts = (data?.allowance_alerts || []) as AllowanceAlert[];
  const snapshot = (data?.billing_snapshot || {}) as BillingSnapshot;
  const sharedPool = Boolean(snapshot.shared_package_pool ?? data?.billing_monitor?.shared_package_pool);

  const grouped = React.useMemo(() => groupAllowancesByProduct(allowances), [allowances]);

  const coreRows = React.useMemo(
    () => pickAllowances(grouped.core, corePanelKeys(sharedPool)),
    [grouped.core, sharedPool],
  );

  const feedbackRows = React.useMemo(
    () => pickAllowances(grouped.feedback, ["feedback_wa", "feedback_web"] as const),
    [grouped.feedback],
  );

  const coreFinance = (subsSummaryQ.data?.core || null) as SubscriptionFinanceSummary | null;
  const feedbackFinance = (subsSummaryQ.data?.feedback || null) as SubscriptionFinanceSummary | null;
  const feedbackSub = feedbackSubQ.data;

  const hasCoreSub = Boolean(
    snapshot.has_core_subscription ||
      coreFinance?.plan_name ||
      (data?.current_plan && !snapshot.is_payg),
  );
  const hasFeedbackSub = Boolean(
    feedbackSub?.active ||
      feedbackFinance?.plan_name ||
      feedbackRows.length > 0,
  );
  const isPayg = Boolean(snapshot.is_payg && !snapshot.has_core_subscription);

  const periodLabel = React.useMemo(() => {
    const start = data?.period_start;
    const end = data?.period_end;
    if (!start && !end) return "";
    const fmt = (raw: string) => {
      const d = new Date(raw);
      return Number.isNaN(d.getTime())
        ? raw
        : d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
    };
    if (start && end) return `${fmt(start)} – ${fmt(end)}`;
    return end ? fmt(end) : "";
  }, [data?.period_start, data?.period_end]);

  const commercial = (data?.billing_monitor as { commercial?: Record<string, unknown> } | undefined)?.commercial;

  return {
    loading: usageQ.isLoading || feedbackSubQ.isLoading || subsSummaryQ.isLoading,
    usage: data as UsageSummary | undefined,
    allowances,
    allowanceAlerts,
    snapshot,
    sharedPool,
    coreRows,
    feedbackRows,
    coreFinance,
    feedbackFinance,
    feedbackSub,
    hasCoreSub,
    hasFeedbackSub,
    isPayg,
    periodLabel,
    coreMeta: PRODUCT_PANEL_META.core,
    feedbackMeta: PRODUCT_PANEL_META.feedback,
    walletDisplay: snapshot.wallet_balance_display || data?.wallet_balance_gbp,
    valuePool: snapshot.value_pool_active
      ? {
          active: true,
          usedDisplay: snapshot.package_used_display || commercial?.package_used_display,
          includedDisplay: snapshot.package_included_display || commercial?.package_included_display,
          remainingDisplay: snapshot.package_remaining_display || commercial?.package_remaining_display,
          percent: Number(commercial?.package_included_pence)
            ? Math.round(
                (Number(commercial?.package_used_pence || 0) / Number(commercial?.package_included_pence || 1)) * 100,
              )
            : undefined,
        }
      : undefined,
  };
}
