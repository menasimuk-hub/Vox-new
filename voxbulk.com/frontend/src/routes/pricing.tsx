import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { ArrowRight, Check, Clock, FileText, MessageCircle, PhoneCall, Wallet } from "lucide-react";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import {
  BottomCTA, PLANS, WA_GBP, CV_GBP, fmt, SliderRow, ServiceCard, TopupCell,
  BillingToggle, type Billing,
} from "@/components/VOXBULKHome";
import { useCurrency, SYM, FX } from "@/components/CurrencyContext";
import { usePublicFeedbackPricing, usePublicPricing, type PublicFeedbackPlan, type PublicPlan } from "@/hooks/usePricing";
import { pageMeta } from "@/lib/seo-defaults";

export const Route = createFileRoute("/pricing")({
  validateSearch: (search: Record<string, unknown>) => ({
    plan: typeof search.plan === "string" && search.plan.trim() ? search.plan.trim() : undefined,
    product: search.product === "feedback" ? ("feedback" as const) : undefined,
  }),
  head: () => ({
    meta: pageMeta("pricing"),
    links: [{ rel: "canonical", href: "https://voxbulk.com/pricing" }],
  }),
  component: PricingPage,
});

// WhatsApp Surveys + AI Interview Screening share one combined plan (see PLANS).

type FeedbackPlan = {
  code: string;
  name: string;
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
    price,
    featured: p.is_featured,
    waSurveys: wa < 0 ? "Unlimited" : wa,
    webSurveys: web < 0 ? "Unlimited" : web,
    extraFeatures: extras.length ? extras : [`${p.max_locations || 1} location(s)`],
  };
}

function feedbackPriceMinor(p: FeedbackPlan, billing: Billing, apiPlan?: PublicFeedbackPlan | null) {
  if (apiPlan?.yearly_price_minor != null && billing === "yearly") return apiPlan.yearly_price_minor;
  if (apiPlan?.monthly_price_minor != null) {
    return billing === "yearly" ? apiPlan.monthly_price_minor * 10 : apiPlan.monthly_price_minor;
  }
  return Math.round(p.price * (billing === "yearly" ? 10 : 1) * 100);
}

function corePriceMinor(p: CorePlanView, billing: Billing, apiPlan?: PublicPlan | null) {
  if (apiPlan?.yearly_price_minor != null && billing === "yearly") return apiPlan.yearly_price_minor;
  if (apiPlan?.monthly_price_minor != null) {
    return billing === "yearly" ? apiPlan.monthly_price_minor * 10 : apiPlan.monthly_price_minor;
  }
  if (p.priceGBP == null) return null;
  return Math.round(p.priceGBP * (billing === "yearly" ? 10 : 1) * 100);
}

function fmtSurveyCount(n: number | "Unlimited") {
  return n === "Unlimited" ? "Unlimited" : n.toLocaleString();
}

function fmtTotalResponses(wa: number | "Unlimited", web: number | "Unlimited") {
  if (wa === "Unlimited" || web === "Unlimited") return "Unlimited";
  return (wa + web).toLocaleString();
}

function feedbackPlanFeatures(p: FeedbackPlan, apiPlan?: PublicFeedbackPlan | null): string[] {
  if (apiPlan?.features?.length) return apiPlan.features;
  return [
    `${fmtSurveyCount(p.waSurveys)} WhatsApp surveys/mo`,
    `${fmtSurveyCount(p.webSurveys)} Web surveys/mo`,
    `${fmtTotalResponses(p.waSurveys, p.webSurveys)} total responses/mo`,
    "Voice-note transcription included",
    ...p.extraFeatures,
  ];
}

