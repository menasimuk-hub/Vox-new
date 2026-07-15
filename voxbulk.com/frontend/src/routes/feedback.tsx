import { createFileRoute, Link } from "@tanstack/react-router";
import React, { useState } from "react";
import { ArrowRight, Check, Utensils, ShoppingBag, Scissors, Hotel, Languages, Smartphone, MessageCircle } from "lucide-react";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { Hero, StatsRow, BottomCTA, BillingToggle, type Billing } from "@/components/VOXBULKHome";
import { useCurrency, SYM, FX } from "@/components/CurrencyContext";

export const Route = createFileRoute("/feedback")({
  head: () => ({
    meta: [
      { title: "Customer Feedback — VoxBulk" },
      { name: "description", content: "One QR code on your table or counter. Customers scan, chat on WhatsApp, you get a weekly report." },
      { property: "og:title", content: "Customer Feedback — VoxBulk" },
      { property: "og:description", content: "Know what your customers really think." },
    ],
    links: [{ rel: "canonical", href: "https://voxbulk.com/feedback" }],
  }),
  component: FeedbackPage,
});

const steps = [
  { n: "01", title: "Place your QR code", body: "You get a unique QR code per location. Print and place on tables, receipts, or your counter. Nothing for the customer to download." },
  { n: "02", title: "Customer scans and chats", body: "WhatsApp opens automatically. AI guides them through 3 to 5 friendly questions in under a minute." },
  { n: "03", title: "You get the report", body: "Weekly or monthly KPI report to your inbox. Response rates, scores, and trends in one clear summary." },
];

const audiences = [
  { icon: Utensils, title: "Restaurants & cafés" },
  { icon: ShoppingBag, title: "Retail shops" },
  { icon: Scissors, title: "Salons & spas" },
  { icon: Hotel, title: "Hotels & hospitality" },
];

type FeedbackPlan = {
  name: string;
  price: number;
  featured?: boolean;
  waSurveys: number | "Unlimited";
  webSurveys: number | "Unlimited";
  extraFeatures: string[];
};

const plans: FeedbackPlan[] = [
  { name: "Starter", price: 49, waSurveys: 200, webSurveys: 100, extraFeatures: ["1 location", "Monthly report", "Email support"] },
  { name: "Growth", price: 99, featured: true, waSurveys: 600, webSurveys: 300, extraFeatures: ["3 locations", "Weekly report", "Live dashboard", "Priority support"] },
  { name: "Pro", price: 199, waSurveys: "Unlimited", webSurveys: "Unlimited", extraFeatures: ["10 locations", "Real-time dashboard", "Branded PDF report", "Dedicated account manager"] },
];

function fmtSurveyCount(n: number | "Unlimited") {
  return n === "Unlimited" ? "Unlimited" : n.toLocaleString();
}

function fmtTotalResponses(wa: number | "Unlimited", web: number | "Unlimited") {
  if (wa === "Unlimited" || web === "Unlimited") return "Unlimited";
  return (wa + web).toLocaleString();
}

function feedbackPlanFeatures(p: FeedbackPlan): string[] {
  return [
    `${fmtSurveyCount(p.waSurveys)} WhatsApp surveys/mo`,
    `${fmtSurveyCount(p.webSurveys)} Web surveys/mo`,
    `${fmtTotalResponses(p.waSurveys, p.webSurveys)} total responses/mo`,
    "Voice-note transcription included",
    ...p.extraFeatures,
  ];
}

const faqs = [
  { q: "Do my customers need to download anything?", a: "No. They scan the QR code and WhatsApp opens automatically. Nothing to download or sign up for." },
  { q: "What questions does the AI ask?", a: "We set up a default question set for your business type. You can customise questions on Growth and Pro plans." },
  { q: "How do I receive the report?", a: "By email on your chosen schedule. Pro plan users also get a live dashboard." },
  { q: "How many QR codes do I get?", a: "One per location included in your plan. Each tracks responses separately." },
  { q: "Is it GDPR compliant?", a: "Yes. All data stored on UK and EU servers. Customers are informed before the survey begins." },
];

