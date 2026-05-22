import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";
import logoLight from "@/assets/logolight.svg";
import logoNormal from "@/assets/logonormal.svg";
import { Link } from "@tanstack/react-router";
import { useAuthModal } from "@/components/AuthModal";
import { AmbientBackdrop } from "@/components/BackgroundDecor";
import { DeferredMount } from "@/components/DeferredMount";
import {
  completeFrontpageTalkToUsCall,
  startFrontpageTalkToUsCall,
  fetchPublicPlans,
} from "@/lib/retoverApi";
import {
  mapPublicPlansToCards,
  overageFootnote,
  type MarketingPlanCard,
  type PublicPlanRow,
} from "@/lib/publicPlanCards";
import { createRingbackTone, type RingbackController } from "@/lib/ringbackTone";
import {
  Search,
  PhoneCall,
  CalendarCheck,
  Bot,
  MessageCircle,
  CheckCircle2,
  RefreshCw,
  AlertTriangle,
  BarChart3,
  FileText,
  Link2,
  PhoneOutgoing,
  ShieldCheck,
  Sparkles,
  Zap,
  ArrowRight,
  ArrowUpRight,
  Quote,
  Star,
  TrendingUp,
  TrendingDown,
  Percent,
  Clock,
  PoundSterling,
  Users,
  ChevronLeft,
  ChevronRight,
  Check,
  Minus,
  Calendar as CalendarIcon,
  Heart,
  Eye,
  Flower2,
  Stethoscope,
  Loader2,
} from "lucide-react";

/* ---------------- NAVBAR ---------------- */
const navLinks = [
  { label: "How it works", href: "#how-it-works" },
  { label: "Features", href: "#features" },
  { label: "Pricing", href: "#pricing" },
  { label: "ROI", href: "#results" },
  { label: "Industries", href: "#industries" },
];

function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const auth = useAuthModal();

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <>
      <header
        className="fixed top-3 inset-x-3 md:inset-x-6 z-50 transition-all duration-300 rounded-full border border-white/[0.08]"
        style={{
          backgroundColor: scrolled ? "rgba(10,10,15,0.92)" : "rgba(10,10,15,0.75)",
          backdropFilter: "saturate(160%) blur(20px)",
          WebkitBackdropFilter: "saturate(160%) blur(20px)",
          boxShadow: scrolled
            ? "0 10px 40px -12px rgba(0,0,0,0.55)"
            : "0 8px 30px -12px rgba(0,0,0,0.4)",
        }}
      >
        <div className="max-w-[1320px] mx-auto h-[60px] md:h-[64px] flex items-center justify-between pl-5 pr-2 md:pl-6 md:pr-2.5 relative">
          <a href="#hero" className="flex items-center group">
            <img
              src={logoLight}
              alt="VOXBULK"
              width={140}
              height={28}
              decoding="async"
              fetchPriority="high"
              className="h-7 md:h-[28px] w-auto object-contain"
            />
          </a>

          <nav className="hidden lg:flex items-center gap-1 absolute left-1/2 -translate-x-1/2">
            {navLinks.map((l) => (
              <a
                key={l.href}
                href={l.href}
                className="text-[14px] font-medium text-white/65 hover:text-white hover:bg-white/[0.06] transition-all px-4 py-2 rounded-full"
              >
                {l.label}
              </a>
            ))}
          </nav>

          <div className="hidden md:flex items-center gap-2">
            <button
              onClick={auth.open}
              aria-label="Sign in"
              className="w-9 h-9 inline-flex items-center justify-center rounded-lg border border-white/[0.10] bg-white/[0.04] text-white/80 hover:text-white hover:bg-white/[0.10] transition-colors"
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
                <polyline points="10 17 15 12 10 7" />
                <line x1="15" y1="12" x2="3" y2="12" />
              </svg>
            </button>
            <a
              href="#demo"
              className="inline-flex items-center justify-center rounded-full px-5 h-9 text-[13.5px] font-semibold text-white transition-all"
              style={{
                background: "linear-gradient(180deg, #FB923C 0%, #F97316 100%)",
                boxShadow:
                  "0 1px 0 rgba(255,255,255,0.18) inset, 0 8px 22px -8px rgba(249,115,22,0.55)",
              }}
            >
              Get Started
            </a>
          </div>

          <button
            className="md:hidden -mr-2 p-2 text-white"
            aria-label="Open menu"
            onClick={() => setOpen(true)}
          >
            <svg
              width="22"
              height="22"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <line x1="4" y1="7" x2="20" y2="7" />
              <line x1="4" y1="12" x2="20" y2="12" />
              <line x1="4" y1="17" x2="20" y2="17" />
            </svg>
          </button>
        </div>
      </header>

      {open && (
        <div className="fixed inset-0 z-[60] bg-white md:hidden flex flex-col animate-fade-in">
          <div className="flex items-center justify-between px-5 h-[68px] border-b border-border">
            <img src={logoNormal} alt="VOXBULK" className="h-7 w-auto" />
            <button
              onClick={() => setOpen(false)}
              aria-label="Close menu"
              className="p-2 text-heading"
            >
              <svg
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <line x1="6" y1="6" x2="18" y2="18" />
                <line x1="18" y1="6" x2="6" y2="18" />
              </svg>
            </button>
          </div>
          <div className="flex-1 px-5 py-4">
            {navLinks.map((l) => (
              <a
                key={l.href}
                href={l.href}
                onClick={() => setOpen(false)}
                className="flex items-center justify-between h-14 border-b border-border text-[17px] font-medium text-heading"
              >
                {l.label}
                <ArrowRight size={18} className="text-muted-text" />
              </a>
            ))}
            <button
              onClick={() => {
                setOpen(false);
                auth.open();
              }}
              className="flex items-center h-14 text-[17px] font-medium text-body w-full text-left"
            >
              Sign in
            </button>
          </div>
          <div className="p-5 border-t border-border">
            <a href="#demo" onClick={() => setOpen(false)} className="btn-primary w-full">
              Book a demo <ArrowRight size={16} />
            </a>
          </div>
        </div>
      )}
    </>
  );
}

