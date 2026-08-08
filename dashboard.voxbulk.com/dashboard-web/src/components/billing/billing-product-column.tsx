import { Link } from "@tanstack/react-router";
import { Sparkles, Smile, QrCode } from "lucide-react";
import * as React from "react";

import { AllowanceProductPanel } from "@/components/billing/allowance-product-panel";
import { PackageValuePoolBar } from "@/components/billing/package-value-pool-bar";
import { ProductCancellationActions } from "@/components/billing/subscription-cancellation-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import type { AllowanceRow, ProductPanelMeta } from "@/lib/billing/allowances";
import type { SubscriptionFinanceSummary } from "@/components/billing/subscription-summary-bar";
import { cn } from "@/lib/utils";

type Props = {
  meta: ProductPanelMeta;
  finance?: (SubscriptionFinanceSummary & { seat_quantity?: number | null; is_payg?: boolean; access_until?: string | null }) | null;
  allowanceRows: AllowanceRow[];
  planLabel?: string;
  billingInterval?: string | null;
  isPayg?: boolean;
  walletDisplay?: string;
  sharedPool?: boolean;
  badges?: Array<{ label: string; variant?: "default" | "secondary" | "outline" }>;
  onTopUp?: () => void;
  compact?: boolean;
  footerNote?: React.ReactNode;
  usedOnlyKpis?: boolean;
  valuePool?: {
    active?: boolean;
    usedDisplay?: string;
    includedDisplay?: string;
    remainingDisplay?: string;
    percent?: number;
  };
  /** Show cancel-at-period-end controls for this product card. */
  showCancel?: boolean;
  /** Core only: org-level overage billing for WA Survey + AI Interview. */
  allowOverage?: boolean;
  overageBusy?: boolean;
  onAllowOverageChange?: (checked: boolean) => void;
};

