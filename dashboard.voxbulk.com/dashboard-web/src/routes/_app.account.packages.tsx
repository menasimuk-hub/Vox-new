import { createFileRoute, Link } from "@tanstack/react-router";
import * as React from "react";
import { Check, Clock, FileText, MessageCircle, Phone, Wallet, Smile, Megaphone, Sparkles, Briefcase, ClipboardList, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { apiFetch } from "@/lib/api";
import { gocardlessAvailable, startGoCardlessSubscription, startFeedbackGoCardlessSubscription } from "@/lib/billing/gocardless";
import { marketLabel } from "@/lib/billing/market";
import {
  feedbackPlanButtonLabel,
  isSamePlan,
  planButtonLabel,
  planChangeToast,
  sortedPlans,
  type PlanLike,
} from "@/lib/billing/plans";
import {
  changeCorePlan,
  changeFeedbackPlan,
  useBillingPricing,
  useBillingSubscriptionsSummary,
  useBillingWallet,
  useCreateSupportTicket,
  useFeedbackPackages,
  useFeedbackSubscription,
  useOrganisation,
  queryKeys,
} from "@/lib/queries";
import { useSession } from "@/lib/session";
import { WalletTopupDialog } from "@/components/wallet-topup-dialog";
import { SubscriptionSummaryBar } from "@/components/billing/subscription-summary-bar";
import type { FeedbackPackage } from "@/lib/queries";
import { useQueryClient } from "@tanstack/react-query";

import { requireBillingAccess } from "@/lib/guards/billing-route";

export const Route = createFileRoute("/_app/account/packages")({
  beforeLoad: () => requireBillingAccess(),
  head: () => ({ meta: [{ title: "Packages & pricing — VoxBulk" }] }),
  validateSearch: (search: Record<string, unknown>) => {
    const tab = typeof search.tab === "string" ? search.tab : undefined;
    return {
      tab: tab === "core" || tab === "feedback" || tab === "campaigns" ? tab : undefined,
    };
  },
  component: PackagesPage,
});

type PlanRow = Record<string, unknown>;
type ServiceTab = "core" | "feedback" | "campaigns";

const CURRENCY_SYMBOL: Record<string, string> = {
  GBP: "£",
  EUR: "€",
  USD: "$",
  CAD: "CA$",
  AUD: "A$",
};

const SERVICE_TABS: Record<ServiceTab, { label: string; icon: React.ComponentType<{ className?: string }>; tint: string; ring: string; bg: string; chip: string; blurb: string; billing: string }> = {
  core: { label: "Core platform", icon: Sparkles, tint: "text-primary", ring: "ring-primary/30", bg: "from-primary/10", chip: "bg-primary/15 text-primary", blurb: "AI interviews + outbound WA & AI-call surveys. Does not include Customer Feedback QR.", billing: "Subscription + top-up" },
  feedback: { label: "Customer Feedback", icon: Smile, tint: "text-success", ring: "ring-success/30", bg: "from-success/10", chip: "bg-success/15 text-success", blurb: "QR-driven inbound WhatsApp feedback. Separate subscription — not included in Core platform.", billing: "Subscription only" },
  campaigns: { label: "Campaigns", icon: Megaphone, tint: "text-amber-500", ring: "ring-amber-500/30", bg: "from-amber-500/10", chip: "bg-amber-500/15 text-amber-500", blurb: "WhatsApp broadcast templates — buy credit packs when you need to send.", billing: "Top-up credits" },
};

const CAMPAIGN_CREDIT_PACKS = [
  { name: "Campaign 1k", sends: 1000, featured: false },
  { name: "Campaign 5k", sends: 5000, featured: true },
  { name: "Campaign 25k", sends: 25000, featured: false },
];

function isPaygPlan(plan: PlanRow) {
  return String(plan.code || "").toLowerCase() === "payg" || Boolean(plan.is_payg);
}

function sym(data: Record<string, unknown> | undefined) {
  const market = String(data?.org_market || data?.market || "usd").toLowerCase();
  const symbols: Record<string, string> = { gbp: "£", eur: "€", usd: "$", cad: "CA$", aud: "A$" };
  return String(data?.currency_symbol || symbols[market] || "$");
}

function interviewCost(perMin: number, duration: number, conn: number, count: number) {
  const perCall = conn + perMin * duration;
  return { perCall, total: perCall * count };
}

function PackagesPage() {
  const { tab: tabFromUrl } = Route.useSearch();
  const [busyPlanId, setBusyPlanId] = React.useState<string | null>(null);
  const { session, refetch: refetchSession } = useSession();
  const qc = useQueryClient();
  const orgQ = useOrganisation();
  const orgCountry = String(orgQ.data?.country || "").trim();
  const pricingQ = useBillingPricing("auto", orgCountry);
  const walletQ = useBillingWallet();
  const feedbackPackagesQ = useFeedbackPackages();
  const feedbackSubQ = useFeedbackSubscription();
  const subsSummaryQ = useBillingSubscriptionsSummary();
  const createTicketM = useCreateSupportTicket();
  const [topupOpen, setTopupOpen] = React.useState(false);
  const [packagesTab, setPackagesTab] = React.useState<ServiceTab>(tabFromUrl || "core");
  const [busyFeedbackPlanId, setBusyFeedbackPlanId] = React.useState<string | null>(null);
  const [enterpriseOpen, setEnterpriseOpen] = React.useState(false);
  const [enterpriseScreenings, setEnterpriseScreenings] = React.useState("");
  const [enterpriseWaSurveys, setEnterpriseWaSurveys] = React.useState("");
  const [enterpriseNotes, setEnterpriseNotes] = React.useState("");

  const data = pricingQ.data;
  const market = String(data?.org_market || data?.market || "gbp");
  const pricingLabel = String(data?.market_label || marketLabel(market));
  const countryLabel = orgCountry || String(data?.org_country || "").trim() || "Not set";
  const subscription = session?.subscription;
  const currentPlan = (subscription?.plan || null) as PlanLike | null;
  const currentCorePlanId = subscription?.subscription?.plan_id || currentPlan?.id || null;
  const pendingCorePlanId = subscription?.pending_plan?.id || subscription?.subscription?.pending_plan_id || null;
  const gcReady = gocardlessAvailable(subscription as Record<string, unknown> | null);
  const coreSubStatus = String(subscription?.subscription?.status || "").toLowerCase();
  const corePaymentProvider = String(subscription?.subscription?.payment_provider || "").toLowerCase();
  const hasActiveCoreGcSub =
    (coreSubStatus === "active" || coreSubStatus === "trial") && corePaymentProvider === "gocardless";
  const hasActiveCorePlan =
    Boolean(currentCorePlanId) &&
    (coreSubStatus === "active" ||
      coreSubStatus === "trial" ||
      coreSubStatus === "pending_first_payment" ||
      (currentPlan ? isPaygPlan(currentPlan as PlanRow) : false));
  const effectiveCorePlanId = hasActiveCorePlan ? currentCorePlanId : null;
  const effectiveCurrentPlan = hasActiveCorePlan ? currentPlan : null;
  const staleCorePlanOnSession = Boolean(currentCorePlanId && !hasActiveCorePlan);
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
  const waPkgFee = Number(services.wa_survey_package_fee_pence || services.whatsapp_survey_fee_pence || 50);
  const waExtraDisplay = String(services.wa_survey_extra_display || services.whatsapp_survey_display || "£0.49");
  const atsFee = Number(services.ats_cv_scan_fee_pence || 75);
  const paygPerMin = Number(services.interview_per_min_pence || 35);

  const breakdown = React.useMemo(() => {
    const avgDuration = Number(settings.estimator_default_duration_min || duration || 12);
    const perInterview = connPence + paygPerMin * avgDuration;
    const credit = topupPence;
    return {
      interviews: perInterview > 0 ? Math.floor(credit / perInterview) : 0,
      wa: waPkgFee > 0 ? Math.floor(credit / waPkgFee) : 0,
      cv: atsFee > 0 ? Math.floor(credit / atsFee) : 0,
    };
  }, [topupPence, connPence, paygPerMin, waPkgFee, atsFee, settings.estimator_default_duration_min, duration]);

  const invalidateBilling = React.useCallback(async () => {
    await Promise.all([
      refetchSession(),
      qc.invalidateQueries({ queryKey: ["billing", "pricing"] }),
      qc.invalidateQueries({ queryKey: queryKeys.billingWallet }),
      qc.invalidateQueries({ queryKey: queryKeys.billingAccess }),
      qc.invalidateQueries({ queryKey: queryKeys.billingUsage }),
    ]);
  }, [qc, refetchSession]);

  const onSubscribe = async (plan: PlanRow) => {
    if (plan.is_enterprise) return;
    if (hasActiveCorePlan && isSamePlan(plan, effectiveCurrentPlan, plans, effectiveCorePlanId)) return;
    if (pendingCorePlanId && String(plan.id) === String(pendingCorePlanId)) return;
    if (isPaygPlan(plan)) {
      setBusyPlanId(String(plan.id));
      try {
        await apiFetch("/billing/subscription/pay-as-you-go", { method: "POST", body: "{}" });
        toast.success("Switched to Pay as you go — top up your wallet when you're ready.");
        await invalidateBilling();
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Could not switch plan");
      } finally {
        setBusyPlanId(null);
      }
      return;
    }
    if (!gcReady) {
      toast.error("GoCardless checkout is not configured. Enable it in admin integrations.");
      return;
    }
    setBusyPlanId(String(plan.id));
    try {
      if (hasActiveCoreGcSub) {
        const result = await changeCorePlan(String(plan.id));
        const planName = String(result.plan?.name || plan.name || "plan");
        toast.success(
          planChangeToast(result.direction, planName, { awaitingAdmin: result.awaiting_admin_approval }),
        );
        setBusyPlanId(null);
        await invalidateBilling();
        return;
      }
      await startGoCardlessSubscription(String(plan.id));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not start checkout");
      setBusyPlanId(null);
    }
  };

  const openEnterpriseContact = () => {
    setEnterpriseScreenings("");
    setEnterpriseWaSurveys("");
    setEnterpriseNotes("");
    setEnterpriseOpen(true);
  };

  const submitEnterpriseContact = async () => {
    const screenings = enterpriseScreenings.trim();
    const waSurveys = enterpriseWaSurveys.trim();
    if (!screenings && !waSurveys) {
      toast.error("Enter expected AI screenings or WA surveys per month");
      return;
    }
    const message = [
      "Enterprise plan enquiry",
      screenings ? `AI screenings per month: ${screenings}` : null,
      waSurveys ? `WA surveys expected per month: ${waSurveys}` : null,
      enterpriseNotes.trim() ? `Notes: ${enterpriseNotes.trim()}` : null,
    ]
      .filter(Boolean)
      .join("\n");
    try {
      await createTicketM.mutateAsync({
        category: "Billing",
        subject: "Enterprise plan enquiry",
        message,
        priority: "normal",
      });
      setEnterpriseOpen(false);
      toast.success("Enquiry sent — our team will reply via support tickets.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not send enquiry");
    }
  };

  const walletBalance = walletQ.data?.wallet_balance_gbp || walletQ.data?.wallet_balance_display || "—";
  const feedbackPackages = (feedbackPackagesQ.data || []).slice().sort((a, b) => (a.display_order || 0) - (b.display_order || 0));
  const feedbackSub = feedbackSubQ.data;
  const orgCurrency = String(orgQ.data?.billing_currency || orgQ.data?.currency || "GBP").toUpperCase();
  const currentFeedbackPlanId = feedbackSub?.active ? feedbackSub.plan_id : null;
  const hasActiveFeedbackSub = Boolean(feedbackSub?.active && currentFeedbackPlanId);

  React.useEffect(() => {
    if (tabFromUrl) {
      setPackagesTab(tabFromUrl);
      return;
    }
    if (feedbackSubQ.isLoading || pricingQ.isLoading) return;
    if (hasActiveFeedbackSub && !hasActiveCorePlan) {
      setPackagesTab("feedback");
    }
  }, [tabFromUrl, feedbackSubQ.isLoading, pricingQ.isLoading, hasActiveFeedbackSub, hasActiveCorePlan]);

  const formatFeedbackPrice = (pkg: FeedbackPackage) => {
    const prices = pkg.prices || [];
    const match = prices.find((p) => p.currency.toUpperCase() === orgCurrency) || prices[0];
    if (!match) return "—";
    const sym = CURRENCY_SYMBOL[match.currency.toUpperCase()] || `${match.currency} `;
    return `${sym}${(match.monthly_price_minor / 100).toFixed(0)}/mo`;
  };

  const onFeedbackSubscribe = async (pkg: FeedbackPackage) => {
    if (!pkg.plan_id || currentFeedbackPlanId === pkg.plan_id) return;
    setBusyFeedbackPlanId(pkg.plan_id);
    try {
      if (feedbackSub?.active) {
        const result = await changeFeedbackPlan(pkg.plan_id);
        const planName = pkg.plan_name || pkg.plan_code || "plan";
        toast.success(planChangeToast(result.direction, planName));
        setBusyFeedbackPlanId(null);
        await Promise.all([
          qc.invalidateQueries({ queryKey: queryKeys.feedbackSubscription }),
          qc.invalidateQueries({ queryKey: queryKeys.feedbackPackages }),
        ]);
        return;
      }
      await startFeedbackGoCardlessSubscription(pkg.plan_id);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not update feedback plan");
      setBusyFeedbackPlanId(null);
    }
  };

  const campaignPackPrice = (sends: number) => {
    const perMsg = sends >= 25000 ? 0.03 : sends >= 5000 ? 0.036 : 0.04;
    const total = (sends * perMsg).toFixed(0);
    return { total: `${sym(data)}${total}`, per: `${sym(data)}${perMsg.toFixed(3)} / msg` };
  };

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-8 pb-16">
      <PageHeader
        eyebrow="Account"
        title="Packages & pricing"
        description="Each service is billed separately — pick a tab to see its plans."
        actions={
          walletQ.data ? (
            <button
              type="button"
              className="inline-flex items-center gap-2 rounded-full border border-border bg-muted/40 px-3 py-1.5 text-sm"
              onClick={() => setTopupOpen(true)}
            >
              <Wallet className="size-4 text-primary" />
              <span className="text-muted-foreground">Wallet</span>
              <span className="font-semibold tabular-nums">{walletBalance}</span>
            </button>
          ) : null
        }
      />

      <Tabs value={packagesTab} onValueChange={(v) => setPackagesTab(v as ServiceTab)} className="w-full">
        <TabsList className="grid h-auto w-full grid-cols-3 gap-1 p-1">
          {(Object.keys(SERVICE_TABS) as ServiceTab[]).map((key) => {
            const s = SERVICE_TABS[key];
            const Icon = s.icon;
            return (
              <TabsTrigger key={key} value={key} className="flex flex-col items-center gap-1 py-2 data-[state=active]:shadow-sm">
                <Icon className={`size-4 ${s.tint}`} />
                <span className="text-[11px] font-medium">{s.label}</span>
                {key === "feedback" && hasActiveFeedbackSub ? (
                  <Badge variant="secondary" className="mt-0.5 h-4 px-1.5 text-[9px] font-semibold uppercase tracking-wide">
                    Active
                  </Badge>
                ) : null}
                {key === "core" && hasActiveCorePlan ? (
                  <Badge variant="secondary" className="mt-0.5 h-4 px-1.5 text-[9px] font-semibold uppercase tracking-wide">
                    Active
                  </Badge>
                ) : null}
              </TabsTrigger>
            );
          })}
        </TabsList>

        {(Object.keys(SERVICE_TABS) as ServiceTab[]).map((key) => {
          const s = SERVICE_TABS[key];
          const Icon = s.icon;
          return (
            <TabsContent key={key} value={key} className="mt-4 space-y-6">
              <div className={`rounded-2xl border border-border bg-gradient-to-br ${s.bg} to-transparent p-4 ring-1 ${s.ring}`}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-3">
                    <div className={`grid size-10 place-items-center rounded-xl bg-background shadow-sm ${s.tint}`}>
                      <Icon className="size-5" />
                    </div>
                    <div>
                      <p className="text-base font-semibold">{s.label}</p>
                      <p className="text-xs text-muted-foreground">{s.blurb}</p>
                    </div>
                  </div>
                  <Badge variant="outline" className={`${s.chip} border-transparent`}>{s.billing}</Badge>
                  {key === "feedback" && feedbackSub?.active ? (
                    <Badge className="bg-success text-success-foreground hover:bg-success">
                      Active · {feedbackSub.plan_name || "Customer feedback"}
                    </Badge>
                  ) : null}
                  {key === "feedback" && !feedbackSub?.active && !feedbackSubQ.isLoading ? (
                    <Badge variant="outline">No subscription</Badge>
                  ) : null}
                </div>

                {key === "core" ? (
                  <SubscriptionSummaryBar
                    title="Core subscription"
                    finance={(subsSummaryQ.data?.core || null) as Parameters<typeof SubscriptionSummaryBar>[0]["finance"]}
                    loading={subsSummaryQ.isLoading}
                    emptyMessage="No active Core platform subscription."
                    tintClass="mt-4 border-primary/20 bg-primary/5"
                  />
                ) : null}
                {key === "feedback" ? (
                  <SubscriptionSummaryBar
                    title="Customer Feedback subscription"
                    finance={
                      (feedbackSubQ.data?.finance ||
                        subsSummaryQ.data?.feedback ||
                        null) as Parameters<typeof SubscriptionSummaryBar>[0]["finance"]
                    }
                    loading={feedbackSubQ.isLoading || subsSummaryQ.isLoading}
                    emptyMessage="No active Customer Feedback subscription."
                    tintClass="mt-4 border-success/20 bg-success/5"
                  />
                ) : null}
                {key === "campaigns" ? (
                  <SubscriptionSummaryBar
                    title="Campaign credits"
                    finance={
                      walletQ.data?.balance_display
                        ? {
                            plan_name: "Campaign credit wallet",
                            status: "active",
                            amount_next_payment_display: String(walletQ.data.balance_display),
                            next_billing_date: null,
                          }
                        : null
                    }
                    loading={walletQ.isLoading}
                    emptyMessage="Top up campaign credits when you need WhatsApp broadcast sends."
                    tintClass="mt-4 border-amber-500/20 bg-amber-500/5"
                  />
                ) : null}

                <div className="mt-5 space-y-6">
                  {key === "core" ? (
                    <>
      {hasActiveFeedbackSub && !hasActiveCorePlan ? (
        <div className="rounded-lg border border-success/30 bg-success/5 px-4 py-3 text-sm">
          <p className="font-medium text-foreground">Your Customer Feedback subscription is active</p>
          <p className="mt-1 text-muted-foreground">
            Core platform is a separate product (AI interviews + outbound surveys). You do not need to pick a Core plan unless you want those features —{" "}
            <button
              type="button"
              className="text-primary underline-offset-4 hover:underline"
              onClick={() => setPackagesTab("feedback")}
            >
              manage your Feedback plan
            </button>
            .
          </p>
        </div>
      ) : null}

      {staleCorePlanOnSession ? (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-sm">
          <p className="font-medium text-foreground">No active Core platform subscription</p>
          <p className="mt-1 text-muted-foreground">
            Your previous Core subscription is not active. Choose a plan below to subscribe or switch to Pay as you go.
          </p>
        </div>
      ) : null}

      <div className="rounded-lg border border-border bg-background/60 px-4 py-3 text-sm">
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

      <WalletTopupDialog open={topupOpen} onOpenChange={setTopupOpen} initialAmountMinor={topupPence} />

      <p className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
        <span className="inline-flex items-center gap-1"><ClipboardList className="size-3.5" /> Surveys</span>
        <span>+</span>
        <span className="inline-flex items-center gap-1"><Briefcase className="size-3.5" /> Interviews</span>
        <span className="text-foreground">included in every plan</span>
      </p>

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
              const isCurrent =
                hasActiveCorePlan && isSamePlan(p, effectiveCurrentPlan, plans, effectiveCorePlanId);
              const isFeatured = Boolean(p.is_featured);
              const payg = isPaygPlan(p);
              const isPendingDowngrade = Boolean(pendingCorePlanId && String(p.id) === String(pendingCorePlanId));
              const btnLabel = planButtonLabel(p, effectiveCurrentPlan, {
                busy: busyPlanId === String(p.id),
                plans,
                currentPlanId: effectiveCorePlanId,
                pendingPlanId: pendingCorePlanId,
              });
              return (
                <div key={String(p.id)} className="relative flex pt-3">
                  {isFeatured && (
                    <span className="absolute left-1/2 top-0 z-10 -translate-x-1/2 rounded-full bg-primary px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-primary-foreground shadow">
                      Most popular
                    </span>
                  )}
                  <Card className={`flex h-full w-full flex-col ${isFeatured ? "border-primary shadow-md" : ""} ${isCurrent ? "ring-2 ring-primary/30" : ""}`}>
                    <CardHeader className="pb-2 pt-5">
                      <Badge variant="outline" className="mb-2 w-fit border-primary/40 text-primary">Core platform</Badge>
                      <CardTitle className="text-base">{String(p.name)}</CardTitle>
                      <CardDescription className="text-xl font-semibold text-foreground">
                        {ent ? "Let's talk" : payg ? "No monthly fee" : `${String(p.price_display || p.price_display_pence)}/mo`}
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="flex flex-1 flex-col space-y-2 text-xs">
                      {!ent && (
                        <>
                          <p>Cost per min: <strong>{String(p.per_min_display)}</strong></p>
                          {payg ? (
                            <p className="text-muted-foreground">Use wallet top-ups — pay only for what you use.</p>
                          ) : (
                            <p className="text-muted-foreground">Extra min (after package): <strong>{String(p.extra_per_min_display || p.per_min_display)}</strong></p>
                          )}
                          {connEnabled && <p className="text-muted-foreground">{String(services.connection_fee_label)}: {String(services.connection_fee_display)}</p>}
                          <p className="text-muted-foreground">Typical interview<br />{sym(data)}{low.toFixed(2)} – {sym(data)}{high.toFixed(2)} per call</p>
                        </>
                      )}
                      <div className="mt-auto space-y-1 border-t border-border pt-2">
                        <div className="flex justify-between"><span className="text-muted-foreground">Mins included</span><span>{ent ? "Custom" : payg ? "Pay per use" : Number(p.minutes_included || 0).toLocaleString()}</span></div>
                        {!ent && !payg ? (
                          <p className="text-muted-foreground">
                            Plan includes: <strong>{Number(p.whatsapp_included || 0).toLocaleString()}</strong> WA survey recipients/month.
                          </p>
                        ) : (
                          <div className="flex justify-between"><span className="text-muted-foreground">WA survey recipients</span><span>{ent ? "Custom" : "Pay per use"}</span></div>
                        )}
                        <div className="flex justify-between"><span className="text-muted-foreground">CV scans</span><span>{ent ? "Custom" : payg ? "Pay per use" : Number(p.cv_scans_included || 0).toLocaleString()}</span></div>
                      </div>
                      <Button
                        className="mt-3 w-full"
                        variant={isFeatured && !isCurrent ? "default" : "outline"}
                        disabled={isCurrent || isPendingDowngrade || Boolean(busyPlanId)}
                        onClick={() => (ent ? openEnterpriseContact() : void onSubscribe(p))}
                      >
                        {ent ? "Let's talk" : btnLabel}
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
                  <button
                    key={String(p.id)}
                    type="button"
                    className="rounded-lg bg-muted/50 p-3 text-center transition hover:bg-muted"
                    onClick={openEnterpriseContact}
                  >
                    <p className="text-[11px] text-muted-foreground">{String(p.name)}</p>
                    <p className="mt-1 text-sm font-medium text-primary">Let's talk</p>
                  </button>
                );
              }
              const perMin = Number(p.per_min_pence || 0);
              const { perCall, total } = interviewCost(perMin, duration, connEnabled ? connPence : 0, interviewCount);
              return (
                <div key={String(p.id)} className="rounded-lg bg-muted/50 p-3 text-center">
                  <p className="text-[11px] text-muted-foreground">{String(p.name)}</p>
                  <p className="text-base font-semibold">{sym(data)}{(total / 100).toFixed(2)}</p>
                  <p className="text-[10px] text-muted-foreground">{sym(data)}{(perCall / 100).toFixed(2)}/call</p>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <section>
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">What each service costs</h2>
        <div className="mb-4 space-y-1 rounded-lg border border-border bg-muted/20 px-4 py-3 text-sm">
          <p>Extra recipients: <strong>{waExtraDisplay}</strong> each after allowance is used.</p>
          <p>Interview WhatsApp: <strong>included</strong>.</p>
          <p>AI phone survey: <strong>billed by connection + minutes</strong>.</p>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <Card><CardContent className="p-4"><div className="mb-2 flex items-center gap-2"><Phone className="size-4 text-primary" /><span className="font-medium">Interview call</span></div><p className="text-xl font-semibold">{String(services.interview_per_min_display)}/min</p>{connEnabled && <p className="text-xs text-muted-foreground">+ {String(services.connection_fee_display)} connection fee per call</p>}</CardContent></Card>
          <Card><CardContent className="p-4"><div className="mb-2 flex items-center gap-2"><MessageCircle className="size-4 text-green-600" /><span className="font-medium">WA survey allowance</span></div><p className="text-xl font-semibold">{String(services.wa_survey_package_fee_display || services.whatsapp_survey_display)}</p><p className="text-xs text-muted-foreground">Package fee used to calculate plan recipients/month</p></CardContent></Card>
          <Card><CardContent className="p-4"><div className="mb-2 flex items-center gap-2"><MessageCircle className="size-4 text-green-600" /><span className="font-medium">WA survey extra</span></div><p className="text-xl font-semibold">{waExtraDisplay}</p><p className="text-xs text-muted-foreground">Each recipient after allowance is used</p></CardContent></Card>
          <Card><CardContent className="p-4"><div className="mb-2 flex items-center gap-2"><FileText className="size-4 text-amber-600" /><span className="font-medium">ATS CV scan</span></div><p className="text-xl font-semibold">{String(services.ats_cv_scan_display)}</p><p className="text-xs text-muted-foreground">Per CV screened · Interview WhatsApp included</p></CardContent></Card>
        </div>
      </section>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-center gap-2">
            <Wallet className="size-5 text-green-600" />
            <div>
              <CardTitle>Wallet top-up</CardTitle>
              <CardDescription>Pay by card (Stripe or Airwallex) — no expiry, use across calls, surveys and CV scans (min {sym(data)}5)</CardDescription>
            </div>
            </div>
            {walletQ.data ? (
              <div className="rounded-lg border border-border bg-muted/30 px-4 py-2 text-right">
                <p className="text-xs text-muted-foreground">Current balance</p>
                <p className="text-2xl font-semibold tabular-nums">{walletBalance}</p>
              </div>
            ) : null}
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {tiers.map((t) => (
              <Button key={String(t.id)} variant="outline" size="sm" onClick={() => { const v = Number(t.total_credit_pence || 0); setTopupPence(v); setCustomTopup(String(v / 100)); setTopupOpen(true); }}>
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
            <Button onClick={() => setTopupOpen(true)}>Top up by card</Button>
          </div>
          <Slider value={[topupPence / 100]} min={5} max={500} step={5} onValueChange={([v]) => { setTopupPence(Math.round(v * 100)); setCustomTopup(String(v)); }} />
          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="rounded-lg bg-muted/50 p-3"><p className="text-[11px] text-muted-foreground">Est. interviews</p><p className="font-semibold">~{breakdown.interviews}</p></div>
            <div className="rounded-lg bg-muted/50 p-3"><p className="text-[11px] text-muted-foreground">Est. WA survey recipients</p><p className="font-semibold">{breakdown.wa}</p></div>
            <div className="rounded-lg bg-muted/50 p-3"><p className="text-[11px] text-muted-foreground">CV scans</p><p className="font-semibold">{breakdown.cv}</p></div>
          </div>
        </CardContent>
      </Card>
                    </>
                  ) : null}

                  {key === "feedback" ? (
                    <>
                      {feedbackPackagesQ.isLoading ? (
                        <div className="grid gap-3 md:grid-cols-3">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-56" />)}</div>
                      ) : feedbackPackages.length === 0 ? (
                        <p className="text-sm text-muted-foreground">
                          No feedback plans in your market yet.{" "}
                          <Link to="/account/feedback/packages" className="text-primary underline-offset-4 hover:underline">Open feedback plans</Link>
                        </p>
                      ) : (
                        <div className="grid gap-3 md:grid-cols-3">
                          {feedbackPackages.map((pkg) => {
                            const featured = Boolean(pkg.is_featured);
                            const isCurrent = currentFeedbackPlanId === pkg.plan_id;
                            const fbBtnLabel = feedbackPlanButtonLabel(pkg, feedbackPackages, {
                              busy: busyFeedbackPlanId === pkg.plan_id,
                              currentPlanId: currentFeedbackPlanId,
                            });
                            return (
                              <Card key={pkg.id} className={featured ? "border-success shadow-md" : ""}>
                                <CardHeader className="pb-2">
                                  <div className="flex items-center justify-between gap-2">
                                    <Badge variant="outline" className="border-success/40 text-success">Customer Feedback</Badge>
                                    {featured ? <Badge className="bg-success text-success-foreground hover:bg-success">Best value</Badge> : null}
                                  </div>
                                  <CardTitle className="text-base pt-1">{pkg.plan_name || pkg.plan_code || "Feedback plan"}</CardTitle>
                                  <CardDescription>
                                    <span className="text-2xl font-semibold tracking-tight text-foreground">{formatFeedbackPrice(pkg)}</span>
                                  </CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-2 text-sm">
                                  <p className="flex items-center gap-2"><Check className="size-4 text-success" /> {pkg.wa_units_included.toLocaleString()} responses / month</p>
                                  <p className="flex items-center gap-2"><Check className="size-4 text-success" /> {pkg.max_locations} location{pkg.max_locations === 1 ? "" : "s"} & QR codes</p>
                                  {(pkg.features || []).slice(0, 2).map((f) => (
                                    <p key={f} className="flex items-center gap-2"><Check className="size-4 text-success" /> {f}</p>
                                  ))}
                                  <Button
                                    className="mt-3 w-full"
                                    variant={featured && !isCurrent ? "default" : "outline"}
                                    disabled={isCurrent || busyFeedbackPlanId === pkg.plan_id}
                                    onClick={() => void onFeedbackSubscribe(pkg)}
                                  >
                                    {isCurrent ? "Current plan" : busyFeedbackPlanId === pkg.plan_id ? <Loader2 className="size-4 animate-spin" /> : fbBtnLabel}
                                  </Button>
                                </CardContent>
                              </Card>
                            );
                          })}
                        </div>
                      )}
                      <p className="text-xs text-muted-foreground">
                        Subscription only — no top-ups.{" "}
                        <Link to="/account/feedback/packages" className="text-primary underline-offset-4 hover:underline">Manage feedback subscription</Link>
                      </p>
                    </>
                  ) : null}

                  {key === "campaigns" ? (
                    <>
                      <div className="grid gap-3 sm:grid-cols-3">
                        {CAMPAIGN_CREDIT_PACKS.map((pack) => {
                          const price = campaignPackPrice(pack.sends);
                          return (
                            <Card key={pack.name} className={pack.featured ? "border-amber-500 shadow-md" : ""}>
                              <CardContent className="p-4">
                                <div className="flex items-center justify-between">
                                  <p className="text-sm font-medium">{pack.name}</p>
                                  {pack.featured ? <Badge className="bg-amber-500 text-white hover:bg-amber-500">Popular</Badge> : null}
                                </div>
                                <p className="mt-1 text-2xl font-semibold text-amber-600 dark:text-amber-500">{price.total}</p>
                                <p className="text-xs text-muted-foreground">{pack.sends.toLocaleString()} WhatsApp template sends</p>
                                <p className="mt-1 text-[11px] font-medium text-amber-600 dark:text-amber-500">{price.per}</p>
                                <Button
                                  size="sm"
                                  className="mt-3 w-full"
                                  variant={pack.featured ? "default" : "outline"}
                                  onClick={() => toast.info("Campaign credit packs will be available shortly.")}
                                >
                                  Top up
                                </Button>
                              </CardContent>
                            </Card>
                          );
                        })}
                      </div>
                      <p className="text-xs text-muted-foreground">Pure top-up — credits never expire.</p>
                    </>
                  ) : null}
                </div>
              </div>
            </TabsContent>
          );
        })}
      </Tabs>

      <Dialog open={enterpriseOpen} onOpenChange={setEnterpriseOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Enterprise plan enquiry</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label className="text-xs">AI screenings per month</Label>
              <Input
                type="number"
                min={0}
                placeholder="e.g. 500"
                value={enterpriseScreenings}
                onChange={(e) => setEnterpriseScreenings(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">WA surveys expected per month</Label>
              <Input
                type="number"
                min={0}
                placeholder="e.g. 2000"
                value={enterpriseWaSurveys}
                onChange={(e) => setEnterpriseWaSurveys(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Team size / notes</Label>
              <Textarea
                rows={4}
                placeholder="Team size, industries, timeline, anything else we should know…"
                value={enterpriseNotes}
                onChange={(e) => setEnterpriseNotes(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEnterpriseOpen(false)} disabled={createTicketM.isPending}>
              Cancel
            </Button>
            <Button onClick={() => void submitEnterpriseContact()} disabled={createTicketM.isPending}>
              {createTicketM.isPending ? "Sending…" : "Send enquiry"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
