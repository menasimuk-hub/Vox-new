import { useEffect, useState, type ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import {
  ArrowRight, ArrowLeft, Headphones, ShieldCheck, Zap, Layers, Sparkles, MessageCircle,
  Inbox, QrCode, IdCard, Check, Flame, Thermometer, Snowflake, PhoneCall, Star, Languages,
  Clock, Users, Wallet, Globe, BarChart3, FileDown,
} from "lucide-react";
import { useTalkModal } from "@/components/TalkModal";

/* ---------- shared mock chrome ---------- */
function MockFrame({ label, live = "Live", tint = "#2A82EB", children }: { label: string; live?: string; tint?: string; children: ReactNode }) {
  return (
    <div className="relative w-full max-w-[560px] mx-auto">
      <div
        className="absolute inset-0 -m-6 rounded-[32px] blur-2xl"
        style={{ background: `radial-gradient(120% 100% at 20% 10%, ${tint}33, transparent 60%), radial-gradient(120% 100% at 85% 95%, ${tint}22, transparent 65%)` }}
      />
      <div
        className="relative rounded-2xl border bg-[#0E1A2E] shadow-elevated overflow-hidden"
        style={{ borderColor: `${tint}40` }}
      >
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-white/10 bg-white/[0.03]">
          <span className="w-2 h-2 rounded-full bg-white/20" />
          <span className="w-2 h-2 rounded-full bg-white/20" />
          <span className="ml-1.5 text-[11px] text-white/45 truncate">{label}</span>
          <span className="ml-auto inline-flex items-center gap-1.5 text-[10.5px] text-teal whitespace-nowrap">
            <span className="w-1.5 h-1.5 rounded-full bg-teal pulse-dot" /> {live}
          </span>
        </div>
        {children}
      </div>
    </div>
  );
}

function LeadTag({ tone }: { tone: "hot" | "warm" | "cold" }) {
  const map = {
    hot: { c: "bg-gold/20 text-gold", I: Flame, l: "Hot" },
    warm: { c: "bg-blue-400/15 text-blue-300", I: Thermometer, l: "Warm" },
    cold: { c: "bg-white/10 text-white/55", I: Snowflake, l: "Cold" },
  } as const;
  const { c, I, l } = map[tone];
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-[0.1em] whitespace-nowrap ${c}`}>
      <I size={10} /> {l}
    </span>
  );
}

/* ---------- per-service visuals ---------- */
function RecruitmentVisual() {
  return (
    <MockFrame label="voxbulk.com · recruitment" tint="#D4A93A">
      <div className="grid grid-cols-3 gap-px bg-white/5">
        {[["CVs scored", "1,248"], ["Avg ATS", "76"], ["Booked", "87"]].map(([l, v]) => (
          <div key={l} className="bg-[#0E1A2E] px-3 py-2">
            <div className="text-[10px] uppercase tracking-wider text-white/45">{l}</div>
            <div className="mt-0.5 text-[18px] font-bold text-white tracking-tight">{v}</div>
          </div>
        ))}
      </div>
      <div className="p-4">
        <div className="grid grid-cols-[1.5fr_0.6fr_0.6fr] gap-2 pb-1.5 text-[10px] uppercase tracking-wider text-white/40 border-b border-white/10">
          <span>Candidate</span><span className="text-right">ATS</span><span className="text-right">Interview</span>
        </div>
        <div className="divide-y divide-white/5">
          {[
            { n: "Amelia Carter", r: "Product Manager", a: 92, i: 89 },
            { n: "Joshua Reid", r: "Senior Engineer", a: 88, i: 84 },
            { n: "Ruby Lawson", r: "Backend Engineer", a: 81, i: 79 },
          ].map((c) => (
            <div key={c.n} className="grid grid-cols-[1.5fr_0.6fr_0.6fr] gap-2 items-center py-2">
              <div className="min-w-0">
                <div className="text-[12.5px] font-semibold text-white truncate leading-tight">{c.n}</div>
                <div className="text-[10.5px] text-white/45 truncate leading-tight">{c.r}</div>
              </div>
              <div className="text-right text-[13px] font-bold text-gold tabular-nums">{c.a}</div>
              <div className="text-right text-[13px] font-bold text-teal tabular-nums">{c.i}</div>
            </div>
          ))}
        </div>
        <div className="mt-3 rounded-xl bg-white/[0.04] border border-white/10 p-3 flex items-center gap-2.5">
          <span className="w-8 h-8 rounded-full bg-gradient-to-br from-gold to-blue-400 flex items-center justify-center text-navy font-bold text-[10px]">CH</span>
          <div className="flex-1 min-w-0">
            <div className="text-[12px] font-semibold text-white truncate">AI interview · Charlotte Hale</div>
            <div className="text-[10.5px] text-white/50 truncate">Skills 9.1 · Comms 8.7 · Fit 9.0</div>
          </div>
          <PhoneCall size={14} className="text-teal shrink-0" />
        </div>
      </div>
    </MockFrame>
  );
}

function SurveysVisual() {
  return (
    <MockFrame label="voxbulk.com · whatsapp surveys" tint="#4FB3A9" live="98% open">
      <div className="p-4 space-y-2.5">
        <div className="max-w-[80%] rounded-2xl rounded-tl-sm bg-white/[0.06] border border-white/10 px-3 py-2 text-[12.5px] text-white/85">
          Quick one — how likely are you to recommend us? 1–10
        </div>
        <div className="max-w-[60%] ml-auto rounded-2xl rounded-tr-sm bg-teal/15 border border-teal/25 px-3 py-2 text-[12.5px] text-teal">
          9 — really easy to deal with
        </div>
        <div className="max-w-[80%] rounded-2xl rounded-tl-sm bg-white/[0.06] border border-white/10 px-3 py-2 text-[12.5px] text-white/85">
          Thanks! Anything we should improve?
        </div>
        <div className="max-w-[72%] ml-auto rounded-2xl rounded-tr-sm bg-teal/15 border border-teal/25 px-3 py-2 text-[12.5px] text-teal inline-flex items-center gap-2">
          <span className="flex items-end gap-[2px] h-3">
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <span key={i} className="eq-bar w-[2px] h-full rounded-full bg-teal" style={{ animationDelay: `${i * 0.12}s` }} />
            ))}
          </span>
          Voice note · 0:14
        </div>
        <div className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-[11px] text-white/60">
          <span className="text-gold font-semibold">Any language in → English out.</span> Voice notes and replies are
          transcribed and translated automatically.
        </div>
      </div>
      <div className="grid grid-cols-3 gap-px bg-white/5 border-t border-white/10">
        {[["WhatsApp", "98%", "text-teal"], ["Email", "21%", "text-white/60"], ["SMS", "34%", "text-white/60"]].map(([l, v, c]) => (
          <div key={l} className="bg-[#0E1A2E] px-3 py-2.5">
            <div className="text-[10px] uppercase tracking-wider text-white/45">{l} open</div>
            <div className={`mt-0.5 text-[17px] font-bold tracking-tight ${c}`}>{v}</div>
          </div>
        ))}
      </div>
    </MockFrame>
  );
}

function FeedbackVisual() {
  const cells: React.ReactElement[] = [];
  const seed = (x: number, y: number) => ((x * 928371 + y * 12345 + 7) % 7) > 3;
  for (let y = 0; y < 25; y++) for (let x = 0; x < 25; x++) if (seed(x, y)) cells.push(<rect key={`${x}-${y}`} x={x} y={y} width={1} height={1} fill="#0A1628" />);
  return (
    <MockFrame label="voxbulk.com · customer feedback" tint="#D4A93A" live="Scanning">
      <div className="p-5 flex items-center gap-5">
        <div className="w-[132px] shrink-0 rounded-xl bg-white p-2.5">
          <svg viewBox="0 0 25 25" width="100%" height="100%" shapeRendering="crispEdges" aria-label="Sample QR code">
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
        <div className="min-w-0">
          <div className="text-[13px] font-semibold text-white">Scan · Chat · Done</div>
          <div className="mt-1 text-[11.5px] text-white/55">One QR per location · no app</div>
          <div className="mt-3 flex items-center gap-1">
            {[0, 1, 2, 3, 4].map((i) => <Star key={i} size={13} className="text-gold fill-gold" />)}
            <span className="ml-1.5 text-[12px] font-bold text-white">4.8</span>
          </div>
          <div className="mt-3 inline-flex items-center gap-1.5 px-2.5 h-6 rounded-full bg-white/[0.08] border border-white/15 text-[10.5px] text-white/75 whitespace-nowrap">
            <Languages size={11} className="text-gold" /> 50+ languages → English
          </div>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-px bg-white/5 border-t border-white/10">
        {[["Responses", "1,904"], ["Avg score", "4.8"], ["Reply rate", "62%"]].map(([l, v]) => (
          <div key={l} className="bg-[#0E1A2E] px-3 py-2.5">
            <div className="text-[10px] uppercase tracking-wider text-white/45">{l}</div>
            <div className="mt-0.5 text-[17px] font-bold text-white tracking-tight">{v}</div>
          </div>
        ))}
      </div>
    </MockFrame>
  );
}

function ExpoVisual() {
  return (
    <MockFrame label="voxbulk.com · expo → leads" tint="#2A82EB" live="Hall 3 · C21">
      <div className="grid grid-cols-3 gap-px bg-white/5">
        {[["Leads today", "128"], ["Hot", "34"], ["Booth active", "3d"]].map(([l, v]) => (
          <div key={l} className="bg-[#0E1A2E] px-3 py-2">
            <div className="text-[10px] uppercase tracking-wider text-white/45">{l}</div>
            <div className="mt-0.5 text-[18px] font-bold text-white tracking-tight">{v}</div>
          </div>
        ))}
      </div>
      <div className="p-4 divide-y divide-white/5">
        {[
          { n: "Oliver Marsden", c: "Marsden Interiors", t: "hot" as const },
          { n: "Grace Fletcher", c: "Northgate Group", t: "hot" as const },
          { n: "Sam Whitfield", c: "Harlow Retail", t: "warm" as const },
          { n: "Callum Brady", c: "Brady & Sons", t: "cold" as const },
        ].map((r) => (
          <div key={r.n} className="flex items-center gap-2.5 py-2">
            <span className="w-7 h-7 rounded-full bg-white/[0.06] border border-white/10 flex items-center justify-center text-[9.5px] font-bold text-gold shrink-0">
              {r.n.split(" ").map((x) => x[0]).join("")}
            </span>
            <div className="min-w-0 flex-1">
              <div className="text-[12.5px] font-semibold text-white truncate leading-tight">{r.n}</div>
              <div className="text-[10.5px] text-white/45 truncate leading-tight">{r.c}</div>
            </div>
            <LeadTag tone={r.t} />
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between px-4 py-2.5 border-t border-white/10 bg-white/[0.02] text-[10.5px] text-white/50">
        <span className="inline-flex items-center gap-1.5"><QrCode size={11} className="text-gold" /> Unique booth QR</span>
        <span className="inline-flex items-center gap-1.5"><Check size={11} className="text-teal" /> CSV · Excel export</span>
      </div>
    </MockFrame>
  );
}

function SmartCardVisual() {
  return (
    <MockFrame label="voxbulk.com · smart card qr" tint="#4FB3A9" live="Seats 12">
      <div className="p-4 flex items-center gap-3">
        <span className="w-10 h-10 rounded-full bg-gradient-to-br from-gold to-blue-400 flex items-center justify-center text-navy font-bold text-[12px] shrink-0">SR</span>
        <div className="min-w-0 flex-1">
          <div className="text-[13.5px] font-bold text-white truncate">Sara Redwood</div>
          <div className="text-[11px] text-white/50 truncate">Senior Account Manager · Seat 1</div>
        </div>
        <span className="shrink-0 inline-flex items-center gap-1.5 px-2.5 h-6 rounded-full bg-white/[0.08] border border-white/15 text-[10px] font-semibold text-white/80 whitespace-nowrap">
          <IdCard size={11} className="text-gold" /> My QR
        </span>
      </div>
      <div className="px-4 pb-4 divide-y divide-white/5 border-t border-white/10">
        {[
          { n: "Ellie Watts", c: "Requested price list", t: "hot" as const },
          { n: "Tom Alderson", c: "Card photo scanned", t: "warm" as const },
          { n: "Freya Bell", c: "Brochure sent", t: "warm" as const },
          { n: "Nathan Cole", c: "Browsing only", t: "cold" as const },
        ].map((r) => (
          <div key={r.n} className="flex items-center gap-2.5 py-2">
            <div className="min-w-0 flex-1">
              <div className="text-[12.5px] font-semibold text-white truncate leading-tight">{r.n}</div>
              <div className="text-[10.5px] text-white/45 truncate leading-tight">{r.c}</div>
            </div>
            <LeadTag tone={r.t} />
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between px-4 py-2.5 border-t border-white/10 bg-white/[0.02] text-[10.5px] text-white/50">
        <span>Reps see only their leads</span>
        <span className="inline-flex items-center gap-1.5 text-teal"><Check size={11} /> Hot-lead alerts on</span>
      </div>
    </MockFrame>
  );
}

/* ---------- slide model ---------- */
type Accent = "blue" | "gold" | "teal";
type Pattern = "grid" | "dots" | "waves" | "rings" | "beams" | "mesh";

type Slide = {
  key: string;
  tab: string;
  Icon: typeof Sparkles;
  badge: string;
  accent: Accent;
  pattern: Pattern;
  kicker: string;
  headline: ReactNode;
  sub: ReactNode;
  href: string;
  cta: string;
  facts: { Icon: typeof Sparkles; label: string }[];
  visual?: ReactNode;
};

const ACCENT = {
  blue: { dot: "bg-blue-400", text: "text-blue-300", ring: "border-blue-400/25", glowA: "#1E6FD9", glowB: "#4FB3A9", highlight: "text-blue-300", raw: "#2A82EB", btn: "linear-gradient(180deg,#2A82EB 0%,#1E6FD9 100%)", fg: "#ffffff" },
  gold: { dot: "bg-gold", text: "text-gold", ring: "border-gold/30", glowA: "#D4A93A", glowB: "#1E6FD9", highlight: "text-gold", raw: "#D4A93A", btn: "linear-gradient(180deg,#E0B94D 0%,#C79A25 100%)", fg: "#0A1628" },
  teal: { dot: "bg-teal", text: "text-teal", ring: "border-teal/30", glowA: "#4FB3A9", glowB: "#1E6FD9", highlight: "text-teal", raw: "#4FB3A9", btn: "linear-gradient(180deg,#59C3B8 0%,#3E9A91 100%)", fg: "#0A1628" },
} as const;


export function buildSlides(platformVisual?: ReactNode): Slide[] {
  return [
    {
      key: "platform",
      pattern: "grid",
      kicker: "One platform",
      tab: "Platform",
      Icon: Layers,
      accent: "blue",
      badge: "Live now · AI Assistant Platform",
      headline: <>Intelligent screening. <span className="serif-italic text-gold">Instant results.</span></>,
      sub: <>Five services on one platform — recruitment screening, WhatsApp surveys, customer feedback, exhibition lead capture and smart card QR for sales reps.</>,
      href: "/demo",
      cta: "Request a demo",
      facts: [
        { Icon: ShieldCheck, label: "GDPR compliant" },
        { Icon: Zap, label: "Live in days" },
        { Icon: Layers, label: "Plug into your stack" },
      ],
      visual: platformVisual,
    },
    {
      key: "recruitment",
      pattern: "rings",
      kicker: "Hiring",
      tab: "Recruitment",
      Icon: Sparkles,
      accent: "gold",
      badge: "Service · Recruitment Automation",
      headline: <>Screen smarter. <span className="serif-italic text-gold">Hire faster.</span></>,
      sub: <>AI interviews every candidate automatically — scoring skills, communication and fit before your team gets involved. No scheduling, no bias, no wasted time.</>,
      href: "/recruitment",
      cta: "Explore recruitment",
      facts: [
        { Icon: Clock, label: "92% less screening time" },
        { Icon: PhoneCall, label: "AI voice interviews" },
        { Icon: BarChart3, label: "ATS + interview scoring" },
      ],
      visual: <RecruitmentVisual />,
    },
    {
      key: "surveys",
      pattern: "waves",
      kicker: "Messaging",
      tab: "WhatsApp Surveys",
      Icon: MessageCircle,
      accent: "teal",
      badge: "Service · WhatsApp Surveys",
      headline: <>Surveys they <span className="serif-italic text-teal">actually respond to.</span></>,
      sub: <>Send smart surveys straight to WhatsApp. 98% open rates, instant responses, zero chasing — and every reply or voice note, in any language, arrives translated into English.</>,
      href: "/surveys",
      cta: "Explore surveys",
      facts: [
        { Icon: Zap, label: "98% open rate" },
        { Icon: Globe, label: "Any language → English" },
        { Icon: Users, label: "14 ready-made templates" },
      ],
      visual: <SurveysVisual />,
    },
    {
      key: "feedback",
      pattern: "dots",
      kicker: "Customer voice",
      tab: "Customer Feedback",
      Icon: Inbox,
      accent: "gold",
      badge: "Service · Customer Feedback",
      headline: <>Know what customers <span className="serif-italic text-gold">really think.</span></>,
      sub: <>One QR code on your table or counter. Customers scan, chat on WhatsApp in 50+ languages, and every answer reaches you in English with a clear weekly report.</>,
      href: "/feedback",
      cta: "Explore feedback",
      facts: [
        { Icon: QrCode, label: "One QR per location" },
        { Icon: Languages, label: "50+ languages → English" },
        { Icon: BarChart3, label: "Weekly KPI report" },
      ],
      visual: <FeedbackVisual />,
    },
    {
      key: "expo",
      pattern: "beams",
      kicker: "Events",
      tab: "Expo",
      Icon: QrCode,
      accent: "blue",
      badge: "New · VoxBulk Expo",
      headline: <>They scan your QR. <span className="serif-italic text-blue-300">You get the lead.</span></>,
      sub: <>Exhibition lead capture for your booth. Visitors scan at the stand, leave details on WhatsApp or a quick form, and the scored lead lands in your dashboard. Pay once per show.</>,
      href: "/expo",
      cta: "Explore Expo",
      facts: [
        { Icon: Wallet, label: "From £49 per show" },
        { Icon: Flame, label: "Hot / Warm / Cold scoring" },
        { Icon: FileDown, label: "CSV & Excel export" },
      ],
      visual: <ExpoVisual />,
    },
    {
      key: "smart-card",
      pattern: "mesh",
      kicker: "Field sales",
      tab: "Smart Card QR",
      Icon: IdCard,
      accent: "teal",
      badge: "New · Smart Card QR",
      headline: <>Paper card out. <span className="serif-italic text-teal">Smart QR in.</span></>,
      sub: <>One personal QR per sales rep. Prospects scan, chat, receive your catalogue — and every lead is scored and attributed to that rep. From $5 per seat.</>,
      href: "/smart-card",
      cta: "Explore Smart Card",
      facts: [
        { Icon: IdCard, label: "One seat = one rep" },
        { Icon: Users, label: "Rep-level lead attribution" },
        { Icon: Wallet, label: "Save 20% yearly" },
      ],
      visual: <SmartCardVisual />,
    },
  ];
}

/* ---------- slide body ---------- */
function SlideBody({
  s,
  onTalk,
  compact = false,
}: {
  s: Slide;
  onTalk: () => void;
  compact?: boolean;
}) {
  const a = ACCENT[s.accent];
  return (
    <div className={`grid ${compact ? "lg:grid-cols-[0.9fr_1.1fr]" : "lg:grid-cols-[0.85fr_1.15fr]"} gap-10 lg:gap-12 items-center`}>
      <div key={s.key} className="relative text-left min-w-0 animate-float-up">
        {/* service watermark */}
        <s.Icon
          aria-hidden
          className="pointer-events-none absolute -top-10 -left-8 opacity-[0.07] hidden sm:block"
          style={{ color: a.raw, width: 168, height: 168 }}
        />

        <div className="relative flex items-center gap-3">
          <span className="hidden sm:block h-px w-8" style={{ backgroundColor: a.raw, opacity: 0.6 }} />
          <span className="text-[11px] font-bold uppercase tracking-[0.24em]" style={{ color: a.raw }}>
            {s.kicker}
          </span>
        </div>

        <div className={`relative mt-3 inline-flex items-center gap-2 px-3.5 h-8 rounded-full border bg-white/[0.06] text-[12.5px] text-white/80 backdrop-blur ${a.ring}`}>
          <span className={`w-1.5 h-1.5 rounded-full pulse-dot ${a.dot}`} />
          {s.badge}
        </div>

        <h1 className="relative mt-5 text-[30px] sm:text-[42px] lg:text-[52px] font-bold tracking-[-0.035em] leading-[1.08] text-white break-words">
          {s.headline}
        </h1>

        <p className="relative mt-5 max-w-[520px] text-[15px] sm:text-[16px] md:text-[17px] text-white/70 leading-[1.6]">
          {s.sub}
        </p>

        <div className="relative mt-7 flex flex-col sm:flex-row items-start sm:items-center gap-3">
          <Link
            to={s.href}
            className="inline-flex items-center justify-center gap-2 rounded-xl px-6 h-12 text-[15px] font-semibold transition-transform hover:-translate-y-0.5"
            style={{ background: a.btn, color: a.fg, boxShadow: `0 12px 30px -12px ${a.raw}` }}
          >
            {s.cta} <ArrowRight size={16} />
          </Link>
          <button onClick={onTalk} className="btn-ghost-light text-[15px] h-12">
            <Headphones size={15} /> Talk to us
          </button>
        </div>

        <div className="relative mt-7 flex flex-wrap items-center gap-2">
          {s.facts.map((f) => (
            <span
              key={f.label}
              className={`inline-flex items-center gap-1.5 px-3 h-8 rounded-lg border bg-white/[0.04] text-[12.5px] text-white/70 ${a.ring}`}
            >
              <f.Icon size={13} className={a.text} /> {f.label}
            </span>
          ))}
        </div>
      </div>

      <div key={`${s.key}-visual`} className="min-w-0 animate-fade-in">
        {s.visual}
      </div>
    </div>
  );
}

function PatternLayer({ pattern, color }: { pattern: Pattern; color: string }) {
  if (pattern === "dots") {
    return (
      <div
        className="absolute inset-0 opacity-[0.18]"
        style={{ backgroundImage: `radial-gradient(${color} 1.4px, transparent 1.4px)`, backgroundSize: "26px 26px" }}
      />
    );
  }
  if (pattern === "waves") {
    return (
      <div className="absolute inset-0 overflow-hidden opacity-[0.22]">
        <svg className="absolute -bottom-6 left-0 w-[200%] h-[70%]" viewBox="0 0 1200 200" preserveAspectRatio="none" aria-hidden>
          {[0, 1, 2].map((i) => (
            <path
              key={i}
              d={`M0 ${80 + i * 28} C 150 ${30 + i * 28} 300 ${130 + i * 28} 450 ${80 + i * 28} S 750 ${30 + i * 28} 900 ${80 + i * 28} S 1200 ${130 + i * 28} 1200 ${80 + i * 28}`}
              fill="none"
              stroke={color}
              strokeWidth={1.2}
              opacity={0.9 - i * 0.25}
            />
          ))}
        </svg>
      </div>
    );
  }
  if (pattern === "rings") {
    return (
      <div className="absolute inset-0 overflow-hidden">
        <div
          className="absolute top-1/2 right-[8%] -translate-y-1/2 w-[620px] h-[620px] rounded-full opacity-[0.16] spin-slow"
          style={{
            background: `repeating-radial-gradient(circle, transparent 0 46px, ${color} 46px 47px)`,
            maskImage: "radial-gradient(circle, #000 40%, transparent 72%)",
            WebkitMaskImage: "radial-gradient(circle, #000 40%, transparent 72%)",
          }}
        />
      </div>
    );
  }
  if (pattern === "beams") {
    return (
      <div
        className="absolute inset-0 opacity-[0.13]"
        style={{
          backgroundImage: `repeating-linear-gradient(115deg, ${color} 0 1px, transparent 1px 34px)`,
          maskImage: "linear-gradient(to bottom, #000, transparent 85%)",
          WebkitMaskImage: "linear-gradient(to bottom, #000, transparent 85%)",
        }}
      />
    );
  }
  if (pattern === "mesh") {
    return (
      <div
        className="absolute inset-0 opacity-[0.14]"
        style={{
          backgroundImage: `linear-gradient(60deg, ${color} 0 1px, transparent 1px 30px), linear-gradient(-60deg, ${color} 0 1px, transparent 1px 30px)`,
        }}
      />
    );
  }
  return <div className="absolute inset-0 bg-grid opacity-[0.3]" />;
}

function SlideBackdrop({ accent, pattern }: { accent: Accent; pattern: Pattern }) {
  const a = ACCENT[accent];
  return (
    <>
      <PatternLayer pattern={pattern} color={a.raw} />
      <div className="absolute inset-0 bg-hero-glow" />
      <div
        className="absolute -top-24 -left-20 w-[380px] h-[380px] rounded-full blur-3xl opacity-30 float-a"
        style={{ background: `radial-gradient(circle, ${a.glowA} 0%, transparent 60%)` }}
      />
      <div
        className="absolute -bottom-24 -right-20 w-[380px] h-[380px] rounded-full blur-3xl opacity-25"
        style={{ background: `radial-gradient(circle, ${a.glowB} 0%, transparent 60%)` }}
      />
      <div className="absolute inset-x-0 bottom-0 h-px" style={{ background: `linear-gradient(90deg, transparent, ${a.raw}55, transparent)` }} />
    </>
  );
}


/* ---------- single-service hero (used on service pages) ---------- */
export function ServiceHero({ service }: { service: string }) {
  const talk = useTalkModal();
  const slides = buildSlides();
  const s = slides.find((x) => x.key === service) ?? slides[0];
  return (
    <section
      id="top"
      className="relative overflow-hidden bg-navy text-white pt-[112px] md:pt-[128px] pb-14 md:pb-16"
      aria-label={`${s.tab} overview`}
    >
      <SlideBackdrop accent={s.accent} pattern={s.pattern} />
      <div className="relative max-w-[1320px] mx-auto px-5 md:px-10">
        <SlideBody s={s} onTalk={talk.open} compact />
      </div>
    </section>
  );
}

/* ---------- homepage slider ---------- */
export function HeroSlider({ platformVisual }: { platformVisual: ReactNode }) {
  const talk = useTalkModal();
  const slides = buildSlides(platformVisual);

  const [i, setI] = useState(0);
  const [paused, setPaused] = useState(false);
  const total = slides.length;
  const go = (n: number) => setI((n + total) % total);

  useEffect(() => {
    if (paused) return;
    const t = setInterval(() => setI((v) => (v + 1) % total), 7000);
    return () => clearInterval(t);
  }, [paused, total]);

  const s = slides[i];

  return (
    <section
      id="top"
      className="relative overflow-hidden bg-navy text-white pt-[112px] md:pt-[128px] pb-10 md:pb-12"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      aria-roledescription="carousel"
      aria-label="VoxBulk services"
    >
      <SlideBackdrop accent={s.accent} pattern={s.pattern} />

      <div className="relative max-w-[1320px] mx-auto px-5 md:px-10">
        <SlideBody s={s} onTalk={talk.open} />

        {/* Slider controls */}
        <div className="mt-10 md:mt-12 pt-5 border-t border-white/10 flex flex-col md:flex-row md:items-center gap-4">
          <div className="flex-1 min-w-0 -mx-1 overflow-x-auto">
            <div className="flex items-center gap-1.5 px-1 pb-1">
              {slides.map((sl, idx) => (
                <button
                  key={sl.key}
                  onClick={() => setI(idx)}
                  aria-current={idx === i}
                  className={`shrink-0 inline-flex items-center gap-1.5 px-3 h-9 rounded-lg text-[12.5px] font-semibold transition-colors whitespace-nowrap ${
                    idx === i
                      ? "bg-white/[0.12] text-white border border-white/20"
                      : "text-white/55 hover:text-white hover:bg-white/[0.06] border border-transparent"
                  }`}
                >
                  <sl.Icon size={13} className={idx === i ? ACCENT[sl.accent].text : "opacity-70"} />
                  {sl.tab}
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <div className="flex items-center gap-1.5">
              {slides.map((sl, idx) => (
                <button
                  key={sl.key}
                  onClick={() => setI(idx)}
                  aria-label={`Go to ${sl.tab}`}
                  className={`h-1.5 rounded-full transition-all ${idx === i ? "w-6 bg-gold" : "w-1.5 bg-white/25 hover:bg-white/50"}`}
                />
              ))}
            </div>
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => go(i - 1)}
                aria-label="Previous slide"
                className="w-9 h-9 rounded-lg border border-white/15 bg-white/[0.06] hover:bg-white/[0.12] text-white/80 flex items-center justify-center transition-colors"
              >
                <ArrowLeft size={15} />
              </button>
              <button
                onClick={() => go(i + 1)}
                aria-label="Next slide"
                className="w-9 h-9 rounded-lg border border-white/15 bg-white/[0.06] hover:bg-white/[0.12] text-white/80 flex items-center justify-center transition-colors"
              >
                <ArrowRight size={15} />
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
