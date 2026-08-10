import { createFileRoute, Link, redirect } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BadgeCheck,
  CalendarClock,
  CreditCard,
  Gauge,
  Package,
  Shield,
  Sparkles,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import {
  CheckoutConfirmDialog,
  type CheckoutConfirmDetails,
} from "@/components/billing/checkout-confirm-dialog";
import { StripeCardCheckoutDialog } from "@/components/billing/stripe-card-checkout-dialog";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/status-badge";
import { apiFetch, ApiError } from "@/lib/api";
import { startGoCardlessSubscription } from "@/lib/billing/gocardless";
import {
  availablePaymentMethods,
  clearCardSubscriptionState,
  completeCardSubscription,
  isStripeElementsCheckout,
  primarySubscriptionProvider,
  startCardSubscription,
  type PaymentMethodChoice,
  type StripeElementsCheckout,
} from "@/lib/billing/subscription-payment";
import { requireBillingAccess } from "@/lib/guards/billing-route";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/account/private-package")({
  beforeLoad: async () => {
    await requireBillingAccess();
    try {
      await apiFetch("/billing/custom-package");
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        throw redirect({ to: "/account/billing" });
      }
    }
  },
  head: () => ({ meta: [{ title: "Private package — VoxBulk" }] }),
  component: PrivatePackagePage,
});

type UsageRow = {
  module: string;
  key: string;
  label: string;
  used: number;
  included: number;
  remaining: number | null;
  unit: string;
  pct_used: number;
};

type CustomPackagePayload = {
  assigned: boolean;
  package: {
    id: string;
    name: string;
    code: string;
    interval: string;
    currency: string;
    price_display: string;
    price_minor?: number;
    status: string;
    enabled_services: string[];
    allowlist_country_count?: number | null;
    allowlist?: { mode?: string };
  };
  billing: {
    interval: string;
    billing_interval?: string;
    currency?: string;
    amount_next_payment_display: string;
    amount_next_payment_minor?: number;
    next_billing_date: string | null;
    payment_status: string;
    payment_method_label?: string | null;
    can_setup_payment: boolean;
    currency_mismatch?: boolean;
    payment_block_reason?: string | null;
    billing_plan_id?: string | null;
    payment_options?: Record<string, unknown>;
    setup_path: string;
  };
  usage: { rows: UsageRow[]; period_note?: string };
  extras: { estimated_display: string; note?: string };
};

const MODULE_LABEL: Record<string, string> = {
  customer_feedback: "Customer Feedback",
  core: "Core / Voice",
  survey: "WA Survey",
  smart_card: "Smart Card",
  expo: "Expo",
};

const MODULE_TONE: Record<string, string> = {
  customer_feedback: "from-emerald-500/15 to-emerald-600/5 border-emerald-500/25",
  core: "from-teal-500/15 to-teal-700/5 border-teal-500/25",
  survey: "from-sky-500/15 to-sky-600/5 border-sky-500/25",
  smart_card: "from-amber-500/15 to-amber-600/5 border-amber-500/25",
  expo: "from-stone-500/15 to-stone-600/5 border-stone-500/25",
};

function usePrivatePackage() {
  return useQuery({
    queryKey: ["billing", "custom-package"],
    queryFn: () => apiFetch<CustomPackagePayload>("/billing/custom-package"),
    retry: false,
    refetchOnMount: "always",
  });
}

function formatDate(iso: string | null | undefined) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

function MeterCard({ row }: { row: UsageRow }) {
  const pct = Math.min(100, Math.max(0, Number(row.pct_used || 0)));
  const tone =
    pct >= 100 ? "text-destructive" : pct >= 80 ? "text-amber-600 dark:text-amber-400" : "text-foreground";
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-border/80 bg-card/60 p-4 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-xs font-medium text-muted-foreground">{row.label}</p>
          <p className={cn("mt-1 text-lg font-semibold tabular-nums", tone)}>
            {row.used.toLocaleString()}
            <span className="text-sm font-normal text-muted-foreground">
              {" "}
              / {row.included > 0 ? row.included.toLocaleString() : "—"} {row.unit}
            </span>
          </p>
        </div>
        <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          {pct.toFixed(0)}%
        </span>
      </div>
      <Progress value={row.included > 0 ? pct : 0} className="h-1.5" />
      {row.remaining != null ? (
        <p className="text-[11px] text-muted-foreground">
          {row.remaining.toLocaleString()} {row.unit} remaining
        </p>
      ) : null}
    </div>
  );
}

