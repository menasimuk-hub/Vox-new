import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { ArrowRight, Check, Clock, FileText, MessageCircle, PhoneCall, Wallet } from "lucide-react";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import {
  BottomCTA, PLANS, WA_GBP, CV_GBP, fmt, SliderRow, ServiceCard, TopupCell,
  BillingToggle, type Billing,
} from "@/components/VOXBULKHome";
import { useCurrency, SYM, FX, MARKETS } from "@/components/CurrencyContext";
import { usePublicFeedbackPricing, usePublicPricing, usePublicExpoPricing, type PublicFeedbackPlan, type PublicPlan, type PublicExpoPlan } from "@/hooks/usePricing";
import { fetchSeoSettings } from "@/lib/seo";
import { pageMeta } from "@/lib/seo-defaults";
import { isPricingKindEnabled, useProductVisibility } from "@/lib/product-visibility";

export const Route = createFileRoute("/pricing")({
  validateSearch: (search: Record<string, unknown>) => ({
    plan: typeof search.plan === "string" && search.plan.trim() ? search.plan.trim() : undefined,
    product:
      search.product === "feedback" || search.product === "expo"
        ? (search.product as "feedback" | "expo")
        : undefined,
  }),
  loader: async () => ({ settings: await fetchSeoSettings() }),
  head: ({ loaderData }) => ({
    meta: pageMeta("pricing", { override: loaderData?.settings?.marketing_pages?.pricing }),
    links: [{ rel: "canonical", href: "https://voxbulk.com/pricing" }],
  }),
  component: PricingPage,
});

// WhatsApp Surveys + AI Interview Screening share one combined plan (see PLANS).

type FeedbackPlan = {
  code: string;
  name: string;
  description?: string | null;
  price: number;
  featured?: boolean;
  waSurveys: number | "Unlimited";
  webSurveys: number | "Unlimited";
  extraFeatures: string[];
};

const FALLBACK_FEEDBACK: FeedbackPlan[] = [
  { code: "feedback_starter_gb", name: "Starter", price: 49, waSurveys: 200, webSurveys: 100, extraFeatures: ["1 location", "Monthly report", "Email support"] },
  { code: "feedback_growth_gb", name: "Growth", price: 99, featured: true, waSurveys: 600, webSurveys: 300, extraFeatures: ["3 locations", "Weekly report", "Live dashboard", "Priority support"] },
  { code: "feedback_pro_gb", name: "Pro", price: 199, waSurveys: "Unlimited", webSurveys: "Unlimited", extraFeatures: ["10 locations", "Real-time dashboard", "Branded PDF report", "Dedicated AM"] },
];

type ExpoPlanView = {
  code: string;
  name: string;
  durationDays: number;
  price: number;
  featured?: boolean;
  features: string[];
};

const FALLBACK_EXPO: ExpoPlanView[] = [
  {
    code: "expo_day1",
    name: "Expo 1 Day",
    durationDays: 1,
    price: 49,
    features: [
      "Booth active 1 day",
      "1 product category",
      "Up to 20 files",
      "Hot / Warm / Cold scoring",
      "CSV & Excel export",
    ],
  },
  {
    code: "expo_day3",
    name: "Expo 3 Days",
    durationDays: 3,
    price: 99,
    featured: true,
    features: [
      "Booth active 3 days",
      "Up to 3 categories",
      "Up to 40 files",
      "Hot / Warm / Cold scoring",
      "CSV & Excel export",
    ],
  },
  {
    code: "expo_day7",
    name: "Expo 7 Days",
    durationDays: 7,
    price: 149,
    features: [
      "Booth active 7 days",
      "Unlimited categories",
      "Up to 100 files",
      "Post-show follow-up ready",
      "AI summary report ready",
    ],
  },
];

function mapExpoPlan(p: PublicExpoPlan): ExpoPlanView {
  const price =
    p.price_minor != null
      ? p.price_minor / 100
      : Number.parseFloat(String(p.price_display || "").replace(/[^\d.]/g, "")) || 0;
  const days = Math.max(1, Number(p.duration_days) || 1);
  const shortName =
    /1\s*day/i.test(p.name) ? "Expo 1 Day" : /3\s*day/i.test(p.name) ? "Expo 3 Days" : /7\s*day/i.test(p.name) ? "Expo 7 Days" : p.name;
  return {
    code: p.code,
    name: shortName,
    durationDays: days,
    price,
    featured: Boolean(p.is_featured),
    features: p.features?.length ? p.features : [`Booth active for ${days} day${days === 1 ? "" : "s"}`],
  };
}

const FALLBACK_NAME_TO_CODE: Record<string, string> = {
  "Pay as you go": "payg",
  Starter: "starter",
  Pro: "pro",
  Business: "business",
  Enterprise: "enterprise",
};

