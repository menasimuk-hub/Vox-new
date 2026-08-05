import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import {
  ArrowRight, Check, QrCode, MessageCircle, ScanLine, FileDown, BellRing,
  Flame, Thermometer, Snowflake, Users, UserCircle2, Layers, Download,
  ShieldCheck, FlaskConical, Building2, Briefcase,
} from "lucide-react";
import { ServiceHero } from "@/components/HeroSlider";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { BottomCTA } from "@/components/VOXBULKHome";
import { useCurrency, SYM, FX } from "@/components/CurrencyContext";

export const Route = createFileRoute("/smart-card/")({
  head: () => ({
    meta: [
      { title: "Smart Card QR — A Personal Lead-Capture QR for Every Rep" },
      {
        name: "description",
        content:
          "One QR per sales rep. Prospects scan, chat on WhatsApp or web, and the scored lead lands in your dashboard — tied to that rep. From $5 per seat per month.",
      },
      { property: "og:title", content: "Smart Card QR — A Personal Lead-Capture QR for Every Rep" },
      { property: "og:description", content: "Your rep's QR. Their leads. Your dashboard." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
    links: [{ rel: "canonical", href: "https://voxbulk.com/smart-card" }],
  }),
  component: SmartCardPage,
});

const steps = [
  { n: "01", title: "Set up your company", body: "Company profile, branding and product catalogue in one place." },
  { n: "02", title: "Choose your questions", body: "Pick the qualifying questions every prospect should answer." },
  { n: "03", title: "Create a QR per rep", body: "One seat = one rep = one QR. Download as PNG in seconds." },
  { n: "04", title: "Rep shares their QR", body: "Phone wallpaper, lanyard, email signature or a printed card." },
  { n: "05", title: "Prospect scans and chats", body: "WhatsApp or web questionnaire, with product files sent in the same flow." },
  { n: "06", title: "Lead scored and routed", body: "Saved to your dashboard, attributed to the rep, hot leads alerted instantly." },
];

const features = [
  { icon: QrCode, title: "One QR per representative", body: "Every lead is attributed to the rep whose code was scanned." },
  { icon: MessageCircle, title: "WhatsApp or web flow", body: "Prospects pick the channel they prefer — both capture the same structured data." },
  { icon: ScanLine, title: "Business-card photo OCR", body: "Reads name, company, email and phone straight from a photographed card." },
  { icon: Layers, title: "Qualifying question bank", body: "The same question family as Expo — interest, role, timeline, follow-up." },
  { icon: FileDown, title: "Catalogue & PDF matching", body: "The right brochure or price list is sent based on what the prospect wants." },
  { icon: Flame, title: "Hot / Warm / Cold scoring", body: "Automatic scoring so reps chase the right people first." },
  { icon: BellRing, title: "Hot-lead WhatsApp alert", body: "The rep's mobile buzzes the moment a hot lead completes the flow." },
  { icon: UserCircle2, title: "Representative login", body: "Each rep sees only their own leads. Owners and managers see everyone's." },
  { icon: Download, title: "QR download as PNG", body: "Print-ready files for cards, lanyards, wallpapers and signatures." },
  { icon: FlaskConical, title: "15 free preview tests", body: "Run the full flow 15 times before you buy a single seat." },
  { icon: ShieldCheck, title: "Unlimited scans & leads", body: "No per-lead fees inside an active subscription." },
  { icon: Users, title: "Monthly or yearly seats", body: "Add and remove reps as the team changes. Pay yearly and save 20%." },
];

const audiences = [
  { icon: Users, title: "Sales & field teams", body: "Every meeting ends with a structured, scored lead instead of a paper card." },
  { icon: Briefcase, title: "Account managers", body: "Share files, capture intent, and keep the relationship history in one system." },
  { icon: Building2, title: "Franchise networks", body: "Consistent capture across locations, with per-rep and per-branch visibility." },
];

const lines = [
  "Your rep's QR. Their leads. Your dashboard.",
  "Paper card out. Smart QR in.",
  "Scan. Chat. Lead captured.",
  "One seat. One rep. One QR.",
];

const faqs = [
  { q: "How is a seat counted?", a: "One seat equals one rep with one personal QR code. Add or remove seats as your team changes." },
  { q: "Can I try it before buying?", a: "Yes — you get 15 free preview tests of the complete flow before you buy seats." },
  { q: "Can reps see each other's leads?", a: "No. Each rep logs in and sees only their own leads. Owners and managers see everything." },
  { q: "How do I pay?", a: "Card for monthly or yearly billing, or Direct Debit via GoCardless where available. Yearly saves 20%." },
  { q: "How is this different from Expo?", a: "Expo is a one-off purchase for an exhibition booth. Smart Card QR is a per-rep subscription for everyday selling." },
  { q: "Are there limits on scans or leads?", a: "No. Scans and leads are unlimited while the subscription is active." },
];

function RepCardMock() {
  const cells: React.ReactElement[] = [];
  const seed = (x: number, y: number) => ((x * 512219 + y * 9173 + 5) % 7) > 3;
  for (let y = 0; y < 25; y++) for (let x = 0; x < 25; x++) if (seed(x, y)) cells.push(<rect key={`${x}-${y}`} x={x} y={y} width={1} height={1} fill="#0A1628" />);
  return (
    <div className="relative mx-auto w-full max-w-[360px]">
      <div className="rounded-2xl border border-white/10 bg-[#0E1A2E] shadow-elevated p-5 text-white">
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-full bg-gradient-to-br from-gold to-blue-400 flex items-center justify-center text-navy font-bold text-[13px]">SR</div>
          <div className="min-w-0">
            <div className="text-[15px] font-bold leading-tight">Sara Redwood</div>
            <div className="text-[12px] text-white/55 leading-tight">Senior Account Manager</div>
          </div>
          <span className="ml-auto inline-flex items-center gap-1.5 px-2.5 h-6 rounded-full bg-white/[0.08] border border-white/15 text-[10px] font-semibold uppercase tracking-[0.12em] text-white/80 whitespace-nowrap">
            Seat 1
          </span>
        </div>
        <div className="mt-5 rounded-xl bg-white p-3">
          <svg viewBox="0 0 25 25" width="100%" height="100%" shapeRendering="crispEdges" aria-label="Sample representative QR code">
            {cells}
            {[[0, 0], [18, 0], [0, 18]].map(([x, y], i) => (
              <g key={i}>
                <rect x={x} y={y} width={7} height={7} fill="#0A1628" />
                <rect x={x + 1} y={y + 1} width={5} height={5} fill="#fff" />
                <rect x={x + 2} y={y + 2} width={3} height={3} fill="#0A1628" />
              </g>
            ))}
            <rect x={9} y={9} width={7} height={7} fill="#fff" />
            <rect x={10} y={10} width={5} height={5} rx={1} fill="#D4A93A" />
          </svg>
        </div>
        <div className="mt-4 text-center text-[13px] text-white/70">Scan to connect · WhatsApp or web</div>
        <div className="mt-4 pt-4 border-t border-white/10 space-y-2">
          {[
            { n: "Oliver Marsden", t: "Hot", tone: "hot" },
            { n: "Grace Fletcher", t: "Warm", tone: "warm" },
            { n: "Callum Brady", t: "Cold", tone: "cold" },
          ].map((l) => (
            <div key={l.n} className="flex items-center gap-2 text-[12.5px]">
              <span className="flex-1 truncate text-white/80">{l.n}</span>
              <span
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-[0.1em] ${
                  l.tone === "hot" ? "bg-gold/20 text-gold" : l.tone === "warm" ? "bg-blue-400/15 text-blue-300" : "bg-white/10 text-white/55"
                }`}
              >
                {l.tone === "hot" ? <Flame size={10} /> : l.tone === "warm" ? <Thermometer size={10} /> : <Snowflake size={10} />}
                {l.t}
              </span>
            </div>
          ))}
        </div>
      </div>
      <span className="absolute -top-4 -left-4 w-2.5 h-2.5 rounded-full bg-teal shadow-[0_0_12px_2px_rgba(79,179,169,0.6)] float-a" />
      <span className="absolute -bottom-4 -right-4 w-2 h-2 rounded-full bg-gold shadow-[0_0_12px_2px_rgba(212,169,58,0.55)] float-b" />
    </div>
  );
}

function SmartCardPage() {
  const { currency: cur } = useCurrency();
  const s = SYM[cur];
  const [openIdx, setOpenIdx] = useState<number | null>(0);
  const [yearly, setYearly] = useState(false);

  // Base price is $5 per seat / month; converted via GBP-pegged FX table.
  const monthly = (5 / FX.usd) * FX[cur];
  const yearlyTotal = monthly * 12 * 0.8;
  const shown = yearly ? yearlyTotal : monthly;
  const fmt = (n: number) => `${s}${n < 20 ? n.toFixed(2) : Math.round(n)}`;

  return (
    <div className="bg-background text-body antialiased">
      <SiteHeader />
      <main>
        <ServiceHero service="smart-card" />

        {/* What it is */}
        <section className="py-20 md:py-24 bg-white">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10 grid lg:grid-cols-2 gap-14 items-center">
            <div>
              <span className="eyebrow">What it is</span>
              <h2 className="mt-4 text-[32px] md:text-[44px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
                Paper card out. <span className="serif-italic text-primary">Smart QR in.</span>
              </h2>
              <p className="mt-5 text-[16px] text-body max-w-[520px] leading-[1.7]">
                Every rep carries one personal QR — on a phone wallpaper, lanyard, email signature or printed card.
                When someone scans it, a short WhatsApp or web conversation starts. The lead is captured, scored and
                attributed to that rep, with your product files sent in the same flow.
              </p>
              <ul className="mt-6 space-y-2.5 text-[14.5px] text-body">
                <li className="flex items-start gap-2"><Check size={16} className="text-primary mt-0.5 shrink-0" /> One seat = one rep = one QR</li>
                <li className="flex items-start gap-2"><Check size={16} className="text-primary mt-0.5 shrink-0" /> Business-card photo OCR fills the contact details</li>
                <li className="flex items-start gap-2"><Check size={16} className="text-primary mt-0.5 shrink-0" /> Reps see their own leads, managers see everyone's</li>
                <li className="flex items-start gap-2"><Check size={16} className="text-primary mt-0.5 shrink-0" /> 15 free preview tests before you buy seats</li>
              </ul>
            </div>
            <RepCardMock />
          </div>
        </section>

        {/* Short lines ticker */}
        <section className="py-8 bg-navy text-white overflow-hidden">
          <div className="flex gap-10 whitespace-nowrap animate-ticker text-[14px] font-semibold text-white/70">
            {[...lines, ...lines].map((l, i) => (
              <span key={i} className="inline-flex items-center gap-3">
                <span className="w-1.5 h-1.5 rounded-full bg-gold" /> {l}
              </span>
            ))}
          </div>
        </section>

        {/* How it works */}
        <section className="py-20 md:py-24 bg-beige">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10">
            <div className="max-w-[680px]">
              <span className="eyebrow">How it works</span>
              <h2 className="mt-4 text-[32px] md:text-[44px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
                Scan. Chat. <span className="serif-italic text-primary">Lead captured.</span>
              </h2>
            </div>
            <div className="mt-12 grid md:grid-cols-2 lg:grid-cols-3 gap-5">
              {steps.map((st) => (
                <div key={st.n} className="card-soft p-6">
                  <div className="text-[12px] font-bold tracking-[0.16em] text-primary">{st.n}</div>
                  <h3 className="mt-3 text-[18px] font-bold text-heading leading-snug">{st.title}</h3>
                  <p className="mt-2 text-[14.5px] text-body leading-[1.65]">{st.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Features */}
        <section className="py-20 md:py-24 bg-white">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10">
            <div className="max-w-[680px]">
              <span className="eyebrow">Key features</span>
              <h2 className="mt-4 text-[32px] md:text-[44px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
                Built for teams who meet people <span className="serif-italic text-primary">every day</span>.
              </h2>
            </div>
            <div className="mt-10 grid sm:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-7">
              {features.map((f) => (
                <div key={f.title} className="flex gap-3">
                  <span className="shrink-0 w-9 h-9 rounded-xl bg-navy text-gold flex items-center justify-center">
                    <f.icon size={16} />
                  </span>
                  <div>
                    <div className="text-[15px] font-bold text-heading">{f.title}</div>
                    <p className="mt-1 text-[13.5px] text-body leading-[1.6]">{f.body}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Who it's for */}
        <section className="py-20 md:py-24 bg-beige">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10">
            <div className="max-w-[680px]">
              <span className="eyebrow">Who it's for</span>
              <h2 className="mt-4 text-[32px] md:text-[44px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
                A trackable QR instead of a <span className="serif-italic text-primary">paper business card</span>.
              </h2>
            </div>
            <div className="mt-10 grid md:grid-cols-3 gap-5">
              {audiences.map((a) => (
                <div key={a.title} className="card-soft p-7">
                  <div className="w-11 h-11 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
                    <a.icon size={20} />
                  </div>
                  <h3 className="mt-5 text-[18px] font-bold text-heading">{a.title}</h3>
                  <p className="mt-2 text-[14.5px] text-body leading-[1.6]">{a.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Pricing */}
        <section id="pricing" className="py-20 md:py-24 bg-white scroll-mt-24">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10">
            <div className="max-w-[680px]">
              <span className="eyebrow">Pricing</span>
              <h2 className="mt-4 text-[32px] md:text-[44px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
                Subscription <span className="serif-italic text-primary">per seat</span>.
              </h2>
              <p className="mt-4 text-[16px] text-body">
                One seat = one rep = one QR. From $5 per seat per month, with local currency equivalents. Pay yearly and save 20%.
              </p>
            </div>

            <div className="mt-10 grid lg:grid-cols-[1fr_0.9fr] gap-5 items-start">
              <div className="rounded-2xl bg-navy border border-navy text-white p-7 md:p-9 shadow-elevated">
                <div className="flex flex-wrap items-center gap-3 justify-between">
                  <div className="text-[13px] font-bold uppercase tracking-[0.14em] text-gold">Smart Card QR — Seat</div>
                  <div className="inline-flex p-1 rounded-lg bg-white/[0.08] border border-white/15">
                    {[
                      { k: false, l: "Monthly" },
                      { k: true, l: "Yearly · −20%" },
                    ].map((o) => (
                      <button
                        key={o.l}
                        onClick={() => setYearly(o.k)}
                        className={`px-3 h-8 rounded-md text-[12.5px] font-semibold transition-colors ${
                          yearly === o.k ? "bg-white text-navy" : "text-white/70 hover:text-white"
                        }`}
                      >
                        {o.l}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="mt-6 flex items-end gap-2">
                  <span className="text-[46px] md:text-[54px] font-bold tracking-[-0.035em] leading-none">{fmt(shown)}</span>
                  <span className="pb-1.5 text-[14px] text-white/60">/ seat / {yearly ? "year" : "month"}</span>
                </div>
                <div className="mt-2 text-[13.5px] text-white/60">
                  {yearly
                    ? `Billed annually · equivalent to ${fmt(yearlyTotal / 12)} per seat per month`
                    : `Billed monthly · switch to yearly and pay ${fmt(yearlyTotal)} per seat per year`}
                </div>
                <ul className="mt-7 grid sm:grid-cols-2 gap-y-2.5 gap-x-6">
                  {[
                    "Unlimited scans and leads",
                    "WhatsApp and web capture",
                    "Business-card photo OCR",
                    "Hot / Warm / Cold scoring",
                    "Hot-lead WhatsApp alerts",
                    "Rep login + manager view",
                    "Catalogue & PDF delivery",
                    "QR download as PNG",
                  ].map((f) => (
                    <li key={f} className="flex items-start gap-2 text-[14px] text-white/80">
                      <Check size={15} className="text-gold mt-0.5 shrink-0" /> {f}
                    </li>
                  ))}
                </ul>
                <Link to="/contact" className="mt-8 btn-primary text-[15px] h-12 px-6">
                  Add seats <ArrowRight size={16} />
                </Link>
              </div>

              <div className="space-y-5">
                <div className="rounded-2xl border border-border bg-white p-7 shadow-elegant">
                  <h3 className="text-[17px] font-bold text-heading">Billing options</h3>
                  <ul className="mt-4 space-y-2.5 text-[14.5px] text-body">
                    <li className="flex items-start gap-2"><Check size={15} className="text-primary mt-0.5 shrink-0" /> Monthly — card, or Direct Debit (GoCardless) where available</li>
                    <li className="flex items-start gap-2"><Check size={15} className="text-primary mt-0.5 shrink-0" /> Yearly — card payment with a 20% discount</li>
                    <li className="flex items-start gap-2"><Check size={15} className="text-primary mt-0.5 shrink-0" /> 15 free preview tests before you buy seats</li>
                  </ul>
                </div>
                <div className="rounded-2xl border border-border bg-beige p-7">
                  <h3 className="text-[17px] font-bold text-heading">Example (USD)</h3>
                  <div className="mt-4 space-y-2 text-[14.5px] text-body">
                    <div className="flex items-center justify-between"><span>Monthly</span><span className="font-semibold text-heading">$5 / seat / month</span></div>
                    <div className="flex items-center justify-between"><span>Yearly</span><span className="font-semibold text-heading">$48 / seat / year</span></div>
                  </div>
                  <p className="mt-3 text-[13px] text-muted-text">Local equivalents shown automatically based on your country.</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Expo vs Smart Card */}
        <section className="py-16 md:py-20 bg-beige">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10 grid md:grid-cols-2 gap-5">
            <div className="rounded-2xl border border-border bg-white p-7">
              <div className="text-[12px] font-bold uppercase tracking-[0.14em] text-primary">Expo</div>
              <p className="mt-3 text-[16px] text-body leading-[1.65]">
                For exhibition stands — pay once per show, one QR per booth.
              </p>
              <Link to="/expo" className="mt-5 inline-flex items-center gap-1.5 text-[14px] font-semibold text-primary hover:gap-2.5 transition-all">
                Explore VoxBulk Expo <ArrowRight size={14} />
              </Link>
            </div>
            <div className="rounded-2xl border border-navy bg-navy text-white p-7">
              <div className="text-[12px] font-bold uppercase tracking-[0.14em] text-gold">Smart Card QR</div>
              <p className="mt-3 text-[16px] text-white/80 leading-[1.65]">
                For sales reps every day — subscribe per rep, one QR per person.
              </p>
            </div>
          </div>
        </section>

        {/* FAQ */}
        <section className="py-20 md:py-24 bg-white">
          <div className="max-w-[880px] mx-auto px-5 md:px-10">
            <span className="eyebrow">Questions</span>
            <h2 className="mt-4 text-[32px] md:text-[42px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
              Smart Card QR, answered.
            </h2>
            <div className="mt-10 divide-y divide-border border-y border-border">
              {faqs.slice(0, 4).map((f, i) => (
                <div key={f.q}>
                  <button
                    onClick={() => setOpenIdx(openIdx === i ? null : i)}
                    className="w-full flex items-center justify-between gap-4 py-5 text-left"
                  >
                    <span className="text-[16px] font-semibold text-heading">{f.q}</span>
                    <span className={`shrink-0 text-primary transition-transform ${openIdx === i ? "rotate-45" : ""}`}>+</span>
                  </button>
                  {openIdx === i && <p className="pb-5 text-[15px] text-body leading-[1.7] max-w-[720px]">{f.a}</p>}
                </div>
              ))}
            </div>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
              <Link to="/help" className="btn-outline text-[14px]">See all FAQs <ArrowRight size={14} /></Link>
              <Link to="/contact" className="text-[14px] font-semibold text-primary hover:underline">Still have questions? Talk to us</Link>
            </div>
          </div>
        </section>

        <BottomCTA />
      </main>
      <SiteFooter />
    </div>
  );
}