function formatSubDate(raw: unknown) {
  if (!raw) return "";
  const d = new Date(String(raw));
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function cancelServiceForProduct(product: string): "voxbulk" | "feedback" | "smart_card" {
  if (product === "feedback") return "feedback";
  if (product === "smart_card") return "smart_card";
  return "voxbulk";
}

export function BillingProductColumn({
  meta,
  finance,
  allowanceRows,
  planLabel,
  billingInterval,
  isPayg,
  walletDisplay,
  sharedPool,
  badges = [],
  onTopUp,
  compact,
  footerNote,
  usedOnlyKpis,
  valuePool,
  showCancel = true,
  allowOverage,
  overageBusy,
  onAllowOverageChange,
}: Props) {
  const Icon = meta.product === "feedback" ? Smile : meta.product === "smart_card" ? QrCode : Sparkles;
  const iconTint =
    meta.product === "feedback"
      ? "text-emerald-600"
      : meta.product === "smart_card"
        ? "text-violet-600"
        : "text-sky-600";
  const planName =
    planLabel ||
    finance?.plan_name ||
    finance?.plan_code ||
    (isPayg || finance?.is_payg ? "Pay as you go" : "—");
  const interval =
    billingInterval === "yearly"
      ? "Yearly"
      : billingInterval === "monthly"
        ? "Monthly"
        : finance?.billing_interval === "yearly"
          ? "Yearly"
          : finance?.billing_interval === "monthly"
            ? "Monthly"
            : null;
  const cancelScheduled = Boolean(finance?.cancel_at_period_end);
  const accessUntil = cancelScheduled
    ? formatSubDate(finance?.access_until || finance?.current_period_end)
    : "";
  const nextDate = cancelScheduled
    ? ""
    : formatSubDate(finance?.next_billing_date || finance?.current_period_end);
  const nextAmount =
    finance?.amount_next_payment_display || (isPayg || finance?.is_payg ? "Pay as you go" : "—");
  const seats = finance?.seat_quantity != null && finance.seat_quantity > 0 ? finance.seat_quantity : null;
  const hasPlan = Boolean(finance?.plan_name || finance?.plan_code || isPayg || finance?.is_payg || planLabel);
  const cancelEnabled = showCancel && hasPlan && !(isPayg || finance?.is_payg);

  return (
    <Card className={cn("overflow-hidden ring-1", meta.tintClass, meta.ringClass)}>
      <CardHeader className="space-y-3 pb-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="flex items-center gap-3">
            <div className={cn("grid size-14 place-items-center rounded-2xl bg-background shadow-sm", iconTint)}>
              <Icon className="size-7" strokeWidth={1.75} />
            </div>
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{meta.title}</p>
              <p className="text-lg font-semibold">
                {planName}
                {interval ? ` · ${interval}` : ""}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-1">
            {badges.map((b) => (
              <Badge key={b.label} variant={b.variant || "secondary"} className="text-[10px]">
                {b.label}
              </Badge>
            ))}
            {cancelScheduled ? (
              <Badge variant="secondary" className="text-[10px]">
                Cancels at period end
              </Badge>
            ) : null}
            {seats != null ? (
              <Badge variant="outline" className="text-[10px]">
                {seats} seat{seats === 1 ? "" : "s"}
              </Badge>
            ) : null}
          </div>
        </div>
        {isPayg || finance?.is_payg ? (
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <span className="text-muted-foreground">
              Wallet: <strong className="text-foreground">{walletDisplay || "—"}</strong>
            </span>
            {onTopUp ? (
              <Button size="sm" variant="outline" onClick={onTopUp}>
                Top up
              </Button>
            ) : (
              <Button asChild size="sm" variant="outline">
                <Link to="/account/packages">Top up wallet</Link>
              </Button>
            )}
          </div>
        ) : hasPlan ? (
          <div className="space-y-1 text-sm text-muted-foreground">
            {cancelScheduled ? (
              <p>
                No next payment
                {accessUntil ? (
                  <>
                    {" "}
                    · Access until <strong className="text-foreground">{accessUntil}</strong>
                  </>
                ) : null}
              </p>
            ) : (
              <p>
                Next payment: <strong className="text-foreground">{nextAmount}</strong>
                {nextDate ? <> · {nextDate}</> : null}
              </p>
            )}
            <div className="flex flex-wrap items-center gap-3">
              <Button asChild size="sm" variant="link" className="h-auto p-0">
                <Link to={meta.packagesLink} search={meta.packagesSearch}>
                  Change plan
                </Link>
              </Button>
            </div>
            <ProductCancellationActions
              planName={typeof planName === "string" ? planName : null}
              service={cancelServiceForProduct(meta.product)}
              enabled={cancelEnabled}
            />
          </div>
        ) : (
          <div className="space-y-1 text-sm text-muted-foreground">
            <p>No active subscription</p>
            <Button asChild size="sm" variant="link" className="h-auto p-0">
              <Link to={meta.packagesLink} search={meta.packagesSearch}>
                View packages →
              </Link>
            </Button>
          </div>
        )}
      </CardHeader>
      <CardContent className="pt-0">
        {valuePool?.active && valuePool.usedDisplay && valuePool.includedDisplay ? (
          <PackageValuePoolBar
            usedDisplay={valuePool.usedDisplay}
            includedDisplay={valuePool.includedDisplay}
            remainingDisplay={valuePool.remainingDisplay}
            percent={valuePool.percent}
            className="mb-3"
          />
        ) : null}
        {allowanceRows.length > 0 ? (
          <AllowanceProductPanel
            meta={meta}
            rows={allowanceRows}
            sharedPool={sharedPool}
            compact={compact}
            hideFooter
            usedOnlyKpis={usedOnlyKpis}
          />
        ) : null}
        {meta.product === "core" && onAllowOverageChange ? (
          <div className="mt-3 flex items-start justify-between gap-3 border-t border-border/60 pt-3">
            <div className="min-w-0">
              <p className="text-sm font-medium">Allow extra usage billing</p>
              <p className="text-xs text-muted-foreground">
                When off, WA Survey and AI Interview stop at plan limits instead of Direct Debit overage.
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Switch
                id={`allow-overage-${meta.product}`}
                checked={Boolean(allowOverage)}
                disabled={Boolean(overageBusy)}
                onCheckedChange={onAllowOverageChange}
              />
              <Label htmlFor={`allow-overage-${meta.product}`} className="text-xs text-muted-foreground">
                {allowOverage ? "On" : "Off"}
              </Label>
            </div>
          </div>
        ) : null}
        {footerNote ? <div className="mt-3 border-t border-border/60 pt-3">{footerNote}</div> : null}
      </CardContent>
    </Card>
  );
}