type CorePlanView = {
  code: string;
  name: string;
  description?: string | null;
  priceGBP: number | null;
  ratePerMinGBP: number | null;
  mins: number | null;
  wa: number | "Unlimited" | "Pay/use";
  cv: number | "Unlimited" | "Pay/use";
  badge?: string;
  enterprise?: boolean;
  payg?: boolean;
};

function mapCorePlan(p: PublicPlan): CorePlanView {
  const monthlyMajor =
    p.monthly_price_minor != null ? p.monthly_price_minor / 100 : Number.parseFloat(p.price_display.replace(/[^\d.]/g, "")) || 0;
  const perMinMajor = p.per_min_minor != null ? p.per_min_minor / 100 : Number.parseFloat(p.per_min_display.replace(/[^\d.]/g, "")) || 0;
  return {
    code: p.code,
    name: p.name,
    description: p.description || null,
    priceGBP: p.is_enterprise ? null : p.is_payg ? 0 : monthlyMajor,
    ratePerMinGBP: p.is_enterprise ? null : perMinMajor,
    mins: p.is_enterprise ? null : p.is_payg ? null : p.minutes_included,
    wa: p.is_enterprise ? "Unlimited" : p.is_payg ? "Pay/use" : p.whatsapp_included,
    cv: p.is_enterprise ? "Unlimited" : p.is_payg ? "Pay/use" : p.cv_scans_included,
    badge: p.is_featured ? "Most popular" : p.is_payg ? "No commitment" : p.is_enterprise ? "Custom pricing" : undefined,
    payg: p.is_payg,
    enterprise: p.is_enterprise,
  };
}

function fallbackCorePlans(): CorePlanView[] {
  return PLANS.map((p) => ({ ...p, code: FALLBACK_NAME_TO_CODE[p.name] || p.name.toLowerCase().replace(/\s+/g, "_") }));
}

function mapFeedbackPlan(p: PublicFeedbackPlan): FeedbackPlan {
  const wa = p.wa_units_included ?? 0;
  const web = p.web_units_included ?? 0;
  const price =
    p.monthly_price_minor != null
      ? p.monthly_price_minor / 100
      : Number.parseFloat(String(p.monthly_price_display || "").replace(/[^\d.]/g, "")) || 0;
  const extras = (p.features || []).filter(
    (f) => !/whatsapp surveys|web surveys|location/i.test(f),
  );
  return {
    code: p.code,
    name: p.name,
    description: p.description || null,
    price,
    featured: p.is_featured,
    waSurveys: wa,
    webSurveys: web,
    extraFeatures: extras.length ? extras : [`${p.max_locations || 1} location(s)`],
  };
}

function feedbackPriceMinor(p: FeedbackPlan, billing: Billing, apiPlan?: PublicFeedbackPlan | null) {
  const yearly =
    apiPlan?.yearly_price_minor != null && apiPlan.yearly_price_minor > 0
      ? apiPlan.yearly_price_minor
      : apiPlan?.monthly_price_minor != null && apiPlan.monthly_price_minor > 0
        ? apiPlan.monthly_price_minor * 10
        : null;
  if (billing === "yearly" && yearly != null) return yearly;
  if (apiPlan?.monthly_price_minor != null) {
    return billing === "yearly" ? apiPlan.monthly_price_minor * 10 : apiPlan.monthly_price_minor;
  }
  return Math.round(p.price * (billing === "yearly" ? 10 : 1) * 100);
}

function corePriceMinor(p: CorePlanView, billing: Billing, apiPlan?: PublicPlan | null) {
  const yearly =
    apiPlan?.yearly_price_minor != null && apiPlan.yearly_price_minor > 0
      ? apiPlan.yearly_price_minor
      : apiPlan?.monthly_price_minor != null && apiPlan.monthly_price_minor > 0
        ? apiPlan.monthly_price_minor * 10
        : null;
  if (billing === "yearly" && yearly != null) return yearly;
  if (apiPlan?.monthly_price_minor != null) {
    return billing === "yearly" ? apiPlan.monthly_price_minor * 10 : apiPlan.monthly_price_minor;
  }
  if (p.priceGBP == null) return null;
  return Math.round(p.priceGBP * (billing === "yearly" ? 10 : 1) * 100);
}

function fmtSurveyCount(n: number | "Unlimited") {
  return n === "Unlimited" ? "Unlimited" : n.toLocaleString();
}

function feedbackPlanFeatures(p: FeedbackPlan, apiPlan?: PublicFeedbackPlan | null): string[] {
  if (apiPlan?.features?.length) return apiPlan.features;
  const web = p.webSurveys;
  if (typeof web === "number" && web < 0) {
    return [
      `${fmtSurveyCount(p.waSurveys)} surveys/mo (WhatsApp or web)`,
      "Voice-note transcription included",
      ...p.extraFeatures,
    ];
  }
  if (web === 0) {
    return [
      `${fmtSurveyCount(p.waSurveys)} WhatsApp surveys/mo`,
      "Voice-note transcription included",
      ...p.extraFeatures,
    ];
  }
  return [
    `${fmtSurveyCount(p.waSurveys)} WhatsApp surveys/mo`,
    `${fmtSurveyCount(web)} Web surveys/mo`,
    "Voice-note transcription included",
    ...p.extraFeatures,
  ];
}

