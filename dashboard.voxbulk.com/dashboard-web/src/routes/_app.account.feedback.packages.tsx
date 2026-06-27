import { createFileRoute, Link } from "@tanstack/react-router";
import * as React from "react";
import { Loader2, MessageCircle, QrCode } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { SubscriptionCancellationBar } from "@/components/billing/subscription-cancellation-card";
import { startFeedbackGoCardlessSubscription } from "@/lib/billing/gocardless";
import { feedbackPlanButtonLabel, planChangeToast } from "@/lib/billing/plans";
import { changeFeedbackPlan, useFeedbackPackages, useFeedbackSubscription, useOrganisation } from "@/lib/queries";
import { useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/lib/queries";
import type { FeedbackPackage } from "@/lib/queries";

import { requireBillingAccess } from "@/lib/guards/billing-route";

export const Route = createFileRoute("/_app/account/feedback/packages")({
  beforeLoad: () => requireBillingAccess(),
  head: () => ({ meta: [{ title: "Customer feedback plans — VoxBulk" }] }),
  component: FeedbackPackagesPage,
});

const CURRENCY_SYMBOL: Record<string, string> = {
  GBP: "£",
  EUR: "€",
  USD: "$",
  CAD: "CA$",
  AUD: "A$",
};

function formatPackagePrice(pkg: FeedbackPackage, orgCurrency?: string, yearly = false) {
  const prices = pkg.prices || [];
  const preferred = orgCurrency?.toUpperCase();
  const match = prices.find((p) => p.currency.toUpperCase() === preferred) || prices[0];
  if (!match) return "—";
  const sym = CURRENCY_SYMBOL[match.currency.toUpperCase()] || `${match.currency} `;
  const minor = yearly ? (match.yearly_price_minor ?? match.monthly_price_minor * 10) : match.monthly_price_minor;
  return `${sym}${(minor / 100).toFixed(0)}/${yearly ? "yr" : "mo"}`;
}

function buildPackageFeatures(pkg: FeedbackPackage): string[] {
  const webIncluded = pkg.web_units_included ?? 0;
  const webLine =
    webIncluded < 0
      ? "Unlimited web surveys/mo"
      : `${webIncluded.toLocaleString()} web surveys/mo`;
  const defaults = [
    `${pkg.max_locations} location${pkg.max_locations === 1 ? "" : "s"}`,
    `${pkg.wa_units_included.toLocaleString()} WhatsApp surveys/mo`,
    webLine,
  ];
  const fromApi = pkg.features?.length ? [...pkg.features] : defaults;
  const hasWeb = fromApi.some((f) => /web survey/i.test(f));
  if (!hasWeb) fromApi.push(webLine);
  return fromApi;
}

function FeedbackPackagesPage() {
  const [busyPlanId, setBusyPlanId] = React.useState<string | null>(null);
  const [billingInterval, setBillingInterval] = React.useState<"monthly" | "yearly">("monthly");
  const qc = useQueryClient();
  const orgQ = useOrganisation();
  const packagesQ = useFeedbackPackages();
  const subscriptionQ = useFeedbackSubscription();

  const orgCountry = String(orgQ.data?.country || "").trim() || "Not set";
  const subscription = subscriptionQ.data;
  const packages = (packagesQ.data || []).slice().sort((a, b) => (a.display_order || 0) - (b.display_order || 0));
  const orgCurrency = String(orgQ.data?.billing_currency || orgQ.data?.currency || "GBP").toUpperCase();
  const currentPlanId = subscription?.active ? subscription.plan_id : null;

  const onSubscribe = async (pkg: FeedbackPackage) => {
    if (!pkg.plan_id) return;
    if (currentPlanId === pkg.plan_id) return;
    setBusyPlanId(pkg.plan_id);
    try {
      if (subscription?.active) {
        const result = await changeFeedbackPlan(pkg.plan_id);
        const planName = pkg.plan_name || pkg.plan_code || "plan";
        toast.success(planChangeToast(result.direction, planName));
        setBusyPlanId(null);
        await Promise.all([
          qc.invalidateQueries({ queryKey: queryKeys.feedbackSubscription }),
          qc.invalidateQueries({ queryKey: queryKeys.feedbackPackages }),
        ]);
        return;
      }
      await startFeedbackGoCardlessSubscription(pkg.plan_id);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not update subscription");
      setBusyPlanId(null);
    }
  };

  const usagePct =
    subscription?.wa_units_included && subscription.wa_units_included > 0
      ? Math.min(100, Math.round(((subscription.wa_units_used || 0) / subscription.wa_units_included) * 100))
      : 0;

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-8 pb-16">
      <PageHeader
        eyebrow="Account"
        title="Customer feedback plans"
        description="Direct Debit packages for WhatsApp and web QR feedback — locations, survey allowances, and monthly/yearly billing."
        actions={
          <Button asChild variant="outline" className="gap-1.5">
            <Link to="/feedback/new">
              <QrCode className="size-4" /> Create QR survey
            </Link>
          </Button>
        }
      />

      <div className="rounded-lg border border-border bg-muted/30 px-4 py-3 text-sm">
        <p className="font-medium">Customer feedback billing</p>
        <p className="text-xs text-muted-foreground">
          Separate from Core platform (AI interviews &amp; outbound surveys). Direct Debit only — no wallet top-ups.
          Plan renames in Admin persist after deploy.
        </p>
        <p className="mt-2 text-xs text-muted-foreground">
          Profile country: <span className="font-medium text-foreground">{orgCountry}</span>
          {" · "}
          <Link to="/settings/profile" className="text-primary underline-offset-4 hover:underline">
            Settings → Profile
          </Link>
        </p>
      </div>

      {subscriptionQ.isLoading ? (
        <Skeleton className="h-32 rounded-xl" />
      ) : subscription?.active ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Current subscription</CardTitle>
            <CardDescription>
              {subscription.plan_name || "Customer feedback"} · {subscription.status}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-lg border border-border bg-background/40 p-3">
                <p className="text-[11px] uppercase tracking-wider text-muted-foreground">Locations allowed</p>
                <p className="mt-1 text-xl font-semibold">{subscription.max_locations ?? 0}</p>
              </div>
              <div className="rounded-lg border border-border bg-background/40 p-3">
                <p className="text-[11px] uppercase tracking-wider text-muted-foreground">WA units remaining</p>
                <p className="mt-1 text-xl font-semibold tabular-nums">{subscription.wa_units_remaining ?? 0}</p>
              </div>
              <div className="rounded-lg border border-border bg-background/40 p-3">
                <p className="text-[11px] uppercase tracking-wider text-muted-foreground">Web surveys remaining</p>
                <p className="mt-1 text-xl font-semibold tabular-nums">
                  {(subscription.web_units_included ?? 0) < 0
                    ? "Unlimited"
                    : (subscription.web_units_remaining ?? 0)}
                </p>
              </div>
              <div className="rounded-lg border border-border bg-background/40 p-3">
                <p className="text-[11px] uppercase tracking-wider text-muted-foreground">Period ends</p>
                <p className="mt-1 text-sm font-medium">
                  {subscription.current_period_end
                    ? new Date(subscription.current_period_end).toLocaleDateString("en-GB")
                    : "—"}
                </p>
              </div>
            </div>
            {subscription.wa_units_included ? (
              <div className="space-y-2">
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>Monthly allowance</span>
                  <span>
                    {subscription.wa_units_used ?? 0} / {subscription.wa_units_included} used
                  </span>
                </div>
                <Progress value={usagePct} className="h-2" />
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center gap-2 py-8 text-center">
            <MessageCircle className="size-8 text-muted-foreground" />
            <p className="font-medium">No active Customer feedback subscription</p>
            <p className="max-w-md text-sm text-muted-foreground">
              Choose a package below to activate QR surveys. Billing is by Direct Debit (GoCardless) only.
            </p>
          </CardContent>
        </Card>
      )}

      <section>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Packages</h2>
          <div className="flex rounded-lg border border-border p-0.5 text-xs">
            <button
              type="button"
              className={`rounded-md px-3 py-1.5 ${billingInterval === "monthly" ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}
              onClick={() => setBillingInterval("monthly")}
            >
              Monthly
            </button>
            <button
              type="button"
              className={`rounded-md px-3 py-1.5 ${billingInterval === "yearly" ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}
              onClick={() => setBillingInterval("yearly")}
            >
              Yearly (2 months free)
            </button>
          </div>
        </div>
        <p className="mb-3 text-xs text-muted-foreground">Prices shown ex-VAT. VAT is added at checkout when applicable.</p>
        {packagesQ.isLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-64 rounded-xl" />
            ))}
          </div>
        ) : packagesQ.isError ? (
          <p className="text-sm text-destructive">
            Could not load packages{packagesQ.error instanceof Error ? `: ${packagesQ.error.message}` : ""}.
          </p>
        ) : packages.length === 0 ? (
          <p className="text-sm text-muted-foreground">No packages available for your market yet.</p>
        ) : (
          <div className="grid items-stretch gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {packages.map((pkg) => {
              const isCurrent = currentPlanId === pkg.plan_id;
              const busy = busyPlanId === pkg.plan_id;
              const btnLabel = feedbackPlanButtonLabel(pkg, packages, {
                busy,
                currentPlanId,
              });
              const features = buildPackageFeatures(pkg);
              return (
                <Card
                  key={pkg.id}
                  className={isCurrent ? "ring-2 ring-primary/30" : pkg.is_featured ? "ring-2 ring-primary/20" : ""}
                >
                  <CardHeader className="pb-2">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <Badge variant="outline" className="mb-2 border-success/40 text-success">Customer Feedback</Badge>
                        <CardTitle className="text-base">{pkg.plan_name || "Customer feedback"}</CardTitle>
                      </div>
                      {pkg.is_featured ? (
                        <span className="shrink-0 rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-primary">
                          Most popular
                        </span>
                      ) : null}
                    </div>
                    <CardDescription className="text-xl font-semibold text-foreground">
                      {formatPackagePrice(pkg, orgCurrency, billingInterval === "yearly")}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-1 flex-col space-y-3 text-sm">
                    <ul className="space-y-1.5 text-muted-foreground">
                      {features.map((feature) => (
                        <li key={feature} className="flex items-start gap-2">
                          <span className="mt-1.5 size-1 shrink-0 rounded-full bg-primary" />
                          <span>{feature}</span>
                        </li>
                      ))}
                    </ul>
                    {pkg.admin_notes ? <p className="text-xs text-muted-foreground">{pkg.admin_notes}</p> : null}
                    <Button
                      className="mt-auto w-full"
                      variant={isCurrent ? "outline" : "default"}
                      disabled={isCurrent || Boolean(busyPlanId)}
                      onClick={() => void onSubscribe(pkg)}
                    >
                      {busy ? (
                        <>
                          <Loader2 className="mr-2 size-4 animate-spin" /> Redirecting…
                        </>
                      ) : (
                        btnLabel
                      )}
                    </Button>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </section>

      {subscription?.active ? (
        <SubscriptionCancellationBar planName={subscription.plan_name} service="feedback" />
      ) : null}
    </div>
  );
}