/* ---------------- HERO ---------------- */
function Hero() {
  return (
    <section
      id="hero"
      className="relative pt-28 md:pt-36 pb-24 md:pb-32 overflow-hidden text-white"
      style={{
        background: "linear-gradient(135deg, #020617 0%, #0F172A 35%, #1E1B4B 70%, #312E81 100%)",
      }}
    >
      <div
        className="absolute inset-0 opacity-[0.08]"
        style={{
          backgroundImage:
            "linear-gradient(to right, rgba(255,255,255,0.5) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,0.5) 1px, transparent 1px)",
          backgroundSize: "56px 56px",
          maskImage: "radial-gradient(ellipse 70% 60% at 50% 30%, #000 30%, transparent 80%)",
        }}
      />
      <div
        className="absolute -top-32 -left-32 w-[520px] h-[520px] rounded-full blur-3xl opacity-30"
        style={{ background: "radial-gradient(circle, #F97316, transparent 70%)" }}
      />
      <div
        className="absolute -bottom-32 -right-20 w-[600px] h-[600px] rounded-full blur-3xl opacity-25"
        style={{ background: "radial-gradient(circle, #312E81, transparent 70%)" }}
      />
      <div className="absolute inset-x-0 bottom-0 h-32 bg-gradient-to-b from-transparent to-background" />

      <div className="relative max-w-[1320px] mx-auto px-5 md:px-10 grid lg:grid-cols-[1.05fr_1.1fr] gap-14 lg:gap-12 items-center">
        {/* LEFT: Text */}
        <div className="text-left">
          <div
            className="inline-flex items-center gap-2 backdrop-blur text-[12.5px] font-medium rounded-full px-4 py-1.5 animate-float-up"
            style={{
              background: "rgba(249,115,22,0.12)",
              border: "1px solid rgba(249,115,22,0.30)",
              color: "#FBA94C",
            }}
          >
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full rounded-full bg-success opacity-60 pulse-dot" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-success" />
            </span>
            Built for UK dental clinics · Live with Dentally
          </div>

          <h1
            className="mt-6 font-bold text-white leading-[0.98] tracking-[-0.04em] animate-float-up"
            style={{ fontSize: "clamp(38px, 5.4vw, 68px)", animationDelay: "60ms" }}
          >
            Stop losing{" "}
            <span className="italic font-serif font-normal" style={{ color: "#FBA94C" }}>
              money
            </span>{" "}
            to empty chairs.
          </h1>

          <p
            className="mt-6 max-w-[560px] text-[17px] md:text-[18.5px] leading-[1.6] animate-float-up"
            style={{ animationDelay: "140ms", color: "rgba(255,255,255,0.65)" }}
          >
            VOXBULK automatically recovers cancelled appointments, confirms bookings, and fills open
            slots — using AI voice calls and WhatsApp. Your clinic software stays exactly as it is.
          </p>

          <div
            className="mt-8 flex flex-wrap items-center gap-3 animate-float-up"
            style={{ animationDelay: "220ms" }}
          >
            <a href="#demo" className="btn-primary text-[15px]">
              Book a free demo <ArrowRight size={16} />
            </a>
            <a
              href="#how-it-works"
              className="inline-flex items-center justify-center gap-2 rounded-[10px] px-6 py-[13px] font-semibold text-[15px] text-white transition-colors"
              style={{ border: "1px solid rgba(255,255,255,0.25)" }}
            >
              See how it works
            </a>
          </div>

          <p
            className="mt-5 text-[13px] animate-float-up"
            style={{ animationDelay: "300ms", color: "rgba(255,255,255,0.45)" }}
          >
            No setup fee · 14-day free trial · Cancel anytime · Pay by direct debit
          </p>

          {/* Mini stat row */}
          <div
            className="mt-9 grid grid-cols-3 gap-3 max-w-[480px] animate-float-up"
            style={{ animationDelay: "380ms" }}
          >
            {[
              { v: "85%", l: "Recovery rate" },
              { v: "£2.4k", l: "Avg/month" },
              { v: "30min", l: "Setup" },
            ].map((s) => (
              <div
                key={s.l}
                className="rounded-xl px-3 py-2.5"
                style={{
                  background: "rgba(255,255,255,0.05)",
                  border: "1px solid rgba(255,255,255,0.08)",
                }}
              >
                <div
                  className="text-[20px] font-bold tabular-nums tracking-tight"
                  style={{ color: "#F97316" }}
                >
                  {s.v}
                </div>
                <div className="text-[11.5px]" style={{ color: "rgba(255,255,255,0.40)" }}>
                  {s.l}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* RIGHT: Dashboard mockup with floating chips */}
        <div className="relative animate-float-up" style={{ animationDelay: "260ms" }}>
          {/* Glow */}
          <div className="absolute -inset-8 bg-gradient-to-br from-primary/25 via-accent/10 to-transparent blur-3xl rounded-[60px]" />

          {/* Floating chips */}
          <div className="absolute -left-4 md:-left-10 top-10 z-30 flex items-center gap-2.5 bg-white/95 backdrop-blur border border-border rounded-2xl px-3.5 py-2.5 shadow-elevated float-a">
            <div className="w-8 h-8 rounded-lg bg-success/10 flex items-center justify-center text-success">
              <CheckCircle2 size={18} />
            </div>
            <div className="text-left">
              <div className="text-[12px] font-semibold text-heading">Slot recovered</div>
              <div className="text-[10.5px] text-muted-text">Sarah J · Tue 14:00</div>
            </div>
          </div>

          <div className="absolute -right-2 md:-right-6 top-[42%] z-30 flex items-center gap-2.5 bg-white/95 backdrop-blur border border-border rounded-2xl px-3.5 py-2.5 shadow-elevated float-b">
            <div className="w-8 h-8 rounded-lg bg-accent/15 flex items-center justify-center text-accent">
              <PoundSterling size={18} />
            </div>
            <div className="text-left">
              <div className="text-[12px] font-semibold text-heading">+£95 recovered</div>
              <div className="text-[10.5px] text-muted-text">Hygiene · Practice 1</div>
            </div>
          </div>

          <div className="absolute -left-2 md:-left-6 bottom-16 z-30 flex items-center gap-2.5 bg-white/95 backdrop-blur border border-border rounded-2xl px-3.5 py-2.5 shadow-elevated float-c">
            <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center text-primary">
              <PhoneCall size={18} />
            </div>
            <div className="text-left">
              <div className="text-[12px] font-semibold text-heading">AI calling Emma R.</div>
              <div className="text-[10.5px] text-muted-text">Live · 00:42</div>
            </div>
          </div>

          {/* Decorative orbiting dot */}
          <div className="absolute -top-4 right-10 w-3 h-3 rounded-full bg-accent shadow-[0_0_20px_var(--accent)] float-c" />
          <div className="absolute top-1/3 -right-12 w-2 h-2 rounded-full bg-primary shadow-[0_0_20px_var(--primary)] float-a hidden md:block" />

          {/* Dashboard */}
          <div className="relative bg-white border border-border/80 rounded-2xl shadow-elevated overflow-hidden">
            <div className="flex items-center gap-2 px-4 py-3 border-b border-border bg-secondary/60">
              <span className="w-2.5 h-2.5 rounded-full bg-[#FF5F57]" />
              <span className="w-2.5 h-2.5 rounded-full bg-[#FEBC2E]" />
              <span className="w-2.5 h-2.5 rounded-full bg-[#28C840]" />
              <div className="ml-3 text-[11.5px] text-muted-text font-mono truncate">
                app.voxbulk.com/dashboard
              </div>
              <div className="ml-auto hidden md:flex items-center gap-1.5 text-[10.5px] text-muted-text">
                <span className="w-1.5 h-1.5 rounded-full bg-success pulse-dot" /> Live
              </div>
            </div>

            <div className="p-4 md:p-5">
              {/* KPIs */}
              <div className="grid grid-cols-3 gap-2.5">
                <KPI
                  icon={<PoundSterling size={14} />}
                  label="Recovered"
                  value="£12,480"
                  trend="+18%"
                />
                <KPI icon={<CalendarCheck size={14} />} label="Slots" value="142" trend="+24" />
                <KPI
                  icon={<TrendingUp size={14} />}
                  label="Answer"
                  value="68%"
                  trend="+4%"
                  accent
                />
              </div>

              {/* Chart card */}
              <div className="mt-3 rounded-xl border border-border bg-gradient-to-br from-primary/[0.04] to-white p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-text">
                      Recovered revenue
                    </div>
                    <div className="mt-0.5 text-[20px] font-bold text-heading tabular-nums">
                      £12,480
                    </div>
                  </div>
                  <div className="flex gap-1 text-[10.5px] font-medium">
                    {["7D", "30D", "90D"].map((t, i) => (
                      <span
                        key={t}
                        className={`px-2 py-1 rounded-md ${i === 1 ? "bg-primary text-white" : "text-muted-text bg-secondary"}`}
                      >
                        {t}
                      </span>
                    ))}
                  </div>
                </div>
                <MiniChart />
              </div>

              {/* Live call card */}
              <div className="mt-3 rounded-xl border border-primary/20 bg-gradient-to-br from-primary/[0.06] via-white to-accent/[0.04] p-3.5">
                <div className="flex items-center gap-2 text-[10.5px] font-semibold uppercase tracking-wider text-success">
                  <span className="w-1.5 h-1.5 rounded-full bg-success pulse-dot" />
                  Live call · 00:42
                </div>
                <div className="mt-2.5 flex items-center gap-2.5">
                  <div className="w-9 h-9 rounded-full bg-gradient-to-br from-primary to-primary-dark text-white flex items-center justify-center font-semibold text-[12px]">
                    SJ
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-[12.5px] font-semibold text-heading">Sarah Johnson</div>
                    <div className="text-[10.5px] text-muted-text">Hygiene · Tue 14:00</div>
                  </div>
                  <div className="hidden sm:flex items-center gap-1 text-[10.5px] text-success bg-success/10 border border-success/20 rounded-full px-2 py-0.5">
                    <CheckCircle2 size={11} /> Booked
                  </div>
                </div>
                <div className="mt-2.5 space-y-1.5">
                  <div className="flex justify-end">
                    <div className="bg-primary text-white text-[11.5px] rounded-2xl rounded-tr-md px-2.5 py-1.5 max-w-[85%]">
                      Hi Sarah, your 2pm slot opened up tomorrow. Would you like it?
                    </div>
                  </div>
                  <div className="flex">
                    <div className="bg-white border border-border text-heading text-[11.5px] rounded-2xl rounded-tl-md px-2.5 py-1.5 max-w-[85%]">
                      Yes please, that works perfectly!
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function KPI({
  icon,
  label,
  value,
  trend,
  accent,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  trend: string;
  accent?: boolean;
}) {
  return (
    <div className="rounded-xl border border-border bg-white p-3">
      <div className="flex items-center gap-1.5 text-muted-text">
        {icon}
        <span className="text-[10px] font-semibold uppercase tracking-wider">{label}</span>
      </div>
      <div
        className={`mt-1 text-[17px] font-bold tabular-nums tracking-tight ${accent ? "text-accent" : "text-heading"}`}
      >
        {value}
      </div>
      <div className="mt-0.5 text-[10.5px] font-semibold text-success flex items-center gap-1">
        <TrendingUp size={10} /> {trend}
      </div>
    </div>
  );
}

function MiniChart() {
  const pts = [18, 26, 22, 34, 30, 44, 38, 52, 48, 62, 58, 72];
  const max = 80;
  const w = 100,
    h = 50;
  const step = w / (pts.length - 1);
  const path = pts
    .map((v, i) => `${i === 0 ? "M" : "L"} ${i * step} ${h - (v / max) * h}`)
    .join(" ");
  const area = `${path} L ${w} ${h} L 0 ${h} Z`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="mt-3 w-full h-20" preserveAspectRatio="none">
      <defs>
        <linearGradient id="chartFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="oklch(0.546 0.227 262)" stopOpacity="0.4" />
          <stop offset="100%" stopColor="oklch(0.546 0.227 262)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill="url(#chartFill)" />
      <path
        d={path}
        fill="none"
        stroke="oklch(0.546 0.227 262)"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/* ---------------- TRUST BAR ---------------- */
function TrustBar() {
  const items = [
    { Icon: Link2, text: "Works with Dentally" },
    { Icon: ShieldCheck, text: "GDPR Compliant" },
    { Icon: PhoneCall, text: "OFCOM Compliant" },
    { Icon: Sparkles, text: "UK-Based Support" },
    { Icon: Zap, text: "30-min setup" },
    { Icon: TrendingUp, text: "85% recovery rate" },
  ];
  return (
    <section className="border-y border-border bg-white">
      <div className="max-w-[1280px] mx-auto px-5 md:px-10 py-5 overflow-hidden">
        <div className="flex items-center justify-center gap-x-9 gap-y-3 flex-wrap">
          {items.map(({ Icon, text }) => (
            <div
              key={text}
              className="inline-flex items-center gap-2 text-[13.5px] font-medium text-body"
            >
              <Icon size={16} className="text-primary" />
              {text}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ---------------- SECTION HEADER ---------------- */
function SectionHeader({
  eyebrow,
  title,
  sub,
  center = true,
}: {
  eyebrow: string;
  title: React.ReactNode;
  sub?: string;
  center?: boolean;
}) {
  return (
    <div className={`max-w-[680px] ${center ? "mx-auto text-center" : ""}`}>
      <span className="eyebrow">{eyebrow}</span>
      <h2 className="mt-4 text-[28px] md:text-[44px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
        {title}
      </h2>
      {sub && <p className="mt-5 text-[16px] md:text-[18px] text-body leading-[1.6]">{sub}</p>}
    </div>
  );
}

/* ---------------- PROBLEM ---------------- */
function Problem() {
  const cards = [
    {
      v: "£2k–£5k",
      suffix: "/month",
      Icon: TrendingDown,
      tone: "accent",
      l: "Lost revenue per clinic from cancellations and no-shows.",
      foot: "Industry average — UK dental",
    },
    {
      v: "85",
      suffix: "%",
      Icon: Percent,
      tone: "primary",
      l: "Of cancelled slots are recoverable with fast, personal follow-up.",
      foot: "Patients want to rebook",
    },
    {
      v: "< 5",
      suffix: "min",
      Icon: Clock,
      tone: "success",
      l: "Average time for VOXBULK to detect and act on a cancellation.",
      foot: "Fully automatic, 24/7",
    },
  ];
  const tones: Record<string, { ring: string; text: string; bg: string; glow: string }> = {
    accent: {
      ring: "ring-accent/20",
      text: "text-accent",
      bg: "bg-accent/10",
      glow: "from-accent/20",
    },
    primary: {
      ring: "ring-primary/20",
      text: "text-primary",
      bg: "bg-primary/10",
      glow: "from-primary/20",
    },
    success: {
      ring: "ring-success/20",
      text: "text-success",
      bg: "bg-success/10",
      glow: "from-success/20",
    },
  };
  return (
    <section id="problem" className="relative py-24 md:py-32 overflow-hidden">
      <AmbientBackdrop variant="warm" />
      <div className="relative max-w-[1180px] mx-auto px-5 md:px-10">
        <SectionHeader
          center
          eyebrow="The problem"
          title={
            <>
              Every empty chair costs your{" "}
              <span className="italic font-serif font-normal text-accent">clinic money.</span>
            </>
          }
          sub="The average UK dental clinic loses thousands every month to cancellations and no-shows. Most of it is recoverable — if you reach the right patient at the right time."
        />

        <div className="mt-16 grid md:grid-cols-3 gap-6">
          {cards.map(({ v, suffix, Icon, tone, l, foot }, i) => {
            const t = tones[tone];
            return (
              <div
                key={v}
                className={`group relative overflow-hidden rounded-3xl bg-white border border-border p-8 shadow-elegant hover:shadow-elevated hover:-translate-y-1.5 transition-all duration-500 ring-1 ${t.ring}`}
                style={{ animationDelay: `${i * 80}ms` }}
              >
                {/* corner glow */}
                <div
                  className={`absolute -top-24 -right-24 w-56 h-56 rounded-full bg-gradient-to-br ${t.glow} to-transparent blur-2xl opacity-70 group-hover:opacity-100 transition-opacity`}
                />
                {/* icon */}
                <div
                  className={`relative w-12 h-12 rounded-2xl ${t.bg} ${t.text} flex items-center justify-center`}
                >
                  <Icon size={22} strokeWidth={2} />
                </div>
                {/* big stat */}
                <div className="relative mt-6 flex items-baseline gap-1.5 whitespace-nowrap">
                  <span
                    className={`text-[34px] md:text-[44px] leading-none font-extrabold tracking-[-0.03em] tabular-nums ${t.text}`}
                  >
                    {v}
                  </span>
                  <span className={`text-[14px] font-semibold ${t.text}/80 tracking-tight`}>
                    {suffix}
                  </span>
                </div>
                <p className="relative mt-5 text-[15.5px] text-heading/80 leading-[1.55] font-medium">
                  {l}
                </p>
                <div className="relative mt-6 pt-5 border-t border-dashed border-border flex items-center gap-2 text-[12px] font-medium text-muted-text uppercase tracking-wider">
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${t.bg} ${t.text}`}
                    style={{ background: "currentColor" }}
                  />
                  {foot}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

/* ---------------- HOW IT WORKS (Modern numbered) ---------------- */
function HowItWorks() {
  const steps = [
    {
      n: "01",
      Icon: Search,
      color: "blue",
      title: "Detect",
      tag: "Real-time",
      body: "The moment a patient cancels or misses an appointment, VOXBULK identifies the open slot and finds the best patients to fill it.",
      bullets: ["Live Dentally sync", "Smart waitlist match", "Instant trigger"],
    },
    {
      n: "02",
      Icon: PhoneOutgoing,
      color: "accent",
      title: "Contact",
      tag: "Voice + WhatsApp",
      body: "Our AI calls the patient from your clinic's own number, speaks naturally, and helps them rebook — or sends a personal WhatsApp.",
      bullets: ["Your caller ID", "Natural AI voice", "OFCOM compliant"],
    },
    {
      n: "03",
      Icon: CalendarCheck,
      color: "success",
      title: "Recover",
      tag: "Synced back",
      body: "The appointment is confirmed in your Dentally diary. You see the recording, transcript and recovered revenue in real time.",
      bullets: ["Auto-booked", "Full transcript", "Revenue tracked"],
    },
  ];
  const tones: Record<
    string,
    { text: string; bg: string; ring: string; grad: string; soft: string }
  > = {
    blue: {
      text: "text-[#2563EB]",
      bg: "bg-[#2563EB]",
      ring: "ring-[#2563EB]/20",
      grad: "from-[#3B82F6] to-[#1D4ED8]",
      soft: "bg-[#2563EB]/10",
    },
    primary: {
      text: "text-primary",
      bg: "bg-primary",
      ring: "ring-primary/20",
      grad: "from-primary to-primary-dark",
      soft: "bg-primary/10",
    },
    accent: {
      text: "text-accent",
      bg: "bg-accent",
      ring: "ring-accent/20",
      grad: "from-accent to-accent-dark",
      soft: "bg-accent/10",
    },
    success: {
      text: "text-success",
      bg: "bg-success",
      ring: "ring-success/20",
      grad: "from-success to-emerald-600",
      soft: "bg-success/10",
    },
  };
  return (
    <section id="how-it-works" className="relative py-24 md:py-32 bg-surface overflow-hidden">
      <div className="absolute inset-0 bg-grid opacity-50" />
      <div className="absolute inset-0 bg-mesh opacity-30" />
      <div className="relative max-w-[1180px] mx-auto px-5 md:px-10">
        <SectionHeader
          eyebrow="How it works"
          title={
            <>
              Three steps.{" "}
              <span className="italic font-serif font-normal text-primary">Zero effort.</span>
            </>
          }
          sub="VOXBULK works silently in the background — detecting cancellations and filling slots without any manual effort from your team."
        />

        <div className="mt-20 relative">
          {/* Connecting line with moving pulse */}
          <div className="hidden md:block absolute top-[78px] left-[10%] right-[10%] h-px bg-gradient-to-r from-transparent via-border to-transparent" />
          <div className="hidden md:block absolute top-[76px] left-[10%] right-[10%] h-[3px] overflow-hidden">
            <div className="h-full w-1/3 bg-gradient-to-r from-transparent via-primary/40 to-transparent animate-marquee" />
          </div>

          <div className="grid md:grid-cols-3 gap-6 relative">
            {steps.map((s, i) => {
              const t = tones[s.color];
              return (
                <div
                  key={s.n}
                  className={`group relative bg-white rounded-3xl p-8 border border-border shadow-elegant hover:shadow-elevated hover:-translate-y-2 transition-all duration-500 ring-1 ${t.ring}`}
                >
                  {/* Floating number bubble */}
                  <div className="relative flex items-center justify-center mb-6">
                    <div
                      className={`relative w-[140px] h-[140px] rounded-full bg-gradient-to-br ${t.grad} flex items-center justify-center shadow-glow`}
                    >
                      <div
                        className={`absolute inset-2 rounded-full bg-white/10 backdrop-blur-sm`}
                      />
                      <div className="relative flex flex-col items-center text-white">
                        <s.Icon size={28} strokeWidth={2} />
                        <span className="mt-1 text-[11px] font-bold tracking-[0.2em] uppercase opacity-90">
                          Step {s.n}
                        </span>
                      </div>
                      {/* orbit dot */}
                      <span
                        className={`absolute -top-1 left-1/2 -translate-x-1/2 w-2.5 h-2.5 rounded-full bg-white shadow-md pulse-dot`}
                      />
                    </div>
                    {/* big number behind */}
                    <span
                      aria-hidden
                      className={`absolute -z-0 num-stamp text-[180px] leading-none -top-6 right-2 select-none opacity-[0.06] ${t.text}`}
                      style={{
                        background: "none",
                        WebkitBackgroundClip: "initial",
                        backgroundClip: "initial",
                        color: "currentColor",
                      }}
                    >
                      {s.n}
                    </span>
                  </div>

                  <div className="text-center">
                    <span
                      className={`inline-flex items-center gap-1.5 text-[10.5px] font-bold tracking-[0.14em] uppercase ${t.text} ${t.soft} rounded-full px-3 py-1`}
                    >
                      {s.tag}
                    </span>
                    <h3 className="mt-4 text-[26px] font-bold text-heading tracking-tight">
                      {s.title}
                    </h3>
                    <p className="mt-3 text-[15px] text-body leading-[1.65]">{s.body}</p>
                  </div>

                  <div className="mt-6 pt-5 border-t border-dashed border-border space-y-2">
                    {s.bullets.map((b) => (
                      <div key={b} className="flex items-center gap-2.5 text-[13.5px] text-body">
                        <span
                          className={`w-4 h-4 rounded-full ${t.soft} ${t.text} flex items-center justify-center shrink-0`}
                        >
                          <Check size={10} strokeWidth={3} />
                        </span>
                        {b}
                      </div>
                    ))}
                  </div>

                  {/* arrow connector */}
                  {i < steps.length - 1 && (
                    <div className="hidden md:flex absolute top-[78px] -right-3 z-10 w-6 h-6 rounded-full bg-white border border-border items-center justify-center shadow-elegant">
                      <ArrowRight size={12} className="text-muted-text" />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        <div className="mt-14 text-center">
          <a
            href="#demo"
            className="inline-flex items-center gap-1.5 text-primary font-semibold hover:gap-2.5 transition-all"
          >
            See a full walkthrough <ArrowRight size={16} />
          </a>
        </div>
      </div>
    </section>
  );
}
function Features() {
  const tiles = [
    { Icon: Bot, t: "AI Voice Calls", d: "Natural AI calls patients on your behalf" },
    { Icon: MessageCircle, t: "WhatsApp Messaging", d: "Automated WhatsApp follow-ups" },
    { Icon: CheckCircle2, t: "Confirmations", d: "Reduces no-shows automatically" },
    { Icon: RefreshCw, t: "Cancellation Recovery", d: "Acts on cancellations instantly" },
    { Icon: AlertTriangle, t: "No-Show Follow-Up", d: "Re-engages missed patients" },
    { Icon: BarChart3, t: "Revenue Dashboard", d: "See recovered revenue in real time" },
    { Icon: FileText, t: "Monthly Reports", d: "PDF reports showing your ROI" },
    { Icon: Link2, t: "Dentally Integration", d: "Connects to your existing system" },
    { Icon: PhoneOutgoing, t: "Your Own Number", d: "Calls display your clinic's number" },
    { Icon: ShieldCheck, t: "OFCOM Compliant", d: "UK calling hours always respected" },
  ];
  return (
    <section id="features" className="relative py-24 md:py-32 overflow-hidden">
      <AmbientBackdrop />
      <div className="relative max-w-[1180px] mx-auto px-5 md:px-10">
        <SectionHeader
          eyebrow="Everything you need"
          title={
            <>
              Built specifically for{" "}
              <span className="italic font-serif font-normal text-primary">dental clinics.</span>
            </>
          }
          sub="A complete recovery engine — voice, messaging, reporting and integrations — all wired into your existing Dentally workflow."
        />
        <div className="mt-14 grid grid-cols-2 md:grid-cols-5 gap-3 md:gap-4">
          {tiles.map(({ Icon, t, d }) => (
            <div key={t} className="group card-soft p-5 text-center">
              <div className="w-11 h-11 mx-auto rounded-xl bg-secondary group-hover:bg-primary/10 transition-colors flex items-center justify-center text-primary">
                <Icon size={20} />
              </div>
              <div className="mt-3 text-[14px] font-semibold text-heading">{t}</div>
              <div className="mt-1 text-[12px] text-muted-text leading-[1.5]">{d}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ---------------- TRANSPARENCY ---------------- */
function Transparency() {
  const points = [
    "Fully disclosed AI interaction — every time",
    "Call recording notification built into every call",
    "Opt-out offered on every call — OFCOM compliant",
  ];
  return (
    <section
      id="transparency"
      className="relative py-24 md:py-32 bg-dark text-white overflow-hidden"
    >
      <div
        className="absolute inset-0 opacity-30"
        style={{
          background:
            "radial-gradient(ellipse 60% 40% at 50% 0%, oklch(0.546 0.227 262 / 0.5), transparent 70%)",
        }}
      />
      <div className="relative max-w-[1180px] mx-auto px-5 md:px-10 grid md:grid-cols-[1.1fr_1fr] gap-12 items-center">
        <div>
          <span className="eyebrow !text-accent">Our commitment</span>
          <h2 className="mt-4 text-[30px] md:text-[44px] font-bold leading-[1.05] tracking-[-0.03em] text-white">
            We always tell patients they're{" "}
            <span className="italic font-serif font-normal text-accent">speaking with an AI.</span>
          </h2>
          <p className="mt-6 text-[16.5px] leading-[1.7] text-white/70 max-w-[520px]">
            Our AI introduces itself clearly and honestly at the start of every call — before
            discussing anything else. Patients appreciate the transparency, and your clinic stays
            fully compliant.
          </p>
        </div>
        <div className="space-y-3">
          {points.map((p) => (
            <div
              key={p}
              className="flex items-start gap-4 bg-white/[0.04] hover:bg-white/[0.08] transition-colors border border-white/10 rounded-xl px-5 py-4"
            >
              <div className="w-7 h-7 rounded-lg bg-accent/15 flex items-center justify-center text-accent shrink-0">
                <Check size={14} strokeWidth={3} />
              </div>
              <div className="text-[15px] text-white/90 pt-0.5">{p}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ---------------- PRICING (compact + extended layout) ---------------- */
function Pricing() {
  const [plans, setPlans] = useState<MarketingPlanCard[]>([]);
  const [rawPlans, setRawPlans] = useState<PublicPlanRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const rows = (await fetchPublicPlans()) as PublicPlanRow[];
        if (cancelled) return;
        const list = Array.isArray(rows) ? rows : [];
        setRawPlans(list);
        setPlans(mapPublicPlansToCards(list));
      } catch {
        if (!cancelled) {
          setRawPlans([]);
          setPlans(mapPublicPlansToCards([]));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const gridClass =
    plans.length <= 1
      ? "mt-12 grid max-w-md mx-auto gap-4"
      : plans.length === 2
        ? "mt-12 grid md:grid-cols-2 gap-4 items-stretch max-w-3xl mx-auto"
        : "mt-12 grid lg:grid-cols-3 gap-4 items-stretch";

  const footnote = overageFootnote(plans, rawPlans);

  return (
    <section id="pricing" className="relative py-24 md:py-32 bg-surface overflow-hidden">
      <div className="absolute inset-0 bg-grid opacity-50" />
      <div className="relative max-w-[1280px] mx-auto px-5 md:px-10">
        <SectionHeader
          eyebrow="Pricing"
          title={
            <>
              Per dentist. Per month.{" "}
              <span className="italic font-serif font-normal text-primary">
                Total transparency.
              </span>
            </>
          }
          sub="Pay per dentist, per month. One recovered appointment often covers the whole month's cost."
        />
        <p className="mt-3 text-center text-[13px] text-muted-text">
          Pay by direct debit · No setup fee · Cancel anytime · All prices ex VAT
        </p>

        <div className={gridClass}>
          {loading && (
            <div className="col-span-full text-center text-[13px] text-muted-text py-8">
              Loading plans…
            </div>
          )}
          {!loading &&
            plans.map((p, index) => (
            <div
              key={p.code}
              className={`relative rounded-2xl bg-white p-6 flex flex-col transition-all duration-300 ${
                p.featured
                  ? "border-2 border-primary shadow-glow lg:-translate-y-1"
                  : "border border-border hover:-translate-y-0.5 hover:shadow-elevated"
              }`}
            >
              {p.featured && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-accent text-white text-[10.5px] font-semibold tracking-wide uppercase px-3 py-1 rounded-full shadow-cta">
                  Most popular
                </div>
              )}
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="text-[18px] font-bold text-heading">{p.name}</h3>
                  <p className="text-[12.5px] text-muted-text mt-0.5">{p.who}</p>
                </div>
                <div
                  className={`w-9 h-9 rounded-xl flex items-center justify-center ${p.featured ? "bg-primary text-white" : "bg-secondary text-primary"}`}
                >
                  {index % 3 === 0 ? (
                    <Users size={16} />
                  ) : index % 3 === 1 ? (
                    <Sparkles size={16} />
                  ) : (
                    <BarChart3 size={16} />
                  )}
                </div>
              </div>

              <div className="mt-5">
                <div className="flex items-baseline gap-1.5">
                  <span className="text-[36px] font-bold text-heading tracking-tight tabular-nums">
                    {p.base}
                  </span>
                  <span className="text-[14px] text-muted-text">/mo</span>
                </div>
                <div className="text-[11.5px] text-body mt-0.5">{p.incl}</div>
                <div className="mt-2 inline-block text-[11.5px] text-primary bg-primary/10 px-2 py-0.5 rounded-md font-medium">
                  {p.extra}
                </div>
                <div className="mt-2 flex items-center gap-3 text-[11.5px]">
                  <span className="text-accent flex items-center gap-1">
                    <PhoneCall size={11} /> {p.calls}
                  </span>
                  <span className="text-success flex items-center gap-1">
                    <Check size={11} /> {p.trial}
                  </span>
                </div>
              </div>

              <div className="my-5 h-px bg-border" />

              <ul className="flex-1 space-y-2">
                {p.features.map((label) => (
                  <li key={label} className="flex items-start gap-2 text-[13px] text-body">
                    <Check size={14} className="text-primary mt-0.5 shrink-0" strokeWidth={2.5} />
                    <span>{label}</span>
                  </li>
                ))}
              </ul>

              <a
                href={p.signupHref}
                className={`mt-5 w-full ${p.ctaStyle === "primary" ? "btn-primary" : "btn-outline"} !py-3 text-[14px]`}
              >
                {p.cta} <ArrowRight size={14} />
              </a>
            </div>
          ))}
        </div>

        <p className="mt-6 text-center text-[12.5px] text-muted-text">{footnote}</p>

        {/* ROI nudge — wider, slimmer */}
        <div className="mt-12 mx-auto bg-dark text-white rounded-2xl p-6 md:p-8 relative overflow-hidden noise flex flex-col md:flex-row items-center justify-between gap-5">
          <div
            className="absolute inset-0 opacity-25"
            style={{
              background:
                "radial-gradient(ellipse 60% 100% at 30% 0%, var(--accent), transparent 70%)",
            }}
          />
          <div className="relative">
            <div className="text-[16px] md:text-[20px] font-semibold tracking-tight">
              Average Practice plan clinic recovers{" "}
              <span className="text-accent">£2,400/month</span>.
            </div>
            <p className="mt-1 text-white/60 text-[13px]">A 12× return on the £99/mo plan.</p>
          </div>
          <a
            href="#results"
            className="relative inline-flex items-center gap-2 bg-accent text-white font-semibold px-5 py-3 rounded-lg text-[14px] hover:brightness-110 transition shrink-0"
          >
            Calculate your ROI <ArrowRight size={16} />
          </a>
        </div>
      </div>
    </section>
  );
}

/* ---------------- ROI CALCULATOR (full-width 2-col) ---------------- */
function ROICalc() {
  const [appts, setAppts] = useState(150);
  const [rate, setRate] = useState(12);
  const [val, setVal] = useState(95);

  const cancellations = Math.round(appts * (rate / 100));
  const monthly = Math.round(cancellations * 0.4 * val);
  const annual = monthly * 12;
  const roi = (monthly / 99).toFixed(1);

  const sliderStyle = (v: number, min: number, max: number) =>
    ({ "--val": `${((v - min) / (max - min)) * 100}%` }) as React.CSSProperties &
      Record<"--val", string>;

  return (
    <section id="results" className="relative py-24 md:py-32 overflow-hidden">
      <div className="absolute inset-0 bg-mesh opacity-50" />
      <div className="relative max-w-[1280px] mx-auto px-5 md:px-10">
        <SectionHeader
          eyebrow="ROI calculator"
          title={
            <>
              How much is your clinic{" "}
              <span className="italic font-serif font-normal text-accent">
                leaving on the table?
              </span>
            </>
          }
          sub="Enter your numbers and get an instant estimate of how much revenue VOXBULK could recover each month."
        />

        <div className="mt-14 grid lg:grid-cols-2 gap-6">
          {/* INPUTS */}
          <div className="bg-white border border-border rounded-2xl shadow-elevated p-7 md:p-9">
            <div className="flex items-center justify-between">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-text">
                Your clinic numbers
              </div>
              <div className="inline-flex items-center gap-1.5 text-[11px] text-primary bg-primary/10 rounded-full px-2.5 py-1">
                <Sparkles size={12} /> Live estimate
              </div>
            </div>

            <div className="mt-7 space-y-7">
              <SliderRow
                label="Monthly appointments"
                value={appts.toString()}
                min={50}
                max={500}
                step={10}
                v={appts}
                onChange={setAppts}
                style={sliderStyle(appts, 50, 500)}
              />
              <SliderRow
                label="Cancellation rate"
                value={`${rate}%`}
                min={5}
                max={30}
                step={1}
                v={rate}
                onChange={setRate}
                style={sliderStyle(rate, 5, 30)}
              />
              <SliderRow
                label="Avg appointment value"
                value={`£${val}`}
                min={30}
                max={300}
                step={5}
                v={val}
                onChange={setVal}
                style={sliderStyle(val, 30, 300)}
              />
            </div>

            <p className="mt-6 text-[12px] text-muted-text">
              Recovery rate fixed at 40% — UK industry benchmark for AI-assisted recovery.
            </p>
          </div>

          {/* RESULTS */}
          <div className="relative bg-dark text-white rounded-2xl p-7 md:p-9 overflow-hidden noise">
            <div
              className="absolute inset-0 opacity-40"
              style={{
                background:
                  "radial-gradient(ellipse 80% 60% at 80% 0%, oklch(0.65 0.25 262 / 0.6), transparent 70%)",
              }}
            />
            <div className="absolute inset-0 bg-grid opacity-10" />
            <div className="relative">
              <div className="flex items-center justify-between">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-white/60">
                  Your estimated recovery
                </div>
                <div className="inline-flex items-center gap-1.5 text-[10.5px] text-accent bg-accent/10 border border-accent/20 rounded-full px-2.5 py-1">
                  <Sparkles size={11} /> Live
                </div>
              </div>

              <div className="mt-6">
                <div className="flex items-baseline gap-2 text-white/70">
                  <span className="text-[12px] uppercase tracking-wider font-semibold">
                    Monthly recovered revenue
                  </span>
                </div>
                <div className="mt-2 flex items-baseline gap-1 leading-none">
                  <span className="text-[36px] md:text-[44px] font-bold text-white/90 tabular-nums">
                    £
                  </span>
                  <span className="text-[60px] md:text-[80px] font-bold text-white tabular-nums tracking-[-0.03em]">
                    {monthly.toLocaleString()}
                  </span>
                </div>
                <div className="mt-2 text-[12.5px] text-white/55">
                  Per month, before subtracting your VOXBULK plan.
                </div>
              </div>

              {/* Cost vs recovery breakdown */}
              <div className="mt-6 grid grid-cols-2 gap-3">
                <div className="bg-white/[0.04] border border-white/10 rounded-xl p-4">
                  <div className="text-[10.5px] uppercase tracking-wider font-semibold text-white/50">
                    VOXBULK cost
                  </div>
                  <div className="mt-1.5 text-[22px] font-bold text-white tabular-nums">
                    £99<span className="text-[13px] font-medium text-white/50"> /mo</span>
                  </div>
                  <div className="mt-0.5 text-[11.5px] text-white/50">Solo plan</div>
                </div>
                <div className="bg-success/10 border border-success/20 rounded-xl p-4">
                  <div className="text-[10.5px] uppercase tracking-wider font-semibold text-success">
                    Net profit
                  </div>
                  <div className="mt-1.5 text-[22px] font-bold text-success tabular-nums">
                    £{Math.max(0, monthly - 99).toLocaleString()}
                    <span className="text-[13px] font-medium text-success/70"> /mo</span>
                  </div>
                  <div className="mt-0.5 text-[11.5px] text-white/50">After VOXBULK cost</div>
                </div>
              </div>

              <div className="mt-4 grid grid-cols-3 gap-3">
                <DarkStat
                  icon={<RefreshCw size={14} />}
                  label="Cancellations"
                  value={cancellations.toString()}
                />
                <DarkStat
                  icon={<TrendingUp size={14} />}
                  label="Annual"
                  value={`£${(annual / 1000).toFixed(1)}k`}
                />
                <DarkStat icon={<Sparkles size={14} />} label="ROI" value={`${roi}×`} highlight />
              </div>

              <div className="mt-5 bg-white/5 border border-white/10 rounded-xl p-4 text-[13px] text-white/80 leading-[1.6]">
                Based on industry benchmarks, your clinic could recover{" "}
                <span className="text-accent font-semibold">£{annual.toLocaleString()}</span> in
                lost revenue every year.
              </div>

              <a href="#demo" className="mt-5 w-full btn-primary !justify-center">
                Book a demo to confirm <ArrowRight size={16} />
              </a>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function SliderRow({
  label,
  value,
  min,
  max,
  step,
  v,
  onChange,
  style,
}: {
  label: string;
  value: string;
  min: number;
  max: number;
  step: number;
  v: number;
  onChange: (n: number) => void;
  style: React.CSSProperties;
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between mb-3">
        <label className="text-[14px] font-medium text-heading">{label}</label>
        <span className="text-[20px] font-bold text-primary tabular-nums">{value}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={v}
        onChange={(e) => onChange(Number(e.target.value))}
        className="premium-slider"
        style={style}
      />
    </div>
  );
}

function DarkStat({
  icon,
  label,
  value,
  highlight,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div className="bg-white/5 border border-white/10 rounded-xl p-3.5">
      <div className="flex items-center gap-1.5 text-white/50 text-[10.5px] uppercase tracking-wider font-semibold">
        {icon} {label}
      </div>
      <div
        className={`mt-1.5 text-[20px] font-bold tabular-nums tracking-tight ${highlight ? "text-accent" : "text-white"}`}
      >
        {value}
      </div>
    </div>
  );
}

/* ---------------- DEMO WIZARD ---------------- */
function DemoWizard() {
  const [step, setStep] = useState(1);
  const [data, setData] = useState({
    firstName: "",
    lastName: "",
    email: "",
    phone: "",
    clinic: "",
    role: "",
    dentists: "",
    source: "",
    date: "" as string,
    time: "" as string,
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [confirmed, setConfirmed] = useState(false);

  const set = (k: string, v: string) => setData((d) => ({ ...d, [k]: v }));

  const validate1 = () => {
    const e: Record<string, string> = {};
    if (!data.firstName) e.firstName = "Required";
    if (!data.lastName) e.lastName = "Required";
    if (!data.email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email))
      e.email = "Valid email required";
    if (!data.phone || data.phone.length < 7) e.phone = "Valid phone required";
    setErrors(e);
    return Object.keys(e).length === 0;
  };
  const validate2 = () => {
    const e: Record<string, string> = {};
    if (!data.clinic) e.clinic = "Required";
    if (!data.role) e.role = "Required";
    if (!data.dentists) e.dentists = "Required";
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const planPreview = useMemo(() => {
    const d = data.dentists;
    if (!d) return null;
    if (d === "1") return "Solo plan — from £99/mo · 100 AI calls included · 14-day free trial";
    if (d === "2") return "Solo plan — from £148/mo · 150 AI calls included · 14-day free trial";
    if (["3", "4", "5", "6"].includes(d))
      return "Practice plan — from £199/mo · 200+ calls included · 14-day free trial";
    return "Group plan — from £399/mo · 400+ calls included · 30-day free trial";
  }, [data.dentists]);

  const today = useMemo(() => new Date(), []);
  const [viewMonth, setViewMonth] = useState(
    () => new Date(today.getFullYear(), today.getMonth(), 1),
  );
  const monthLabel = viewMonth.toLocaleDateString("en-GB", { month: "long", year: "numeric" });
  const daysInMonth = new Date(viewMonth.getFullYear(), viewMonth.getMonth() + 1, 0).getDate();
  const firstWeekday =
    (new Date(viewMonth.getFullYear(), viewMonth.getMonth(), 1).getDay() + 6) % 7;

  const slots = [
    "9:00 AM",
    "9:30 AM",
    "10:00 AM",
    "10:30 AM",
    "11:00 AM",
    "11:30 AM",
    "2:00 PM",
    "2:30 PM",
    "3:00 PM",
    "3:30 PM",
    "4:00 PM",
    "4:30 PM",
  ];
  const unavailableSlots = new Set(["10:00 AM", "2:30 PM", "4:00 PM"]);

  return (
    <section id="demo" className="py-24 md:py-32 bg-surface relative overflow-hidden">
      <div className="absolute inset-0 bg-grid opacity-50" />
      <div className="relative max-w-[1180px] mx-auto px-5 md:px-10">
        <SectionHeader
          eyebrow="Book a demo"
          title={
            <>
              See VOXBULK live in{" "}
              <span className="italic font-serif font-normal text-primary">15 minutes.</span>
            </>
          }
          sub="Pick a time that works. We'll show you a live AI call demo and give you a personalised recovery estimate for your clinic."
        />

        <div className="mt-14 max-w-[920px] mx-auto bg-white border border-border rounded-2xl shadow-elevated overflow-hidden">
          {!confirmed && (
            <div className="bg-secondary/50 border-b border-border px-6 md:px-10 py-5">
              <div className="flex items-center justify-between max-w-[640px] mx-auto">
                {[
                  { n: 1, label: "Your details" },
                  { n: 2, label: "Your clinic" },
                  { n: 3, label: "Pick a time" },
                ].map((s, i, arr) => {
                  const done = step > s.n;
                  const active = step === s.n;
                  return (
                    <div key={s.n} className="flex items-center flex-1">
                      <div className="flex flex-col items-center">
                        <div
                          className={`w-8 h-8 rounded-full flex items-center justify-center text-[13px] font-semibold transition-all ${
                            done
                              ? "bg-success text-white"
                              : active
                                ? "bg-primary text-white shadow-glow"
                                : "bg-border text-muted-text"
                          }`}
                        >
                          {done ? <Check size={14} strokeWidth={3} /> : s.n}
                        </div>
                        <div
                          className={`mt-2 text-[12px] font-medium ${active ? "text-primary" : done ? "text-success" : "text-muted-text"}`}
                        >
                          {s.label}
                        </div>
                      </div>
                      {i < arr.length - 1 && (
                        <div
                          className={`flex-1 h-[2px] mx-3 mb-5 rounded-full transition-colors ${done ? "bg-success" : "bg-border"}`}
                        />
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {confirmed ? (
            <div className="p-10 md:p-16 text-center">
              <div className="mx-auto w-16 h-16 rounded-full bg-success/15 text-success flex items-center justify-center animate-scale-in">
                <Check size={32} strokeWidth={3} />
              </div>
              <h3 className="mt-6 text-[26px] md:text-[32px] font-bold text-heading tracking-tight">
                You're booked in! 🎉
              </h3>
              <p className="mt-3 text-[16px] text-body">
                Your demo is confirmed for <strong className="text-heading">{data.date}</strong> at{" "}
                <strong className="text-heading">{data.time}</strong>. Check your email for the
                calendar invite.
              </p>
              <div className="mt-8 mx-auto max-w-[440px] bg-surface border border-border rounded-xl p-5 text-left">
                <div className="text-[12.5px] font-semibold text-heading mb-3">
                  What happens next:
                </div>
                <ul className="space-y-2 text-[13.5px] text-body">
                  {[
                    "You'll receive a calendar invite with the video call link",
                    "Our AI assistant may call you to confirm — it will introduce itself as an AI",
                    "We'll prepare a personalised recovery estimate for your clinic before the call",
                  ].map((it) => (
                    <li key={it} className="flex gap-2.5">
                      <span className="text-accent">●</span>
                      <span>{it}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <button className="btn-outline mt-7">
                <CalendarIcon size={16} /> Add to calendar
              </button>
            </div>
          ) : (
            <div className="p-6 md:p-10">
              {step === 1 && (
                <div className="animate-fade-in">
                  <h3 className="text-[20px] font-bold text-heading">Tell us about yourself</h3>
                  <p className="mt-1.5 text-[14px] text-body">
                    We'll use these details to personalise your demo.
                  </p>
                  <div className="mt-7 grid sm:grid-cols-2 gap-5">
                    <Field
                      label="First name *"
                      placeholder="Sarah"
                      value={data.firstName}
                      onChange={(v) => set("firstName", v)}
                      error={errors.firstName}
                    />
                    <Field
                      label="Last name *"
                      placeholder="Johnson"
                      value={data.lastName}
                      onChange={(v) => set("lastName", v)}
                      error={errors.lastName}
                    />
                    <div className="sm:col-span-2">
                      <Field
                        label="Email address *"
                        type="email"
                        placeholder="sarah@smileclinic.co.uk"
                        value={data.email}
                        onChange={(v) => set("email", v)}
                        error={errors.email}
                      />
                    </div>
                    <div className="sm:col-span-2">
                      <Field
                        label="Phone number *"
                        type="tel"
                        placeholder="+44 7700 900000"
                        value={data.phone}
                        onChange={(v) => set("phone", v)}
                        error={errors.phone}
                        help="Our AI assistant may call to confirm your demo time — it will introduce itself as an AI."
                      />
                    </div>
                  </div>
                  <div className="mt-8 flex justify-end">
                    <button className="btn-primary" onClick={() => validate1() && setStep(2)}>
                      Continue <ArrowRight size={16} />
                    </button>
                  </div>
                </div>
              )}

              {step === 2 && (
                <div className="animate-fade-in">
                  <h3 className="text-[20px] font-bold text-heading">About your clinic</h3>
                  <p className="mt-1.5 text-[14px] text-body">
                    This helps us show you the most relevant demo.
                  </p>
                  <div className="mt-7 grid sm:grid-cols-2 gap-5">
                    <Field
                      label="Clinic name *"
                      placeholder="Smile Dental Clinic"
                      value={data.clinic}
                      onChange={(v) => set("clinic", v)}
                      error={errors.clinic}
                    />
                    <Select
                      label="Your role *"
                      value={data.role}
                      onChange={(v) => set("role", v)}
                      error={errors.role}
                      options={[
                        "Please select...",
                        "Practice Owner",
                        "Practice Manager",
                        "Receptionist",
                        "Other",
                      ]}
                    />
                    <div className="sm:col-span-2">
                      <Select
                        label="How many dentists work at your clinic? *"
                        value={data.dentists}
                        onChange={(v) => set("dentists", v)}
                        error={errors.dentists}
                        options={["Please select...", "1", "2", "3", "4", "5", "6", "7-10", "10+"]}
                        labelMap={{
                          "1": "1 dentist",
                          "2": "2 dentists",
                          "3": "3 dentists",
                          "4": "4 dentists",
                          "5": "5 dentists",
                          "6": "6 dentists",
                          "7-10": "7–10 dentists",
                          "10+": "10+ dentists",
                        }}
                        help="This determines which plan and pricing we show you."
                      />
                    </div>
                    <div className="sm:col-span-2">
                      <Select
                        label="How did you hear about VOXBULK?"
                        value={data.source}
                        onChange={(v) => set("source", v)}
                        options={[
                          "Please select...",
                          "Google Search",
                          "Facebook",
                          "Instagram",
                          "LinkedIn",
                          "Referral from colleague",
                          "Other",
                        ]}
                      />
                    </div>
                  </div>
                  {planPreview && (
                    <div className="mt-6 bg-primary/5 border border-primary/20 rounded-xl p-4 animate-fade-in">
                      <div className="text-[11px] font-semibold uppercase tracking-wider text-body">
                        Your estimated plan
                      </div>
                      <div className="mt-1 text-[14px] font-semibold text-primary">
                        {planPreview}
                      </div>
                    </div>
                  )}
                  <div className="mt-8 flex justify-between">
                    <button
                      className="text-body font-medium hover:text-heading transition-colors"
                      onClick={() => setStep(1)}
                    >
                      ← Back
                    </button>
                    <button className="btn-primary" onClick={() => validate2() && setStep(3)}>
                      Continue <ArrowRight size={16} />
                    </button>
                  </div>
                </div>
              )}

              {step === 3 && (
                <div className="animate-fade-in">
                  <h3 className="text-[20px] font-bold text-heading">Choose your demo time</h3>
                  <p className="mt-1.5 text-[14px] text-body">
                    All demos are 15 minutes via video call. Pick a slot that works for you.
                  </p>

                  <div className="mt-7 grid md:grid-cols-2 gap-8">
                    <div>
                      <div className="flex items-center justify-between mb-4">
                        <button
                          className="w-8 h-8 rounded-lg hover:bg-secondary text-primary flex items-center justify-center"
                          onClick={() =>
                            setViewMonth(
                              new Date(viewMonth.getFullYear(), viewMonth.getMonth() - 1, 1),
                            )
                          }
                        >
                          <ChevronLeft size={18} />
                        </button>
                        <div className="text-[15px] font-semibold text-heading">{monthLabel}</div>
                        <button
                          className="w-8 h-8 rounded-lg hover:bg-secondary text-primary flex items-center justify-center"
                          onClick={() =>
                            setViewMonth(
                              new Date(viewMonth.getFullYear(), viewMonth.getMonth() + 1, 1),
                            )
                          }
                        >
                          <ChevronRight size={18} />
                        </button>
                      </div>
                      <div className="grid grid-cols-7 gap-1 text-center">
                        {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => (
                          <div key={d} className="text-[11px] text-muted-text font-medium py-1.5">
                            {d}
                          </div>
                        ))}
                        {Array.from({ length: firstWeekday }).map((_, i) => (
                          <div key={`b${i}`} />
                        ))}
                        {Array.from({ length: daysInMonth }).map((_, i) => {
                          const day = i + 1;
                          const date = new Date(viewMonth.getFullYear(), viewMonth.getMonth(), day);
                          const isPast =
                            date < new Date(today.getFullYear(), today.getMonth(), today.getDate());
                          const weekend = date.getDay() === 0 || date.getDay() === 6;
                          const disabled = isPast || weekend;
                          const dateStr = date.toLocaleDateString("en-GB", {
                            weekday: "short",
                            day: "numeric",
                            month: "short",
                          });
                          const isSelected = data.date === dateStr;
                          const isToday = date.toDateString() === today.toDateString();
                          return (
                            <button
                              key={day}
                              disabled={disabled}
                              onClick={() => {
                                set("date", dateStr);
                                set("time", "");
                              }}
                              className={`h-9 rounded-lg text-[13.5px] font-medium transition-all ${
                                isSelected
                                  ? "bg-primary text-white shadow-glow"
                                  : disabled
                                    ? "text-border cursor-not-allowed"
                                    : isToday
                                      ? "border border-primary text-primary hover:bg-primary/5"
                                      : "text-heading hover:bg-primary/10 hover:text-primary"
                              }`}
                            >
                              {day}
                            </button>
                          );
                        })}
                      </div>
                      <p className="mt-4 text-[12px] text-muted-text">
                        All times shown in GMT/BST (London).
                      </p>
                    </div>

                    <div>
                      <div className="text-[14px] font-semibold text-heading mb-4">
                        {data.date ? `Available times — ${data.date}` : "Select a date first"}
                      </div>
                      <div
                        className={`grid grid-cols-2 gap-2 ${data.date ? "" : "opacity-50 pointer-events-none"}`}
                      >
                        {slots.map((s) => {
                          const unavail = unavailableSlots.has(s);
                          const sel = data.time === s;
                          return (
                            <button
                              key={s}
                              disabled={unavail}
                              onClick={() => set("time", s)}
                              className={`py-2.5 rounded-lg text-[13.5px] font-medium transition-all border ${
                                sel
                                  ? "bg-primary text-white border-primary"
                                  : unavail
                                    ? "bg-secondary text-border border-border cursor-not-allowed"
                                    : "bg-white text-heading border-border hover:border-primary hover:text-primary"
                              }`}
                            >
                              {s}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  </div>

                  <div className="mt-8 flex justify-between">
                    <button
                      className="text-body font-medium hover:text-heading transition-colors"
                      onClick={() => setStep(2)}
                    >
                      ← Back
                    </button>
                    <button
                      className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none"
                      disabled={!data.date || !data.time}
                      onClick={() => setConfirmed(true)}
                    >
                      Confirm my demo <ArrowRight size={16} />
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function Field({
  label,
  type = "text",
  placeholder,
  value,
  onChange,
  error,
  help,
}: {
  label: string;
  type?: string;
  placeholder?: string;
  value: string;
  onChange: (v: string) => void;
  error?: string;
  help?: string;
}) {
  return (
    <div>
      <label className="block text-[13px] font-medium text-heading mb-1.5">{label}</label>
      <input
        type={type}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={`w-full px-4 py-3 text-[14.5px] bg-white border rounded-lg outline-none transition-all ${
          error
            ? "border-destructive ring-2 ring-destructive/15"
            : "border-border focus:border-primary focus:ring-2 focus:ring-primary/15"
        }`}
      />
      {error && <p className="mt-1.5 text-[12px] text-destructive">{error}</p>}
      {help && !error && <p className="mt-1.5 text-[12px] text-muted-text">{help}</p>}
    </div>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
  error,
  help,
  labelMap,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
  error?: string;
  help?: string;
  labelMap?: Record<string, string>;
}) {
  return (
    <div>
      <label className="block text-[13px] font-medium text-heading mb-1.5">{label}</label>
      <div className="relative">
        <select
          value={value}
          onChange={(e) => onChange(e.target.value === "Please select..." ? "" : e.target.value)}
          className={`w-full appearance-none px-4 py-3 pr-10 text-[14.5px] bg-white border rounded-lg outline-none transition-all ${
            error
              ? "border-destructive ring-2 ring-destructive/15"
              : "border-border focus:border-primary focus:ring-2 focus:ring-primary/15"
          }`}
        >
          {options.map((o: string) => (
            <option key={o} value={o === "Please select..." ? "" : o}>
              {labelMap?.[o] ?? o}
            </option>
          ))}
        </select>
        <svg
          className="absolute right-3 top-1/2 -translate-y-1/2 text-primary pointer-events-none"
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </div>
      {error && <p className="mt-1.5 text-[12px] text-destructive">{error}</p>}
      {help && !error && <p className="mt-1.5 text-[12px] text-muted-text">{help}</p>}
    </div>
  );
}

/* ---------------- INDUSTRIES ---------------- */
function Industries() {
  const cards = [
    {
      Icon: Stethoscope,
      title: "VB Dental",
      tag: "Live",
      tagColor: "bg-success/15 text-success",
      body: "AI recovery for dental clinics. Works with Dentally. GDPR and OFCOM compliant.",
      cta: "Get started",
      border: "border-primary/30",
      iconBg: "from-primary to-primary-dark",
    },
    {
      Icon: Eye,
      title: "VB Opticians",
      tag: "Coming soon",
      tagColor: "bg-blue-100 text-blue-700",
      body: "Recall reminders and appointment recovery for optometry and eyewear practices.",
      cta: "Join waitlist",
      border: "border-blue-200",
      iconBg: "from-blue-500 to-cyan-500",
    },
    {
      Icon: Flower2,
      title: "VB Beauty",
      tag: "Coming soon",
      tagColor: "bg-purple-100 text-purple-700",
      body: "Recovery and rebooking for beauty salons, aesthetics, and cosmetic clinics.",
      cta: "Join waitlist",
      border: "border-purple-200",
      iconBg: "from-purple-500 to-pink-500",
    },
    {
      Icon: Heart,
      title: "VB Wellness",
      tag: "Coming soon",
      tagColor: "bg-emerald-100 text-emerald-700",
      body: "For massage, physio, osteopathy, and wellness centres.",
      cta: "Join waitlist",
      border: "border-emerald-200",
      iconBg: "from-emerald-500 to-teal-500",
    },
  ];
  return (
    <section id="industries" className="py-24 md:py-32 bg-surface">
      <div className="max-w-[1180px] mx-auto px-5 md:px-10">
        <SectionHeader
          eyebrow="Industries"
          title={
            <>
              Starting with dental.{" "}
              <span className="italic font-serif font-normal text-primary">Built to expand.</span>
            </>
          }
          sub="VOXBULK is designed as a multi-industry platform. Each industry gets its own sub-brand, terminology, and integrations — powered by the same AI engine."
        />
        <div className="mt-14 grid md:grid-cols-2 gap-5 max-w-[880px] mx-auto">
          {cards.map((c) => (
            <div
              key={c.title}
              className={`bg-white border ${c.border} rounded-2xl p-7 hover:-translate-y-1 hover:shadow-elevated transition-all duration-300`}
            >
              <div
                className={`w-12 h-12 rounded-xl bg-gradient-to-br ${c.iconBg} text-white flex items-center justify-center shadow-elegant`}
              >
                <c.Icon size={22} />
              </div>
              <div className="mt-4 flex items-center gap-2.5 flex-wrap">
                <h3 className="text-[19px] font-bold tracking-tight text-heading">{c.title}</h3>
                <span
                  className={`text-[10.5px] font-semibold px-2.5 py-0.5 rounded-full uppercase tracking-wider ${c.tagColor}`}
                >
                  {c.tag}
                </span>
              </div>
              <p className="mt-3 text-[14.5px] text-body leading-[1.6]">{c.body}</p>
              <a
                href="#demo"
                className="inline-flex items-center gap-1.5 mt-4 text-[14px] font-semibold text-primary hover:gap-2 transition-all"
              >
                {c.cta} <ArrowRight size={14} />
              </a>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ---------------- TESTIMONIAL (Modern carousel) ---------------- */
function Testimonial() {
  const quotes = [
    {
      text: "We recovered £1,800 in our first month without changing anything about how we work. The AI calls are professional and our patients didn't mind at all.",
      name: "Practice Manager",
      clinic: "London Dental Clinic",
      initials: "PM",
    },
    {
      text: "Setup took 25 minutes. By the end of week two, VOXBULK had filled 14 cancelled slots that would have stayed empty. Genuinely impressed.",
      name: "Dr. Hassan",
      clinic: "Manchester Smile Studio",
      initials: "DH",
    },
    {
      text: "Patients keep telling us they appreciate the AI being upfront about what it is. It's so far ahead of robocall scripts — feels like a real assistant.",
      name: "Reception Lead",
      clinic: "Bristol Family Dental",
      initials: "RL",
    },
  ];
  const [idx, setIdx] = useState(0);
  const q = quotes[idx];

  return (
    <section id="testimonial" className="relative py-24 md:py-32 overflow-hidden">
      <div className="absolute inset-0 bg-mesh opacity-50" />
      <div className="relative max-w-[1080px] mx-auto px-5 md:px-10">
        <SectionHeader
          eyebrow="What clinics say"
          title={
            <>
              Loved by{" "}
              <span className="italic font-serif font-normal text-primary">UK clinics.</span>
            </>
          }
        />

        <div className="mt-14 relative">
          {/* Big quote mark */}
          <div className="absolute -top-8 left-6 md:left-10 z-0">
            <Quote size={120} className="text-primary/10 fill-primary/10 -scale-x-100" />
          </div>

          <div className="relative bg-white border border-border rounded-3xl p-8 md:p-14 shadow-elevated">
            <div className="grid md:grid-cols-[auto_1fr] gap-8 md:gap-12 items-center">
              {/* Avatar block */}
              <div className="flex md:flex-col items-center md:items-start gap-4 md:gap-3">
                <div className="relative">
                  <div className="w-20 h-20 md:w-24 md:h-24 rounded-2xl bg-gradient-to-br from-primary to-primary-dark text-white flex items-center justify-center font-bold text-[28px] shadow-glow">
                    {q.initials}
                  </div>
                  <div className="absolute -bottom-2 -right-2 w-8 h-8 rounded-full bg-success text-white flex items-center justify-center border-4 border-white">
                    <Check size={14} strokeWidth={3} />
                  </div>
                </div>
                <div>
                  <div className="text-[15px] font-bold text-heading">{q.name}</div>
                  <div className="text-[13px] text-muted-text">{q.clinic}</div>
                  <div className="mt-1.5 flex items-center gap-0.5 text-accent">
                    {[...Array(5)].map((_, i) => (
                      <Star key={i} size={13} fill="currentColor" />
                    ))}
                  </div>
                </div>
              </div>

              {/* Quote */}
              <div>
                <blockquote
                  key={idx}
                  className="text-[20px] md:text-[26px] font-medium text-heading leading-[1.4] tracking-tight animate-fade-in"
                >
                  {q.text}
                </blockquote>

                {/* Controls */}
                <div className="mt-8 flex items-center justify-between">
                  <div className="flex gap-2">
                    {quotes.map((_, i) => (
                      <button
                        key={i}
                        onClick={() => setIdx(i)}
                        className={`h-1.5 rounded-full transition-all ${i === idx ? "w-8 bg-primary" : "w-1.5 bg-border hover:bg-primary/40"}`}
                        aria-label={`Quote ${i + 1}`}
                      />
                    ))}
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setIdx((idx - 1 + quotes.length) % quotes.length)}
                      className="w-10 h-10 rounded-full border border-border hover:border-primary hover:text-primary text-body flex items-center justify-center transition-all"
                    >
                      <ChevronLeft size={18} />
                    </button>
                    <button
                      onClick={() => setIdx((idx + 1) % quotes.length)}
                      className="w-10 h-10 rounded-full border border-border bg-primary text-white hover:brightness-110 flex items-center justify-center transition-all"
                    >
                      <ChevronRight size={18} />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <p className="mt-6 text-center text-[12.5px] text-muted-text">
          Early access testimonials. VOXBULK is currently onboarding its first clinics.
        </p>
      </div>
    </section>
  );
}

/* ---------------- BOTTOM CTA ---------------- */
function BottomCTA() {
  return (
    <section
      id="cta"
      className="relative py-24 md:py-32 overflow-hidden"
      style={{ background: "linear-gradient(135deg, #020617 0%, #0F0C29 50%, #1E1B4B 100%)" }}
    >
      <div
        className="absolute inset-0 opacity-40"
        style={{
          background:
            "radial-gradient(ellipse 70% 50% at 50% 0%, rgba(249,115,22,0.35), transparent 70%)",
        }}
      />
      <div className="absolute inset-0 bg-grid opacity-[0.07]" />
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 50% 40% at 80% 100%, rgba(251,169,76,0.18), transparent 60%)",
        }}
      />
      <div className="relative max-w-[820px] mx-auto px-5 md:px-10 text-center text-white">
        <span className="inline-flex items-center gap-2 bg-white/10 border border-white/20 backdrop-blur rounded-full px-4 py-1.5 text-[12.5px] font-medium">
          <span className="w-1.5 h-1.5 rounded-full bg-success pulse-dot" /> Limited demo slots this
          week
        </span>
        <h2 className="mt-6 text-[34px] md:text-[52px] font-bold leading-[1.05] tracking-[-0.03em] text-white">
          See how much your clinic could{" "}
          <span className="italic font-serif font-normal">recover.</span>
        </h2>
        <p className="mt-5 text-[16px] md:text-[18px] text-white/75 max-w-[540px] mx-auto leading-[1.55]">
          Book a free 15-minute demo. No commitment. We'll show you VOXBULK live with your clinic
          setup and give you a personalised recovery estimate.
        </p>
        <div className="mt-9 flex flex-wrap justify-center gap-3">
          <a href="#demo" className="btn-primary !px-8 !py-4 text-[15px]">
            Book my free demo <ArrowRight size={16} />
          </a>
          <a
            href="#results"
            className="btn-outline !bg-white/10 !border-white/30 !text-white hover:!bg-white/20 hover:!border-white/40 !py-4 !px-7"
          >
            Calculate your ROI
          </a>
        </div>
        <p className="mt-5 text-[12.5px] text-white/55">
          Average setup time: 30 minutes · No software to replace · Cancel anytime
        </p>
      </div>
    </section>
  );
}

/* ---------------- FOOTER ---------------- */
function Footer() {
  return (
    <footer className="bg-dark text-white pt-20 pb-10">
      <div className="max-w-[1180px] mx-auto px-5 md:px-10">
        <div className="grid md:grid-cols-4 grid-cols-2 gap-10">
          <div className="col-span-2 md:col-span-1">
            <img src={logoLight} alt="VOXBULK" className="h-8 w-auto" />
            <p className="mt-4 text-[14px] text-white/60 leading-[1.7] max-w-[260px]">
              Intelligent Voice Calls at Scale.
            </p>
            <p className="mt-5 text-[13px] text-white/40">
              © 2026 VOXBULK LTD. All rights reserved.
            </p>
          </div>

          <FooterCol
            title="Product"
            links={[
              ["How it works", "#how-it-works"],
              ["Pricing", "#pricing"],
              ["ROI calculator", "#results"],
              ["Book a demo", "#demo"],
            ]}
          />
          <FooterCol
            title="Industries"
            links={[
              ["VB Dental", "#industries"],
              ["VB Opticians (soon)", null],
              ["VB Beauty (soon)", null],
              ["VB Wellness (soon)", null],
            ]}
          />
          <FooterCol
            title="Legal"
            links={[
              ["Legal & policies", "/legal-policies"],
              ["Contact us", "/contact"],
            ]}
          />
        </div>

        <div className="my-10 h-px bg-white/10" />

        <div className="flex flex-wrap items-center justify-between gap-3 text-[12px] text-white/40">
          <div>VOXBULK LTD · Registered in England &amp; Wales</div>
          <div>ICO Registered · OFCOM Compliant · GDPR Compliant</div>
        </div>
      </div>
    </footer>
  );
}

function FooterCol({ title, links }: { title: string; links: Array<[string, string | null]> }) {
  return (
    <div>
      <div className="text-[12px] font-semibold uppercase tracking-[0.1em] text-white mb-4">
        {title}
      </div>
      <ul className="space-y-2.5">
        {links.map(([label, href]) => (
          <li key={label}>
            {!href ? (
              <span className="text-[14px] text-white/30">{label}</span>
            ) : href.startsWith("/") ? (
              <Link
                to={href}
                className="text-[14px] text-white/60 hover:text-white transition-colors"
              >
                {label}
              </Link>
            ) : (
              <a
                href={href}
                className="text-[14px] text-white/60 hover:text-white transition-colors"
              >
                {label}
              </a>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ---------------- TALK TO US ---------------- */
function TalkToUs() {
  const [status, setStatus] = useState<"idle" | "connecting" | "live" | "ended" | "error">("idle");
  const [activeVoiceProvider, setActiveVoiceProvider] = useState<"vapi" | "telnyx">("vapi");
  const [seconds, setSeconds] = useState(0);
  const [modalOpen, setModalOpen] = useState(false);
  const [contactName, setContactName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [formError, setFormError] = useState("");
  const [callId, setCallId] = useState("");
  const callIdRef = useRef("");
  const finalizedRef = useRef(false);
  const vapiProviderCallIdRef = useRef("");
  const telnyxProviderCallIdRef = useRef("");
  const voiceProviderRef = useRef<"vapi" | "telnyx">("vapi");
  const vapiConnectTimeoutRef = useRef<number | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const recordedChunksRef = useRef<Blob[]>([]);
  const socketRef = useRef<WebSocket | null>(null);
  const telnyxAgentRef = useRef<{
    endConversation(): Promise<void>;
    disconnect(): Promise<void>;
  } | null>(null);
  const telnyxAudioRef = useRef<HTMLAudioElement | null>(null);
  const telnyxConnectTimeoutRef = useRef<number | null>(null);
  const telnyxStartingRef = useRef(false);
  const telnyxMixAudioContextRef = useRef<AudioContext | null>(null);
  const telnyxRecorderStartedRef = useRef(false);
  const vapiRef = useRef<{
    stop(): void;
    start(assistantId: string, overrides?: unknown): Promise<void>;
    on(event: string, handler: (...args: unknown[]) => void): void;
    send?(payload: unknown): void;
  } | null>(null);
  const transcriptPartsRef = useRef<string[]>([]);
  const agentPartsRef = useRef<string[]>([]);
  const conversationLinesRef = useRef<string[]>([]);
  const ringbackRef = useRef<RingbackController | null>(null);

  useEffect(() => {
    ringbackRef.current = createRingbackTone();
    return () => {
      ringbackRef.current?.stop(0);
    };
  }, []);

  const startRingback = () => {
    try {
      ringbackRef.current?.start();
    } catch {
      /* ignore */
    }
  };

  const stopRingback = () => {
    try {
      ringbackRef.current?.stop(180);
    } catch {
      /* ignore */
    }
  };

  const speakerLabel = (role: string) => {
    const clean = role.trim().toLowerCase();
    if (clean === "user" || clean === "customer") return "User";
    if (clean === "assistant" || clean === "bot" || clean === "ai") return "Agent";
    return "";
  };

  const appendConversationLine = (role: string, content: string) => {
    const text = content.trim();
    const label = speakerLabel(role);
    if (!label || !text) return;
    const line = `${label}: ${text}`;
    const lines = conversationLinesRef.current;
    if (lines[lines.length - 1] === line) return;
    lines.push(line);
    if (label === "User") transcriptPartsRef.current.push(line);
    else agentPartsRef.current.push(line);
  };

  const ingestVapiConversationMessages = (messages: unknown[]) => {
    conversationLinesRef.current = [];
    transcriptPartsRef.current = [];
    agentPartsRef.current = [];
    for (const raw of messages) {
      if (!raw || typeof raw !== "object") continue;
      const msg = raw as Record<string, unknown>;
      if (msg.toolCalls || msg.toolCallId) continue;
      const role = String(msg.role || "");
      const nested = msg.message;
      const text =
        typeof nested === "string"
          ? nested.trim()
          : String(msg.transcript || msg.content || "").trim();
      appendConversationLine(role, text);
    }
  };
  const callStartedAtRef = useRef<number>(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioQueueRef = useRef<Array<{ audio_b64: string; audio_mime?: string }>>([]);
  const audioPlayingRef = useRef(false);

  useEffect(() => {
    if (status !== "live") return;
    const id = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [status]);

  useEffect(() => () => stopBrowserCall(), []);

  const openLeadModal = () => {
    setFormError("");
    setModalOpen(true);
  };

  const closeLeadModal = () => {
    if (status === "connecting") return;
    setModalOpen(false);
    if (status !== "live") setStatus("idle");
  };

  const stopBrowserCall = () => {
    stopRingback();
    if (vapiConnectTimeoutRef.current) {
      window.clearTimeout(vapiConnectTimeoutRef.current);
      vapiConnectTimeoutRef.current = null;
    }
    try {
      vapiRef.current?.stop();
    } catch {
      /* ignore */
    }
    vapiRef.current = null;
    if (telnyxConnectTimeoutRef.current) {
      window.clearTimeout(telnyxConnectTimeoutRef.current);
      telnyxConnectTimeoutRef.current = null;
    }
    const telnyxAgent = telnyxAgentRef.current;
    if (telnyxAgent) {
      void telnyxAgent.endConversation().catch(() => undefined);
      void telnyxAgent.disconnect().catch(() => undefined);
    }
    telnyxAgentRef.current = null;
    telnyxRecorderStartedRef.current = false;
    if (telnyxMixAudioContextRef.current) {
      void telnyxMixAudioContextRef.current.close().catch(() => undefined);
      telnyxMixAudioContextRef.current = null;
    }
    if (telnyxAudioRef.current) {
      telnyxAudioRef.current.pause();
      telnyxAudioRef.current.srcObject = null;
    }
    try {
      socketRef.current?.send(JSON.stringify({ type: "close" }));
      socketRef.current?.close();
    } catch {
      /* ignore */
    }
    try {
      if (recorderRef.current?.state !== "inactive") recorderRef.current?.stop();
    } catch {
      /* ignore */
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    recorderRef.current = null;
    socketRef.current = null;
    audioRef.current?.pause();
    audioRef.current = null;
    audioQueueRef.current = [];
    audioPlayingRef.current = false;
  };

  const startMicRecorder = (micStream: MediaStream, options?: { forwardToSocket?: boolean }) => {
    recordedChunksRef.current = [];
    const recorder = new MediaRecorder(
      micStream,
      { mimeType: MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "audio/webm" },
    );
    recorder.ondataavailable = (event) => {
      if (!event.data?.size) return;
      recordedChunksRef.current.push(event.data);
      if (options?.forwardToSocket && socketRef.current?.readyState === WebSocket.OPEN) {
        socketRef.current.send(event.data);
      }
    };
    recorderRef.current = recorder;
    return recorder;
  };

  const finalizeCall = async (endedCallId: string) => {
    if (!endedCallId || finalizedRef.current) return;
    finalizedRef.current = true;
    const duration = callStartedAtRef.current
      ? Math.max(0, Math.round((Date.now() - callStartedAtRef.current) / 1000))
      : seconds;
    const isTelnyx = voiceProviderRef.current === "telnyx";
    const recording =
      !isTelnyx && recordedChunksRef.current.length > 0
        ? new Blob(recordedChunksRef.current, { type: "audio/webm" })
        : null;
    try {
      const transcriptText =
        conversationLinesRef.current.length > 0
          ? conversationLinesRef.current.join("\n")
          : [...transcriptPartsRef.current, ...agentPartsRef.current].join("\n");
      await completeFrontpageTalkToUsCall(endedCallId, {
        transcript_text: transcriptText,
        agent_response_text: "",
        duration_seconds: duration,
        recording,
        provider_call_id: isTelnyx
          ? telnyxProviderCallIdRef.current || undefined
          : vapiProviderCallIdRef.current || undefined,
      });
    } catch {
      /* lead still created; admin can review partial data */
    }
  };

  const playNextAudio = () => {
    if (audioPlayingRef.current) return;
    const next = audioQueueRef.current.shift();
    if (!next) return;
    audioPlayingRef.current = true;
    const audio = new Audio(`data:${next.audio_mime || "audio/wav"};base64,${next.audio_b64}`);
    audioRef.current = audio;
    audio.onended = () => {
      audioPlayingRef.current = false;
      playNextAudio();
    };
    audio.onerror = () => {
      audioPlayingRef.current = false;
      playNextAudio();
    };
    audio.play().catch(() => {
      audioPlayingRef.current = false;
      audioQueueRef.current.unshift(next);
      setFormError("Browser blocked audio playback. Click Talk to us again after enabling audio.");
    });
  };

  const unlockAudioPlayback = async () => {
    try {
      const silent = new Audio(
        "data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEAESsAACJWAAACABAAZGF0YQQAAAAAAA==",
      );
      silent.muted = true;
      silent.volume = 0;
      await silent.play();
      silent.pause();
    } catch {
      /* browser may still allow Vapi WebRTC audio */
    }
  };

  const startVapiVoiceCall = async (
    _newCallId: string,
    vapiSession: {
      public_key: string;
      assistant_id: string;
      system_prompt: string;
      variable_values?: Record<string, string>;
      first_message?: string;
    },
  ) => {
    const publicKey = String(vapiSession.public_key || "").trim();
    const assistantId = String(vapiSession.assistant_id || "").trim();
    const systemPrompt = String(vapiSession.system_prompt || "").trim();
    if (!publicKey || !assistantId) {
      throw new Error("Vapi is not configured. Set public key (Integrations) and assistant ID (admin).");
    }

    try {
      vapiRef.current?.stop();
    } catch {
      /* ignore */
    }
    vapiRef.current = null;
    vapiProviderCallIdRef.current = "";

    await unlockAudioPlayback();

    const { default: Vapi } = await import("@vapi-ai/web");
    const vapi = new Vapi(publicKey);

    vapi.on("call-start", () => {
      if (vapiConnectTimeoutRef.current) {
        window.clearTimeout(vapiConnectTimeoutRef.current);
        vapiConnectTimeoutRef.current = null;
      }
      if (systemPrompt) {
        try {
          vapi.send?.({
            type: "add-message",
            message: { role: "system", content: systemPrompt },
          });
        } catch {
          /* assistant may already have a system prompt in Vapi dashboard */
        }
      }
      callStartedAtRef.current = Date.now();
      setSeconds(0);
      setStatus("live");
    });

    vapi.on("call-start-success", (event: { callId?: string }) => {
      if (event?.callId) vapiProviderCallIdRef.current = String(event.callId);
    });

    vapi.on("call-start-failed", (event: { error?: { message?: string }; stage?: string }) => {
      const message =
        event?.error?.message ||
        `Vapi could not connect (${event?.stage || "setup failed"}). Check assistant ID and Vapi public key.`;
      setFormError(message);
      setStatus("error");
    });

    vapi.on("call-end", () => {
      setStatus("ended");
      const endedId = callIdRef.current;
      if (endedId) void finalizeCall(endedId);
    });

    vapi.on("speech-start", () => {
      setFormError("");
      stopRingback();
    });

    vapi.on("message", (message: Record<string, unknown>) => {
      const type = String(message?.type || "");
      if (type === "conversation-update" && Array.isArray(message.messages)) {
        ingestVapiConversationMessages(message.messages);
        return;
      }
      if (type.includes("transcript")) {
        if (String(message.transcriptType || "") === "partial") return;
        const role = String(message.role || "");
        const content = String(message.transcript || "").trim();
        appendConversationLine(role, content);
        return;
      }
      const role = String(message?.role || (message?.message as { role?: string })?.role || "").trim();
      const nested = message?.message as { content?: string; transcript?: string } | undefined;
      const content = String(
        message?.transcript || message?.transcriptChunk || message?.content || nested?.content || nested?.transcript || "",
      ).trim();
      if (!content || !role) return;
      appendConversationLine(role, content);
    });

    vapi.on("error", (event: { message?: string; error?: { message?: string } }) => {
      const raw = String(event?.message || event?.error?.message || "Vapi call failed");
      const message = /invalid key|unauthorized|401/i.test(raw)
        ? "Invalid Vapi public key. In admin → Integrations → Vapi, paste the Public Key (not the private API key), then Save."
        : raw;
      setFormError(message);
      setStatus("error");
    });

    vapiRef.current = vapi;

    const overrides: {
      firstMessage?: string;
      variableValues?: Record<string, string>;
      model?: { messages?: Array<{ role: string; content: string }> };
    } = {
      variableValues: vapiSession.variable_values || {},
    };
    if (systemPrompt) {
      overrides.model = {
        messages: [{ role: "system", content: systemPrompt }],
      };
    }
    if (vapiSession.first_message) {
      overrides.firstMessage = vapiSession.first_message;
    }

    setStatus("connecting");
    if (vapiConnectTimeoutRef.current) window.clearTimeout(vapiConnectTimeoutRef.current);
    vapiConnectTimeoutRef.current = window.setTimeout(() => {
      setFormError(
        "Vapi did not connect in time. Check your assistant ID, Vapi public key (Integrations), and allow microphone access.",
      );
      setStatus("error");
      try {
        vapi.stop();
      } catch {
        /* ignore */
      }
    }, 25000);

    await vapi.start(assistantId, overrides);
  };

  const startTelnyxBrowserCall = async (
    newCallId: string,
    assistantId: string,
    lead: { contact_name: string; company_name: string; email: string; phone?: string },
    telnyxSession: {
      custom_headers?: Array<{ name: string; value: string }>;
      phone_e164?: string | null;
    } = {},
  ) => {
    const cleanAssistantId = String(assistantId || "").trim();
    if (!cleanAssistantId) {
      throw new Error("Telnyx assistant ID is missing. Save it in admin → Front page call leads.");
    }
    if (telnyxStartingRef.current) return;
    telnyxStartingRef.current = true;

    const markLive = () => {
      if (callStartedAtRef.current !== 0) return;
      callStartedAtRef.current = Date.now();
      setSeconds(0);
      setStatus("live");
      setFormError("");
      if (telnyxConnectTimeoutRef.current) {
        window.clearTimeout(telnyxConnectTimeoutRef.current);
        telnyxConnectTimeoutRef.current = null;
      }
    };

    const attachRemoteAudio = (remoteStream?: MediaStream | null) => {
      if (!remoteStream || !telnyxAudioRef.current) return;
      const audioEl = telnyxAudioRef.current;
      const onAgentAudio = () => {
        stopRingback();
        audioEl.removeEventListener("playing", onAgentAudio);
      };
      audioEl.addEventListener("playing", onAgentAudio);
      audioEl.srcObject = remoteStream;
      void audioEl.play().catch(() => undefined);
    };

    const attachLocalRecorder = (localStream?: MediaStream | null) => {
      if (voiceProviderRef.current === "telnyx") return;
      if (!localStream) return;
      streamRef.current = localStream;
      if (!recorderRef.current || recorderRef.current.state === "inactive") {
        startMicRecorder(localStream);
        try {
          recorderRef.current?.start(120);
        } catch {
          /* recorder may already be running */
        }
      }
    };

    const attachTelnyxMixedRecorder = (localStream?: MediaStream | null, remoteStream?: MediaStream | null) => {
      if (voiceProviderRef.current !== "telnyx" || telnyxRecorderStartedRef.current) return;
      if (!localStream && !remoteStream) return;
      if (telnyxMixAudioContextRef.current) {
        void telnyxMixAudioContextRef.current.close().catch(() => undefined);
        telnyxMixAudioContextRef.current = null;
      }
      const mixContext = new AudioContext();
      telnyxMixAudioContextRef.current = mixContext;
      const destination = mixContext.createMediaStreamDestination();
      if (localStream) {
        mixContext.createMediaStreamSource(localStream).connect(destination);
        streamRef.current = localStream;
      }
      if (remoteStream) {
        mixContext.createMediaStreamSource(remoteStream).connect(destination);
      }
      startMicRecorder(destination.stream);
      try {
        recorderRef.current?.start(250);
        telnyxRecorderStartedRef.current = true;
      } catch {
        /* recorder may already be running */
      }
    };

    try {
      await unlockAudioPlayback();

      const { TelnyxAIAgent } = await import("@telnyx/ai-agent-lib");
      const agent = new TelnyxAIAgent({
        agentId: cleanAssistantId,
        environment: "production",
        vad: {
          volumeThreshold: 12,
          silenceDurationMs: 700,
          minSpeechDurationMs: 120,
        },
      });
      telnyxAgentRef.current = agent;

      agent.on("transcript.item", (item: { role?: string; content?: string }) => {
        const role = String(item?.role || "").toLowerCase();
        const content = String(item?.content || "").trim();
        if (!content) return;
        appendConversationLine(role === "user" ? "user" : "assistant", content);
      });

      agent.on(
        "conversation.update",
        (notification: { call?: { remoteStream?: MediaStream; localStream?: MediaStream; state?: string } }) => {
          const call = notification?.call;
          attachRemoteAudio(call?.remoteStream);
          attachTelnyxMixedRecorder(call?.localStream, call?.remoteStream);
          const state = String(call?.state || "").toLowerCase();
          if (state === "active" || state === "ringing" || state === "trying" || state === "early") {
            markLive();
          }
          if (state === "hangup" || state === "destroy") {
            const endedId = callIdRef.current;
            if (endedId && !finalizedRef.current) {
              setStatus("ended");
              void finalizeCall(endedId);
            }
          }
        },
      );

      agent.on("conversation.agent.state", (data: { state?: string }) => {
        const state = String(data?.state || "").toLowerCase();
        if (state === "speaking") {
          stopRingback();
        }
        if (state === "speaking" || state === "listening" || state === "thinking") {
          markLive();
        }
      });

      agent.on("agent.connected", (data: { callReportId?: string | null }) => {
        telnyxProviderCallIdRef.current = String(data?.callReportId || "").trim();
      });

      agent.on("agent.error", (error: Error) => {
        const raw = String(error?.message || "Telnyx voice call failed");
        const message = /auth|login|46001|46002|46003|credential|incorrect/i.test(raw)
          ? "Telnyx could not connect. Confirm assistant ID in admin and Telnyx API key under Integrations."
          : raw;
        setFormError(message);
        setStatus("error");
        if (telnyxConnectTimeoutRef.current) {
          window.clearTimeout(telnyxConnectTimeoutRef.current);
          telnyxConnectTimeoutRef.current = null;
        }
      });

      agent.on("agent.disconnected", () => {
        const endedId = callIdRef.current;
        if (!endedId || finalizedRef.current) return;
        if (callStartedAtRef.current > 0) {
          setStatus("ended");
          void finalizeCall(endedId);
        } else {
          setFormError("Telnyx disconnected before the call could start. Check assistant ID and try again.");
          setStatus("error");
        }
      });

      if (telnyxConnectTimeoutRef.current) window.clearTimeout(telnyxConnectTimeoutRef.current);
      telnyxConnectTimeoutRef.current = window.setTimeout(() => {
        setFormError("Telnyx did not connect in time. Check assistant ID and allow microphone access.");
        setStatus("error");
      }, 45000);

      await new Promise<void>((resolve, reject) => {
        const timeout = window.setTimeout(() => {
          reject(new Error("Telnyx login timed out. Check assistant ID and try again."));
        }, 30000);
        const finish = () => {
          window.clearTimeout(timeout);
          resolve();
        };
        const fail = (err: unknown) => {
          window.clearTimeout(timeout);
          reject(err instanceof Error ? err : new Error(String(err)));
        };
        agent.once("agent.connected", finish);
        agent.once("agent.error", fail);
        void agent.connect().catch(fail);
      });

      const customHeaders =
        Array.isArray(telnyxSession.custom_headers) && telnyxSession.custom_headers.length > 0
          ? telnyxSession.custom_headers
          : [
              { name: "X-Lead-Call-Id", value: newCallId },
              { name: "X-Contact-Name", value: lead.contact_name },
              { name: "X-Company-Name", value: lead.company_name },
              { name: "X-Email", value: lead.email },
              { name: "X-Phone", value: String(telnyxSession.phone_e164 || lead.phone || "") },
              { name: "X-Phone-Raw", value: lead.phone || "" },
            ];

      await agent.startConversation({
        callerName: lead.contact_name,
        callerNumber: String(telnyxSession.phone_e164 || lead.phone || ""),
        customHeaders,
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });

    } finally {
      telnyxStartingRef.current = false;
    }
  };

  const submitLeadCall = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const cleanName = contactName.trim();
    const cleanCompany = companyName.trim();
    const cleanEmail = email.trim();
    const cleanPhone = phone.trim();

    if (!cleanName) {
      setFormError("Your name is required.");
      return;
    }
    if (!cleanCompany) {
      setFormError("Company name is required.");
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(cleanEmail)) {
      setFormError("Enter a valid email address.");
      return;
    }

    try {
      setFormError("");
      setStatus("connecting");
      await unlockAudioPlayback();
      startRingback();
      transcriptPartsRef.current = [];
      agentPartsRef.current = [];
      conversationLinesRef.current = [];
      finalizedRef.current = false;
      telnyxRecorderStartedRef.current = false;
      let clientTimezone = "";
      let clientLocale = "";
      try {
        clientTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
      } catch {
        /* ignore */
      }
      try {
        clientLocale = navigator.language || "";
      } catch {
        /* ignore */
      }
      const result = await startFrontpageTalkToUsCall({
        contact_name: cleanName,
        company_name: cleanCompany,
        email: cleanEmail,
        phone: cleanPhone,
        client_timezone: clientTimezone,
        client_locale: clientLocale,
        source: "frontpage_talk_to_us",
      });
      const newCallId = String(result?.call_id || "");
      setCallId(newCallId);
      callIdRef.current = newCallId;
      callStartedAtRef.current = 0;
      const voiceProvider = String(result?.voice_provider || "vapi").toLowerCase() as "vapi" | "telnyx";
      const resolvedProvider = voiceProvider === "telnyx" ? "telnyx" : "vapi";
      voiceProviderRef.current = resolvedProvider;
      telnyxProviderCallIdRef.current = "";
      setActiveVoiceProvider(resolvedProvider);
      if (voiceProvider === "telnyx") {
        const assistantId = String(result?.telnyx?.agent_id || "");
        if (!result?.telnyx?.configured || !assistantId) {
          throw new Error(
            String(
              result?.detail ||
                "Telnyx is not ready. In admin: choose Telnyx, save assistant ID + system prompt (syncs to Telnyx), and Telnyx API key under Integrations.",
            ),
          );
        }
        await startTelnyxBrowserCall(
          newCallId,
          assistantId,
          {
            contact_name: cleanName,
            company_name: cleanCompany,
            email: cleanEmail,
            phone: cleanPhone,
          },
          {
            custom_headers: result?.telnyx?.custom_headers,
            phone_e164: result?.telnyx?.phone_e164,
          },
        );
        return;
      }
      const vapiSession = result?.vapi;
      if (!vapiSession?.public_key || !vapiSession?.assistant_id) {
        throw new Error(
          String(result?.detail || "Vapi is not ready. In admin: Vapi assistant ID + system prompt saved, and Vapi public key under Integrations."),
        );
      }
      await startVapiVoiceCall(newCallId, {
        public_key: String(vapiSession.public_key),
        assistant_id: String(vapiSession.assistant_id),
        system_prompt: String(vapiSession.system_prompt || ""),
        variable_values: vapiSession.variable_values || {},
        first_message: vapiSession.first_message ? String(vapiSession.first_message) : undefined,
      });
    } catch (error) {
      stopRingback();
      setFormError(error instanceof Error ? error.message : "Unable to connect you to an agent. Please try again.");
      setStatus("error");
    }
  };

  const endCall = async () => {
    const endedId = callId;
    stopBrowserCall();
    await finalizeCall(endedId);
    setSeconds(0);
    setCallId("");
    callIdRef.current = "";
    setModalOpen(false);
    setStatus("idle");
  };

  const mmss = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;

  const isActive = status === "live" || status === "connecting";

  return (
    <section id="talk-to-us" className="relative py-12 md:py-16 bg-background overflow-hidden">
      <audio ref={telnyxAudioRef} autoPlay playsInline className="sr-only" aria-hidden />
      {/* Ambient background illustration */}
      <div aria-hidden className="absolute inset-0 pointer-events-none">
        <div
          className="absolute inset-0 opacity-[0.5]"
          style={{
            background:
              "radial-gradient(ellipse 60% 70% at 50% 50%, color-mix(in oklab, var(--primary) 10%, transparent), transparent 70%)",
          }}
        />
        <div
          className="absolute inset-0 opacity-[0.05]"
          style={{
            backgroundImage: "radial-gradient(currentColor 1px, transparent 1px)",
            backgroundSize: "22px 22px",
            color: "var(--heading)",
            maskImage: "radial-gradient(ellipse 60% 70% at 50% 50%, #000 30%, transparent 80%)",
            WebkitMaskImage:
              "radial-gradient(ellipse 60% 70% at 50% 50%, #000 30%, transparent 80%)",
          }}
        />
        {/* Concentric rings emanating from center */}
        <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2">
          <div className="relative w-[520px] h-[520px]">
            {[0, 1, 2, 3].map((i) => (
              <span
                key={i}
                className="absolute inset-0 rounded-full border border-primary/15"
                style={{
                  animation: `ring-pulse 4s ease-out ${i * 1}s infinite`,
                }}
              />
            ))}
          </div>
        </div>
      </div>

      <style>{`
        @keyframes ring-pulse {
          0% { transform: scale(0.4); opacity: 0; }
          20% { opacity: 0.7; }
          100% { transform: scale(1); opacity: 0; }
        }
        @keyframes eq-bar {
          0%, 100% { transform: scaleY(0.25); }
          50% { transform: scaleY(1); }
        }
      `}</style>

      <div className="relative mx-auto max-w-6xl px-6">
        <div className="grid md:grid-cols-2 gap-10 md:gap-12 items-center">
          {/* LEFT — copy */}
          <div className="text-left">
            <span className="eyebrow">Live demo</span>
            <h2 className="mt-3 text-3xl md:text-4xl font-bold tracking-tight text-heading">
              Talk to us
            </h2>
            <p className="mt-3 text-base md:text-[17px] text-body max-w-md leading-relaxed">
              Test our AI calling experience in real time and hear how VOXBULK speaks with your
              customers. Click to start a live demo call.
            </p>
            <p className="mt-4 text-xs text-muted-text">
              No signup required · Uses your browser microphone
            </p>
          </div>

          {/* RIGHT — equalizer + button */}
          <div className="relative flex flex-col items-center justify-center">
            <div className="flex items-end justify-center gap-2 h-28 md:h-32">
              {Array.from({ length: 21 }).map((_, i) => {
                const heights = [
                  40, 70, 52, 92, 62, 104, 78, 56, 88, 66, 112, 66, 88, 56, 78, 104, 62, 92, 52, 70,
                  40,
                ];
                const delay = (i % 7) * 0.12;
                return (
                  <span
                    key={i}
                    className="w-2.5 rounded-full bg-gradient-to-t from-primary/60 to-primary"
                    style={{
                      height: `${heights[i]}px`,
                      transformOrigin: "bottom",
                      animation: isActive
                        ? `eq-bar 0.9s ease-in-out ${delay}s infinite`
                        : `eq-bar 2.4s ease-in-out ${delay}s infinite`,
                      opacity: isActive ? 1 : 0.55,
                    }}
                  />
                );
              })}
            </div>

            <div className="mt-9 flex flex-col items-center gap-3">
              {status === "idle" && (
                <button onClick={openLeadModal} className="btn-primary group text-base px-8 py-4">
                  <PhoneCall className="w-5 h-5" />
                  Talk to us
                  <ArrowRight className="w-5 h-5 transition-transform group-hover:translate-x-0.5" />
                </button>
              )}
              {status === "connecting" && (
                <button disabled className="btn-primary opacity-80">
                  <span className="w-2 h-2 rounded-full bg-white animate-ping" />
                  Connecting you to our agent…
                </button>
              )}
              {status === "live" && (
                <div className="flex flex-col items-center gap-3">
                  <p className="text-xs text-muted-text">You should hear the agent. Speak after they greet you.</p>
                  <div className="inline-flex items-center gap-3 rounded-full border border-border bg-card px-5 py-2.5 shadow-elegant">
                    <span className="relative flex w-2.5 h-2.5">
                      <span className="absolute inset-0 rounded-full bg-primary opacity-60 animate-ping" />
                      <span className="relative w-2.5 h-2.5 rounded-full bg-primary" />
                    </span>
                    <span className="text-sm font-semibold text-heading">Live · {mmss}</span>
                  </div>
                  <button onClick={endCall} className="btn-outline">
                    End call
                  </button>
                </div>
              )}
              {status === "ended" && (
                <p className="text-sm text-muted-text">Call ended. Thanks for trying VOXBULK.</p>
              )}
              {status === "error" && (
                <div className="flex flex-col items-center gap-3">
                  <p className="text-sm text-destructive">
                    We could not connect you to an agent.
                  </p>
                  <button onClick={openLeadModal} className="btn-outline">
                    Try again
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {modalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center px-4 py-6">
          <button
            type="button"
            aria-label="Close talk to us popup"
            className="absolute inset-0 bg-heading/50 backdrop-blur-sm"
            onClick={closeLeadModal}
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="talk-to-us-modal-title"
            className="relative w-full max-w-lg rounded-3xl border border-border bg-white p-6 md:p-7 shadow-elevated"
          >
            {status === "live" ? (
              <div className="text-center">
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
                  <CheckCircle2 className="h-6 w-6" />
                </div>
                <h3 id="talk-to-us-modal-title" className="mt-5 text-2xl font-bold tracking-tight text-heading">
                  You&apos;re connected
                </h3>
                <p className="mt-2 text-sm text-body">Our agent is now on the line.</p>
                <div className="mt-5 inline-flex items-center gap-3 rounded-full border border-border bg-card px-5 py-2.5 shadow-elegant">
                  <span className="relative flex h-2.5 w-2.5">
                    <span className="absolute inset-0 rounded-full bg-primary opacity-60 animate-ping" />
                    <span className="relative h-2.5 w-2.5 rounded-full bg-primary" />
                  </span>
                  <span className="text-sm font-semibold text-heading">In call · {mmss}</span>
                </div>
                {callId && <p className="mt-3 text-xs text-muted-text">Call ID: {callId}</p>}
                <div className="mt-7 flex justify-center gap-3">
                  <button type="button" className="btn-outline" onClick={closeLeadModal}>
                    Close
                  </button>
                  <button type="button" className="btn-primary" onClick={endCall}>
                    End call
                  </button>
                </div>
              </div>
            ) : (
              <form onSubmit={submitLeadCall}>
                <span className="eyebrow">Live demo</span>
                <h3 id="talk-to-us-modal-title" className="mt-3 text-2xl font-bold tracking-tight text-heading">
                  Talk to us now
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-body">
                  Share a few details and we&apos;ll connect you to our voice agent.
                </p>

                <div className="mt-6 space-y-4">
                  <label className="block">
                    <span className="text-sm font-semibold text-heading">Your name</span>
                    <input
                      required
                      value={contactName}
                      onChange={(event) => setContactName(event.target.value)}
                      className="mt-2 h-11 w-full rounded-xl border border-input bg-background px-3 text-sm text-heading shadow-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15"
                      placeholder="First name"
                    />
                  </label>
                  <label className="block">
                    <span className="text-sm font-semibold text-heading">Company name</span>
                    <input
                      required
                      value={companyName}
                      onChange={(event) => setCompanyName(event.target.value)}
                      className="mt-2 h-11 w-full rounded-xl border border-input bg-background px-3 text-sm text-heading shadow-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15"
                      placeholder="Your company"
                    />
                  </label>
                  <label className="block">
                    <span className="text-sm font-semibold text-heading">Email address</span>
                    <input
                      required
                      type="email"
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      className="mt-2 h-11 w-full rounded-xl border border-input bg-background px-3 text-sm text-heading shadow-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15"
                      placeholder="you@company.com"
                    />
                  </label>
                  <label className="block">
                    <span className="text-sm font-semibold text-heading">Phone number</span>
                    <input
                      value={phone}
                      onChange={(event) => setPhone(event.target.value)}
                      className="mt-2 h-11 w-full rounded-xl border border-input bg-background px-3 text-sm text-heading shadow-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15"
                      placeholder="Optional"
                    />
                  </label>
                </div>

                <p className="mt-4 text-xs text-muted-text">
                  This call may be recorded for quality and training.
                </p>
                {status === "connecting" && (
                  <p className="mt-3 text-xs text-muted-text">
                    You&apos;ll hear a short connecting tone until our agent starts speaking.
                  </p>
                )}
                {formError && <p className="mt-4 text-[13.5px] text-destructive">{formError}</p>}

                <div className="mt-7 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
                  <button type="button" className="btn-outline justify-center" onClick={closeLeadModal}>
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={status === "connecting"}
                    className="btn-primary justify-center disabled:cursor-not-allowed disabled:opacity-70"
                  >
                    {status === "connecting" ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Connecting you to an agent…
                      </>
                    ) : (
                      <>
                        <PhoneCall className="h-4 w-4" />
                        Talk to us
                      </>
                    )}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

export default function VOXBULKHome() {
  return (
    <div className="bg-background text-body antialiased">
      <Navbar />
      <main>
        <Hero />
        <DeferredMount minHeight={420}>
          <TalkToUs />
        </DeferredMount>
        <TrustBar />
        <Problem />
        <HowItWorks />
        <Features />
        <Transparency />
        <DeferredMount minHeight={520}>
          <Pricing />
        </DeferredMount>
        <DeferredMount minHeight={480}>
          <ROICalc />
        </DeferredMount>
        <DeferredMount minHeight={560}>
          <DemoWizard />
        </DeferredMount>
        <Industries />
        <Testimonial />
        <BottomCTA />
      </main>
      <Footer />
    </div>
  );
}
