import * as React from "react";
import { CalendarClock, CreditCard } from "lucide-react";
import { Link } from "@tanstack/react-router";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export type SubscriptionFinanceSummary = {
  plan_name?: string | null;
  plan_code?: string | null;
  status?: string | null;
  next_billing_date?: string | null;
  amount_next_payment_display?: string | null;
  amount_next_payment_minor?: number | null;
  billing_currency?: string | null;
  cancel_at_period_end?: boolean;
  mandate_status?: string | null;
  payment_provider?: string | null;
  current_period_end?: string | null;
};

function formatDate(iso: string | null | undefined) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function mandateLabel(status: string | null | undefined) {
  const s = String(status || "").toLowerCase();
  if (!s) return null;
  if (s === "active" || s === "submitted") return { text: "Direct Debit active", variant: "default" as const };
  if (s === "pending_customer_approval") return { text: "Mandate pending", variant: "secondary" as const };
  if (s === "failed" || s === "cancelled" || s === "expired") return { text: "Update payment", variant: "destructive" as const };
  return { text: s.replace(/_/g, " "), variant: "outline" as const };
}

type Props = {
  title: string;
  finance: SubscriptionFinanceSummary | null | undefined;
  loading?: boolean;
  emptyMessage?: string;
  tintClass?: string;
};

export function SubscriptionSummaryBar({
  title,
  finance,
  loading,
  emptyMessage = "No active subscription on this tab.",
  tintClass = "border-border/60 bg-muted/30",
}: Props) {
  if (loading) {
    return (
      <Card className={`mb-6 ${tintClass}`}>
        <CardContent className="flex flex-wrap items-center gap-4 py-4">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-5 w-28" />
          <Skeleton className="h-5 w-32" />
        </CardContent>
      </Card>
    );
  }

  if (!finance?.plan_name && !finance?.plan_code) {
    return (
      <Card className={`mb-6 ${tintClass}`}>
        <CardContent className="py-4 text-sm text-muted-foreground">{emptyMessage}</CardContent>
      </Card>
    );
  }

  const mandate = mandateLabel(finance.mandate_status);
  const nextLabel = finance.cancel_at_period_end ? "Access until" : "Next invoice";
  const nextDate = finance.cancel_at_period_end
    ? finance.current_period_end || finance.next_billing_date
    : finance.next_billing_date;

  return (
    <Card className={`mb-6 ${tintClass}`}>
      <CardContent className="flex flex-col gap-3 py-4 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <div className="space-y-1">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{title}</p>
          <p className="text-base font-semibold">{finance.plan_name || finance.plan_code}</p>
          {finance.status ? (
            <p className="text-xs capitalize text-muted-foreground">Status: {String(finance.status).replace(/_/g, " ")}</p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <span className="inline-flex items-center gap-1.5 text-muted-foreground">
            <CalendarClock className="h-4 w-4 shrink-0" />
            <span>
              {nextLabel}: <strong className="text-foreground">{formatDate(nextDate)}</strong>
            </span>
          </span>
          <span className="inline-flex items-center gap-1.5 text-muted-foreground">
            <CreditCard className="h-4 w-4 shrink-0" />
            <span>
              Amount:{" "}
              <strong className="text-foreground">
                {finance.amount_next_payment_display ||
                  (finance.amount_next_payment_minor != null ? `${finance.amount_next_payment_minor}` : "—")}
              </strong>
            </span>
          </span>
          {mandate ? <Badge variant={mandate.variant}>{mandate.text}</Badge> : null}
          {finance.cancel_at_period_end ? <Badge variant="secondary">Cancels at period end</Badge> : null}
        </div>
        <Link to="/account/billing" className="text-sm font-medium text-primary hover:underline">
          Billing details →
        </Link>
      </CardContent>
    </Card>
  );
}