function corePlanFeatureLines(p: CorePlanView, apiPlan?: PublicPlan | null): string[] {
  if (apiPlan?.features?.length) return apiPlan.features;
  if (p.enterprise) {
    return ["Custom minutes & allowances", "Volume rates · SLA", "Dedicated support"];
  }
  if (p.payg) {
    return [
      "No monthly fee",
      "Pay per minute for interview calls",
      "Pay per WhatsApp survey sent",
      "Pay per CV scan",
      "Wallet top-up credits — no expiry",
    ];
  }
  const waV = typeof p.wa === "number" ? p.wa.toLocaleString() : String(p.wa);
  const cvV = typeof p.cv === "number" ? p.cv.toLocaleString() : String(p.cv);
  const minsV = p.mins == null ? "0" : p.mins.toLocaleString();
  return [
    `${minsV} minutes included`,
    `${waV} WhatsApp survey recipients/mo`,
    `${cvV} CV scans/mo`,
  ];
}

// $5 USD per seat / month, converted from the GBP base used across the site.
const SMART_SEAT_GBP = 5 / FX.usd;
const smartSeat = (fx: number) => Math.max(4, Math.round(SMART_SEAT_GBP * fx));

function SimplePlanCard({
  p,
  s,
  billing,
  highlight,
  apiPlan,
}: {
  p: FeedbackPlan;
  s: string;
  billing: Billing;
  highlight?: boolean;
  apiPlan?: PublicFeedbackPlan | null;
}) {
  const minor = feedbackPriceMinor(p, billing, apiPlan);
  const displayPrice = minor != null ? (minor / 100).toFixed(0) : "—";
  const period = billing === "yearly" ? "/yr" : "/mo";
  const features = feedbackPlanFeatures(p, apiPlan);
  return (
    <div
      id={`pricing-feedback-${p.code}`}
      className={`relative rounded-2xl p-6 flex flex-col transition-shadow ${highlight ? "ring-2 ring-gold shadow-elevated" : ""} ${p.featured ? "bg-navy text-white border-2 border-gold shadow-elevated" : "bg-white border border-border shadow-elegant"}`}
    >
      {p.featured && <span className="absolute -top-3 left-5 text-[10.5px] font-bold uppercase tracking-[0.14em] px-2.5 py-1 rounded-full bg-gold text-navy">Most popular</span>}
      <div className={`text-[14px] font-semibold ${p.featured ? "text-white/90" : "text-heading"}`}>{p.name}</div>
      <div className="mt-3 flex items-baseline gap-1">
        <span className={`text-[30px] font-bold tracking-[-0.02em] ${p.featured ? "text-gold" : "text-heading"}`}>{s}{displayPrice}</span>
        <span className={`text-[13px] ${p.featured ? "text-white/60" : "text-muted-text"}`}>{period}</span>
      </div>
      {(apiPlan?.description || p.description) ? (
        <p className={`mt-1.5 text-[12.5px] leading-snug ${p.featured ? "text-white/65" : "text-muted-text"}`}>
          {apiPlan?.description || p.description}
        </p>
      ) : null}
      <ul className={`mt-5 space-y-2.5 text-[13.5px] flex-1 ${p.featured ? "text-white/80" : "text-body"}`}>
        {features.map((f) => <li key={f} className="flex items-center gap-2"><Check size={13} className={p.featured ? "text-gold" : "text-primary"} /> {f}</li>)}
      </ul>
      <Link to="/contact" className={`mt-6 w-full inline-flex items-center justify-center gap-1.5 h-10 rounded-xl font-semibold text-[13.5px] transition-all ${p.featured ? "bg-gold text-navy hover:brightness-105" : "bg-navy text-white hover:bg-navy/90"}`}>
        Get started <ArrowRight size={13} />
      </Link>
    </div>
  );
}

