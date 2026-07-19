import { createFileRoute, Link } from "@tanstack/react-router";
import React, { useMemo, useState } from "react";
import {
  ArrowRight, Check, Utensils, ShoppingBag, Scissors, Hotel, Languages, Smartphone,
  MessageCircle, Mic, MapPin, ShieldCheck, AlertTriangle,
} from "lucide-react";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { Hero, StatsRow, BottomCTA, BillingToggle, type Billing } from "@/components/VOXBULKHome";
import { useCurrency, SYM } from "@/components/CurrencyContext";
import { usePublicFeedbackPricing, type PublicFeedbackPlan } from "@/hooks/usePricing";
import { pageMeta } from "@/lib/seo-defaults";

export const Route = createFileRoute("/feedback")({
  head: () => ({
    meta: pageMeta("feedback"),
    links: [{ rel: "canonical", href: "https://voxbulk.com/feedback" }],
  }),
  component: FeedbackPage,
});

const steps = [
  {
    n: "01",
    title: "Place your QR code",
    body: "You get a unique QR per location — table, counter, receipt, room or delivery bag. Print it; nothing for the customer to download.",
  },
  {
    n: "02",
    title: "Customer scans and chats",
    body: "WhatsApp opens instantly. They tap Excellent / Good / Poor, type, or record a voice note in any language — usually finished in about 30 seconds.",
  },
  {
    n: "03",
    title: "You compare and act",
    body: "Live dashboard shows scores by location, English translations, voice transcripts, red flags and AI actions for what to fix this week.",
  },
];

const audiences = [
  { icon: Utensils, title: "Restaurants & cafés" },
  { icon: ShoppingBag, title: "Retail shops" },
  { icon: Scissors, title: "Salons & spas" },
  { icon: Hotel, title: "Hotels & hospitality" },
];

const highlights = [
  {
    icon: Languages,
    title: "Country-code language",
    body: "+966 Arabic, +33 French, +34 Spanish and 50+ more. Customers chat in theirs; you read English.",
  },
  {
    icon: Mic,
    title: "Voice notes",
    body: "Customers tap and talk freely. VoxBulk transcribes, translates and highlights key themes.",
  },
  {
    icon: MapPin,
    title: "Compare locations",
    body: "Every branch has its own QR, results, trends and colour-coded comparison.",
  },
  {
    icon: ShieldCheck,
    title: "Privacy ready",
    body: "Consent on scan, STOP honoured, UK & EU data centres, UK GDPR.",
  },
];

type FaqItem = { q: string; a: React.ReactNode };

const faqs: FaqItem[] = [
  {
    q: "Do my customers need to download anything?",
    a: "No. They scan the QR code and WhatsApp opens automatically. Nothing to download or sign up for.",
  },
  {
    q: "Can customers leave voice notes?",
    a: "Yes. They can tap buttons, type, or record a voice note in any language. Audio, transcript, English translation and sentiment land in your dashboard together.",
  },
  {
    q: "How do languages work?",
    a: "The survey starts from the customer's mobile country code and message language — 50+ languages including Arabic, French, Spanish, Chinese and more. Your team reads everything in English; originals are kept.",
  },
  {
    q: "Can I compare multiple locations?",
    a: "Yes. Each QR belongs to a location so you can track branches side by side, spot weak sites, and see recommend rate and red flags per venue.",
  },
  {
    q: "What happens when someone leaves a poor score?",
    a: "Low scores open a polite follow-up (“Can you tell us what happened?”) and create a red-flag item so managers can recover the customer before a public review.",
  },
  {
    q: "How do I receive the report?",
    a: "By email on your chosen schedule, plus a live dashboard on Growth and Pro plans — with exports for owners and branch managers.",
  },
  {
    q: "Is it GDPR compliant?",
    a: (
      <>
        Yes. Consent on scan, STOP honoured, and data stored in UK and EU centres. See our{" "}
        <Link to="/gdpr" className="text-primary font-semibold underline-offset-2 hover:underline">
          GDPR overview
        </Link>{" "}
        and{" "}
        <Link to="/privacy" className="text-primary font-semibold underline-offset-2 hover:underline">
          Privacy Policy
        </Link>
        .
      </>
    ),
  },
];

