import { createFileRoute, Link } from "@tanstack/react-router";
import * as React from "react";
import { Clock, FileText, MessageCircle, Phone, Wallet } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import { gocardlessAvailable, startGoCardlessSubscription } from "@/lib/billing/gocardless";
import { marketLabel } from "@/lib/billing/market";
import { isSamePlan, planButtonLabel, sortedPlans, type PlanLike } from "@/lib/billing/plans";
import { useBillingPricing, useBillingWallet, useOrganisation, useWalletTopup } from "@/lib/queries";
import { useSession } from "@/lib/session";

export const Route = createFileRoute("/_app/account/packages")({
  head: () => ({ meta: [{ title: "Packages & pricing — VoxBulk" }] }),
  component: PackagesPage,
});

type PlanRow = Record<string, unknown>;

function sym(data: Record<string, unknown> | undefined) {
  return String(data?.currency_symbol || "£");
}

function interviewCost(perMin: number, duration: number, conn: number, count: number) {
  const perCall = conn + perMin * duration;
  return { perCall, total: perCall * count };
}

function PackagesPage() {
  const [busyPlanId, setBusyPlanId] = React.useState<string | null>(null);
  const { session } = useSession();
  const orgQ = useOrganisation();
  const orgCountry = String(orgQ.data?.country || "").trim();
  const pricingQ = useBillingPricing("auto", orgCountry);
  const walletQ = useBillingWallet();
  const topupM = useWalletTopup();

  const data = pricingQ.data;
  const market = String(data?.org_market || data?.market || "gbp");
  const pricingLabel = String(data?.market_label || marketLabel(market));
  const countryLabel = orgCountry || String(data?.org_country || "").trim() || "Not set";
  const subscription = session?.subscription;
  const currentPlan = (subscription?.plan || null) as PlanLike | null;
  const gcReady = gocardlessAvailable(subscription as Record<string, unknown> | null);
  const settings = (data?.settings || {}) as Record<string, unknown>;
  const plans = sortedPlans((data?.plans || []) as PlanRow[]);
  const services = (data?.services || {}) as Record<string, unknown>;
  const tiers = (data?.topup_tiers || []) as Array<Record<string, unknown>>;
  const estimatorDefaults = (data?.estimator_defaults || {}) as Record<string, number>;

  const [duration, setDuration] = React.useState(12);
  const [interviewCount, setInterviewCount] = React.useState(100);
  const [topupPence, setTopupPence] = React.useState(5000);
  const [customTopup, setCustomTopup] = React.useState("50");

  React.useEffect(() => {
    if (estimatorDefaults.duration_min) setDuration(estimatorDefaults.duration_min);
    if (estimatorDefaults.interview_count) setInterviewCount(estimatorDefaults.interview_count);
  }, [estimatorDefaults.duration_min, estimatorDefaults.interview_count]);

  const connEnabled = Boolean(services.connection_fee_enabled);
  const connPence = Number(services.connection_fee_pence || 0);
  const waFee = Number(services.whatsapp_survey_fee_pence || 150);
  const atsFee = Number(services.ats_cv_scan_fee_pence || 75);
  const paygPerMin = Number(services.interview_per_min_pence || 35);

  const breakdown = React.useMemo(() => {
    const avgDuration = Number(settings.estimator_default_duration_min || duration || 12);
    const perInterview = connPence + paygPerMin * avgDuration;
    const credit = topupPence;
    return {
      interviews: perInterview > 0 ? Math.floor(credit / perInterview) : 0,
      wa: waFee > 0 ? Math.floor(credit / waFee) : 0,
      cv: atsFee > 0 ? Math.floor(credit / atsFee) : 0,
    };
  }, [topupPence, connPence, paygPerMin, waFee, atsFee, settings.estimator_default_duration_min, duration]);

  const onTopup = async (amountPence: number, tierId?: string) => {
    try {
      const res = await topupM.mutateAsync({ amount_pence: amountPence, tier_id: tierId });
      if ((res as Record<string, unknown>).awaiting_payment) {
        toast.message("Payment required", { description: String((res as Record<string, unknown>).message || "") });
        return;
      }
      toast.success(`Wallet topped up — ${String((res as Record<string, unknown>).wallet_balance_gbp || "")}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Top-up failed");
    }
  };

  const onSubscribe = async (plan: PlanRow) => {
    if (plan.is_enterprise) return;
    if (isSamePlan(plan, currentPlan, plans)) return;
    if (!gcReady) {
      toast.error("GoCardless checkout is not configured. Enable it in admin integrations.");
      return;
    }
    setBusyPlanId(String(plan.id));
    try {
      await startGoCardlessSubscription(String(plan.id));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not start checkout");
      setBusyPlanId(null);
    }
  };

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-8 pb-16">
      <PageHeader eyebrow="Account" title="Packages & pricing" description="Subscription plans, service costs, and wallet top-up." />

      <div className="rounded-lg border border-border bg-muted/30 px-4 py-3 text-sm">
        <p className="font-medium">{pricingLabel}</p>
        <p className="text-xs text-muted-foreground">
          Profile country: <span className="font-medium text-foreground">{countryLabel}</span>
          {!orgCountry ? (
            <>
              {" "}— select your country in{" "}
              <Link to="/settings/profile" className="text-primary underline-offset-4 hover:underline">Settings → Profile</Link>{" "}
              to see local prices (defaults to GBP until saved).
            </>
          ) : (
            <>
              {" "}· change in{" "}
              <Link to="/settings/profile" className="text-primary underline-offset-4 hover:underline">Settings → Profile</Link>.
            </>
          )}
        </p>
      </div>

      {walletQ.data && (
        <Card>
          <CardContent className="flex items-center justify-between gap-4 p-4">
            <div className="flex items-center gap-2 text-sm">
              <Wallet className="size-4 text-primary" />
              <span className="text-muted-foreground">Wallet balance</span>
              <span className="font-semibold">{walletQ.data.wallet_balance_gbp}</span>
            </div>
          </CardContent>
        </Card>
      )}

      <section>
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Subscription plans</h2>
        {pricingQ.isLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-72" />)}</div>
        ) : (
          <div className="grid items-stretch gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {plans.map((p) => {
              const ent = Boolean(p.is_enterprise);
              const perMin = Number(p.per_min_pence || 0);
              const conn = connEnabled ? connPence : 0;
              const low = Number(p.typical_call_low_display?.toString().replace(/[^\d.]/g, "") || (conn + perMin * 10) / 100);
              const high = Number(p.typical_call_high_display?.toString().replace(/[^\d.]/g, "") || (conn + perMin * 15) / 100);
              const isCurrent = isSamePlan(p, currentPlan, plans);
              const isFeatured = Boolean(p.is_featured);
              const btnLabel = planButtonLabel(p, currentPlan, { busy: busyPlanId === String(p.id), plans });
              return (
                <div key={String(p.id)} className="relative flex pt-3">
                  {isFeatured && (
                    <span className="absolute left-1/2 top-0 z-10 -translate-x-1/2 rounded-full bg-primary px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-primary-foreground shadow">
                      Most popular
                    </span>
                  )}
                  <Card className={`flex h-full w-full flex-col ${isFeatured ? "border-primary shadow-md" : ""} ${isCurrent ? "ring-2 ring-primary/30" : ""}`}>
                    <CardHeader className="pb-2 pt-5">
                      <CardTitle className="text-base">{String(p.name)}</CardTitle>
                      <CardDescription className="text-xl font-semibold text-foreground">
                        {ent ? "Let's talk" : `${String(p.price_display || p.price_display_pence)}${!ent ? "/mo" : ""}`}
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="flex flex-1 flex-col space-y-2 text-xs">
                      {!ent && (
                        <>
                          <p>Cost per min: <strong>{String(p.per_min_display)}</strong></p>
                          <p className="text-muted-foreground">Extra min (after package): <strong>{String(p.extra_per_min_display || p.per_min_display)}</strong></p>
                          {connEnabled && <p className="text-muted-foreground">{String(services.connection_fee_label)}: {String(services.connection_fee_display)}</p>}
                          <p className="text-muted-foreground">Typical interview<br />{sym(data)}{low.toFixed(2)} – {sym(data)}{high.toFixed(2)} per call</p>
                        </>
                      )}
                      <div className="mt-auto space-y-1 border-t border-border pt-2">
                        <div className="flex justify-between"><span className="text-muted-foreground">Mins included</span><span>{ent ? "Custom" : Number(p.minutes_included || 0).toLocaleString()}</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">WA surveys</span><span>{ent ? "Custom" : Number(p.whatsapp_included || 0).toLocaleString()}</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">CV scans</span><span>{ent ? "Custom" : Number(p.cv_scans_included || 0).toLocaleString()}</span></div>
                      </div>
                      <Button
                        className="mt-3 w-full"
                        variant={isFeatured && !isCurrent ? "default" : "outline"}
                        disabled={ent || isCurrent || Boolean(busyPlanId)}
                        onClick={() => void onSubscribe(p)}
                      >
                        {ent ? "Contact us" : btnLabel}
                      </Button>
                    </CardContent>
                  </Card>
                </div>
              );
            })}
          </div>
        )}
      </section>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Clock className="size-5 text-primary" />
            <div>
              <CardTitle>How much will my interviews cost?</CardTitle>
              <CardDescription>(connection fee + duration × per-minute rate) × number of interviews</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-3">
            <span className="min-w-36 text-sm text-muted-foreground">Call duration (mins)</span>
            <Slider value={[duration]} min={5} max={30} step={1} onValueChange={([v]) => setDuration(v)} className="flex-1" />
            <span className="min-w-12 text-right text-sm font-medium">{duration} min</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="min-w-36 text-sm text-muted-foreground">Number of interviews</span>
            <Slider value={[interviewCount]} min={10} max={500} step={10} onValueChange={([v]) => setInterviewCount(v)} className="flex-1" />
            <span className="min-w-12 text-right text-sm font-medium">{interviewCount}</span>
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {plans.map((p) => {
              if (p.is_enterprise) {
                return (
                  <div key={String(p.id)} className="rounded-lg bg-muted/50 p-3 text-center">
                    <p className="text-[11px] text-muted-foreground">{String(p.name)}</p>
                    <p className="mt-1 text-sm font-medium">Contact us</p>
                  </div>
                );
              }
              const perMin = Number(p.per_min_pence || 0);
              const { perCall, total } = interviewCost(perMin, duration, connEnabled ? connPence : 0, interviewCount);
              const fx = Number(data?.fx_multipliers?.[market as keyof object] || 1);
              return (
                <div key={String(p.id)} className="rounded-lg bg-muted/50 p-3 text-center">
                  <p className="text-[11px] text-muted-foreground">{String(p.name)}</p>
                  <p className="text-base font-semibold">{sym(data)}{((total * fx) / 100).toFixed(2)}</p>
                  <p className="text-[10px] text-muted-foreground">{sym(data)}{((perCall * fx) / 100).toFixed(2)}/call</p>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <section>
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">What each service costs</h2>
        <div className="grid gap-3 md:grid-cols-3">
          <Card><CardContent className="p-4"><div className="mb-2 flex items-center gap-2"><Phone className="size-4 text-primary" /><span className="font-medium">Interview call</span></div><p className="text-xl font-semibold">{String(services.interview_per_min_display)}/min</p>{connEnabled && <p className="text-xs text-muted-foreground">+ {String(services.connection_fee_display)} connection fee per call</p>}</CardContent></Card>
          <Card><CardContent className="p-4"><div className="mb-2 flex items-center gap-2"><MessageCircle className="size-4 text-green-600" /><span className="font-medium">WhatsApp survey</span></div><p className="text-xl font-semibold">{String(services.whatsapp_survey_display)}</p><p className="text-xs text-muted-foreground">per user sent</p></CardContent></Card>
          <Card><CardContent className="p-4"><div className="mb-2 flex items-center gap-2"><FileText className="size-4 text-amber-600" /><span className="font-medium">ATS CV scan</span></div><p className="text-xl font-semibold">{String(services.ats_cv_scan_display)}</p><p className="text-xs text-muted-foreground">per CV scanned</p></CardContent></Card>
        </div>
      </section>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Wallet className="size-5 text-green-600" />
            <div>
              <CardTitle>Credit top-up</CardTitle>
              <CardDescription>No expiry — use across calls, surveys and CV scans (min {sym(data)}5)</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {tiers.map((t) => (
              <Button key={String(t.id)} variant="outline" size="sm" disabled={topupM.isPending} onClick={() => void onTopup(Number(t.total_credit_pence || 0), String(t.id))}>
                {String(t.total_credit_display || t.credit_display)}
                {Number(t.bonus_credit_pence || 0) > 0 && <span className="ml-1 text-[10px] text-green-600">+bonus</span>}
              </Button>
            ))}
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Custom amount ({sym(data)})</label>
              <Input type="number" min={5} step={5} value={customTopup} onChange={(e) => { setCustomTopup(e.target.value); setTopupPence(Math.round(Number(e.target.value || 0) * 100)); }} className="w-32" />
            </div>
            <Button disabled={topupM.isPending} onClick={() => void onTopup(Math.round(Number(customTopup || 0) * 100))}>Top up custom</Button>
          </div>
          <Slider value={[topupPence / 100]} min={5} max={500} step={5} onValueChange={([v]) => { setTopupPence(Math.round(v * 100)); setCustomTopup(String(v)); }} />
          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="rounded-lg bg-muted/50 p-3"><p className="text-[11px] text-muted-foreground">Est. interviews</p><p className="font-semibold">~{breakdown.interviews}</p></div>
            <div className="rounded-lg bg-muted/50 p-3"><p className="text-[11px] text-muted-foreground">WA surveys</p><p className="font-semibold">{breakdown.wa}</p></div>
            <div className="rounded-lg bg-muted/50 p-3"><p className="text-[11px] text-muted-foreground">CV scans</p><p className="font-semibold">{breakdown.cv}</p></div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