function FeedbackPage() {
  const { currency: cur } = useCurrency();
  const s = SYM[cur]; const fx = FX[cur];
  const [openIdx, setOpenIdx] = useState<number | null>(0);
  const [billing, setBilling] = useState<Billing>("monthly");
  return (
    <div className="bg-background text-body antialiased">
      <SiteHeader />
      <main>
        <Hero
          badgeText="Live now · Customer Feedback"
          headline={<>Know what your customers <span className="serif-italic text-gold">really think</span>.</>}
          sub={<>One QR code on your table or counter. Customers scan, chat on WhatsApp, you get a weekly report.</>}
          primaryHref="/contact"
          primaryLabel="Get started"
        />

        {/* QR showcase */}
        <section className="py-20 md:py-24 bg-white relative overflow-hidden">
          <div className="absolute -top-24 -right-20 w-[380px] h-[380px] rounded-full blur-3xl opacity-30 float-a" style={{ background: "radial-gradient(circle, #1E6FD9 0%, transparent 60%)" }} />
          <div className="absolute -bottom-24 -left-20 w-[380px] h-[380px] rounded-full blur-3xl opacity-25 float-b" style={{ background: "radial-gradient(circle, #4FB3A9 0%, transparent 60%)" }} />
          <div className="relative max-w-[1080px] mx-auto px-5 md:px-10 grid md:grid-cols-2 gap-12 items-center">
            <div>
              <span className="eyebrow">Scan · Chat · Done</span>
              <h2 className="mt-4 text-[34px] md:text-[44px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
                One QR code. <span className="serif-italic text-primary">Real feedback.</span>
              </h2>
              <p className="mt-5 text-[16px] text-body max-w-[480px]">
                Print it, stick it on tables, receipts, or your counter. Customers point their camera, WhatsApp opens, and the AI handles the rest — no app, no signup.
              </p>
              <ul className="mt-6 space-y-2.5 text-[14.5px] text-body">
                <li className="flex items-center gap-2"><Check size={15} className="text-primary" /> Unique QR per location</li>
                <li className="flex items-center gap-2"><Check size={15} className="text-primary" /> Branded with your logo &amp; colours</li>
                <li className="flex items-center gap-2"><Check size={15} className="text-primary" /> Weekly KPI report by email</li>
              </ul>
            </div>
            <div className="relative mx-auto max-w-full flex justify-center">
              <div className="relative w-[min(280px,calc(100vw-2.5rem))] h-[min(280px,calc(100vw-2.5rem))] md:w-[320px] md:h-[320px] rounded-3xl bg-white border border-border shadow-elevated p-6 flex items-center justify-center">
                <div className="absolute -top-3 left-6 inline-flex items-center gap-1.5 px-3 h-7 rounded-full bg-navy text-white text-[11px] font-bold uppercase tracking-[0.14em]">
                  <span className="w-1.5 h-1.5 rounded-full bg-teal pulse-dot" /> Live
                </div>
                <svg viewBox="0 0 33 33" width="100%" height="100%" shapeRendering="crispEdges" aria-label="Sample QR code">
                  {(() => {
                    // Deterministic pseudo-QR pattern (visual mock only)
                    const cells: React.ReactElement[] = [];
                    const seed = (x: number, y: number) => ((x * 928371 + y * 12345 + 7) % 7) > 3;
                    for (let y = 0; y < 33; y++) for (let x = 0; x < 33; x++) {
                      if (seed(x, y)) cells.push(<rect key={`${x}-${y}`} x={x} y={y} width={1} height={1} fill="#0A1628" />);
                    }
                    return cells;
                  })()}
                  {/* finder squares */}
                  {[[0,0],[26,0],[0,26]].map(([x,y],i) => (
                    <g key={i}>
                      <rect x={x} y={y} width={7} height={7} fill="#0A1628" />
                      <rect x={x+1} y={y+1} width={5} height={5} fill="#fff" />
                      <rect x={x+2} y={y+2} width={3} height={3} fill="#0A1628" />
                    </g>
                  ))}
                  {/* center logo dot */}
                  <rect x={13} y={13} width={7} height={7} fill="#fff" />
                  <rect x={14} y={14} width={5} height={5} rx={1} fill="#D4A93A" />
                </svg>
                <span className="absolute -bottom-3 right-6 inline-flex items-center gap-1.5 px-3 h-7 rounded-full bg-gold text-navy text-[11px] font-bold uppercase tracking-[0.14em]">
                  voxbulk.com
                </span>
              </div>
              <span className="absolute -top-4 -left-4 w-2.5 h-2.5 rounded-full bg-teal shadow-[0_0_12px_2px_rgba(79,179,169,0.6)] float-a" />
              <span className="absolute -bottom-4 -right-4 w-2 h-2 rounded-full bg-primary shadow-[0_0_12px_2px_rgba(30,111,217,0.55)] float-b" />
            </div>
          </div>
        </section>

        {/* Multi-language auto-detect */}
        <section className="py-20 md:py-24 bg-beige">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10 grid md:grid-cols-2 gap-12 items-center">
            <div className="order-2 md:order-1 relative">
              <div className="relative mx-auto max-w-[360px] rounded-3xl bg-white border border-border shadow-elevated p-5">
                <div className="flex items-center gap-2 pb-3 border-b border-border">
                  <span className="w-2 h-2 rounded-full bg-success" />
                  <span className="text-[12px] font-semibold text-heading">WhatsApp · VoxBulk</span>
                  <Smartphone size={12} className="ml-auto text-muted-text" />
                </div>
                <div className="mt-4 space-y-2.5">
                  <div className="max-w-[78%] rounded-2xl rounded-tl-sm bg-beige px-3 py-2 text-[13px] text-heading">مرحبًا! كيف كانت تجربتك معنا اليوم؟</div>
                  <div className="max-w-[78%] ml-auto rounded-2xl rounded-tr-sm bg-primary/10 text-primary px-3 py-2 text-[13px]">ممتازة، شكرًا!</div>
                  <div className="max-w-[78%] rounded-2xl rounded-tl-sm bg-beige px-3 py-2 text-[13px] text-heading">您会向朋友推荐我们吗？</div>
                  <div className="max-w-[78%] ml-auto rounded-2xl rounded-tr-sm bg-primary/10 text-primary px-3 py-2 text-[13px]">当然会 ⭐⭐⭐⭐⭐</div>
                  <div className="max-w-[78%] rounded-2xl rounded-tl-sm bg-beige px-3 py-2 text-[13px] text-heading">¡Gracias por tus comentarios!</div>
                </div>
                <div className="mt-4 pt-3 border-t border-border flex items-center justify-between text-[11px] text-muted-text">
                  <span className="inline-flex items-center gap-1.5"><Languages size={11} /> English / Arabic from mobile country code</span>
                  <span className="font-semibold text-success">Delivered</span>
                </div>
              </div>
              <span className="absolute -top-3 -left-3 inline-flex items-center gap-1.5 px-3 h-7 rounded-full bg-navy text-white text-[11px] font-bold uppercase tracking-[0.14em]">
                <Languages size={12} className="text-gold" /> English &amp; Arabic
              </span>
            </div>
            <div className="order-1 md:order-2">
              <span className="eyebrow">Multi-language</span>
              <h2 className="mt-4 text-[34px] md:text-[44px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
                Speaks your customer's <span className="serif-italic text-primary">language</span>.
              </h2>
              <p className="mt-5 text-[16px] text-body max-w-[520px]">
                Scan the QR code and the system sends a WhatsApp message to VoxBulk. The survey language is auto-detected from the customer&apos;s mobile country code — English or Arabic today, with more locales as templates are added.
              </p>
              <ul className="mt-6 space-y-2.5 text-[14.5px] text-body">
                <li className="flex items-center gap-2"><Check size={15} className="text-primary" /> Arabic for Gulf, Levant, and North Africa numbers (e.g. +966, +971, +970)</li>
                <li className="flex items-center gap-2"><Check size={15} className="text-primary" /> English for UK, US, EU, and other regions by default</li>
                <li className="flex items-center gap-2"><Check size={15} className="text-primary" /> Right-to-left Arabic handled natively in WhatsApp</li>
                <li className="flex items-center gap-2"><Check size={15} className="text-primary" /> No app, no signup — runs entirely inside WhatsApp</li>
              </ul>
              <div className="mt-6 flex flex-wrap gap-2">
                {["English","العربية","+970 PS","+966 SA","+971 AE","+44 UK"].map((l) => (
                  <span key={l} className="inline-flex items-center gap-1.5 px-3 h-7 rounded-full bg-white border border-border text-[12px] font-semibold text-heading">
                    <MessageCircle size={11} className="text-teal" /> {l}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </section>


        <section className="py-24 md:py-28 bg-beige">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10">
            <div className="text-center max-w-[680px] mx-auto">
              <span className="eyebrow">How it works</span>
              <h2 className="mt-4 text-[36px] md:text-[48px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">Three steps. <span className="serif-italic text-primary">One QR code.</span></h2>
            </div>
            <div className="mt-14 grid md:grid-cols-3 gap-5">
              {steps.map((st) => (
                <div key={st.n} className="bg-white border border-border rounded-2xl p-7">
                  <div className="w-14 h-14 rounded-full bg-navy text-gold flex items-center justify-center font-bold">{st.n}</div>
                  <h3 className="mt-4 text-[19px] font-bold text-heading">{st.title}</h3>
                  <p className="mt-2 text-[14.5px] text-body leading-[1.65]">{st.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="py-24 md:py-28 bg-white">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10">
            <div className="max-w-[680px]">
              <span className="eyebrow">Who it's for</span>
              <h2 className="mt-4 text-[36px] md:text-[48px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">Built for businesses with <span className="serif-italic text-primary">real customers</span>.</h2>
            </div>
            <div className="mt-12 grid md:grid-cols-4 sm:grid-cols-2 gap-5">
              {audiences.map((a) => (
                <div key={a.title} className="card-soft p-6">
                  <div className="w-11 h-11 rounded-xl bg-primary/10 text-primary flex items-center justify-center"><a.icon size={20} /></div>
                  <h3 className="mt-4 text-[16px] font-bold text-heading">{a.title}</h3>
                </div>
              ))}
            </div>
          </div>
        </section>

        <StatsRow items={[
          { value: "98%", label: "WhatsApp open rate" },
          { value: "3×", label: "more responses than paper or web forms" },
          { value: "<60s", label: "average survey completion time" },
          { value: "1", label: "QR code per location, nothing to install" },
        ]} />

        <section className="py-24 md:py-28 bg-beige">
          <div className="max-w-[1080px] mx-auto px-5 md:px-10">
            <div className="text-center max-w-[680px] mx-auto">
              <span className="eyebrow">Pricing</span>
              <h2 className="mt-4 text-[36px] md:text-[48px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">Simple monthly plans.</h2>
            </div>
            <div className="mt-8 flex justify-center">
              <BillingToggle value={billing} onChange={setBilling} />
            </div>
            <div className="mt-12 grid md:grid-cols-3 gap-5">
              {plans.map((p) => {
                const features = feedbackPlanFeatures(p);
                const displayPrice = Math.round(p.price * (billing === "yearly" ? 10 : 1) * fx);
                const period = billing === "yearly" ? "/yr" : "/mo";
                return (
                <div key={p.name} className={`relative rounded-2xl p-6 flex flex-col ${p.featured ? "bg-navy text-white border-2 border-gold shadow-elevated" : "bg-white border border-border shadow-elegant"}`}>
                  {p.featured && <span className="absolute -top-3 left-5 text-[10.5px] font-bold uppercase tracking-[0.14em] px-2.5 py-1 rounded-full bg-gold text-navy">Most popular</span>}
                  <div className={`text-[14px] font-semibold ${p.featured ? "text-white/90" : "text-heading"}`}>{p.name}</div>
                  <div className="mt-3 flex items-baseline gap-1">
                    <span className={`text-[32px] font-bold tracking-[-0.02em] ${p.featured ? "text-gold" : "text-heading"}`}>{s}{displayPrice}</span>
                    <span className={`text-[13px] ${p.featured ? "text-white/60" : "text-muted-text"}`}>{period}</span>
                  </div>
                  <ul className={`mt-5 space-y-2.5 text-[14px] flex-1 ${p.featured ? "text-white/80" : "text-body"}`}>
                    {features.map((f) => <li key={f} className="flex items-center gap-2"><Check size={13} className={p.featured ? "text-gold" : "text-primary"} /> {f}</li>)}
                  </ul>
                  <Link to="/contact" className={`mt-6 w-full inline-flex items-center justify-center gap-1.5 h-10 rounded-xl font-semibold text-[13.5px] transition-all ${p.featured ? "bg-gold text-navy hover:brightness-105" : "bg-navy text-white hover:bg-navy/90"}`}>
                    Get started <ArrowRight size={13} />
                  </Link>
                </div>
                );
              })}
            </div>
            <p className="mt-8 text-center text-[13px] text-muted-text">
              WhatsApp delivery included in all plans · No per-message charges · Cancel anytime with 30 days notice
            </p>
          </div>
        </section>

        <section className="py-24 md:py-28 bg-white">
          <div className="max-w-[860px] mx-auto px-5 md:px-10">
            <div className="text-center"><span className="eyebrow">FAQ</span>
              <h2 className="mt-4 text-[36px] md:text-[48px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">Questions, <span className="serif-italic text-primary">answered</span>.</h2>
            </div>
            <div className="mt-12 divide-y divide-border border-y border-border">
              {faqs.map((item, i) => {
                const open = openIdx === i;
                return (
                  <div key={item.q}>
                    <button onClick={() => setOpenIdx(open ? null : i)} className="w-full flex items-center justify-between text-left py-5 gap-6" aria-expanded={open}>
                      <span className="text-[16px] md:text-[17px] font-semibold text-heading">{item.q}</span>
                      <span className={`w-8 h-8 rounded-full border border-border flex items-center justify-center transition-transform ${open ? "rotate-45 bg-navy text-gold border-navy" : "text-heading"}`}>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></svg>
                      </span>
                    </button>
                    {open && <div className="pb-6 pr-12 text-[15.5px] text-body leading-[1.65]">{item.a}</div>}
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        <BottomCTA />
      </main>
      <SiteFooter />
    </div>
  );
}