function planPriceDisplay(p: PublicFeedbackPlan, billing: Billing, symbol: string) {
  const minor =
    billing === "yearly" && p.yearly_price_minor != null
      ? p.yearly_price_minor
      : p.monthly_price_minor != null
        ? billing === "yearly"
          ? p.monthly_price_minor * 10
          : p.monthly_price_minor
        : null;
  if (minor != null) return `${symbol}${(minor / 100).toFixed(0)}`;
  const raw = billing === "yearly" ? p.yearly_price_display : p.monthly_price_display;
  return raw?.trim() || "—";
}

function FeedbackPage() {
  const { currency: cur } = useCurrency();
  const s = SYM[cur];
  const feedbackPricing = usePublicFeedbackPricing();
  const [billing, setBilling] = useState<Billing>("monthly");
  const [openIdx, setOpenIdx] = useState<number | null>(0);

  const plans = useMemo(() => {
    const list = feedbackPricing.data?.plans ?? [];
    return [...list].sort((a, b) => (b.is_featured ? 1 : 0) - (a.is_featured ? 1 : 0) || a.name.localeCompare(b.name));
  }, [feedbackPricing.data?.plans]);

  return (
    <div className="bg-background text-body antialiased">
      <SiteHeader />
      <main>
        <Hero
          badgeText="Live now · Customer Feedback"
          headline={
            <>
              One QR. Their voice. <span className="serif-italic text-gold">Their language</span>.
            </>
          }
          sub={
            <>
              Scan → WhatsApp → ~30-second chat. Customers answer in their own language, record voice notes, and your
              dashboard translates everything into English with live multi-location comparison.
            </>
          }
          primaryHref="/contact"
          primaryLabel="Get started"
        />

        <section className="py-20 md:py-24 bg-white relative overflow-hidden">
          <div className="absolute -top-24 -right-20 w-[380px] h-[380px] rounded-full blur-3xl opacity-30 float-a" style={{ background: "radial-gradient(circle, #1E6FD9 0%, transparent 60%)" }} />
          <div className="absolute -bottom-24 -left-20 w-[380px] h-[380px] rounded-full blur-3xl opacity-25 float-b" style={{ background: "radial-gradient(circle, #4FB3A9 0%, transparent 60%)" }} />
          <div className="relative max-w-[1080px] mx-auto px-5 md:px-10 grid md:grid-cols-2 gap-12 items-center">
            <div>
              <span className="eyebrow">Scan · Chat · Done</span>
              <h2 className="mt-4 text-[34px] md:text-[44px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
                One QR code. <span className="serif-italic text-primary">Honest feedback before they leave.</span>
              </h2>
              <p className="mt-5 text-[16px] text-body max-w-[480px]">
                Bad reviews arrive too late. Paper cards get ignored. VoxBulk catches how customers feel while they are
                still in your venue — no app, no login, no long form.
              </p>
              <ul className="mt-6 space-y-2.5 text-[14.5px] text-body">
                <li className="flex items-center gap-2"><Check size={15} className="text-primary" /> Unique QR per location — table, counter, receipt or room</li>
                <li className="flex items-center gap-2"><Check size={15} className="text-primary" /> Buttons, free text or voice notes in any language</li>
                <li className="flex items-center gap-2"><Check size={15} className="text-primary" /> Live dashboard + weekly KPI email</li>
                <li className="flex items-center gap-2"><Check size={15} className="text-primary" /> Red flags so managers can recover unhappy guests</li>
              </ul>
            </div>
            <div className="relative mx-auto">
              <div className="relative w-[280px] h-[280px] md:w-[320px] md:h-[320px] rounded-3xl bg-white border border-border shadow-elevated p-6 flex items-center justify-center">
                <div className="absolute -top-3 left-6 inline-flex items-center gap-1.5 px-3 h-7 rounded-full bg-navy text-white text-[11px] font-bold uppercase tracking-[0.14em]">
                  <span className="w-1.5 h-1.5 rounded-full bg-teal pulse-dot" /> Live
                </div>
                <svg viewBox="0 0 33 33" width="100%" height="100%" shapeRendering="crispEdges" aria-label="Sample QR code">
                  {(() => {
                    const cells: React.ReactElement[] = [];
                    const seed = (x: number, y: number) => ((x * 928371 + y * 12345 + 7) % 7) > 3;
                    for (let y = 0; y < 33; y++) for (let x = 0; x < 33; x++) {
                      if (seed(x, y)) cells.push(<rect key={`${x}-${y}`} x={x} y={y} width={1} height={1} fill="#0A1628" />);
                    }
                    return cells;
                  })()}
                  {[[0, 0], [26, 0], [0, 26]].map(([x, y], i) => (
                    <g key={i}>
                      <rect x={x} y={y} width={7} height={7} fill="#0A1628" />
                      <rect x={x + 1} y={y + 1} width={5} height={5} fill="#fff" />
                      <rect x={x + 2} y={y + 2} width={3} height={3} fill="#0A1628" />
                    </g>
                  ))}
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

        <section className="py-16 md:py-20 bg-beige">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10 grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {highlights.map((h) => (
              <div key={h.title} className="bg-white border border-border rounded-2xl p-5">
                <div className="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
                  <h.icon size={18} />
                </div>
                <h3 className="mt-3 text-[15px] font-bold text-heading">{h.title}</h3>
                <p className="mt-1.5 text-[13.5px] text-body leading-[1.6]">{h.body}</p>
              </div>
            ))}
          </div>
        </section>

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
                  <div className="max-w-[78%] rounded-2xl rounded-tl-sm bg-beige px-3 py-2 text-[13px] text-heading inline-flex items-center gap-1.5">
                    <Mic size={12} className="text-gold" /> Voice note · 0:11
                  </div>
                </div>
                <div className="mt-4 pt-3 border-t border-border flex items-center justify-between text-[11px] text-muted-text">
                  <span className="inline-flex items-center gap-1.5"><Languages size={11} /> Auto-detected by phone country</span>
                  <span className="font-semibold text-success">→ EN in dashboard</span>
                </div>
              </div>
              <span className="absolute -top-3 -left-3 inline-flex items-center gap-1.5 px-3 h-7 rounded-full bg-navy text-white text-[11px] font-bold uppercase tracking-[0.14em]">
                <Languages size={12} className="text-gold" /> 50+ languages
              </span>
            </div>
            <div className="order-1 md:order-2">
              <span className="eyebrow">Multi-language</span>
              <h2 className="mt-4 text-[34px] md:text-[44px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
                Customer chats in theirs. <span className="serif-italic text-primary">You read English.</span>
              </h2>
              <p className="mt-5 text-[16px] text-body max-w-[520px]">
                Scan the QR and WhatsApp opens to VoxBulk. Language is auto-detected from the mobile country code and
                message — the dashboard keeps the original, translation, voice recording, sentiment and location tag together.
              </p>
              <ul className="mt-6 space-y-2.5 text-[14.5px] text-body">
                <li className="flex items-center gap-2"><Check size={15} className="text-primary" /> 50+ languages including English, Arabic, Chinese, Spanish, French, Hindi</li>
                <li className="flex items-center gap-2"><Check size={15} className="text-primary" /> Right-to-left scripts (Arabic, Hebrew) handled natively</li>
                <li className="flex items-center gap-2"><Check size={15} className="text-primary" /> Voice notes transcribed and translated for managers</li>
                <li className="flex items-center gap-2"><Check size={15} className="text-primary" /> No app, no signup — runs entirely inside WhatsApp</li>
              </ul>
              <div className="mt-6 flex flex-wrap gap-2">
                {["English", "العربية", "中文", "Español", "Français", "हिन्दी", "Português", "Türkçe", "Deutsch", "Italiano", "+40 more"].map((l) => (
                  <span key={l} className="inline-flex items-center gap-1.5 px-3 h-7 rounded-full bg-white border border-border text-[12px] font-semibold text-heading">
                    <MessageCircle size={11} className="text-teal" /> {l}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section className="py-24 md:py-28 bg-white">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10">
            <div className="text-center max-w-[680px] mx-auto">
              <span className="eyebrow">How it works</span>
              <h2 className="mt-4 text-[36px] md:text-[48px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
                Three steps. <span className="serif-italic text-primary">One QR code.</span>
              </h2>
            </div>
            <div className="mt-14 grid md:grid-cols-3 gap-5">
              {steps.map((st) => (
                <div key={st.n} className="bg-white border border-border rounded-2xl p-7 shadow-elegant">
                  <div className="w-14 h-14 rounded-full bg-navy text-gold flex items-center justify-center font-bold">{st.n}</div>
                  <h3 className="mt-4 text-[19px] font-bold text-heading">{st.title}</h3>
                  <p className="mt-2 text-[14.5px] text-body leading-[1.65]">{st.body}</p>
                </div>
              ))}
            </div>
            <div className="mt-10 grid md:grid-cols-2 gap-5">
              <div className="rounded-2xl border border-border bg-beige/60 p-6">
                <div className="inline-flex items-center gap-2 text-[12px] font-bold uppercase tracking-[0.12em] text-muted-text">
                  <AlertTriangle size={14} className="text-primary" /> Before VoxBulk
                </div>
                <ul className="mt-4 space-y-2 text-[14px] text-body">
                  <li className="flex gap-2"><span className="text-muted-text">·</span> Paper cards, lost receipts and late Google reviews</li>
                  <li className="flex gap-2"><span className="text-muted-text">·</span> No clear view of which branch is underperforming</li>
                  <li className="flex gap-2"><span className="text-muted-text">·</span> Manual translation for Arabic, French and Spanish</li>
                  <li className="flex gap-2"><span className="text-muted-text">·</span> Voice feedback disappears because customers will not type</li>
                </ul>
              </div>
              <div className="rounded-2xl border border-border bg-white p-6 shadow-elegant">
                <div className="inline-flex items-center gap-2 text-[12px] font-bold uppercase tracking-[0.12em] text-primary">
                  <Check size={14} /> With VoxBulk
                </div>
                <ul className="mt-4 space-y-2 text-[14px] text-body">
                  <li className="flex gap-2"><Check size={14} className="text-primary shrink-0 mt-0.5" /> Location-tagged feedback in real time</li>
                  <li className="flex gap-2"><Check size={14} className="text-primary shrink-0 mt-0.5" /> Colour-coded graphs compare every branch</li>
                  <li className="flex gap-2"><Check size={14} className="text-primary shrink-0 mt-0.5" /> Voice notes + AI themes and weekly actions</li>
                  <li className="flex gap-2"><Check size={14} className="text-primary shrink-0 mt-0.5" /> Red flags before complaints become public reviews</li>
                </ul>
              </div>
            </div>
          </div>
        </section>

        <section className="py-24 md:py-28 bg-beige">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10">
            <div className="max-w-[680px]">
              <span className="eyebrow">Who it's for</span>
              <h2 className="mt-4 text-[36px] md:text-[48px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
                Built for businesses with <span className="serif-italic text-primary">real customers</span>.
              </h2>
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

        <StatsRow
          items={[
            { value: "~30s", label: "average finish time" },
            { value: "50+", label: "languages, auto-translated" },
            { value: "3×", label: "more responses than paper or web forms" },
            { value: "Live", label: "multi-location dashboard" },
          ]}
        />

        <section className="py-24 md:py-28 bg-beige">
          <div className="max-w-[1080px] mx-auto px-5 md:px-10">
            <div className="text-center max-w-[680px] mx-auto">
              <span className="eyebrow">Pricing</span>
              <h2 className="mt-4 text-[36px] md:text-[48px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">Simple plans.</h2>
              <div className="mt-6 flex justify-center">
                <BillingToggle value={billing} onChange={setBilling} />
              </div>
            </div>
            {feedbackPricing.loading && (
              <p className="mt-10 text-center text-[14px] text-muted-text">Loading plans…</p>
            )}
            {!feedbackPricing.loading && plans.length === 0 && (
              <p className="mt-10 text-center text-[14px] text-muted-text">
                {feedbackPricing.error || "Plans unavailable right now."}{" "}
                <Link to="/contact" className="text-primary font-semibold underline-offset-2 hover:underline">Contact us</Link>
              </p>
            )}
            <div className="mt-12 grid md:grid-cols-3 gap-5">
              {plans.map((p) => (
                <div
                  key={p.code}
                  className={`relative rounded-2xl p-6 flex flex-col ${p.is_featured ? "bg-navy text-white border-2 border-gold shadow-elevated" : "bg-white border border-border shadow-elegant"}`}
                >
                  {p.is_featured && (
                    <span className="absolute -top-3 left-5 text-[10.5px] font-bold uppercase tracking-[0.14em] px-2.5 py-1 rounded-full bg-gold text-navy">
                      Most popular
                    </span>
                  )}
                  <div className={`text-[14px] font-semibold ${p.is_featured ? "text-white/90" : "text-heading"}`}>{p.name}</div>
                  {p.description ? (
                    <p className={`mt-1 text-[12.5px] ${p.is_featured ? "text-white/60" : "text-muted-text"}`}>{p.description}</p>
                  ) : null}
                  <div className="mt-3 flex items-baseline gap-1">
                    <span className={`text-[32px] font-bold tracking-[-0.02em] ${p.is_featured ? "text-gold" : "text-heading"}`}>
                      {planPriceDisplay(p, billing, s)}
                    </span>
                    <span className={`text-[13px] ${p.is_featured ? "text-white/60" : "text-muted-text"}`}>
                      {billing === "yearly" ? "/yr" : "/mo"}
                    </span>
                  </div>
                  <ul className={`mt-5 space-y-2.5 text-[14px] flex-1 ${p.is_featured ? "text-white/80" : "text-body"}`}>
                    {(p.features?.length ? p.features : []).map((f) => (
                      <li key={f} className="flex items-center gap-2">
                        <Check size={13} className={p.is_featured ? "text-gold" : "text-primary"} /> {f}
                      </li>
                    ))}
                  </ul>
                  <Link
                    to="/contact"
                    className={`mt-6 w-full inline-flex items-center justify-center gap-1.5 h-10 rounded-xl font-semibold text-[13.5px] transition-all ${p.is_featured ? "bg-gold text-navy hover:brightness-105" : "bg-navy text-white hover:bg-navy/90"}`}
                  >
                    Get started <ArrowRight size={13} />
                  </Link>
                </div>
              ))}
            </div>
            <p className="mt-8 text-center text-[13px] text-muted-text">
              WhatsApp delivery included · Cancel anytime with 30 days notice ·{" "}
              <Link to="/pricing" search={{ product: "feedback" }} className="text-primary font-semibold underline-offset-2 hover:underline">
                Full pricing
              </Link>
            </p>
          </div>
        </section>

        <section className="py-24 md:py-28 bg-white">
          <div className="max-w-[860px] mx-auto px-5 md:px-10">
            <div className="text-center">
              <span className="eyebrow">FAQ</span>
              <h2 className="mt-4 text-[36px] md:text-[48px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
                Questions, <span className="serif-italic text-primary">answered</span>.
              </h2>
            </div>
            <div className="mt-12 divide-y divide-border border-y border-border">
              {faqs.map((item, i) => {
                const open = openIdx === i;
                return (
                  <div key={item.q}>
                    <button
                      type="button"
                      onClick={() => setOpenIdx(open ? null : i)}
                      className="w-full flex items-center justify-between text-left py-5 gap-6"
                      aria-expanded={open}
                    >
                      <span className="text-[16px] md:text-[17px] font-semibold text-heading">{item.q}</span>
                      <span className={`w-8 h-8 rounded-full border border-border flex items-center justify-center transition-transform ${open ? "rotate-45 bg-navy text-gold border-navy" : "text-heading"}`}>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                          <line x1="12" y1="5" x2="12" y2="19" />
                          <line x1="5" y1="12" x2="19" y2="12" />
                        </svg>
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
