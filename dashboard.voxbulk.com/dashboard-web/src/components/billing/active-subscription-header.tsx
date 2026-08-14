import { CalendarClock, CreditCard } from "lucide-react";
import { Link } from "@tanstack/react-router";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { SubscriptionFinanceSummary } from "@/components/billing/subscription-summary-bar";
import { cn } from "@/lib/utils";

export type ActiveSubscriptionHeaderProps = {
  title: string;
  finance?: (SubscriptionFinanceSummary & { seat_quantity?: number | null; is_payg?: boolean }) | null;
  loading?: boolean;
  emptyMessage?: string;
  tintClass?: string;
  packagesHref?: string;
  packagesSearch?: Record<string, string>;
  extra?: React.ReactNode;
};

function formatDate(iso: string | null | undefined) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function intervalLabel(raw: string | null | undefined) {
  const v = String(raw || "").toLowerCase();
  if (v === "yearly") return "Yearly";
  if (v === "monthly") return "Monthly";
  return null;
}

export function ActiveSubscriptionHeader({
  title,
  finance,
  loading,
  emptyMessage = "No active subscription.",
  tintClass = "border-border/60 bg-background/70",
  packagesHref,
  packagesSearch,
  extra,
}: ActiveSubscriptionHeaderProps) {
  if (loading) {
    return (
      <Card className={cn(tintClass)}>
        <CardContent className="flex flex-wrap items-center gap-4 py-4">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-5 w-28" />
          <Skeleton className="h-5 w-32" />
        </CardContent>
      </Card>
    );
  }

  const hasPlan = Boolean(finance?.plan_name || finance?.plan_code || finance?.is_payg);
  if (!hasPlan) {
    return (
      <Card className={cn(tintClass)}>
        <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4 text-sm text-muted-foreground">
          <span>{emptyMessage}</span>
          {packagesHref ? (
            <Link
              to={packagesHref}
              search={packagesSearch}
              className="text-primary underline-offset-4 hover:underline"
            >
              View plans →
            </Link>
          ) : null}
        </CardContent>
      </Card>
    );
  }

  const interval = intervalLabel(finance?.billing_interval);
  const nextDate = finance?.cancel_at_period_end
    ? formatDate(finance.current_period_end || finance.next_billing_date)
    : formatDate(finance?.next_billing_date || finance?.current_period_end);
  const expires = formatDate(finance?.current_period_end);
  const amount = finance?.amount_next_payment_display || (finance?.is_payg ? "Pay as you go" : "—");
  const seats = finance?.seat_quantity != null && finance.seat_quantity > 0 ? finance.seat_quantity : null;

  return (
    <Card className={cn(tintClass)}>
      <CardContent className="space-y-3 py-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{title}</p>
            <p className="text-lg font-semibold">
              {finance?.plan_name || finance?.plan_code || "Active plan"}
              {interval ? ` · ${interval}` : ""}
            </p>
          </div>
          <div className="flex flex-wrap gap-1">
            {(() => {
              const st = String(finance?.status || "").toLowerCase();
              if (st === "trial" || st === "trialing") {
                return (
                  <Badge variant="default" className="text-[10px]">
                    Free trial
                  </Badge>
                );
              }
              if (st === "active" || st === "past_due") {
                return (
                  <Badge variant="secondary" className="text-[10px]">
                    Active subscription
                  </Badge>
                );
              }
              if (finance?.status) {
                return (
                  <Badge variant="secondary" className="text-[10px] capitalize">
                    {String(finance.status).replace(/_/g, " ")}
                  </Badge>
                );
              }
              return null;
            })()}
            {finance?.cancel_at_period_end ? (
              <Badge variant="outline" className="text-[10px]">
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
        <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-muted-foreground">
          {!finance?.is_payg ? (
            <p className="inline-flex items-center gap-1.5">
              <CreditCard className="size-3.5" />
              Next payment: <strong className="text-foreground">{amount}</strong>
              {nextDate ? <> · {nextDate}</> : null}
            </p>
          ) : (
            <p className="inline-flex items-center gap-1.5">
              <CreditCard className="size-3.5" />
              Billing: <strong className="text-foreground">Pay as you go</strong>
            </p>
          )}
          {String(finance?.status || "").toLowerCase() === "trial" || finance?.is_trial ? (
            <p className="inline-flex items-center gap-1.5">
              <CalendarClock className="size-3.5" />
              Free trial
              {finance?.trial_started_at ? <> from {formatDate(finance.trial_started_at)}</> : null}
              {finance?.trial_ends_at || finance?.current_period_end
                ? <> until {formatDate(finance.trial_ends_at || finance.current_period_end)}</>
                : null}
            </p>
          ) : expires ? (
            <p className="inline-flex items-center gap-1.5">
              <CalendarClock className="size-3.5" />
              {finance?.cancel_at_period_end ? "Access until" : "Period ends"}:{" "}
              <strong className="text-foreground">{expires}</strong>
            </p>
          ) : null}
          {Number(finance?.free_seat_quantity || 0) > 0 ? (
            <p className="text-xs">
              {finance?.free_seat_quantity} new seat(s) free until {formatDate(finance?.added_seats_free_until)} ·{" "}
              {finance?.billable_seat_quantity ?? seats} billable now
            </p>
          ) : null}
        </div>
        {extra}
      </CardContent>
    </Card>
  );
}