function corePlanFeatureLines(p: CorePlanView, apiPlan?: PublicPlan | null): string[] {
  if (apiPlan?.features?.length) return apiPlan.features;
  if (p.enterprise) {
    return ["Custom minutes & allowances", "Volume rates ┬╖ SLA", "Dedicated support"];
  }
  if (p.payg) {
    return [
      "No monthly fee",
      "Pay per minute for interview calls",
      "Pay per WhatsApp survey sent",
      "Pay per CV scan",
      "Wallet top-up credits ΓÇö no expiry",
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
  const displayPrice = minor != null ? (minor / 100).toFixed(0) : "ΓÇö";
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
  const { currency: cur } = useCurrency();
  const { plan: highlightPlan, product: highlightProduct } = Route.useSearch();
  const corePricing = usePublicPricing();
  const feedbackPricing = usePublicFeedbackPricing();
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
  const feedbackPlans = useMemo(
    () => (feedbackApiPlans.length ? feedbackApiPlans.map(mapFeedbackPlan) : FALLBACK_FEEDBACK),
    [feedbackApiPlans],
  );
  const services = corePricing.data?.services;

  useEffect(() => {
    if (!highlightPlan) return;
    const isFeedback = highlightProduct === "feedback";
    const id = isFeedback ? `pricing-feedback-${highlightPlan}` : `pricing-core-${highlightPlan}`;
    const timer = window.setTimeout(() => {
      document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 120);
    return () => window.clearTimeout(timer);
  }, [highlightPlan, highlightProduct, corePlans.length, feedbackPlans.length]);

  const waRate = services?.whatsapp_survey_display
    ? Number.parseFloat(String(services.whatsapp_survey_display).replace(/[^\d.]/g, "")) || WA_GBP * fx
    : WA_GBP * fx;
  const cvRate = services?.ats_cv_scan_display
    ? Number.parseFloat(String(services.ats_cv_scan_display).replace(/[^\d.]/g, "")) || CV_GBP * fx
    : CV_GBP * fx;

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
              Pick the plan that fits. Use one product or all three.
            </p>
            <div className="mt-4 text-[12.5px] text-muted-text">
              Prices shown in <span className="font-semibold text-heading">{s} {cur.toUpperCase()}</span> ┬╖ change country in footer
            </div>
          </div>
        </section>

        {/* Group 1 ΓÇö AI Interview Screening + WhatsApp Surveys (shared package) */}
        <section className="py-16 bg-beige">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10">
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-text">AI Interview Screening &amp; WhatsApp Surveys</div>
            <p className="mb-6 text-[14px] text-body max-w-[680px]">One shared plan ΓÇö use minutes for AI interviews or calling surveys, plus WhatsApp surveys, all from the same bucket. Subscribe monthly or pay as you go.</p>
            <div className="mb-6 flex justify-center">
              <BillingToggle value={coreBilling} onChange={setCoreBilling} />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5">
              {corePlans.map((p) => {
                const apiPlan = coreApiPlans.find((row) => row.code === p.code);
                const featured = p.badge === "Most popular";
                const highlighted = highlightProduct !== "feedback" && highlightPlan === p.code;
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
                        <div className="mt-1 text-[12px] text-muted-text">Volume rates ┬╖ SLA ┬╖ dedicated support</div>
                      </>
                    ) : p.payg ? (
                      <>
                        <div className="mt-3 flex items-baseline gap-1"><span className="text-[30px] font-bold tracking-[-0.02em] text-heading">{s}0</span><span className="text-[13px] text-muted-text">/mo</span></div>
                        <div className="mt-1 text-[12px] text-muted-text">Per minute: <strong className="text-heading">{apiPlan?.per_min_display || `${s}${fmt((p.ratePerMinGBP as number) * fx)}`}</strong></div>
                      </>
                    ) : (
                      <>
                        <div className="mt-3 flex items-baseline gap-1">
                          <span className={`text-[30px] font-bold tracking-[-0.02em] ${featured ? "text-gold" : "text-heading"}`}>{s}{displayPrice ?? Math.round((p.priceGBP as number) * (coreBilling === "yearly" ? 10 : 1) * fx)}</span>
                          <span className={`text-[13px] ${featured ? "text-white/60" : "text-muted-text"}`}>{coreBilling === "yearly" ? "/yr" : "/mo"}</span>
                        </div>
                        <div className={`mt-1 text-[12px] ${featured ? "text-white/70" : "text-muted-text"}`}>Per minute: <strong className={featured ? "text-white" : "text-heading"}>{apiPlan?.per_min_display || `${s}${perMinDisplay}`}</strong></div>
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
                  <div className="text-[12.5px] text-muted-text">Typical interview: 10ΓÇô15 minutes.</div>
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


        {/* Group 3 ΓÇö Feedback */}
        <section className="py-16 bg-beige">
          <div className="max-w-[1080px] mx-auto px-5 md:px-10">
            <div className="mb-6 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-text">Customer Feedback</div>
            <div className="mb-6 flex justify-center">
              <BillingToggle value={feedbackBilling} onChange={setFeedbackBilling} />
            </div>
            <div className="grid md:grid-cols-3 gap-5">
              {feedbackPlans.map((p) => {
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
              All plans ┬╖ GDPR compliant ┬╖ UK and EU data centres ┬╖ Cancel with 30 days notice
            </p>
          </div>
        </section>

        {/* What each service costs */}
        <section className="py-16 bg-white">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-text mb-4">What each service costs</div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <ServiceCard tone="blue" icon={<PhoneCall size={16} />} title="Interview & survey call"
                price={`${s}${fmt(0.25 * fx)} ΓÇô ${s}${fmt(0.35 * fx)}/min`} unit="per minute ┬╖ depends on your plan"
                desc={`Starter: ${s}${fmt(0.35 * fx)}/min ┬╖ Pro: ${s}${fmt(0.30 * fx)}/min ┬╖ Business: ${s}${fmt(0.25 * fx)}/min.`} />
              <ServiceCard tone="teal" icon={<MessageCircle size={16} />} title="WhatsApp survey"
                price={`${s}${fmt(waRate)}`} unit="per user sent"
                desc="One flat charge every time a survey is sent. No per-reply charge ΓÇö just the send." />
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
                  <div className="text-[12.5px] text-muted-text">No expiry ΓÇö use across calls, surveys and CV scans</div>
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

        <BottomCTA />
      </main>
      <SiteFooter />
    </div>
  );
}