function PricingPage() {
  const { currency: cur, setCurrency } = useCurrency();
  const { plan: highlightPlan, product: highlightProduct } = Route.useSearch();
  const corePricing = usePublicPricing();
  const feedbackPricing = usePublicFeedbackPricing();
  const expoPricing = usePublicExpoPricing();
  const productVis = useProductVisibility();
  const showCore = isPricingKindEnabled(productVis, "core");
  const showFeedback = isPricingKindEnabled(productVis, "feedback");
  const showExpo = isPricingKindEnabled(productVis, "expo");
  const showSmartCard = isPricingKindEnabled(productVis, "smart_card");
  const s = SYM[cur];
  const fx = FX[cur];
  const [topup, setTopup] = useState(50);
  const [dur, setDur] = useState(12);
  const [num, setNum] = useState(100);
  const [coreBilling, setCoreBilling] = useState<Billing>("monthly");
  const [feedbackBilling, setFeedbackBilling] = useState<Billing>("monthly");

  const coreApiPlans = corePricing.data?.plans ?? [];
  const corePlans = useMemo(
    () => (coreApiPlans.length ? coreApiPlans.map(mapCorePlan) : fallbackCorePlans()),
    [coreApiPlans],
  );
  const feedbackApiPlans = feedbackPricing.data?.plans ?? [];
  const feedbackPlans = useMemo(() => {
    if (feedbackPricing.data) return feedbackApiPlans.map(mapFeedbackPlan);
    if (feedbackPricing.error) return FALLBACK_FEEDBACK;
    return [];
  }, [feedbackApiPlans, feedbackPricing.data, feedbackPricing.error]);
  const expoApiPlans = expoPricing.data?.plans ?? [];
  const expoPlans = useMemo(
    () => (expoApiPlans.length ? expoApiPlans.map(mapExpoPlan) : FALLBACK_EXPO),
    [expoApiPlans],
  );
  const services = corePricing.data?.services;

  useEffect(() => {
    if (!highlightPlan) return;
    const id =
      highlightProduct === "feedback"
        ? `pricing-feedback-${highlightPlan}`
        : highlightProduct === "expo"
          ? `pricing-expo-${highlightPlan}`
          : `pricing-core-${highlightPlan}`;
    const timer = window.setTimeout(() => {
      document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 120);
    return () => window.clearTimeout(timer);
  }, [highlightPlan, highlightProduct, corePlans.length, feedbackPlans.length, expoPlans.length]);

  const waRate = services?.whatsapp_survey_display
    ? Number.parseFloat(String(services.whatsapp_survey_display).replace(/[^\d.]/g, "")) || WA_GBP * fx
    : WA_GBP * fx;
  const cvRate = services?.ats_cv_scan_display
    ? Number.parseFloat(String(services.ats_cv_scan_display).replace(/[^\d.]/g, "")) || CV_GBP * fx
    : CV_GBP * fx;

  const seatMonthly = smartSeat(fx);

  return (
    <div className="bg-background text-body antialiased">
      <SiteHeader />
      <main className="pt-[120px] md:pt-[140px]">
        <section className="bg-beige py-12 md:py-16">
          <div className="max-w-[1080px] mx-auto px-5 md:px-10 text-center">
            <span className="eyebrow">Pricing</span>
            <h1 className="mt-4 text-[36px] md:text-[56px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
              Simple pricing across <span className="serif-italic text-primary">every product</span>.
            </h1>
            <p className="mt-5 text-[17px] text-body max-w-[620px] mx-auto">
              Pick the plan that fits. Use one service or all five.
            </p>
            <div className="mt-6 flex flex-wrap items-center justify-center gap-2" role="group" aria-label="Currency">
              {MARKETS.map((m) => (
                <button
                  key={m.code}
                  type="button"
                  onClick={() => setCurrency(m.code)}
                  className={`inline-flex items-center gap-1.5 h-9 px-3 rounded-full text-[12.5px] font-semibold border transition-colors ${
                    m.code === cur
                      ? "bg-navy text-white border-navy"
                      : "bg-white text-heading border-border hover:border-navy/30"
                  }`}
                >
                  <span aria-hidden>{m.flag}</span>
                  {m.label}
                </button>
              ))}
            </div>
            <div className="mt-3 text-[12.5px] text-muted-text">
              Prices shown in <span className="font-semibold text-heading">{s} {cur.toUpperCase()}</span>
              {(corePricing.loading || feedbackPricing.loading || expoPricing.loading) ? " · loading live prices…" : " · live from billing"}
            </div>
          </div>
        </section>

        {/* Group 1 — AI Interview Screening + WhatsApp Surveys (shared package) */}
        {showCore ? (
        <section className="py-16 bg-beige">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10">
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-text">AI Interview Screening &amp; WhatsApp Surveys</div>
            <p className="mb-2 text-[14px] text-body max-w-[720px]">One shared plan — use minutes for AI interviews or calling surveys, plus WhatsApp surveys, all from the same bucket. Subscribe monthly or pay as you go.</p>
            <p className="mb-6 text-[13px] text-muted-text max-w-[720px] italic">Supports English (GB, Irish, Australian, American, Scottish, Canadian dialects) and Arabic (Egyptian &amp; Saudi dialects).</p>
            <div className="mb-6 flex justify-center">
              <BillingToggle value={coreBilling} onChange={setCoreBilling} />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5">
              {corePlans.map((p) => {
                const apiPlan = coreApiPlans.find((row) => row.code === p.code);
                const featured = p.badge === "Most popular";
                const highlighted = highlightProduct !== "feedback" && highlightProduct !== "expo" && highlightPlan === p.code;
                const priceMinor = corePriceMinor(p, coreBilling, apiPlan);
                const displayPrice = priceMinor != null ? (priceMinor / 100).toFixed(0) : null;
                const perMinDisplay = apiPlan?.per_min_display
                  ? apiPlan.per_min_display.replace(/[^\d.,]/g, "").replace(",", ".")
                  : p.ratePerMinGBP != null
                    ? fmt(p.ratePerMinGBP * fx)
                    : null;
                return (
                  <div
                    key={p.code}
                    id={`pricing-core-${p.code}`}
                    className={`relative rounded-2xl p-5 flex flex-col transition-shadow ${highlighted ? "ring-2 ring-gold shadow-elevated" : ""} ${
                    featured ? "bg-navy text-white border-2 border-gold shadow-elevated"
                      : p.enterprise ? "bg-white border border-navy/15 shadow-elegant"
                      : p.payg ? "bg-gradient-to-br from-white to-beige-2/40 border border-primary/25 shadow-elegant"
                      : "bg-white border border-border shadow-elegant"}`}>
                    {p.badge && (
                      <span className={`absolute -top-3 left-5 text-[10.5px] font-bold uppercase tracking-[0.14em] px-2.5 py-1 rounded-full ${featured ? "bg-gold text-navy" : p.payg ? "bg-primary text-white" : "bg-navy text-white"}`}>{p.badge}</span>
                    )}
                    <div className={`text-[14px] font-semibold ${featured ? "text-white/90" : "text-heading"}`}>{p.name}</div>
                    {p.enterprise ? (
                      <>
                        <div className="mt-3 text-[24px] font-bold tracking-[-0.02em] text-heading">Let's talk</div>
                        {(apiPlan?.description || p.description) ? (
                          <p className="mt-1.5 text-[12.5px] leading-snug text-muted-text">
                            {apiPlan?.description || p.description}
                          </p>
                        ) : (
                          <div className="mt-1 text-[12px] text-muted-text">Volume rates · SLA · dedicated support</div>
                        )}
                      </>
                    ) : p.payg ? (
                      <>
                        <div className="mt-3 flex items-baseline gap-1"><span className="text-[30px] font-bold tracking-[-0.02em] text-heading">{s}0</span><span className="text-[13px] text-muted-text">/mo</span></div>
                        <div className="mt-1 text-[12px] text-muted-text">Per minute: <strong className="text-heading">{apiPlan?.per_min_display || `${s}${fmt((p.ratePerMinGBP as number) * fx)}`}</strong></div>
                        {(apiPlan?.description || p.description) ? (
                          <p className="mt-1.5 text-[12.5px] leading-snug text-muted-text">
                            {apiPlan?.description || p.description}
                          </p>
                        ) : null}
                      </>
                    ) : (
                      <>
                        <div className="mt-3 flex items-baseline gap-1">
                          <span className={`text-[30px] font-bold tracking-[-0.02em] ${featured ? "text-gold" : "text-heading"}`}>{s}{displayPrice ?? Math.round((p.priceGBP as number) * (coreBilling === "yearly" ? 10 : 1) * fx)}</span>
                          <span className={`text-[13px] ${featured ? "text-white/60" : "text-muted-text"}`}>{coreBilling === "yearly" ? "/yr" : "/mo"}</span>
                        </div>
                        <div className={`mt-1 text-[12px] ${featured ? "text-white/70" : "text-muted-text"}`}>Per minute: <strong className={featured ? "text-white" : "text-heading"}>{apiPlan?.per_min_display || `${s}${perMinDisplay}`}</strong></div>
                        {(apiPlan?.description || p.description) ? (
                          <p className={`mt-1.5 text-[12.5px] leading-snug ${featured ? "text-white/65" : "text-muted-text"}`}>
                            {apiPlan?.description || p.description}
                          </p>
                        ) : null}
                      </>
                    )}
                    <div className={`my-4 h-px ${featured ? "bg-white/15" : "bg-border"}`} />
                    <ul className={`space-y-2.5 text-[13px] flex-1 ${featured ? "text-white/80" : "text-body"}`}>
                      {corePlanFeatureLines(p, apiPlan).map((f) => (
                        <li key={f} className="flex items-start gap-2">
                          <Check size={13} className={`mt-0.5 shrink-0 ${featured ? "text-gold" : "text-primary"}`} />
                          <span>{f}</span>
                        </li>
                      ))}
                    </ul>
                    <Link to="/contact" className={`mt-5 w-full inline-flex items-center justify-center gap-1.5 h-10 rounded-xl font-semibold text-[13.5px] transition-all ${featured ? "bg-gold text-navy hover:brightness-105" : p.payg ? "bg-primary text-white hover:bg-primary-dark" : "bg-navy text-white hover:bg-navy/90"}`}>
                      {p.enterprise ? "Contact us" : p.payg ? "Start free" : "Subscribe"} <ArrowRight size={13} />
                    </Link>
                  </div>
                );
              })}
            </div>

            {/* Estimator */}
            <div className="mt-12 bg-white border border-border rounded-2xl p-6 md:p-8 shadow-elegant">
              <div className="flex items-center gap-3 mb-6">
                <div className="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center"><Clock size={18} /></div>
                <div>
                  <div className="text-[15px] font-semibold text-heading">Interview call cost estimator</div>
                  <div className="text-[12.5px] text-muted-text">Typical interview: 10–15 minutes.</div>
                </div>
              </div>
              <div className="space-y-4 mb-5">
                <SliderRow label="Call duration" value={dur} min={5} max={30} step={1} onChange={setDur} display={`${dur} min`} />
                <SliderRow label="Number of interviews" value={num} min={10} max={500} step={10} onChange={setNum} display={`${num}`} />
              </div>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                {corePlans.map((p) => {
                  if (p.enterprise || p.ratePerMinGBP === null) {
                    return (
                      <div key={p.code} className="bg-beige rounded-xl px-4 py-3 text-center">
                        <div className="text-[11px] text-muted-text mb-1">{p.name}</div>
                        <div className="text-[14px] font-semibold text-heading">Contact us</div>
                      </div>
                    );
                  }
                  const apiPlan = coreApiPlans.find((row) => row.code === p.code);
                  const perMinMajor = apiPlan?.per_min_minor != null ? apiPlan.per_min_minor / 100 : (p.ratePerMinGBP as number) * fx;
                  const total = perMinMajor * dur * num;
                  const perCall = perMinMajor * dur;
                  return (
                    <div key={p.code} className="bg-beige rounded-xl px-4 py-3 text-center">
                      <div className="text-[11px] text-muted-text mb-1">{p.name}</div>
                      <div className="text-[16px] font-bold text-heading tabular-nums">{s}{fmt(total)}</div>
                      <div className="text-[10.5px] text-muted-text mt-0.5">{s}{fmt(perCall)}/call</div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </section>
        ) : null}

        {/* Group 3 — Feedback */}
        {showFeedback ? (
        <section className="py-16 bg-beige">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10">
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-text">Customer Feedback</div>
            <p className="mb-6 text-[14px] text-body max-w-[720px]">Collect feedback via WhatsApp and web surveys, with voice-note transcription in any language.</p>
            <div className="mb-6 flex justify-center">
              <BillingToggle value={feedbackBilling} onChange={setFeedbackBilling} />
            </div>
            <div className={`grid gap-4 ${feedbackPlans.length >= 4 ? "grid-cols-1 sm:grid-cols-2 lg:grid-cols-4" : "grid-cols-1 md:grid-cols-3"}`}>
              {feedbackPricing.loading ? (
                <p className="text-[14px] text-muted-text">Loading live prices…</p>
              ) : feedbackPlans.length === 0 ? (
                <p className="text-[14px] text-muted-text">No Customer Feedback packages are published for this market.</p>
              ) : feedbackPlans.map((p) => {
                const apiPlan = feedbackApiPlans.find((row) => row.code === p.code) ?? null;
                const highlighted = highlightProduct === "feedback" && highlightPlan === p.code;
                return (
                  <SimplePlanCard
                    key={p.code}
                    p={p}
                    s={s}
                    billing={feedbackBilling}
                    highlight={highlighted}
                    apiPlan={apiPlan}
                  />
                );
              })}
            </div>
            <p className="mt-10 text-center text-[13px] text-muted-text">
              All plans · GDPR compliant · UK and EU data centres · Cancel with 30 days notice
            </p>
          </div>
        </section>
        ) : null}

        {/* Group 4 — Expo (one-off) */}
        {showExpo ? (
        <section className="py-16 bg-white">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10">
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-text">VoxBulk Expo · one-off per exhibition</div>
            <p className="mb-6 text-[14px] text-body max-w-[720px]">One package = one booth QR. No monthly Expo subscription — buy again for another booth or another show.</p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {expoPlans.map((p) => {
                const featured = Boolean(p.featured);
                const highlighted = highlightProduct === "expo" && highlightPlan === p.code;
                // API returns market currency already; fallback GBP amounts need FX.
                const displayPrice = Math.round(expoApiPlans.length ? p.price : p.price * fx);
                return (
                  <div
                    key={p.code}
                    id={`pricing-expo-${p.code}`}
                    className={`relative rounded-2xl p-6 flex flex-col transition-shadow ${highlighted ? "ring-2 ring-gold shadow-elevated" : ""} ${
                      featured
                        ? "bg-navy text-white border-2 border-gold shadow-elevated"
                        : "bg-white border border-border shadow-elegant"
                    }`}
                  >
                    {featured && (
                      <span className="absolute -top-3 left-5 text-[10.5px] font-bold uppercase tracking-[0.14em] px-2.5 py-1 rounded-full bg-gold text-navy">
                        Most popular
                      </span>
                    )}
                    <div className={`text-[14px] font-semibold ${featured ? "text-white/90" : "text-heading"}`}>{p.name}</div>
                    <div className="mt-3 flex items-baseline gap-1">
                      <span className={`text-[30px] font-bold tracking-[-0.02em] ${featured ? "text-gold" : "text-heading"}`}>
                        {s}{displayPrice}
                      </span>
                      <span className={`text-[13px] ${featured ? "text-white/60" : "text-muted-text"}`}>/ exhibition</span>
                    </div>
                    <ul className={`mt-5 space-y-2.5 text-[13.5px] flex-1 ${featured ? "text-white/80" : "text-body"}`}>
                      {p.features.map((f) => (
                        <li key={f} className="flex items-center gap-2">
                          <Check size={13} className={featured ? "text-gold" : "text-primary"} /> {f}
                        </li>
                      ))}
                    </ul>
                    <Link
                      to="/expo"
                      className={`mt-6 w-full inline-flex items-center justify-center gap-1.5 h-10 rounded-xl font-semibold text-[13.5px] transition-all ${
                        featured ? "bg-gold text-navy hover:brightness-105" : "bg-navy text-white hover:bg-navy/90"
                      }`}
                    >
                      View Expo <ArrowRight size={13} />
                    </Link>
                  </div>
                );
              })}
            </div>
          </div>
        </section>
        ) : null}

        {/* Group 5 — Smart Card QR (subscription per seat) */}
        {showSmartCard ? (
        <section className="py-16 bg-beige">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10">
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-text">Smart Card QR · per seat</div>
            <p className="mb-6 text-[14px] text-body max-w-[720px]">One seat = one rep = one QR. Unlimited scans and leads while your subscription is active. 15 free preview tests before you buy seats.</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-[760px]">
              <div className="rounded-2xl p-6 bg-white border border-border shadow-elegant flex flex-col">
                <div className="text-[14px] font-semibold text-heading">Monthly</div>
                <div className="mt-3 flex items-baseline gap-1">
                  <span className="text-[30px] font-bold tracking-[-0.02em] text-heading">{s}{seatMonthly}</span>
                  <span className="text-[13px] text-muted-text">/ seat / month</span>
                </div>
                <ul className="mt-5 space-y-2.5 text-[13.5px] text-body flex-1">
                  {["One QR per rep", "WhatsApp or web questionnaire", "Business-card photo OCR", "Hot / Warm / Cold scoring", "Rep login — sees own leads only", "Card payment or Direct Debit"].map((f) => (
                    <li key={f} className="flex items-center gap-2"><Check size={13} className="text-primary" /> {f}</li>
                  ))}
                </ul>
                <Link to="/smart-card" className="mt-6 w-full inline-flex items-center justify-center gap-1.5 h-10 rounded-xl font-semibold text-[13.5px] bg-navy text-white hover:bg-navy/90 transition-all">
                  View Smart Card <ArrowRight size={13} />
                </Link>
              </div>
              <div className="relative rounded-2xl p-6 bg-navy text-white border-2 border-gold shadow-elevated flex flex-col">
                <span className="absolute -top-3 left-5 text-[10.5px] font-bold uppercase tracking-[0.14em] px-2.5 py-1 rounded-full bg-gold text-navy">Save 20%</span>
                <div className="text-[14px] font-semibold text-white/90">Yearly</div>
                <div className="mt-3 flex items-baseline gap-1">
                  <span className="text-[30px] font-bold tracking-[-0.02em] text-gold">{s}{Math.round(seatMonthly * 12 * 0.8)}</span>
                  <span className="text-[13px] text-white/60">/ seat / year</span>
                </div>
                <ul className="mt-5 space-y-2.5 text-[13.5px] text-white/80 flex-1">
                  {["Everything in Monthly", "20% off the annual price", "Unlimited scans and leads", "Owner/manager view of all leads", "Catalogue & PDF matching", "QR download as PNG"].map((f) => (
                    <li key={f} className="flex items-center gap-2"><Check size={13} className="text-gold" /> {f}</li>
                  ))}
                </ul>
                <Link to="/smart-card" className="mt-6 w-full inline-flex items-center justify-center gap-1.5 h-10 rounded-xl font-semibold text-[13.5px] bg-gold text-navy hover:brightness-105 transition-all">
                  View Smart Card <ArrowRight size={13} />
                </Link>
              </div>
            </div>
          </div>
        </section>
        ) : null}

        {/* Security / trust */}
        <section className="py-16 bg-white">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10">
            <div className="rounded-2xl border border-border bg-gradient-to-br from-navy to-[#0E1A2E] text-white p-8 md:p-12 shadow-elevated">
              <div className="grid lg:grid-cols-[0.9fr_1.1fr] gap-10 items-start">
                <div>
                  <span className="inline-flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.14em] text-gold">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                    Security &amp; compliance
                  </span>
                  <h2 className="mt-3 text-[28px] md:text-[38px] font-bold tracking-[-0.02em] leading-[1.1] text-white">
                    Your data, <span className="serif-italic text-gold">protected by design</span>.
                  </h2>
                  <p className="mt-4 text-[15px] text-white/75 leading-[1.7] max-w-[460px]">
                    VoxBulk is built as a multi-tenant business platform. Organisation data is isolated, access is controlled, and sensitive credentials are handled with industry-standard safeguards — meeting UK and international requirements.
                  </p>
                  <div className="mt-6 flex flex-wrap gap-2">
                    {["GDPR compliant", "UK & EU data centres", "Encrypted at rest", "Role-based access", "Multi-tenant isolation"].map((t) => (
                      <span key={t} className="px-3 h-8 inline-flex items-center rounded-full border border-white/15 bg-white/[0.04] text-[12px] text-white/85">
                        {t}
                      </span>
                    ))}
                  </div>
                </div>
                <ul className="space-y-3.5 text-[14.5px]">
                  {[
                    ["Tenant isolation", "Each organisation's data is kept separate — your workspace stays yours."],
                    ["Secure sign-in", "Encrypted password storage and modern authentication flows."],
                    ["Encrypted secrets", "Integration secrets encrypted at rest in our systems."],
                    ["Role-based access", "Only authorised team members see what they need."],
                    ["Hardened infrastructure", "Production systems run on secured infrastructure with controlled deployments."],
                  ].map(([t, d]) => (
                    <li key={t} className="flex items-start gap-3 rounded-xl border border-white/10 bg-white/[0.04] p-4">
                      <span className="mt-0.5 shrink-0 w-8 h-8 rounded-lg bg-gold/20 text-gold flex items-center justify-center">
                        <Check size={16} />
                      </span>
                      <div>
                        <div className="font-semibold text-white">{t}</div>
                        <div className="mt-0.5 text-white/70 leading-[1.55]">{d}</div>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="mt-8 pt-6 border-t border-white/10 text-[13px] text-white/60 italic">
                Built for businesses that need WhatsApp, voice, and customer data handled with care.
              </div>
            </div>
          </div>
        </section>

        {/* What each service costs */}
        {showCore ? (
        <section className="py-16 bg-beige">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-text mb-4">What each service costs</div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <ServiceCard tone="blue" icon={<PhoneCall size={16} />} title="Interview & survey call"
                price={`${s}${fmt(0.25 * fx)} – ${s}${fmt(0.35 * fx)}/min`} unit="per minute · depends on your plan"
                desc={`Starter: ${s}${fmt(0.35 * fx)}/min · Pro: ${s}${fmt(0.30 * fx)}/min · Business: ${s}${fmt(0.25 * fx)}/min.`} />
              <ServiceCard tone="teal" icon={<MessageCircle size={16} />} title="WhatsApp survey"
                price={`${s}${fmt(waRate)}`} unit="per user sent"
                desc="One flat charge every time a survey is sent. No per-reply charge — just the send." />
              <ServiceCard tone="gold" icon={<FileText size={16} />} title="ATS CV scan"
                price={`${s}${fmt(cvRate)}`} unit="per CV scanned"
                desc="Each CV uploaded and processed by the ATS costs a flat fee." />
            </div>

            {/* Top-up */}
            <div className="mt-12 bg-white border border-border rounded-2xl p-6 md:p-8 shadow-elegant">
              <div className="flex items-center gap-3 mb-6">
                <div className="w-10 h-10 rounded-xl bg-success/10 text-success flex items-center justify-center"><Wallet size={18} /></div>
                <div>
                  <div className="text-[15px] font-semibold text-heading">Pay-as-you-go credit top-up</div>
                  <div className="text-[12.5px] text-muted-text">No expiry — use across calls, surveys and CV scans</div>
                </div>
              </div>
              <div className="flex items-center gap-4 mb-5">
                <input type="range" min={10} max={500} step={10} value={topup} onChange={(e) => setTopup(parseInt(e.target.value))} className="flex-1 accent-primary" aria-label="Top-up amount" />
                <div className="text-[15px] font-semibold text-heading min-w-[80px] text-right tabular-nums">{s}{fmt(topup * fx)}</div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <TopupCell label="Minutes of calls" value={`~${Math.floor(topup / 0.35)} mins`} />
                <TopupCell label="WhatsApp surveys" value={`${Math.floor(topup / (waRate || WA_GBP)).toLocaleString()} surveys`} />
                <TopupCell label="CV scans" value={`${Math.floor(topup / (cvRate || CV_GBP)).toLocaleString()} scans`} />
              </div>
            </div>
          </div>
        </section>
        ) : null}

        <BottomCTA />
      </main>
      <SiteFooter />
    </div>
  );
}
