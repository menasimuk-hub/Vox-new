import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import {
  ArrowRight, Check, QrCode, MessageCircle, ScanLine, FileDown, BellRing,
  Flame, Thermometer, Snowflake, Building2, Users, Briefcase, Gift, Contact,
  CalendarDays, Sparkles,
} from "lucide-react";
import { ServiceHero } from "@/components/HeroSlider";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { BottomCTA } from "@/components/VOXBULKHome";
import { useCurrency, SYM, FX } from "@/components/CurrencyContext";

export const Route = createFileRoute("/expo")({
  head: () => ({
    meta: [
      { title: "VoxBulk Expo — Exhibition Lead Capture by QR" },
      {
        name: "description",
        content:
          "Visitors scan your booth QR, leave details on WhatsApp or a quick form, and the lead lands in your VoxBulk dashboard — scored and exportable. Pay once per show.",
      },
      { property: "og:title", content: "VoxBulk Expo — Exhibition Lead Capture by QR" },
      {
        property: "og:description",
        content: "They scan your QR. You get the lead. No badge reader, no waiting for the organiser's export.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
    links: [{ rel: "canonical", href: "https://voxbulk.com/expo" }],
  }),
  component: ExpoPage,
});

const steps = [
  { n: "01", title: "Create your booth", body: "Set up the booth for your event inside VoxBulk and get a unique QR code." },
  { n: "02", title: "Set questions & files", body: "Choose your qualifying questions and upload the catalogue, brochures and price lists." },
  { n: "03", title: "Print the QR at your stand", body: "Download as PNG, print it on the stand, banner or table card." },
  { n: "04", title: "Visitors scan and complete", body: "WhatsApp in any language, or a quick web form in English. Under a minute." },
  { n: "05", title: "Leads scored automatically", body: "Every lead is saved and scored Hot, Warm or Cold as it arrives." },
  { n: "06", title: "Follow up or export", body: "Work leads from the dashboard, or export the whole show to CSV or Excel." },
];

const features = [
  { icon: QrCode, title: "Unique QR per booth", body: "One package, one booth, one code — tracked separately from every other show." },
  { icon: MessageCircle, title: "WhatsApp or web capture", body: "Visitors choose WhatsApp in any language, or a short English web form." },
  { icon: ScanLine, title: "Business-card photo", body: "They snap their card or type details — both land as structured contact data." },
  { icon: Sparkles, title: "Qualifying questions", body: "Interest, role, timeline, follow-up preference and more — your question set." },
  { icon: FileDown, title: "Catalogue delivery", body: "Send brochures and price lists in the same chat, or by email after the visit." },
  { icon: Flame, title: "Hot / Warm / Cold scoring", body: "Every lead is scored so your team knows who to call first on Monday." },
  { icon: BellRing, title: "Hot-lead alerts", body: "Optional WhatsApp alert to the stand mobile the moment a hot lead completes." },
  { icon: Gift, title: "Free-gift message", body: "Optional thank-you or gift message triggered after the visitor completes." },
  { icon: Contact, title: "Company card & vCard", body: "Visitors get your company card and can save your contact in one tap." },
];

const audiences = [
  { icon: Building2, title: "Exhibitors", body: "Own your lead data from the first hour of the show, not two weeks later." },
  { icon: Briefcase, title: "Brand teams", body: "Deliver catalogues and price lists instantly, with every download attributed." },
  { icon: Users, title: "Sales teams", body: "Structured, scored leads in your own system — ready for Monday follow-up." },
];

const lines = [
  "They scan your QR. You get the lead.",
  "Visitor scans. Lead in your dashboard.",
  "Skip the badge wait. Capture them at the stand.",
  "Pay once per show. Export leads after the event.",
];

const plans = [
  {
    name: "Expo 1 Day",
    gbp: 49,
    days: "Booth active 1 day",
    features: ["1 product category", "Up to 20 files", "Hot / Warm / Cold scoring", "Full CSV & Excel export"],
  },
  {
    name: "Expo 3 Days",
    gbp: 99,
    featured: true,
    days: "Booth active 3 days",
    features: ["Up to 3 categories", "Up to 40 files", "Hot / Warm / Cold scoring", "Full CSV & Excel export"],
  },
  {
    name: "Expo 7 Days",
    gbp: 149,
    days: "Booth active 7 days",
    features: [
      "Unlimited categories",
      "Up to 100 files",
      "Hot / Warm / Cold scoring",
      "Full CSV & Excel export",
      "Post-show follow-up ready",
      "AI summary report ready",
    ],
  },
];

const faqs = [
  { q: "Is this a subscription?", a: "No. Expo is a one-off purchase per exhibition. One package equals one booth QR. Buy again for another booth or another show." },
  { q: "Do I need a badge scanner?", a: "No hardware at all. The visitor uses their own phone to scan your printed QR code." },
  { q: "What if the show runs longer than my package?", a: "Pick the 3-day or 7-day package, or buy an additional package. The booth simply deactivates when the window ends." },
  { q: "Which languages are supported?", a: "The WhatsApp flow handles any language the visitor writes in. The web form is English." },
  { q: "Can I still get the organiser's badge data?", a: "Yes. Expo runs alongside it — the difference is that these leads are yours immediately and already scored." },
];

function LeadsMock() {
  const rows = [
    { name: "Oliver Marsden", co: "Marsden Interiors", tag: "Hot", tone: "hot", q: "Buying in 30 days" },
    { name: "Grace Fletcher", co: "Northgate Group", tag: "Hot", tone: "hot", q: "Requested price list" },
    { name: "Sam Whitfield", co: "Harlow Retail", tag: "Warm", tone: "warm", q: "Budget next quarter" },
    { name: "Aiko Tanaka", co: "Sakura Trading", tag: "Warm", tone: "warm", q: "Comparing suppliers" },
    { name: "Callum Brady", co: "Brady & Sons", tag: "Cold", tone: "cold", q: "Browsing only" },
  ];
  return (
    <div className="rounded-2xl border border-border bg-white shadow-elevated overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border bg-beige/60">
        <QrCode size={14} className="text-primary" />
        <span className="text-[12.5px] font-semibold text-heading">Expo → Leads</span>
        <span className="ml-auto inline-flex items-center gap-1.5 text-[11px] text-success font-semibold">
          <span className="w-1.5 h-1.5 rounded-full bg-success pulse-dot" /> Live · Hall 3, Stand C21
        </span>
      </div>
      <div className="divide-y divide-border">
        {rows.map((r) => (
          <div key={r.name} className="flex items-center gap-3 px-4 py-3">
            <div className="w-8 h-8 rounded-full bg-navy text-gold flex items-center justify-center text-[10px] font-bold shrink-0">
              {r.name.split(" ").map((n) => n[0]).join("")}
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-[13.5px] font-semibold text-heading truncate">{r.name}</div>
              <div className="text-[11.5px] text-muted-text truncate">{r.co} · {r.q}</div>
            </div>
            <span
              className={`shrink-0 inline-flex items-center gap-1 px-2 py-1 rounded-full text-[10.5px] font-bold uppercase tracking-[0.1em] ${
                r.tone === "hot" ? "bg-gold/20 text-[#8a6a1a]" : r.tone === "warm" ? "bg-primary/10 text-primary" : "bg-muted text-muted-text"
              }`}
            >
              {r.tone === "hot" ? <Flame size={11} /> : r.tone === "warm" ? <Thermometer size={11} /> : <Snowflake size={11} />}
              {r.tag}
            </span>
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between px-4 py-3 border-t border-border bg-beige/40 text-[11.5px] text-muted-text">
        <span>128 leads captured today</span>
        <span className="inline-flex items-center gap-1.5 font-semibold text-heading"><FileDown size={12} /> CSV · Excel</span>
      </div>
    </div>
  );
}

function BoothQR() {
  const cells: React.ReactElement[] = [];
  const seed = (x: number, y: number) => ((x * 733331 + y * 5711 + 13) % 7) > 3;
  for (let y = 0; y < 29; y++) for (let x = 0; x < 29; x++) if (seed(x, y)) cells.push(<rect key={`${x}-${y}`} x={x} y={y} width={1} height={1} fill="#0A1628" />);
  return (
    <div className="relative mx-auto w-[268px] rounded-3xl bg-white border border-border shadow-elevated p-5 text-center">
      <span className="absolute -top-3 left-1/2 -translate-x-1/2 inline-flex items-center gap-1.5 px-3 h-7 rounded-full bg-navy text-white text-[10.5px] font-bold uppercase tracking-[0.14em] whitespace-nowrap">
        <CalendarDays size={11} className="text-gold" /> Booth active · 3 days
      </span>
      <svg viewBox="0 0 29 29" width="100%" height="100%" shapeRendering="crispEdges" aria-label="Sample booth QR code" className="mt-2">
        {cells}
        {[[0, 0], [22, 0], [0, 22]].map(([x, y], i) => (
          <g key={i}>
            <rect x={x} y={y} width={7} height={7} fill="#0A1628" />
            <rect x={x + 1} y={y + 1} width={5} height={5} fill="#fff" />
            <rect x={x + 2} y={y + 2} width={3} height={3} fill="#0A1628" />
          </g>
        ))}
        <rect x={11} y={11} width={7} height={7} fill="#fff" />
        <rect x={12} y={12} width={5} height={5} rx={1} fill="#D4A93A" />
      </svg>
      <div className="mt-4 text-[15px] font-bold text-heading">Scan to leave your details</div>
      <div className="mt-1 text-[12.5px] text-muted-text">WhatsApp or quick form · Under a minute</div>
      <span className="absolute -top-4 -left-4 w-2.5 h-2.5 rounded-full bg-teal shadow-[0_0_12px_2px_rgba(79,179,169,0.6)] float-a" />
      <span className="absolute -bottom-4 -right-4 w-2 h-2 rounded-full bg-primary shadow-[0_0_12px_2px_rgba(30,111,217,0.55)] float-b" />
    </div>
  );
}

function ExpoPage() {
  const { currency: cur } = useCurrency();
  const s = SYM[cur];
  const fx = FX[cur];
  const [openIdx, setOpenIdx] = useState<number | null>(0);
  const price = (gbp: number) => `${s}${Math.round(gbp * fx)}`;

  return (
    <div className="bg-background text-body antialiased">
      <SiteHeader />
      <main>
        <ServiceHero service="expo" />

        {/* What it is */}
        <section className="py-20 md:py-24 bg-white">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10 grid lg:grid-cols-2 gap-12 items-center">
            <div>
              <span className="eyebrow">What it is</span>
              <h2 className="mt-4 text-[32px] md:text-[44px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
                Lead capture for <span className="serif-italic text-primary">one booth, one event</span>.
              </h2>
              <p className="mt-5 text-[16px] text-body max-w-[520px] leading-[1.7]">
                Most exhibitors scan visitor badges and then wait for the organiser's export. VoxBulk Expo works the
                other way around: the visitor scans your QR at the stand, answers your questions, and the lead is
                yours instantly.
              </p>
              <ul className="mt-6 space-y-2.5 text-[14.5px] text-body">
                <li className="flex items-start gap-2"><Check size={16} className="text-primary mt-0.5 shrink-0" /> Built for exhibition booths — no badge reader required</li>
                <li className="flex items-start gap-2"><Check size={16} className="text-primary mt-0.5 shrink-0" /> WhatsApp in any language, or an English web form</li>
                <li className="flex items-start gap-2"><Check size={16} className="text-primary mt-0.5 shrink-0" /> Catalogue and price list delivered in the same session</li>
                <li className="flex items-start gap-2"><Check size={16} className="text-primary mt-0.5 shrink-0" /> Leads appear under Expo → Leads, scored and exportable</li>
              </ul>
            </div>
            <LeadsMock />
          </div>
        </section>

        {/* Short lines strip */}
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
                Live at your stand in <span className="serif-italic text-primary">minutes</span>.
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

        {/* QR sign + features */}
        <section className="py-20 md:py-24 bg-white">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10 grid lg:grid-cols-[0.8fr_1.2fr] gap-14 items-start">
            <BoothQR />
            <div>
              <span className="eyebrow">Key features</span>
              <h2 className="mt-4 text-[30px] md:text-[40px] font-bold tracking-[-0.03em] text-heading leading-[1.06]">
                Everything the stand needs.
              </h2>
              <div className="mt-8 grid sm:grid-cols-2 gap-x-8 gap-y-6">
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
          </div>
        </section>

        {/* Who it's for */}
        <section className="py-20 md:py-24 bg-beige">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10">
            <div className="max-w-[680px]">
              <span className="eyebrow">Who it's for</span>
              <h2 className="mt-4 text-[32px] md:text-[44px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
                Structured leads in <span className="serif-italic text-primary">your own system</span>.
              </h2>
              <p className="mt-4 text-[16px] text-body">
                For trade shows, expos and multi-day events where waiting for someone else's export costs you the
                first week of follow-up.
              </p>
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
                One-off, <span className="serif-italic text-primary">per exhibition</span>.
              </h2>
              <p className="mt-4 text-[16px] text-body">
                One package = one booth QR. No monthly Expo subscription — buy again for another booth or another show.
              </p>
            </div>
            <div className="mt-12 grid md:grid-cols-3 gap-5 items-start">
              {plans.map((p) => (
                <div
                  key={p.name}
                  className={`relative rounded-2xl p-7 border ${
                    p.featured ? "bg-navy border-navy text-white shadow-elevated" : "bg-white border-border shadow-elegant"
                  }`}
                >
                  {p.featured && (
                    <span className="absolute -top-3 left-7 inline-flex items-center px-3 h-6 rounded-full bg-gold text-navy text-[10.5px] font-bold uppercase tracking-[0.14em]">
                      Most popular
                    </span>
                  )}
                  <div className={`text-[13px] font-bold uppercase tracking-[0.14em] ${p.featured ? "text-gold" : "text-primary"}`}>
                    {p.name}
                  </div>
                  <div className="mt-4 flex items-end gap-1.5">
                    <span className={`text-[40px] font-bold tracking-[-0.03em] ${p.featured ? "text-white" : "text-heading"}`}>
                      {price(p.gbp)}
                    </span>
                    <span className={`pb-2 text-[13.5px] ${p.featured ? "text-white/60" : "text-muted-text"}`}>/ exhibition</span>
                  </div>
                  <div className={`mt-2 text-[13.5px] font-semibold ${p.featured ? "text-white/75" : "text-heading"}`}>{p.days}</div>
                  <ul className="mt-6 space-y-2.5">
                    {p.features.map((f) => (
                      <li key={f} className={`flex items-start gap-2 text-[14px] ${p.featured ? "text-white/80" : "text-body"}`}>
                        <Check size={15} className={`mt-0.5 shrink-0 ${p.featured ? "text-gold" : "text-primary"}`} /> {f}
                      </li>
                    ))}
                  </ul>
                  <Link
                    to="/contact"
                    className={`mt-7 w-full ${p.featured ? "btn-primary" : "btn-outline"} text-[14.5px]`}
                  >
                    Get this package <ArrowRight size={15} />
                  </Link>
                </div>
              ))}
            </div>
            <p className="mt-6 text-[13.5px] text-muted-text">
              Also available in EUR, USD, CAD and AUD. Switch country at the bottom of the page to see your local price.
            </p>
          </div>
        </section>

        {/* Expo vs Smart Card */}
        <section className="py-16 md:py-20 bg-beige">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10 grid md:grid-cols-2 gap-5">
            <div className="rounded-2xl border border-navy bg-navy text-white p-7">
              <div className="text-[12px] font-bold uppercase tracking-[0.14em] text-gold">Expo</div>
              <p className="mt-3 text-[16px] text-white/80 leading-[1.65]">
                For exhibition stands — pay once per show, one QR per booth.
              </p>
            </div>
            <div className="rounded-2xl border border-border bg-white p-7">
              <div className="text-[12px] font-bold uppercase tracking-[0.14em] text-primary">Smart Card QR</div>
              <p className="mt-3 text-[16px] text-body leading-[1.65]">
                For sales reps every day — subscribe per rep, one QR per person.
              </p>
              <Link to="/smart-card" className="mt-5 inline-flex items-center gap-1.5 text-[14px] font-semibold text-primary hover:gap-2.5 transition-all">
                Explore Smart Card QR <ArrowRight size={14} />
              </Link>
            </div>
          </div>
        </section>

        {/* FAQ */}
        <section className="py-20 md:py-24 bg-white">
          <div className="max-w-[880px] mx-auto px-5 md:px-10">
            <span className="eyebrow">Questions</span>
            <h2 className="mt-4 text-[32px] md:text-[42px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
              Expo, answered.
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
