import { Link } from "@tanstack/react-router";
import { Sparkles, Smile } from "lucide-react";
import * as React from "react";

import { AllowanceProductPanel } from "@/components/billing/allowance-product-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import type { AllowanceRow, ProductPanelMeta } from "@/lib/billing/allowances";
import type { SubscriptionFinanceSummary } from "@/components/billing/subscription-summary-bar";
import { cn } from "@/lib/utils";

type Props = {
  meta: ProductPanelMeta;
  finance?: SubscriptionFinanceSummary | null;
  allowanceRows: AllowanceRow[];
  planLabel?: string;
  billingInterval?: string | null;
  isPayg?: boolean;
  walletDisplay?: string;
  sharedPool?: boolean;
  badges?: Array<{ label: string; variant?: "default" | "secondary" | "outline" }>;
  onTopUp?: () => void;
  compact?: boolean;
};

function formatSubDate(raw: unknown) {
  if (!raw) return "";
  const d = new Date(String(raw));
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
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
}: Props) {
  const Icon = meta.product === "feedback" ? Smile : Sparkles;
  const planName = planLabel || finance?.plan_name || finance?.plan_code || (isPayg ? "Pay as you go" : "—");
  const interval =
    billingInterval === "yearly" ? "Yearly" : billingInterval === "monthly" ? "Monthly" : finance?.billing_interval === "yearly" ? "Yearly" : finance?.billing_interval === "monthly" ? "Monthly" : null;
  const nextDate = finance?.cancel_at_period_end
    ? formatSubDate(finance.current_period_end || finance.next_billing_date)
    : formatSubDate(finance?.next_billing_date || finance?.current_period_end);
  const nextAmount = finance?.amount_next_payment_display || "—";

  return (
    <Card className={cn("overflow-hidden ring-1", meta.tintClass, meta.ringClass)}>
      <CardHeader className="space-y-3 pb-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className={cn("grid size-10 place-items-center rounded-xl bg-background shadow-sm", meta.product === "feedback" ? "text-success" : "text-primary")}>
              <Icon className="size-5" />
            </div>
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{meta.title}</p>
              <p className="text-lg font-semibold">{planName}{interval ? ` · ${interval}` : ""}</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-1">
            {badges.map((b) => (
              <Badge key={b.label} variant={b.variant || "secondary"} className="text-[10px]">
                {b.label}
              </Badge>
            ))}
          </div>
        </div>
        {isPayg ? (
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
        ) : finance?.plan_name || finance?.plan_code ? (
          <div className="space-y-1 text-sm text-muted-foreground">
            <p>
              Next payment: <strong className="text-foreground">{nextAmount}</strong>
              {nextDate ? <> · {nextDate}</> : null}
              {finance.cancel_at_period_end ? " · Cancels at period end" : null}
            </p>
            <Button asChild size="sm" variant="link" className="h-auto p-0">
              <Link to={meta.packagesLink} search={meta.packagesSearch}>
                Change plan
              </Link>
            </Button>
          </div>
        ) : null}
      </CardHeader>
      <CardContent className="pt-0">
        <AllowanceProductPanel
          meta={meta}
          rows={allowanceRows}
          sharedPool={sharedPool}
          compact={compact}
        />
      </CardContent>
    </Card>
  );
}