function PrivatePackagePage() {
  const q = usePrivatePackage();
  const qc = useQueryClient();
  const data = q.data;

  const [checkoutOpen, setCheckoutOpen] = React.useState(false);
  const [checkoutDetails, setCheckoutDetails] = React.useState<CheckoutConfirmDetails | null>(null);
  const [busyCheckout, setBusyCheckout] = React.useState(false);
  const [stripeCheckout, setStripeCheckout] = React.useState<StripeElementsCheckout | null>(null);

  const paymentOpts = data?.billing?.payment_options || null;
  const paymentMethods = availablePaymentMethods(
    paymentOpts ? { payment_options: paymentOpts } : null,
  );
  const primaryProvider = primarySubscriptionProvider(
    paymentOpts ? { payment_options: paymentOpts } : null,
  );
  const defaultPayMethod =
    (paymentMethods.includes(primaryProvider as PaymentMethodChoice)
      ? (primaryProvider as PaymentMethodChoice)
      : paymentMethods[0]) || "gocardless";

  const billingInterval = (
    data?.billing?.billing_interval === "yearly" || data?.package?.interval === "yearly"
      ? "yearly"
      : "monthly"
  ) as "monthly" | "yearly";

  const invalidate = React.useCallback(async () => {
    await qc.invalidateQueries({ queryKey: ["billing", "custom-package"] });
  }, [qc]);

  const openPaymentSetup = () => {
    if (!data?.billing?.billing_plan_id) {
      toast.error("Payment plan is not ready yet. Try again in a moment.");
      return;
    }
    if (!paymentMethods.length) {
      toast.error("No subscription payment method is configured for your region.");
      return;
    }
    setCheckoutDetails({
      planName: data.package.name,
      intervalLabel: billingInterval === "yearly" ? "Annually" : "Monthly",
      amountDisplay: data.billing.amount_next_payment_display,
      amountMinor: data.billing.amount_next_payment_minor ?? data.package.price_minor ?? null,
      amountNote: "Private package fee",
      serviceKind: "voxbulk",
      currency: data.package.currency || data.billing.currency || null,
    });
    setCheckoutOpen(true);
  };

  const runCheckout = async (paymentMethod?: PaymentMethodChoice) => {
    const planId = data?.billing?.billing_plan_id;
    if (!planId) return;
    setBusyCheckout(true);
    setCheckoutOpen(false);
    try {
      const method = paymentMethod || defaultPayMethod;
      if (method === "gocardless") {
        await startGoCardlessSubscription(planId, billingInterval, {
          returnTo: "/account/private-package",
        });
        return;
      }
      const result = await startCardSubscription(planId, billingInterval, "stripe", {
        returnPath: "/account/private-package",
      });
      if (result?.provider === "promo_discount" || result?.paid) {
        toast.success(
          result.trial_days
            ? `Trial started — ${result.trial_days} days free`
            : "Promo applied — subscription activated",
        );
        await invalidate();
      } else if (isStripeElementsCheckout(result)) {
        setStripeCheckout(result);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not start checkout");
    } finally {
      setBusyCheckout(false);
    }
  };

  if (q.isLoading) {
    return (
      <div className="flex w-full flex-col gap-6">
        <PageHeader eyebrow="Account" title="Private package" description="Loading your negotiated package…" />
        <div className="grid gap-4 md:grid-cols-3">
          <Skeleton className="h-36 rounded-2xl" />
          <Skeleton className="h-36 rounded-2xl" />
          <Skeleton className="h-36 rounded-2xl" />
        </div>
        <Skeleton className="h-64 rounded-2xl" />
      </div>
    );
  }

  if (q.isError || !data?.package) {
    return (
      <div className="flex w-full flex-col gap-6">
        <PageHeader
          eyebrow="Account"
          title="Private package"
          description="No private package is assigned to this organisation."
          actions={
            <Button asChild variant="outline" size="sm">
              <Link to="/account/billing">Back to Billing</Link>
            </Button>
          }
        />
      </div>
    );
  }

  const pkg = data.package;
  const billing = data.billing;
  const rows = data.usage?.rows || [];
  const byModule = React.useMemo(() => {
    const map = new Map<string, UsageRow[]>();
    for (const row of rows) {
      const list = map.get(row.module) || [];
      list.push(row);
      map.set(row.module, list);
    }
    return map;
  }, [rows]);

  const intervalLabel = billing.interval === "yearly" ? "Annually" : "Monthly";
  const needsPayment = billing.can_setup_payment;

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Account"
        title="Private package"
        description="Your negotiated VoxBulk deal — usage, next payment, and payment setup in one place. Standard Billing stays available for other products."
        actions={
          <Button asChild variant="outline" size="sm" className="gap-1.5">
            <Link to="/account/billing">
              <CreditCard className="size-4" /> Billing & invoices
            </Link>
          </Button>
        }
      />

      <section
        className={cn(
          "relative overflow-hidden rounded-2xl border border-primary/20 bg-gradient-to-br from-primary/10 via-background to-emerald-500/5 p-6 shadow-sm",
        )}
      >
        <div className="pointer-events-none absolute -right-8 -top-8 size-40 rounded-full bg-primary/10 blur-2xl" />
        <div className="relative flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="min-w-0 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-primary">
                <Sparkles className="size-3.5" /> Special package
              </span>
              <StatusBadge tone="live" label="Active" />
            </div>
            <div>
              <h2 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">{pkg.name}</h2>
              <p className="mt-1 font-mono text-xs text-muted-foreground">{pkg.code}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {(pkg.enabled_services || []).map((key) => (
                <span
                  key={key}
                  className={cn(
                    "rounded-lg border bg-gradient-to-br px-2.5 py-1 text-xs font-medium text-foreground",
                    MODULE_TONE[key] || "border-border bg-muted",
                  )}
                >
                  {MODULE_LABEL[key] || key}
                </span>
              ))}
            </div>
          </div>
          <div className="rounded-xl border border-border/70 bg-background/80 px-5 py-4 backdrop-blur">
            <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Package price</p>
            <p className="mt-1 font-mono text-3xl font-semibold tabular-nums text-foreground">
              {pkg.price_display}
              <span className="ml-1 text-sm font-normal text-muted-foreground">
                /{billing.interval === "yearly" ? "yr" : "mo"}
              </span>
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              {intervalLabel} · {pkg.currency}
            </p>
          </div>
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <Card className="border-border/80 shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <CalendarClock className="size-4 text-primary" /> Next payment
            </CardTitle>
            <CardDescription>Base package fee for your private deal</CardDescription>
          </CardHeader>
          <CardContent className="space-y-1">
            <p className="font-mono text-2xl font-semibold tabular-nums">{billing.amount_next_payment_display}</p>
            <p className="text-sm text-muted-foreground">Due {formatDate(billing.next_billing_date)}</p>
            <p className="text-xs text-muted-foreground">{data.extras?.note}</p>
          </CardContent>
        </Card>

        <Card className="border-border/80 shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <CreditCard className="size-4 text-primary" /> Payment method
            </CardTitle>
            <CardDescription>Direct Debit or card on file for renewals</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {needsPayment ? (
              <>
                <p className="text-sm text-amber-700 dark:text-amber-400">
                  Payment setup required before automatic collection.
                </p>
                <Button className="gap-1.5" disabled={busyCheckout} onClick={openPaymentSetup}>
                  <Shield className="size-4" /> Set up payment
                </Button>
              </>
            ) : billing.payment_block_reason ? (
              <>
                <p className="text-sm text-amber-700 dark:text-amber-400">{billing.payment_block_reason}</p>
                <Button asChild variant="outline" size="sm" className="gap-1.5">
                  <Link to="/account/billing">Billing & invoices</Link>
                </Button>
              </>
            ) : (
              <>
                <div className="flex items-center gap-2 text-sm">
                  <BadgeCheck className="size-4 text-emerald-600" />
                  <span>{billing.payment_method_label || "Payment method on file"}</span>
                </div>
                <Button asChild variant="outline" size="sm" className="gap-1.5">
                  <Link to="/account/billing">Manage on Billing</Link>
                </Button>
              </>
            )}
          </CardContent>
        </Card>

        <Card className="border-border/80 shadow-sm md:col-span-2 xl:col-span-1">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <Gauge className="size-4 text-primary" /> Extras this period
            </CardTitle>
            <CardDescription>Estimated overage before next invoice</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="font-mono text-2xl font-semibold tabular-nums">{data.extras?.estimated_display || "—"}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Accrued extras will be added to your next monthly invoice once metering is fully wired.
            </p>
          </CardContent>
        </Card>
      </div>

      <section className="space-y-4">
        <div className="flex items-end justify-between gap-3">
          <div>
            <h3 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
              <Package className="size-5 text-primary" /> Package usage
            </h3>
            <p className="mt-1 text-sm text-muted-foreground">{data.usage?.period_note}</p>
          </div>
        </div>

        {Array.from(byModule.entries()).map(([module, moduleRows]) => (
          <div key={module} className="space-y-3">
            <div
              className={cn(
                "inline-flex rounded-lg border bg-gradient-to-br px-3 py-1.5 text-sm font-semibold",
                MODULE_TONE[module] || "border-border bg-muted",
              )}
            >
              {MODULE_LABEL[module] || module}
            </div>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {moduleRows.map((row) => (
                <MeterCard key={`${row.module}-${row.key}`} row={row} />
              ))}
            </div>
          </div>
        ))}

        {rows.length === 0 ? (
          <Card>
            <CardContent className="py-10 text-center text-sm text-muted-foreground">
              No service modules are enabled on this package yet. Ask your account manager to update the deal.
            </CardContent>
          </Card>
        ) : null}
      </section>

      {pkg.allowlist?.mode === "custom" ? (
        <Card className="border-border/80 bg-muted/20 shadow-sm">
          <CardContent className="flex flex-wrap items-center gap-3 py-4 text-sm">
            <Shield className="size-4 text-primary" />
            <span>
              Outbound AI calls allowed to{" "}
              <strong>{pkg.allowlist_country_count ?? 0} countries</strong> on this private package.
            </span>
          </CardContent>
        </Card>
      ) : null}

      <CheckoutConfirmDialog
        open={checkoutOpen}
        onOpenChange={(open) => {
          setCheckoutOpen(open);
          if (!open) setCheckoutDetails(null);
        }}
        details={checkoutDetails}
        serviceHint="Private package"
        tintClass="border-emerald-200/80 bg-emerald-50/50 dark:border-emerald-800/40 dark:bg-emerald-950/20"
        confirmLabel="Continue to payment"
        paymentMethods={paymentMethods}
        defaultPaymentMethod={defaultPayMethod}
        loading={busyCheckout}
        onConfirm={runCheckout}
      />

      <StripeCardCheckoutDialog
        open={Boolean(stripeCheckout)}
        onOpenChange={(open) => {
          if (!open) setStripeCheckout(null);
        }}
        session={stripeCheckout}
        title="Pay for private package"
        onPaid={async (paymentIntentId) => {
          try {
            await completeCardSubscription(paymentIntentId);
            clearCardSubscriptionState();
            toast.success("Private package payment set up successfully.");
            setStripeCheckout(null);
            await invalidate();
          } catch (e) {
            toast.error(e instanceof Error ? e.message : "Could not activate subscription");
            throw e;
          }
        }}
      />
    </div>
  );
}
